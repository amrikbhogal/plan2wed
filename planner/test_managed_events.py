from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import WeddingBudgetForm
from .models import EventTemplate, Member, WeddingBudget


class ManagedSuggestedEventTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='managed-events')
        member = Member.objects.create(user=user, email='managed@example.com')
        self.budget = WeddingBudget.objects.create(member=member)
        self.anand = EventTemplate.objects.get(name='Anand Karaj')
        self.reception = EventTemplate.objects.get(name='Reception')
        self.client.force_login(user)

    def states(self):
        response = self.client.get(reverse('event_catalogue'))
        return {item.pk: item.managed_in_details for item in response.context['templates']}

    def test_no_disables_only_anand_karaj(self):
        states = self.states()
        self.assertTrue(states[self.anand.pk])
        self.assertFalse(states[self.reception.pk])

    def test_yes_disables_both_and_changing_back_enables_reception(self):
        self.budget.has_separate_meal = True
        self.budget.save()
        states = self.states()
        self.assertTrue(states[self.anand.pk])
        self.assertTrue(states[self.reception.pk])
        self.budget.has_separate_meal = False
        self.budget.save()
        self.assertFalse(self.states()[self.reception.pk])

    def test_disabled_templates_cannot_be_added_by_direct_post(self):
        self.budget.has_separate_meal = True
        self.budget.save()
        count = self.budget.events.count()
        for template in [self.anand, self.reception]:
            url = reverse('event_template_detail', args=[template.pk])
            self.assertRedirects(self.client.post(url, {}), reverse('event_catalogue'))
        self.assertEqual(self.budget.events.count(), count)

    def test_help_text_uses_reception_wording(self):
        self.assertTrue(WeddingBudgetForm().fields['has_separate_meal'].help_text.startswith('Choose Yes to add a Reception event.'))

    def test_separate_reception_reuses_existing_event(self):
        reception = self.budget.events.create(name='Reception')
        self.budget.has_separate_meal = True
        self.budget.save()
        reception.refresh_from_db()
        self.assertTrue(reception.is_wedding_meal)
        self.assertEqual(self.budget.events.filter(is_wedding_meal=True).get(), reception)
        self.assertEqual(self.budget.events.filter(name='Reception').count(), 1)

    def test_rename_all_legacy_reception_name_variants(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        from .models import WeddingEvent
        names = ['Wedding Meal /Reception', 'Wedding Meal/Reception',
                 'Wedding Meal / Reception', 'wedding meal / reception',
                 ' Wedding   Meal/ RECEPTION ']
        events = WeddingEvent.objects.bulk_create([
            WeddingEvent(budget=self.budget, name=name, notes='Keep my notes') for name in names
        ])
        custom = self.budget.events.create(name='Family meal')
        migration = import_module('planner.migrations.0025_normalize_reception_names')
        from types import SimpleNamespace
        migration.rename_reception_variants(apps, SimpleNamespace(connection=connection))
        for event in events:
            event.refresh_from_db()
            self.assertEqual(event.name, 'Reception')
            self.assertEqual(event.notes, 'Keep my notes')
        custom.refresh_from_db()
        self.assertEqual(custom.name, 'Family meal')
