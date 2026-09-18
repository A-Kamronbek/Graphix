/* GRAPHIX form controls: the browser's own words, in the page's language.
 *
 * Loaded by both shells - the storefront and the staff panel. Two things a
 * browser says for itself, in its own language rather than the page's:
 *
 * 1. The bubble a form shows when a field is missing or malformed ("Please
 *    fill out this field."). Each check is answered with a sentence from
 *    `#gx-forms`, which the shell renders through gettext (§18, form
 *    warnings). For a pattern, a field that states its own format - in
 *    `title`, or in the `data-error-format` the checkout's index carries -
 *    says that instead, because it says what the pattern is.
 * 2. A file input's "Choose Files / No file chosen". A field marked
 *    `data-file-field` is upgraded to a translated button and a line naming
 *    what was picked (§18 #29). Without this script the native control stays,
 *    and still works.
 *
 * Nothing here is load-bearing: the server validates everything again. This
 * is the only script that sets a custom validity message, which is what makes
 * it safe to clear every one of them before a form is checked; a script that
 * needs its own will have to be reconciled with that first.
 */
(function () {
  'use strict';

  var SAY = {};
  try {
    var node = document.getElementById('gx-forms');
    if (node) SAY = JSON.parse(node.textContent);
  } catch (e) { /* A broken block leaves the browser's own words. */ }

  function say(key, n) {
    var text = SAY[key] || '';
    return n === undefined ? text : text.replace('{n}', n);
  }

  function messageFor(el) {
    var v = el.validity;
    var type = (el.type || '').toLowerCase();
    if (v.valueMissing) {
      if (type === 'checkbox') return say('checkbox');
      if (type === 'radio') return say('radio');
      if (type === 'file') return say('file');
      if (el.tagName === 'SELECT') return say('select');
      return say('required');
    }
    if (v.badInput) return say('number');
    if (v.patternMismatch) {
      return el.title || el.getAttribute('data-error-format') || say('pattern');
    }
    if (v.rangeUnderflow) return say('min', el.min);
    if (v.rangeOverflow) return say('max', el.max);
    if (v.stepMismatch) return say('whole');
    return say('invalid');
  }

  /* `invalid` does not bubble, so it is caught on the way down. The message
     is set while the browser is still deciding what to show. */
  document.addEventListener('invalid', function (e) {
    var el = e.target;
    if (!el.setCustomValidity || !el.validity || el.validity.customError) return;
    var text = messageFor(el);
    if (text) el.setCustomValidity(text);
  }, true);

  /* A custom message makes a field invalid until it is cleared, so it is
     cleared whenever the field changes - and, because a script can fill a
     field without either event (the map fills the address), again on every
     attempt to send the form, before the browser checks it. Enter in a field
     is a click on the form's default button, so that path is covered too. */
  function clear(el) {
    if (el && el.setCustomValidity && el.validity && el.validity.customError) {
      el.setCustomValidity('');
    }
  }
  document.addEventListener('input', function (e) { clear(e.target); }, true);
  document.addEventListener('change', function (e) { clear(e.target); }, true);
  document.addEventListener('click', function (e) {
    var button = e.target.closest && e.target.closest('button, input[type="submit"]');
    var form = button && button.form;
    if (!form || (button.type && button.type !== 'submit')) return;
    Array.prototype.forEach.call(form.elements, clear);
  }, true);

  /* ------------------------------------------------------ file pickers */
  document.querySelectorAll('[data-file-field]').forEach(function (field) {
    var input = field.querySelector('input[type="file"]');
    var ui = field.querySelector('[data-file-ui]');
    var status = field.querySelector('[data-file-status]');
    if (!input || !ui || !status) return;

    /* Into the button's row, hidden but still focusable, so the row can draw
       the focus ring on the button (`.field__file:has(input:focus-visible)`). */
    input.classList.remove('input');
    input.classList.add('sr-only');
    ui.insertBefore(input, status);
    ui.hidden = false;

    function show() {
      var count = input.files ? input.files.length : 0;
      status.textContent = count === 0 ? say('noFile')
        : count === 1 ? input.files[0].name
        : say('files', count);
    }
    input.addEventListener('change', show);
    show();
  });
})();
