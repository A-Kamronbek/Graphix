"""Core models: the contact-form message and the suggested design."""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from product.models import Photograph


class Msg(models.Model):
    """A message submitted through the contact form."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    phone_num = models.CharField(max_length=25)
    topic = models.CharField(max_length=255)
    msg_text = models.TextField()
    # The panel's dashboard counts unread messages and its inbox marks them
    # read (§9 Phase 7 items 1 and 9). A message with nothing to say whether
    # anyone has looked at it turns an inbox into a list you re-read every
    # morning. Indexed because the count is on every dashboard load.
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return f"{self.user}. {self.topic}"

    class Meta:
        ordering = ['-id']


def design_photo_path(instance, filename):
    """Where a suggestion's picture is stored: a name nobody can guess.

    A customer's sketch or logo, shown to staff and nowhere else (§9 Phase 23
    item 26). The media folder is served as it is, so the name is what keeps
    one from being found: random, and carrying nothing about the customer.
    """
    import secrets
    return 'designs/%s.jpg' % secrets.token_urlsafe(18)


class DesignRequest(models.Model):
    """A design a customer suggests to the owner (§17 #402).

    Phase 23 part E. A request, not an order: the owner reads it in the
    panel's "Dizaynlar", rings or writes back, and marks it read, as a
    contact message is (§17 #155). Nothing about it is priced or paid on the
    site. The rules for what may be sent are `core/designs.py`.

    The size is kept as its label rather than a key to `Size`: the request
    says what the customer asked for, and a size the owner later renames or
    deletes should not change or lose it.
    """

    class Garment(models.TextChoices):
        TSHIRT = 'tshirt', _('Futbolka')
        LONGSLEEVE = 'longsleeve', _('Longsliv')

    class Colour(models.TextChoices):
        """The garment's colour: a short fixed list, and another in words (§17 #406)."""
        WHITE = 'white', _('Oq')
        BLACK = 'black', _('Qora')
        GREY = 'grey', _('Kulrang')
        OTHER = 'other', _('Boshqa rang')

    class Placement(models.TextChoices):
        FRONT = 'front', _('Old tomonga')
        BACK = 'back', _('Orqa tomonga')
        BOTH = 'both', _('Ikkala tomonga')

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='design_requests')
    idea = models.TextField()
    print_text = models.CharField(max_length=200, blank=True, default='')
    garment = models.CharField(max_length=12, choices=Garment.choices)
    colour = models.CharField(max_length=8, choices=Colour.choices)
    colour_other = models.CharField(max_length=60, blank=True, default='')
    #: Up to three ``#rrggbb``, space-separated, in the order they were picked.
    print_colours = models.CharField(max_length=32, blank=True, default='')
    placement = models.CharField(max_length=8, choices=Placement.choices)
    size = models.CharField(max_length=20)
    quantity = models.PositiveSmallIntegerField(default=1)
    phone = models.CharField(max_length=25)
    # Read and unread, as the contact form's messages (§17 #155). Indexed
    # because the dashboard counts the unread ones on every load.
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"{self.user} · {self.get_garment_display()} · {self.created_at:%Y-%m-%d}"

    @property
    def colour_label(self):
        """The garment's colour as the customer said it."""
        if self.colour == self.Colour.OTHER and self.colour_other:
            return self.colour_other
        return self.get_colour_display()

    @property
    def colour_list(self):
        """The print's colours, as a list of ``#rrggbb``."""
        return self.print_colours.split()


class DesignImage(Photograph):
    """A picture attached to a suggested design: a sketch, a logo, an example.

    Cleaned as a review's photographs are (`product.images.sanitise`):
    re-encoded, its metadata dropped (§17 #132), with a transparent ground
    made grey rather than white so a white logo stays visible. Kept as long
    as its request.
    """
    request = models.ForeignKey(DesignRequest, on_delete=models.CASCADE, related_name='images')
    picture = models.ImageField(upload_to=design_photo_path)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.request_id} · {self.order}"
