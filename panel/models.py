"""One table: who changed an order's status, when, and from what.

It lives in ``panel`` rather than in ``payment`` because it exists for the
panel's sake — payment does not read it and should not have to know it is
there. Nothing about an order depends on it, so a lost row costs the history
and not the order.

Why a table of our own rather than ``django.contrib.admin.models.LogEntry``
(§17, Phase 7): LogEntry records a free-text change message against a generic
object, which is fine for "somebody edited this" and useless for "show me
every order that went from paid to cancelled last week". The panel needs the
second question answered, and answering it from a text column is not a thing
worth building.
"""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class OrderStatusChange(models.Model):
    """A single move from one status to another, with its author.

    ``changed_by`` is SET_NULL so the history survives a staff member leaving:
    an order's trail is about the order, not about who still has an account.
    The status values are stored as plain text rather than as a FK to the
    choices, so a future rename of a status label cannot rewrite what actually
    happened.
    """
    order = models.ForeignKey('payment.Order', on_delete=models.CASCADE,
                              related_name='status_changes')
    from_status = models.CharField(max_length=50, blank=True, default='')
    to_status = models.CharField(max_length=50)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='order_status_changes')
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    note = models.CharField(max_length=200, blank=True, default='')

    def __str__(self):
        return f"{self.order_id}: {self.from_status or '—'} → {self.to_status}"

    @staticmethod
    def _label(value):
        """The human label for a stored status value, or the value itself.

        Falls back rather than raising: these columns are plain text on purpose
        so that a status removed from the choices in a year's time still reads
        as *something* in the history it belongs to, instead of taking the
        whole page down with a ValueError.
        """
        from payment.models import Order
        try:
            return Order.Status(value).label
        except ValueError:
            return value

    @property
    def from_label(self):
        return self._label(self.from_status) if self.from_status else ''

    @property
    def to_label(self):
        return self._label(self.to_status)

    class Meta:
        verbose_name = _('Holat oʻzgarishi')
        verbose_name_plural = _('Holat oʻzgarishlari')
        ordering = ['-changed_at', '-id']
        indexes = [models.Index(fields=['order', '-changed_at'])]
