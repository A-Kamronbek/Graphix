/* The home page's slide carousel.
 *
 * The markup is already a working carousel without this file: a scroll-snap
 * track a thumb can swipe. Everything here is addition — the arrows, the dots,
 * and advancing on its own — which is why all three controls ship `hidden` and
 * are revealed from in here. A control that cannot do anything is worse than
 * no control at all.
 *
 * Scrolling the track is how a slide is changed, even from an arrow or a dot.
 * Position is read back off `scrollLeft` rather than tracked in a variable, so
 * a swipe, a trackpad flick, a keyboard scroll and a click all go through one
 * path and nothing can disagree about which slide is showing.
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-slides]');
  if (!root) return;

  var track = root.querySelector('[data-slides-track]');
  var items = Array.prototype.slice.call(root.querySelectorAll('[data-slides-item]'));
  if (!track || items.length < 2) return;

  var prev = root.querySelector('[data-slides-prev]');
  var next = root.querySelector('[data-slides-next]');
  var controls = root.querySelector('[data-slides-controls]');
  var dots = Array.prototype.slice.call(root.querySelectorAll('[data-slides-dot]'));
  var pause = root.querySelector('[data-slides-pause]');
  var pauseLabel = root.querySelector('[data-slides-pause-label]');

  /* Five seconds a slide. Long enough to read a banner, short enough that the
   * second one is seen before somebody scrolls past. */
  var EVERY = 5000;

  /* Someone who has asked their system for less motion gets none: no timer at
   * all, and the jumps are instant rather than smoothed. */
  var calm = window.matchMedia
    ? window.matchMedia('(prefers-reduced-motion: reduce)')
    : { matches: false };

  var timer = null;
  var stopped = false;      /* the pause button, which outranks everything */

  function current() {
    /* Whichever slide's left edge is nearest the track's scroll position. */
    var best = 0;
    var shortest = Infinity;
    for (var i = 0; i < items.length; i++) {
      var gap = Math.abs(items[i].offsetLeft - track.scrollLeft);
      if (gap < shortest) { shortest = gap; best = i; }
    }
    return best;
  }

  function show(index, smooth) {
    var wrapped = (index + items.length) % items.length;
    track.scrollTo({
      left: items[wrapped].offsetLeft,
      behavior: (smooth && !calm.matches) ? 'smooth' : 'auto'
    });
  }

  function sync() {
    var at = current();
    for (var i = 0; i < dots.length; i++) {
      dots[i].setAttribute('aria-selected', String(i === at));
    }
    /* The arrows wrap rather than stop, so they are never disabled: a
     * carousel that dead-ends on the last card makes somebody guess whether
     * it is broken. */
  }

  /* ------------------------------------------------------------ advancing */

  function tick() {
    /* Never advance a track somebody is in the middle of touching, and never
     * one that is off-screen: a tab in the background would otherwise come
     * back having silently walked through every slide. */
    if (document.hidden) return;
    show(current() + 1, true);
  }

  function start() {
    if (timer || stopped || calm.matches) return;
    timer = window.setInterval(tick, EVERY);
  }

  function halt() {
    if (!timer) return;
    window.clearInterval(timer);
    timer = null;
  }

  /* The button is the mechanism WCAG 2.2.2 asks for. Hovering and focusing
   * pause it too, but neither of those is a mechanism — they are side
   * effects of doing something else, and they leave out anybody who is
   * reading the page without a pointer or a keyboard on it. */
  function setStopped(value) {
    stopped = value;
    if (stopped) { halt(); } else { start(); }
    if (!pause) return;
    pause.setAttribute('aria-pressed', String(stopped));
    var icon = pause.querySelector('use');
    if (icon) icon.setAttribute('href', stopped ? '#i-play' : '#i-pause');
    if (pauseLabel) {
      pauseLabel.textContent = stopped
        ? pause.dataset.playLabel || pauseLabel.textContent
        : pause.dataset.pauseLabel || pauseLabel.textContent;
    }
  }

  /* ---------------------------------------------------------------- wiring */

  if (prev) {
    prev.hidden = false;
    prev.addEventListener('click', function () { show(current() - 1, true); });
  }
  if (next) {
    next.hidden = false;
    next.addEventListener('click', function () { show(current() + 1, true); });
  }
  /* The controls row is no longer revealed here. CSS shows it whenever the
   * document carries `html.js`, which the head sets before the first paint,
   * so its height is never added to a page somebody is already reading
   * (§17 #276). `controls` is still read above, for the pause wiring. */

  dots.forEach(function (dot) {
    dot.addEventListener('click', function () {
      show(parseInt(dot.dataset.slidesDot, 10) || 0, true);
    });
  });

  if (pause) {
    pause.addEventListener('click', function () { setStopped(!stopped); });
  }

  /* One listener, throttled by the frame: `scroll` fires continuously through
   * a swipe and the dots only have to be right when it settles. */
  var pending = false;
  track.addEventListener('scroll', function () {
    if (pending) return;
    pending = true;
    window.requestAnimationFrame(function () { pending = false; sync(); });
  }, { passive: true });

  /* Paused while a pointer is over it, or while the keyboard is inside it:
   * moving something out from under somebody who is reading or tabbing
   * through it is the carousel's oldest rudeness. */
  root.addEventListener('mouseenter', halt);
  root.addEventListener('mouseleave', start);
  root.addEventListener('focusin', halt);
  root.addEventListener('focusout', function (event) {
    if (!root.contains(event.relatedTarget)) start();
  });

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { halt(); } else { start(); }
  });

  /* A system setting can change while the page is open. */
  if (calm.addEventListener) {
    calm.addEventListener('change', function () {
      if (calm.matches) { halt(); } else { start(); }
    });
  }

  sync();
  start();
}());
