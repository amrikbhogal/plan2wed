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
