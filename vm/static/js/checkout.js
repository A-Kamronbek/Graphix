/* Checkout behaviour: the delivery branch, the two drawers, and the map.
 *
 * Every control here already works without JavaScript. The delivery choice is
 * radios; the region and district are real <select>s that submit; the postal
 * index is a text field the server validates; the address is a textarea. This
 * file only makes them nicer — it hides the half of the form that does not
 * apply, turns the two selects into drawers that can group and search, and
 * offers a pin. Nothing here is load-bearing, which is the rule the checkout
 * depends on (§3, §17 #91).
 */
(function () {
  'use strict';

  var GX = (window.GX = window.GX || {});
  var form = document.querySelector('[data-checkout]');
  if (!form) return;

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  var DISTRICTS = {};
  try { DISTRICTS = JSON.parse(form.dataset.districts || '{}'); } catch (e) { DISTRICTS = {}; }

  var locationFields = $('[data-location-fields]');
  var branchFields = $('[data-branch-fields]');
  var homeFields = $('[data-home-fields]');
  var regionSelect = $('[data-region]');
  var districtSelect = $('[data-district]');
  var noteField = $('[data-location-note-field]');
  var indexInput = $('[data-postal-index]');
  var indexHint = $('[data-postal-hint]');

  /* ------------------------------------------------- which half is showing */

  function chosenDelivery() {
    return $$('[data-delivery-choice]').filter(function (r) { return r.checked; })[0] || null;
  }

  /* Hiding happens here and only here, which is also why the markup ships with
   * no `hidden` attribute on these three: a browser with the script blocked
   * shows the whole form and it still submits (§17 #107). Region and district
   * belong to both methods, so they appear as soon as either is chosen. */
  function syncBranch() {
    var choice = chosenDelivery();
    var branch = !!choice && choice.dataset.branch === '1';
    if (locationFields) locationFields.hidden = !choice;
    if (branchFields) branchFields.hidden = !choice || !branch;
    if (homeFields) homeFields.hidden = !choice || branch;
    syncTotals(choice);
  }

  /* The summary follows the choice immediately. The server recomputes it from
   * the locked cart lines anyway — this is a preview, never the number that
   * gets charged. */
  function syncTotals(choice) {
    var totalEl = $('[data-order-total]');
    var deliveryEl = $('[data-delivery-total]');
    if (!choice || !totalEl || !deliveryEl) return;
    var price = parseInt(choice.dataset.price, 10) || 0;
    var subtotal = parseInt(totalEl.dataset.subtotal, 10);
    if (isNaN(subtotal)) return;
    deliveryEl.textContent = format(price) + deliveryEl.dataset.suffix;
    totalEl.textContent = format(subtotal + price) + totalEl.dataset.suffix;
  }

  /* Thin spaces between thousands, the way the price filter renders them. */
  function format(n) {
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  }

  $$('[data-delivery-choice]').forEach(function (radio) {
    radio.addEventListener('change', syncBranch);
  });

  /* ------------------------------------------------------------- drawers */
  /* A native <select> cannot group Tumanlar and Shaharlar under headings, and
   * cannot carry a search field only where one is warranted. Both are the
   * reason these are drawers and not selects (§17 #87). */

  var picker = $('[data-picker]');
  var pickerList = $('[data-picker-list]');
  var pickerTitle = $('[data-picker-title]');
  var pickerSearch = $('[data-picker-search]');
  var pickerQuery = $('[data-picker-query]');
  var SEARCH_FROM = 15;     /* below this a search box is clutter */
  var release = null;
  var activeSelect = null;

  function closePicker() {
    if (!picker || picker.hidden) return;
    picker.hidden = true;
    if (release) { release(); release = null; }
    if (GX.lockScroll) GX.lockScroll(false);
    if (activeSelect) activeSelect.focus();
    activeSelect = null;
  }

  function openPicker(select, title, groups) {
    if (!picker) return;
    activeSelect = select;
    pickerTitle.textContent = title;

    var total = groups.reduce(function (n, g) { return n + g.items.length; }, 0);
    pickerSearch.hidden = total < SEARCH_FROM;
    pickerQuery.value = '';

    render(groups, '');
    pickerQuery.oninput = function () { render(groups, pickerQuery.value.trim().toLowerCase()); };

    picker.hidden = false;
    if (GX.lockScroll) GX.lockScroll(true);
    if (GX.trapFocus) release = GX.trapFocus(picker);
    (pickerSearch.hidden ? $('[data-picker-close]') : pickerQuery).focus();
  }

  function render(groups, query) {
    pickerList.innerHTML = '';
    groups.forEach(function (group) {
      var items = group.items.filter(function (it) {
        return !query || it.name.toLowerCase().indexOf(query) !== -1;
      });
      if (!items.length) return;
      if (group.label) {
        var head = document.createElement('p');
        head.className = 'picker__group';
        head.textContent = group.label;
        pickerList.appendChild(head);
      }
      items.forEach(function (it) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'picker__item';
        btn.textContent = it.name;
        btn.setAttribute('aria-pressed', String(activeSelect.value) === String(it.id));
        btn.addEventListener('click', function () {
          activeSelect.value = it.id;
          /* The select is still what submits, so changing it by hand has to
           * fire the same event a real change would. */
          activeSelect.dispatchEvent(new Event('change', { bubbles: true }));
          closePicker();
        });
        pickerList.appendChild(btn);
      });
    });
  }

  if (picker) {
    $$('[data-picker-close]').forEach(function (el) {
      el.addEventListener('click', closePicker);
    });
    picker.addEventListener('click', function (e) {
      if (e.target === picker) closePicker();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closePicker();
    });
  }

  /* A select that opens a drawer instead of its own list. The select stays in
   * the document and stays the thing that submits. */
  function drawerise(select, title, groupsFor) {
    if (!select || !picker) return;
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.id = select.id + '_drawer';
    btn.className = 'select select--drawer';
    btn.setAttribute('aria-haspopup', 'dialog');

    /* The field's own <label> points at the select, which is about to become
     * invisible — so the button borrows it. Without this a screen reader
     * announces the button as "Toshkent shahri, button" with no hint that the
     * field is the region, because the only thing naming it is the text of the
     * value it currently holds. */
    var field = document.querySelector('label[for="' + select.id + '"]');
    if (field) {
      if (!field.id) field.id = select.id + '_label';
      btn.setAttribute('aria-labelledby', field.id + ' ' + btn.id);
    }

    function label() {
      var opt = select.options[select.selectedIndex];
      btn.textContent = opt ? opt.textContent : '';
      btn.classList.toggle('is-empty', !select.value);
    }

    btn.addEventListener('click', function () { openPicker(select, title, groupsFor()); });
    select.addEventListener('change', label);
    select.classList.add('sr-only');
    select.setAttribute('tabindex', '-1');
    /* Hidden from assistive technology as well as from the eye: it is still the
     * element that submits, but the button above now carries the label and the
     * value, and announcing both makes the form sound like it has two region
     * fields. tabindex="-1" already keeps it out of the tab order, so nothing
     * focusable is being hidden. */
    select.setAttribute('aria-hidden', 'true');
    select.parentNode.insertBefore(btn, select.nextSibling);
    label();
  }

  /* ----------------------------------------------------- region/district */

  function districtGroups() {
    var data = DISTRICTS[regionSelect.value] || { district: [], city: [], other: [] };
    return [
      { label: districtSelect.dataset.groupDistricts, items: data.district || [] },
      { label: districtSelect.dataset.groupCities, items: data.city || [] },
      { label: '', items: data.other || [] },
    ];
  }

  function fillDistricts(keep) {
    if (!districtSelect) return;
    var previous = keep ? districtSelect.value : '';
    districtSelect.innerHTML = '';
    var blank = document.createElement('option');
    blank.value = '';
    blank.textContent = districtSelect.dataset.placeholder || '';
    districtSelect.appendChild(blank);

    districtGroups().forEach(function (group) {
      group.items.forEach(function (it) {
        var opt = document.createElement('option');
        opt.value = it.id;
        opt.textContent = it.name;
        if (String(it.id) === String(previous)) opt.selected = true;
        districtSelect.appendChild(opt);
      });
    });
    districtSelect.dispatchEvent(new Event('change', { bubbles: true }));
  }

  if (regionSelect) {
    regionSelect.addEventListener('change', function () {
      /* Changing the region CLEARS the district. A stale district from the
       * previous region submits silently, and a wrong address that looks
       * completely plausible is the worst kind there is (§17 #87). */
      fillDistricts(false);
      validateIndex();
    });
  }

  function chosenDistrictKind() {
    var id = districtSelect && districtSelect.value;
    if (!id) return null;
    var data = DISTRICTS[regionSelect.value] || {};
    var found = null;
    ['district', 'city', 'other'].forEach(function (kind) {
      (data[kind] || []).forEach(function (it) {
        if (String(it.id) === String(id)) found = kind;
      });
    });
    return found;
  }

  if (districtSelect) {
    districtSelect.addEventListener('change', function () {
      if (noteField) noteField.hidden = chosenDistrictKind() !== 'other';
    });
  }

  /* ------------------------------------------------- the postal index */
  /* The same check the server makes, said sooner. The server is still the
   * authority — this only saves the customer a round trip. */

  function regionPrefix() {
    var opt = regionSelect && regionSelect.options[regionSelect.selectedIndex];
    return opt ? (opt.dataset.prefix || '') : '';
  }

  function validateIndex() {
    if (!indexInput || !indexHint) return;
    var value = indexInput.value.trim();
    indexHint.classList.remove('field__error');
    if (!value) { indexHint.textContent = indexHint.dataset.default || ''; return; }

    if (!/^\d{6}$/.test(value)) {
      indexHint.textContent = indexInput.dataset.errorFormat;
      indexHint.classList.add('field__error');
      return;
    }
    var prefix = regionPrefix();
    if (prefix && value.indexOf(prefix) !== 0) {
      indexHint.textContent = indexInput.dataset.errorRegion;
      indexHint.classList.add('field__error');
      return;
    }
    indexHint.textContent = indexHint.dataset.default || '';
  }

  if (indexInput && indexHint) {
    indexHint.dataset.default = indexHint.textContent.trim();
    indexInput.addEventListener('input', validateIndex);
    indexInput.addEventListener('blur', validateIndex);
  }

  /* --------------------------------- leaving for Uzpost's own branch map */
  /* Sending someone off-site in the middle of checkout is a real drop-off
   * risk, so the form is saved before they go and restored if they come back
   * through history rather than through the new tab (§17 #92). */

  var KEY = 'gx-checkout-draft';

  function saveDraft() {
    try {
      var draft = {};
      $$('input, select, textarea', form).forEach(function (el) {
        if (!el.name || el.type === 'hidden' && !el.dataset.keep) {
          if (el.type !== 'hidden') return;
        }
        if (el.type === 'radio') { if (el.checked) draft[el.name] = el.value; }
        else if (el.name) draft[el.name] = el.value;
      });
      sessionStorage.setItem(KEY, JSON.stringify(draft));
    } catch (e) { /* private window, or storage is full — not worth failing for */ }
  }

  function restoreDraft() {
    var draft;
    try {
      draft = JSON.parse(sessionStorage.getItem(KEY) || 'null');
      sessionStorage.removeItem(KEY);
    } catch (e) { return; }
    if (!draft) return;
    Object.keys(draft).forEach(function (name) {
      var fields = $$('[name="' + name + '"]', form);
      fields.forEach(function (el) {
        if (el.type === 'radio') el.checked = el.value === draft[name];
        else el.value = draft[name];
      });
    });
  }

  $$('[data-leave-checkout]').forEach(function (link) {
    link.addEventListener('click', saveDraft);
  });

  /* ------------------------------------------------------------- the map */

  var sourceToggle = $('[data-address-source-toggle]');
  var sourceInput = $('[data-address-source]');
  var latInput = $('[data-latitude]');
  var lngInput = $('[data-longitude]');
  var addressInput = $('[data-address]');
  var mapBlock = $('[data-map]');

  function setSource(source) {
    if (sourceInput) sourceInput.value = source;
    $$('[data-source]', sourceToggle).forEach(function (btn) {
      btn.setAttribute('aria-pressed', String(btn.dataset.source === source));
    });
    if (mapBlock) mapBlock.hidden = source !== 'map';
    if (source !== 'map') {
      /* A typed address stores no coordinates at all, so the absence is
       * meaningful rather than missing data (§17 #88). */
      if (latInput) latInput.value = '';
      if (lngInput) lngInput.value = '';
    } else if (GX.map && GX.map.available()) {
      ensureMap();
    }
  }

  var mapStarted = false;
  function ensureMap() {
    if (mapStarted || !GX.map || !mapBlock) return;
    mapStarted = true;
    var canvas = $('[data-map-canvas]', mapBlock);
    var start = (latInput && latInput.value && lngInput && lngInput.value)
      ? { lat: parseFloat(latInput.value), lng: parseFloat(lngInput.value) }
      : null;
    GX.map.init(canvas, start);
    GX.map.onPinMove(function (pos) {
      if (!pos) return;
      if (latInput) latInput.value = pos.lat.toFixed(6);
      if (lngInput) lngInput.value = pos.lng.toFixed(6);
      GX.map.reverseGeocode(pos, function (text) {
        /* Fills the address in, and the customer can then edit it freely. It
         * never overwrites something they typed themselves. */
        if (text && addressInput && !addressInput.value.trim()) addressInput.value = text;
      });
    });
    var locate = $('[data-map-locate]', mapBlock);
    if (locate) locate.addEventListener('click', function () {
      GX.map.locate(function (pos) {
        if (!pos) return;
        if (latInput) latInput.value = pos.lat.toFixed(6);
        if (lngInput) lngInput.value = pos.lng.toFixed(6);
      });
    });
  }

  if (sourceToggle) {
    $$('[data-source]', sourceToggle).forEach(function (btn) {
      btn.addEventListener('click', function () { setSource(btn.dataset.source); });
    });
    /* The toggle only appears once a provider has actually loaded. Until then
     * there is nothing to toggle to, and offering a choice that leads to a
     * blank grey box is worse than not offering one. */
    if (GX.map) GX.map.ready(function () { sourceToggle.hidden = false; });
  }

  /* ------------------------------------------------------------- startup */

  restoreDraft();
  if (regionSelect && districtSelect) fillDistricts(true);
  drawerise(regionSelect, regionSelect && regionSelect.dataset.title, function () {
    return [{ label: '', items: $$('option', regionSelect).slice(1).map(function (o) {
      return { id: o.value, name: o.textContent };
    }) }];
  });
  drawerise(districtSelect, districtSelect && districtSelect.dataset.title, districtGroups);
  syncBranch();
  validateIndex();
  if (noteField && districtSelect) noteField.hidden = chosenDistrictKind() !== 'other';
})();
