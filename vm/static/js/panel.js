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
