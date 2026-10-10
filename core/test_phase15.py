"""Phase 15: a customer signs in and signs up with a phone number and a code.

There is no username and no password on the storefront any more, so the code
sent by SMS is the only key to an account. These tests are the phase's
Definition of Done written as assertions, and most of them are about the ways
that key could be got round: guessing it, guessing it from a second browser,
asking for it until the shop has paid for a thousand SMS, and reading a
customer's number off a public page now that the number is the username.

Nothing here reaches Eskiz. Each test gets an :class:`Inbox`, which stands in
for the gateway and keeps what it was asked to send, so a test reads the code
the way a customer does: out of the message.
"""
import importlib
import re
from datetime import timedelta
from unittest import mock

from django.apps import apps
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from cart.models import Cart, CartItem
from core import legal, telegram
from core.ratelimit import RATE_LIMIT_MESSAGE, _bucket_key
from payment.models import Order
from product.models import Review
from user import codes, services
from user.models import User

from .test_phase4 import make_product

PHONE = '+998 90 111 22 33'
OTHER = '+998 90 111 22 44'
LANGS = ('uz', 'ru', 'en')


class Inbox:
    """Stands in for the SMS gateway and keeps what it was asked to send."""

    def __init__(self):
        self.delivers = True
        self.messages = []

    def __call__(self, phone, message):
        if self.delivers:
            self.messages.append((phone, message))
        return self.delivers

    @property
    def code(self):
        """The code in the last message, read as a customer reads it."""
        return re.search(r'\b\d{6}\b', self.messages[-1][1]).group(0)


def catch_sms(test):
    """Send this test's codes to an :class:`Inbox` instead of to Eskiz.

    The counters are emptied as well, before and after. The limits on codes
    are kept in the cache, which outlives a test, and fifty tests signing in
    from the test client's one address would otherwise run into the limit
    that address has.
    """
    cache.clear()
    test.addCleanup(cache.clear)
    inbox = Inbox()
    patcher = mock.patch.object(codes, 'send_sms', inbox)
    patcher.start()
    test.addCleanup(patcher.stop)
    return inbox


def customer(phone=PHONE, name=''):
    """An account as sign-up leaves it: a number, no password."""
    user = services.create_customer(phone, legal.accepted_versions())
    if name:
        user.first_name = name
        user.save(update_fields=['first_name'])
    return user


def make_order(user, variant):
    """A delivered order of one ``variant``, which is what a review needs."""
    cart = Cart.objects.create(user=user, status=False)
    CartItem.objects.create(cart=cart, variant=variant, quantity=1, price_stat=variant.price)
    return Order.objects.create(user=user, cart=cart, phone=user.phone, address='Amir Temur 1',
                                total_price=variant.price, status='done')


def enter_by_code(client, inbox, phone=PHONE, door='login', **query):
    """Go in by a door as a customer does: the number, then the code sent to it."""
    target = reverse(door)
    if query:
        target += '?' + '&'.join('%s=%s' % pair for pair in query.items())
    data = {'phone': phone}
    if door == 'signup':
        data['agree'] = 'on'
    client.post(target, data)
    return client.post(reverse('verify_phone'), {'code': inbox.code})


def wrong(code):
    """Six digits that are not ``code``."""
    return '%06d' % ((int(code) + 1) % 1000000)


def age(client, **seconds):
    """Move the open attempt's timestamps back, as if that long had passed."""
    session = client.session
    state = session[codes.SESSION_KEY]
    for key, value in seconds.items():
        moved = timezone.datetime.fromisoformat(state[key]) - timedelta(seconds=value)
        state[key] = moved.isoformat()
    session[codes.SESSION_KEY] = state
    session.save()


class CodeCase(TestCase):
    """Every test starts with empty counters and an inbox of its own."""

    def setUp(self):
        self.inbox = catch_sms(self)

    def signed_in(self, client=None):
        """The id of whoever this browser is signed in as, or None."""
        return (client or self.client).session.get('_auth_user_id')

    def ask(self, phone=PHONE, door='login', client=None, **extra):
        """Post a number at a door."""
        data = {'phone': phone}
        if door == 'signup':
            data['agree'] = 'on'
        return (client or self.client).post(reverse(door), data, **extra)

    def enter(self, code, client=None):
        """Post a code on the code page."""
        return (client or self.client).post(reverse('verify_phone'), {'code': code})


# ------------------------------------------------------------------ sign-up

class SignUpTests(CodeCase):
    """A new number, the consent box and a code. The account waits for the code."""

    def test_a_new_number_signs_up_and_lands_signed_in(self):
        response = self.ask(door='signup')
        self.assertRedirects(response, reverse('verify_phone'))
        self.assertFalse(User.objects.exists(), 'the account must wait for the code')

        response = self.enter(self.inbox.code)
        self.assertRedirects(response, reverse('account'))
        user = User.objects.get()
        self.assertEqual(user.phone, PHONE)
        self.assertEqual(user.username, '+998901112233')
        self.assertTrue(user.phone_verified)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(self.signed_in(), str(user.pk))

    def test_the_documents_agreed_to_are_stamped_on_the_account(self):
        enter_by_code(self.client, self.inbox, door='signup')
        user = User.objects.get()
        agreed = legal.accepted_versions()
        self.assertTrue(all(agreed.values()))
        self.assertEqual({'terms_version': user.terms_version,
                          'privacy_version': user.privacy_version}, agreed)

    def test_a_wrong_code_makes_no_account(self):
        self.ask(door='signup')
        response = self.enter(wrong(self.inbox.code))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())
        self.assertIsNone(self.signed_in())

    def test_without_the_consent_box_no_code_is_sent(self):
        response = self.client.post(reverse('signup'), {'phone': PHONE})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors['agree'])
        self.assertEqual(self.inbox.messages, [])

    def test_a_number_that_is_not_a_number_is_refused(self):
        for typed in ('', 'telefon', '+998 90 111', '+7 900 111 22 33'):
            with self.subTest(typed=typed):
                response = self.ask(typed, door='signup')
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors['phone'])
        self.assertEqual(self.inbox.messages, [])

    def test_a_number_in_another_scripts_digits_is_refused(self):
        """The same number written in them would be a second account, with
        its own allowance of codes."""
        customer()
        for door in ('login', 'signup'):
            with self.subTest(door=door):
                response = self.ask('+998 ٩٠ ١١١ ٢٢ ٣٣', door=door)
                self.assertTrue(response.context['form'].errors['phone'])
        self.assertEqual(self.inbox.messages, [])
        self.assertEqual(User.objects.count(), 1)

    def test_a_registered_number_is_told_so_and_offered_sign_in(self):
        customer()
        response = self.client.post(reverse('signup') + '?next=/uz/checkout/',
                                    {'phone': PHONE, 'agree': 'on'})
        self.assertContains(response, 'Bu raqam roʻyxatdan oʻtgan.')
        door = response.context['other_door']
        self.assertTrue(door.startswith(reverse('login') + '?'))
        self.assertIn('phone=%2B998+90+111+22+33', door)
        self.assertIn('next=%2Fuz%2Fcheckout%2F', door)
        self.assertEqual(self.inbox.messages, [])
        # The other door opens with the number already in it.
        self.assertContains(self.client.get(door), 'value="%s"' % PHONE)

    def test_the_message_is_the_text_eskiz_approved(self):
        self.ask(door='signup')
        phone, text = self.inbox.messages[0]
        self.assertEqual(phone, PHONE)
        self.assertEqual(text, "GRAPHIX saytida ro'yxatdan o'tish uchun kodingiz: %s"
                         % self.inbox.code)


# ------------------------------------------------------------------ sign-in

class SignInTests(CodeCase):
    """A registered number and a code."""

    def test_a_registered_number_signs_in(self):
        user = customer()
        response = self.ask()
        self.assertRedirects(response, reverse('verify_phone'))
        response = self.enter(self.inbox.code)
        self.assertRedirects(response, reverse('shop'))
        self.assertEqual(self.signed_in(), str(user.pk))

    def test_the_message_has_a_text_of_its_own(self):
        customer()
        self.ask()
        self.assertEqual(self.inbox.messages[0][1],
                         'GRAPHIX saytiga kirish uchun kodingiz: %s' % self.inbox.code)

    def test_the_number_may_be_typed_any_of_the_usual_ways(self):
        user = customer()
        for typed in ('+998901112233', '901112233', '998 90 111-22-33', '(90) 111 22 33'):
            with self.subTest(typed=typed):
                self.client.logout()
                cache.clear()
                enter_by_code(self.client, self.inbox, typed)
                self.assertEqual(self.signed_in(), str(user.pk))

    def test_an_unregistered_number_is_told_so_and_offered_sign_up(self):
        response = self.client.post(reverse('login') + '?next=/uz/checkout/', {'phone': PHONE})
        self.assertContains(response, 'Bu raqam roʻyxatdan oʻtmagan.')
        door = response.context['other_door']
        self.assertTrue(door.startswith(reverse('signup') + '?'))
        self.assertIn('next=%2Fuz%2Fcheckout%2F', door)
        self.assertEqual(self.inbox.messages, [])
        self.assertContains(self.client.get(door), 'value="%s"' % PHONE)

    def test_the_way_back_is_kept_through_both_pages(self):
        customer()
        response = enter_by_code(self.client, self.inbox, next='/uz/checkout/')
        self.assertRedirects(response, '/uz/checkout/', fetch_redirect_response=False)

    def test_a_way_back_to_another_site_is_dropped(self):
        """And a bare word: it names no host, so it would pass for a page of
        this site, and then be read as the name of a view that does not exist."""
        customer()
        for target in ('https://evil.example/', '//evil.example/x', 'zzz', 'javascript:alert(1)'):
            with self.subTest(target=target):
                self.client.logout()
                cache.clear()
                response = enter_by_code(self.client, self.inbox, next=target)
                self.assertRedirects(response, reverse('shop'))

    def test_an_existing_customer_finds_their_orders(self):
        user = customer()
        _, variant = make_product('Buyurtma qilingan', stock=3)
        order = make_order(user, variant)
        enter_by_code(self.client, self.inbox)
        response = self.client.get(reverse('account_orders'))
        self.assertEqual(list(response.context['orders']), [order])

    def test_a_switched_off_account_is_told_so_before_any_code(self):
        user = customer()
        user.is_active = False
        user.save(update_fields=['is_active'])
        response = self.ask()
        self.assertContains(response, 'Bu hisob faol emas.')
        self.assertEqual(self.inbox.messages, [])

    def test_someone_already_signed_in_is_sent_to_their_account(self):
        self.client.force_login(customer())
        for door in ('login', 'signup'):
            with self.subTest(door=door):
                self.assertRedirects(self.client.get(reverse(door)), reverse('account'))


# ---------------------------------------------------------------- the code

class CodePageTests(CodeCase):
    """What a code is held to between being sent and being entered."""

    def setUp(self):
        super().setUp()
        self.user = customer()

    def test_the_page_is_closed_without_an_attempt(self):
        self.assertRedirects(self.client.get(reverse('verify_phone')), reverse('login'))
        self.assertRedirects(self.enter('123456'), reverse('login'))

    def test_the_session_never_holds_the_code(self):
        self.ask()
        state = self.client.session[codes.SESSION_KEY]
        self.assertNotIn(self.inbox.code, str(state))
        self.assertEqual(len(state['digest']), 40)

    def test_a_code_is_bound_to_its_number_and_its_purpose(self):
        code = '246810'
        mine = codes._digest(codes.SIGN_IN, PHONE, code)
        self.assertNotEqual(mine, codes._digest(codes.SIGN_IN, OTHER, code))
        self.assertNotEqual(mine, codes._digest(codes.SIGN_UP, PHONE, code))

    def test_a_code_works_once(self):
        self.ask()
        code = self.inbox.code
        self.enter(code)
        # Signing in keeps the session's contents, so the attempt has to be
        # taken out of it, not merely left behind.
        self.assertNotIn(codes.SESSION_KEY, self.client.session)
        self.client.logout()
        self.assertRedirects(self.enter(code), reverse('login'))
        self.assertIsNone(self.signed_in())

    def test_a_wrong_code_is_said_to_be_wrong(self):
        self.ask()
        response = self.enter(wrong(self.inbox.code))
        self.assertContains(response, 'Kod notoʻgʻri.')
        self.assertIsNone(self.signed_in())

    def test_a_wrong_code_is_not_written_back_into_the_field(self):
        """The cells post the form once all six are filled. With the wrong
        digits left in them, the next key pressed would send them again."""
        self.ask()
        tried = wrong(self.inbox.code)
        html = self.enter(tried).content.decode()
        self.assertNotIn(tried, html)

    def test_anything_but_six_digits_is_not_a_try(self):
        self.ask()
        for typed in ('', '12345', '1234567', 'abcdef'):
            with self.subTest(typed=typed):
                self.assertEqual(self.enter(typed).status_code, 200)
        self.assertEqual(self.client.session[codes.SESSION_KEY]['attempts'], 0)

    def test_seven_wrong_codes_end_the_attempt(self):
        self.ask()
        code = self.inbox.code
        for _ in range(codes.MAX_ATTEMPTS - 1):
            self.assertEqual(self.enter(wrong(code)).status_code, 200)
        self.assertRedirects(self.enter(wrong(code)), reverse('login'))
        # The right code is no use now: the attempt is over.
        self.assertRedirects(self.enter(code), reverse('login'))
        self.assertIsNone(self.signed_in())

    def test_a_new_session_does_not_reset_the_count(self):
        self.ask()
        for _ in range(codes.MAX_ATTEMPTS):
            self.enter(wrong(self.inbox.code))
        sent = len(self.inbox.messages)

        second = self.client_class()
        response = self.ask(client=second)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(RATE_LIMIT_MESSAGE))
        self.assertEqual(len(self.inbox.messages), sent, 'no new code for a number being guessed at')

    def test_a_second_session_cannot_carry_the_guessing_on(self):
        """Two browsers each ask for a code, then share seven tries, not fourteen."""
        second = self.client_class()
        self.ask()
        first_code = self.inbox.code
        self.ask(client=second)
        second_code = self.inbox.code
        for _ in range(codes.MAX_ATTEMPTS):
            self.enter(wrong(first_code))
        self.assertRedirects(self.enter(second_code, client=second), reverse('login'))
        self.assertIsNone(self.signed_in(second))

    def test_wrong_codes_are_counted_by_the_hour_as_well(self):
        """Seven tries a code would otherwise be seven with every new code.

        Six wrong tries at a time, with the short counts run out in between
        as they would be five and ten minutes later: the twentieth is the
        last, whatever code it is tried against.
        """
        self.assertEqual(codes.WRONG_HOUR, 20)
        tried = 0
        while tried < codes.WRONG_HOUR:
            cache.delete(_bucket_key('code_wrong', PHONE))
            cache.delete(_bucket_key('code_number_short', PHONE))
            self.assertRedirects(self.ask(), reverse('verify_phone'))
            for _ in range(min(6, codes.WRONG_HOUR - tried)):
                self.enter(wrong(self.inbox.code))
                tried += 1
        cache.delete(_bucket_key('code_wrong', PHONE))
        cache.delete(_bucket_key('code_number_short', PHONE))
        sent = len(self.inbox.messages)
        self.assertContains(self.ask(), str(RATE_LIMIT_MESSAGE))
        self.assertEqual(len(self.inbox.messages), sent)

    def test_the_session_still_counts_when_the_cache_cannot(self):
        self.ask()
        code = self.inbox.code
        with mock.patch('core.ratelimit.cache.incr', side_effect=RuntimeError('down')):
            for _ in range(codes.MAX_ATTEMPTS - 1):
                self.assertEqual(self.enter(wrong(code)).status_code, 200)
            self.assertRedirects(self.enter(wrong(code)), reverse('login'))

    def test_a_code_lasts_five_minutes(self):
        self.assertEqual(codes.TTL_SECONDS, 300)
        self.ask()
        code = self.inbox.code
        age(self.client, expires_at=codes.TTL_SECONDS + 1)
        response = self.enter(code)
        self.assertRedirects(response, reverse('login') + '?reason=expired')
        self.assertIsNone(self.signed_in())
        self.assertContains(self.client.get(response['Location']), 'Kod muddati tugadi.')

    def test_another_code_waits_a_minute(self):
        self.ask()
        self.client.post(reverse('resend_otp'))
        self.assertEqual(len(self.inbox.messages), 1)
        age(self.client, sent_at=codes.RESEND_COOLDOWN + 1)
        self.client.post(reverse('resend_otp'))
        self.assertEqual(len(self.inbox.messages), 2)

    def test_a_new_code_replaces_the_old_and_keeps_the_deadline(self):
        self.ask()
        old = self.inbox.code
        deadline = self.client.session[codes.SESSION_KEY]['expires_at']
        age(self.client, sent_at=codes.RESEND_COOLDOWN + 1)
        with mock.patch.object(codes.secrets, 'randbelow', return_value=int(wrong(old))):
            self.client.post(reverse('resend_otp'))
        self.assertEqual(self.client.session[codes.SESSION_KEY]['expires_at'], deadline)
        self.assertEqual(self.enter(old).status_code, 200)
        self.assertRedirects(self.enter(self.inbox.code), reverse('shop'))

    def test_giving_up_ends_the_attempt(self):
        self.ask()
        code = self.inbox.code
        self.assertRedirects(self.client.post(reverse('cancel_verification')), reverse('login'))
        self.assertRedirects(self.enter(code), reverse('login'))

    def test_giving_up_a_sign_up_says_so(self):
        self.ask(OTHER, door='signup')
        response = self.client.post(reverse('cancel_verification'))
        self.assertRedirects(response, reverse('signup') + '?reason=cancelled')
        self.assertFalse(User.objects.filter(phone=OTHER).exists())

    def test_the_countdown_cannot_end_a_live_attempt(self):
        """The page posts here at zero. The server's clock decides, not the page's."""
        self.ask()
        self.assertRedirects(self.client.post(reverse('expire_verification')),
                             reverse('verify_phone'))
        self.assertRedirects(self.enter(self.inbox.code), reverse('shop'))

    def test_the_countdown_ends_an_attempt_that_is_over(self):
        self.ask()
        age(self.client, expires_at=codes.TTL_SECONDS + 1)
        self.assertRedirects(self.client.post(reverse('expire_verification')),
                             reverse('login') + '?reason=expired')

    def test_the_three_buttons_only_answer_a_post(self):
        for name in ('resend_otp', 'cancel_verification', 'expire_verification'):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 405)

    def test_the_page_works_without_its_script(self):
        """One ordinary field named ``code``, in a form that posts to its own
        address. The six cells are there too, hidden until the script is ready,
        and nothing the page needs is disabled or hidden waiting for it."""
        self.ask()
        html = self.client.get(reverse('verify_phone')).content.decode()
        self.assertRegex(html, r'<form method="post"[^>]*id="otpForm"')
        self.assertRegex(html, r'<input class="input otp__plain" type="text" name="code" id="id_code"')
        self.assertIn('<div class="otp" hidden>', html)
        self.assertNotRegex(html, r'id="otpResend"[^>]*disabled')
        self.assertNotIn(self.inbox.code, html)


# -------------------------------------------------------------- the limits

class LimitTests(CodeCase):
    """Every code costs an SMS, so each of these refuses past its figure."""

    def test_the_figures_are_the_ones_agreed(self):
        self.assertEqual((codes.NUMBER_SHORT, codes.NUMBER_HOUR, codes.ADDRESS_HOUR,
                          codes.SITE_HOUR), (4, 8, 50, 150))

    def test_a_number_gets_four_codes_in_ten_minutes(self):
        customer()
        customer(OTHER)
        for _ in range(codes.NUMBER_SHORT):
            self.assertRedirects(self.ask(), reverse('verify_phone'))
        response = self.ask()
        self.assertContains(response, str(RATE_LIMIT_MESSAGE))
        self.assertEqual(len(self.inbox.messages), codes.NUMBER_SHORT)
        # The limit is the number's, so another number is not held up by it.
        self.assertRedirects(self.ask(OTHER), reverse('verify_phone'))

    def test_a_number_gets_eight_codes_in_an_hour(self):
        customer()
        for _ in range(2):
            for _ in range(codes.NUMBER_SHORT):
                self.assertRedirects(self.ask(), reverse('verify_phone'))
            # Ten minutes on: the short count has run out, the hour's has not.
            cache.delete(_bucket_key('code_number_short', PHONE))
        self.assertEqual(self.ask().status_code, 200)
        self.assertEqual(len(self.inbox.messages), codes.NUMBER_HOUR)

    def test_the_resend_button_spends_the_same_allowance(self):
        customer()
        self.ask()
        for _ in range(codes.NUMBER_SHORT - 1):
            age(self.client, sent_at=codes.RESEND_COOLDOWN + 1)
            self.client.post(reverse('resend_otp'))
        age(self.client, sent_at=codes.RESEND_COOLDOWN + 1)
        self.client.post(reverse('resend_otp'))
        self.assertEqual(len(self.inbox.messages), codes.NUMBER_SHORT)

    def test_an_address_gets_its_figure_and_no_more(self):
        with mock.patch.object(codes, 'ADDRESS_HOUR', 3):
            for n in range(3):
                response = self.ask('+998 90 200 00 0%d' % n, door='signup')
                self.assertRedirects(response, reverse('verify_phone'))
            response = self.ask('+998 90 200 00 09', door='signup')
            self.assertContains(response, str(RATE_LIMIT_MESSAGE))
            self.assertEqual(len(self.inbox.messages), 3)
            # Another address is another visitor.
            response = self.ask('+998 90 200 00 09', door='signup', REMOTE_ADDR='10.9.9.9')
            self.assertRedirects(response, reverse('verify_phone'))

    def test_an_ipv6_visitor_is_counted_by_the_network_they_were_given(self):
        """One machine has a /64 of addresses to itself, and could otherwise
        give each request a new one and never be counted twice."""
        from core.ratelimit import address_bucket
        self.assertEqual(address_bucket('2001:db8:1:2:aaaa:bbbb:cccc:dddd'), '2001:db8:1:2::/64')
        self.assertEqual(address_bucket('2001:db8:1:2::1'), '2001:db8:1:2::/64')
        self.assertNotEqual(address_bucket('2001:db8:1:3::1'), '2001:db8:1:2::/64')
        self.assertEqual(address_bucket('::ffff:203.0.113.9'), '203.0.113.9')
        self.assertEqual(address_bucket('203.0.113.9'), '203.0.113.9')
        self.assertEqual(address_bucket('unknown'), 'unknown')
        with mock.patch.object(codes, 'ADDRESS_HOUR', 3):
            for n in range(3):
                self.ask('+998 90 200 00 0%d' % n, door='signup',
                         REMOTE_ADDR='2001:db8:1:2::%d' % (n + 1))
            response = self.ask('+998 90 200 00 09', door='signup',
                                REMOTE_ADDR='2001:db8:1:2:ffff::9')
        self.assertContains(response, str(RATE_LIMIT_MESSAGE))
        self.assertEqual(len(self.inbox.messages), 3)

    def test_the_whole_site_has_a_ceiling_and_the_owner_is_told_once(self):
        with (mock.patch.object(codes, 'SITE_HOUR', 3),
              mock.patch.object(telegram, 'notify_code_ceiling') as told):
            for n in range(3):
                self.ask('+998 90 300 00 0%d' % n, door='signup', REMOTE_ADDR='10.1.1.%d' % n)
            for n in range(3, 6):
                response = self.ask('+998 90 300 00 0%d' % n, door='signup',
                                    REMOTE_ADDR='10.1.1.%d' % n)
                self.assertContains(response, 'Hozir kod yubora olmaymiz.')
        self.assertEqual(len(self.inbox.messages), 3)
        told.assert_called_once_with(3)

    def test_a_code_that_could_not_be_sent_is_said_and_not_counted(self):
        customer()
        self.inbox.delivers = False
        for _ in range(codes.NUMBER_SHORT + 2):
            response = self.ask()
            self.assertContains(response, 'Kod yuborilmadi.')
        self.assertNotIn(codes.SESSION_KEY, self.client.session)
        self.inbox.delivers = True
        self.assertRedirects(self.ask(), reverse('verify_phone'))

    def test_no_code_is_sent_when_the_counters_cannot_be_kept(self):
        """Elsewhere a limit that cannot be read lets the request through. Not here."""
        customer()
        with mock.patch.object(codes, '_counting', return_value=False):
            response = self.ask()
        self.assertContains(response, 'Hozir kod yubora olmaymiz.')
        self.assertEqual(self.inbox.messages, [])

    def test_a_cache_that_is_down_is_noticed(self):
        self.assertTrue(codes._counting())
        with (mock.patch.object(codes.cache, 'set', side_effect=RuntimeError('down')),
              self.assertLogs('user.codes', level='ERROR')):
            self.assertFalse(codes._counting())

    def test_the_doors_are_limited_by_address(self):
        customer()
        cache.set(_bucket_key('code_ask_address', '127.0.0.1'), 60, 300)
        response = self.ask()
        self.assertContains(response, str(RATE_LIMIT_MESSAGE))
        self.assertEqual(self.inbox.messages, [])

    def test_the_gateway_failing_in_a_new_way_is_still_only_not_sent(self):
        """A reply from Eskiz in a shape nobody has seen must not be a failed page."""
        from core import sms
        with (mock.patch.object(sms, '_get_token', side_effect=KeyError('data')),
              self.assertLogs('core.sms', level='ERROR')):
            self.assertFalse(sms.send_sms(PHONE, 'matn'))


# ---------------------------------------------------- no password anywhere

class NoPasswordTests(CodeCase):
    """No storefront page asks for a password, and none accepts one."""

    def test_no_page_has_a_password_field(self):
        user = customer()
        for lang in LANGS:
            with translation.override(lang):
                doors = [reverse('login'), reverse('signup')]
                settings_page = reverse('account_settings')
            for address in doors:
                with self.subTest(address=address):
                    html = self.client.get(address).content.decode()
                    self.assertNotIn('type="password"', html)
                    self.assertNotIn('name="username"', html)
            self.client.force_login(user)
            html = self.client.get(settings_page).content.decode()
            self.assertNotIn('type="password"', html)
            self.assertNotIn('name="username"', html)
            self.client.logout()

    def test_a_username_and_password_open_nothing(self):
        user = User.objects.create_user(username='eski', password='parol12345', phone=PHONE)
        user.phone_verified = True
        user.save()
        response = self.client.post(reverse('login'),
                                    {'username': 'eski', 'password': 'parol12345'})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.signed_in())

    def test_every_retired_address_still_resolves_and_leads_to_sign_in(self):
        for name in ('account_forgot_password', 'password_reset_request',
                     'password_reset_verify', 'password_reset_resend',
                     'password_reset_expire', 'password_reset_set'):
            for method in ('get', 'post'):
                with self.subTest(name=name, method=method):
                    response = getattr(self.client, method)(reverse(name))
                    self.assertRedirects(response, reverse('login'))

    def test_settings_change_the_name_and_nothing_else(self):
        user = customer()
        self.client.force_login(user)
        response = self.client.post(reverse('account_settings'), {
            'first_name': 'Dilnoza', 'username': 'boshqa', 'phone': OTHER,
            'password': 'parol12345', 'is_staff': 'on'})
        self.assertRedirects(response, reverse('account_settings'))
        user.refresh_from_db()
        self.assertEqual(user.first_name, 'Dilnoza')
        self.assertEqual((user.username, user.phone, user.is_staff),
                         ('+998901112233', PHONE, False))
        self.assertFalse(user.has_usable_password())

    def test_settings_show_the_number_and_how_to_change_it(self):
        self.client.force_login(customer())
        response = self.client.get(reverse('account_settings'))
        self.assertContains(response, PHONE)
        self.assertContains(response, reverse('contact'))
        self.assertNotContains(response, 'name="phone"')


# ------------------------------------------- a number is nobody else's business

class NumberStaysPrivateTests(CodeCase):
    """The username is the phone number now, so no public page may print it."""

    def assert_no_number(self, html):
        for spelling in ('+998901112233', '998901112233', '90 111 22 33', '901112233'):
            self.assertNotIn(spelling, html)

    def test_the_public_name_is_the_first_name_or_a_word(self):
        user = customer()
        for lang, word in (('uz', 'Xaridor'), ('ru', 'Покупатель'), ('en', 'Customer')):
            with self.subTest(lang=lang), translation.override(lang):
                self.assertEqual(user.public_name, word)
        user.first_name = 'Dilnoza'
        self.assertEqual(user.public_name, 'Dilnoza')

    def test_a_review_with_no_name_shows_a_word_and_not_the_number(self):
        user = customer()
        product, variant = make_product('Sharhlangan', stock=3)
        Review.objects.create(user=user, product=product, order=make_order(user, variant),
                              rating=5, text='Yaxshi', status=Review.Status.APPROVED)
        html = self.client.get(reverse('item', kwargs={'slug': product.slug})).content.decode()
        self.assertIn('<span class="review__who">Xaridor</span>', html)
        self.assertIn('"author": {"@type": "Person", "name": "Xaridor"}', html)
        self.assert_no_number(html)

    def test_the_header_does_not_read_the_number_out(self):
        self.client.force_login(customer())
        for name in ('home', 'shop', 'cart'):
            with self.subTest(name=name):
                self.assert_no_number(self.client.get(reverse(name)).content.decode())


# -------------------------------------------------------------------- staff

class StaffTests(CodeCase):
    """Staff keep a password, at the admin's form, and that is their only door."""

    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username='egasi', password='parol12345',
                                              phone=PHONE, is_staff=True, is_superuser=True)
        self.owner.phone_verified = True
        self.owner.save()

    def admin_sign_in(self, password='parol12345', **extra):
        return self.client.post('/admin/login/?next=%s' % reverse('panel_dashboard'),
                                {'username': 'egasi', 'password': password}, **extra)

    def test_the_owner_signs_in_with_sms_switched_off(self):
        self.inbox.delivers = False
        response = self.admin_sign_in()
        self.assertRedirects(response, reverse('panel_dashboard'))
        self.assertEqual(self.inbox.messages, [])

    def test_a_staff_number_is_not_sent_a_code(self):
        """A code is a weaker key than a password, and this account opens every order."""
        response = self.client.post(reverse('login') + '?next=/uz/boshqaruv/', {'phone': PHONE})
        self.assertContains(response, 'Xodim hisobiga parol bilan kiriladi.')
        self.assertEqual(response.context['staff_door'], '/admin/login/?next=%2Fuz%2Fboshqaruv%2F')
        self.assertEqual(self.inbox.messages, [])

    def test_a_staff_number_cannot_be_signed_up_again(self):
        response = self.ask(door='signup')
        self.assertContains(response, 'Bu raqam roʻyxatdan oʻtgan.')
        self.assertEqual(self.inbox.messages, [])

    def test_the_panel_sends_a_visitor_to_the_staff_door(self):
        target = reverse('panel_orders')
        response = self.client.get(target)
        self.assertRedirects(response, '/admin/login/?next=%s' % target.replace('/', '%2F'),
                             fetch_redirect_response=False)

    def test_the_staff_door_limits_guesses_at_a_name(self):
        for _ in range(8):
            self.assertEqual(self.admin_sign_in('notogri').status_code, 200)
        # The ninth is the right password, and it is still turned away.
        response = self.admin_sign_in()
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])
        self.assertIsNone(self.signed_in())
        self.assertContains(self.client.get(response['Location']), str(RATE_LIMIT_MESSAGE))

    def test_a_name_spelt_in_look_alike_letters_is_the_same_name(self):
        """Django folds them together before it looks the name up, so each
        spelling would otherwise be a fresh eight tries at one account."""
        for _ in range(8):
            self.admin_sign_in('notogri')
        response = self.client.post('/admin/login/', {'username': 'ｅｇasi',
                                                      'password': 'parol12345'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])
        self.assertIsNone(self.signed_in())

    def test_a_superuser_without_the_staff_box_is_staff_all_the_same(self):
        User.objects.filter(pk=self.owner.pk).update(is_staff=False)
        response = self.ask()
        self.assertContains(response, 'Xodim hisobiga parol bilan kiriladi.')
        self.assertEqual(self.inbox.messages, [])

    def test_a_confirmation_left_behind_by_a_signed_out_account_opens_nothing(self):
        """The attempt stays in the session when the account is switched off."""
        self.owner.phone_verified = False
        self.owner.save()
        self.admin_sign_in()
        self.client.get(reverse('verify_phone'))
        code = self.inbox.code
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        self.assertRedirects(self.enter(code), reverse('login'))

    def test_the_staff_door_limits_guesses_from_an_address(self):
        cache.set(_bucket_key('staff_login_address', '127.0.0.1'), 60, 300)
        self.admin_sign_in()
        self.assertIsNone(self.signed_in())

    def test_a_staff_number_nobody_confirmed_is_confirmed_by_a_code(self):
        self.owner.phone_verified = False
        self.owner.save()
        self.admin_sign_in()
        response = self.client.get(reverse('shop'))
        self.assertRedirects(response, reverse('verify_phone'), fetch_redirect_response=False)
        self.client.get(reverse('verify_phone'))
        self.assertEqual(len(self.inbox.messages), 1)
        self.assertRedirects(self.enter(self.inbox.code), reverse('account'))
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.phone_verified)

    def test_an_unconfirmed_staff_account_still_reaches_the_admin(self):
        self.owner.phone_verified = False
        self.owner.save()
        self.admin_sign_in()
        self.assertEqual(self.client.get('/admin/').status_code, 200)


# ---------------------------------------------- what staff change in the admin

class AdminEditTests(CodeCase):
    """The admin's user form is where a number is changed, and the number is the account."""

    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username='egasi', password='parol12345',
                                              phone='+998 90 999 00 01', is_staff=True,
                                              is_superuser=True)
        self.owner.phone_verified = True
        self.owner.save()
        self.customer = customer(name='Dilnoza')
        self.staff_browser = self.client_class()
        self.staff_browser.force_login(self.owner)

    def edit(self, user, **changes):
        """Post the admin's change form for ``user`` with ``changes`` applied."""
        address = reverse('admin:user_user_change', args=[user.pk])
        form = self.staff_browser.get(address).context['adminform'].form
        data = {name: ('' if value is None else value) for name, value in form.initial.items()
                if not isinstance(value, (list, bool)) or value is True}
        data = {k: ('on' if v is True else v) for k, v in data.items()}
        for name in ('date_joined', 'last_login'):
            stamp = form.initial.get(name)
            data.pop(name, None)
            if stamp:
                data[name + '_0'] = stamp.strftime('%Y-%m-%d')
                data[name + '_1'] = stamp.strftime('%H:%M:%S')
        data.update(changes)
        response = self.staff_browser.post(address, data)
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None)
                         and response.context['adminform'].form.errors)
        user.refresh_from_db()

    def test_a_new_number_takes_the_username_with_it_and_ends_every_session(self):
        enter_by_code(self.client, self.inbox)
        self.assertIsNotNone(self.signed_in())
        self.edit(self.customer, phone=OTHER)
        self.assertEqual((self.customer.phone, self.customer.username), (OTHER, '+998901112244'))
        self.assertEqual(self.customer.first_name, 'Dilnoza')
        # The browser that signed in with the old number is no longer the account.
        self.assertRedirects(self.client.get(reverse('account')),
                             reverse('login') + '?next=' + reverse('account'))

    def test_the_old_number_is_free_for_whoever_holds_it_next(self):
        self.edit(self.customer, phone=OTHER)
        stranger = self.client_class()
        response = enter_by_code(stranger, self.inbox, PHONE, door='signup')
        self.assertRedirects(response, reverse('account'))
        self.assertEqual(User.objects.filter(phone=PHONE).exclude(pk=self.customer.pk).count(), 1)

    def test_an_edit_that_leaves_the_number_alone_ends_nothing(self):
        enter_by_code(self.client, self.inbox)
        self.edit(self.customer, first_name='Dilnoza Karimova')
        self.assertEqual(self.client.get(reverse('account')).status_code, 200)

    def test_a_customer_made_staff_does_not_keep_a_session_opened_by_a_code(self):
        enter_by_code(self.client, self.inbox)
        self.edit(self.customer, is_staff='on')
        self.assertTrue(self.customer.is_staff)
        response = self.client.get(reverse('panel_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/admin/login/'))

    def test_a_name_somebody_else_holds_does_not_stop_a_sign_up(self):
        """A staff account named like a number, or a row edited by hand."""
        User.objects.filter(pk=self.owner.pk).update(username='+998901112255')
        response = enter_by_code(self.client, self.inbox, '+998 90 111 22 55', door='signup')
        self.assertRedirects(response, reverse('account'))
        made = User.objects.get(phone='+998 90 111 22 55')
        self.assertTrue(made.username.startswith('+998901112255.'))


# ------------------------------------------------- rows from before the change

class RowsFromBeforeTests(CodeCase):
    """Accounts made while a sign-up wrote its row before the code was entered."""

    def leftover(self):
        """A sign-up that was never finished: a row, a name, no confirmation."""
        user = User.objects.create_user(username='chala', password='parol12345',
                                        phone=PHONE, first_name='Begona')
        return user

    def test_an_unfinished_sign_up_is_not_an_account_at_the_sign_in_door(self):
        self.leftover()
        response = self.ask()
        self.assertContains(response, 'Bu raqam roʻyxatdan oʻtmagan.')
        self.assertEqual(self.inbox.messages, [])

    def test_its_number_signs_up_and_takes_the_row_over(self):
        row = self.leftover()
        response = enter_by_code(self.client, self.inbox, door='signup')
        self.assertRedirects(response, reverse('account'))
        user = User.objects.get()
        self.assertEqual(user.pk, row.pk)
        self.assertTrue(user.phone_verified)
        self.assertEqual(user.username, '+998901112233')
        self.assertFalse(user.has_usable_password())
        # Whoever typed the name never showed they hold the number.
        self.assertEqual(user.first_name, '')
        self.assertEqual(user.terms_version, legal.accepted_versions()['terms_version'])


class MigrationTests(TestCase):
    """0006 turns each customer's username into their number and drops the password."""

    def run_migration(self):
        module = importlib.import_module('user.migrations.0006_customers_sign_in_by_code')
        module.forwards(apps, None)

    def old_account(self, username, phone, **fields):
        return User.objects.create_user(username=username, password='parol12345',
                                        phone=phone, **fields)

    def test_a_customer_gets_their_number_and_no_password(self):
        user = self.old_account('mijoz', PHONE, first_name='Dilnoza')
        self.run_migration()
        user.refresh_from_db()
        self.assertEqual(user.username, '+998901112233')
        self.assertFalse(user.has_usable_password())
        self.assertEqual((user.phone, user.first_name), (PHONE, 'Dilnoza'))

    def test_a_session_opened_with_the_old_password_ends(self):
        user = self.old_account('mijoz', PHONE)
        user.phone_verified = True
        user.save()
        self.client.force_login(user)
        self.run_migration()
        self.assertRedirects(self.client.get(reverse('account')),
                             reverse('login') + '?next=' + reverse('account'))

    def test_staff_are_left_exactly_as_they_were(self):
        staff = self.old_account('xodim', PHONE, is_staff=True)
        owner = self.old_account('egasi', OTHER, is_superuser=True)
        before = {u.pk: (u.username, u.password) for u in (staff, owner)}
        self.run_migration()
        for user in User.objects.all():
            self.assertEqual((user.username, user.password), before[user.pk])
        self.assertTrue(self.client.login(username='xodim', password='parol12345'))

    def test_customers_named_like_each_others_numbers_do_not_collide(self):
        first = self.old_account('+998901112244', PHONE)
        second = self.old_account('+998901112233', OTHER)
        self.run_migration()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.username, second.username), ('+998901112233', '+998901112244'))

    def test_a_staff_name_like_a_customers_number_stops_it_before_any_change(self):
        self.old_account('+998901112233', OTHER, is_staff=True)
        customer_row = self.old_account('mijoz', PHONE)
        with self.assertRaisesMessage(RuntimeError, '+998901112233'):
            self.run_migration()
        customer_row.refresh_from_db()
        self.assertEqual(customer_row.username, 'mijoz')
        self.assertTrue(customer_row.has_usable_password())

    def test_a_number_saved_without_its_spaces_is_written_the_usual_way(self):
        """Or nobody could sign in to it: the door looks a number up in one form."""
        user = self.old_account('mijoz', PHONE)
        User.objects.filter(pk=user.pk).update(phone='+998901112233')
        self.run_migration()
        user.refresh_from_db()
        self.assertEqual((user.phone, user.username), (PHONE, '+998901112233'))

    def test_one_number_held_twice_stops_it_before_any_change(self):
        first = self.old_account('bir', PHONE)
        second = self.old_account('ikki', OTHER)
        User.objects.filter(pk=second.pk).update(phone='+998901112233')
        with self.assertRaisesMessage(RuntimeError, 'same phone number'):
            self.run_migration()
        first.refresh_from_db()
        self.assertEqual(first.username, 'bir')

    def test_a_phone_that_is_not_a_number_stops_it_before_any_change(self):
        user = self.old_account('mijoz', PHONE)
        odd = self.old_account('galati', OTHER)
        User.objects.filter(pk=odd.pk).update(phone='yoq')
        with self.assertRaisesMessage(RuntimeError, 'ids [%d]' % odd.pk):
            self.run_migration()
        user.refresh_from_db()
        self.assertEqual(user.username, 'mijoz')

    def test_nobody_is_deleted(self):
        self.old_account('mijoz', PHONE)
        self.old_account('chala', OTHER)
        self.run_migration()
        self.assertEqual(User.objects.count(), 2)


# ------------------------------------------------------- the guest's cart

class CartComesAlongTests(CodeCase):
    """Whatever a guest put in the cart is there after either door."""

    def setUp(self):
        super().setUp()
        self.product, self.variant = make_product('Savatdagi', stock=5)
        self.client.post(reverse('cart_add', kwargs={'product_id': self.product.pk}),
                         {'colour': self.variant.colour_id, 'size': self.variant.size_id,
                          'quantity': 2})

    def lines(self, user):
        cart = Cart.objects.get(user=user, status=True)
        return {line.variant_id: line.quantity for line in cart.cart_items.all()}

    def test_after_signing_up(self):
        enter_by_code(self.client, self.inbox, door='signup')
        self.assertEqual(self.lines(User.objects.get()), {self.variant.pk: 2})
        self.assertFalse(Cart.objects.filter(user__isnull=True).exists())

    def test_after_signing_in(self):
        user = customer()
        enter_by_code(self.client, self.inbox)
        self.assertEqual(self.lines(user), {self.variant.pk: 2})
        self.assertFalse(Cart.objects.filter(user__isnull=True).exists())


# ------------------------------------------------------- what the owner is told

class OwnerIsToldTests(TestCase):
    """The notifications: the new one, and no username left in the old ones."""

    def test_the_ceiling_is_an_event_of_its_own(self):
        with (mock.patch.object(telegram, 'deliver') as deliver,
              self.captureOnCommitCallbacks(execute=True)):
            telegram.notify_code_ceiling(150)
        event, text, data = deliver.call_args.args
        self.assertEqual(event, 'signin.ceiling')
        self.assertIn('150 ta kod', text)
        self.assertEqual(data, {'signin': {'codes_sent': 150, 'window_minutes': 60}})

    def test_a_message_names_the_customer_without_a_username(self):
        from core.models import Msg
        user = customer()
        msg = Msg(user=user, phone_num=user.phone, topic='Savol', msg_text='Salom')
        with (mock.patch.object(telegram, 'deliver') as deliver,
              self.captureOnCommitCallbacks(execute=True)):
            telegram.notify_message(msg)
        event, text, data = deliver.call_args.args
        self.assertNotIn('username', data['message'])
        self.assertNotIn('@', text)
        self.assertIn('Xaridor', text)


# ------------------------------------------------------- the documents

class DocumentsTests(TestCase):
    """The two documents say what the site now does, in each language."""

    NO_PASSWORD = {'uz': 'parol ham yoʻq', 'ru': 'пароля у аккаунта нет', 'en': 'no password'}
    REVIEW_WORD = {'uz': '«Xaridor»', 'ru': '«Покупатель»', 'en': '“Customer”'}
    OLD = {'uz': ('Parolingizni', 'foydalanuvchi nomingiz', 'parolni oʻzgartiring'),
           'ru': ('Не сообщайте пароль', 'смените пароль', 'восстановление пароля'),
           'en': ('Keep your password', 'change your password', 'resetting your password')}

    def page(self, doc, lang):
        return self.client.get('/%s/%s/' % (lang, doc)).content.decode()

    def test_the_privacy_policy_says_there_is_no_password(self):
        for lang in LANGS:
            with self.subTest(lang=lang):
                self.assertIn(self.NO_PASSWORD[lang], self.page('privacy', lang))

    def test_the_terms_say_what_a_review_shows(self):
        for lang in LANGS:
            with self.subTest(lang=lang):
                self.assertIn(self.REVIEW_WORD[lang], self.page('terms', lang))

    def test_nothing_is_left_of_the_password_clauses(self):
        for lang in LANGS:
            text = self.page('privacy', lang) + self.page('terms', lang)
            for phrase in self.OLD[lang]:
                with self.subTest(lang=lang, phrase=phrase):
                    self.assertNotIn(phrase, text)

    def test_the_documents_are_still_version_one(self):
        """Edited in place: the shop has not opened, so nobody agreed to the old wording."""
        self.assertEqual(set(legal.accepted_versions().values()), {'1.0'})
