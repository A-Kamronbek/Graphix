"""A slide has two pictures: the laptop's (16:5) and the phone's (16:9).

The owner's call (§17 #302). Either may be missing, not both, and the one a
slide has is shown on both screens - which is exactly how every slide looked
before there were two, so nothing already uploaded changes.

When both are there the home page serves them through one <picture>: the
laptop file as a <source> from 860 px, the phone file as the <img>. A browser
downloads the picture for its own screen and never the other, and the <img>
keeps the fetch priority, the alt and the stored size it always had.
"""
import re

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from product.models import Slide, SlidePhone
from product.templatetags.image_tags import SIZES

from .test_backlog import TempMedia
from .test_phase6 import make_user
from .test_phase7 import make_staff
from .test_phase7b import photo

WIDE = (1600, 500)
PHONE = (1600, 900)


class SlideUploadTests(TempMedia, TestCase):
    """The Slaydlar screen: a new slide, and a picture added or replaced later."""

    def setUp(self):
        self.client.force_login(make_staff('ikkirasm', '+998901270101'))

    def add(self, **files):
        data = {'alt': 'Yozgi aksiya', 'link': '/dokon/'}
        data.update(files)
        return self.client.post(reverse('panel_slide_new'), data)

    def change(self, slide, which, upload):
        return self.client.post(reverse('panel_slide_picture', args=[slide.pk, which]),
                                {'picture': upload})

    def test_both_pictures(self):
        self.add(picture=photo(WIDE, name='w.jpg'), phone=photo(PHONE, name='p.jpg'))
        slide = Slide.objects.get()
        self.assertIsNotNone(slide.wide_photo)
        self.assertIsNotNone(slide.phone_photo)
        self.assertTrue(slide.phone.picture.name.startswith('slides/phone/'))

    def test_the_laptop_picture_alone(self):
        self.add(picture=photo(WIDE))
        slide = Slide.objects.get()
        self.assertIsNotNone(slide.wide_photo)
        self.assertIsNone(slide.phone_photo)

    def test_the_phone_picture_alone(self):
        self.add(phone=photo(PHONE))
        slide = Slide.objects.get()
        self.assertIsNone(slide.wide_photo)
        self.assertIsNotNone(slide.phone_photo)

    def test_neither_is_refused(self):
        self.add()
        self.assertFalse(Slide.objects.exists())

    def test_a_refused_phone_picture_leaves_no_half_slide(self):
        """Both files are cleaned before anything is written."""
        bad = SimpleUploadedFile('x.jpg', b'not an image', content_type='image/jpeg')
        self.add(picture=photo(WIDE), phone=bad)
        self.assertFalse(Slide.objects.exists())

    def test_the_missing_picture_can_be_added_later(self):
        """Without typing the description again in three languages."""
        self.add(picture=photo(WIDE))
        slide = Slide.objects.get()
        self.change(slide, 'phone', photo(PHONE))
        self.assertIsNotNone(Slide.objects.get().phone_photo)

    def test_either_picture_can_be_replaced(self):
        self.add(picture=photo(WIDE), phone=photo(PHONE))
        slide = Slide.objects.get()
        phone_before, wide_before = slide.phone.picture.name, slide.picture.name
        self.change(slide, 'phone', photo(PHONE, name='new-p.jpg'))
        self.change(slide, 'wide', photo(WIDE, name='new-w.jpg'))
        slide = Slide.objects.get()
        self.assertEqual(SlidePhone.objects.count(), 1)
        self.assertNotEqual(slide.phone.picture.name, phone_before)
        self.assertNotEqual(slide.picture.name, wide_before)

    def test_no_file_is_a_sentence_not_a_change(self):
        self.add(picture=photo(WIDE))
        slide = Slide.objects.get()
        response = self.client.post(reverse('panel_slide_picture', args=[slide.pk, 'phone']))
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(Slide.objects.get().phone_photo)

    def test_an_unknown_picture_is_not_found(self):
        self.add(picture=photo(WIDE))
        slide = Slide.objects.get()
        self.assertEqual(self.change(slide, 'tablet', photo(WIDE)).status_code, 404)

    def test_a_customer_cannot_change_one(self):
        self.add(picture=photo(WIDE))
        slide = Slide.objects.get()
        self.client.force_login(make_user('ikkixaridor', '+998901270102'))
        self.assertEqual(self.change(slide, 'phone', photo(PHONE)).status_code, 403)
        self.assertIsNone(Slide.objects.get().phone_photo)

    def test_deleting_the_slide_takes_its_phone_picture(self):
        self.add(picture=photo(WIDE), phone=photo(PHONE))
        slide = Slide.objects.get()
        self.client.post(reverse('panel_reference_delete',
                                 kwargs={'kind': 'slide', 'pk': slide.pk}))
        self.assertFalse(SlidePhone.objects.exists())

    def test_the_screen_offers_both_uploads(self):
        self.add(picture=photo(WIDE))
        slide = Slide.objects.get()
        html = self.client.get(reverse('panel_slides')).content.decode()
        self.assertIn(reverse('panel_slide_picture', args=[slide.pk, 'wide']), html)
        self.assertIn(reverse('panel_slide_picture', args=[slide.pk, 'phone']), html)
        self.assertIn('Rasm yoʻq', html)     # the phone picture, not given
        self.assertIn('name="phone"', html)  # the new-slide form's second file


class HomeSlidePictureTests(TempMedia, TestCase):
    """What the home page serves for each combination."""

    def slide(self, wide=True, phone=True, built=False):
        def make():
            slide = Slide.objects.create(
                picture=photo(WIDE, name='w.jpg') if wide else '', alt='Kartochka')
            if phone:
                SlidePhone.objects.create(slide=slide, picture=photo(PHONE, name='p.jpg'))
            return slide
        if not built:
            return make()
        # The renditions are built once the rows commit; run that here.
        with self.captureOnCommitCallbacks(execute=True):
            return make()

    def track(self):
        html = self.client.get(reverse('home')).content.decode()
        return html.split('data-slides-track', 1)[1].split('</ul>', 1)[0]

    def test_both_the_laptop_file_is_a_source_from_860(self):
        self.slide()
        track = self.track()
        source = re.search(r'<source media="\(min-width: 860px\)"[^>]*>', track)
        self.assertIsNotNone(source)
        self.assertIn('slides/w', source.group(0))
        img = re.search(r'<img[^>]*>', track).group(0)
        self.assertIn('slides/phone/p', img)
        self.assertIn('alt="Kartochka"', img)
        self.assertIn('fetchpriority="high"', img)

    def test_with_one_picture_there_is_no_source(self):
        for wide, phone, name in ((True, False, 'slides/w'), (False, True, 'slides/phone/p')):
            with self.subTest(wide=wide, phone=phone):
                Slide.objects.all().delete()
                self.slide(wide=wide, phone=phone)
                track = self.track()
                self.assertNotIn('<source', track)
                self.assertIn(name, re.search(r'<img[^>]*>', track).group(0))

    def test_a_slide_with_neither_is_not_a_card(self):
        Slide.objects.create(picture='', alt='Boʻsh karta')
        self.assertNotIn('Boʻsh karta', self.client.get(reverse('home')).content.decode())

    def test_the_sizes_are_the_width_each_picture_is_drawn_at(self):
        """Built renditions, so the tags carry srcset and sizes."""
        self.slide(built=True)
        track = self.track()
        source = re.search(r'<source[^>]*>', track).group(0)
        img = re.search(r'<img[^>]*>', track).group(0)
        self.assertIn('sizes="%s"' % SIZES['slide-card'], source)
        self.assertIn('sizes="%s"' % SIZES['slide-card'], img)
        self.assertIn('srcset=', source)

    def test_a_laptop_picture_alone_keeps_the_phone_crop_sizes(self):
        """The 16:5 file on a phone is drawn 1.8 card-widths wide (§17 #300)."""
        self.slide(phone=False, built=True)
        img = re.search(r'<img[^>]*>', self.track()).group(0)
        self.assertIn('sizes="%s"' % SIZES['slide'], img)

    def test_the_picture_fills_the_card(self):
        """An inline <picture> would leave the <img>'s 100% height nothing to fill."""
        from pathlib import Path
        from django.conf import settings
        css = (Path(settings.BASE_DIR) / 'static' / 'css' / 'pages.css').read_text(encoding='utf-8')
        self.assertIn('.slides__item picture { display: block; width: 100%; height: 100%; }', css)


class SlideAdminTests(TempMedia, TestCase):
    """The admin shows the phone picture under its slide."""

    def test_the_change_page_has_the_phone_inline(self):
        staff = make_staff('ikkiadmin', '+998901270103')
        staff.is_superuser = True
        staff.save(update_fields=['is_superuser'])
        self.client.force_login(staff)
        slide = Slide.objects.create(picture=photo(WIDE, name='w.jpg'), alt='Admin karta')
        html = self.client.get(reverse('admin:product_slide_change', args=[slide.pk])).content.decode()
        self.assertIn('name="phone-TOTAL_FORMS"', html)
