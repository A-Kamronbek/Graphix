from django.db import models
from colorfield.fields import ColorField


class Category(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')

    def __str__(self):
        return self.name

class ImageP(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    picture = models.ImageField(upload_to="products/")

    def __str__(self):
        return f"{self.id} | {self.product.name} | {self.picture.name.split('/')[-1]}"

class Size(models.Model):
    size = models.CharField(max_length=50)

    def __str__(self):
        return self.size

class Colour(models.Model):
    colour = models.CharField(max_length=100)
    hex_code = ColorField(null=True, blank=True)

    def __str__(self):
        return self.colour

class Variant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    size = models.ForeignKey(Size, on_delete=models.CASCADE)
    colour = models.ForeignKey(Colour, on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=10, decimal_places=0)
    available = models.BooleanField(default=False)

    def __str__(self):
        return  f"{self.product.name} | {self.colour.colour} | {self.size.size}"

    class Meta:
        unique_together = ('product', 'size', 'colour')
        ordering = ['product', 'size']
