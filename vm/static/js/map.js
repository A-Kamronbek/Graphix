/* GX.map — the one place in the project that knows which map provider we use.
 *
 * Written before the provider was settled, and that is exactly why changing it
 * cost nothing: the provider moved from Yandex to Google with no code to
 * rewrite, because none had been written outside this file (§17 #27, #83).
 * 2GIS or Leaflet stay one file away.
 *
 * The interface is deliberately small: init, setPin, getPin, onPinMove,
 * locate, reverseGeocode. No page ever touches a `google.*` global.
 *
 * Everything here is optional to the checkout. If the key is blank the script
 * tag is not rendered at all; if the script is blocked or fails, `ready` never
 * resolves and the page carries on with a typed address (§3, §17 #91).
 */
(function () {
  'use strict';

  var GX = (window.GX = window.GX || {});

  /* Tashkent centre — where a pin starts when the customer has not moved it. */
  var DEFAULT = { lat: 41.311081, lng: 69.240562 };

  var waiting = [];
  var loaded = false;

  /* Google calls this when its script finishes. Named on window because the
   * loader takes a global callback name, not a function. */
  window.GXMapReady = function () {
    loaded = true;
    waiting.splice(0).forEach(function (fn) { fn(); });
  };

  function whenReady(fn) {
    if (loaded) fn();
    else waiting.push(fn);
  }

  /* One map instance per page; the checkout only ever needs one. */
  var map = null;
  var marker = null;
  var listeners = [];

  function emit(pos) {
    listeners.forEach(function (fn) { fn(pos); });
  }

  var api = {
    /* Is a provider actually available? The caller uses this to decide whether
     * to show the map controls at all, rather than showing a broken grey box. */
    available: function () { return loaded; },

    ready: whenReady,

    /* Draw the map into `el` with a draggable pin. Returns nothing; the pin's
     * position arrives through onPinMove. */
    init: function (el, start) {
      if (!loaded || !el) return;
      var centre = start || DEFAULT;
      map = new google.maps.Map(el, {
        center: centre,
        zoom: start ? 16 : 12,
        mapTypeControl: false,
        streetViewControl: false,
        fullscreenControl: false,
        /* The pin is the only thing being chosen here, so everything that
         * competes with it is off. */
        clickableIcons: false,
      });
      marker = new google.maps.Marker({
        position: centre, map: map, draggable: true,
      });
      marker.addListener('dragend', function () { emit(api.getPin()); });
      map.addListener('click', function (e) {
        api.setPin({ lat: e.latLng.lat(), lng: e.latLng.lng() });
        emit(api.getPin());
      });
    },

    /* A read-only map of one point: the admin's view of where a courier is
     * actually going. Deliberately not `init` with the dragging turned off —
     * the checkout's map is a control the customer operates and this one is a
     * picture, and keeping them apart means the admin page can never acquire a
     * pin the customer did not drop. It also keeps its own instance, so
     * neither can disturb the other. */
    show: function (el, pos, zoom) {
      if (!loaded || !el || !pos) return;
      var shown = new google.maps.Map(el, {
        center: pos,
        zoom: zoom || 16,
        mapTypeControl: false,
        streetViewControl: false,
        clickableIcons: false,
      });
      new google.maps.Marker({ position: pos, map: shown });
    },

    setPin: function (pos) {
      if (!marker || !pos) return;
      marker.setPosition(pos);
      if (map) map.panTo(pos);
    },

    getPin: function () {
      if (!marker) return null;
      var p = marker.getPosition();
      return p ? { lat: p.lat(), lng: p.lng() } : null;
    },

    onPinMove: function (fn) { listeners.push(fn); },

    /* The browser's own geolocation, behind an explicit tap. Never called on
     * load: a permission prompt nobody asked for is the fastest way to get it
     * denied for good. */
    locate: function (onDone) {
      if (!navigator.geolocation) { onDone(null); return; }
      navigator.geolocation.getCurrentPosition(
        function (p) {
          var pos = { lat: p.coords.latitude, lng: p.coords.longitude };
          api.setPin(pos);
          onDone(pos);
        },
        function () { onDone(null); },
        { enableHighAccuracy: true, timeout: 8000 }
      );
    },

    /* Coordinates to a human address. Best-effort by definition: a failure
     * leaves the form exactly as the customer left it.
     *
     * The callback gets (text, parts). `parts` is a flat object keyed by
     * Google's component type — administrative_area_level_1, route and so on —
     * because the checkout does not want a formatted string, it wants to fill
     * a region, a district and a street separately (§17 #116). It stays a
     * plain object rather than a google.* structure so nothing outside this
     * file learns which provider we use (§17 #27).
     *
     * Every result is scanned, not just the first: the nearest match to a
     * point is often a plus code or a building, and the district can be
     * several results down. */
    reverseGeocode: function (pos, onDone) {
      if (!loaded || !pos) { onDone(null, {}); return; }
      new google.maps.Geocoder().geocode({ location: pos }, function (results, status) {
        if (status !== 'OK' || !results || !results.length) { onDone(null, {}); return; }
        var parts = {};
        results.forEach(function (result) {
          (result.address_components || []).forEach(function (c) {
            (c.types || []).forEach(function (type) {
              if (!parts[type]) parts[type] = c.long_name;
            });
          });
        });
        onDone(results[0].formatted_address, parts);
      });
    },
  };

  GX.map = api;
})();
