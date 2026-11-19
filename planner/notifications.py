"""Member account emails, delivered only after registration commits."""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger(__name__)


def send_member_verification(member, token):
    verification_url = settings.PLAN2WED_SITE_URL + reverse('verify_email', args=[token])
    try:
        sent = send_mail(
            subject='Verify your email to activate your Plan2Wed membership',
            message=render_to_string('planner/emails/verify_email.txt', {
                'member': member, 'verification_url': verification_url,
                'resend_url': settings.PLAN2WED_SITE_URL + reverse('resend_verification'),
            }),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[member.email],
        )
        if not sent:
            logger.error('Verification email was not delivered; member id=%s', member.pk)
    except Exception:
        # Keep the pending registration so the member can request another email.
        logger.exception('Verification email delivery failed; member id=%s', member.pk)
