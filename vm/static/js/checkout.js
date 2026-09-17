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

  /* --------------------------------- matching a place name to one of ours */
  /* Google names a place in its own words: Chilonzor comes back as
   * "Chilanzar District" in English and "Чиланзарский район" in Russian, and
   * the classifier we built `regions.csv` from spells it "Chilonzor tumani".
   * So the comparison has to survive both a different transliteration and a
   * different suffix — otherwise a dropped pin fills nothing, which is worse
   * than not offering to fill it (§17 #116). */

  /* Words that say what KIND of place something is rather than which one.
   * One line on purpose: a regular expression literal cannot be wrapped. */
  var NOISE = new RegExp(
    '(^| )(tumani|tuman|shahri|shahar|shaharchasi|viloyati|viloyat|respublikasi'
    + '|rayon|rayonu|rajon|raion|district|districts|city|town|region|province'
    + '|район|районы'
    + '|районный'
    + '|городской'
    + '|город|области'
    + '|область|обл)( |$)', 'g');

  function normalise(value) {
    var out = String(value || '')
      .toLowerCase()
      /* The apostrophes Uzbek uses for oʻ and gʻ, however they were typed:
       * U+02BB, U+02BC, U+2018, U+2019, U+0027, U+00B4, U+0060. */
      .replace(/[ʻʼ‘’'´`]/g, '')
      .replace(/[^a-zЀ-ӿ0-9]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    /* Twice: the words can sit next to each other ("shahar tumani"), and one
     * pass consumes the space the next match needs. */
    out = out.replace(NOISE, ' ').replace(NOISE, ' ');
    return out.replace(/\s+/g, ' ').trim();
  }

  /* Edit distance, capped — two short strings, so the simple table is fine. */
  function distance(a, b) {
    if (a === b) return 0;
    if (!a.length || !b.length) return Math.max(a.length, b.length);
    var prev = [], row = [], i, j;
    for (j = 0; j <= b.length; j++) prev[j] = j;
    for (i = 1; i <= a.length; i++) {
      row = [i];
      for (j = 1; j <= b.length; j++) {
        row[j] = Math.min(prev[j] + 1, row[j - 1] + 1,
                          prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      }
      prev = row;
    }
    return prev[b.length];
  }

  /* A deliberately strict test. A wrong district is a parcel sent to the wrong
   * place and it looks completely plausible on the form, so anything less than
   * a near-exact match leaves the field alone for the customer to fill. */
  function same(a, b) {
    a = normalise(a); b = normalise(b);
    if (!a || !b) return false;
    if (a === b) return true;
    var shortest = Math.min(a.length, b.length);
    if (shortest < 4) return false;
    var allowed = shortest >= 6 ? 2 : 1;
    return distance(a, b) <= allowed;
  }

  /* Every option one name could be. */
  function matches(candidate, options) {
    return options.filter(function (option) {
      return option.names.some(function (name) { return same(candidate, name); });
    });
  }

  /* Both pickers below follow the same rule: an ambiguous name is skipped
   * rather than resolved by position. First-in-the-list is not a reason to
   * believe anything, and a field left empty costs the customer one tap while
   * a field filled wrongly costs them the parcel. */

  /* Is this the name of a province, or of a city in its own right? Read from
   * the raw name, before `normalise` throws those very words away. */
  function kindOf(name) {
    var s = String(name || '').toLowerCase();
    if (/viloyat|region|област/.test(s)) return 'province';
    if (/shahri|shahar|\bcity\b|город/.test(s)) return 'city';
    return '';
  }

  function optionKind(option) {
    for (var i = 0; i < option.names.length; i++) {
      var k = kindOf(option.names[i]);
      if (k) return k;
    }
    return '';
  }

  /* Tashkent is why this is not just `pick`.
   *
   * Google calls the capital "Toshkent" and the province around it "Toshkent
   * viloyati" — and once the word *viloyat* is stripped as noise, both are the
   * single word "toshkent" and match both of our rows. Sending a city order to
   * the province is a parcel that goes to the wrong place and a form that
   * looks perfectly filled in, so the collision is broken on evidence rather
   * than left to chance: the province wins when Google said province, and the
   * city wins when the name it gave for the region is also the name it gave
   * for the locality — which is what happens, and only happens, inside a city
   * that is its own region. Anything else leaves the field empty. */
  function pickRegion(parts, options) {
    var admin = parts.administrative_area_level_1;
    var locality = parts.locality;
    var candidates = [admin, locality];

    for (var c = 0; c < candidates.length; c++) {
      if (!candidates[c]) continue;
      var found = matches(candidates[c], options);
      if (found.length === 1) return found[0].value;
      if (found.length > 1) {
        var want = kindOf(candidates[c]);
        if (!want && locality && admin && same(admin, locality)) want = 'city';
        if (!want) continue;
        var narrowed = found.filter(function (o) { return optionKind(o) === want; });
        if (narrowed.length === 1) return narrowed[0].value;
      }
    }
    return null;
  }

  function regionOptions() {
    return $$('option', regionSelect).slice(1).map(function (opt) {
      return { value: opt.value, names: (opt.dataset.match || '').split('|') };
    });
  }

  function districtOptions(regionId) {
    var data = DISTRICTS[regionId] || {};
    var out = [];
    ['district', 'city', 'other'].forEach(function (kind) {
      (data[kind] || []).forEach(function (it) {
        out.push({ value: String(it.id), names: it.match || [it.name], kind: kind });
      });
    });
    return out;
  }

  /* The same collision one level down, and the same way out of it.
   *
   * Most provinces have a *tuman* and a *shahar* of the same name — Samarqand
   * tumani is the countryside around Samarqand shahri, and they are different
   * places with different post offices. Stripping the word that distinguishes
   * them makes both rows match the one name Google gives, so the row's own
   * `kind` decides: a `locality` is a city, an administrative area or a
   * sublocality is a district. `kind` is the column Phase 6d added for the
   * drawer's headings (§17 #87), doing a second job it happens to be exactly
   * right for. */
  function pickDistrict(parts, options) {
    var candidates = [
      { name: parts.administrative_area_level_2, kind: 'district' },
      { name: parts.sublocality_level_1, kind: 'district' },
      { name: parts.sublocality, kind: 'district' },
      { name: parts.locality, kind: 'city' },
    ];
    for (var c = 0; c < candidates.length; c++) {
      if (!candidates[c].name) continue;
      var found = matches(candidates[c].name, options);
      if (found.length === 1) return found[0].value;
      if (found.length > 1) {
        var want = kindOf(candidates[c].name) || candidates[c].kind;
        var narrowed = found.filter(function (o) { return o.kind === want; });
        if (narrowed.length === 1) return narrowed[0].value;
      }
    }
    return null;
  }

  /* ------------------------------------------------------------- the map */

  var sourceToggle = $('[data-address-source-toggle]');
  var sourceInput = $('[data-address-source]');
  var latInput = $('[data-latitude]');
  var lngInput = $('[data-longitude]');
  var addressInput = $('[data-address]');
  var mapBlock = $('[data-map]');
  var mapError = mapBlock && $('[data-map-error]', mapBlock);

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
    } else {
      loadMap();
    }
  }

  /* The provider is fetched on the first tap of "Xaritadan" and never before
   * (§18 #34), so this is where waiting for it lives. The answer is one of
   * two: the map appears, or the toggle goes back to manual entry and says
   * why — a customer looking at an empty grey box has no way to know that the
   * form still works. */
  function loadMap() {
    if (!GX.map || !mapBlock) return;
    if (mapError) mapError.hidden = true;
    GX.map.load(mapBlock.dataset.mapSrc, function (ok) {
      if (ok) {
        ensureMap();
        return;
      }
      if (mapError) mapError.hidden = false;
      setSource('manual');
    });
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
      GX.map.reverseGeocode(pos, applyPlace);
    });
    var locate = $('[data-map-locate]', mapBlock);
    if (locate) locate.addEventListener('click', function () {
      GX.map.locate(function (pos) {
        if (!pos) return;
        if (latInput) latInput.value = pos.lat.toFixed(6);
        if (lngInput) lngInput.value = pos.lng.toFixed(6);
        GX.map.reverseGeocode(pos, applyPlace);
      });
    });
  }

  /* What a dropped pin does to the form.
   *
   * Moving the pin is a deliberate act, so it fills all three fields rather
   * than only an empty one: region, district and the street line, each of them
   * still editable afterwards. That is a change from the original rule, which
   * only filled the address and only when it was blank — a customer who has
   * just pointed at their own front door should not then have to find their
   * district in a list of two hundred (§17 #117, amending #91).
   *
   * Nothing here is ever a guess. A name that does not match one of our rows
   * to within an edit or two leaves that field exactly as it was: an empty
   * district the customer fills in themselves is a small annoyance, and a
   * wrong one that looks plausible is a parcel in another district. */
  function applyPlace(text, parts) {
    parts = parts || {};

    var regionId = pickRegion(parts, regionOptions());
    if (regionId && regionSelect && regionSelect.value !== regionId) {
      regionSelect.value = regionId;
      /* The real change event: it clears the district, refills the list for
       * the new region and relabels the drawer button, exactly as it does when
       * a person picks a region by hand. */
      regionSelect.dispatchEvent(new Event('change', { bubbles: true }));
    }

    var current = regionSelect ? regionSelect.value : '';
    if (current && districtSelect) {
      var districtId = pickDistrict(parts, districtOptions(current));
      if (districtId) {
        districtSelect.value = districtId;
        districtSelect.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }

    if (addressInput) {
      /* The street line only — the region and the district are their own
       * fields now, and repeating them here is how an address ends up saying
       * "Toshkent, Toshkent, Chilonzor, Chilonzor". */
      var street = [parts.route, parts.street_number].filter(Boolean).join(' ');
      if (street) addressInput.value = street;
      else if (text && !addressInput.value.trim()) addressInput.value = text;
    }
  }

  if (sourceToggle) {
    $$('[data-source]', sourceToggle).forEach(function (btn) {
      btn.addEventListener('click', function () { setSource(btn.dataset.source); });
    });
    /* The toggle appears when there is a map to offer — which since §18 #34 is
     * known from the page rather than from a loaded script: `data-map-src` is
     * the provider's address, rendered only when a key is configured. Waiting
     * for the script to arrive would mean fetching it, which is the thing that
     * is not done until somebody asks.
     *
     * The state the page came back with is restored here too. Submitting the
     * form with a field missing re-renders it with `address_source` still set
     * to `map` and the coordinates still in their hidden inputs — but nothing
     * put the map back on screen, so the customer was shown the manual form
     * and their pin survived only as two numbers they could not see. The pin
     * is still there; now so is the map (§17 #118). */
    if (mapBlock && mapBlock.dataset.mapSrc) {
      sourceToggle.hidden = false;
      if (sourceInput && sourceInput.value === 'map') setSource('map');
    }
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
