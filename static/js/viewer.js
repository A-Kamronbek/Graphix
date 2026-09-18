/* The full-screen viewer: one component, two callers.
 *
 * A tap on the size chart or on a product photograph opens the same overlay —
 * which is why the gallery's zoom was moved here rather than built twice
 * (§17 #79). Zooming itself is the browser's: the stage is a scroll container
 * with `touch-action: pinch-zoom`, so a phone pinches the way it does anywhere
 * else and nothing has to be reimplemented with transforms.
 *
 * Everything it opens already exists on the page — the chart block is rendered
 * hidden, the gallery image is the page's own image — so with JavaScript off
 * the size-guide link is still a link to the real page and the photograph is
 * still the photograph. Nothing here is required to buy.
 */
(function () {
  'use strict';

  var GX = (window.GX = window.GX || {});
  var viewer = document.querySelector('[data-viewer]');
  if (!viewer) return;

  var stage = viewer.querySelector('[data-viewer-stage]');
  var closeBtn = viewer.querySelector('[data-viewer-close]');
  var ZOOM_LABEL = viewer.getAttribute('data-zoom-label') || '';
  var ZOOM_SUFFIX = viewer.getAttribute('data-zoom-suffix') || '';
  var release = null;
  var opener = null;

  function close() {
    if (viewer.hidden) return;
    viewer.hidden = true;
    stage.innerHTML = '';
    if (release) { release(); release = null; }
    if (GX.lockScroll) GX.lockScroll(false);
    if (opener && document.contains(opener)) opener.focus();
    opener = null;
  }

  /* `content` is a DOM node the caller owns; it is cloned, so the page keeps
   * its own copy and closing the viewer cannot take markup away with it. */
  function open(content, from) {
    if (!content) return;
    opener = from || null;
    stage.innerHTML = '';
    var copy = content.cloneNode(true);
    /* The source block is rendered hidden — that is how it can sit in the
     * document for a screen reader without showing on the page. The clone is
     * the thing being shown, so it must not inherit that. */
    copy.hidden = false;
    copy.removeAttribute('hidden');
    stage.appendChild(copy);
    viewer.hidden = false;
    if (GX.lockScroll) GX.lockScroll(true);
    if (GX.trapFocus) release = GX.trapFocus(viewer);
    closeBtn.focus();
  }

  closeBtn.addEventListener('click', close);
  /* A tap on the backdrop closes; a tap on the content does not. */
  viewer.addEventListener('click', function (e) {
    if (e.target === viewer || e.target === stage) close();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') close();
  });

  GX.viewer = { open: open, close: close };

  /* ---------------------------------------------------------- size chart */
  /* The chart block is rendered hidden on the product page so the viewer has
   * real markup to show — image, table and note — rather than a second copy
   * built in JavaScript that could drift from the page's own. */
  var link = document.querySelector('[data-size-guide]');
  var chart = document.querySelector('[data-sizeguide-content]');
  if (link && chart) {
    link.addEventListener('click', function (e) {
      e.preventDefault();          /* the href stays as the no-JS fallback */
      open(chart, link);
      highlightChosenSize();
    });
  }

  /* The row for the size the customer has actually picked, so the number they
   * need is the one that stands out. Read from the size picker's pressed
   * button rather than from a variable, because that button is the truth. */
  function highlightChosenSize() {
    var pressed = document.querySelector('.sizes__btn[aria-pressed="true"]');
    if (!pressed) return;
    var id = pressed.getAttribute('data-size');
    Array.prototype.forEach.call(stage.querySelectorAll('[data-row-size]'), function (row) {
      var mine = row.getAttribute('data-row-size') === id;
      row.classList.toggle('is-current', mine);
      if (mine) row.setAttribute('aria-current', 'true');
      else row.removeAttribute('aria-current');
    });
  }

  /* ------------------------------------------------- any zoomable image */
  /* The product photograph and the chart on the standalone page are the same
   * gesture: tap the picture, see it big. Delegated, so the gallery swapping
   * its main image does not need re-binding. */
  function zoomable(el) {
    return el && el.tagName === 'IMG' &&
           (el.hasAttribute('data-gallery-main') || el.hasAttribute('data-zoom'));
  }

  function zoomOpen(el) {
    var img = document.createElement('img');
    /* The full-width rendition, not what the page is showing: the frame is
     * given a photograph sized for the frame, and zooming into that is a
     * blurry photograph. No `srcset` on the clone for the same reason — the
     * viewer wants this file, at this size, whatever the viewport is. */
    img.src = el.getAttribute('data-zoom-src') || el.currentSrc || el.src;
    img.alt = el.alt;
    open(img, el);
  }

  document.addEventListener('click', function (e) {
    if (zoomable(e.target)) zoomOpen(e.target);
  });

  /* Enter and Space, because these are controls now (below). Read off
   * `document.activeElement` rather than from a listener per image: the
   * gallery replaces nothing and the review photographs are rendered once, but
   * one handler is one thing to keep right. */
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Spacebar') return;
    var el = document.activeElement;
    if (!zoomable(el)) return;
    e.preventDefault();          /* Space would otherwise scroll the page */
    zoomOpen(el);
  });

  /* A photograph that opens full screen IS a control, and an <img> is not one:
   * it takes no focus, answers no key and has no role, so the only way into a
   * 72 px review photograph was a mouse or a finger (§18 #24). Given the role,
   * the tab stop and a name here — one place for every zoomable image on the
   * site — rather than by wrapping nine templates' images in a button.
   *
   * The name is the picture's own `alt` plus a word saying what pressing it
   * does; an image with no alt gets the label alone. */
  Array.prototype.forEach.call(
    document.querySelectorAll('[data-gallery-main], [data-zoom]'),
    function (el) {
      el.classList.add('zoomable');
      if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '0');
      el.setAttribute('role', 'button');
      var alt = (el.getAttribute('alt') || '').trim();
      var name = alt ? (ZOOM_SUFFIX ? alt + ' — ' + ZOOM_SUFFIX : alt) : ZOOM_LABEL;
      if (name) el.setAttribute('aria-label', name);
    }
  );
})();
