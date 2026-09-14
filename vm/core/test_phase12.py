"""Phase 12: reviews, moderation, and the rating that follows them.

Three of these protect something that cannot be undone once it is wrong:

* a review is invisible until a human approves it — photos are user content on
  a public page (§17 #25);
* only the person who actually received the parcel can write one, which is the
  entire basis of the "verified purchase" badge;
* an uploaded photograph carries no EXIF, because a phone writes the customer's
  home coordinates into it by default and publishing that is a privacy breach
  committed by accident.
"""
import io
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import translation
from PIL import Image

from cart.models import Cart, CartItem
from product import images, services
from product.models import Product, Review, ReviewImage

from .test_phase4 import make_product
from .test_phase6 import make_user


def make_order(user, variant, status='done'):
    """A real order for ``variant``, in ``status``."""
    from payment.models import Order
    cart = Cart.objects.create(user=user, status=False)
    CartItem.objects.create(cart=cart, variant=variant, quantity=1,
                            price_stat=variant.price)
    return Order.objects.create(user=user, cart=cart, phone=user.phone,
                                address='Amir Temur 1', total_price=variant.price,
                                status=status)


def photo(size=(40, 30), fmt='JPEG', exif=None):
    """An uploaded image file, optionally carrying EXIF."""
    buf = io.BytesIO()
    image = Image.new('RGB', size, (200, 120, 60))
    if exif is not None:
        image.save(buf, format=fmt, exif=exif)
    else:
        image.save(buf, format=fmt)
    return SimpleUploadedFile('photo.jpg', buf.getvalue(),
                              content_type=f'image/{fmt.lower()}')


class EligibilityTests(TestCase):
    """Who may write a review. Every rule, each on its own."""

    def setUp(self):
        self.user = make_user('sharhchi', '+998901110001')
        self.other = make_user('boshqa', '+998901110002')
        self.product, self.variant = make_product('Sharhli', stock=5)
        self.order = make_order(self.user, self.variant)

    def test_a_delivered_purchaser_may_review(self):
        services.check_may_review(self.user, self.order, self.product)   # no raise

    def test_someone_elses_order_grants_nothing(self):
        with self.assertRaises(services.NotEligible):
            services.check_may_review(self.other, self.order, self.product)

    def test_an_undelivered_order_grants_nothing(self):
        """Paid is not delivered — and it is what someone gaming ratings has."""
        for status in ('paying', 'paid', 'processing', 'on_the_way', 'cancelled'):
            with self.subTest(status=status):
                order = make_order(self.user, self.variant, status=status)
                with self.assertRaises(services.NotEligible):
                    services.check_may_review(self.user, order, self.product)

    def test_a_product_that_was_not_in_the_order_grants_nothing(self):
        elsewhere, _ = make_product('Boshqa mahsulot', stock=2)
        with self.assertRaises(services.NotEligible):
            services.check_may_review(self.user, self.order, elsewhere)

    def test_one_review_per_person_per_product(self):
        services.create_review(self.user, self.order, self.product, 5)
        with self.assertRaises(services.NotEligible):
            services.check_may_review(self.user, self.order, self.product)

    def test_a_second_order_does_not_grant_a_second_review(self):
        """Buying the same shirt twice is not two opinions."""
        services.create_review(self.user, self.order, self.product, 4)
        again = make_order(self.user, self.variant)
        with self.assertRaises(services.NotEligible):
            services.check_may_review(self.user, again, self.product)


class ModerationTests(TestCase):
    """Nothing reaches the page before a human says so, and the rating follows."""

    def setUp(self):
        self.user = make_user('bahochi', '+998901110003')
        self.product, self.variant = make_product('Bahoulash', stock=9)
        self.order = make_order(self.user, self.variant)

    def _review(self, user, rating):
        order = make_order(user, self.variant)
        return services.create_review(user, order, self.product, rating)

    def test_a_new_review_is_pending_and_moves_no_rating(self):
        review = services.create_review(self.user, self.order, self.product, 5)
        self.product.refresh_from_db()
        self.assertEqual(review.status, Review.Status.PENDING)
        self.assertEqual(self.product.review_count, 0)
        self.assertEqual(self.product.rating_avg, Decimal('0'))

    def test_approving_moves_the_rating(self):
        review = services.create_review(self.user, self.order, self.product, 4)
        services.moderate(Review.objects.filter(pk=review.pk), Review.Status.APPROVED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.review_count, 1)
        self.assertEqual(self.product.rating_avg, Decimal('4.0'))

    def test_the_average_counts_approved_reviews_only(self):
        """A pending 1-star must not drag down a published 5-star."""
        good = self._review(make_user('a', '+998901110011'), 5)
        services.moderate(Review.objects.filter(pk=good.pk), Review.Status.APPROVED)
        self._review(make_user('b', '+998901110012'), 1)      # left pending
        self.product.refresh_from_db()
        self.assertEqual(self.product.review_count, 1)
        self.assertEqual(self.product.rating_avg, Decimal('5.0'))

    def test_rejecting_an_approved_review_takes_it_back_out(self):
        review = self._review(make_user('c', '+998901110013'), 5)
        qs = Review.objects.filter(pk=review.pk)
        services.moderate(qs, Review.Status.APPROVED)
        services.moderate(qs, Review.Status.REJECTED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.review_count, 0)
        self.assertEqual(self.product.rating_avg, Decimal('0'))

    def test_the_average_is_rounded_to_one_decimal(self):
        """The column is DecimalField(max_digits=2, decimal_places=1); 4.25
        stars is false precision anyway."""
        for i, rating in enumerate((4, 4, 5, 4)):
            self._review(make_user(f'd{i}', f'+99890111002{i}'), rating)
        services.moderate(Review.objects.all(), Review.Status.APPROVED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.rating_avg, Decimal('4.3'))

    def test_saving_one_review_in_the_admin_also_moves_the_rating(self):
        """The bulk action is not the only path: the change form saves a row,
        which fires a signal instead."""
        review = services.create_review(self.user, self.order, self.product, 3)
        review.status = Review.Status.APPROVED
        review.save()
        self.product.refresh_from_db()
        self.assertEqual(self.product.review_count, 1)
        self.assertEqual(self.product.rating_avg, Decimal('3.0'))

    def test_deleting_a_review_takes_its_stars_with_it(self):
        review = self._review(make_user('e', '+998901110031'), 5)
        services.moderate(Review.objects.filter(pk=review.pk), Review.Status.APPROVED)
        review.delete()
        self.product.refresh_from_db()
        self.assertEqual(self.product.review_count, 0)

    def test_moderating_a_mixed_selection_fixes_every_product(self):
        """The admin selects a page of the queue, not one product's reviews."""
        other, other_variant = make_product('Ikkinchi', stock=3)
        u1, u2 = make_user('f', '+998901110041'), make_user('g', '+998901110042')
        services.create_review(u1, make_order(u1, self.variant), self.product, 5)
        services.create_review(u2, make_order(u2, other_variant), other, 3)
        services.moderate(Review.objects.all(), Review.Status.APPROVED)
        self.product.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.product.rating_avg, Decimal('5.0'))
        self.assertEqual(other.rating_avg, Decimal('3.0'))


class VisibilityTests(TestCase):
    """What the product page shows, and what it must not."""

    def setUp(self):
        self.user = make_user('koruvchi', '+998901110005')
        self.product, self.variant = make_product('Koʻrinish', stock=4)
        self.order = make_order(self.user, self.variant)

    def _page(self):
        """Fetch the product page in Uzbek, whatever ran before.

        LocaleMiddleware leaves the last request's language active for the rest
        of the process, so an unpinned reverse() here builds ``/en/…`` or
        ``/ru/…`` depending on test order — and the Uzbek copy asserted below
        then legitimately isn't on the page.
        """
        with translation.override('uz'):
            url = self.product.get_absolute_url()
        return self.client.get(url)

    def test_a_product_with_no_reviews_shows_no_review_block(self):
        """An empty rating reads worse than no rating at all."""
        response = self._page()
        self.assertNotContains(response, 'reviews-heading')
        self.assertNotContains(response, 'aggregateRating')

    def test_a_pending_review_is_on_no_page_at_all(self):
        services.create_review(self.user, self.order, self.product, 1,
                               text='Bu matn hech qayerda koʻrinmasligi kerak')
        response = self._page()
        self.assertNotContains(response, 'Bu matn hech qayerda')
        self.assertNotContains(response, 'reviews-heading')

    def test_an_approved_review_appears_with_its_badge(self):
        review = services.create_review(self.user, self.order, self.product, 5,
                                        text='Juda zoʻr futbolka')
        services.moderate(Review.objects.filter(pk=review.pk), Review.Status.APPROVED)
        response = self._page()
        self.assertContains(response, 'Juda zoʻr futbolka')
        self.assertContains(response, 'reviews-heading')
        self.assertContains(response, 'Tasdiqlangan xarid')

    def test_the_page_carries_structured_data_once_there_are_reviews(self):
        """The JSON-LD is what puts stars in a Google result."""
        review = services.create_review(self.user, self.order, self.product, 4)
        services.moderate(Review.objects.filter(pk=review.pk), Review.Status.APPROVED)
        html = self._page().content.decode()
        self.assertIn('application/ld+json', html)
        self.assertIn('"aggregateRating"', html)
        self.assertIn('"ratingValue": "4.0"', html)

    def test_review_text_cannot_close_the_json_ld_script(self):
        """A review is a stranger's text going into a <script> element."""
        review = services.create_review(
            self.user, self.order, self.product, 5,
            text='</script><img src=x onerror=alert(1)>')
        services.moderate(Review.objects.filter(pk=review.pk), Review.Status.APPROVED)
        html = self._page().content.decode()
        self.assertNotIn('</script><img', html)
        self.assertIn('\\u003c/script', html)


class SubmissionViewTests(TestCase):
    """The form itself, driven through the client."""

    def setUp(self):
        self.user = make_user('yozuvchi', '+998901110006')
        self.product, self.variant = make_product('Yozish', stock=6)
        self.order = make_order(self.user, self.variant)
        self.client.force_login(self.user)

    def url(self):
        return reverse('review_create', kwargs={'order_id': self.order.pk})

    def test_the_form_is_offered_for_a_delivered_order(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="rating"')

    def test_the_form_is_withheld_before_delivery(self):
        order = make_order(self.user, self.variant, status='paid')
        response = self.client.get(
            reverse('review_create', kwargs={'order_id': order.pk}))
        self.assertNotContains(response, 'name="rating"')

    def test_another_customers_order_is_a_404(self):
        intruder = make_user('begona', '+998901110007')
        self.client.force_login(intruder)
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_posting_creates_a_pending_review(self):
        self.client.post(self.url(), {'product': self.product.pk,
                                      'rating': '5', 'text': 'Ajoyib'})
        review = Review.objects.get(product=self.product, user=self.user)
        self.assertEqual(review.status, Review.Status.PENDING)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.order_id, self.order.pk)

    def test_a_rating_outside_one_to_five_is_refused(self):
        for bad in ('0', '6', '', 'ikki'):
            with self.subTest(bad=bad):
                self.client.post(self.url(), {'product': self.product.pk, 'rating': bad})
                self.assertFalse(Review.objects.filter(product=self.product).exists())

    def test_posting_for_a_product_that_was_not_bought_is_refused(self):
        elsewhere, _ = make_product('Sotib olinmagan', stock=1)
        self.client.post(self.url(), {'product': elsewhere.pk, 'rating': '5'})
        self.assertFalse(Review.objects.filter(product=elsewhere).exists())

    def test_photos_are_attached_and_capped(self):
        self.client.post(self.url(), {
            'product': self.product.pk, 'rating': '4',
            'photos': [photo(), photo()],
        })
        review = Review.objects.get(product=self.product)
        self.assertEqual(review.images.count(), 2)

    def test_more_than_four_photos_is_refused_whole(self):
        """Publishing three of four silently would leave the customer guessing."""
        self.client.post(self.url(), {
            'product': self.product.pk, 'rating': '4',
            'photos': [photo() for _ in range(5)],
        })
        self.assertFalse(Review.objects.filter(product=self.product).exists())
        self.assertEqual(ReviewImage.objects.count(), 0)

    def test_the_order_page_offers_the_link_only_once_delivered(self):
        delivered = self.client.get(reverse('order_detail', kwargs={'pk': self.order.pk}))
        self.assertContains(delivered, self.url())

        paid = make_order(self.user, self.variant, status='paid')
        response = self.client.get(reverse('order_detail', kwargs={'pk': paid.pk}))
        self.assertNotContains(
            response, reverse('review_create', kwargs={'order_id': paid.pk}))


class PhotoTests(TestCase):
    """The photo pipeline. The EXIF test is the one that matters."""

    def test_exif_does_not_survive(self):
        """A phone writes GPS into every photograph it takes."""
        exif = Image.Exif()
        exif[271] = 'GRAPHIX-TEST-CAMERA'          # Make
        exif[272] = 'SECRET-MODEL'                  # Model
        original = photo(exif=exif.tobytes())
        self.assertTrue(images.has_metadata(io.BytesIO(original.read())),
                        'the fixture carries no EXIF, so this proves nothing')
        original.seek(0)

        cleaned = images.sanitise(original)
        self.assertFalse(images.has_metadata(io.BytesIO(cleaned.read())))
        cleaned.seek(0)
        self.assertNotIn(b'SECRET-MODEL', cleaned.read())

    def test_a_large_photograph_is_shrunk(self):
        cleaned = images.sanitise(photo(size=(4000, 3000)))
        with Image.open(io.BytesIO(cleaned.read())) as out:
            self.assertLessEqual(max(out.size), images.MAX_EDGE)
            # Shrunk, not squashed: 4:3 in, 4:3 out.
            self.assertAlmostEqual(out.size[0] / out.size[1], 4 / 3, places=2)

    def test_a_small_photograph_is_left_its_own_size(self):
        cleaned = images.sanitise(photo(size=(40, 30)))
        with Image.open(io.BytesIO(cleaned.read())) as out:
            self.assertEqual(out.size, (40, 30))

    def test_a_file_that_is_not_an_image_is_refused(self):
        upload = SimpleUploadedFile('photo.jpg', b'not an image at all',
                                    content_type='image/jpeg')
        with self.assertRaises(ValidationError):
            images.sanitise(upload)

    def test_a_png_becomes_a_jpeg(self):
        """One stored format, and re-encoding is what strips the metadata."""
        cleaned = images.sanitise(photo(fmt='PNG'))
        with Image.open(io.BytesIO(cleaned.read())) as out:
            self.assertEqual(out.format, 'JPEG')

    def test_an_oversized_upload_is_refused_before_decoding(self):
        upload = SimpleUploadedFile('huge.jpg', b'x' * (images.MAX_BYTES + 1),
                                    content_type='image/jpeg')
        with self.assertRaises(ValidationError):
            images.sanitise(upload)
