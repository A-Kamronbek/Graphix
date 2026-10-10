"""Sign-in, sign-up, the code page and the account pages.

A customer signs in and signs up with a phone number and a code sent to it by
SMS; there is no username and no password to ask for (§17 #309). Both doors
lead to one code page, and the rules a code is held to are in
:mod:`user.codes`. An account is made only once the code is right, so an
abandoned sign-up leaves nothing behind.

Staff keep a username and a password at ``/admin/``, so an SMS outage cannot
lock the owner out, and that is their only door: a staff number is not sent a
code here, because a code is a weaker key than a password and a staff session
opens every customer's orders. A staff account whose number was never
confirmed is sent to the same code page while signed in (§17 #227).
"""
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from core import legal
from core.ratelimit import RATE_LIMIT_MESSAGE, is_currently_limited, is_rate_limited
from payment.models import Order

from . import codes, services
from .forms import OTPForm, PhoneForm, ProfileForm, SignupForm
from .models import User

BACKEND = 'django.contrib.auth.backends.ModelBackend'


def _safe_next(request):
    """Where the visitor was going, if it is a page of this site.

    A path and nothing else. A bare word would pass the host check, since it
    names no host, and ``redirect()`` would then read it as the name of a
    view and fail on it after the code had been spent.
    """
    target = request.GET.get('next') or request.POST.get('next') or ''
    if (target.startswith('/') and not target.startswith('//')
            and url_has_allowed_host_and_scheme(
                target, allowed_hosts={request.get_host()}, require_https=request.is_secure())):
        return target
    return ''


def _refused(outcome):
    """What to tell someone a code was not sent to."""
    if outcome == codes.UNSENT:
        return _("Kod yuborilmadi. Birozdan soʻng qayta urinib koʻring.")
    if outcome == codes.CEILING:
        return _("Hozir kod yubora olmaymiz. Birozdan soʻng qayta urinib koʻring.")
    return RATE_LIMIT_MESSAGE


def _reasons():
    """Why a visitor was sent back to a door, keyed by ``?reason=``.

    Kept in the URL rather than as a flash message: the code page signs a
    staff account out when its attempt ends, and that empties the session.
    """
    return {
        'expired': _("Kod muddati tugadi. Iltimos, qaytadan urinib koʻring."),
        'cancelled': _("Roʻyxatdan oʻtish bekor qilindi."),
    }


def _door(state, reason=None):
    """Back to where the attempt began, with why."""
    name = 'signup' if state and state.get('purpose') == codes.SIGN_UP else 'login'
    target = reverse(name)
    return redirect('%s?%s' % (target, urlencode({'reason': reason})) if reason else target)


def _other_door(name, phone, next_url):
    """The other door's address, carrying the number and the way back."""
    query = {'phone': phone}
    if next_url:
        query['next'] = next_url
    return '%s?%s' % (reverse(name), urlencode(query))


def _staff_door(next_url):
    """Where staff sign in: the Django admin's form, then on to the panel."""
    return '%s?%s' % (reverse('admin:login'),
                      urlencode({'next': next_url or reverse('panel_dashboard')}))


def _ask(request, form, purpose, template):
    """Both doors: check the number, send it a code, go to the code page.

    Sign-in wants a registered number and sign-up an unregistered one, and
    each sends the other kind to the other door. The site says which it is
    (§17 #327). That lets a stranger learn whether a number has an account,
    and the limit on asking is the brake on it.
    """
    context = {'form': form, 'notice': _reasons().get(request.GET.get('reason')),
               'next': _safe_next(request)}
    if request.method == 'POST':
        if is_rate_limited(request, 'code_ask_address', 60, 300):
            messages.error(request, RATE_LIMIT_MESSAGE)
        elif form.is_valid():
            phone = form.cleaned_data['phone']
            holder = User.objects.filter(phone=phone).first()
            registered = services.is_registered(holder)
            if purpose == codes.SIGN_IN and not registered:
                form.add_error('phone', _("Bu raqam roʻyxatdan oʻtmagan."))
                context['other_door'] = _other_door('signup', phone, context['next'])
            elif purpose == codes.SIGN_UP and registered:
                form.add_error('phone', _("Bu raqam roʻyxatdan oʻtgan."))
                context['other_door'] = _other_door('login', phone, context['next'])
            elif services.is_staff_account(holder):
                form.add_error('phone', _("Xodim hisobiga parol bilan kiriladi."))
                context['staff_door'] = _staff_door(context['next'])
            elif holder is not None and not holder.is_active:
                # Said before a code is sent: it would open nothing.
                form.add_error('phone', _("Bu hisob faol emas."))
            else:
                keep = {'next': context['next']}
                if purpose == codes.SIGN_UP:
                    # Which wording was agreed to is fixed here, where the box
                    # is read, and kept with the attempt (§17 #272).
                    keep['versions'] = legal.accepted_versions()
                outcome = codes.start(request, purpose, phone, **keep)
                if outcome == codes.SENT:
                    return redirect('verify_phone')
                messages.error(request, _refused(outcome))
    context['rate_limited'] = is_currently_limited(request, 'code_ask_address', 60)
    return render(request, template, context)


def login_view(request):
    """Sign in: a registered number is sent a code."""
    if request.user.is_authenticated:
        return redirect('account')
    form = PhoneForm(request.POST or None, initial={'phone': request.GET.get('phone', '')})
    return _ask(request, form, codes.SIGN_IN, 'user/login.html')


def signup_view(request):
    """Sign up: a new number is sent a code, and the account waits for it."""
    if request.user.is_authenticated:
        return redirect('account')
    form = SignupForm(request.POST or None, initial={'phone': request.GET.get('phone', '')})
    return _ask(request, form, codes.SIGN_UP, 'user/signup.html')


def _attempt(request):
    """The open attempt that belongs on the code page, or None.

    A signed-in account is only ever here to confirm its own number, so an
    attempt for anything else is not its attempt.
    """
    state = codes.get(request)
    if state is None:
        return None
    confirming = state['purpose'] == codes.CONFIRM
    if request.user.is_authenticated:
        if not confirming or state['phone'] != request.user.phone:
            return None
    elif confirming:
        # The account it was for is no longer signed in.
        return None
    return state


def _leave(request, state, reason=None):
    """End the attempt and go back to its door.

    A staff account that was confirming its number is signed out as well: it
    cannot use the site unconfirmed, and leaving it on a page that sends a
    code each time it is opened would spend an SMS a visit.
    """
    codes.clear(request)
    if request.user.is_authenticated:
        logout(request)
    return _door(state, reason)


def _finish(request, state):
    """The code was right: do what it was asked for."""
    codes.clear(request)
    purpose, phone = state['purpose'], state['phone']

    if purpose == codes.CONFIRM:
        request.user.phone_verified = True
        request.user.save(update_fields=['phone_verified'])
        messages.success(request, _("Telefon raqam tasdiqlandi."))
        return redirect('account')

    user = User.objects.filter(phone=phone).first()
    if user is not None and (not user.is_active or services.is_staff_account(user)):
        # The door turns both away before a code is sent. This is for an
        # account that changed between the two pages.
        messages.error(request, _("Bu hisob faol emas.") if not user.is_active
                       else _("Xodim hisobiga parol bilan kiriladi."))
        return redirect('login')
    if purpose == codes.SIGN_IN:
        if not services.is_registered(user):
            # The account went away between the two pages.
            return redirect(_other_door('signup', phone, state.get('next')))
        welcome, landing = _("Xush kelibsiz!"), 'shop'
    else:
        if user is None:
            user = services.create_customer(phone, state.get('versions'))
        elif not user.phone_verified:
            services.claim_unconfirmed(user, state.get('versions'))
        welcome, landing = _("Telefon raqam tasdiqlandi."), 'account'

    # A cart filled as a guest follows them in: cart.signals merges it
    # whenever anyone signs in.
    login(request, user, backend=BACKEND)
    messages.success(request, welcome)
    return redirect(state.get('next') or landing)


def verify_phone(request):
    """The code page, for both doors and for a staff number being confirmed."""
    user = request.user
    if user.is_authenticated and user.phone_verified:
        return redirect('account')

    state = _attempt(request)
    if user.is_authenticated and (state is None or codes.is_expired(state)):
        # Signed in at /admin/ with a number nobody has confirmed (§17 #227).
        # The code goes out when the page is opened, as it always has.
        if request.method == 'POST':
            return redirect('verify_phone')
        outcome = codes.start(request, codes.CONFIRM, user.phone)
        if outcome != codes.SENT:
            messages.error(request, _refused(outcome))
        state = _attempt(request)
    elif state is None:
        return redirect('login')
    elif codes.is_expired(state):
        return _leave(request, state, 'expired')

    form = OTPForm(request.POST or None)
    if request.method == 'POST' and state:
        if is_rate_limited(request, 'code_check_address', 30, 300):
            messages.error(request, RATE_LIMIT_MESSAGE)
        elif form.is_valid():
            result = codes.check(request, form.cleaned_data['code'])
            if result == codes.OK:
                return _finish(request, state)
            if result == codes.SPENT:
                messages.error(request, _("Juda koʻp urinish. "
                                          "Iltimos, qaytadan urinib koʻring."))
                return _leave(request, state)
            form.add_error('code', _("Kod notoʻgʻri."))

    # No-break spaces, so the number is not cut in two at the end of a line.
    phone = (state['phone'] if state else user.phone).replace(' ', '\u00a0')
    return render(request, 'user/verify_phone.html', {
        'form': form,
        'purpose': state['purpose'] if state else codes.CONFIRM,
        'phone': phone,
        'resend_in': codes.resend_cooldown(state) if state else 0,
        'ttl': codes.ttl_remaining(state) if state else 0,
        'rate_limited': not state or is_currently_limited(request, 'code_check_address', 30),
    })


def _nothing_to_confirm(request):
    """A signed-in account with a confirmed number has no business on these pages."""
    return request.user.is_authenticated and request.user.phone_verified


@require_POST
def resend_otp(request):
    """Send a new code for the open attempt, a minute after the last."""
    if _nothing_to_confirm(request):
        return redirect('account')
    state = _attempt(request)
    if state is None:
        return redirect('verify_phone' if request.user.is_authenticated else 'login')
    if codes.is_expired(state):
        return _leave(request, state, 'expired')
    if codes.resend_cooldown(state) > 0:
        messages.error(request, _("Iltimos biroz kuting."))
        return redirect('verify_phone')
    outcome = codes.resend(request)
    if outcome == codes.SENT:
        messages.success(request, _("Yangi kod yuborildi."))
    else:
        messages.error(request, _refused(outcome))
    return redirect('verify_phone')


@require_POST
def cancel_verification(request):
    """Give up on the attempt. Nothing was made, so nothing is removed."""
    if _nothing_to_confirm(request):
        return redirect('account')
    state = _attempt(request)
    return _leave(request, state,
                  'cancelled' if state and state['purpose'] == codes.SIGN_UP else None)


@require_POST
def expire_verification(request):
    """Where the page's countdown posts when it reaches zero.

    The server's clock decides, not the page's: a post that arrives while the
    code is still good is sent back to the code page.
    """
    if _nothing_to_confirm(request):
        return redirect('account')
    state = _attempt(request)
    if state and not codes.is_expired(state):
        return redirect('verify_phone')
    return _leave(request, state, 'expired')


def retired(request):
    """A password page that no longer exists. Its name still resolves, to sign-in."""
    return redirect('login')


@login_required
def account(request):
    """Account home: show the five most recent orders."""
    recent_orders = Order.objects.filter(user=request.user).select_related('cart')[:5]
    return render(request, 'user/account.html', {
        'recent_orders': recent_orders,
    })


@login_required
def account_orders(request):
    """List all of the user's orders."""
    orders = Order.objects.filter(user=request.user).select_related('cart').prefetch_related('cart__cart_items')
    return render(request, 'user/account_orders.html', {'orders': orders})


@login_required
def account_settings(request):
    """Settings: the name. The number is the account, and changing it is a request to the shop."""
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, _("Maʼlumotlar yangilandi."))
        return redirect('account_settings')
    return render(request, 'user/account_settings.html', {'profile_form': form})
