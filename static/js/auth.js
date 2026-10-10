/* Auth-page behaviour: the code cells and the signup draft.
 *
 * The code page works without this script: it has one plain field for the
 * code. This swaps in the six cells and adds the countdown and the resend
 * timer. The DOM contract: [data-otp], .otp, .otp__cell, #id_code, #otpForm,
 * #otpTimer[data-ttl], #otpExpireForm, #otpResend[data-cooldown], #signupForm.
 *
 * One thing did change, and it was a bug: the resend button's label was a
 * hardcoded Uzbek string in JavaScript, so it reverted to Uzbek under /ru/ and
 * /en/ as soon as the countdown ticked. It now comes from data-label, which the
 * template renders through {% trans %}.
 */
(function () {
  'use strict';

  /* ------------------------------------------------------------ OTP cells */
  (function initOtp() {
    var wrap = document.querySelector('[data-otp]');
    if (!wrap) return;
    var row = wrap.querySelector('.otp');
    var cells = Array.prototype.slice.call(wrap.querySelectorAll('.otp__cell'));
    var hidden = document.getElementById('id_code');
    var form = document.getElementById('otpForm');
    if (!row || !cells.length || !hidden || !form) return;

    /* The swap: the plain field becomes the hidden store the cells write
     * into, and the cells take its place and its label. */
    hidden.type = 'hidden';
    row.hidden = false;
    var label = wrap.querySelector('label[for="id_code"]');
    if (label) label.htmlFor = cells[0].id;
    if (!cells[0].disabled) cells[0].focus();

    /* Start empty, whatever the browser put back after "back": the form is
     * posted the moment the cells are full, so nothing may be in them that
     * the visitor did not just type. */
    hidden.value = '';
    cells.forEach(function (c) { c.value = ''; });

    function syncHidden() { hidden.value = cells.map(function (c) { return c.value; }).join(''); }
    function focusCell(i) { if (i >= 0 && i < cells.length) cells[i].focus(); }
    function complete() { return cells.every(function (c) { return c.value; }); }

    /* Lay digits out from one cell onwards. Returns the cell to stand in next. */
    function spread(digits, from) {
      digits.split('').slice(0, cells.length - from).forEach(function (ch, i) {
        cells[from + i].value = ch;
        cells[from + i].classList.add('is-filled');
      });
      return Math.min(from + digits.length, cells.length - 1);
    }

    cells.forEach(function (cell, idx) {
      /* A phone that offers the code from the SMS puts all six digits into
       * the first cell at once, so that cell takes any number of them and
       * they are dealt out from there. */
      cell.addEventListener('input', function () {
        var digits = cell.value.replace(/\D/g, '');
        if (digits.length > 1) {
          var next = spread(digits, idx);
          syncHidden();
          focusCell(next);
        } else {
          cell.value = digits;
          cell.classList.toggle('is-filled', !!digits);
          syncHidden();
          if (digits && idx < cells.length - 1) focusCell(idx + 1);
        }
        if (complete()) form.requestSubmit();
      });

      /* Typing into a filled cell replaces what is there. */
      cell.addEventListener('focus', function () { cell.select(); });

      cell.addEventListener('keydown', function (e) {
        if (e.key === 'Backspace') {
          if (!cell.value && idx > 0) {
            e.preventDefault();
            cells[idx - 1].value = '';
            cells[idx - 1].classList.remove('is-filled');
            syncHidden();
            focusCell(idx - 1);
          }
        } else if (e.key === 'ArrowLeft') { e.preventDefault(); focusCell(idx - 1); }
        else if (e.key === 'ArrowRight') { e.preventDefault(); focusCell(idx + 1); }
      });

      cell.addEventListener('paste', function (e) {
        e.preventDefault();
        var text = (e.clipboardData || window.clipboardData).getData('text') || '';
        var digits = text.replace(/\D/g, '').slice(0, cells.length);
        if (!digits) return;
        var next = spread(digits, 0);
        syncHidden();
        focusCell(next);
        if (complete()) form.requestSubmit();
      });
    });

    /* Expiry countdown. The server is the source of truth; this is visual only.
     * On hitting zero it submits the CSRF-protected expire form, and the server
     * re-checks the absolute expiry before acting — so a forged or early POST
     * cannot end an attempt whose code is still valid. */
    var timerEl = document.getElementById('otpTimer');
    if (timerEl) {
      /* Hidden until now: without this script the clock would never move. */
      timerEl.parentNode.hidden = false;
      var left = parseInt(timerEl.dataset.ttl, 10) || 0;
      var fired = false;
      var expireForm = document.getElementById('otpExpireForm');
      var tick = function () {
        if (left < 0) {
          timerEl.textContent = '00:00';
          if (!fired && expireForm) { fired = true; expireForm.submit(); }
          return;
        }
        var m = String(Math.floor(left / 60));
        var s = String(left % 60);
        timerEl.textContent = (m.length < 2 ? '0' + m : m) + ':' + (s.length < 2 ? '0' + s : s);
        left -= 1;
      };
      tick();
      setInterval(tick, 1000);
    }

    /* Resend cooldown. */
    var resendBtn = document.getElementById('otpResend');
    if (resendBtn) {
      var cd = parseInt(resendBtn.dataset.cooldown, 10) || 0;
      if (cd > 0) {
        /* Disabled here and not in the markup: without this script nothing
         * would enable it again, and the server already refuses an early
         * press with a sentence. */
        var baseLabel = resendBtn.dataset.label || resendBtn.textContent.trim();
        resendBtn.disabled = true;
        resendBtn.textContent = baseLabel + ' (' + cd + 's)';
        cd -= 1;
        var iv = setInterval(function () {
          if (cd <= 0) {
            resendBtn.disabled = false;
            resendBtn.textContent = baseLabel;
            clearInterval(iv);
            return;
          }
          resendBtn.textContent = baseLabel + ' (' + cd + 's)';
          cd -= 1;
        }, 1000);
      }
    }
  })();

  /* -------------------------------------------------------- signup draft */
  /* Keeps the number when the visitor pops out to the Terms page and comes
   * back. sessionStorage clears itself with the tab, so the draft never
   * outlives the session. */
  (function initSignupPersist() {
    var form = document.getElementById('signupForm');
    if (!form) return;

    var KEY = 'gx_signup_draft';
    var FIELDS = ['phone'];

    /* Restore only into fields the server left empty, so values re-rendered
     * after a validation error always beat the saved draft. */
    var saved = {};
    try { saved = JSON.parse(sessionStorage.getItem(KEY)) || {}; } catch (e) { saved = {}; }
    FIELDS.forEach(function (name) {
      var el = form.elements[name];
      if (el && !el.value && saved[name]) el.value = saved[name];
    });

    form.addEventListener('input', function () {
      var data = {};
      FIELDS.forEach(function (name) {
        var el = form.elements[name];
        if (el) data[name] = el.value;
      });
      try { sessionStorage.setItem(KEY, JSON.stringify(data)); } catch (e) { /* private mode */ }
    });
  })();
})();
