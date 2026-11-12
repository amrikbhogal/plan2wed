"""Signup notifications sent after the account transaction commits."""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

logger = logging.getLogger(__name__)


def notify_administrator(member):
    if not settings.SIGNUP_NOTIFICATION_EMAILS:
        logger.error('Signup notification recipients are not configured; member id=%s', member.pk)
        return
    approval_url = settings.PLAN2WED_SITE_URL + reverse('admin:planner_member_change', args=[member.pk])
    try:
        send_mail(
            subject='Plan2Wed: new account awaiting approval',
            message=(f'A new account is awaiting your approval.\n\n'
                     f'Name: {member.first_name} {member.last_name}\n'
                     f'Email: {member.email}\n'
                     f'Account type: {member.get_signup_role_display()}\n\n'
                     f'Review account: {approval_url}\n\n'
                     'Sign in as an administrator and change membership status to Active to approve.\n'
                     'The account remains inactive until approved.\n'),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=settings.SIGNUP_NOTIFICATION_EMAILS,
        )
    except Exception:
        # Do not lose the pending account if the mail service is unavailable.
        logger.exception('Signup notification delivery failed; member id=%s', member.pk)
