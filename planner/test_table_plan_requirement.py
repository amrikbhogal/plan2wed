from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import WeddingEventForm
from .models import Member, SeatingTable, WeddingBudget


class TablePlanRequirementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='table-preference')
        member = Member.objects.create(user=self.user, first_name='Alex', last_name='Smith', email='tables@example.com')
        self.budget = WeddingBudget.objects.create(member=member)
        self.event = self.budget.events.create(name='Reception')
        self.url = reverse('event_detail', args=[self.event.pk])
        self.table_url = reverse('table_plan', args=[self.event.pk])
        self.client.force_login(self.user)

    def test_toggle_preserves_tables_and_blocks_disabled_plan(self):
        table = SeatingTable.objects.create(event=self.event, name='Family', capacity=8)
        self.assertContains(self.client.get(self.url), self.table_url)
        for required in (False, True):
            response = self.client.post(self.url, {
                'action': 'set_table_plan_requirement', 'requires_table_plan': str(required),
            })
            self.assertRedirects(response, self.url)
            self.event.refresh_from_db()
            self.assertEqual(self.event.requires_table_plan, required)
            self.assertTrue(self.event.seating_tables.filter(pk=table.pk).exists())
            if required:
                self.assertContains(self.client.get(self.url), self.table_url)
            else:
                self.assertNotContains(self.client.get(self.url), self.table_url)
                self.assertRedirects(self.client.get(self.table_url), self.url)
                self.assertRedirects(self.client.post(self.table_url, {'action': 'delete_table', 'table_id': table.pk}), self.url)

    def test_invalid_choice_is_rejected(self):
        response = self.client.post(self.url, {'action': 'set_table_plan_requirement', 'requires_table_plan': 'invalid'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['table_plan_form'].errors)
        self.event.refresh_from_db()
        self.assertTrue(self.event.requires_table_plan)

    def test_event_form_saves_no(self):
        form = WeddingEventForm(data={
            'name': 'Picnic', 'requires_table_plan': 'False', 'other_spent': '0', 'other_pending': '0',
        }, budget=self.budget)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.save().requires_table_plan)

    def test_other_member_cannot_change_preference(self):
        self.client.force_login(get_user_model().objects.create_user(username='other-table-member'))
        Member.objects.create(user=get_user_model().objects.get(username='other-table-member'), first_name='Other', last_name='Member', email='other-tables@example.com')
        self.assertEqual(self.client.post(self.url, {'action': 'set_table_plan_requirement', 'requires_table_plan': 'False'}).status_code, 404)
        self.event.refresh_from_db()
        self.assertTrue(self.event.requires_table_plan)
