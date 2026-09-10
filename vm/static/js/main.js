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

  /* ------------------------------------------------------------- drawer */
  /* Focus is moved into the drawer on open and back to the button on close, and
   * the backdrop is removed from the tree entirely while closed, so a closed
   * drawer can never hold the keyboard. */
  function initDrawer() {
    var drawer = $('[data-drawer]');
    var backdrop = $('[data-drawer-backdrop]');
    var opener = $('[data-drawer-open]');
    if (!drawer || !opener) return;

    function setOpen(open) {
      drawer.classList.toggle('is-open', open);
      drawer.setAttribute('aria-hidden', open ? 'false' : 'true');
      opener.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (backdrop) backdrop.hidden = !open;
      document.documentElement.style.overflow = open ? 'hidden' : '';
      if (open) {
        var first = drawer.querySelector('a, button');
        if (first) first.focus();
      } else {
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

    toggle.addEventListener('click', function () {
      var open = !form.classList.contains('is-open');
      form.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) {
        var input = form.querySelector('input');
        if (input) input.focus();
      }
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
      var max = parseInt(wrap.getAttribute('data-qty-max'), 10) || 99;

      function nudge(by) {
        var n = parseInt(input.value, 10);
        if (isNaN(n)) n = 1;
        input.value = Math.max(1, Math.min(max, n + by));
        input.dispatchEvent(new Event('change', { bubbles: true }));
      }

      var dec = wrap.querySelector('[data-qty-dec]');
      var inc = wrap.querySelector('[data-qty-inc]');
      if (dec) dec.addEventListener('click', function () { nudge(-1); });
      if (inc) inc.addEventListener('click', function () { nudge(1); });

      input.addEventListener('change', function () {
        var n = parseInt(input.value, 10);
        input.value = isNaN(n) ? 1 : Math.max(1, Math.min(max, n));
      });
    });
  }

  /* ----------------------------------------------------- filter sheet */
  /* Same markup as the desktop sidebar; on mobile it becomes a bottom sheet. */
  function initFilterSheet() {
    var toggle = $('[data-filters-toggle]');
    var panel = $('[data-filters]');
    if (!toggle || !panel) return;

    function setOpen(open) {
      panel.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      document.documentElement.style.overflow = open ? 'hidden' : '';
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

  GX.$ = $;
  GX.$$ = $$;

  document.addEventListener('DOMContentLoaded', function () {
    initDrawer();
    initSearchToggle();
    initSteppers();
    initFilterSheet();
  });
})();
