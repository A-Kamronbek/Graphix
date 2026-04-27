from django.contrib.auth.models import User
from django.db import models
from cart.models import Cart


class Address(models.Model):
    regions = [
        ('andijon', 'Andijon viloyati'),
        ('buxoro', 'Buxoro viloyati'),
        ('fargona', 'Farg\'ona viloyati'),
        ('jizzax', 'Jizzax viloyati'),
        ('xorazm', 'Xorazm viloyati'),
        ('namangan', 'Namangan viloyati'),
        ('navoiy', 'Navoiy viloyati'),
        ('qashqadaryo', 'Qashqadaryo viloyati'),
        ('qoraqalpogiston', 'Qoraqalpog\'iston Respublikasi'),
        ('samarqand', 'Samarqand viloyati'),
        ('sirdaryo', 'Sirdaryo viloyati'),
        ('surxondaryo', 'Surxondaryo viloyati'),
        ('toshkent_sh', 'Toshkent Shahri'),
        ('toshkent', 'Toshkent viloyati'),
    ]

    region = models.CharField(max_length=50, choices=regions, db_index=True)
    district = models.CharField(max_length=50)
    street = models.CharField(max_length=150)

    def get_address(self):
        return f"{self.get_region_display()}, {self.district}, {self.street}"

    def __str__(self):
        return self.get_address()

class Order(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        PAYING = 'paying', 'Paying'
        PAID = 'paid', 'Paid'
        PROCESSING = 'processing', 'Processing'
        ON_THE_WAY = 'on_the_way', 'On the Way'
        DONE = 'done', 'Done'
        CANCELLED = 'cancelled', 'Cancelled'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    cart = models.OneToOneField(Cart, on_delete=models.CASCADE, related_name='order')
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    address = models.CharField(max_length=255) # get_address() in views
    created_at = models.DateTimeField(auto_now_add=True)
    total_price = models.DecimalField(max_digits=15, decimal_places=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order {self.id} | {self.user.username} | {self.get_status_display()}"

    class Meta:
        ordering = ['-created_at']
