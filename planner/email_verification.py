"""Expiring, single-use verification for pending member registrations."""
from datetime import timedelta
import secrets
import uuid

from django.core import signing
from django.db import transaction
from django.utils import timezone

from .models import Member
from .notifications import send_member_verification

VERIFICATION_MAX_AGE = 24 * 60 * 60
VERIFICATION_RESEND_DELAY = timedelta(seconds=60)
VERIFICATION_SALT = 'planner.member-email-verification'


def verification_token(member):
    return signing.dumps(
        {'member_id': member.pk, 'email': member.email, 'nonce': str(member.email_verification_nonce)},
        salt=VERIFICATION_SALT,
    )


def pending_verifications():
    # Suspended accounts and accounts already activated by staff cannot be
    # reactivated by an old verification email or by the public resend form.
    return Member.objects.filter(
        status=Member.Status.PENDING, email_verified_at__isnull=True,
        user__is_active=False, user__is_staff=False, user__is_superuser=False,
    )


def matches_verification(member, payload):
    return (
        member.email_verification_nonce is not None
        and member.email == payload.get('email')
        and member.email.lower() == member.user.email.lower()
        and secrets.compare_digest(str(member.email_verification_nonce), str(payload.get('nonce', '')))
    )


def verification_payload(token):
    try:
        payload = signing.loads(token, salt=VERIFICATION_SALT, max_age=VERIFICATION_MAX_AGE)
        if isinstance(payload, dict) and type(payload.get('member_id')) is int and 0 < payload['member_id'] <= 2**63 - 1:
            return payload
    except (signing.BadSignature, ValueError, TypeError):
        pass
    return None


def request_email_verification(member_id):
    with transaction.atomic():
        member = pending_verifications().select_for_update(of=('self',)).select_related('user').filter(pk=member_id).first()
        if member is None or member.email.lower() != member.user.email.lower():
            return
        now = timezone.now()
        if member.email_verification_sent_at and now - member.email_verification_sent_at < VERIFICATION_RESEND_DELAY:
            return
        member.email_verification_nonce = uuid.uuid4()
        member.email_verification_sent_at = now
        member.save(update_fields=['email_verification_nonce', 'email_verification_sent_at'])
        token = verification_token(member)
        transaction.on_commit(lambda: send_member_verification(member, token), robust=True)
