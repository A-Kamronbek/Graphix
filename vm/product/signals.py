"""Catalogue signals. One, today: tell the owner a review needs moderation.

A signal rather than a call in the review form, because there is more than one
way a review gets created — the admin can add one now, and Phase 12 adds the
customer's own form. Wiring the notification to the *creation* rather than to
one call site means Phase 12 does not have to remember, and a path nobody
thought of still gets caught.

Nothing here may raise: ``core.telegram`` swallows its own failures, and the
send is queued on transaction commit rather than run inline.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from core import telegram
from .models import Review


@receiver(post_save, sender=Review, dispatch_uid='notify_pending_review')
def notify_pending_review(sender, instance, created, **kwargs):
    """Notify on a new review that is waiting for moderation.

    Only on creation, and only while it is pending: approving or rejecting one
    saves it again, and the owner does not need to be told about a decision he
    just made.
    """
    if created and instance.status == Review.Status.PENDING:
        telegram.notify_review(instance)
