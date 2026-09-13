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

  document.addEventListener('click', function (e) {
    var el = e.target;
    if (!zoomable(el)) return;
    var img = document.createElement('img');
    img.src = el.currentSrc || el.src;
    img.alt = el.alt;
    open(img, el);
  });

  Array.prototype.forEach.call(
    document.querySelectorAll('[data-gallery-main], [data-zoom]'),
    function (el) { el.style.cursor = 'zoom-in'; }
  );
})();
