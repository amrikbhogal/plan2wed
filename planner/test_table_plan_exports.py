from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Member, SeatingAssignment, SeatingTable, WeddingBudget, WeddingGuest
from .table_plan_exports import plan_sections, table_plan_pdf


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TablePlanExportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='export-owner')
        self.member = Member.objects.create(user=self.user, email='owner@example.com')
        self.budget = WeddingBudget.objects.create(member=self.member)
        self.event = self.budget.events.create(name='Reception')
        self.table = SeatingTable.objects.create(event=self.event, name='Family & friends')
        self.guest = WeddingGuest.objects.create(budget=self.budget, first_name='Zoë', last_name='Singh')
        self.guest.events.add(self.event)
        SeatingAssignment.objects.create(event=self.event, table=self.table, guest=self.guest)
        self.url = reverse('table_plan_export', args=[self.event.pk])
        self.pdf_url = reverse('table_plan_pdf', args=[self.event.pk])
        self.client.force_login(self.user)

    def test_preview_download_and_print_controls(self):
        response = self.client.get(self.url)
        for text in ['Family &amp; friends', 'Zoë Singh', 'Download PDF', 'window.print()', 'Send PDF by email']:
            self.assertContains(response, text)
        response = self.client.get(self.pdf_url)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(len(mail.outbox), 0)

    def test_email_attaches_pdf_only_after_valid_submission(self):
        response = self.client.post(self.url, {'recipient': 'invalid'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        response = self.client.post(self.url, {'recipient': 'venue@example.com'})
        self.assertRedirects(response, self.url)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['venue@example.com'])
        self.assertEqual(email.attachments[0].mimetype, 'application/pdf')
        self.assertTrue(email.attachments[0].content.startswith(b'%PDF-'))

    def test_failed_email_shows_retry_without_success(self):
        with patch('planner.table_plan_exports.EmailMessage.send', side_effect=OSError('SMTP unavailable')):
            with self.assertLogs('planner.table_plan_exports', level='ERROR'):
                response = self.client.post(self.url, {'recipient': 'venue@example.com'})
        self.assertContains(response, 'The email could not be sent.')
        self.assertNotContains(response, 'Table plan PDF sent by email.')

    def test_export_is_private_and_respects_disabled_planning(self):
        self.client.force_login(get_user_model().objects.create_user(username='other-export-user'))
        other = Member.objects.create(user=get_user_model().objects.get(username='other-export-user'), email='other@example.com')
        for url in [self.url, self.pdf_url]:
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {'recipient': other.email}).status_code, 404)
        self.client.force_login(self.user)
        self.event.requires_table_plan = False
        self.event.save()
        for url in [self.url, self.pdf_url]:
            self.assertRedirects(self.client.get(url), reverse('event_detail', args=[self.event.pk]))
        self.client.logout()
        self.assertEqual(self.client.get(self.pdf_url).status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_declined_uninvited_and_other_budget_guests_are_excluded(self):
        self.guest.rsvp_status = WeddingGuest.RSVPStatus.DECLINED
        self.guest.save()
        unseated = WeddingGuest.objects.create(budget=self.budget, first_name='Unseated')
        unseated.events.add(self.event)
        uninvited = WeddingGuest.objects.create(budget=self.budget, first_name='Uninvited')
        SeatingAssignment.objects.create(event=self.event, table=self.table, guest=uninvited)
        sections = plan_sections(self.event)
        self.assertEqual(sections[0]['guests'], [])
        self.assertEqual(sections[-1]['name'], 'Unseated guests')
        self.assertEqual(sections[-1]['guests'], [unseated])

    def test_long_names_and_large_tables_paginate(self):
        sections = [{'name': 'Family <table> & friends ' * 3, 'guests': ['Long guest name ' * 8 for _ in range(150)]}]
        pdf = table_plan_pdf(self.event, sections)
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertGreater(len(pdf), 10000)
        empty_pdf = table_plan_pdf(self.event, [])
        self.assertTrue(empty_pdf.startswith(b'%PDF-'))
