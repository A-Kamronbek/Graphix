/* Auth-page behaviour: the OTP cell field and the signup draft.
 *
 * Both are ported from the pre-Phase-5 script unchanged in behaviour — the OTP
 * flow, its rate limiting and its expiry are on the "never break these" list, so
 * this is a move, not a rewrite. The DOM contract is identical: [data-otp],
 * .otp__cell, #id_code, #otpForm, #otpTimer[data-ttl], #otpExpireForm,
 * #otpResend[data-cooldown], #signupForm.
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
    var cells = Array.prototype.slice.call(wrap.querySelectorAll('.otp__cell'));
    var hidden = document.getElementById('id_code');
    var form = document.getElementById('otpForm');
    if (!cells.length || !hidden || !form) return;

    if (hidden.value) {
      hidden.value.split('').slice(0, cells.length).forEach(function (ch, i) {
        cells[i].value = ch;
        cells[i].classList.toggle('is-filled', !!ch);
      });
    }

    function syncHidden() { hidden.value = cells.map(function (c) { return c.value; }).join(''); }
    function focusCell(i) { if (i >= 0 && i < cells.length) cells[i].focus(); }
    function complete() { return cells.every(function (c) { return c.value; }); }

    cells.forEach(function (cell, idx) {
      cell.addEventListener('input', function () {
        cell.value = cell.value.replace(/\D/g, '').slice(-1);
        cell.classList.toggle('is-filled', !!cell.value);
        syncHidden();
        if (cell.value && idx < cells.length - 1) focusCell(idx + 1);
        if (complete()) form.requestSubmit();
      });

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
        digits.split('').forEach(function (ch, i) {
          if (cells[i]) { cells[i].value = ch; cells[i].classList.add('is-filled'); }
        });
        syncHidden();
        focusCell(Math.min(digits.length, cells.length - 1));
        if (complete()) form.requestSubmit();
      });
    });

    /* Expiry countdown. The server is the source of truth; this is visual only.
     * On hitting zero it submits the CSRF-protected expire form, and the server
     * re-checks the absolute expiry before acting — so a forged or early POST
     * cannot delete a user whose code is still valid. */
    var timerEl = document.getElementById('otpTimer');
    if (timerEl) {
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
        var baseLabel = resendBtn.dataset.label || resendBtn.textContent.trim();
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
  /* Keeps the non-sensitive fields when the visitor pops out to the Terms page
   * and comes back. Passwords are deliberately never saved, and sessionStorage
   * clears itself with the tab, so the draft never outlives the session. */
  (function initSignupPersist() {
    var form = document.getElementById('signupForm');
    if (!form) return;

    var KEY = 'gx_signup_draft';
    var FIELDS = ['username', 'first_name', 'phone'];

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
