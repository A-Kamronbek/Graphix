/* Size picker: keeps the hidden inputs, the price and the buy button in step.
 *
 * The map is keyed "colour_id:size_id" and comes from the server, which is the
 * only thing that knows the real prices and stock — this file never decides
 * whether something is purchasable, it only reflects what it was told (§17 #23).
 *
 * Without JavaScript the form still posts the server-chosen default variant, so
 * the customer can always buy the size that was pre-selected.
 */
(function () {
  'use strict';

  var form = document.querySelector('[data-variant-form]');
  if (!form) return;

  var map = {};
  try {
    map = JSON.parse(form.getAttribute('data-variants') || '{}');
  } catch (e) {
    return;                               // malformed payload: leave the form as served
  }

  var colourInput = form.querySelector('[data-variant-colour]');
  var sizeInput = form.querySelector('[data-variant-size]');
  var hint = form.querySelector('[data-variant-hint]');
  var buy = form.querySelector('[data-buy]');
  var stepper = form.querySelector('[data-qty]');
  var buttons = Array.prototype.slice.call(form.querySelectorAll('[data-size]'));

  /* Both the buy column and the mobile bar show the price, and they must agree. */
  var priceNodes = Array.prototype.slice.call(document.querySelectorAll('[data-price-display]'));
  var labelNodes = Array.prototype.slice.call(document.querySelectorAll('[data-variant-label]'));

  /* Read the currency word out of what the server rendered rather than hardcoding
   * it — the page may be in any of three languages. */
  var CURRENCY = (function () {
    var text = priceNodes.length ? priceNodes[0].textContent.trim() : '';
    var parts = text.split(/\s+/);
    return parts.length > 1 ? parts[parts.length - 1] : '';
  })();

  function format(value) {
    /* Thin spaces every three digits, matching the server's price filter. */
    return String(Math.round(value)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  }

  function apply(colourId, sizeId) {
    var entry = map[(colourId || '') + ':' + (sizeId || '')];

    if (colourInput) colourInput.value = colourId || '';
    if (sizeInput) sizeInput.value = sizeId || '';

    buttons.forEach(function (b) {
      b.setAttribute('aria-pressed', b.getAttribute('data-size') === String(sizeId) ? 'true' : 'false');
    });

    if (!entry) return;

    priceNodes.forEach(function (n) { n.textContent = format(entry.price) + ' ' + CURRENCY; });

    var label = buttons.filter(function (b) {
      return b.getAttribute('data-size') === String(sizeId);
    })[0];
    if (label) {
      labelNodes.forEach(function (n) { n.textContent = label.textContent.trim(); });
    }

    if (stepper) {
      stepper.setAttribute('data-qty-max', Math.max(1, Math.min(99, entry.stock || 1)));
      var qty = stepper.querySelector('input');
      if (qty) {
        qty.disabled = !entry.available;
        if (parseInt(qty.value, 10) > entry.stock) qty.value = Math.max(1, entry.stock);
      }
    }

    if (buy) buy.disabled = !entry.available;
    if (hint) {
      /* Only ever a reassurance, never the only signal: a size that has run out is
       * already a disabled button. */
      hint.textContent = (entry.available && entry.stock > 0 && entry.stock <= 3)
        ? hint.getAttribute('data-low') || ''
        : '';
    }
  }

  buttons.forEach(function (b) {
    if (b.disabled) return;
    b.addEventListener('click', function () {
      apply(colourInput ? colourInput.value : '', b.getAttribute('data-size'));
    });
  });

  /* The mobile bar's button is a jump to the real one, not a second submit. */
  var jump = document.querySelector('[data-buy-jump]');
  if (jump && buy) {
    jump.addEventListener('click', function () {
      form.scrollIntoView({ behavior: 'smooth', block: 'center' });
      buy.focus();
    });
  }
})();
