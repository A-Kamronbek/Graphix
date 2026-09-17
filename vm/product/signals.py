"""Catalogue signals: tell the owner a review needs moderation, keep the
product's rating true to its approved reviews, and take an image's file away
with its row.

Signals rather than calls at the call sites, because there is more than one way
a review appears or changes — the customer's form, the admin's add page, the
admin's change form, a cascade when a product is deleted. Wiring the work to
the *event* means a path nobody thought of is still covered, which is the whole
argument for paying the signal's indirection.

The one path signals cannot see is a bulk ``update()``, which is exactly what
moderating a selection in the admin does. ``services.moderate`` therefore
recomputes explicitly, and these two ways of arriving at the same guarantee are
covered by their own tests.

**Files.** Deleting a row that holds an image left the file on disk (§18 #28).
Django stopped deleting files with their rows in 1.3, for two reasons: a
transaction that rolls back needs the file where it was, and two rows may name
the same file. Both are real here — the demo seed deletes the catalogue and
recreates rows over the very same photographs inside one transaction. So a
file goes only once the delete has committed, and only if no row names it any
more. Bulk ``delete()`` is covered too: unlike ``update()``, it sends
``post_delete`` for every row when a receiver is listening.

Nothing here may raise: ``core.telegram`` swallows its own failures, the send
is queued on transaction commit rather than run inline, and a file that will
not delete is logged and left.
"""
import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core import telegram
from .models import ImageP, Review, ReviewImage, SizeChart
from .services import recompute_rating

logger = logging.getLogger(__name__)

#: Every column that holds an uploaded image, as ``(model, field name)``. A
#: file is still in use while any of them names it.
FILE_COLUMNS = ((ImageP, 'picture'), (ReviewImage, 'picture'), (SizeChart, 'image'))


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


def still_used(name, using=None):
    """Does any row, in any image column, still name the stored file ``name``?"""
    return any(model._base_manager.using(using).filter(**{field: name}).exists()
               for model, field in FILE_COLUMNS)


def forget_file(fieldfile, using=None):
    """Delete ``fieldfile``'s file once the delete of its row has committed.

    The name and the storage are read now, while the instance is at hand; the
    check and the delete wait for the commit, and a rollback drops them. A
    stray file costs disk space and a delete that raised would turn a tidy-up
    into an error page, so a failure is logged and nothing more.
    """
    name, storage = fieldfile.name, fieldfile.storage
    if not name:
        return

    def remove():
        try:
            if not still_used(name, using):
                storage.delete(name)
        except Exception:
            logger.exception('could not delete the file %s', name)

    transaction.on_commit(remove, using=using)


@receiver(post_delete, sender=ImageP, dispatch_uid='product_photo_file')
@receiver(post_delete, sender=ReviewImage, dispatch_uid='review_photo_file')
def photo_file_goes_with_its_row(sender, instance, using=None, **kwargs):
    """A deleted product or review photograph takes its file with it (§18 #28)."""
    forget_file(instance.picture, using)


@receiver(post_delete, sender=SizeChart, dispatch_uid='size_chart_file')
def chart_file_goes_with_its_row(sender, instance, using=None, **kwargs):
    """A deleted size chart takes its picture with it."""
    forget_file(instance.image, using)
