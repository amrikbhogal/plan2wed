from datetime import timedelta
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail, signing
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .email_verification import VERIFICATION_SALT, request_email_verification, verification_token
from .models import Member, WeddingBudget


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', PLAN2WED_SITE_URL='https://plan2wed.co.uk')
class EmailVerificationTests(TestCase):
    password = 'LongUniqueVerificationPassword!2026'

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='verify@example.com', email='verify@example.com', password=self.password, is_active=False)
        self.member = Member.objects.create(user=self.user, email=self.user.email, first_name='Alex', last_name='Smith')
        self.budget = WeddingBudget.objects.create(member=self.member)
        self.url = reverse('verify_email', args=[verification_token(self.member)])

    def assert_pending(self):
        self.member.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.member.status, Member.Status.PENDING)
        self.assertIsNone(self.member.email_verified_at)
        self.assertFalse(self.user.is_active)

    def resend(self, email=None):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse('resend_verification'), {'email': email or self.member.email})

    def email_url(self):
        return re.search(r'https://plan2wed.co.uk(/verify-email/[^\s]+)', mail.outbox[-1].body)[1]

    def test_email_link_preview_does_not_activate_and_confirmation_allows_login(self):
        self.assertFalse(self.client.login(username=self.user.username, password=self.password))
        response = self.client.get(self.url)
        self.assertContains(response, 'Verify email and activate membership')
        self.assertEqual(response['Referrer-Policy'], 'no-referrer')
        self.assertIn('no-store', response['Cache-Control'])
        self.assert_pending()
        response = self.client.post(self.url, follow=True)
        self.assertContains(response, 'Your email is verified and your membership is active.')
        self.member.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.member.status, Member.Status.ACTIVE)
        self.assertIsNotNone(self.member.email_verified_at)
        self.assertTrue(self.user.is_active)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertTrue(self.client.login(username=self.user.username, password=self.password))
        self.assertEqual(self.client.get(reverse('member_portal')).status_code, 200)
        self.assertEqual(self.member.wedding_budget.pk, self.budget.pk)

    def test_used_link_cannot_be_reused_or_reactivate_suspended_account(self):
        self.client.post(self.url)
        verified_at = Member.objects.get(pk=self.member.pk).email_verified_at
        for method in (self.client.get, self.client.post):
            response = method(self.url)
            self.assertContains(response, 'data-level="error"', count=1)
        self.member.refresh_from_db()
        self.assertEqual(self.member.email_verified_at, verified_at)
        self.member.status = Member.Status.INACTIVE
        self.member.save(update_fields=['status'])
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.client.post(self.url)
        self.user.refresh_from_db()
        self.member.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(self.member.status, Member.Status.INACTIVE)

    def test_invalid_tampered_and_expired_links_do_not_activate(self):
        with patch('django.core.signing.time.time', return_value=timezone.now().timestamp() - 86401):
            expired = reverse('verify_email', args=[verification_token(self.member)])
        tampered = reverse('verify_email', args=[verification_token(self.member) + 'x'])
        for url in (reverse('verify_email', args=['invalid']), tampered, expired):
            for method in (self.client.get, self.client.post):
                response = method(url)
                self.assertContains(response, 'data-level="error"', count=1)
                self.assertContains(response, reverse('resend_verification'))
                self.assert_pending()

    def test_changed_email_invalidates_link(self):
        self.member.email = 'changed@example.com'
        self.member.save(update_fields=['email'])
        self.user.email = self.member.email
        self.user.save(update_fields=['email'])
        self.assertContains(self.client.post(self.url), 'data-level="error"')
        self.assert_pending()

    def test_different_link_user_email_or_invalid_member_cannot_be_activated(self):
        self.user.email = 'different@example.com'
        self.user.save(update_fields=['email'])
        self.assertContains(self.client.post(self.url), 'data-level="error"')
        self.assert_pending()
        token = signing.dumps({'member_id': 999999, 'nonce': 'unknown'}, salt=VERIFICATION_SALT)
        self.assertContains(self.client.post(reverse('verify_email', args=[token])), 'data-level="error"')

    def test_resend_rotates_link_and_is_throttled(self):
        response = self.resend(' VERIFY@example.com ')
        self.assertRedirects(response, reverse('resend_verification'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.member.email])
        first_link = self.email_url()
        self.assertContains(self.client.get(self.url), 'data-level="error"')
        self.assertContains(self.client.get(first_link), 'Verify email and activate membership')
        self.resend()
        self.assertEqual(len(mail.outbox), 1)
        Member.objects.filter(pk=self.member.pk).update(email_verification_sent_at=timezone.now() - timedelta(seconds=61))
        self.resend()
        self.assertEqual(len(mail.outbox), 2)
        self.assertNotEqual(first_link, self.email_url())
        self.assertContains(self.client.get(first_link), 'data-level="error"')
        self.client.post(self.email_url())
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_resend_unknown_active_suspended_and_staff_accounts_are_generic(self):
        addresses = ['unknown@example.com']
        for status, active, staff in ((Member.Status.ACTIVE, True, False), (Member.Status.INACTIVE, False, False), (Member.Status.PENDING, False, True)):
            email = f'{status}-{staff}@example.com'
            user = get_user_model().objects.create_user(username=email, email=email, is_active=active, is_staff=staff)
            Member.objects.create(user=user, email=email, status=status)
            addresses.append(email)
        pages = []
        for address in addresses:
            response = self.resend(address)
            self.assertRedirects(response, reverse('resend_verification'), fetch_redirect_response=False)
            page = self.client.get(response.url)
            self.assertContains(page, 'If that email belongs to an unverified registration')
            pages.append(page.status_code)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(pages, [200] * len(addresses))

    def test_inactive_and_staff_status_cannot_be_verified_with_existing_token(self):
        self.member.status = Member.Status.INACTIVE
        self.member.save(update_fields=['status'])
        self.assertContains(self.client.post(self.url), 'data-level="error"')
        self.member.status = Member.Status.PENDING
        self.member.save(update_fields=['status'])
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        self.assertContains(self.client.post(self.url), 'data-level="error"')
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_resend_validation_is_in_shared_notifications(self):
        response = self.client.post(reverse('resend_verification'), {'email': 'invalid'})
        self.assertContains(response, 'data-level="error"', count=1)
        self.assertEqual(len(mail.outbox), 0)

    def test_csrf_is_required_to_activate_or_resend(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.url).status_code, 403)
        self.assertEqual(client.post(reverse('resend_verification'), {'email': self.member.email}).status_code, 403)
        response = client.get(self.url)
        self.assertContains(response, 'Verify email and activate membership')
        self.assert_pending()
        response = client.post(self.url, {'csrfmiddlewaretoken': client.cookies['csrftoken'].value})
        self.assertRedirects(response, reverse('login'))

    def test_mail_is_not_sent_before_commit_or_after_rollback(self):
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    request_email_verification(self.member.pk)
                    self.assertEqual(len(mail.outbox), 0)
                    raise ValueError('Rollback registration')
            except ValueError:
                pass
        self.assertEqual(len(mail.outbox), 0)
        self.member.refresh_from_db()
        self.assertIsNone(self.member.email_verification_sent_at)

    def test_email_failure_keeps_account_pending_and_resend_can_recover(self):
        with patch('planner.notifications.send_mail', side_effect=OSError('SMTP unavailable')):
            with self.assertLogs('planner.notifications', level='ERROR'):
                self.resend()
        self.assert_pending()
        Member.objects.filter(pk=self.member.pk).update(email_verification_sent_at=timezone.now() - timedelta(seconds=61))
        self.resend()
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(self.client.get(self.email_url()), 'Verify email and activate membership')

    def test_public_links_and_legacy_active_account_are_preserved(self):
        self.assertContains(self.client.get(reverse('login')), reverse('resend_verification'))
        self.assertContains(self.client.get(reverse('signup_complete')), reverse('resend_verification'))
        self.user.is_active = True
        self.user.save(update_fields=['is_active'])
        self.member.status = Member.Status.ACTIVE
        self.member.save(update_fields=['status'])
        self.assertTrue(self.client.login(username=self.user.username, password=self.password))
        self.assertEqual(self.client.get(reverse('member_portal')).status_code, 200)
