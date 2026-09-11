/* Product gallery: thumbnail rail, keyboard arrows, and swipe on touch.
 *
 * The first image is already in the document and the thumbnails are real links to
 * image URLs, so with JavaScript off the customer still sees the product — just
 * without the ability to switch. Nothing here is required to buy.
 */
(function () {
  'use strict';

  var gallery = document.querySelector('[data-gallery]');
  if (!gallery) return;

  var main = gallery.querySelector('[data-gallery-main]');
  var thumbs = Array.prototype.slice.call(gallery.querySelectorAll('[data-gallery-thumb]'));
  if (!main || thumbs.length < 2) return;

  var index = 0;

  function show(next) {
    index = (next + thumbs.length) % thumbs.length;
    main.src = thumbs[index].getAttribute('data-gallery-thumb');
    thumbs.forEach(function (t, i) {
      t.setAttribute('aria-current', i === index ? 'true' : 'false');
    });
  }

  thumbs.forEach(function (thumb, i) {
    thumb.addEventListener('click', function () { show(i); });
  });

  /* Left/right arrows move through the rail once a thumbnail has focus. */
  gallery.addEventListener('keydown', function (e) {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    if (!gallery.contains(document.activeElement)) return;
    e.preventDefault();
    show(index + (e.key === 'ArrowRight' ? 1 : -1));
    thumbs[index].focus();
  });

  /* Horizontal swipe on the main image. The 40 px threshold and the
   * wider-than-tall check keep a vertical page scroll from changing the image. */
  var startX = null, startY = null;
  var frame = main.parentNode;

  frame.addEventListener('touchstart', function (e) {
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
  }, { passive: true });

  frame.addEventListener('touchend', function (e) {
    if (startX === null) return;
    var dx = e.changedTouches[0].clientX - startX;
    var dy = e.changedTouches[0].clientY - startY;
    if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) {
      show(index + (dx < 0 ? 1 : -1));
    }
    startX = startY = null;
  }, { passive: true });
})();
