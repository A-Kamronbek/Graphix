from django.db import models

from vm.settings import AUTH_USER_MODEL


class msg(models.Model):
    user = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)
    phone_num = models.CharField(max_length=25)
    topic = models.CharField(max_length=255)
    msg_text = models.TextField()


    def __str__(self):
        return f"{self.user}. {self.topic}"

