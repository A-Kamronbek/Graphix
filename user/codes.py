"""The sign-in code: one flow for signing in, signing up and confirming a number.

A customer has no password (§17 #309). A six-digit code sent by SMS is the only
key to an account, so everything that keeps a guess, a script or a second
browser from getting past it lives here, in one place:

* the code is drawn with ``secrets`` and kept in the session only as a keyed
  hash, bound to the number and to what it was asked for, so a code for one
  number or one purpose opens nothing else;
* it is compared in constant time and never logged;
* wrong tries are counted against the number in the cache as well as in the
  session, so opening a new browser buys no new tries;
* codes are limited per number, per address and across the whole site, because
  every one costs an SMS and a script can ask for thousands;
* the counters live in the cache, and with the cache down no code is sent at
  all. Everywhere else a limit that cannot be read lets the request through;
  here that would mean codes with no limit on them.

Two things these limits cannot stop, and are accepted: somebody who knows a
number can have codes sent to it until its limit is reached, which keeps its
owner out for up to an hour; and a number the operator gives to a new person
opens the account its last owner made (§12 risk #29).

Each counter is read before the code is sent and moved after, so that a code
the gateway refused costs the customer nothing. Requests that arrive in the
same instant can therefore each be let through before any of them is counted:
with three workers, a figure here can be passed by two.

The attempt lives in the visitor's session from the moment the code is asked
for until it is entered, so nothing is written to the database for a number
that never confirms. One window covers the whole attempt: a resend sends a new
code and keeps the deadline.
"""
import hmac
import logging
import secrets
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from django.utils.crypto import salted_hmac

from core import telegram
from core.ratelimit import is_currently_limited, is_rate_limited
from core.sms import send_sms

logger = logging.getLogger(__name__)

#: What a code is asked for. CONFIRM is a signed-in account whose number was
#: never confirmed, which since Phase 15 means staff made in the Django admin.
SIGN_IN, SIGN_UP, CONFIRM = 'signin', 'signup', 'confirm'

# Five minutes for the whole attempt, a minute between sends, seven wrong tries.
TTL_SECONDS = 5 * 60
RESEND_COOLDOWN = 60
MAX_ATTEMPTS = 7

#: Wrong tries against one number in an hour, from every session together.
#: Seven a code would otherwise be seven with each new code, all day.
WRONG_HOUR = 20

#: How many codes may be sent: to one number in ten minutes and in an hour,
#: from one address in an hour, and by the whole site in an hour. The windows
#: are written out at each call, where a test reads them and holds every one
#: to ``core.ratelimit.MAX_WINDOW``.
NUMBER_SHORT = 4
NUMBER_HOUR = 8
ADDRESS_HOUR = 50
SITE_HOUR = 150

#: What start() and resend() answer.
SENT, LIMITED, CEILING, UNSENT = 'sent', 'limited', 'ceiling', 'unsent'
#: What check() answers.
OK, WRONG, SPENT = 'ok', 'wrong', 'spent'

SESSION_KEY = 'signin_code'

#: Plain ASCII, so each is one GSM-7 SMS, and exactly as Eskiz moderated them:
#: a body Eskiz has not approved is not sent (§17 #104, #292).
MESSAGES = {
    SIGN_IN: "GRAPHIX saytiga kirish uchun kodingiz: {code}",
    SIGN_UP: "GRAPHIX saytida ro'yxatdan o'tish uchun kodingiz: {code}",
}
MESSAGES[CONFIRM] = MESSAGES[SIGN_UP]


def _digest(purpose, phone, code):
    """The keyed hash kept in place of the code."""
    return salted_hmac('user.codes', '%s:%s:%s' % (purpose, phone, code)).hexdigest()


def _alert_once():
    """Tell the owner the site-wide ceiling was reached, once per hour."""
    try:
        first = cache.add('code_site_alerted', 1, 3600)
    except Exception:
        first = False
    if first:
        telegram.notify_code_ceiling(SITE_HOUR)


def _counting():
    """Can the limits be kept? They live in the cache, and it may be down."""
    try:
        cache.set('code_counting', 1, 60)
        return cache.get('code_counting') == 1
    except Exception:
        logger.error("The cache cannot be reached, so no sign-in code is sent: "
                     "its limits could not be kept")
        return False


def _guessed_out(request, phone):
    """Has ``phone`` had as many wrong codes as it may, from all sessions together?"""
    return (is_currently_limited(request, 'code_wrong', MAX_ATTEMPTS, ident=phone)
            or is_currently_limited(request, 'code_wrong_hour', WRONG_HOUR, ident=phone))


def _refusal(request, phone):
    """LIMITED or CEILING when another code may not be sent to ``phone``, else None."""
    if not _counting():
        return CEILING
    if is_currently_limited(request, 'code_site', SITE_HOUR, ident='site'):
        _alert_once()
        return CEILING
    if (is_currently_limited(request, 'code_number_short', NUMBER_SHORT, ident=phone)
            or is_currently_limited(request, 'code_number_hour', NUMBER_HOUR, ident=phone)
            or is_currently_limited(request, 'code_address', ADDRESS_HOUR)
            or _guessed_out(request, phone)):
        return LIMITED
    return None


def _send(request, purpose, phone):
    """Draw a code and send it. Returns ``(outcome, digest)``.

    A code that could not be sent is not counted: it cost nothing, and an
    outage at the gateway should not use up a customer's tries.
    """
    refusal = _refusal(request, phone)
    if refusal:
        return refusal, None
    code = '%06d' % secrets.randbelow(1000000)
    if not send_sms(phone, MESSAGES[purpose].format(code=code)):
        return UNSENT, None
    is_rate_limited(request, 'code_number_short', NUMBER_SHORT, 600, ident=phone)
    is_rate_limited(request, 'code_number_hour', NUMBER_HOUR, 3600, ident=phone)
    is_rate_limited(request, 'code_address', ADDRESS_HOUR, 3600)
    is_rate_limited(request, 'code_site', SITE_HOUR, 3600, ident='site')
    return SENT, _digest(purpose, phone, code)


def start(request, purpose, phone, **keep):
    """Send ``phone`` a code and open an attempt in the session.

    ``keep`` is carried with the attempt to the moment the code is entered:
    where to go afterwards, and for a sign-up the document versions agreed to.
    Returns SENT, or the reason nothing was sent; the session is left as it
    was unless a code went out.
    """
    outcome, digest = _send(request, purpose, phone)
    if outcome != SENT:
        return outcome
    now = timezone.now()
    request.session[SESSION_KEY] = {
        **keep,
        'purpose': purpose,
        'phone': phone,
        'digest': digest,
        'expires_at': (now + timedelta(seconds=TTL_SECONDS)).isoformat(),
        'sent_at': now.isoformat(),
        'attempts': 0,
    }
    return SENT


def resend(request):
    """Send a new code for the open attempt. The deadline does not move."""
    state = get(request)
    if state is None:
        return UNSENT
    outcome, digest = _send(request, state['purpose'], state['phone'])
    if outcome != SENT:
        return outcome
    state.update(digest=digest, sent_at=timezone.now().isoformat(), attempts=0)
    request.session[SESSION_KEY] = state
    return SENT


def get(request):
    """The open attempt, or None. An expired one is still returned."""
    state = request.session.get(SESSION_KEY)
    return state if isinstance(state, dict) and state.get('digest') else None


def clear(request):
    """End the attempt."""
    request.session.pop(SESSION_KEY, None)


def _since(raw):
    """Seconds since an ISO timestamp from the session; None if it is unreadable."""
    try:
        return (timezone.now() - timezone.datetime.fromisoformat(raw)).total_seconds()
    except (TypeError, ValueError):
        return None


def is_expired(state):
    """Has the attempt's window passed? Unreadable counts as passed."""
    elapsed = _since(state.get('expires_at'))
    return elapsed is None or elapsed > 0


def ttl_remaining(state):
    """Seconds left in the attempt's window."""
    elapsed = _since(state.get('expires_at'))
    return 0 if elapsed is None else max(0, int(-elapsed))


def resend_cooldown(state):
    """Seconds until another code may be asked for."""
    elapsed = _since(state.get('sent_at'))
    return 0 if elapsed is None else max(0, int(RESEND_COOLDOWN - elapsed))


def check(request, code):
    """Compare ``code`` with the open attempt's. Returns OK, WRONG or SPENT.

    SPENT ends the attempt: seven wrong tries, here or from any other session
    guessing at the same number. The session keeps its own count as well, so
    a code still has its seven tries and no more while the cache is down. The
    caller clears the attempt after OK, once it has acted on it.
    """
    state = get(request)
    if state is None or is_expired(state):
        return SPENT
    phone = state['phone']
    if _guessed_out(request, phone):
        clear(request)
        return SPENT
    if hmac.compare_digest(state['digest'], _digest(state['purpose'], phone, str(code))):
        return OK
    is_rate_limited(request, 'code_wrong', MAX_ATTEMPTS, 300, ident=phone)
    is_rate_limited(request, 'code_wrong_hour', WRONG_HOUR, 3600, ident=phone)
    state['attempts'] = state.get('attempts', 0) + 1
    request.session[SESSION_KEY] = state
    if state['attempts'] >= MAX_ATTEMPTS or _guessed_out(request, phone):
        clear(request)
        return SPENT
    return WRONG
