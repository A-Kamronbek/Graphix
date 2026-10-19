"""Phase 22: every order goes to Uzpost through Uzpost's own API.

An office order travels by Bir Qadam to the post office of the district the
customer chose, from a list or from a pin on a map; a home order by Kuryerlik
joʻnatmasi. Staff make the shipment and print its label from the panel, the
customer follows the parcel from the order page, and the shop's status follows
Uzpost's (§9 Phase 22, §17 #376 to #384).

No test calls Uzpost. The client is tested against Uzpost's answers as they
were recorded on 2026-10-18 (``core/testdata/uzpost.json``), and everything
above it against the client's own answers.
"""
import csv
import json
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest import mock

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from cart.models import Cart, CartItem
from core import uzpost
from panel.models import OrderStatusChange
from payment import shipments
from payment.management.commands import sync_uzpost_regions as sync
from payment.models import (DeliveryOption, District, Order, Region, Shipment,
                            ShipmentStatus)

from .test_phase4 import make_product
from .test_phase6 import make_regions, make_user
from .test_phase7 import make_staff
from .test_phase16 import CheckoutCase

ANSWERS = json.loads((Path(__file__).parent / 'testdata' / 'uzpost.json')
                     .read_text(encoding='utf-8'))

#: The owner's credentials as a test has them: present, and not real.
SET_UP = override_settings(UZPOST_LOGIN='shop', UZPOST_PASSWORD='not-the-password')

OK = uzpost.Answer(True, None, '', False)


class Reply:
    """An HTTP answer as ``requests`` would give it."""

    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.text = json.dumps(body) if body is not None else ''

    def json(self):
        if self._body is None:
            raise ValueError('no JSON')
        return self._body


def facts(**over):
    """What ``uzpost.shipment_facts`` makes of the recorded create answer."""
    value = uzpost.shipment_facts(ANSWERS['create']['data'])
    value.update(over)
    return value


# ====================================================================== client

@SET_UP
class ClientTests(TestCase):
    """``core.uzpost``: the token, the answers it reads, and never a raise."""

    def setUp(self):
        # Only the token: the cache is Redis and shared with the other workers
        # of a parallel run, whose rate-limit counters a clear() would wipe.
        cache.delete(uzpost._TOKEN_KEY)
        self.addCleanup(cache.delete, uzpost._TOKEN_KEY)
        self.login = mock.patch('core.uzpost.requests.post',
                                return_value=Reply(200, ANSWERS['authenticate']))
        self.post = self.login.start()
        self.addCleanup(self.login.stop)

    def calls(self, *replies):
        """Make the next calls to Uzpost answer ``replies`` in turn."""
        patcher = mock.patch('core.uzpost.requests.request', side_effect=list(replies))
        self.addCleanup(patcher.stop)
        return patcher.start()

    @override_settings(UZPOST_LOGIN='', UZPOST_PASSWORD='')
    def test_blank_credentials_call_nothing(self):
        request = self.calls()
        answer = uzpost.create_order({})
        self.assertFalse(answer.ok)
        self.assertEqual(answer.error, 'not configured')
        request.assert_not_called()
        self.post.assert_not_called()
        self.assertFalse(uzpost.configured())

    def test_the_token_is_fetched_once_and_sent_as_bearer(self):
        request = self.calls(Reply(200, ANSWERS['tariff']), Reply(200, ANSWERS['tariff']))
        uzpost.transportation_type(1076362452, 273)
        uzpost.transportation_type(1076362452, 273)
        self.assertEqual(self.post.call_count, 1)
        self.assertEqual(self.post.call_args.kwargs['json']['username'], 'shop')
        headers = request.call_args.kwargs['headers']
        self.assertEqual(headers['Authorization'], 'Bearer recorded-token')

    def test_a_401_fetches_a_new_token_and_asks_again(self):
        request = self.calls(Reply(401, {}), Reply(200, ANSWERS['tariff']))
        answer = uzpost.transportation_type(1076362452, 273)
        self.assertTrue(answer.ok)
        self.assertEqual(self.post.call_count, 2)
        self.assertEqual(request.call_count, 2)

    def test_a_cache_that_cannot_be_read_costs_a_login_not_the_call(self):
        self.calls(Reply(200, ANSWERS['tariff']))
        with mock.patch('core.uzpost.cache.get', side_effect=ConnectionError('down')), \
                mock.patch('core.uzpost.cache.set', side_effect=ConnectionError('down')):
            self.assertTrue(uzpost.transportation_type(1076362452, 273).ok)

    def test_the_price_call_gives_the_route_its_transportation_type(self):
        request = self.calls(Reply(200, ANSWERS['tariff']))
        answer = uzpost.transportation_type(1076362452, 273)
        self.assertEqual(answer.data, 'terrestrial')
        params = request.call_args.kwargs['params']
        self.assertEqual(params['fromJurisdictionId'], settings.UZPOST_SENDER_JURISDICTION)
        self.assertEqual(params['toJurisdictionId'], 273)
        self.assertEqual(params['service_type'], 1076362452)

    def test_no_price_for_a_route_is_a_failure_in_words(self):
        empty = {'status': 'success', 'data': {'total': 0, 'list': []}}
        self.calls(Reply(200, empty))
        answer = uzpost.transportation_type(1076362452, 273)
        self.assertFalse(answer.ok)
        self.assertEqual(answer.error, 'no price for this route')

    def test_the_create_answer_is_read_for_what_the_shop_keeps(self):
        self.calls(Reply(201, ANSWERS['create']))
        answer = uzpost.create_order({'any': 'thing'})
        self.assertTrue(answer.ok)
        self.assertEqual(answer.data['id'], 5696260512)
        self.assertEqual(answer.data['number'], 'MM216886699UZ')
        self.assertEqual(answer.data['status'], 'unassigned')
        self.assertEqual(answer.data['office_index'], '150700')
        self.assertIn('Коканд', answer.data['office_name'])
        self.assertEqual(answer.data['status_at'].year, 2026)

    def test_a_refusal_carries_uzposts_own_words(self):
        self.calls(Reply(400, ANSWERS['refused']))
        answer = uzpost.create_order({})
        self.assertFalse(answer.ok)
        self.assertFalse(answer.unknown)
        self.assertEqual(answer.error, 'Invalid argument type')

    def test_a_create_whose_answer_is_lost_is_unknown_not_failed(self):
        """It may have reached Uzpost: staff are told to look, not to press again."""
        self.calls(requests.Timeout('slow'))
        answer = uzpost.create_order({})
        self.assertFalse(answer.ok)
        self.assertTrue(answer.unknown)

    def test_a_gateway_error_on_a_write_is_unknown_too(self):
        """A 504 can come from a gateway after Uzpost did the work."""
        self.calls(Reply(504, None))
        answer = uzpost.create_order({})
        self.assertFalse(answer.ok)
        self.assertTrue(answer.unknown)

    def test_an_answer_without_success_is_not_taken_for_one(self):
        """An HTML maintenance page with a 200 is not a cancelled shipment."""
        page = Reply(200, None)
        page.text = '<html>Texnik ishlar</html>'
        self.calls(page)
        answer = uzpost.cancel('MM216886699UZ')
        self.assertFalse(answer.ok)
        self.assertTrue(answer.unknown)
        self.calls(Reply(200, {'data': {'list': []}}))
        answer = uzpost.transportation_type(1076362452, 273)
        self.assertFalse(answer.ok)
        self.assertFalse(answer.unknown)

    def test_a_read_that_times_out_is_simply_failed(self):
        self.calls(requests.Timeout('slow'))
        answer = uzpost.details(5696260512)
        self.assertFalse(answer.ok)
        self.assertFalse(answer.unknown)

    def test_nothing_unexpected_escapes(self):
        self.calls(Reply(200, {'status': 'success', 'data': 'not a shipment'}))
        self.assertFalse(uzpost.details(5696260512).ok)
        self.calls(Reply(500, None))
        self.assertFalse(uzpost.cancel('MM216886699UZ').ok)

    def test_the_label_is_a_link_on_uzposts_own_domain(self):
        self.calls(Reply(200, ANSWERS['label']))
        answer = uzpost.label(5696260512)
        self.assertTrue(answer.ok)
        self.assertTrue(answer.data.startswith('https://prodapi.pochta.uz/'))

    def test_a_label_link_anywhere_else_is_refused(self):
        for link in ('http://prodapi.pochta.uz/x', 'https://pochta.uz.example.com/x',
                     'javascript:alert(1)'):
            with self.subTest(link=link):
                self.calls(Reply(200, {'status': 'success', 'data': link}))
                self.assertFalse(uzpost.label(5696260512).ok)

    def test_cancel_asks_by_the_barcode(self):
        request = self.calls(Reply(200, ANSWERS['cancel']))
        self.assertTrue(uzpost.cancel('MM216886699UZ').ok)
        self.assertEqual(request.call_args.args[0], 'PUT')
        self.assertEqual(request.call_args.kwargs['params'], {'barcode': 'MM216886699UZ'})

    def test_text_for_uzpost_has_plain_apostrophes(self):
        """Uzpost kept Qoʻqon as Qo?qon (§17 #384)."""
        self.assertEqual(uzpost.plain('Qoʻqon  shahri,\nGʻallaorol'), "Qo'qon shahri, G'allaorol")
        self.assertEqual(uzpost.plain('maʼlumot — «uy»'), "ma'lumot - \"uy\"")


# ====================================================================== regions

class NameTests(TestCase):
    """Uzpost's names, with the typography put right and nothing else."""

    def test_the_typography_is_put_right(self):
        cases = {
            'Qоrashina': 'Qorashina',
            'Mug`lon': 'Mugʻlon',
            "Qo'ng'irot": 'Qoʻngʻirot',
            'Ellikqal’a': 'Ellikqalʼa',
            'Amudaryo Tumani': 'Amudaryo tumani',
            'Buxoro Shahar ': 'Buxoro shahar',
            '  Navoiy   Shahri': 'Navoiy shahri',
        }
        for raw, clean in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(sync.clean_name(raw), clean)

    def test_matches_are_proposed_by_name_within_the_region(self):
        official = [
            {'code': '1726294', 'region_code': '1726', 'name': 'Chilonzor tumani', 'kind': 'district'},
            {'code': '1703232', 'region_code': '1703', 'name': 'Paxtaobod tumani', 'kind': 'district'},
            {'code': '1703401', 'region_code': '1703', 'name': 'Andijon shahri', 'kind': 'city'},
            {'code': '1703203', 'region_code': '1703', 'name': 'Andijon tumani', 'kind': 'district'},
        ]
        districts = [{'id': d['id'], 'parent_id': d['parent_id'], 'name': d['name']}
                     for d in ANSWERS['level3']['data']]
        found = sync.propose_matches(districts, official,
                                     {258: '1703', 270: '1726', 271: '1733'},
                                     {258: 'andijon', 270: 'toshkent', 271: 'xorazm'})
        self.assertEqual(found[273], ('1726294', False))       # Chilanzar, a letter apart
        self.assertEqual(found[313], ('1703232', True))        # its region's name dropped
        self.assertEqual(found[300], ('1703401', True))        # "shahri" picks the city
        self.assertNotIn(279, found)                           # no Uchtepa in this list


class SyncRegionsTests(TestCase):
    """``sync_uzpost_regions`` loads Uzpost's lists over the official ones."""

    def setUp(self):
        call_command('seed_regions', stdout=StringIO())

    def load(self, *args):
        call_command('sync_uzpost_regions', *args, stdout=StringIO(), stderr=StringIO())

    def test_the_lists_become_uzposts(self):
        self.load()
        self.assertEqual(Region.objects.filter(is_active=True).count(), 14)
        self.assertEqual(District.objects.filter(is_active=True).count(), 198)
        self.assertFalse(District.objects.filter(is_active=True, uzpost_id__isnull=True).exists())
        self.assertFalse(District.objects.filter(is_active=True, latitude__isnull=True).exists())
        # The escapes are switched off and nothing is deleted.
        self.assertFalse(Region.objects.get(code='0000').is_active)
        self.assertFalse(District.objects.filter(kind='other', is_active=True).exists())
        self.assertEqual(District.objects.filter(code__in=['1726900', '1706240']).count(), 2)

    def test_a_matched_row_takes_the_files_uzbek_name_and_keeps_its_translations(self):
        self.load()
        chilonzor = District.objects.get(code='1726294')
        self.assertEqual(chilonzor.uzpost_id, 273)
        self.assertEqual(chilonzor.name, 'Chilonzor tumani')
        self.assertEqual(chilonzor.name_ru, 'Чиланзарский район')

    def test_a_region_keeps_its_own_name(self):
        self.load()
        tashkent = Region.objects.get(code='1726')
        self.assertEqual(tashkent.uzpost_id, 270)
        self.assertEqual(tashkent.name, 'Toshkent shahri')

    def test_a_district_with_no_official_row_is_created_without_translations(self):
        self.load()
        gagarin = District.objects.get(uzpost_id=361)
        self.assertEqual(gagarin.code, 'U361')
        self.assertEqual(gagarin.name, 'Gagarin')
        self.assertEqual((gagarin.name_ru, gagarin.name_en), ('', ''))
        self.assertEqual(gagarin.region.code, '1708')

    def test_a_centre_corrected_by_hand_is_the_one_loaded(self):
        self.load()
        romitan = District.objects.get(uzpost_id=326)
        self.assertEqual(romitan.latitude, Decimal('39.933333'))
        self.assertEqual(romitan.longitude, Decimal('64.383333'))

    def test_loading_twice_changes_nothing(self):
        self.load()
        before = list(District.objects.order_by('pk').values_list(
            'pk', 'name', 'is_active', 'uzpost_id', 'latitude'))
        self.load()
        after = list(District.objects.order_by('pk').values_list(
            'pk', 'name', 'is_active', 'uzpost_id', 'latitude'))
        self.assertEqual(before, after)

    def test_seed_regions_will_not_undo_it(self):
        self.load()
        with self.assertRaises(CommandError):
            call_command('seed_regions', stdout=StringIO())
        self.assertEqual(District.objects.get(code='1726294').name, 'Chilonzor tumani')

    def test_a_bad_file_writes_nothing(self):
        source = Path(settings.BASE_DIR) / 'data' / 'uzpost-regions.csv'
        text = source.read_text(encoding='utf-8').replace(',district,41.267426,', ',town,41.267426,')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.csv'
            path.write_text(text, encoding='utf-8')
            with self.assertRaises(CommandError):
                self.load('--file', str(path))
        self.assertFalse(Region.objects.filter(uzpost_id__isnull=False).exists())
        self.assertTrue(District.objects.get(code='1726900').is_active)

    def edited(self, *pairs):
        """The real file with ``pairs`` replaced, in a temporary folder. Returns its path."""
        text = (Path(settings.BASE_DIR) / 'data' / 'uzpost-regions.csv').read_text(encoding='utf-8')
        for old, new in pairs:
            self.assertIn(old, text)
            text = text.replace(old, new)
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = Path(folder) / 'uzpost-regions.csv'
        path.write_text(text, encoding='utf-8')
        return str(path)

    def test_a_match_corrected_in_the_file_takes_effect(self):
        self.load()
        # Gagarin is Mirzachoʻl's centre: a person writes the official row in.
        self.load('--file', self.edited((',Gagarin,district,40.698624,68.026584,,',
                                         ',Gagarin,district,40.698624,68.026584,1708223,')))
        mirzachol = District.objects.get(code='1708223')
        self.assertEqual((mirzachol.uzpost_id, mirzachol.name, mirzachol.is_active),
                         (361, 'Gagarin', True))
        left = District.objects.get(code='U361')
        self.assertEqual((left.is_active, left.uzpost_id, left.name),
                         (False, None, 'Gagarin (U361)'))

    def test_a_row_made_before_is_taken_again(self):
        self.load()
        District.objects.filter(code='U361').update(uzpost_id=None, is_active=False)
        self.load()
        self.assertEqual(District.objects.filter(code='U361', uzpost_id=361, is_active=True).count(), 1)

    def test_an_official_row_from_another_region_is_refused(self):
        with self.assertRaises(CommandError):
            self.load('--file', self.edited(
                (',Chilonzor tumani,district,41.267426,69.191946,1726294,',
                 ',Chilonzor tumani,district,41.267426,69.191946,1718401,')))
        self.assertFalse(Region.objects.filter(uzpost_id__isnull=False).exists())

    def test_a_point_that_is_not_a_number_is_refused_in_words(self):
        with self.assertRaises(CommandError):
            self.load('--file', self.edited((',Chilonzor tumani,district,41.267426,',
                                             ',Chilonzor tumani,district,nan,')))

    def test_the_file_itself(self):
        """Every row is usable, and every name is written as §4.3 asks."""
        with (Path(settings.BASE_DIR) / 'data' / 'uzpost-regions.csv').open(encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
        districts = [r for r in rows if r['level'] == 'district']
        self.assertEqual(len([r for r in rows if r['level'] == 'region']), 14)
        self.assertEqual(len(districts), 198)
        for row in districts:
            with self.subTest(name=row['name']):
                self.assertTrue(row['lat'] and row['lng'])
                self.assertNotIn("'", row['name'])
                for i, ch in enumerate(row['name']):
                    if ch == 'ʻ':
                        self.assertIn(row['name'][i - 1].lower(), 'og')
        notes = [r for r in districts if r['note']]
        self.assertEqual({r['uzpost_id'] for r in notes}, {'326', '363'})

    def test_the_files_names_are_uzbek(self):
        """A district with an official row carries its official name; none keeps
        a Russian-style spelling of Uzpost's (§19 Q63)."""
        data = Path(settings.BASE_DIR) / 'data'
        with (data / 'regions.csv').open(encoding='utf-8-sig') as fh:
            official = {r['code']: r['name'] for r in csv.DictReader(fh)}
        with (data / 'uzpost-regions.csv').open(encoding='utf-8') as fh:
            districts = [r for r in csv.DictReader(fh) if r['level'] == 'district']
        for row in districts:
            if row['soato'] and row['soato'] != '1735250':      # Ellikqalʼa keeps its tutuq
                with self.subTest(name=row['name']):
                    self.assertEqual(row['name'], sync.clean_name(official[row['soato']]))
        names = {row['name'] for row in districts}
        for russian in ('Chilanzar', 'Mirabad', 'Yunusabad', 'Yashnabad', 'Yakkasaray',
                        'Shayhontohur', 'Mirzo Ulugbek', 'Chimbay', 'Chinaz', 'Zarafshan',
                        'Gazgon', 'Honobod', 'Jalolquduq', 'Toyloq', 'Yangiyul shahri',
                        'Ziaddin', 'Paxtabod'):
            with self.subTest(russian=russian):
                self.assertFalse(any(name.startswith(russian) for name in names))

    @override_settings(UZPOST_LOGIN='shop', UZPOST_PASSWORD='not-the-password')
    def test_a_fetch_keeps_what_a_person_wrote(self):
        def answer(level, parent_id=None):
            return uzpost.Answer(True, ANSWERS[f'level{level}']['data'], '', False)

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'uzpost-regions.csv'
            sync.write_rows(path, [
                {'level': 'region', 'uzpost_id': 270, 'parent_id': '', 'name': 'Toshkent shahar',
                 'kind': '', 'lat': '', 'lng': '', 'soato': '1726', 'note': ''},
                {'level': 'district', 'uzpost_id': 279, 'parent_id': 270, 'name': 'Uchtepa',
                 'kind': 'district', 'lat': '41.300000', 'lng': '69.170000', 'soato': '1726262',
                 'note': 'centre corrected by hand'},
                {'level': 'district', 'uzpost_id': 273, 'parent_id': 270,
                 'name': 'Chilonzor tumani', 'kind': 'district', 'lat': '41.267426',
                 'lng': '69.191946', 'soato': '1726294', 'note': ''},
            ])
            with mock.patch('core.uzpost.jurisdictions', side_effect=answer):
                call_command('sync_uzpost_regions', '--fetch', '--file', str(path),
                             stdout=StringIO())
            with path.open(encoding='utf-8') as fh:
                rows = {(r['level'], r['uzpost_id']): r for r in csv.DictReader(fh)}
        uchtepa = rows[('district', '279')]
        self.assertEqual((uchtepa['lat'], uchtepa['lng']), ('41.300000', '69.170000'))
        self.assertEqual(uchtepa['soato'], '1726262')
        self.assertEqual(rows[('district', '273')]['soato'], '1726294')
        # The name the file had stays, though Uzpost writes "Chilanzar" (§19 Q63);
        # a new match takes the official name, and one with none Uzpost's, cleaned.
        self.assertEqual(rows[('district', '273')]['name'], 'Chilonzor tumani')
        self.assertEqual(rows[('district', '313')]['name'], 'Paxtaobod tumani')
        self.assertEqual(rows[('district', '900')]['name'], 'Qorashina')
        self.assertEqual(rows[('district', '901')]['name'], 'Mugʻlon')
        self.assertNotIn(('district', '999'), rows)

    @override_settings(UZPOST_LOGIN='', UZPOST_PASSWORD='')
    def test_a_fetch_needs_the_login(self):
        with self.assertRaises(CommandError):
            call_command('sync_uzpost_regions', '--fetch', '--file', '/tmp/never.csv',
                         stdout=StringIO())


# ====================================================================== checkout

class OfficeCheckoutTests(CheckoutCase):
    """An office order is a district and nothing typed (§17 #377)."""

    def test_an_office_order_is_placed_with_a_district_alone(self):
        response = self.post(postal_index=None)
        order = Order.objects.get(cart=self.cart)
        self.assertRedirects(response, reverse('payment', args=[order.pk]),
                             fetch_redirect_response=False)
        self.assertEqual(order.postal_index, '')
        self.assertEqual(order.district, self.geo['chilonzor'])
        self.assertEqual(order.location_snapshot, 'Toshkent shahri · Chilonzor tumani')

    def test_a_district_uzpost_does_not_know_is_neither_offered_nor_taken(self):
        page = self.client.get(reverse('checkout')).content.decode()
        self.assertNotIn('>Boshqa<', page)
        self.post(region=self.geo['other'].pk, district=self.geo['other_district'].pk)
        self.assertFalse(Order.objects.filter(cart=self.cart).exists())

    def test_the_page_asks_for_no_index_and_sends_nobody_away(self):
        page = self.client.get(reverse('checkout')).content.decode()
        self.assertNotIn('name="postal_index"', page)
        self.assertNotIn('uz.post/uz/map', page)
        self.assertNotIn('data-leave-checkout', page)
        self.assertIn('Bir Qadam', page)

    def test_every_district_carries_its_centre_for_the_map(self):
        response = self.client.get(reverse('checkout'))
        districts = json.loads(response.context['districts_json'])
        row = districts[str(self.geo['tashkent'].pk)]['district'][0]
        self.assertEqual((row['lat'], row['lng']), (41.267426, 69.191946))

    @override_settings(GOOGLE_MAPS_API_KEY='')
    def test_without_a_key_there_is_no_office_map(self):
        page = self.client.get(reverse('checkout')).content.decode()
        self.assertNotIn('data-office-map', page)

    @override_settings(GOOGLE_MAPS_API_KEY='test-key')
    def test_with_a_key_the_office_map_waits_behind_its_button(self):
        page = self.client.get(reverse('checkout')).content.decode()
        self.assertIn('data-office-map-open', page)
        self.assertIn('data-office-map-near', page)
        # Nothing from Google until the button is pressed (§18 #34).
        self.assertNotIn('<script src="https://maps.googleapis.com', page)

    def test_a_home_order_is_placed_as_before(self):
        self.post(delivery_option='uzpost_door', postal_index=None,
                  address='Bunyodkor 12', address_source='manual')
        order = Order.objects.get(cart=self.cart)
        self.assertEqual(order.address, 'Bunyodkor 12')
        self.assertEqual(order.postal_index, '')


# ====================================================================== shipments

def placed(user, variant, geo, *, option='uzpost_office', status=Order.Status.PAID,
           quantity=1, **extra):
    """An order as the checkout leaves it, then paid for."""
    cart = Cart.objects.create(user=user, status=False)
    CartItem.objects.create(cart=cart, variant=variant, quantity=quantity,
                            price_stat=variant.price)
    delivery = DeliveryOption.objects.get(code=option)
    fields = dict(user=user, cart=cart, phone='+998 90 122 00 03',
                  recipient_name='Dilnoza Oʻtkirova', status=status,
                  delivery_option=delivery, delivery_price=delivery.price,
                  total_price=variant.price * quantity + delivery.price,
                  region=geo['tashkent'], district=geo['chilonzor'],
                  address='' if delivery.requires_branch else 'Bunyodkor koʻchasi 12')
    fields.update(extra)
    return Order.objects.create(**fields)


class ShipmentCase(TestCase):
    """A paid office order, staff in the panel, and Uzpost answering as it did."""

    def setUp(self):
        self.geo = make_regions()
        self.customer = make_user('mijoz', '+998901220003')
        self.staff = make_staff()
        self.product, self.variant = make_product('Joʻnatma', stock=10)
        self.order = placed(self.customer, self.variant, self.geo, quantity=2)
        self.route_call = mock.patch(
            'payment.shipments.uzpost.transportation_type',
            return_value=uzpost.Answer(True, 'terrestrial', '', False)).start()
        self.create_call = mock.patch('payment.shipments.uzpost.create_order',
                                      side_effect=self.made).start()
        self.addCleanup(mock.patch.stopall)
        self.made_count = 0

    def made(self, payload):
        """Uzpost's answer to a create: the recorded one first, then others like it."""
        self.made_count += 1
        if self.made_count == 1:
            return uzpost.Answer(True, facts(), '', False)
        number = 5696260512 + self.made_count
        return uzpost.Answer(True, facts(id=number, number=f'MM{number}UZ'), '', False)

    def ship(self, order=None):
        return shipments.create(order or self.order, by=self.staff)


@SET_UP
class PayloadTests(ShipmentCase):
    """What Uzpost is asked to carry (§9 Phase 22 items 3, 5, 8)."""

    def test_an_office_order_is_addressed_by_its_district(self):
        body = shipments.payload(self.order, 'terrestrial')
        self.assertEqual(body['service_type'], {'code': 'ONE_STEP_WITHOUT_BAG'})
        self.assertEqual(body['payment_type'], 'credit_balance')
        self.assertEqual(body['transportation_type'], 'terrestrial')
        recipient = body['recipient_data']
        self.assertEqual(recipient['jurisdiction'], {'id': 273})
        self.assertEqual(recipient['address'], 'Chilonzor tumani')
        self.assertEqual(recipient['phone'], '+998901220003')
        self.assertEqual(recipient['customer'], {'name': "Dilnoza O'tkirova"})
        self.assertEqual(body['dimensions'], {'weight': 0.34})

    def test_the_sender_is_the_shop_from_its_own_district(self):
        sender = shipments.payload(self.order, 'air')['sender_data']
        self.assertEqual(sender['jurisdiction'], {'id': 339})
        self.assertEqual(sender['customer'], {'name': 'GRAPHIX'})
        self.assertEqual(sender['phone'], '+998507888436')
        self.assertTrue(sender['address'].startswith("Farg'ona viloyati, Qo'qon shahri"))

    def test_a_typed_home_order_is_addressed_by_its_district_and_street(self):
        order = placed(self.customer, self.variant, self.geo, option='uzpost_door')
        body = shipments.payload(order, 'terrestrial')
        self.assertEqual(body['service_type'], {'code': 'COURIER_SERVICE_WITHOUT_BAG'})
        self.assertEqual(body['recipient_data']['jurisdiction'], {'id': 273})
        self.assertEqual(body['recipient_data']['address'], "Bunyodkor ko'chasi 12")

    def test_a_home_order_from_the_map_is_addressed_by_its_pin(self):
        order = placed(self.customer, self.variant, self.geo, option='uzpost_door',
                       address_source='map', latitude=Decimal('41.311081'),
                       longitude=Decimal('69.240562'))
        recipient = shipments.payload(order, 'terrestrial')['recipient_data']
        self.assertEqual((recipient['lat'], recipient['lon']), (41.311081, 69.240562))
        self.assertNotIn('jurisdiction', recipient)

    def test_nothing_sent_carries_the_uzbek_apostrophe(self):
        text = json.dumps(shipments.payload(self.order, 'terrestrial'), ensure_ascii=False)
        self.assertNotIn('ʻ', text)
        self.assertNotIn('ʼ', text)


@SET_UP
class CreateTests(ShipmentCase):
    """The button: staff accepting a paid order (§17 #379)."""

    def test_a_paid_order_gets_its_shipment_and_moves_to_processing(self):
        shipment = self.ship()
        self.assertEqual(shipment.number, 'MM216886699UZ')
        self.assertEqual(shipment.uzpost_id, 5696260512)
        self.assertEqual(shipment.weight, Decimal('0.340'))
        self.assertEqual(shipment.office_index, '150700')
        self.assertEqual(shipment.transportation, 'terrestrial')
        self.assertEqual(shipment.created_by, self.staff)
        self.assertEqual(list(shipment.history.values_list('status', flat=True)), ['unassigned'])
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PROCESSING)
        change = self.order.status_changes.get()
        self.assertEqual(change.changed_by, self.staff)
        self.route_call.assert_called_once_with(1076362452, 273)

    def test_a_processing_order_keeps_its_status(self):
        self.order.status = Order.Status.PROCESSING
        self.order.save(update_fields=['status'])
        self.ship()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PROCESSING)
        self.assertFalse(self.order.status_changes.exists())

    def test_one_live_shipment_an_order(self):
        self.ship()
        with self.assertRaises(shipments.ShipmentError):
            self.ship()
        self.assertEqual(self.create_call.call_count, 1)

    def test_an_order_awaiting_payment_gets_none(self):
        self.order.status = Order.Status.PAYING
        self.order.save(update_fields=['status'])
        with self.assertRaises(shipments.ShipmentError):
            self.ship()
        self.create_call.assert_not_called()

    def test_a_refusal_leaves_nothing_made(self):
        self.create_call.side_effect = None
        self.create_call.return_value = uzpost.Answer(False, None, 'Invalid argument type', False)
        with self.assertRaises(shipments.ShipmentError) as raised:
            self.ship()
        self.assertIn('Invalid argument type', raised.exception.message)
        self.assertFalse(Shipment.objects.exists())
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_a_lost_answer_leaves_the_request_and_says_to_look(self):
        self.create_call.side_effect = None
        self.create_call.return_value = uzpost.Answer(False, None, 'timeout', True)
        with self.assertRaises(shipments.ShipmentError) as raised:
            self.ship()
        self.assertIn('my.pochta.uz', raised.exception.message)
        request = Shipment.objects.get()
        self.assertTrue(request.is_request)
        self.assertEqual(request.status, shipments.REQUESTED)
        # A second press makes nothing until staff withdraw the request.
        self.assertFalse(shipments.can_create(self.order))
        with self.assertRaises(shipments.ShipmentError):
            self.ship()
        self.assertEqual(self.create_call.call_count, 1)
        self.assertTrue(shipments.withdraw_request(self.order))
        self.create_call.side_effect = self.made
        self.assertEqual(self.ship().number, 'MM216886699UZ')

    def test_the_request_is_written_before_uzpost_is_asked(self):
        """A worker killed while Uzpost answers leaves the mark behind."""
        def killed(payload):
            self.assertTrue(Shipment.objects.get().is_request)
            raise RuntimeError('worker killed')
        self.create_call.side_effect = killed
        with self.assertRaises(RuntimeError):
            self.ship()
        self.assertTrue(Shipment.objects.get().is_request)
        with self.assertRaises(shipments.ShipmentError):
            self.ship()

    def test_a_slow_route_call_does_not_ask_for_the_shipment(self):
        """Past the deadline the create call could outlast the request."""
        clock = iter([0.0, shipments.DEADLINE + 1.0])
        with mock.patch('payment.shipments.time.monotonic', side_effect=lambda: next(clock)):
            with self.assertRaises(shipments.ShipmentError):
                self.ship()
        self.create_call.assert_not_called()
        self.assertFalse(Shipment.objects.exists())

    def test_an_office_order_with_a_typed_index_is_made_by_hand(self):
        """Placed before Phase 22: Uzpost would not send it to the branch chosen."""
        Order.objects.filter(pk=self.order.pk).update(postal_index='100011')
        self.order.refresh_from_db()
        self.assertFalse(shipments.can_create(self.order))
        with self.assertRaises(shipments.ShipmentError):
            self.ship()
        self.route_call.assert_not_called()

    def test_no_price_for_the_route_makes_nothing(self):
        self.route_call.return_value = uzpost.Answer(False, None, 'no price for this route', False)
        with self.assertRaises(shipments.ShipmentError):
            self.ship()
        self.create_call.assert_not_called()

    @override_settings(UZPOST_LOGIN='', UZPOST_PASSWORD='')
    def test_without_the_login_nothing_is_asked(self):
        with self.assertRaises(shipments.ShipmentError) as raised:
            self.ship()
        self.assertIn('UZPOST_LOGIN', raised.exception.message)
        self.route_call.assert_not_called()


@SET_UP
class PanelTests(ShipmentCase):
    """The panel's Uzpost section, its label and its cancel (§17 #379, #380)."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)
        self.screen = reverse('panel_order', kwargs={'order_no': self.order.order_no})

    def test_a_paid_order_offers_the_button_with_its_weight(self):
        page = self.client.get(self.screen).content.decode()
        self.assertIn(reverse('panel_order_shipment', kwargs={'order_no': self.order.order_no}), page)
        self.assertIn('0,34 kg', page)

    @override_settings(UZPOST_LOGIN='', UZPOST_PASSWORD='')
    def test_without_the_login_the_section_says_so(self):
        page = self.client.get(self.screen).content.decode()
        self.assertIn('UZPOST_LOGIN', page)
        self.assertNotIn(reverse('panel_order_shipment', kwargs={'order_no': self.order.order_no}),
                         page)

    def test_pressing_it_makes_the_shipment(self):
        url = reverse('panel_order_shipment', kwargs={'order_no': self.order.order_no})
        response = self.client.post(url, follow=True)
        self.assertContains(response, 'MM216886699UZ')
        self.assertContains(response, 'Yorliqni chop etish')
        self.assertTrue(Shipment.objects.filter(order=self.order).exists())

    def test_a_refusal_is_said_and_the_button_stays(self):
        self.create_call.side_effect = None
        self.create_call.return_value = uzpost.Answer(False, None, 'Invalid argument type', False)
        url = reverse('panel_order_shipment', kwargs={'order_no': self.order.order_no})
        response = self.client.post(url, follow=True)
        self.assertContains(response, 'Invalid argument type')
        self.assertContains(response, 'Joʻnatma yaratish')

    def test_the_label_opens_a_fresh_link(self):
        self.ship()
        link = ANSWERS['label']['data']
        with mock.patch('payment.shipments.uzpost.label',
                        return_value=uzpost.Answer(True, link, '', False)) as label:
            response = self.client.get(
                reverse('panel_order_label', kwargs={'order_no': self.order.order_no}))
        self.assertRedirects(response, link, fetch_redirect_response=False)
        label.assert_called_once_with(5696260512)

    def test_a_label_uzpost_will_not_give_is_said(self):
        self.ship()
        with mock.patch('payment.shipments.uzpost.label',
                        return_value=uzpost.Answer(False, None, 'timeout', False)):
            response = self.client.get(
                reverse('panel_order_label', kwargs={'order_no': self.order.order_no}),
                follow=True)
        self.assertContains(response, 'timeout')

    def test_customers_cannot_reach_any_of_it(self):
        self.client.force_login(self.customer)
        url = reverse('panel_order_shipment', kwargs={'order_no': self.order.order_no})
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertFalse(Shipment.objects.exists())

    def cancel(self, **headers):
        url = reverse('panel_order_status', kwargs={'order_no': self.order.order_no})
        return self.client.post(url, {'status': 'cancelled'}, **headers)

    def test_cancelling_the_order_cancels_its_new_shipment(self):
        shipment = self.ship()
        with mock.patch('payment.shipments.uzpost.cancel', return_value=OK) as cancel:
            response = self.cancel(follow=True)
        cancel.assert_called_once_with('MM216886699UZ')
        shipment.refresh_from_db()
        self.assertIsNotNone(shipment.cancelled_at)
        self.assertEqual(shipment.status, 'cancelled')
        self.assertContains(response, 'MM216886699UZ')
        self.assertIsNone(shipments.live_shipment(self.order))

    def test_an_order_whose_parcel_uzpost_keeps_is_cancelled_all_the_same(self):
        self.ship()
        refusal = uzpost.Answer(False, None, 'Order is not new', False)
        with mock.patch('payment.shipments.uzpost.cancel', return_value=refusal):
            response = self.cancel(HTTP_X_REQUESTED_WITH='fetch')
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['status'], 'cancelled')
        self.assertIn('allaqachon Uzpostda', data['notice'])
        self.assertFalse(data['notice_ok'])
        self.assertIsNotNone(shipments.live_shipment(self.order))

    def test_a_failed_call_back_can_be_tried_again(self):
        self.ship()
        with mock.patch('payment.shipments.uzpost.cancel',
                        return_value=uzpost.Answer(False, None, 'timeout', True)):
            self.cancel()
        with mock.patch('payment.shipments.uzpost.cancel', return_value=OK) as cancel:
            self.cancel()
        cancel.assert_called_once_with('MM216886699UZ')
        self.assertIsNone(shipments.live_shipment(self.order))

    def test_an_unanswered_request_is_shown_and_can_be_withdrawn(self):
        self.create_call.side_effect = None
        self.create_call.return_value = uzpost.Answer(False, None, 'timeout', True)
        url = reverse('panel_order_shipment', kwargs={'order_no': self.order.order_no})
        page = self.client.post(url, follow=True).content.decode()
        withdraw = reverse('panel_order_shipment_withdraw', kwargs={'order_no': self.order.order_no})
        self.assertIn(withdraw, page)
        self.assertNotIn(reverse('panel_order_label', kwargs={'order_no': self.order.order_no}), page)
        with mock.patch('payment.shipments.uzpost.cancel') as cancel:
            response = self.cancel(follow=True)
        cancel.assert_not_called()
        self.assertContains(response, 'my.pochta.uz')
        self.client.post(withdraw)
        self.assertIsNone(shipments.live_shipment(self.order))

    def test_cancelling_an_order_without_a_shipment_asks_uzpost_nothing(self):
        with mock.patch('payment.shipments.uzpost.cancel') as cancel:
            self.cancel()
        cancel.assert_not_called()

    def test_the_django_admin_cancels_it_too(self):
        from django.contrib.admin.sites import site
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        from payment.admin import OrderAdmin

        self.ship()
        request = RequestFactory().post('/')
        request.user = self.staff
        request.session = {}
        request._messages = FallbackStorage(request)
        self.order.refresh_from_db()
        self.order.status = Order.Status.CANCELLED
        with mock.patch('payment.shipments.uzpost.cancel', return_value=OK) as cancel, \
                self.captureOnCommitCallbacks(execute=True):
            OrderAdmin(Order, site).save_model(
                request, self.order, mock.Mock(changed_data=['status']), change=True)
        cancel.assert_called_once_with('MM216886699UZ')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertIsNone(shipments.live_shipment(self.order))


# ====================================================================== following

@SET_UP
class FollowTests(ShipmentCase):
    """The shop's status follows Uzpost's, forward only (§17 #380, §12 risk #35)."""

    def setUp(self):
        super().setUp()
        self.shipment = self.ship()
        self.order.refresh_from_db()
        self.notify = mock.patch('payment.shipments.telegram.notify_shipment_status').start()

    def read(self, status, **over):
        with mock.patch('payment.shipments.uzpost.details', return_value=uzpost.Answer(
                True, facts(status=status, status_at=timezone.now(), **over), '', False)):
            return shipments.follow(Shipment.objects.get(pk=self.shipment.pk))

    def status(self):
        self.order.refresh_from_db()
        return self.order.status

    def test_a_parcel_on_its_way_moves_the_order_with_uzpost_in_the_trail(self):
        self.assertTrue(self.read('in_transit'))
        self.assertEqual(self.status(), Order.Status.ON_THE_WAY)
        change = self.order.status_changes.order_by('-pk').first()
        self.assertTrue(change.is_uzpost)
        self.assertEqual(change.note, 'Uzpost: in_transit')
        self.client.force_login(self.staff)
        page = self.client.get(reverse('panel_order', kwargs={'order_no': self.order.order_no}))
        self.assertContains(page, '<span>Uzpost</span>', html=False)

    def test_a_delivered_parcel_makes_the_order_done(self):
        self.read('in_transit')
        self.read('completed')
        self.assertEqual(self.status(), Order.Status.DONE)
        seen = list(ShipmentStatus.objects.filter(shipment=self.shipment)
                    .order_by('at', 'pk').values_list('status', flat=True))
        self.assertEqual(seen, ['unassigned', 'in_transit', 'completed'])

    def test_a_shipment_just_made_moves_nothing(self):
        self.read('unassigned')
        self.assertEqual(self.status(), Order.Status.PROCESSING)

    def test_it_never_moves_an_order_back(self):
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.DONE)
        self.read('in_transit')
        self.assertEqual(self.status(), Order.Status.DONE)

    def test_it_never_touches_a_cancelled_or_unpaid_order(self):
        for status, at_uzpost in ((Order.Status.CANCELLED, 'in_transit'),
                                  (Order.Status.PAYING, 'completed')):
            with self.subTest(status=status):
                Order.objects.filter(pk=self.order.pk).update(status=status)
                self.read(at_uzpost)
                self.assertEqual(self.status(), status)

    def test_an_order_staff_moved_back_stays_until_uzpost_says_more(self):
        self.read('in_transit')
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.PROCESSING)
        self.read('in_transit')
        self.assertEqual(self.status(), Order.Status.PROCESSING)
        self.read('out_for_delivery')
        self.assertEqual(self.status(), Order.Status.ON_THE_WAY)

    def test_a_status_it_does_not_know_changes_nothing_and_is_told_once(self):
        self.read('returned_to_origin')
        self.read('returned_to_origin')
        self.assertEqual(self.status(), Order.Status.PROCESSING)
        self.assertEqual(self.notify.call_count, 1)
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.status, 'returned_to_origin')

    def test_a_shipment_uzpost_cancelled_stops_being_live_and_is_told(self):
        self.read('cancelled')
        self.assertEqual(self.notify.call_count, 1)
        self.assertIsNone(shipments.live_shipment(self.order))
        self.assertEqual(self.status(), Order.Status.PROCESSING)
        # And the button is back, for staff to send it again.
        self.assertTrue(shipments.can_create(self.order))

    def test_uzpost_down_is_a_failed_read_and_nothing_else(self):
        with mock.patch('payment.shipments.uzpost.details',
                        return_value=uzpost.Answer(False, None, 'timeout', False)):
            self.assertFalse(shipments.follow(self.shipment))
        self.assertEqual(self.status(), Order.Status.PROCESSING)

    def test_a_parcel_waiting_at_its_office_reaches_the_owner_and_no_sms_goes(self):
        """The arrival SMS is a draft (§17 #394): the status it needs is learnt
        from the owner's message about a status the shop does not know."""
        with mock.patch('core.sms.send_sms') as send:
            self.read('at_office')
            self.read('at_office')
        send.assert_not_called()
        self.assertEqual(self.notify.call_count, 1)
        self.assertEqual(self.status(), Order.Status.PROCESSING)


@SET_UP
class SyncCommandTests(ShipmentCase):
    """``uzpost_sync``, the job the timer runs every 30 minutes."""

    def setUp(self):
        super().setUp()
        self.shipment = self.ship()
        mock.patch('payment.management.commands.uzpost_sync.PAUSE', 0).start()

    def test_it_reads_every_live_shipment(self):
        with mock.patch('payment.shipments.follow', return_value=True) as follow:
            call_command('uzpost_sync', stdout=StringIO())
        follow.assert_called_once()

    def test_it_stops_after_failures_in_a_row(self):
        for _ in range(7):
            order = placed(self.customer, self.variant, self.geo)
            self.ship(order)
        with mock.patch('payment.shipments.follow', return_value=False) as follow:
            call_command('uzpost_sync', stdout=StringIO(), stderr=StringIO())
        self.assertEqual(follow.call_count, 5)

    def test_a_delivered_or_cancelled_shipment_is_not_read_again(self):
        Shipment.objects.filter(pk=self.shipment.pk).update(status='completed')
        with mock.patch('payment.shipments.follow') as follow:
            call_command('uzpost_sync', stdout=StringIO())
        follow.assert_not_called()

    def test_an_old_shipment_or_an_unanswered_request_is_not_read(self):
        Shipment.objects.filter(pk=self.shipment.pk).update(
            created_at=timezone.now() - timedelta(days=shipments.FOLLOW_DAYS + 1))
        order = placed(self.customer, self.variant, self.geo)
        Shipment.objects.create(order=order, service='ONE_STEP_WITHOUT_BAG',
                                weight=Decimal('0.170'), status=shipments.REQUESTED)
        with mock.patch('payment.shipments.follow') as follow:
            call_command('uzpost_sync', stdout=StringIO())
        follow.assert_not_called()

    @override_settings(UZPOST_LOGIN='', UZPOST_PASSWORD='')
    def test_without_the_login_it_reads_nothing(self):
        out = StringIO()
        with mock.patch('payment.shipments.follow') as follow:
            call_command('uzpost_sync', stdout=out)
        follow.assert_not_called()
        self.assertIn('not set up', out.getvalue())

    def test_the_timer_is_in_the_repository(self):
        folder = Path(settings.BASE_DIR) / 'deploy' / 'systemd'
        self.assertIn('uzpost_sync', (folder / 'graphix-uzpost.service').read_text())
        self.assertIn('*:00/30', (folder / 'graphix-uzpost.timer').read_text())


# ====================================================================== the customer

@SET_UP
class OrderPageTests(ShipmentCase):
    """The customer follows the parcel without the page calling Uzpost (item 13)."""

    def setUp(self):
        super().setUp()
        self.shipment = self.ship()
        self.client.force_login(self.customer)
        self.url = reverse('order_detail', args=[self.order.pk])

    def test_the_number_status_office_and_history_are_shown(self):
        with mock.patch('core.uzpost._call', side_effect=AssertionError('no call')):
            page = self.client.get(self.url).content.decode()
        self.assertIn('MM216886699UZ', page)
        self.assertIn('Rasmiylashtirildi', page)
        self.assertIn('Коканд ОПС', page)
        self.assertIn('https://uz.post/uz/tracking/MM216886699UZ/', page)

    def test_the_status_is_in_the_readers_language(self):
        with translation.override('ru'):
            page = self.client.get(reverse('order_detail', args=[self.order.pk])).content.decode()
        self.assertIn('Отправление оформлено', page)

    def test_the_hold_is_fourteen_days(self):
        page = self.client.get(self.url).content.decode()
        self.assertIn('14 kun saqlanadi', page)

    def test_a_cancelled_shipment_is_not_shown(self):
        Shipment.objects.filter(pk=self.shipment.pk).update(cancelled_at=timezone.now())
        self.assertNotContains(self.client.get(self.url), 'MM216886699UZ')

    def test_nobody_else_sees_the_number(self):
        self.client.force_login(make_user('boshqa', '+998901220077'))
        self.assertEqual(self.client.get(self.url).status_code, 404)


class TelegramEventTests(ShipmentCase):
    """``uzpost.status``: a status the shop does not act on, told to the owner."""

    @SET_UP
    def test_the_event_carries_the_order_the_parcel_and_the_status(self):
        shipment = self.ship()
        shipment.status = 'returned_to_origin'
        with mock.patch('core.telegram.notify') as notify:
            from core import telegram
            telegram.notify_shipment_status(shipment)
        text = notify.call_args.args[0]
        self.assertIn(self.order.order_no, text)
        self.assertIn('returned_to_origin', text)
        self.assertEqual(notify.call_args.kwargs['event'], 'uzpost.status')
        data = notify.call_args.kwargs['data']['shipment']
        self.assertEqual(data['number'], 'MM216886699UZ')
        self.assertTrue(data['admin_url'].endswith(f'/boshqaruv/buyurtmalar/{self.order.order_no}/'))


# ====================================================================== words

class WordsTests(TestCase):
    """The delivery page, the terms and the privacy policy say what the shop does now."""

    def page(self, name, lang):
        with translation.override(lang):
            return self.client.get(reverse(name)).content.decode()

    def test_the_office_is_bir_qadam_and_holds_fourteen_days(self):
        expected = {'uz': '14 kun', 'ru': '14 дней', 'en': '14 days'}
        for lang, words in expected.items():
            for name in ('delivery', 'terms'):
                with self.subTest(lang=lang, page=name):
                    page = self.page(name, lang)
                    self.assertIn('Bir Qadam', page)
                    self.assertIn(words, page)

    def test_no_page_asks_for_an_index_or_sends_to_uzposts_map(self):
        for lang in ('uz', 'ru', 'en'):
            for name in ('delivery', 'terms', 'privacy'):
                with self.subTest(lang=lang, page=name):
                    self.assertNotIn('uz.post/uz/map', self.page(name, lang))
                    self.assertNotIn('uz.post/ru/map', self.page(name, lang))

    def test_no_page_promises_an_sms_when_the_parcel_arrives(self):
        """Not sent, so not promised (§17 #394)."""
        unsent = {'uz': 'SMS yuboramiz', 'ru': 'пришлём вам SMS', 'en': 'text message when'}
        for lang, words in unsent.items():
            for name in ('delivery', 'terms', 'privacy'):
                with self.subTest(lang=lang, page=name):
                    self.assertNotIn(words, self.page(name, lang))

    def test_the_privacy_policy_names_what_goes_to_uzpost(self):
        page = self.page('privacy', 'uz')
        self.assertIn('Pochta tizimiga', page)
        self.assertIn('Menga yaqin', page)
