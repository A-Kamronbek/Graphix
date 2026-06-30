"""Catalog models: categories, products, images, sizes, colours, and variants."""
from django.db import models
from colorfield.fields import ColorField


class Category(models.Model):
    """A product category (e.g. shirts, trousers)."""
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

class Product(models.Model):
    """A catalog product; its sizes, colours, and prices live on related Variants."""
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')

    def __str__(self):
        return self.name

class ImageP(models.Model):
    """A product photo, displayed in ``order`` (lowest first)."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    picture = models.ImageField(upload_to="products/")
    order = models.PositiveSmallIntegerField()

    def __str__(self):
        return f"{self.id} | {self.product.name} | {self.order} | {self.picture.name.split('/')[-1]}"

    class Meta:
        ordering = ['order', 'id']

class Size(models.Model):
    """A selectable size value."""
    size = models.CharField(max_length=50)

    def __str__(self):
        return self.size

class Colour(models.Model):
    """A selectable colour, with an optional hex code for the swatch."""
    colour = models.CharField(max_length=100)
    hex_code = ColorField(null=True, blank=True)

    def __str__(self):
        return self.colour

class Variant(models.Model):
    """A buyable variant (product + size + colour) with its own price.

    ``unique_together`` keeps one row per (product, size, colour); ``available``
    controls whether it can currently be purchased.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    size = models.ForeignKey(Size, on_delete=models.PROTECT)
    colour = models.ForeignKey(Colour, on_delete=models.PROTECT)
    price = models.DecimalField(max_digits=15, decimal_places=0)
    available = models.BooleanField(default=False)

    def __str__(self):
        return  f"{self.product.name} | {self.colour.colour} | {self.size.size}"

    class Meta:
        unique_together = ('product', 'size', 'colour')
        ordering = ['product', 'size']
