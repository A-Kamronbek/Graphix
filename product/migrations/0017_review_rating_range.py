"""Make a rating outside 1-5 impossible at the database, not only in a view.

``Review.rating`` carries ``choices``, which is a form-and-admin convenience
and is enforced by nothing that writes through the ORM. The column feeds
``Product.rating_avg`` — a public number on a public page — so one bad row
would skew it with nothing to notice. Every existing row is already 1-5, so
this applies without a backfill.
"""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0015_delivery_price_and_payment_options'),
        ('product', '0016_seed_size_charts'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='review',
            constraint=models.CheckConstraint(condition=models.Q(('rating__gte', 1), ('rating__lte', 5)), name='review_rating_between_1_and_5'),
        ),
    ]
