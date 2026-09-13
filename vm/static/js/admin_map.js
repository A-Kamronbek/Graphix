/* The order admin's map: where the courier is actually going.
 *
 * A coordinate in a form field tells the owner nothing — 41.311081 is a number,
 * not a place. This draws the one pin the customer dropped so he can see at a
 * glance whether the parcel is going across town or across the country, without
 * leaving the order he is looking at.
 *
 * Read-only by construction: it calls GX.map.show, which has no dragging and no
 * click handler, so the admin page cannot acquire a pin the customer never
 * dropped (§17 #108). Everything goes through the GX.map wrapper for the same
 * reason the checkout does — the provider is one file away from being swapped
 * (§17 #27).
 *
 * The Google script is loaded from here rather than from the template because
 * the admin template is Django's, not ours; the key travels on the element as a
 * data attribute, the same browser key the checkout already ships.
 */
(function () {
  'use strict';

  /* Django puts ModelAdmin.Media scripts in the head WITHOUT `defer`, so this
   * file runs before the body it is looking for exists. Without the wait it
   * found nothing, returned, and left an empty 320 px box on the page — which
   * looks exactly like a map that failed to load (§17 #113). */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }

  function start() {
    var el = document.querySelector('[data-admin-map]');
    if (!el || !window.GX || !GX.map) return;

    var lat = parseFloat(el.dataset.lat);
    var lng = parseFloat(el.dataset.lng);
    var key = el.dataset.key || '';
    if (!key || isNaN(lat) || isNaN(lng)) return;

    GX.map.ready(function () {
      GX.map.show(el, { lat: lat, lng: lng });
    });

    /* Loaded once per page, and only when there is a pin worth drawing: an
     * order with a typed address costs the Maps account nothing. */
    if (!document.querySelector('script[data-gx-maps]')) {
      var script = document.createElement('script');
      script.async = true;
      script.dataset.gxMaps = '1';
      script.src = 'https://maps.googleapis.com/maps/api/js?key=' +
        encodeURIComponent(key) + '&loading=async&callback=GXMapReady';
      document.head.appendChild(script);
    }
  }
})();
