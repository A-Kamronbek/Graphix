"""Core models: the contact-form message."""
from django.db import models

from django.conf import  settings


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
