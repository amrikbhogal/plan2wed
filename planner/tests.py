from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
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
            self.assertEqual(command[-2:], ['--psm', '1'])
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
