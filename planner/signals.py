from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from .models import SeatingAssignment, WeddingGuest


@receiver(m2m_changed, sender=WeddingGuest.events.through)
def release_removed_invitations(sender, instance, action, reverse, using, **kwargs):
    if action not in {"post_remove", "post_clear"}:
        return
    assignments = SeatingAssignment.objects.using(using)
    if reverse:
        assignments.filter(event=instance).exclude(guest__in=instance.guests.all()).delete()
    else:
        assignments.filter(guest=instance).exclude(event__in=instance.events.all()).delete()


@receiver(post_save, sender=WeddingGuest)
def release_declined_seats(sender, instance, using, **kwargs):
    if instance.rsvp_status == WeddingGuest.RSVPStatus.DECLINED:
        SeatingAssignment.objects.using(using).filter(guest=instance).delete()
