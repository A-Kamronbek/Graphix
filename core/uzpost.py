"""Uzpost's partner API: districts, shipments, labels and statuses.

Built like :mod:`core.sms` and for the same reason (§17 #17): a module logger,
everything caught, every failure logged, nothing raised. Uzpost being down or
refusing a call degrades a feature, the panel's Uzpost section, and never
breaks a page. Each call answers with an :class:`Answer` the caller reads,
rather than a value that might be ``None`` for three different reasons.

This module knows Uzpost's addresses and the shape of its answers and nothing
about the shop: which order becomes which shipment is
``payment.shipments``'s business. Nothing here touches the database.

Uzpost's documentation describes no answer, so the shapes read here are the
ones recorded from real calls on 2026-10-18 (§9 Phase 22). The tests replay
those answers; no test calls Uzpost.

The owner's login and password (``UZPOST_LOGIN``, ``UZPOST_PASSWORD``) are
turned into a token that lasts a day. It is kept in the cache for 23 hours
and fetched again on a 401, and it lives in ``.env`` and the cache only. With
either credential blank nothing is called at all (§17 #93).
"""
import logging
from collections import namedtuple
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

#: There is no test environment: this is the only address Uzpost has.
BASE = "https://prodapi.pochta.uz/api/"

#: Seconds to connect and seconds to wait for an answer. A panel request that
#: makes a shipment calls Uzpost up to three times (a token, the price, the
#: shipment), and the three together stay under the 60 seconds gunicorn and
#: nginx give a request.
TIMEOUT = (5, 12)

_TOKEN_KEY = "uzpost_token"
#: Uzpost's token lasts 24 hours; one kept for 23 is never sent stale.
_TOKEN_TTL = 23 * 60 * 60


class Answer(namedtuple('Answer', 'ok data error unknown')):
    """What a call came back with.

    ``ok`` and ``data`` when it worked. ``error`` is a short text when it did
    not: Uzpost's own message where it gave one, for staff to read. ``unknown``
    is true when the request may have reached Uzpost and its answer did not
    reach us, so whether it took effect cannot be said.
    """

    __slots__ = ()


def _failed(error, unknown=False):
    """An answer for a call that did not work."""
    return Answer(False, None, error, unknown)


def configured():
    """Are the owner's credentials present? Blank is a supported state."""
    return bool(settings.UZPOST_LOGIN and settings.UZPOST_PASSWORD)


#: Characters Uzpost does not keep, and what is sent in their place. It
#: stored ``Qoʻqon`` as ``Qo?qon`` (§17 #384), so the apostrophes of Uzbek
#: Latin go as the plain one Uzpost's own names use, and the rest of the
#: typography as its plainest form.
_PLAIN = str.maketrans({
    'ʻ': "'", 'ʼ': "'", '‘': "'", '’': "'", '`': "'", '´': "'",
    '«': '"', '»': '"', '“': '"', '”': '"', '„': '"',
    '–': '-', '—': '-', '\u00a0': ' ', '\u202f': ' ',
})


def plain(text):
    """``text`` as it should be sent to Uzpost, on one line."""
    return ' '.join(str(text or '').translate(_PLAIN).split())


# ------------------------------------------------------------------ transport

def _cache_get(key):
    """Read the cache, or None when it cannot be read. A cache outage costs a login."""
    try:
        return cache.get(key)
    except Exception:
        logger.warning("Uzpost: the cache could not be read; logging in afresh")
        return None


def _cache_set(key, value, ttl):
    """Write the cache, or carry on without it."""
    try:
        cache.set(key, value, ttl)
    except Exception:
        logger.warning("Uzpost: the cache could not be written")


def _login():
    """Exchange the owner's login for a token. Returns the token or None."""
    try:
        response = requests.post(
            BASE + "v1/customer/authenticate",
            json={"username": settings.UZPOST_LOGIN,
                  "password": settings.UZPOST_PASSWORD,
                  "remember_me": True},
            timeout=TIMEOUT,
        )
        if response.status_code >= 400:
            # Never the body: it could echo what was sent.
            logger.error("Uzpost refused the login (%s)", response.status_code)
            return None
        token = response.json()["data"]["id_token"]
    except requests.RequestException as e:
        logger.error("Uzpost login request error: %s", e)
        return None
    except Exception:
        logger.exception("Uzpost login answered in a shape it has never used")
        return None
    _cache_set(_TOKEN_KEY, token, _TOKEN_TTL)
    return token


def _token(fresh=False):
    """The token to send, from the cache unless ``fresh`` is asked for."""
    token = None if fresh else _cache_get(_TOKEN_KEY)
    return token or _login()


def _message(body, response):
    """Uzpost's own words for a refusal, or the HTTP status when it gave none."""
    if isinstance(body, dict):
        for key in ('message', 'error', 'detail'):
            if isinstance(body.get(key), str) and body[key].strip():
                return body[key].strip()[:300]
    return f"HTTP {response.status_code}"


def _call(method, path, *, params=None, body=None, writes=False):
    """Send one request with the token, once more on a 401. Returns an Answer.

    ``writes`` says the call changes something at Uzpost: if its answer is
    lost on the way back, the Answer says the outcome is unknown rather than
    that it failed, so nobody is told to press the button again blindly.
    """
    if not configured():
        return _failed("not configured")

    def send(token):
        return requests.request(
            method, BASE + path, params=params, json=body,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=TIMEOUT,
        )

    try:
        token = _token()
        if token is None:
            return _failed("login failed")
        response = send(token)
        if response.status_code == 401:
            token = _token(fresh=True)
            if token is None:
                return _failed("login failed")
            response = send(token)
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if response.status_code >= 400 or (isinstance(payload, dict)
                                           and payload.get('status') == 'error'):
            error = _message(payload, response)
            logger.error("Uzpost %s %s refused (%s): %s",
                         method, path, response.status_code, error)
            return _failed(error)
        data = payload.get('data') if isinstance(payload, dict) else None
        return Answer(True, data, '', False)
    except requests.ConnectionError as e:
        # Refused or unreachable before anything was sent: nothing happened.
        # A connection dropped after sending reads the same, so a write still
        # says it cannot be sure.
        logger.error("Uzpost %s %s: no connection: %s", method, path, e)
        return _failed("no connection", unknown=writes)
    except requests.Timeout as e:
        logger.error("Uzpost %s %s timed out: %s", method, path, e)
        return _failed("timeout", unknown=writes)
    except requests.RequestException as e:
        logger.error("Uzpost %s %s request error: %s", method, path, e)
        return _failed("request error", unknown=writes)
    except Exception:
        logger.exception("Uzpost %s %s failed unexpectedly", method, path)
        return _failed("unexpected answer", unknown=writes)


# ------------------------------------------------------------------ reading answers

def shipment_facts(data):
    """The few things the shop keeps from a shipment's record at Uzpost.

    Read from the answer of the create call and of the detail call, which
    share a shape: ``id``; ``order_number``, which is also the barcode;
    ``status`` and when it changed; and the office Uzpost assigned, whose
    index is the recipient's postcode and whose name Uzpost writes in Russian.
    Returns None for anything without an id and a number.
    """
    if not isinstance(data, dict) or not data.get('id') or not data.get('order_number'):
        return None
    recipient = data.get('recipient_data') or {}
    postcode = recipient.get('postcode') or {}
    office = data.get('to_warehouse') or {}
    return {
        'id': int(data['id']),
        'number': str(data['order_number'])[:40],
        'status': str(data.get('status') or '')[:40],
        'status_at': parse_datetime(str(data.get('last_status_date') or '')) or None,
        'office_index': str(postcode.get('name') or '')[:10],
        'office_name': str(office.get('name') or '')[:200],
    }


# ------------------------------------------------------------------ the calls

def jurisdictions(level, parent_id=None):
    """Every jurisdiction on one level: 2 is the regions, 3 the districts.

    Uzpost ignores ``page`` and ``size`` here and answers the whole level.
    The documentation's levels are wrong; these are the ones that work.
    """
    params = {'page': 0, 'size': 1000, 'levelId': level, 'search': ''}
    if parent_id:
        params['parentId'] = parent_id
    answer = _call('GET', 'v2/jurisdiction/choose/list', params=params)
    if answer.ok and not isinstance(answer.data, list):
        return _failed("unexpected answer")
    return answer


def transportation_type(service_id, to_jurisdiction):
    """Whether Uzpost carries this service on this route by land or by air.

    The documentation says air when one end is in Xorazm or Qoraqalpogʻiston,
    and the price call disagrees, so the price call is asked and its answer
    is what the shipment is created with. ``data`` is ``terrestrial`` or
    ``air``.
    """
    answer = _call('GET', 'v2/customer/packages/prices/starting_from', params={
        'dimensions.weight': settings.UZPOST_ITEM_KG,
        'service_type': service_id,
        'page': 0, 'size': 20,
        'fromJurisdictionId': settings.UZPOST_SENDER_JURISDICTION,
        'toJurisdictionId': to_jurisdiction,
    })
    if not answer.ok:
        return answer
    try:
        kind = answer.data['list'][0]['transportation_type']
    except (KeyError, IndexError, TypeError):
        return _failed("no price for this route")
    if kind not in ('terrestrial', 'air'):
        return _failed(f"unknown transportation type {kind!r}")
    return Answer(True, kind, '', False)


def create_order(payload):
    """Create one shipment. ``data`` is :func:`shipment_facts` of the answer."""
    answer = _call('POST', 'v1/customer/order', body=payload, writes=True)
    if not answer.ok:
        return answer
    facts = shipment_facts(answer.data)
    if facts is None:
        logger.error("Uzpost created a shipment and answered without its id or number")
        return _failed("unexpected answer", unknown=True)
    return Answer(True, facts, '', False)


def details(uzpost_id):
    """One shipment as Uzpost has it now. ``data`` is :func:`shipment_facts`."""
    answer = _call('GET', f'v1/customer/order/{int(uzpost_id)}/mobile')
    if not answer.ok:
        return answer
    facts = shipment_facts(answer.data)
    if facts is None:
        return _failed("unexpected answer")
    return Answer(True, facts, '', False)


def label(uzpost_id):
    """A fresh link to the shipment's label, a PDF that opens without the token.

    Only an https link on Uzpost's own domain is passed on: the panel sends
    staff straight to it.
    """
    answer = _call('GET', 'v2/customer/cn22_shipping_label', params={'ids': int(uzpost_id)})
    if not answer.ok:
        return answer
    link = answer.data if isinstance(answer.data, str) else ''
    parts = urlsplit(link)
    host = (parts.hostname or '').lower()
    if parts.scheme != 'https' or not (host == 'pochta.uz' or host.endswith('.pochta.uz')):
        logger.error("Uzpost answered a label request with %r", link[:200])
        return _failed("unexpected answer")
    return Answer(True, link, '', False)


def cancel(number):
    """Ask Uzpost to cancel a shipment. It agrees only while the shipment is new."""
    return _call('PUT', 'v1/customer/order/cancel', params={'barcode': number}, writes=True)
