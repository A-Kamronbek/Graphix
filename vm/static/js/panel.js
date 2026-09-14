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
 */
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

    select.disabled = true;
    var body = new FormData(form);

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
        window.alert(data.error || select.dataset.error || 'Saqlanmadi');
        form.submit();
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
      form.submit();
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
          window.alert(data.error || 'Saqlanmadi');
          return;
        }
        if (box) {
          box.classList.add('is-saved');
          /* The box says out-of-stock the moment it is, rather than at the
             next page load — the owner is looking at it when they type. */
          box.classList.toggle('is-out', !data.purchasable);
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
        resolve('“' + file.name + '” juda katta.');
        return;
      }
      if (!/^image\/(jpeg|png|webp|avif)$/.test(file.type)) {
        resolve('“' + file.name + '” — qoʻllab-quvvatlanmaydigan tur.');
        return;
      }
      if (!maxPixels) { resolve(''); return; }
      /* Dimensions need the file decoded, so this is the one check that
         cannot be a property read. createImageBitmap does it off the main
         thread where it exists. */
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () {
        URL.revokeObjectURL(url);
        resolve(img.naturalWidth * img.naturalHeight > maxPixels
          ? '“' + file.name + '” — rasm oʻlchami juda katta.' : '');
      };
      img.onerror = function () {
        URL.revokeObjectURL(url);
        resolve('“' + file.name + '” — rasm sifatida oʻqib boʻlmadi.');
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
      x.setAttribute('aria-label', 'Oʻchirish');
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
      say('Koʻpi bilan ' + maxShots + ' ta rasm.');
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
        if (!data.ok) { say(data.error || 'Yuklanmadi'); return; }
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
      if (!data.ok) { window.alert(data.error || 'Saqlanmadi'); return; }

      var badge = card.querySelector('[data-mod-badge]');
      if (badge) {
        badge.className = 'badge ' + (data.status === 'approved'
          ? 'badge--success' : 'badge--danger');
        badge.textContent = button.textContent.trim();
      }
      /* The product's rating moves with the decision, and seeing it move is
         the confirmation that the approval actually did something. */
      var rating = card.querySelector('[data-mod-rating]');
      if (rating) rating.textContent = data.rating + ' — ' + data.count;
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
        if (!data.ok) { window.alert(data.error || 'Saqlanmadi'); return; }
        control.classList.add('is-saved-field');
        setTimeout(function () { control.classList.remove('is-saved-field'); }, 1200);
      })
      .catch(function () { control.classList.remove('is-saving-field'); });
  }

  document.addEventListener('change', function (e) {
    var control = e.target.closest('[data-ref-field]');
    if (control) saveField(control);
  });
})();
