"""Catalogue signals: tell the owner a review needs moderation, and keep the
product's rating true to its approved reviews.

Signals rather than calls at the call sites, because there is more than one way
a review appears or changes — the customer's form, the admin's add page, the
admin's change form, a cascade when an account is deleted. Wiring the work to
the *event* means a path nobody thought of is still covered, which is the whole
argument for paying the signal's indirection.

The one path signals cannot see is a bulk ``update()``, which is exactly what
moderating a selection in the admin does. ``services.moderate`` therefore
recomputes explicitly, and these two ways of arriving at the same guarantee are
covered by their own tests.

Nothing here may raise: ``core.telegram`` swallows its own failures, and the
send is queued on transaction commit rather than run inline.
"""
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core import telegram
from .models import Review
from .services import recompute_rating


@receiver(post_save, sender=Review, dispatch_uid='notify_pending_review')
def notify_pending_review(sender, instance, created, **kwargs):
    """Notify on a new review that is waiting for moderation.

    Only on creation, and only while it is pending: approving or rejecting one
    saves it again, and the owner does not need to be told about a decision he
    just made.
    """
    if created and instance.status == Review.Status.PENDING:
        # Composed at commit, not here. `create_review` writes the review first
        # and its photographs immediately after, both inside one transaction —
        # so at the moment this signal fires the review has no images yet, and
        # the "a photograph is attached" line never appeared on the one kind of
        # review that most needs a human to look at it. `notify` already defers
        # the *send*; what has to be deferred is reading the row.
        transaction.on_commit(lambda: telegram.notify_review(instance))


@receiver(post_save, sender=Review, dispatch_uid='review_saved_rating')
@receiver(post_delete, sender=Review, dispatch_uid='review_deleted_rating')
def keep_rating_true(sender, instance, **kwargs):
    """Recount the product's rating whenever one of its reviews changes.

    Unconditional on purpose. Working out whether *this* save could have moved
    the number means knowing the row's previous status, which a signal does not
    get — and getting that wrong leaves a product advertising a rating it no
    longer has. A recount is one aggregate over a few rows; the caution is
    free.
    """
    recompute_rating(instance.product_id)
