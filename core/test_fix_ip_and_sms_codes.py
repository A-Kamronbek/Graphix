"""The rate limiter believes the address nginx saw, and SMS codes come from secrets.

Two small holes, found by reading the code rather than by anything breaking.

client_ip read the first X-Forwarded-For hop. nginx appends the address of
whoever connected to it to the header the request arrived with, so the first
hop is the client's own claim: a new invented address with each request
stepped around every IP-keyed limit on the site. It reads the last hop now.

The signup and password-reset codes were drawn with random, which is a
predictable generator. They are drawn with secrets now.
"""
from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase

from core.ratelimit import client_ip, is_rate_limited
from user import otp, password_reset


def request_from(forwarded_for=None, remote_addr='10.0.0.1'):
    """A request as gunicorn hands it over, with the given proxy header."""
    extra = {'REMOTE_ADDR': remote_addr}
    if forwarded_for is not None:
        extra['HTTP_X_FORWARDED_FOR'] = forwarded_for
    return RequestFactory().get('/', **extra)


class ClientIpTests(SimpleTestCase):

    def test_the_hop_nginx_appended_is_the_one_believed(self):
        request = request_from('203.0.113.9, 198.51.100.7')
        self.assertEqual(client_ip(request), '198.51.100.7')

    def test_a_single_hop_is_read_as_it_is(self):
        self.assertEqual(client_ip(request_from('198.51.100.7')), '198.51.100.7')

    def test_spaces_around_a_hop_are_ignored(self):
        request = request_from('203.0.113.9 ,  198.51.100.7 ')
        self.assertEqual(client_ip(request), '198.51.100.7')

    def test_without_the_header_the_socket_address_is_used(self):
        self.assertEqual(client_ip(request_from(remote_addr='192.0.2.4')), '192.0.2.4')

    def test_an_empty_header_falls_back_to_the_socket_address(self):
        for header in ('', ' , '):
            with self.subTest(header=header):
                request = request_from(header, remote_addr='192.0.2.4')
                self.assertEqual(client_ip(request), '192.0.2.4')

    def test_with_nothing_to_go_on_the_answer_is_still_a_string(self):
        self.assertEqual(client_ip(request_from(remote_addr='')), 'unknown')


class SpoofedAddressTests(SimpleTestCase):
    """An invented first hop no longer buys a fresh counter."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_a_new_claimed_address_per_request_is_still_one_client(self):
        limited = [
            is_rate_limited(request_from(f'203.0.113.{n}, 198.51.100.7'), 'test_spoof', 2, 60)
            for n in range(1, 5)
        ]
        self.assertEqual(limited, [False, False, True, True])

    def test_two_real_clients_are_still_counted_apart(self):
        first, second = request_from('198.51.100.7'), request_from('198.51.100.8')
        self.assertFalse(is_rate_limited(first, 'test_apart', 2, 60))
        self.assertFalse(is_rate_limited(first, 'test_apart', 2, 60))
        self.assertTrue(is_rate_limited(first, 'test_apart', 2, 60))
        self.assertFalse(is_rate_limited(second, 'test_apart', 2, 60))


class SmsCodeTests(SimpleTestCase):
    """Both codes are drawn from secrets and keep their six digits."""

    def fake_request(self):
        user = SimpleNamespace(id=1, phone='+998901234567')
        return SimpleNamespace(session={}, user=user)

    def test_the_signup_code_is_drawn_from_secrets_and_zero_padded(self):
        request = self.fake_request()
        with (mock.patch.object(otp, 'send_sms') as send,
              mock.patch.object(otp.secrets, 'randbelow', return_value=42) as draw):
            code = otp.generate(request, reset_expiry=True)
        draw.assert_called_once_with(1000000)
        self.assertEqual(code, '000042')
        self.assertEqual(request.session['otp_code'], '000042')
        self.assertIn('000042', send.call_args.args[1])

    def test_the_reset_code_is_drawn_from_secrets_and_zero_padded(self):
        request = self.fake_request()
        with (mock.patch.object(password_reset, 'send_sms') as send,
              mock.patch.object(password_reset.secrets, 'randbelow', return_value=7) as draw):
            code = password_reset.issue_code(request, request.user)
        draw.assert_called_once_with(1000000)
        self.assertEqual(code, '000007')
        self.assertEqual(request.session['pwreset_code'], '000007')
        self.assertIn('000007', send.call_args.args[1])

    def test_neither_module_imports_random_any_more(self):
        self.assertFalse(hasattr(otp, 'random'))
        self.assertFalse(hasattr(password_reset, 'random'))
