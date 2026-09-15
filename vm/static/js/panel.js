/* GRAPHIX staff panel.
 *
 * The panel is the one part of the project allowed to assume JavaScript
 * (Kamronbek's decision, §17) — the storefront still works without it. This
 * file is small anyway, because the thing it upgrades was built as a real form
 * first: with the script the status saves in place and the row's badge
 * changes; without it the form posts and the page reloads, and the parcel
 * still gets packed.
 *
 * No framework and no build step (§3). One delegated listener, because the
 * orders list is twenty forms and twenty listeners is twenty things to unbind
 * the day the list starts paginating in place.
 *
 * Every sentence this file can show a person comes from `SAY`, which is read
 * out of a JSON block the shell renders through `{% trans %}`. A string typed
 * into a .js file is a string that cannot be translated (§4), and the panel is
 * read in three languages like everything else.
 */
var SAY = (function () {
  'use strict';
  var node = document.getElementById('pnl-i18n');
  var fallback = {failed: 'Saqlanmadi', upload: 'Yuklanmadi', remove: 'Oʻchirish',
                  tooMany: 'Koʻpi bilan {n} ta rasm.', tooBig: '“{name}” juda katta.',
                  badType: '“{name}” — qoʻllab-quvvatlanmaydigan tur.',
                  tooManyPixels: '“{name}” — rasm oʻlchami juda katta.',
                  notAnImage: '“{name}” — rasm sifatida oʻqib boʻlmadi.',
                  confirmDelete: '“{name}” oʻchirilsinmi?', noFile: 'Tanlanmagan'};
  var data = fallback;
  try {
    if (node) data = JSON.parse(node.textContent);
  } catch (e) { /* A broken block must not take the panel down with it. */ }
  return function (key, values) {
    var text = data[key] || fallback[key] || key;
    for (var name in (values || {})) {
      text = text.replace('{' + name + '}', values[name]);
    }
    return text;
  };
})();


(function () {
  'use strict';

  /* The submit button is only there for the no-JS path. With the script
     running, changing the select is the action — an extra tap to confirm what
     you just chose is an extra tap, on a phone, while holding a parcel. */
  document.querySelectorAll('[data-status-submit]').forEach(function (button) {
    button.hidden = true;
  });

  function badgeFor(form) {
    /* The badge belongs to the same card as the form on the list, and to the
       page header on the detail screen. Look up, then fall back to the page. */
    var card = form.closest('[data-order]');
    return (card && card.querySelector('[data-order-badge]'))
      || document.querySelector('[data-order-badge]');
  }

  function classFor(status) {
    if (status === 'done') return 'badge badge--success';
    if (status === 'cancelled') return 'badge badge--danger';
    if (status === 'paid') return 'badge badge--brand';
    return 'badge badge--info';
  }

  function save(form) {
    var select = form.querySelector('[data-status-select]');
    var badge = badgeFor(form);
    if (!select) return;

    /* The body is built BEFORE the control is disabled, and that order is the
       whole bug this control had: a disabled field is not in its form's data,
       so disabling first posted no `status` at all — the endpoint answered 400,
       the fall-back full post did the same, and the panel's most-used control
       had never once saved anything in a browser. */
    var body = new FormData(form);
    select.disabled = true;

    /* Re-enable, then post the real form. A disabled select would leave the
       reload just as empty-handed as the fetch was. */
    function fallBack() {
      select.disabled = false;
      form.submit();
    }

    fetch(form.action, {
      method: 'POST',
      body: body,
      /* Tells the view to answer JSON. The same URL serves the plain form
         post, so there is one route and one permission check, not two. */
      headers: {'X-Requested-With': 'fetch'},
      credentials: 'same-origin'
    }).then(function (response) {
      return response.json().catch(function () { return {ok: false}; });
    }).then(function (data) {
      if (!data.ok) {
        /* Put the control back where it was and say so out loud rather than
           leaving a select showing a status the order is not in. */
        window.alert(data.error || SAY('failed'));
        fallBack();
        return;
      }
      if (badge) {
        badge.className = classFor(data.status);
        badge.textContent = data.label;
      }
      select.disabled = false;
    }).catch(function () {
      /* Offline, or the session expired. The full post will either work or
         land on the login page, and either is more useful than a dead select. */
      fallBack();
    });
  }

  document.addEventListener('change', function (e) {
    var select = e.target.closest('[data-status-select]');
    if (!select) return;
    var form = select.closest('[data-status-form]');
    if (form) save(form);
  });

  /* Somebody who tabs to the button and presses it still gets the in-place
     save rather than a reload, even though the button is hidden for a pointer. */
  document.addEventListener('submit', function (e) {
    var form = e.target.closest('[data-status-form]');
    if (!form) return;
    e.preventDefault();
    save(form);
  });
})();


/* ------------------------------------------------------------- products */
/* Two jobs: saving one number from the catalogue list, and running the
   gallery. Both are in the panel, which is the one part of the project
   allowed to assume JavaScript (§17 #141). */
(function () {
  'use strict';

  function csrf() {
    var field = document.querySelector('[name=csrfmiddlewaretoken]');
    return field ? field.value : '';
  }

  function post(url, body) {
    return fetch(url, {
      method: 'POST',
      body: body,
      headers: {'X-Requested-With': 'fetch', 'X-CSRFToken': csrf()},
      credentials: 'same-origin'
    }).then(function (r) { return r.json().catch(function () { return {ok: false}; }); });
  }

  /* ------------------------------------------------- one number at a time */
  /* The list's stock boxes, price and switch. Each saves on its own, because
     the alternative is a Save button per row and nobody presses those. */
  function inlineSave(input) {
    var row = input.closest('[data-product]');
    if (!row) return;
    var field = input.dataset.inline;
    var body = new FormData();
    body.append('field', field);
    body.append('value', input.type === 'checkbox' ? (input.checked ? '1' : '0') : input.value);
    if (input.dataset.size) body.append('size', input.dataset.size);

    var box = input.closest('.stockbox');
    if (box) { box.classList.add('is-saving'); box.classList.remove('is-saved'); }

    post(row.dataset.inlineUrl, body)
      .then(function (data) {
        if (box) box.classList.remove('is-saving');
        if (!data.ok) {
          window.alert(data.error || SAY('failed'));
          return;
        }
        /* Show what was actually stored: "12 000" typed into the price box is
           saved as 12000, and a box still reading the typed form invites a
           second save of a number the server has already tidied. */
        if (input.type !== 'checkbox' && data.value !== undefined
            && String(data.value) !== input.value) {
          input.value = data.value;
        }
        if (box) {
          box.classList.add('is-saved');
          /* The box says out-of-stock the moment it is, rather than at the
             next page load — the owner is looking at it when they type.
             Red wins over amber, the same order the template renders them in:
             a size nobody can buy is not also "nearly gone". */
          box.classList.toggle('is-out', !data.purchasable);
          box.classList.toggle('is-low', !!data.purchasable && !!data.low);
          setTimeout(function () { box.classList.remove('is-saved'); }, 1200);
        }
      })
      .catch(function () { if (box) box.classList.remove('is-saving'); });
  }

  document.addEventListener('change', function (e) {
    var input = e.target.closest('[data-inline]');
    if (input) inlineSave(input);
  });
  /* Enter in a number box means "done", not "submit the page". */
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    var input = e.target.closest('[data-inline]');
    if (!input) return;
    e.preventDefault();
    input.blur();
  });

  /* ----------------------------------------------------- filtering chips */
  /* Forty tags in one block is a wall. Typing narrows it; a group with nothing
     left in it goes with them, so the headings do not sit over empty space.
     A chip that is already ticked always stays visible — hiding a choice
     somebody has made is how a filter loses a selection without saying so. */
  var chipBox = document.querySelector('[data-chips]');
  if (chipBox) {
    var chipFilter = chipBox.querySelector('[data-chip-filter]');
    var chipEmpty = chipBox.querySelector('[data-chip-empty]');
    chipFilter.addEventListener('input', function () {
      var needle = chipFilter.value.trim().toLowerCase();
      var shown = 0;
      chipBox.querySelectorAll('[data-chip-group]').forEach(function (group) {
        var visible = 0;
        group.querySelectorAll('.chip').forEach(function (chip) {
          var box = chip.querySelector('input');
          var hit = !needle || (chip.dataset.chip || '').toLowerCase().indexOf(needle) >= 0;
          var keep = hit || (box && box.checked);
          chip.classList.toggle('is-hidden', !keep);
          if (keep) visible += 1;
        });
        group.classList.toggle('is-hidden', visible === 0);
        shown += visible;
      });
      if (chipEmpty) chipEmpty.hidden = shown > 0;
    });
  }

  /* ------------------------------------------------------ filtering rows */
  /* The same idea one level up: a list of editable rows, narrowed by typing.
     The tag list on the settings screen is the one that needed it — the owner
     writes the tags, so it only grows, and forty rows of four boxes each is a
     screen nobody scrolls to the bottom of.
     Every language is in the haystack, because the tag somebody remembers may
     be the Russian one. Client side, because the whole list is already here:
     a round trip per keystroke to filter rows already on the page is latency
     bought with nothing. */
  document.querySelectorAll('[data-rowsearch]').forEach(function (box) {
    var input = box.querySelector('[data-rowsearch-input]');
    var empty = box.querySelector('[data-rowsearch-empty]');
    var rows = box.querySelectorAll('[data-rowsearch-row]');
    if (!input || !rows.length) return;
    input.addEventListener('input', function () {
      var needle = input.value.trim().toLowerCase();
      var shown = 0;
      rows.forEach(function (row) {
        var hit = !needle || (row.dataset.search || '').toLowerCase().indexOf(needle) >= 0;
        row.classList.toggle('is-hidden', !hit);
        if (hit) shown += 1;
      });
      if (empty) empty.hidden = shown > 0;
    });
  });

  /* --------------------------------------------------------- the gallery */
  var editor = document.querySelector('[data-gallery-editor]');
  if (!editor) return;

  var list = editor.querySelector('[data-shots]');
  var input = editor.querySelector('[data-shots-input]');
  var error = editor.querySelector('[data-shots-error]');
  var url = editor.dataset.url;
  var maxShots = parseInt(editor.dataset.max, 10) || 8;
  var maxBytes = parseInt(editor.dataset.maxBytes, 10) || 0;
  var maxPixels = parseInt(editor.dataset.maxPixels, 10) || 0;

  function say(message) {
    error.textContent = message || '';
    error.hidden = !message;
  }

  /* Checked here as well as on the server, and the reason is the plan's: the
     owner should never wait thirty seconds for an upload that will be
     rejected. The server checks again, because a browser is not a guard. */
  function check(file) {
    return new Promise(function (resolve) {
      if (maxBytes && file.size > maxBytes) {
        resolve(SAY('tooBig', {name: file.name}));
        return;
      }
      /* An empty type is not a refusal: some Android pickers hand over a file
         with no MIME type at all, and the server reads the bytes regardless. */
      if (file.type && !/^image\/(jpeg|png|webp|avif)$/.test(file.type)) {
        resolve(SAY('badType', {name: file.name}));
        return;
      }
      if (!maxPixels) { resolve(''); return; }
      /* Dimensions need the file decoded, so this is the one check that
         cannot be a property read. */
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () {
        URL.revokeObjectURL(url);
        resolve(img.naturalWidth * img.naturalHeight > maxPixels
          ? SAY('tooManyPixels', {name: file.name}) : '');
      };
      img.onerror = function () {
        URL.revokeObjectURL(url);
        resolve(SAY('notAnImage', {name: file.name}));
      };
      img.src = url;
    });
  }

  function render(images) {
    list.innerHTML = '';
    images.forEach(function (image) {
      var li = document.createElement('li');
      li.className = 'shot';
      li.draggable = true;
      li.dataset.id = image.id;
      var img = document.createElement('img');
      img.src = image.url;
      img.alt = '';
      img.loading = 'lazy';
      var x = document.createElement('button');
      x.type = 'button';
      x.className = 'shot__x';
      x.dataset.shotDelete = image.id;
      x.setAttribute('aria-label', SAY('remove'));
      x.innerHTML = '<svg class="i i--sm" aria-hidden="true"><use href="#i-close"></use></svg>';
      li.appendChild(img);
      li.appendChild(x);
      list.appendChild(li);
    });
  }

  input.addEventListener('change', function () {
    var files = Array.prototype.slice.call(input.files);
    if (!files.length) return;
    say('');

    if (list.children.length + files.length > maxShots) {
      say(SAY('tooMany', {n: maxShots}));
      input.value = '';
      return;
    }

    Promise.all(files.map(check)).then(function (problems) {
      var first = problems.filter(Boolean)[0];
      if (first) { say(first); input.value = ''; return; }

      var body = new FormData();
      body.append('action', 'add');
      files.forEach(function (file) { body.append('images', file); });
      post(url, body).then(function (data) {
        input.value = '';
        if (!data.ok) { say(data.error || SAY('upload')); return; }
        render(data.images);
      });
    });
  });

  list.addEventListener('click', function (e) {
    var button = e.target.closest('[data-shot-delete]');
    if (!button) return;
    var body = new FormData();
    body.append('action', 'delete');
    body.append('id', button.dataset.shotDelete);
    post(url, body).then(function (data) {
      if (data.ok) render(data.images);
    });
  });

  /* Drag to reorder. HTML's own drag events rather than a library: §3 says no
     build step, and this is forty lines. */
  var dragging = null;

  list.addEventListener('dragstart', function (e) {
    dragging = e.target.closest('.shot');
    if (!dragging) return;
    dragging.classList.add('is-dragging');
    e.dataTransfer.effectAllowed = 'move';
    /* Firefox will not start a drag without data on the transfer. */
    e.dataTransfer.setData('text/plain', dragging.dataset.id);
  });

  list.addEventListener('dragover', function (e) {
    if (!dragging) return;
    e.preventDefault();
    var over = e.target.closest('.shot');
    if (!over || over === dragging) return;
    list.querySelectorAll('.is-over').forEach(function (el) {
      el.classList.remove('is-over');
    });
    over.classList.add('is-over');
    var after = over.getBoundingClientRect().left + over.offsetWidth / 2 < e.clientX;
    list.insertBefore(dragging, after ? over.nextSibling : over);
  });

  list.addEventListener('dragend', function () {
    if (!dragging) return;
    dragging.classList.remove('is-dragging');
    list.querySelectorAll('.is-over').forEach(function (el) {
      el.classList.remove('is-over');
    });
    dragging = null;

    var body = new FormData();
    body.append('action', 'order');
    list.querySelectorAll('.shot').forEach(function (shot) {
      body.append('ids', shot.dataset.id);
    });
    post(url, body);
  });
})();


/* ------------------------------------------- moderation, inbox, reference */
/* Three more screens, all the same shape: a control changes, one thing saves,
   the page says so. Sharing the fetch helper below rather than each screen
   bringing its own. */
(function () {
  'use strict';

  function token() {
    var field = document.querySelector('[name=csrfmiddlewaretoken]');
    return field ? field.value : '';
  }

  function send(url, body) {
    return fetch(url, {
      method: 'POST', body: body,
      headers: {'X-Requested-With': 'fetch', 'X-CSRFToken': token()},
      credentials: 'same-origin'
    }).then(function (r) { return r.json().catch(function () { return {ok: false}; }); });
  }

  /* ------------------------------------------------------------ reviews */
  document.addEventListener('click', function (e) {
    var button = e.target.closest('[data-mod]');
    if (!button) return;
    var card = button.closest('[data-review]');
    if (!card) return;

    var body = new FormData();
    body.append('status', button.dataset.mod);
    card.querySelectorAll('[data-mod]').forEach(function (b) { b.disabled = true; });

    send(card.dataset.url, body).then(function (data) {
      card.querySelectorAll('[data-mod]').forEach(function (b) { b.disabled = false; });
      if (!data.ok) { window.alert(data.error || SAY('failed')); return; }

      var badge = card.querySelector('[data-mod-badge]');
      if (badge) {
        badge.className = 'badge ' + (data.status === 'approved'
          ? 'badge--success' : 'badge--danger');
        /* The label comes from the server, because the button says what you
           are about to do and the badge says what the review now is. Copying
           the button's own text put "Tasdiqlash" — approve — where
           "Tasdiqlangan" — approved — belongs. */
        badge.textContent = data.label;
      }
      /* The product's rating moves with the decision, and seeing it move is
         the confirmation that the approval actually did something. Rendered
         by the server, so the line reads the same before and after. */
      var rating = card.querySelector('[data-mod-rating]');
      if (rating) rating.textContent = data.rating_line;
      /* Only the decision that would still change something stays on screen:
         an approved review offering "Approve" is a button that does nothing. */
      card.querySelectorAll('[data-mod]').forEach(function (b) {
        b.hidden = b.dataset.mod === data.status;
      });
      /* Dimmed, not removed: a decision made by accident should still be on
         the screen a second later, with its own page one click away. */
      card.classList.add('is-done');
    });
  });

  /* -------------------------------------------------------------- inbox */
  document.addEventListener('change', function (e) {
    var box = e.target.closest('[data-msg-read]');
    if (!box) return;
    var card = box.closest('[data-msg]');
    if (!card) return;

    var body = new FormData();
    body.append('value', box.checked ? '1' : '0');
    send(card.dataset.url, body).then(function (data) {
      if (!data.ok) return;
      card.classList.toggle('is-unread', !data.value);
      /* The count in the header is the same number the dashboard shows; the
         server has already worked it out, so the page should not go stale. */
      var counter = document.querySelector('[data-unread-count]');
      if (counter) {
        counter.textContent = data.unread;
        counter.hidden = !data.unread;
      }
    });
  });

  /* ---------------------------------------------------------- reference */
  /* One endpoint behind all of these, and it is safe because of an allowlist
     on the server — `panel/reference.py` names what may be written. */
  function saveField(control) {
    var row = control.closest('[data-ref]');
    if (!row) return;

    var body = new FormData();
    body.append('field', control.dataset.refField);
    body.append('value', control.type === 'checkbox'
      ? (control.checked ? '1' : '0') : control.value);

    control.classList.add('is-saving-field');
    /* The URL comes from the row, written by `{% url %}`. Assembling it here
       would mean guessing the language prefix, which is the bug this file
       already made once on the catalogue list. */
    send(row.dataset.refUrl, body)
      .then(function (data) {
        control.classList.remove('is-saving-field');
        if (!data.ok) { window.alert(data.error || SAY('failed')); return; }
        if (control.type !== 'checkbox' && data.value !== undefined
            && String(data.value) !== control.value) {
          control.value = data.value;
        }
        control.classList.add('is-saved-field');
        setTimeout(function () { control.classList.remove('is-saved-field'); }, 1200);
      })
      .catch(function () { control.classList.remove('is-saving-field'); });
  }

  document.addEventListener('change', function (e) {
    var control = e.target.closest('[data-ref-field]');
    if (control) saveField(control);
  });

  /* ------------------------------------------------- removing a row */
  /* Confirmed first, because this is the one control on the panel that
     destroys something, and then removed from the page rather than reloading
     it — the settings screen is long and a reload loses your place in it.
     What cannot be removed is refused by the server, not by the button: the
     database is what knows whether a tag kind still has tags on it. */
  document.addEventListener('click', function (e) {
    var button = e.target.closest('[data-ref-delete]');
    if (!button) return;
    var row = button.closest('[data-ref]');
    if (!row) return;
    if (!window.confirm(SAY('confirmDelete', {name: button.dataset.refName || ''}))) return;

    button.disabled = true;
    send(button.dataset.refDelete, new FormData()).then(function (data) {
      button.disabled = false;
      if (!data.ok) { window.alert(data.error || SAY('failed')); return; }
      row.remove();
    });
  });

  /* The chart upload is a styled label over a hidden input, so the browser's
     own "no file chosen" — in English, on an Uzbek screen — never appears.
     Nothing else would say a file had been picked, so this does. */
  document.addEventListener('change', function (e) {
    var input = e.target.closest('[data-file-name]');
    if (!input) return;
    var label = input.parentElement.querySelector('[data-file-label]');
    if (label) label.textContent = input.files.length ? input.files[0].name
                                                     : SAY('noFile');
  });
})();
