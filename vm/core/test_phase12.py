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
from product import images, services, views
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


    def test_a_decompression_bomb_is_refused_without_decoding_it(self):
        """A small file is not a small picture, and only one of them is checked.

        12 000 x 12 000 of one flat colour is ~140 KB on the wire and 432 MB of
        pixels. Pillow's own ceiling does not stop it — it warns at 89 Mpx and
        raises only at twice that — so without this guard any customer with a
        delivered order could spend the server's memory four files at a time.
        """
        buf = io.BytesIO()
        Image.new('RGB', (12000, 12000), (10, 10, 10)).save(buf, format='PNG')
        payload = buf.getvalue()
        self.assertLess(len(payload), images.MAX_BYTES,
                        'the bomb must be small enough to pass the size check, '
                        'or this tests the wrong guard')

        upload = SimpleUploadedFile('bomb.png', payload, content_type='image/png')
        with self.assertRaises(ValidationError) as caught:
            images.sanitise(upload)
        self.assertEqual(caught.exception.code, 'too_many_pixels')

    def test_every_allowed_format_can_actually_be_opened(self):
        """A format we accept but cannot decode is a promise we cannot keep.

        ALLOWED used to list HEIF and HEIC, which this Pillow has no codec for:
        an iPhone upload would have been refused with "that is not an image"
        rather than anything true.
        """
        openable = set(Image.registered_extensions().values())
        self.assertEqual(images.ALLOWED - openable, set(),
                         'these formats are accepted but Pillow cannot open them')


class LimitTests(TestCase):
    """The limits that exist only because a POST does not have to come from us."""

    def setUp(self):
        self.user = make_user('cheklov', '+998901110008')
        self.product, self.variant = make_product('Chegara', stock=3)
        self.order = make_order(self.user, self.variant)
        self.client.force_login(self.user)

    def url(self):
        return reverse('review_create', kwargs={'order_id': self.order.pk})

    def test_review_text_is_capped_server_side(self):
        """`maxlength` on a textarea is a convenience in a browser, not a limit."""
        self.client.post(self.url(), {'product': self.product.pk, 'rating': '5',
                                      'text': 'x' * (views.MAX_TEXT + 1)})
        self.assertFalse(Review.objects.filter(product=self.product).exists())

    def test_text_at_exactly_the_limit_is_accepted(self):
        """The boundary belongs to the customer, not to the error."""
        self.client.post(self.url(), {'product': self.product.pk, 'rating': '5',
                                      'text': 'x' * views.MAX_TEXT})
        self.assertTrue(Review.objects.filter(product=self.product).exists())

    def test_the_template_and_the_view_agree_about_the_limit(self):
        """Two copies of a number is one number that will drift (§17 #111)."""
        response = self.client.get(self.url())
        self.assertContains(response, 'maxlength="%d"' % views.MAX_TEXT)

    def test_a_rating_outside_the_range_cannot_reach_the_database(self):
        """The view checks it for the customer; the constraint is the guarantee."""
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Review.objects.create(user=self.user, order=self.order,
                                      product=self.product, rating=7)

    def test_a_refused_submission_keeps_what_was_typed(self):
        """A rejected photograph must not also cost the paragraph (§17 #118)."""
        response = self.client.post(self.url(), {
            'product': self.product.pk, 'rating': '4',
            'text': 'Bu matn saqlanib qolishi kerak',
            'photos': [photo() for _ in range(5)],      # over MAX_PHOTOS
        })
        self.assertEqual(response.status_code, 200, 'refusal should re-render, not redirect')
        self.assertContains(response, 'Bu matn saqlanib qolishi kerak')
        # The four-star radio, and only it, comes back checked. Matched with a
        # regex because the attributes are spread over three lines of template.
        import re
        checked = re.findall(r'id="rate-\d+-(\d)"[^>]*\bchecked\b',
                             response.content.decode())
        self.assertEqual(checked, ['4'], 'the chosen rating did not come back')

    def test_submitting_too_often_is_rate_limited(self):
        """The only write on the site that accepts uploads had no limit."""
        from django.core.cache import cache
        cache.clear()
        allowed, refused = 0, 0
        for n in range(14):
            other, variant = make_product('Chegara-%d' % n, stock=2)
            order = make_order(self.user, variant)
            self.client.post(reverse('review_create', kwargs={'order_id': order.pk}),
                             {'product': other.pk, 'rating': '5'})
            if Review.objects.filter(product=other).exists():
                allowed += 1
            else:
                refused += 1
        # Exactly the limit gets through and every attempt after it is turned
        # away - not "some were refused", which would also pass if the limit
        # were one, or a hundred.
        self.assertEqual((allowed, refused), (10, 4), 'the limit is not 10 per hour')
        cache.clear()


class PluralTests(TestCase):
    """A number inside a sentence is a plural, or two of the three languages read wrong.

    Both of Phase 12's counted strings run over small numbers where Russian
    changes the noun three times and English twice. The catalogue test next
    door only asks whether the forms are *filled*; this asks whether they are
    the right ones, which is the part a reader would notice.
    """

    def _forms(self, msgid, expected):
        from django.utils.translation import ngettext, override
        for lang, by_number in expected.items():
            for number, want in by_number.items():
                with self.subTest(lang=lang, n=number), override(lang):
                    rendered = ngettext(msgid, msgid, number) % {'n': number}
                    self.assertIn(want, rendered)

    def test_the_star_rows_agree_with_their_number(self):
        """The distribution runs 1 to 5, so "1 звёзд" was on the page five times."""
        self._forms('%(n)s yulduz', {
            'ru': {1: '1 звезда', 2: '2 звезды', 4: '4 звезды', 5: '5 звёзд'},
            'en': {1: '1 star', 2: '2 stars', 5: '5 stars'},
            'uz': {1: '1 yulduz', 5: '5 yulduz'},
        })

    def test_the_review_count_agrees_with_its_number(self):
        self._forms('%(n)s ta sharh', {
            'ru': {1: '1 отзыв', 3: '3 отзыва', 11: '11 отзывов'},
            'en': {1: '1 review', 2: '2 reviews'},
            'uz': {1: '1 ta sharh', 7: '7 ta sharh'},
        })


class SpellingTests(TestCase):
    """Uzbek Latin has two modifier letters and they are not interchangeable.

    U+02BB, the turned comma, builds the LETTERS oʻ and gʻ. The glottal stop in
    maʼlumot, sanʼat, maʼno is the tutuq belgisi, U+02BC. The catalogue had 225
    correct uses of the first and five of it standing in for the second, in
    four files from three phases — Phase 12 inherited the spelling by copying
    its neighbours, which is how a wrong character spreads.
    """
    TURNED = 'ʻ'

    def test_the_turned_comma_only_ever_follows_an_o_or_a_g(self):
        from pathlib import Path
        from django.conf import settings

        offenders = []
        for lang in ('uz', 'ru', 'en'):
            path = Path(settings.LOCALE_PATHS[0]) / lang / 'LC_MESSAGES' / 'django.po'
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                for i, char in enumerate(line):
                    if char == self.TURNED and (i == 0 or line[i - 1].lower() not in 'og'):
                        offenders.append('%s:%d %s' % (lang, number, line.strip()[:60]))
                        break
        self.assertEqual(offenders, [], 'U+02BB used where U+02BC belongs')

    def test_no_ascii_apostrophe_stands_in_for_either(self):
        """The straight quote is neither letter, and it breaks search matching."""
        from pathlib import Path
        from django.conf import settings

        path = Path(settings.LOCALE_PATHS[0]) / 'uz' / 'LC_MESSAGES' / 'django.po'
        bad = [line for line in path.read_text(encoding='utf-8').splitlines()
               if line.startswith('msgid "') and "'" in line]
        self.assertEqual(bad, [])


class NotificationTests(TestCase):
    """What the owner is told when a review lands in the queue."""

    def setUp(self):
        self.user = make_user('xabarchi', '+998901110009')
        self.product, self.variant = make_product('Xabar', stock=2)
        self.order = make_order(self.user, self.variant)

    def _sent(self, **kwargs):
        """Create a review and return the Telegram text that would have gone out.

        Inside ``captureOnCommitCallbacks`` because the notification is queued
        for commit, and a TestCase never commits — without this the assertions
        below would pass on an empty string.
        """
        from unittest.mock import patch
        sent = []
        with patch('core.telegram.send', side_effect=lambda text, **kw: sent.append(text)):
            with self.captureOnCommitCallbacks(execute=True):
                services.create_review(self.user, self.order, self.product, 5, **kwargs)
        return '\n'.join(sent)

    def test_the_owner_is_told_a_review_is_waiting(self):
        text = self._sent(text='Tekshirish uchun')
        self.assertIn('sharh', text.lower())

    def test_the_owner_is_told_when_a_review_carries_photographs(self):
        """The one review that most needs a human to look at it.

        `create_review` writes the review and then its photographs, both inside
        one transaction, so a notification composed when the review row is
        saved sees no images at all — and the line never appeared.
        """
        text = self._sent(text='Rasm bilan', photos=(photo(),))
        self.assertIn('Rasm biriktirilgan', text)


class RichResultTests(TestCase):
    """The Definition of Done says rich-result validation passes. This is it.

    Asserted against Google's documented requirements for a review snippet
    rather than against our own shape, because the point of the markup is that
    somebody else's parser accepts it. Checking that a key exists in a dict we
    just built proves nothing; checking the rules that dict has to satisfy is
    the same test Google's tool runs.
    """

    def setUp(self):
        self.user = make_user('boyitilgan', '+998901110010')
        self.product, self.variant = make_product('Boyitilgan', stock=4)
        self.order = make_order(self.user, self.variant)
        review = services.create_review(self.user, self.order, self.product, 4,
                                        text='Mato yaxshi, oʻlchami toʻgʻri keldi.')
        services.moderate(Review.objects.filter(pk=review.pk), Review.Status.APPROVED)

    def _payload(self):
        import json
        import re
        with translation.override('uz'):
            url = self.product.get_absolute_url()
        html = self.client.get(url).content.decode()
        found = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        self.assertIsNotNone(found, 'no structured data on a reviewed product')
        # Phase 9 put every node on the page into one `@graph` — the product,
        # its offer and the trail to it — because two script elements is two
        # things claiming to describe the page. The reviews live on the
        # Product node, which is what this file is about.
        graph = json.loads(found.group(1))['@graph']
        for node in graph:
            if node.get('@type') == 'Product':
                return node
        self.fail('no Product node in the structured data')

    def test_the_block_is_valid_json(self):
        """It is a stranger's text inside a script element; only a parser knows."""
        self._payload()                                     # raises if it is not

    def test_the_product_node_carries_what_google_requires(self):
        data = self._payload()
        self.assertEqual(data['@type'], 'Product')
        self.assertTrue(data.get('name'), 'Product.name is required')
        self.assertTrue(data.get('url', '').startswith('http'))

    def test_the_aggregate_rating_carries_what_google_requires(self):
        agg = self._payload()['aggregateRating']
        self.assertEqual(agg['@type'], 'AggregateRating')
        self.assertTrue(agg.get('ratingValue'))
        self.assertTrue(agg.get('reviewCount') or agg.get('ratingCount'))
        best, worst = float(agg['bestRating']), float(agg['worstRating'])
        self.assertLessEqual(worst, float(agg['ratingValue']))
        self.assertLessEqual(float(agg['ratingValue']), best)

    def test_every_review_node_carries_what_google_requires(self):
        data = self._payload()
        self.assertTrue(data['review'], 'aggregateRating without a review is refused')
        for node in data['review']:
            self.assertEqual(node['@type'], 'Review')
            # Author is required, and an empty name is the same as no author.
            self.assertTrue(node['author']['name'].strip())
            rating = node['reviewRating']
            self.assertTrue(rating.get('ratingValue'))
            self.assertLessEqual(float(rating['worstRating']),
                                 float(rating['ratingValue']))
            self.assertLessEqual(float(rating['ratingValue']),
                                 float(rating['bestRating']))

    def test_the_numbers_in_the_markup_are_the_numbers_on_the_page(self):
        """Markup that disagrees with the visible page is a manual action."""
        data = self._payload()
        self.product.refresh_from_db()
        self.assertEqual(data['aggregateRating']['ratingValue'],
                         str(self.product.rating_avg))
        self.assertEqual(data['aggregateRating']['reviewCount'],
                         self.product.review_count)

    def test_there_is_exactly_one_structured_data_block(self):
        """Two Product nodes on one page is one product described twice."""
        with translation.override('uz'):
            url = self.product.get_absolute_url()
        html = self.client.get(url).content.decode()
        self.assertEqual(html.count('application/ld+json'), 1)

    def test_a_product_with_no_approved_reviews_claims_no_rating(self):
        """schema.org requires aggregateRating to describe real reviews."""
        bare, _ = make_product('Sharhsiz', stock=1)
        with translation.override('uz'):
            url = bare.get_absolute_url()
        html = self.client.get(url).content.decode()
        self.assertNotIn('aggregateRating', html)


class ShopSortTests(TestCase):
    """Phase 12 item 8: the shop's Reyting sort, driven by real reviews.

    Phase 6 tested the sort by writing ``rating_avg`` into the column directly,
    which proved the ORDER BY and nothing else. Now that reviews are what fill
    that column, the honest test runs the whole way: write reviews, approve
    them, ask the shop.
    """

    def setUp(self):
        self.user = make_user('saralovchi', '+998901110011')
        self.middling, self.mid_variant = make_product('Oʻrtacha dizayn', stock=5)
        self.best, self.best_variant = make_product('Eng yaxshi dizayn', stock=5)
        self.unreviewed, _ = make_product('Baholanmagan dizayn', stock=5)

        for product, variant, stars in ((self.middling, self.mid_variant, 3),
                                        (self.best, self.best_variant, 5)):
            order = make_order(self.user, variant)
            review = services.create_review(self.user, order, product, stars)
            services.moderate(Review.objects.filter(pk=review.pk),
                              Review.Status.APPROVED)

    def _names(self):
        response = self.client.get(reverse('shop'), {'sort': 'rating'})
        return [p.name for p in response.context['products']]

    def test_the_best_reviewed_product_comes_first(self):
        names = self._names()
        self.assertEqual(names[0], 'Eng yaxshi dizayn')
        self.assertLess(names.index('Eng yaxshi dizayn'),
                        names.index('Oʻrtacha dizayn'))

    def test_an_unreviewed_product_sorts_below_a_reviewed_one(self):
        """Nobody's opinion is not the same as a bad opinion, but it is not better."""
        names = self._names()
        self.assertLess(names.index('Oʻrtacha dizayn'),
                        names.index('Baholanmagan dizayn'))

    def test_a_pending_review_does_not_move_the_shop_order(self):
        quiet, variant = make_product('Kutayotgan dizayn', stock=5)
        order = make_order(self.user, variant)
        services.create_review(self.user, order, quiet, 5)      # left pending
        self.assertEqual(self._names()[0], 'Eng yaxshi dizayn')


class AccountEntryPointTests(TestCase):
    """Both ways into the review form, since the SMS link is blocked (§17 #104)."""

    def setUp(self):
        self.user = make_user('kiruvchi', '+998901110012')
        self.product, self.variant = make_product('Kirish', stock=2)
        self.order = make_order(self.user, self.variant)
        self.client.force_login(self.user)

    def test_the_orders_list_offers_the_link_on_a_delivered_order(self):
        response = self.client.get(reverse('account_orders'))
        self.assertContains(
            response, reverse('review_create', kwargs={'order_id': self.order.pk}))

    def test_the_orders_list_offers_nothing_on_an_undelivered_one(self):
        order = make_order(self.user, self.variant, status='paid')
        response = self.client.get(reverse('account_orders'))
        self.assertNotContains(
            response, reverse('review_create', kwargs={'order_id': order.pk}))


class ReviewDateTests(TestCase):
    """A date under a review is read, not parsed, so it has to read correctly.

    Django's `F` gives the month in the nominative, which is right for a
    heading and wrong after a day number in Russian: "14 Сентябрь 2026" is the
    sort of thing that tells a reader the site was translated by a machine.
    `E` is the alternative form Django ships for exactly this, and it falls
    back to `F` where a language has no separate one.
    """

    def _formatted(self, lang, spec):
        from datetime import date
        from django.utils.dateformat import format as dateformat
        with translation.override(lang):
            return dateformat(date(2026, 9, 14), spec)

    def test_russian_uses_the_genitive_month(self):
        self.assertEqual(self._formatted('ru', 'j E Y'), '14 сентября 2026')
        # The form the template used to ask for, kept here so the difference is
        # on the record rather than in a commit message.
        self.assertEqual(self._formatted('ru', 'j F Y'), '14 Сентябрь 2026')

    def test_uzbek_and_english_are_unchanged_by_it(self):
        for lang in ('uz', 'en'):
            with self.subTest(lang=lang):
                self.assertEqual(self._formatted(lang, 'j E Y'),
                                 self._formatted(lang, 'j F Y'))

    def test_the_template_asks_for_the_alternative_form(self):
        from pathlib import Path
        from django.conf import settings
        source = (Path(settings.BASE_DIR) / 'templates' / 'product' / '_reviews.html'
                  ).read_text(encoding='utf-8')
        self.assertIn('date:"j E Y"', source)
        self.assertNotIn('date:"j F Y"', source)
