/* GRAPHIX shell behaviour: drawer, header search, quantity steppers, filter sheet.
 *
 * Progressive enhancement throughout. Every control this file touches already
 * works without it: the drawer's links are in the document, the search field is a
 * plain GET form, the quantity input is a text field, and the filter panel is a
 * form that submits. JavaScript only makes them nicer to use — nothing here is
 * load-bearing, which is the rule the checkout depends on (plan §9 Phase 6d).
 *
 * No framework, no build step (§17 #1). One IIFE, no globals but GX.
 */
(function () {
  'use strict';

  var GX = (window.GX = window.GX || {});

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  /* --------------------------------------------------------- scroll lock */
  /* Counted rather than set and cleared, because the shop has both a drawer and
   * a filter sheet: closing one while the other is open used to hand the page
   * its scrollbar back underneath an open overlay. */
  var locks = 0;
  function lockScroll(on) {
    locks = Math.max(0, locks + (on ? 1 : -1));
    document.documentElement.style.overflow = locks ? 'hidden' : '';
  }

  /* --------------------------------------------------------- focus trap */
  /* An overlay that covers the page must also own the keyboard. Without this,
   * Tab walks straight out of an open drawer and onto links the visitor cannot
   * see, which is worse than no keyboard support at all. */
  var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]),' +
                  ' select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  function focusablesIn(root) {
    return $$(FOCUSABLE, root).filter(function (el) {
      return el.offsetWidth || el.offsetHeight || el.getClientRects().length;
    });
  }

  function trapFocus(root) {
    function onKey(e) {
      if (e.key !== 'Tab') return;
      var items = focusablesIn(root);
      if (!items.length) return;
      var first = items[0], last = items[items.length - 1];
      /* Focus can start outside the overlay (a click on the backdrop, say), so
       * both edges are handled by where focus *is*, not by where it came from. */
      if (!root.contains(document.activeElement)) {
        e.preventDefault();
        first.focus();
      } else if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener('keydown', onKey, true);
    return function release() { document.removeEventListener('keydown', onKey, true); };
  }

  /* ------------------------------------------------------------- drawer */
  /* Focus is moved into the drawer on open and back to the button on close, the
   * backdrop is removed from the tree entirely while closed, and Tab is held
   * inside while it is open. */
  function initDrawer() {
    var drawer = $('[data-drawer]');
    var backdrop = $('[data-drawer-backdrop]');
    var opener = $('[data-drawer-open]');
    if (!drawer || !opener) return;

    var release = null;

    function setOpen(open) {
      if (open === drawer.classList.contains('is-open')) return;
      drawer.classList.toggle('is-open', open);
      drawer.setAttribute('aria-hidden', open ? 'false' : 'true');
      opener.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (backdrop) backdrop.hidden = !open;
      lockScroll(open);
      if (open) {
        release = trapFocus(drawer);
        var first = focusablesIn(drawer)[0];
        if (first) first.focus();
      } else {
        if (release) { release(); release = null; }
        opener.focus();
      }
    }

    opener.addEventListener('click', function () { setOpen(true); });
    $$('[data-drawer-close]').forEach(function (el) {
      el.addEventListener('click', function () { setOpen(false); });
    });
    if (backdrop) backdrop.addEventListener('click', function () { setOpen(false); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && drawer.classList.contains('is-open')) setOpen(false);
    });
  }

  /* ------------------------------------------------------ header search */
  /* Below 860 px the field is hidden and this reveals it as a second header row. */
  function initSearchToggle() {
    var toggle = $('[data-search-toggle]');
    var form = $('.nav__search');
    if (!toggle || !form) return;

    function setOpen(open) {
      form.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) {
        var input = form.querySelector('input');
        if (input) input.focus();
      } else {
        toggle.focus();
      }
    }

    toggle.addEventListener('click', function () {
      setOpen(!form.classList.contains('is-open'));
    });
    /* Escape is what people press to dismiss a revealed field; without it the
     * only way back was to find the toggle again. */
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && form.classList.contains('is-open')) setOpen(false);
    });
  }

  /* ---------------------------------------------------------- steppers */
  /* The input stays a plain text field that submits its own value; these buttons
   * are a convenience. max comes from the server, which is the only place that
   * knows the real stock. */
  function initSteppers() {
    $$('[data-qty]').forEach(function (wrap) {
      var input = wrap.querySelector('input');
      if (!input) return;
      var dec = wrap.querySelector('[data-qty-dec]');
      var inc = wrap.querySelector('[data-qty-inc]');

      function max() { return parseInt(wrap.getAttribute('data-qty-max'), 10) || 99; }

      /* A button that does nothing should look like it does nothing. Without
       * this the minus at quantity 1 was fully styled and simply ignored the
       * click, which reads as a broken control rather than a limit. */
      function sync() {
        var n = parseInt(input.value, 10) || 1;
        if (dec) dec.disabled = input.disabled || n <= 1;
        if (inc) inc.disabled = input.disabled || n >= max();
      }

      function nudge(by) {
        var n = parseInt(input.value, 10);
        if (isNaN(n)) n = 1;
        input.value = Math.max(1, Math.min(max(), n + by));
        input.dispatchEvent(new Event('change', { bubbles: true }));
      }

      if (dec) dec.addEventListener('click', function () { nudge(-1); });
      if (inc) inc.addEventListener('click', function () { nudge(1); });

      input.addEventListener('change', function () {
        var n = parseInt(input.value, 10);
        input.value = isNaN(n) ? 1 : Math.max(1, Math.min(max(), n));
        sync();
      });
      /* The size picker rewrites data-qty-max when the chosen variant changes,
       * so the stepper has to be told to look again. */
      wrap.addEventListener('gx:qtymax', sync);
      sync();
    });
  }

  /* ----------------------------------------------------- filter sheet */
  /* Same markup as the desktop sidebar; on mobile it becomes a bottom sheet, and
   * a sheet that covers the page gets the same focus treatment as the drawer. */
  function initFilterSheet() {
    var toggle = $('[data-filters-toggle]');
    var panel = $('[data-filters]');
    var backdrop = $('[data-filters-backdrop]');
    if (!toggle || !panel) return;

    var release = null;

    function setOpen(open) {
      if (open === panel.classList.contains('is-open')) return;
      panel.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (backdrop) backdrop.hidden = !open;
      lockScroll(open);
      if (open) {
        release = trapFocus(panel);
        var first = focusablesIn(panel)[0];
        if (first) first.focus();
      } else {
        if (release) { release(); release = null; }
        toggle.focus();
      }
    }

    toggle.addEventListener('click', function () {
      setOpen(!panel.classList.contains('is-open'));
    });
    $$('[data-filters-close]').forEach(function (el) {
      el.addEventListener('click', function () { setOpen(false); });
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && panel.classList.contains('is-open')) setOpen(false);
    });
  }

  /* ------------------------------------------------------------- toasts */
  /* A transient confirmation, in a container the shell always renders with
   * aria-live. Used by the heart and by copy-link; the server's own messages
   * still come through the message strip, which survives with JS off. */
  function toast(text, kind) {
    var host = $('[data-toasts]');
    if (!host) return;
    var el = document.createElement('div');
    el.className = 'toast' + (kind ? ' toast--' + kind : '');
    el.textContent = text;
    host.appendChild(el);
    setTimeout(function () { el.remove(); }, 4000);
  }

  /* --------------------------------------------------------------- heart */
  /* The heart is a real form and works with JavaScript off — it posts and the
   * server redirects back. This upgrades it to a fetch so the page does not
   * jump, and paints the new state immediately, rolling back if the request
   * fails. The server is still the authority: the count that lands on the
   * button is the one it returns, not the one we guessed. */
  function initLikes() {
    document.addEventListener('submit', function (e) {
      var form = e.target.closest('[data-like-form]');
      if (!form) return;
      var btn = form.id
        ? $('[data-like][form="' + form.id + '"]') || form.querySelector('[data-like]')
        : form.querySelector('[data-like]');
      if (!btn) return;

      e.preventDefault();
      var wasPressed = btn.getAttribute('aria-pressed') === 'true';
      var countEl = btn.querySelector('[data-like-count]');
      var wasCount = countEl ? countEl.textContent : '';
      var wasHidden = countEl ? countEl.hidden : true;

      function paint(pressed, count) {
        btn.setAttribute('aria-pressed', pressed ? 'true' : 'false');
        btn.setAttribute('aria-label', pressed ? btn.dataset.labelOn || btn.getAttribute('aria-label')
                                               : btn.dataset.labelOff || btn.getAttribute('aria-label'));
        if (!countEl) return;
        if (count !== null && count !== undefined) countEl.textContent = String(count);
        countEl.hidden = String(countEl.textContent) === '0';
      }

      /* Optimistic: the count moves by one in the direction of the tap, and is
       * corrected to the server's number a moment later. */
      paint(!wasPressed, countEl ? Math.max(0, (parseInt(wasCount, 10) || 0) + (wasPressed ? -1 : 1)) : null);
      btn.setAttribute('aria-busy', 'true');

      fetch(form.action, {
        method: 'POST',
        headers: { 'Accept': 'application/json', 'X-Requested-With': 'fetch' },
        body: new FormData(form),
        credentials: 'same-origin',
      }).then(function (res) {
        if (res.status === 401) {
          return res.json().then(function (data) { window.location.href = data.login_url; });
        }
        if (!res.ok) throw new Error('like failed');
        return res.json().then(function (data) { paint(data.liked, data.count); });
      }).catch(function () {
        paint(wasPressed, wasCount);
        if (countEl) countEl.hidden = wasHidden;
        /* No fallback string here on purpose: a message the page shows is copy,
         * and copy lives in the template where gettext can reach it. A literal
         * written in this file would render Uzbek to a Russian visitor. */
        if (btn.dataset.error) toast(btn.dataset.error, 'danger');
      }).then(function () {
        btn.removeAttribute('aria-busy');
      });
    });
  }

  /* --------------------------------------------------------------- share */
  /* navigator.share where it exists (every phone this shop sells to), and a
   * two-item menu where it does not. Instagram has no URL that shares a link,
   * so copy-link IS the Instagram path — offering a dead "Instagram" item
   * would be worse than not offering one. */
  function initShare() {
    var wrap = $('[data-share-wrap]');
    if (!wrap) return;
    var btn = $('[data-share]', wrap);
    var menu = $('[data-share-menu]', wrap);
    var url = window.location.href;
    var title = document.title;

    wrap.hidden = false;

    var tg = $('[data-share-telegram]', wrap);
    if (tg) tg.href = 'https://t.me/share/url?url=' + encodeURIComponent(url) +
                      '&text=' + encodeURIComponent(title);

    function setOpen(open) {
      menu.hidden = !open;
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    btn.addEventListener('click', function () {
      if (navigator.share) {
        navigator.share({ title: title, url: url }).catch(function () { /* dismissed */ });
        return;
      }
      setOpen(menu.hidden);
    });

    var copy = $('[data-share-copy]', wrap);
    if (copy) copy.addEventListener('click', function () {
      var done = function () {
        if (copy.dataset.done) toast(copy.dataset.done, 'success');
        setOpen(false);
      };
      if (navigator.clipboard) navigator.clipboard.writeText(url).then(done, done);
      else done();
    });

    document.addEventListener('click', function (e) {
      if (!menu.hidden && !wrap.contains(e.target)) setOpen(false);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !menu.hidden) { setOpen(false); btn.focus(); }
    });
  }

  GX.$ = $;
  GX.$$ = $$;
  GX.toast = toast;
  GX.trapFocus = trapFocus;
  GX.lockScroll = lockScroll;
  GX.focusablesIn = focusablesIn;
  GX.prefersReducedMotion = function () {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  };

  document.addEventListener('DOMContentLoaded', function () {
    initDrawer();
    initSearchToggle();
    initSteppers();
    initFilterSheet();
    initLikes();
    initShare();
  });
})();
