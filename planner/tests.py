from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Member, ShoppingListItem, WeddingBudget, WeddingGuest


class WeddingDayTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='couple', password='test-password')
        self.member = Member.objects.create(user=self.user, first_name='A', last_name='B', email='couple@example.com')
        self.budget = WeddingBudget.objects.create(member=self.member)
        self.client.force_login(self.user)

    def test_date_creates_one_event_and_preserves_guests_and_shopping(self):
        self.assertFalse(self.budget.events.exists())
        self.budget.wedding_date = date(2027, 6, 12)
        self.budget.save()
        event = self.budget.events.get(is_wedding_day=True)
        guest = WeddingGuest.objects.create(budget=self.budget, first_name='Guest')
        guest.events.add(event)
        ShoppingListItem.objects.create(event=event, name='Flowers', quantity=2, unit_cost=Decimal('25'))
        self.budget.wedding_date = date(2027, 6, 19)
        self.budget.save()
        self.budget.save()
        event.refresh_from_db()
        self.assertEqual(self.budget.events.count(), 1)
        self.assertEqual(event.event_date, self.budget.wedding_date)
        self.assertEqual(event.guests.get(), guest)
        self.assertEqual(event.pending, Decimal('50'))
        response = self.client.get(reverse('member_portal'))
        self.assertEqual(len(response.context['timeline_items']), 1)
        self.assertContains(response, reverse('event_detail', args=[event.pk]))
        detail = self.client.get(reverse('event_detail', args=[event.pk]))
        self.assertContains(detail, reverse('event_shopping_list', args=[event.pk]))
        self.assertContains(detail, f'?event={event.pk}')
        self.assertContains(self.client.get(reverse('guest_list')), 'Wedding Day')
        self.assertContains(self.client.get(reverse('event_shopping_list', args=[event.pk])), 'Flowers')

    def test_editing_event_updates_wedding_date_and_keeps_custom_details(self):
        self.budget.wedding_date = date(2027, 6, 12)
        self.budget.save()
        event = self.budget.events.get()
        event.name = 'Our Anand Karaj'
        event.event_date = date(2027, 6, 20)
        event.save()
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.wedding_date, event.event_date)
        self.budget.save()
        event.refresh_from_db()
        self.assertEqual(event.name, 'Our Anand Karaj')
        self.assertEqual(self.budget.events.count(), 1)

    def test_clearing_date_keeps_event_and_its_shopping(self):
        self.budget.wedding_date = date(2027, 6, 12)
        self.budget.save()
        event = self.budget.events.get()
        ShoppingListItem.objects.create(event=event, name='Flowers')
        self.budget.wedding_date = None
        self.budget.save()
        event.refresh_from_db()
        self.assertIsNone(event.event_date)
        self.assertEqual(event.shopping_items.count(), 1)

    def test_separate_meal_is_optional_and_keeps_its_own_plans(self):
        self.budget.wedding_date = date(2027, 6, 12)
        self.budget.has_separate_meal = True
        self.budget.save()
        meal = self.budget.events.get(is_wedding_meal=True)
        self.assertEqual(meal.event_date, self.budget.wedding_date)
        guest = WeddingGuest.objects.create(budget=self.budget, first_name='Meal guest')
        guest.events.add(meal)
        ShoppingListItem.objects.create(event=meal, name='Table settings')
        self.budget.wedding_date = date(2027, 6, 19)
        self.budget.save()
        meal.refresh_from_db()
        self.assertEqual(meal.event_date, self.budget.wedding_date)
        meal.name = 'Family lunch'
        meal.event_date = date(2027, 6, 20)
        meal.save()
        self.budget.refresh_from_db()
        self.budget.wedding_date = date(2027, 6, 21)
        self.budget.save()
        meal.refresh_from_db()
        self.assertEqual(meal.event_date, date(2027, 6, 20))
        self.assertEqual(meal.name, 'Family lunch')
        self.budget.has_separate_meal = False
        self.budget.save()
        self.budget.has_separate_meal = True
        self.budget.save()
        self.assertEqual(self.budget.events.filter(is_wedding_meal=True).count(), 1)
        self.assertEqual(meal.guests.get(), guest)
        self.assertEqual(meal.shopping_items.count(), 1)
        ceremony = self.budget.events.get(is_wedding_day=True)
        self.assertFalse(ceremony.guests.exists())

    def test_wedding_details_question_creates_meal_event(self):
        response = self.client.post(reverse('member_portal'), {
            'action': 'save_budget', 'wedding_date': '2027-06-12',
            'has_separate_meal': 'True', 'meal_date': '', 'allocated': '1000',
        })
        self.assertEqual(response.status_code, 302)
        meal = self.budget.events.get(is_wedding_meal=True)
        self.assertEqual(meal.event_date, date(2027, 6, 12))
        response = self.client.get(reverse('member_portal'))
        self.assertContains(response, 'Will you have a separate meal or reception')
        self.assertContains(response, 'Wedding Meal / Reception')
        self.assertEqual(len(response.context['timeline_items']), 2)
        self.assertContains(self.client.get(reverse('guest_list')), meal.name)
        self.assertEqual(self.client.get(reverse('event_shopping_list', args=[meal.pk])).status_code, 200)

    def test_meal_can_be_planned_before_wedding_date_is_known(self):
        self.budget.has_separate_meal = True
        self.budget.save()
        meal = self.budget.events.get(is_wedding_meal=True)
        self.assertIsNone(meal.event_date)
        self.budget.wedding_date = date(2027, 6, 12)
        self.budget.save()
        meal.refresh_from_db()
        self.assertEqual(meal.event_date, self.budget.wedding_date)


class TablePlanTests(TestCase):
    def setUp(self):
        from .models import WeddingEvent
        self.user = get_user_model().objects.create_user(username='tables', password='test-password')
        self.member = Member.objects.create(user=self.user, first_name='A', last_name='B', email='tables@example.com')
        self.budget = WeddingBudget.objects.create(member=self.member)
        self.event = WeddingEvent.objects.create(budget=self.budget, name='Reception')
        self.guest = WeddingGuest.objects.create(budget=self.budget, first_name='Alice')
        self.other_guest = WeddingGuest.objects.create(budget=self.budget, first_name='Bob')
        self.event.guests.add(self.guest, self.other_guest)
        self.url = reverse('table_plan', args=[self.event.pk])
        self.client.force_login(self.user)

    def save_table(self, **changes):
        data = {'action': 'save_table', 'name': 'Table 1', 'capacity': '2', 'guests': [self.guest.pk], 'notes': ''}
        data.update(changes)
        return self.client.post(self.url, data)

    def test_add_edit_move_and_delete_table(self):
        from .models import SeatingTable, SeatingAssignment
        self.assertEqual(self.save_table().status_code, 302)
        table = SeatingTable.objects.get()
        response = self.client.get(self.url)
        self.assertContains(response, 'Table 1')
        self.assertEqual(response.context['seated_count'], 1)
        self.assertEqual(list(response.context['unseated_guests']), [self.other_guest])
        self.assertContains(self.client.get(self.url + f'?edit={table.pk}'), 'checked')
        self.assertEqual(self.save_table(table_id=table.pk, name='Family', guests=[self.guest.pk, self.other_guest.pk]).status_code, 302)
        self.assertEqual(self.save_table(name='Table 2', guests=[self.guest.pk]).status_code, 302)
        self.assertEqual(table.assignments.count(), 1)
        self.assertEqual(SeatingAssignment.objects.filter(event=self.event, guest=self.guest).count(), 1)
        response = self.client.post(self.url, {'action': 'delete_table', 'table_id': table.pk})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(WeddingGuest.objects.filter(pk=self.other_guest.pk).exists())
        self.assertIn(self.other_guest, self.client.get(self.url).context['unseated_guests'])

    def test_capacity_and_duplicate_name_validation_preserve_assignments(self):
        from .models import SeatingTable
        self.save_table()
        table = SeatingTable.objects.get()
        response = self.save_table(table_id=table.pk, capacity=1, guests=[self.guest.pk, self.other_guest.pk])
        self.assertContains(response, 'more guests than seats')
        self.assertEqual(table.assignments.count(), 1)
        self.assertContains(self.save_table(), 'already has a table with that name')
        self.assertContains(self.save_table(name='Empty capacity', capacity=0), 'greater than or equal to 1')
        self.assertEqual(SeatingTable.objects.count(), 1)

    def test_ineligible_guests_cannot_be_seated(self):
        from .models import SeatingTable
        outsider = WeddingGuest.objects.create(budget=self.budget, first_name='Not invited')
        self.assertEqual(self.save_table(guests=[outsider.pk]).status_code, 200)
        self.guest.rsvp_status = WeddingGuest.RSVPStatus.DECLINED
        self.guest.save()
        self.assertEqual(self.save_table().status_code, 200)
        self.assertFalse(SeatingTable.objects.exists())

    def test_access_is_scoped_to_owner_and_event(self):
        from .models import SeatingTable, WeddingEvent
        self.save_table()
        table = SeatingTable.objects.get()
        other_member = Member.objects.create(first_name='Other', last_name='Account', email='other-tables@example.com')
        other_budget = WeddingBudget.objects.create(member=other_member)
        other_event = WeddingEvent.objects.create(budget=other_budget, name='Private')
        self.assertEqual(self.client.get(reverse('table_plan', args=[other_event.pk])).status_code, 404)
        same_owner_event = WeddingEvent.objects.create(budget=self.budget, name='Another event')
        url = reverse('table_plan', args=[same_owner_event.pk])
        self.assertEqual(self.client.post(url, {'action': 'delete_table', 'table_id': table.pk}).status_code, 404)
        self.assertTrue(SeatingTable.objects.filter(pk=table.pk).exists())
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_seating_is_independent_between_events(self):
        from .models import WeddingEvent, SeatingAssignment
        self.save_table()
        second = WeddingEvent.objects.create(budget=self.budget, name='Dinner')
        second.guests.add(self.guest)
        self.client.post(reverse('table_plan', args=[second.pk]), {'action': 'save_table', 'name': 'Dinner table', 'capacity': 1, 'guests': [self.guest.pk]})
        self.assertEqual(SeatingAssignment.objects.filter(guest=self.guest).count(), 2)

    def test_removed_or_declined_guests_are_not_counted_as_seated(self):
        self.save_table()
        self.event.guests.remove(self.guest)
        self.assertFalse(self.guest.seating_assignments.exists())
        response = self.client.get(self.url)
        self.assertEqual(response.context['seated_count'], 0)
        self.assertEqual(response.context['tables'][0].available_seats, 2)


    def test_declining_rsvp_releases_seat(self):
        self.save_table()
        self.guest.rsvp_status = WeddingGuest.RSVPStatus.DECLINED
        self.guest.save()
        self.assertFalse(self.guest.seating_assignments.exists())


class SpendingStatementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='statement-owner')
        self.member = Member.objects.create(user=self.user, first_name='Alex', last_name='Smith', email='statement@example.com')
        self.budget = WeddingBudget.objects.create(member=self.member, allocated=Decimal('1000'))
        self.client.force_login(self.user)

    def test_statement_includes_all_spending_and_separates_pending(self):
        event = self.budget.events.create(name='Ceremony', other_spent=Decimal('125.50'), other_pending=Decimal('40'))
        ShoppingListItem.objects.create(event=event, name='Purchased flowers', quantity=3, unit_cost=Decimal('12.25'), is_purchased=True)
        ShoppingListItem.objects.create(event=event, name='Unpurchased cake', unit_cost=Decimal('80'))
        second = self.budget.events.create(name='Reception', other_spent=Decimal('200'))
        ShoppingListItem.objects.create(event=second, name='Purchased candles', quantity=2, unit_cost=Decimal('5'), is_purchased=True)
        response = self.client.get(reverse('spending_statement'))
        self.assertEqual(response.context['spent'], Decimal('372.25'))
        self.assertEqual(response.context['pending'], Decimal('120'))
        self.assertEqual(response.context['remaining'], Decimal('507.75'))
        self.assertEqual(response.context['spent'], self.budget.spent)
        self.assertEqual(response.context['sections'][0]['budget_percentage'], Decimal('16.225'))
        self.assertContains(response, '16.23%')
        self.assertContains(response, '21.00%')
        self.assertContains(response, 'Purchased flowers')
        self.assertContains(response, 'Purchased candles')
        self.assertContains(response, 'Other event spending')
        self.assertNotContains(response, 'Unpurchased cake')
        self.assertContains(self.client.get(reverse('member_portal')), reverse('spending_statement'))

    def test_event_percentage_handles_unset_budget_and_overspending(self):
        self.budget.events.create(name='Reception', other_spent=Decimal('1250'))
        response = self.client.get(reverse('spending_statement'))
        self.assertContains(response, '125.00%')
        self.budget.allocated = Decimal('0')
        self.budget.save()
        response = self.client.get(reverse('spending_statement'))
        self.assertContains(response, 'N/A (total budget not set)')

    def test_statement_only_shows_current_members_costs(self):
        other = Member.objects.create(first_name='Other', last_name='Couple', email='other-statement@example.com')
        budget = WeddingBudget.objects.create(member=other)
        event = budget.events.create(name='Private event', other_spent=Decimal('999'))
        ShoppingListItem.objects.create(event=event, name='Private purchase', is_purchased=True, unit_cost=Decimal('200'))
        response = self.client.get(reverse('spending_statement'), {'member_id': other.pk})
        self.assertNotContains(response, 'Private event')
        self.assertNotContains(response, 'Private purchase')
        self.assertEqual(response.context['spent'], Decimal('0'))

    def test_empty_statement_and_missing_budget(self):
        self.budget.delete()
        response = self.client.get(reverse('spending_statement'))
        self.assertContains(response, 'No spending recorded yet')
        self.assertEqual(response.context['spent'], Decimal('0'))

    def test_statement_requires_login_and_member_profile(self):
        self.client.logout()
        self.assertRedirects(self.client.get(reverse('spending_statement')), reverse('login') + '?next=' + reverse('spending_statement'))
        self.client.force_login(get_user_model().objects.create_user(username='no-member'))
        self.assertRedirects(self.client.get(reverse('spending_statement')), reverse('member_portal'))


class EventDetailTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='event-owner')
        self.member = Member.objects.create(user=self.user, first_name='Alex', last_name='Smith', email='event-owner@example.com')
        self.budget = WeddingBudget.objects.create(member=self.member)
        self.event = self.budget.events.create(name='Reception', other_spent=Decimal('125'), notes='Evening celebration')
        self.url = reverse('event_detail', args=[self.event.pk])
        self.client.force_login(self.user)

    def test_event_page_contains_details_and_actions(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Evening celebration')
        self.assertContains(response, '125.00')
        for name in ['event_shopping_list', 'table_plan', 'event_edit']:
            self.assertContains(response, reverse(name, args=[self.event.pk]))
        self.assertContains(response, f'?event={self.event.pk}')
        self.assertContains(response, 'name="action" value="delete_event"')
        dashboard = self.client.get(reverse('member_portal'))
        self.assertContains(dashboard, self.url)
        self.assertNotContains(dashboard, reverse('event_shopping_list', args=[self.event.pk]))
        self.assertNotContains(dashboard, 'value="delete_event"')

    def test_event_subpages_link_back_to_event(self):
        for name in ['event_shopping_list', 'table_plan', 'event_edit']:
            self.assertContains(self.client.get(reverse(name, args=[self.event.pk])), self.url)
        self.assertContains(self.client.get(reverse('guest_list'), {'event': self.event.pk}), self.url)

    def test_event_page_and_deletion_are_private(self):
        other = Member.objects.create(first_name='Other', last_name='Couple', email='private-event@example.com')
        budget = WeddingBudget.objects.create(member=other)
        event = budget.events.create(name='Private event')
        url = reverse('event_detail', args=[event.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {'action': 'delete_event'}).status_code, 404)
        self.assertTrue(budget.events.filter(pk=event.pk).exists())
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_delete_from_event_page(self):
        self.client.get(self.url)
        self.assertTrue(self.budget.events.filter(pk=self.event.pk).exists())
        self.assertRedirects(self.client.post(self.url, {'action': 'delete_event'}), reverse('member_portal'))
        self.assertFalse(self.budget.events.filter(pk=self.event.pk).exists())


class EventDescriptionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='descriptions')
        self.member = Member.objects.create(user=self.user, first_name='A', last_name='B', email='descriptions@example.com')
        self.budget = WeddingBudget.objects.create(member=self.member)
        self.client.force_login(self.user)

    def test_all_predefined_events_have_editable_defaults(self):
        from .event_descriptions import EVENT_DESCRIPTIONS
        from .forms import WeddingEventForm
        self.assertEqual(set(WeddingEventForm.EVENT_SUGGESTIONS), set(EVENT_DESCRIPTIONS))
        for name, description in EVENT_DESCRIPTIONS.items():
            event = self.budget.events.create(name=name)
            self.assertEqual(event.description, description)
            self.assertIsNotNone(event.description_source)
        event.description = 'Our own family celebration.'
        event.save()
        event.refresh_from_db()
        self.assertEqual(event.description, 'Our own family celebration.')
        self.assertIsNone(event.description_source)
        event.description = ''
        event.save()
        event.refresh_from_db()
        self.assertEqual(event.description, '')

    def test_create_and_edit_description_through_form(self):
        data = {'name': 'Anand Karaj', 'description': 'Our ceremony and shared journey.',
                'other_spent': '0', 'other_pending': '0'}
        response = self.client.post(reverse('event_add'), data)
        event = self.budget.events.get()
        self.assertRedirects(response, reverse('event_detail', args=[event.pk]))
        self.assertEqual(event.description, data['description'])
        self.assertContains(self.client.get(reverse('event_detail', args=[event.pk])), data['description'])
        data['description'] = 'Updated ceremony details.'
        self.client.post(reverse('event_edit', args=[event.pk]), data)
        event.refresh_from_db()
        self.assertEqual(event.description, data['description'])

    def test_custom_event_and_safe_description_rendering(self):
        event = self.budget.events.create(name='Family lunch')
        self.assertEqual(event.description, '')
        event.description = '<script>alert(1)</script>'
        event.save()
        response = self.client.get(reverse('event_detail', args=[event.pk]))
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        response = self.client.get(reverse('event_add'))
        self.assertContains(response, 'id_description')
        self.assertContains(response, 'event-descriptions')


class ReceiptTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='receipt-user')
        member = Member.objects.create(user=self.user, first_name='A', last_name='B', email='receipt@example.com')
        self.budget = WeddingBudget.objects.create(member=member, wedding_date=date(2027, 6, 12))
        self.event = self.budget.events.get()
        self.url = reverse('event_shopping_list', args=[self.event.pk])
        self.client.force_login(self.user)

    @staticmethod
    def receipt_image():
        import io
        from PIL import Image
        buffer = io.BytesIO()
        Image.new('RGB', (200, 300), 'white').save(buffer, format='PNG')
        return buffer.getvalue()

    def scan(self):
        from unittest.mock import patch
        from django.core.files.uploadedfile import SimpleUploadedFile
        with patch('planner.views.scan_receipt', return_value='SHOP\n2 x Candles 12.00\nFlowers 20.00\nTOTAL 32.00'):
            return self.client.post(self.url, {'action': 'scan_receipt', 'image': SimpleUploadedFile('receipt.png', b'example')})

    def confirmation(self, token, **changes):
        data = {'action': 'confirm_receipt', 'receipt_token': token,
                'receipt-TOTAL_FORMS': '1', 'receipt-INITIAL_FORMS': '0',
                'receipt-0-include': 'on', 'receipt-0-name': 'Candles',
                'receipt-0-quantity': '2', 'receipt-0-unit_cost': '6.00',
                'receipt-0-supplier_name': 'Shop'}
        data.update(changes)
        return self.client.post(self.url, data)

    def test_review_does_not_change_spending_and_confirmation_updates_match(self):
        item = ShoppingListItem.objects.create(event=self.event, name='Candles', quantity=1, unit_cost=5)
        response = self.scan()
        self.assertContains(response, 'Review receipt items')
        self.assertEqual(len(response.context['receipt_rows'].forms), 2)
        self.assertEqual(self.event.spent, 0)
        token = response.context['receipt_token']
        self.assertEqual(self.confirmation(token, **{'receipt-0-existing_item': item.pk}).status_code, 302)
        item.refresh_from_db()
        self.assertTrue(item.is_purchased)
        self.assertEqual(self.event.spent, Decimal('12'))
        self.assertEqual(self.event.pending, 0)
        self.confirmation(token)
        self.assertEqual(self.event.shopping_items.count(), 1)

    def test_invalid_price_keeps_review_without_saving(self):
        token = self.scan().context['receipt_token']
        response = self.confirmation(token, **{'receipt-0-unit_cost': '-1'})
        self.assertContains(response, 'Review receipt items')
        self.assertFalse(self.event.shopping_items.exists())

    def test_match_cannot_reference_another_event(self):
        from .models import WeddingEvent
        other = WeddingEvent.objects.create(budget=self.budget, name='Other')
        item = ShoppingListItem.objects.create(event=other, name='Candles')
        token = self.scan().context['receipt_token']
        response = self.confirmation(token, **{'receipt-0-existing_item': item.pk})
        self.assertTrue(response.context['receipt_rows'].errors)
        item.refresh_from_db()
        self.assertFalse(item.is_purchased)

    def test_ocr_failure_and_invalid_file_are_recoverable(self):
        from unittest.mock import patch
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .receipts import scan_receipt
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            scan_receipt(SimpleUploadedFile('bad.png', b'not an image'))
        with patch('planner.receipts.subprocess.run', side_effect=FileNotFoundError):
            response = self.client.post(self.url, {'action': 'scan_receipt', 'image': SimpleUploadedFile('receipt.png', self.receipt_image())})
        self.assertContains(response, 'not configured')
        self.assertFalse(self.event.shopping_items.exists())

    def test_ocr_and_new_purchase(self):
        from unittest.mock import patch
        from subprocess import CompletedProcess
        from django.core.files.uploadedfile import SimpleUploadedFile
        with patch('planner.receipts.subprocess.run', return_value=CompletedProcess([], 0, b'Candles 12.00', b'')):
            response = self.client.post(self.url, {'action': 'scan_receipt', 'image': SimpleUploadedFile('receipt.png', self.receipt_image())})
        self.assertEqual(self.confirmation(response.context['receipt_token']).status_code, 302)
        self.assertEqual(self.event.spent, Decimal('12'))

    def test_receipt_text_without_upload_is_rejected(self):
        response = self.client.post(self.url, {'action': 'scan_receipt', 'text': 'Candles 12.00'})
        self.assertContains(response, 'Upload a receipt photo.')
        self.assertNotContains(response, 'name="text"')
        self.assertFalse(self.event.shopping_items.exists())

    def test_common_ocr_price_formats(self):
        from .receipts import receipt_items
        for line, expected in [
            ('Candles12.50', '12.50'),
            ('Candles 12 . 50 A', '12.50'),
            ('Flowers 1,234.50 GBP', '1234.50'),
            ('Flowers 1 234,50 €', '1234.50'),
        ]:
            with self.subTest(line=line):
                rows = receipt_items(line)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['unit_cost'], Decimal(expected))
        self.assertEqual(receipt_items('TOTAL 12.50\nVAT 2.50\nCARD 12.50'), [])

    def test_unrecognised_prices_show_extracted_text_for_diagnosis(self):
        from unittest.mock import patch
        from django.core.files.uploadedfile import SimpleUploadedFile
        with patch('planner.views.scan_receipt', return_value='Candles unreadable price'):
            response = self.client.post(self.url, {'action': 'scan_receipt', 'image': SimpleUploadedFile('receipt.png', b'example')})
        self.assertContains(response, 'No item prices were found.')
        self.assertContains(response, 'Extracted receipt text')
        self.assertContains(response, 'Candles unreadable price')
        self.assertFalse(self.event.shopping_items.exists())

    def test_phone_orientation_is_applied_before_ocr(self):
        import io
        from PIL import Image
        from subprocess import CompletedProcess
        from unittest.mock import patch
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .receipts import scan_receipt
        buffer = io.BytesIO()
        image = Image.new('RGB', (300, 100), 'white')
        exif = Image.Exif()
        exif[274] = 6
        image.save(buffer, format='JPEG', exif=exif)

        def recognise(command, **kwargs):
            with Image.open(command[1]) as prepared:
                self.assertEqual(prepared.size, (100, 300))
                self.assertEqual(prepared.mode, 'L')
            self.assertIn(command[-1], ('0', '4'))
            return CompletedProcess(command, 0, b'Candles 12.50', b'')

        with patch('planner.receipts.subprocess.run', side_effect=recognise):
            text = scan_receipt(SimpleUploadedFile('phone.jpg', buffer.getvalue()))
        self.assertEqual(text, 'Candles 12.50')

    def test_aldi_receipt_layout_preserves_quantities_and_total(self):
        from .receipts import receipt_items
        # Transcribed item lines from the supplied photo, not OCR output.
        text = """ALDI STORES
GBP
755322 LED CANDLES 3.99 B
582544 ASIAN SELECTION 1.49 A
752666 ADHESIVE MIX 0.89 B
585909 AA/AAA BATTERIES 2.49 B
2 x 0.45
625258 CHICKPEAS 0.90A
417200 CHEESE DBL G/WENSL 1.75 A
285988 LIMES 1.15 A
759884 SS FUSIL/CONCHI 1.59 A
383427 SUGAR DEMERARA 1.09 A
339792 CARROTS 500G 0.55 A
339914 RED ONIONS 0.59 A
339808 COURGETTES 1.39 A
273691 BABY CUCUMBERS 0.99 A
339817 CUT CORIANDER 0.50 A
340015 MUSHROOM CLSEDCUP 1.29 A
2 x 0.16
267186 BANANAS LOOSE 0.32 A
339750 BABY SPINACH 1.09 A
723367 LE PETIT 2.99 B
T o t a l 25.05
20 Items
Card Sales GBP 25.05
A 00.0% Net 14.69 Vat 0.00
B 20.0% Net 8.63 Vat 1.73"""
        rows = receipt_items(text)
        self.assertEqual(len(rows), 18)
        self.assertEqual(sum(row['quantity'] for row in rows), 20)
        self.assertEqual(sum(row['unit_cost'] * row['quantity'] for row in rows), Decimal('25.05'))
        self.assertEqual(rows[0]['name'], 'LED CANDLES')
        self.assertEqual(rows[4]['quantity'], 2)
        self.assertEqual(rows[4]['unit_cost'], Decimal('0.45'))
        self.assertEqual(rows[15]['quantity'], 2)
        self.assertEqual(rows[15]['unit_cost'], Decimal('0.16'))

    def test_full_resolution_phone_photo_is_resized_for_ocr(self):
        import io
        from PIL import Image
        from subprocess import CompletedProcess
        from unittest.mock import patch
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .receipts import scan_receipt
        buffer = io.BytesIO()
        with Image.new('L', (4284, 5712), 'white') as image:
            image.save(buffer, format='JPEG')

        def recognise(command, **kwargs):
            with Image.open(command[1]) as prepared:
                self.assertLessEqual(max(prepared.size), 4000)
                self.assertEqual(prepared.mode, 'L')
            return CompletedProcess(command, 0, b'LED CANDLES 3.99 B', b'')

        with patch('planner.receipts.subprocess.run', side_effect=recognise):
            text = scan_receipt(SimpleUploadedFile('phone.jpg', buffer.getvalue()))
        self.assertIn('LED CANDLES', text)

    def test_receipt_orientation_and_row_layout_are_separate(self):
        from subprocess import CompletedProcess
        from unittest.mock import patch
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        from .receipts import scan_receipt

        def recognise(command, **kwargs):
            if command[-1] == '0':
                return CompletedProcess(command, 0, b'Rotate: 90\nOrientation confidence: 12.0\n', b'')
            self.assertEqual(command[-2:], ['--psm', '4'])
            with Image.open(command[1]) as image:
                self.assertEqual(image.size, (300, 200))
            return CompletedProcess(command, 0, b'755322 LED CANDLES 3.99 B', b'')

        with patch('planner.receipts.subprocess.run', side_effect=recognise):
            text = scan_receipt(SimpleUploadedFile('receipt.png', self.receipt_image()))
        self.assertEqual(text, '755322 LED CANDLES 3.99 B')

    def test_orientation_timeout_does_not_prevent_receipt_ocr(self):
        from subprocess import CompletedProcess, TimeoutExpired
        from unittest.mock import patch
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .receipts import scan_receipt
        with patch('planner.receipts.subprocess.run', side_effect=[
            TimeoutExpired('tesseract', 5),
            CompletedProcess([], 0, b'LED CANDLES 3.99 B', b''),
        ]):
            self.assertIn('3.99', scan_receipt(SimpleUploadedFile('receipt.png', self.receipt_image())))

    def test_b_and_q_barcode_price_lines(self):
        from .receipts import receipt_items
        text = """B&Q
1x HEBE ADDENDA PURPLE

5059340873817 £6.00
1x METHOD ALL FLOOR CLEANER 739ML
0817939013779 ¢4.75
S Promo ey oe
1x MTD DAILY SHOWER SPRAY 0.828L EN ¢
0817939005231 £4.00
S Promo ~£4.20
1x PACK OF 20 TEA LIGHTS
5053844425183 £3.00
1x FOLIAGE IN CERAMIC 12CM
9063022511621 £3.00
Ix HEBE ADDENDA BLUE
9059340873794 £6.00
1x INTERLOCK CHILDREN TRAFFIC PLAY MA
9063022558817 £9.50
1x BATTERY NORDIC LANTERN ARONA
9050642116879 £12.00
8 Item(s)
TOTAL £50.10
Card sale ~£50.10"""
        rows = receipt_items(text)
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[0]['name'], 'HEBE ADDENDA PURPLE')
        self.assertEqual(rows[1]['unit_cost'], Decimal('4.75'))
        self.assertEqual(rows[5]['name'], 'HEBE ADDENDA BLUE')
        self.assertEqual(sum(row['unit_cost'] * row['quantity'] for row in rows), Decimal('48.25'))

    def test_multiline_receipt_does_not_pair_unrelated_barcode(self):
        from .receipts import receipt_items
        self.assertEqual(receipt_items('1x Missing price item\nTOTAL £9.00\n5059340873817 £9.00'), [])
        self.assertEqual(receipt_items('5059340873817 £9.00'), [])
        rows = receipt_items('2x CANDLES\n5059340873817 £6.00')
        self.assertEqual(rows[0]['quantity'], 2)
        self.assertEqual(rows[0]['unit_cost'], Decimal('3.00'))


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    SIGNUP_NOTIFICATION_EMAILS=['info@plan2wed.co.uk'],
    PLAN2WED_SITE_URL='https://plan2wed.co.uk',
)
class AccountEmailTests(TestCase):
    def signup_data(self):
        return {'signup_role': 'couple', 'first_name': 'Alex', 'last_name': 'Smith',
                'email': 'alex@example.com', 'bride_name': 'Alex', 'groom_name': 'Sam',
                'password1': 'LongUniquePassword!2026', 'password2': 'LongUniquePassword!2026'}

    def test_signup_emails_member_after_commit_and_stays_pending(self):
        from django.core import mail
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('signup'), self.signup_data())
        self.assertRedirects(response, reverse('signup_complete'))
        member = Member.objects.get(email='alex@example.com')
        self.assertEqual(member.status, Member.Status.PENDING)
        self.assertFalse(member.user.is_active)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['alex@example.com'])
        self.assertIn('https://plan2wed.co.uk/verify-email/', mail.outbox[0].body)
        self.assertIn('24 hours', mail.outbox[0].body)
        self.assertNotIn('/admin/', mail.outbox[0].body)
        self.assertNotIn('LongUniquePassword', mail.outbox[0].body)

    def test_failed_email_does_not_lose_account(self):
        from unittest.mock import patch
        with patch('planner.notifications.send_mail', side_effect=OSError('SMTP unavailable')):
            with self.assertLogs('planner.notifications', level='ERROR'):
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(reverse('signup'), self.signup_data())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Member.objects.filter(email='alex@example.com').exists())

    def test_couple_and_representative_signup_email_links_activate_their_accounts(self):
        import re
        from django.core import mail
        for role in (Member.SignupRole.COUPLE, Member.SignupRole.REPRESENTATIVE):
            with self.subTest(role=role):
                self.client.logout()
                data = self.signup_data()
                data.update(signup_role=role, email=f'{role}@example.com')
                with self.captureOnCommitCallbacks(execute=True):
                    self.client.post(reverse('signup'), data)
                member = Member.objects.get(email=data['email'])
                self.assertFalse(member.user.is_active)
                url = re.search(r'https://plan2wed.co.uk(/verify-email/[^\s]+)', mail.outbox[-1].body)[1]
                self.assertContains(self.client.get(url), 'Verify email and activate membership')
                self.assertRedirects(self.client.post(url), reverse('login'))
                member.refresh_from_db()
                self.assertEqual(member.status, Member.Status.ACTIVE)
                self.assertIsNotNone(member.email_verified_at)
                self.assertTrue(self.client.login(username=data['email'], password=data['password1']))
                portal = self.client.get(reverse('member_portal'))
                self.assertEqual(portal.status_code, 200)
                self.assertEqual(portal.context['budget'].member_id, member.pk)

    def test_password_reset_changes_password_and_token_cannot_be_reused(self):
        import re
        from django.core import mail
        user = get_user_model().objects.create_user(username='alex@example.com', email='alex@example.com', password='OldUniquePassword!2026')
        response = self.client.post(reverse('password_reset'), {'email': user.email})
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        url = re.search(r'https://plan2wed.co.uk(/reset/[^\s]+)', mail.outbox[0].body)[1]
        response = self.client.get(url)
        confirm_url = response.url
        self.assertContains(self.client.get(confirm_url), 'Choose a new password')
        response = self.client.post(confirm_url, {'new_password1': 'NewUniquePassword!2026', 'new_password2': 'NewUniquePassword!2026'})
        self.assertRedirects(response, reverse('password_reset_complete'))
        user.refresh_from_db()
        self.assertTrue(user.check_password('NewUniquePassword!2026'))
        self.assertContains(self.client.get(url), 'This link has expired')

    def test_pending_and_unknown_emails_get_same_response_without_mail(self):
        from django.core import mail
        user = get_user_model().objects.create_user(username='pending', email='pending@example.com', password='OldUniquePassword!2026', is_active=False)
        for address in (user.email, 'missing@example.com'):
            response = self.client.post(reverse('password_reset'), {'email': address})
            self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_invalid_reset_link_and_login_link(self):
        self.assertContains(self.client.get(reverse('password_reset_confirm', args=['invalid', 'invalid'])), 'This link has expired')
        self.assertContains(self.client.get(reverse('login')), reverse('password_reset'))

    def test_password_reset_link_expires_after_one_hour(self):
        from datetime import datetime, timedelta
        from unittest.mock import patch
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        user = get_user_model().objects.create_user(username='expiry', email='expiry@example.com', password='OldUniquePassword!2026')
        issued = datetime(2026, 11, 12, 12, 0, 0)
        with patch.object(default_token_generator, '_now', return_value=issued):
            token = default_token_generator.make_token(user)
        url = reverse('password_reset_confirm', args=[urlsafe_base64_encode(force_bytes(user.pk)), token])
        with patch.object(default_token_generator, '_now', return_value=issued + timedelta(seconds=3601)):
            self.assertContains(self.client.get(url), 'This link has expired')

    def test_invalid_or_duplicate_signup_does_not_notify(self):
        from django.core import mail
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('signup'), self.signup_data())
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('signup'), self.signup_data())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(Member.objects.filter(email='alex@example.com').count(), 1)


class ShoppingListImportTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='shopping-import')
        member = Member.objects.create(user=user, first_name='A', last_name='B', email='import@example.com')
        self.budget = WeddingBudget.objects.create(member=member, wedding_date=date(2027, 6, 12))
        self.event = self.budget.events.get()
        self.url = reverse('event_shopping_list', args=[self.event.pk])
        self.client.force_login(user)

    def preview(self, text):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return self.client.post(reverse('shopping_management'), {'action': 'preview_import', 'event': self.event.pk, 'list_category': 'decorations',
            'file': SimpleUploadedFile('shopping.csv', text.encode('utf-8'), content_type='text/csv')})

    def confirm(self, response):
        return self.client.post(reverse('shopping_management'), {'action': 'confirm_import', 'import_token': response.context['import_token']})

    def test_preview_confirm_optional_prices_and_duplicate_skip(self):
        response = self.preview('Item,Quantity,List,Unit cost\nCandles,,,\nJuice,2,Drinks,3.50\nCandles,,,\n')
        self.assertContains(response, 'Not priced')
        self.assertFalse(self.event.shopping_items.exists())
        self.assertEqual(self.confirm(response).status_code, 302)
        self.assertEqual(self.event.shopping_items.count(), 2)
        candle = self.event.shopping_items.get(name='Candles')
        self.assertIsNone(candle.unit_cost)
        self.assertEqual(candle.quantity, 1)
        self.assertEqual(candle.list_category, 'decorations')
        self.assertFalse(candle.is_purchased)
        self.assertEqual(self.event.pending, Decimal('7.00'))
        self.confirm(response)
        self.assertEqual(self.event.shopping_items.count(), 2)

    def test_invalid_csv_does_not_import_partial_rows(self):
        for text in ['Item,Quantity\nCandles,1\nJuice,-2', 'Item,List\nCandles,Unknown',
                     'Item,Event\nCandles,Another event', 'Item,Unit cost\nCandles,-1']:
            with self.subTest(csv=text):
                response = self.preview(text)
                self.assertTrue(response.context['import_form'].errors)
                self.assertFalse(self.event.shopping_items.exists())
                self.assertIsNone(response.context['import_preview'])

    def test_list_filter_keeps_event_totals(self):
        ShoppingListItem.objects.create(event=self.event, name='Candles', list_category='decorations', unit_cost=2)
        ShoppingListItem.objects.create(event=self.event, name='Juice', list_category='drinks', unit_cost=3)
        response = self.client.get(self.url, {'list': 'decorations'})
        self.assertEqual([item.name for item in response.context['items']], ['Candles'])
        self.assertEqual(response.context['pending_total'], Decimal('5'))

    def test_add_item_without_price(self):
        response = self.client.post(self.url, {'action': 'add_item', 'name': 'Flowers', 'list_category': 'flowers', 'quantity': 1, 'unit_cost': ''})
        self.assertEqual(response.status_code, 302)
        item = self.event.shopping_items.get()
        self.assertIsNone(item.unit_cost)
        self.assertEqual(item.total_cost, 0)
        self.assertContains(self.client.get(self.url), 'Not priced')

    def test_cannot_import_into_another_members_event(self):
        from .models import WeddingEvent
        other = Member.objects.create(first_name='Other', last_name='Member', email='other-import@example.com')
        budget = WeddingBudget.objects.create(member=other)
        event = WeddingEvent.objects.create(budget=budget, name='Private')
        from django.core.files.uploadedfile import SimpleUploadedFile
        response = self.client.post(reverse('shopping_management'), {'action': 'preview_import', 'event': event.pk, 'list_category': 'other', 'file': SimpleUploadedFile('items.csv', b'Item\nCandles')})
        self.assertTrue(response.context['import_form'].errors)
        self.assertFalse(event.shopping_items.exists())

    def test_management_navigation_and_preselected_event(self):
        self.assertContains(self.client.get(reverse('member_portal')), reverse('shopping_management'))
        response = self.client.get(reverse('shopping_management'), {'event': self.event.pk})
        self.assertEqual(response.context['import_form'].initial['event'], self.event.pk)
        self.assertContains(response, 'Manage shopping lists')
        self.assertContains(response, 'Download CSV template')
        event_page = self.client.get(self.url)
        self.assertContains(event_page, reverse('shopping_management'))
        self.assertNotContains(event_page, 'name="action" value="preview_import"')

    def test_management_requires_login_and_handles_no_events(self):
        self.event.delete()
        self.assertContains(self.client.get(reverse('shopping_management')), 'Add an event first')
        self.client.logout()
        self.assertEqual(self.client.get(reverse('shopping_management')).status_code, 302)

    def test_manual_item_from_management_without_cost(self):
        response = self.client.post(reverse('shopping_management'), {
            'action': 'add_manual_item', 'manual-event': self.event.pk,
            'manual-name': 'Candles', 'manual-list_category': 'decorations', 'manual-quantity': 3,
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('event=', response.url)
        item = self.event.shopping_items.get()
        self.assertEqual(item.quantity, 3)
        self.assertEqual(item.list_category, 'decorations')
        self.assertIsNone(item.unit_cost)
        self.assertFalse(item.is_purchased)

    def test_manual_item_rejects_other_members_event_and_shows_errors(self):
        from .models import WeddingEvent
        other = Member.objects.create(first_name='Other', last_name='Member', email='manual-other@example.com')
        event = WeddingEvent.objects.create(budget=WeddingBudget.objects.create(member=other), name='Private')
        response = self.client.post(reverse('shopping_management'), {
            'action': 'add_manual_item', 'manual-event': event.pk,
            'manual-name': 'Candles', 'manual-list_category': 'decorations', 'manual-quantity': 1,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['manual_form'].errors)
        self.assertContains(response, 'Candles')
        self.assertFalse(event.shopping_items.exists())

    def test_items_grouped_by_category_with_counts_and_event_totals(self):
        ShoppingListItem.objects.create(event=self.event, name='Candles', list_category='decorations', unit_cost=2)
        ShoppingListItem.objects.create(event=self.event, name='Balloons', list_category='decorations', unit_cost=3, is_purchased=True)
        ShoppingListItem.objects.create(event=self.event, name='Juice', list_category='drinks', unit_cost=4)
        response = self.client.get(self.url)
        groups = response.context['item_groups']
        self.assertEqual([group['category'] for group in groups], ['decorations', 'drinks'])
        self.assertEqual(len(groups[0]['items']), 2)
        self.assertFalse(any(group['open'] for group in groups))
        self.assertContains(response, '(2 items)')
        self.assertContains(response, 'Expand all')
        self.assertEqual(response.context['purchased_total'], Decimal('3'))
        self.assertEqual(response.context['pending_total'], Decimal('6'))
        filtered = self.client.get(self.url, {'list': 'drinks'})
        self.assertEqual(len(filtered.context['item_groups']), 1)
        self.assertTrue(filtered.context['item_groups'][0]['open'])
        self.assertEqual(filtered.context['pending_total'], Decimal('6'))
        self.assertNotContains(filtered, 'Balloons')

    def test_category_total_includes_purchases_and_flags_unpriced_items(self):
        ShoppingListItem.objects.create(event=self.event, name='Candles', list_category='decorations', quantity=3, unit_cost=Decimal('2.50'))
        ShoppingListItem.objects.create(event=self.event, name='Balloons', list_category='decorations', quantity=2, unit_cost=Decimal('1.25'), is_purchased=True)
        ShoppingListItem.objects.create(event=self.event, name='Ribbon', list_category='decorations')
        ShoppingListItem.objects.create(event=self.event, name='Juice', list_category='drinks', unit_cost=4)
        response = self.client.get(self.url)
        group = response.context['item_groups'][0]
        self.assertEqual(group['total'], Decimal('10.00'))
        self.assertEqual(group['committed'], Decimal('2.50'))
        self.assertEqual(group['pending'], Decimal('7.50'))
        self.assertEqual(group['total'], group['committed'] + group['pending'])
        self.assertContains(response, 'Committed: <strong class="money-value">2.50</strong>')
        self.assertContains(response, 'Pending: <strong class="money-value">7.50</strong>')
        self.assertEqual(group['unpriced_count'], 1)
        self.assertContains(response, '10.00</span>')
        self.assertContains(response, '(1 not priced)')


class VenueDirectoryTests(TestCase):
    def test_wedding_location_defaults_venue_search_and_can_be_overridden(self):
        from .models import DirectoryVenue
        WeddingBudget.objects.create(member=self.member, wedding_location='Ipswich')
        DirectoryVenue.objects.create(name='London Hall', location='London', is_published=True)
        response = self.client.get(self.url)
        self.assertContains(response, 'Example Hall')
        self.assertNotContains(response, 'London Hall')
        response = self.client.get(self.url, {'location': 'London'})
        self.assertContains(response, 'London Hall')
        self.assertNotContains(response, 'Example Hall')
        response = self.client.get(self.url, {'location': ''})
        self.assertContains(response, 'Example Hall')
        self.assertContains(response, 'London Hall')

    def test_wedding_location_is_saved_with_details(self):
        response = self.client.post(reverse('member_portal'), {
            'action': 'save_budget', 'wedding_location': 'Ipswich',
            'has_separate_meal': 'False', 'allocated': '1000',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WeddingBudget.objects.get(member=self.member).wedding_location, 'Ipswich')

    def setUp(self):
        from .models import DirectoryVenue
        self.user = get_user_model().objects.create_user(username='venue-browser')
        self.member = Member.objects.create(user=self.user, first_name='A', last_name='B', email='venues@example.com')
        self.listing = DirectoryVenue.objects.create(name='Example Hall', location='Ipswich', venue_type='hall', capacity=200, facilities='Accessible parking', address='Example address', is_published=True)
        self.draft = DirectoryVenue.objects.create(name='Draft venue', location='London')
        self.url = reverse('venue_directory')
        self.client.force_login(self.user)

    def test_browse_published_venues_and_filter(self):
        self.assertContains(self.client.get(self.url), 'Example Hall')
        self.assertNotContains(self.client.get(self.url), 'Draft venue')
        self.assertContains(self.client.get(self.url, {'location': 'ipswich', 'capacity': 150, 'venue_type': 'hall', 'query': 'parking'}), 'Example Hall')
        self.assertNotContains(self.client.get(self.url, {'capacity': 300}), 'Example Hall')
        self.assertTrue(self.client.get(self.url, {'capacity': '-1'}).context['search_form'].errors)

    def test_save_is_private_and_idempotent(self):
        from .models import Venue
        self.client.post(self.url, {'venue_id': self.listing.pk})
        self.client.post(self.url, {'venue_id': self.listing.pk})
        venue = Venue.objects.get(budget__member=self.member)
        self.assertEqual(venue.directory_entry, self.listing)
        self.assertEqual(venue.name, 'Example Hall')
        venue.notes = 'Private booking details'
        venue.save()
        self.listing.name = 'Updated shared name'
        self.listing.save()
        self.client.post(self.url, {'venue_id': self.listing.pk})
        venue.refresh_from_db()
        self.assertEqual(venue.name, 'Example Hall')
        self.assertEqual(venue.notes, 'Private booking details')
        self.assertNotContains(self.client.get(self.url), 'Private booking details')
        other_user = get_user_model().objects.create_user(username='another-browser')
        other = Member.objects.create(user=other_user, first_name='C', last_name='D', email='other-venues@example.com')
        self.client.force_login(other_user)
        self.client.post(self.url, {'venue_id': self.listing.pk})
        self.assertEqual(Venue.objects.count(), 2)
        self.assertEqual(Venue.objects.get(budget__member=other).notes, '')

    def test_draft_cannot_be_added_and_anonymous_cannot_browse(self):
        self.assertEqual(self.client.post(self.url, {'venue_id': self.draft.pk}).status_code, 404)
        self.assertEqual(self.client.post(self.url, {'venue_id': 'invalid'}).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_listing_deletion_keeps_members_saved_venue(self):
        from .models import Venue
        self.client.post(self.url, {'venue_id': self.listing.pk})
        self.listing.delete()
        venue = Venue.objects.get(budget__member=self.member)
        self.assertIsNone(venue.directory_entry)
        self.assertEqual(venue.name, 'Example Hall')

    def test_member_cannot_edit_shared_listing(self):
        response = self.client.get(reverse('admin:planner_directoryvenue_change', args=[self.listing.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get(reverse('venue_list')), self.url)
        self.assertContains(self.client.get(reverse('member_portal')), self.url)


class EventCatalogueTests(TestCase):
    def setUp(self):
        from .models import EventTemplate, SuggestedShoppingItem
        self.user = get_user_model().objects.create_user(username='event-browser')
        self.member = Member.objects.create(user=self.user, first_name='A', last_name='B', email='event-browser@example.com')
        self.template = EventTemplate.objects.create(name='Test Chunni', description='A family celebration', is_published=True)
        self.item = SuggestedShoppingItem.objects.create(event_template=self.template, name='Chunni / scarf', list_category='clothing', quantity=1, notes='Choose with family')
        self.extra = SuggestedShoppingItem.objects.create(event_template=self.template, name='Sweets', list_category='food')
        self.url = reverse('event_template_detail', args=[self.template.pk])
        self.client.force_login(self.user)

    def test_choose_event_and_selected_unpriced_items_idempotently(self):
        self.assertContains(self.client.get(self.url), 'Choose with family')
        for _ in range(2):
            response = self.client.post(self.url, {'items': [self.item.pk], 'event_date': '2027-06-10'})
            self.assertEqual(response.status_code, 302)
        event = self.member.wedding_budget.events.get(event_template=self.template)
        self.assertEqual(event.name, 'Test Chunni')
        self.assertEqual(event.event_date, date(2027, 6, 10))
        self.assertEqual(event.shopping_items.count(), 1)
        item = event.shopping_items.get()
        self.assertEqual(item.name, 'Chunni / scarf')
        self.assertEqual(item.list_category, 'clothing')
        self.assertIsNone(item.unit_cost)
        self.assertFalse(item.is_purchased)
        self.assertEqual(event.pending, 0)

    def test_add_to_existing_event_without_replacing_private_details(self):
        from .models import WeddingEvent
        budget = WeddingBudget.objects.create(member=self.member)
        event = WeddingEvent.objects.create(budget=budget, name='Our family ceremony', notes='Private arrangements')
        ShoppingListItem.objects.create(event=event, name='Chunni / scarf', list_category='clothing', quantity=2, unit_cost=25)
        response = self.client.post(self.url, {'event': event.pk, 'items': [self.item.pk, self.extra.pk]})
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.notes, 'Private arrangements')
        self.assertEqual(event.shopping_items.count(), 2)
        self.assertEqual(event.shopping_items.get(name='Chunni / scarf').unit_cost, Decimal('25'))
        self.assertEqual(budget.events.count(), 1)

    def test_hidden_templates_foreign_events_and_foreign_suggestions_rejected(self):
        from .models import EventTemplate, SuggestedShoppingItem, WeddingEvent
        hidden = EventTemplate.objects.create(name='Hidden event')
        suggestion = SuggestedShoppingItem.objects.create(event_template=hidden, name='Other')
        self.assertEqual(self.client.get(reverse('event_template_detail', args=[hidden.pk])).status_code, 404)
        self.assertTrue(self.client.post(self.url, {'items': [suggestion.pk]}).context['form'].errors)
        other = Member.objects.create(first_name='C', last_name='D', email='other-template@example.com')
        event = WeddingEvent.objects.create(budget=WeddingBudget.objects.create(member=other), name='Private event')
        response = self.client.post(self.url, {'event': event.pk, 'items': [self.item.pk]})
        self.assertTrue(response.context['form'].errors)
        self.assertFalse(event.shopping_items.exists())
        self.client.logout()
        self.assertEqual(self.client.get(reverse('event_catalogue')).status_code, 302)

    def test_seeded_chunni_and_admin_only_editing(self):
        from .models import EventTemplate
        chunni = EventTemplate.objects.get(name='Chunni Chadana')
        self.assertTrue(chunni.is_published)
        self.assertTrue(chunni.shopping_suggestions.filter(list_category='clothing').exists())
        self.assertContains(self.client.get(reverse('event_catalogue')), 'Chunni Chadana')
        self.assertEqual(self.client.get(reverse('admin:planner_eventtemplate_change', args=[chunni.pk])).status_code, 302)

    def test_removing_template_keeps_member_event_and_items(self):
        self.client.post(self.url, {'items': [self.item.pk]})
        event = self.member.wedding_budget.events.get(event_template=self.template)
        self.template.delete()
        event.refresh_from_db()
        self.assertIsNone(event.event_template)
        self.assertEqual(event.shopping_items.count(), 1)


class InAppCatalogueAdminTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(username='catalogue-admin', is_staff=True)
        self.venues_url = reverse('admin_venues')
        self.shopping_url = reverse('admin_shopping')
        self.client.force_login(self.staff)

    def test_staff_without_member_profile_can_create_and_edit_venue(self):
        from .models import DirectoryVenue
        response = self.client.post(self.venues_url, {'action': 'save', 'name': 'Shared Hall', 'venue_type': 'hall', 'location': 'Ipswich', 'capacity': 100, 'is_published': 'on'})
        self.assertEqual(response.status_code, 302)
        venue = DirectoryVenue.objects.get(name='Shared Hall')
        self.assertTrue(venue.is_published)
        response = self.client.post(self.venues_url, {'action': 'save', 'venue_id': venue.pk, 'name': 'Updated Hall', 'venue_type': 'hotel', 'location': 'London'})
        self.assertEqual(response.status_code, 302)
        venue.refresh_from_db()
        self.assertEqual(venue.name, 'Updated Hall')
        self.assertFalse(venue.is_published)
        self.assertContains(self.client.get(reverse('member_list')), self.venues_url)
        self.assertContains(self.client.get(self.venues_url), self.shopping_url)

    def test_venue_validation_and_confirmation_before_deletion(self):
        from .models import DirectoryVenue, Venue
        venue = DirectoryVenue.objects.create(name='Shared Hall', location='Ipswich')
        member = Member.objects.create(first_name='A', last_name='B', email='saved-venue@example.com')
        saved = Venue.objects.create(budget=WeddingBudget.objects.create(member=member), directory_entry=venue, name='My venue', notes='Private')
        response = self.client.post(self.venues_url, {'action': 'save', 'name': '', 'venue_type': 'hall', 'location': 'Ipswich'})
        self.assertTrue(response.context['form'].errors)
        response = self.client.post(self.venues_url, {'action': 'delete', 'venue_id': venue.pk})
        self.assertContains(response, 'Confirm deletion')
        self.assertTrue(DirectoryVenue.objects.filter(pk=venue.pk).exists())
        self.client.post(self.venues_url, {'action': 'confirm_delete', 'venue_id': venue.pk})
        self.assertFalse(DirectoryVenue.objects.filter(pk=venue.pk).exists())
        saved.refresh_from_db()
        self.assertIsNone(saved.directory_entry)
        self.assertEqual(saved.notes, 'Private')

    def test_create_checklist_and_manage_suggestions(self):
        from .models import EventTemplate
        response = self.client.post(self.shopping_url, {'action': 'save_template', 'template-name': 'New shared ceremony', 'template-description': 'Planning ideas', 'template-is_published': 'on'})
        self.assertEqual(response.status_code, 302)
        template = EventTemplate.objects.get(name='New shared ceremony')
        url = self.shopping_url + f'?template={template.pk}'
        response = self.client.post(url, {'action': 'save_item', 'item-name': 'Chunni', 'item-list_category': 'clothing', 'item-quantity': 1, 'item-notes': 'Optional'})
        self.assertEqual(response.status_code, 302)
        item = template.shopping_suggestions.get()
        self.assertContains(self.client.get(url), 'Chunni')
        response = self.client.post(url + f'&item={item.pk}', {'action': 'save_item', 'item-name': 'Scarf', 'item-list_category': 'clothing', 'item-quantity': 2})
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.name, 'Scarf')
        self.client.post(url, {'action': 'delete_item', 'item_id': item.pk})
        self.assertTrue(template.shopping_suggestions.exists())
        self.client.post(url, {'action': 'confirm_delete', 'item_id': item.pk})
        self.assertFalse(template.shopping_suggestions.exists())

    def test_other_template_item_cannot_be_modified_and_invalid_qty_rejected(self):
        from .models import EventTemplate, SuggestedShoppingItem
        template = EventTemplate.objects.create(name='First checklist')
        other = EventTemplate.objects.create(name='Second checklist')
        item = SuggestedShoppingItem.objects.create(event_template=other, name='Other suggestion')
        url = self.shopping_url + f'?template={template.pk}'
        self.assertEqual(self.client.post(url, {'action': 'confirm_delete', 'item_id': item.pk}).status_code, 404)
        response = self.client.post(url, {'action': 'save_item', 'item-name': 'Invalid', 'item-list_category': 'food', 'item-quantity': 0})
        self.assertTrue(response.context['item_form'].errors)
        self.assertFalse(template.shopping_suggestions.exists())

    def test_non_staff_and_anonymous_cannot_read_or_write_admin(self):
        from .models import DirectoryVenue
        user = get_user_model().objects.create_user(username='ordinary-member')
        self.client.force_login(user)
        for url in (self.venues_url, self.shopping_url):
            self.assertEqual(self.client.get(url).status_code, 302)
            self.assertEqual(self.client.post(url, {'action': 'save', 'name': 'Forbidden'}).status_code, 302)
        self.assertFalse(DirectoryVenue.objects.filter(name='Forbidden').exists())
        self.client.logout()
        self.assertEqual(self.client.get(self.venues_url).status_code, 302)


class EventDuplicatePreventionTests(TestCase):
    def setUp(self):
        from .models import WeddingEvent
        self.user = get_user_model().objects.create_user(username='duplicate-event-owner')
        self.member = Member.objects.create(user=self.user, first_name='A', last_name='B', email='duplicate-events@example.com')
        self.budget = WeddingBudget.objects.create(member=self.member)
        self.event = WeddingEvent.objects.create(budget=self.budget, name='Reception', notes='Keep our plans')
        self.client.force_login(self.user)

    def event_data(self, name, **overrides):
        data = {'name': name, 'event_date': '', 'description': '', 'venue': '', 'other_spent': '0', 'other_pending': '0', 'notes': ''}
        data.update(overrides)
        return data

    def test_duplicate_names_are_rejected_in_add_form_even_on_another_date(self):
        for name in ['Reception', 'reception', ' RECEPTION ']:
            with self.subTest(name=name):
                response = self.client.post(reverse('event_add'), self.event_data(name, event_date='2027-06-12'))
                self.assertEqual(response.status_code, 200)
                self.assertIn('name', response.context['form'].errors)
                self.assertContains(response, 'already in your wedding plan')
                self.assertEqual(self.budget.events.count(), 1)
        self.event.refresh_from_db()
        self.assertEqual(self.event.notes, 'Keep our plans')

    def test_form_detects_existing_legacy_names_with_surrounding_spaces(self):
        from .models import WeddingEvent
        WeddingEvent.objects.filter(pk=self.event.pk).update(name=' Reception ')
        response = self.client.post(reverse('event_add'), self.event_data('reception'))
        self.assertIn('name', response.context['form'].errors)
        self.assertEqual(self.budget.events.count(), 1)

    def test_repeated_submission_creates_only_one_new_event(self):
        data = self.event_data(' Mehndi ')
        first = self.client.post(reverse('event_add'), data)
        self.assertEqual(first.status_code, 302)
        second = self.client.post(reverse('event_add'), data)
        self.assertIn('name', second.context['form'].errors)
        self.assertEqual(self.budget.events.filter(name='Mehndi').count(), 1)

    def test_editing_same_event_is_allowed_but_renaming_another_to_it_is_not(self):
        from .models import WeddingEvent
        url = reverse('event_edit', args=[self.event.pk])
        response = self.client.post(url, self.event_data('Reception', notes='Updated private notes'))
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.notes, 'Updated private notes')
        other = WeddingEvent.objects.create(budget=self.budget, name='Mehndi')
        response = self.client.post(reverse('event_edit', args=[other.pk]), self.event_data('RECEPTION'))
        self.assertIn('name', response.context['form'].errors)
        other.refresh_from_db()
        self.assertEqual(other.name, 'Mehndi')

    def test_same_event_name_is_allowed_in_another_wedding_plan(self):
        from .models import WeddingEvent
        other_member = Member.objects.create(first_name='C', last_name='D', email='another-wedding@example.com')
        other_budget = WeddingBudget.objects.create(member=other_member)
        event = WeddingEvent.objects.create(budget=other_budget, name='reception')
        self.assertEqual(event.budget, other_budget)
        self.assertEqual(self.budget.events.count(), 1)

    def test_model_save_also_rejects_duplicate_creation_and_rename(self):
        from django.core.exceptions import ValidationError
        from .models import WeddingEvent
        with self.assertRaises(ValidationError):
            WeddingEvent.objects.create(budget=self.budget, name=' RECEPTION ')
        other = WeddingEvent.objects.create(budget=self.budget, name='Mehndi')
        other.name = 'reception'
        with self.assertRaises(ValidationError):
            other.save()
        other.refresh_from_db()
        self.assertEqual(other.name, 'Mehndi')
        self.assertEqual(self.budget.events.count(), 2)

    def test_save_time_conflict_is_shown_as_field_error_without_losing_input(self):
        from django.core.exceptions import ValidationError
        from unittest.mock import patch
        with patch('planner.views.WeddingEvent.save', side_effect=ValidationError({'name': 'An event with this name is already in your wedding plan.'})):
            response = self.client.post(reverse('event_add'), self.event_data('Mehndi', notes='Keep this input'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('name', response.context['form'].errors)
        self.assertEqual(response.context['form']['notes'].value(), 'Keep this input')
        self.assertEqual(self.budget.events.count(), 1)

    def test_existing_duplicate_records_are_not_deleted_or_blocked_from_maintenance(self):
        from .models import WeddingEvent
        other = WeddingEvent.objects.create(budget=self.budget, name='Old event')
        WeddingEvent.objects.filter(pk=other.pk).update(name='reception')
        self.event.notes = 'Still editable'
        self.event.save()
        self.assertEqual(self.budget.events.count(), 2)
        self.event.refresh_from_db()
        self.assertEqual(self.event.notes, 'Still editable')

    def test_automatic_events_reuse_manual_events_and_keep_related_plans(self):
        from .models import WeddingEvent
        day = WeddingEvent.objects.create(budget=self.budget, name=' wedding day ', notes='Ceremony notes')
        meal = WeddingEvent.objects.create(budget=self.budget, name='wedding meal / reception', notes='Meal notes')
        guest = WeddingGuest.objects.create(budget=self.budget, first_name='Family')
        day.guests.add(guest)
        item = ShoppingListItem.objects.create(event=meal, name='Table flowers', unit_cost=30)
        self.budget.wedding_date = date(2027, 6, 12)
        self.budget.has_separate_meal = True
        self.budget.save()
        self.budget.save()
        day.refresh_from_db()
        meal.refresh_from_db()
        self.assertTrue(day.is_wedding_day)
        self.assertTrue(meal.is_wedding_meal)
        self.assertEqual(day.event_date, self.budget.wedding_date)
        self.assertEqual(meal.event_date, self.budget.wedding_date)
        self.assertEqual(day.guests.get(), guest)
        self.assertEqual(meal.shopping_items.get(), item)
        self.assertEqual(meal.notes, 'Meal notes')
        self.assertEqual(self.budget.events.count(), 3)

    def test_catalogue_reuses_matching_manual_event_and_preserves_details(self):
        from .models import EventTemplate, SuggestedShoppingItem
        template = EventTemplate.objects.create(name='RECEPTION', description='Suggested description', is_published=True)
        item = SuggestedShoppingItem.objects.create(event_template=template, name='Flowers', list_category='flowers')
        self.event.event_date = date(2027, 6, 12)
        self.event.description = 'Our own description'
        self.event.save()
        guest = WeddingGuest.objects.create(budget=self.budget, first_name='Family')
        self.event.guests.add(guest)
        existing_item = ShoppingListItem.objects.create(event=self.event, name='Flowers', list_category='flowers', quantity=3, unit_cost=50)
        url = reverse('event_template_detail', args=[template.pk])
        for _ in range(2):
            response = self.client.post(url, {'items': [item.pk], 'event_date': '2027-07-01'})
            self.assertRedirects(response, reverse('event_shopping_list', args=[self.event.pk]))
        self.assertEqual(self.budget.events.count(), 1)
        self.event.refresh_from_db()
        self.assertEqual(self.event.event_template, template)
        self.assertEqual(self.event.description, 'Our own description')
        self.assertEqual(self.event.event_date, date(2027, 6, 12))
        self.assertEqual(self.event.notes, 'Keep our plans')
        self.assertEqual(self.event.guests.get(), guest)
        self.assertEqual(self.event.shopping_items.get(), existing_item)
        self.assertEqual(self.event.pending, Decimal('150'))

    def test_catalogue_disables_matching_names_and_linked_renamed_events(self):
        from .models import EventTemplate, WeddingEvent
        manual = EventTemplate.objects.get(name='Reception')
        manual.name = ' reception '
        manual.save(update_fields=['name'])
        linked = EventTemplate.objects.create(name='Original ceremony', is_published=True)
        available = EventTemplate.objects.create(name='Available ceremony', is_published=True)
        WeddingEvent.objects.create(budget=self.budget, event_template=linked, name='Our renamed ceremony')
        response = self.client.get(reverse('event_catalogue'))
        states = {template.pk: template.already_in_plan for template in response.context['templates']}
        self.assertTrue(states[manual.pk])
        self.assertTrue(states[linked.pk])
        self.assertFalse(states[available.pk])
        self.assertContains(response, 'type="button" disabled>Already in your plan</button>', count=2)
        self.assertNotContains(response, f'href="{reverse("event_template_detail", args=[manual.pk])}"')
        self.assertNotContains(response, f'href="{reverse("event_template_detail", args=[linked.pk])}"')
        self.assertContains(response, f'href="{reverse("event_template_detail", args=[available.pk])}"')
        self.assertEqual(self.budget.events.count(), 2)

    def test_catalogue_search_and_deletion_refresh_already_planned_status(self):
        from .models import EventTemplate
        template = EventTemplate.objects.get(name='Reception')
        url = reverse('event_catalogue')
        response = self.client.get(url, {'q': 'RECEPTION'})
        self.assertTrue(response.context['templates'].get(pk=template.pk).already_in_plan)
        self.assertContains(response, 'Already in your plan', count=1)
        self.event.delete()
        response = self.client.get(url, {'q': 'RECEPTION'})
        self.assertFalse(response.context['templates'].get(pk=template.pk).already_in_plan)
        self.assertNotContains(response, 'Already in your plan')
        self.assertContains(response, f'href="{reverse("event_template_detail", args=[template.pk])}"')

    def test_catalogue_does_not_disable_events_from_another_members_plan(self):
        from .models import EventTemplate, WeddingEvent
        template = EventTemplate.objects.create(name='Another ceremony', is_published=True)
        other_member = Member.objects.create(first_name='C', last_name='D', email='catalogue-other@example.com')
        other_budget = WeddingBudget.objects.create(member=other_member)
        WeddingEvent.objects.create(budget=other_budget, event_template=template, name=template.name)
        response = self.client.get(reverse('event_catalogue'))
        self.assertFalse(response.context['templates'].get(pk=template.pk).already_in_plan)
        user = get_user_model().objects.create_user(username='catalogue-no-budget')
        Member.objects.create(user=user, first_name='E', last_name='F', email='catalogue-empty@example.com')
        self.client.force_login(user)
        response = self.client.get(reverse('event_catalogue'))
        self.assertFalse(any(template.already_in_plan for template in response.context['templates']))
        self.assertNotContains(response, 'Already in your plan')

    def test_shared_event_catalogue_form_rejects_case_and_space_variants(self):
        from .forms import EventTemplateAdminForm
        from .models import EventTemplate
        template = EventTemplate.objects.create(name='Unique shared ceremony')
        form = EventTemplateAdminForm({'name': ' UNIQUE SHARED CEREMONY '})
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)
        same = EventTemplateAdminForm({'name': 'Unique shared ceremony'}, instance=template)
        self.assertTrue(same.is_valid(), same.errors)

    def test_catalogue_reuses_same_named_manual_event_and_keeps_private_details(self):
        from .models import EventTemplate, SuggestedShoppingItem
        template = EventTemplate.objects.create(name='RECEPTION', description='Shared text', is_published=True)
        suggestion = SuggestedShoppingItem.objects.create(event_template=template, name='Table flowers', list_category='flowers')
        self.event.event_date = date(2027, 6, 12)
        self.event.description = 'Our private description'
        self.event.save()
        guest = WeddingGuest.objects.create(budget=self.budget, first_name='Family')
        self.event.guests.add(guest)
        paid_item = ShoppingListItem.objects.create(event=self.event, name='Venue deposit', unit_cost=100, is_purchased=True)
        url = reverse('event_template_detail', args=[template.pk])
        for _ in range(2):
            response = self.client.post(url, {'items': [suggestion.pk], 'event_date': '2028-01-01'})
            self.assertRedirects(response, reverse('event_shopping_list', args=[self.event.pk]))
        self.assertEqual(self.budget.events.count(), 1)
        self.event.refresh_from_db()
        self.assertEqual(self.event.event_template_id, template.pk)
        self.assertEqual(self.event.event_date, date(2027, 6, 12))
        self.assertEqual(self.event.description, 'Our private description')
        self.assertEqual(self.event.notes, 'Keep our plans')
        self.assertEqual(self.event.guests.get(), guest)
        self.assertEqual(self.event.shopping_items.count(), 2)
        self.assertTrue(self.event.shopping_items.filter(pk=paid_item.pk, is_purchased=True, unit_cost=100).exists())

    def test_legacy_duplicates_can_still_be_edited_without_deleting_any_data(self):
        from .models import WeddingEvent
        other = WeddingEvent.objects.create(budget=self.budget, name='Other legacy event')
        WeddingEvent.objects.filter(pk=other.pk).update(name='reception')
        response = self.client.post(reverse('event_edit', args=[self.event.pk]), self.event_data('Reception', notes='Still editable'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.budget.events.count(), 2)
        self.event.refresh_from_db()
        self.assertEqual(self.event.notes, 'Still editable')
        response = self.client.post(reverse('event_add'), self.event_data('RECEPTION'))
        self.assertIn('name', response.context['form'].errors)

    def test_admin_event_table_rejects_duplicate_variant_without_changing_existing(self):
        from .models import EventTemplate
        staff = get_user_model().objects.create_user(username='duplicate-check-staff', is_staff=True)
        existing = EventTemplate.objects.create(name='Unique shared event', description='Keep this description')
        self.client.force_login(staff)
        response = self.client.post(reverse('admin_shopping'), {
            'action': 'save_template', 'template-name': ' UNIQUE SHARED EVENT ',
            'template-description': 'Do not overwrite',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('name', response.context['template_form'].errors)
        existing.refresh_from_db()
        self.assertEqual(existing.description, 'Keep this description')
        self.assertEqual(EventTemplate.objects.filter(name__iexact='Unique shared event').count(), 1)


class DjangoMessageDisplayTests(TestCase):
    def render_notices(self, notices):
        from django.contrib.auth.models import AnonymousUser
        from django.contrib.messages import constants
        from django.template.loader import render_to_string
        from django.test import RequestFactory
        request = RequestFactory().get('/')
        request.user = AnonymousUser()
        return render_to_string('planner/base.html', {
            'messages': notices, 'DEFAULT_MESSAGE_LEVELS': constants.DEFAULT_LEVELS,
        }, request=request)

    def test_no_notification_panel_when_there_are_no_messages(self):
        response = self.client.get(reverse('signup'))
        self.assertNotContains(response, 'id="django-messages"')
        self.assertContains(response, 'planner/messages.css')
        self.assertContains(response, 'planner/messages.js')

    def test_all_message_levels_have_accessible_roles_and_dismiss_controls(self):
        from django.contrib import messages
        from django.contrib.messages.storage.base import Message
        html = self.render_notices([
            Message(messages.SUCCESS, 'Saved your plan.'),
            Message(messages.INFO, 'A useful update.'),
            Message(messages.WARNING, 'Review the date.', extra_tags='custom-tag'),
            Message(messages.ERROR, 'Please try again.'),
        ])
        for level in ['success', 'info', 'warning', 'error']:
            self.assertIn(f'data-level="{level}"', html)
        self.assertEqual(html.count('role="alert"'), 1)
        self.assertEqual(html.count('role="status"'), 3)
        self.assertEqual(html.count('data-dismiss-message'), 4)
        self.assertIn('aria-label="Notifications"', html)
        self.assertIn('aria-label="Dismiss notification"', html)
        self.assertNotIn('custom-tag', html)

    def test_message_content_is_escaped(self):
        from django.contrib import messages
        from django.contrib.messages.storage.base import Message
        html = self.render_notices([Message(messages.ERROR, '<script>alert("unsafe")</script>')])
        self.assertNotIn('<script>alert("unsafe")</script>', html)
        self.assertIn('&lt;script&gt;alert(&quot;unsafe&quot;)&lt;/script&gt;', html)

    def test_redirect_messages_display_once_in_shared_panel_and_are_consumed(self):
        from .models import WeddingEvent
        user = get_user_model().objects.create_user(username='notification-staff', is_staff=True)
        member = Member.objects.create(user=user, first_name='A', last_name='B', email='notifications@example.com')
        budget = WeddingBudget.objects.create(member=member)
        event = WeddingEvent.objects.create(budget=budget, name='Reception')
        self.client.force_login(user)
        # The shared panel also replaces the former guest/seating inline displays.
        for index, destination in enumerate([
            reverse('admin_venues'), reverse('guest_list'), reverse('table_plan', args=[event.pk]),
        ]):
            with self.subTest(destination=destination):
                saved = self.client.post(reverse('admin_venues'), {
                    'action': 'save', 'name': f'Notification venue {index}',
                    'venue_type': 'hall', 'location': 'London',
                })
                self.assertEqual(saved.status_code, 302)
                response = self.client.get(destination)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="django-messages"', count=1)
                self.assertContains(response, 'Shared venue saved.', count=1)
                self.assertContains(response, 'data-level="success"', count=1)
                next_page = self.client.get(destination)
                self.assertNotContains(next_page, 'id="django-messages"')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ProjectWideNotificationTests(TestCase):
    def setUp(self):
        from .models import WeddingEvent
        self.user = get_user_model().objects.create_user(username='notice@example.com', email='notice@example.com', password='StrongNoticePassword!2027')
        self.member = Member.objects.create(user=self.user, first_name='A', last_name='B', email='notice@example.com')
        self.budget = WeddingBudget.objects.create(member=self.member)
        self.event = WeddingEvent.objects.create(budget=self.budget, name='Reception')
        self.client.force_login(self.user)

    def assert_success_notice(self, response, text):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="django-messages"', count=1)
        self.assertContains(response, 'data-level="success"', count=1)
        self.assertContains(response, text)

    def test_event_form_errors_use_shared_panel_and_do_not_persist(self):
        response = self.client.post(reverse('event_add'), {'name': ' RECEPTION ', 'other_spent': '0', 'other_pending': '0'})
        self.assertContains(response, 'id="django-messages"', count=1)
        self.assertContains(response, 'data-level="error"', count=1)
        self.assertContains(response, 'Event name: An event with this name is already in your wedding plan.')
        self.assertContains(response, 'An event with this name is already in your wedding plan.', count=1)
        self.assertNotContains(response, 'Event or expense')
        self.assertNotContains(response, 'Choose a suggested ceremony or enter your own event.')
        self.assertIn('name', response.context['form'].errors)
        self.assertNotContains(self.client.get(reverse('member_portal')), 'id="django-messages"')

    def test_signup_validation_summary_is_present_with_modal(self):
        self.client.logout()
        response = self.client.post(reverse('signup'), {'signup_role': 'couple'})
        self.assertContains(response, 'data-level="error"', count=1)
        self.assertContains(response, 'id="signup-dialog"')
        self.assertContains(response, "document.getElementById('signup-dialog').showModal()")
        self.assertTrue(response.context['form'].errors)

    def test_form_aliases_do_not_duplicate_the_notification_and_errors_are_escaped(self):
        from django import forms
        from django.template.loader import render_to_string
        from django.test import RequestFactory
        class NoticeForm(forms.Form):
            name = forms.CharField(label='Event name')
        form = NoticeForm({'name': ''})
        form.is_valid()
        form.add_error(None, '<script>unsafe</script>')
        request = RequestFactory().get('/')
        request.user = self.user
        html = render_to_string('planner/base.html', {'form': form, 'same_form': form}, request=request)
        self.assertEqual(html.count('data-level="error"'), 1)
        self.assertIn('Event name: This field is required.', html)
        self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;', html)
        self.assertNotIn('<script>unsafe</script>', html)

    def test_formset_and_non_form_errors_are_in_shared_panel(self):
        from django import forms
        from django.forms import formset_factory
        from django.template.loader import render_to_string
        from django.test import RequestFactory
        class ItemForm(forms.Form):
            name = forms.CharField(label='Item name')
        ItemForms = formset_factory(ItemForm, min_num=1, validate_min=True)
        rows = ItemForms({'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0', 'items-0-name': ''}, prefix='items')
        request = RequestFactory().get('/')
        request.user = self.user
        html = render_to_string('planner/base.html', {'receipt_rows': rows}, request=request)
        self.assertIn('Item 1 — Item name: This field is required.', html)
        self.assertIn('Please submit at least 1 form.', html)
        self.assertEqual(html.count('data-level="error"'), 1)

    def test_login_logout_and_failed_login_use_notifications_without_password_leaks(self):
        self.client.logout()
        response = self.client.post(reverse('login'), {'username': self.user.username, 'password': 'IncorrectSecretPassword'})
        self.assertContains(response, 'data-level="error"', count=1)
        self.assertContains(response, 'Your email or password is incorrect, or your membership is not active yet.', count=1)
        self.assertNotContains(response, 'IncorrectSecretPassword')
        response = self.client.post(reverse('login'), {'username': self.user.username, 'password': 'StrongNoticePassword!2027'}, follow=True)
        self.assert_success_notice(response, 'Welcome back to Plan2Wed.')
        response = self.client.post(reverse('logout'), follow=True)
        self.assert_success_notice(response, 'been signed out.')
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)

    def test_invalid_reset_link_and_reset_request_have_feedback(self):
        self.client.logout()
        response = self.client.get(reverse('password_reset_confirm', args=['invalid', 'invalid']))
        self.assertContains(response, 'data-level="error"')
        self.assertContains(response, 'Request a new link.')
        for email in ['notice@example.com', 'unknown@example.com']:
            response = self.client.post(reverse('password_reset'), {'email': email}, follow=True)
            self.assertContains(response, 'data-level="info"', count=1)
            self.assertContains(response, 'If an active account matches that address')

    def test_password_change_success_and_mismatch_use_shared_panel(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        self.client.logout()
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        response = self.client.get(reverse('password_reset_confirm', args=[uid, token]))
        url = response.url
        response = self.client.post(url, {'new_password1': 'StrongNewPassword!2027', 'new_password2': 'DifferentPassword!2027'})
        self.assertContains(response, 'data-level="error"', count=1)
        self.assertTrue(response.context['form'].errors)
        response = self.client.post(url, {'new_password1': 'StrongNewPassword!2027', 'new_password2': 'StrongNewPassword!2027'}, follow=True)
        self.assert_success_notice(response, 'Your password has been updated.')
        self.assertNotContains(response, 'StrongNewPassword')

    def test_wedding_details_event_add_edit_delete_have_feedback(self):
        from .models import WeddingEvent
        response = self.client.post(reverse('member_portal'), {'action': 'save_budget', 'allocated': '1000', 'has_separate_meal': 'False'}, follow=True)
        self.assert_success_notice(response, 'Your wedding details and budget have been saved.')
        data = {'name': 'Mehndi', 'other_spent': '0', 'other_pending': '0'}
        response = self.client.post(reverse('event_add'), data, follow=True)
        self.assert_success_notice(response, 'Event added to your wedding plan.')
        event = WeddingEvent.objects.get(budget=self.budget, name='Mehndi')
        response = self.client.post(reverse('event_edit', args=[event.pk]), {**data, 'notes': 'Updated'}, follow=True)
        self.assert_success_notice(response, 'Event updated.')
        response = self.client.post(reverse('event_detail', args=[event.pk]), {'action': 'delete_event'}, follow=True)
        self.assert_success_notice(response, 'Event deleted from your wedding plan.')

    def test_shopping_add_edit_toggle_delete_have_feedback(self):
        url = reverse('event_shopping_list', args=[self.event.pk])
        data = {'name': 'Flowers', 'list_category': 'flowers', 'quantity': '1', 'unit_cost': '10'}
        response = self.client.post(url, {'action': 'add_item', **data}, follow=True)
        self.assert_success_notice(response, 'Shopping item added.')
        item = self.event.shopping_items.get()
        response = self.client.post(url, {'action': 'update_item', 'item_id': item.pk, **data, 'quantity': '2'}, follow=True)
        self.assert_success_notice(response, 'Shopping item updated.')
        response = self.client.post(url, {'action': 'toggle_item', 'item_id': item.pk}, follow=True)
        self.assert_success_notice(response, 'Item marked as purchased.')
        response = self.client.post(url, {'action': 'toggle_item', 'item_id': item.pk}, follow=True)
        self.assert_success_notice(response, 'Item marked as To buy.')
        response = self.client.post(url, {'action': 'delete_item', 'item_id': item.pk}, follow=True)
        self.assert_success_notice(response, 'Shopping item deleted.')

    def test_venue_and_guest_actions_have_feedback(self):
        url = reverse('venue_list')
        response = self.client.post(url, {'action': 'save_venue', 'name': 'Our hall'}, follow=True)
        self.assert_success_notice(response, 'Venue added to your plan.')
        venue = self.budget.venues.get()
        response = self.client.post(url, {'action': 'update_venue', 'venue_id': venue.pk, 'name': 'Updated hall'}, follow=True)
        self.assert_success_notice(response, 'Venue updated.')
        response = self.client.post(url, {'action': 'delete_venue', 'venue_id': venue.pk}, follow=True)
        self.assert_success_notice(response, 'Venue deleted from your plan.')
        url = reverse('guest_list')
        data = {'first_name': 'Family', 'rsvp_status': 'invited'}
        response = self.client.post(url, {'action': 'save_guest', **data}, follow=True)
        self.assert_success_notice(response, 'Guest added to your list.')
        guest = self.budget.guests.get()
        response = self.client.post(url, {'action': 'update_guest', 'guest_id': guest.pk, **data, 'last_name': 'Guest'}, follow=True)
        self.assert_success_notice(response, 'Guest updated.')
        response = self.client.post(url, {'action': 'delete_guest', 'guest_id': guest.pk}, follow=True)
        self.assert_success_notice(response, 'Guest removed from your list.')

    def test_membership_status_actions_and_invalid_admin_form_have_feedback(self):
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        self.client.force_login(self.user)
        response = self.client.post(reverse('member_status', args=[self.member.pk]), {'status': Member.Status.ACTIVE}, follow=True)
        self.assert_success_notice(response, 'Membership status updated.')
        response = self.client.post(reverse('member_status', args=[self.member.pk]), {'status': 'unknown'}, follow=True)
        self.assertContains(response, 'data-level="error"', count=1)
        self.assertContains(response, 'Choose a valid membership status.')
        response = self.client.post(reverse('admin_shopping'), {'action': 'save_template', 'template-name': ''})
        self.assertContains(response, 'data-level="error"', count=1)
        self.assertContains(response, 'Name: This field is required.')
        self.assertTrue(response.context['template_form'].errors)
