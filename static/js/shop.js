/* The shop's list as one list: the next page of designs is added under the
 * last as the visitor nears the end of it, in place of page links.
 *
 * The page links stay in the document. A browser that runs no script pages
 * through them as before, and so does a search engine. This script hides them
 * and takes over only from the first page: any other page has designs before
 * it, and the links are the one way back to those (§17 #356).
 *
 * The next page is fetched as the ordinary page it is and its cards are
 * lifted out of it. A lighter answer made for a script would be a second
 * shape of the same address, and a browser's Back button can then show the
 * wrong one of the two.
 *
 * What has been added is kept for the tab. Coming back from a product, a
 * browser either restores the page whole or loads it again; when it loads it
 * again the list is rebuilt to the length it was left at before the browser
 * puts the scroll back, so the visitor lands on the design they left from.
 */
(function () {
  'use strict';

  var grid = document.querySelector('[data-more-grid]');
  var box = document.querySelector('[data-more]');
  if (!grid || !box || !box.hasAttribute('data-first')) return;
  if (!window.fetch || !window.IntersectionObserver || !window.DOMParser) return;

  var pager = box.querySelector('.pager');
  var fail = box.querySelector('[data-more-fail]');
  var retry = box.querySelector('[data-more-retry]');
  if (!fail || !retry) return;

  /* How long a page may take before the list says it did not arrive. A
   * connection that stalls neither answers nor fails. */
  var TIMEOUT = 15000;

  /* How many cards the page itself brought. The ones after them were added. */
  var own = grid.children.length;

  /* The address of the page after the one `doc` is, or '' on the last. */
  function nextOf(doc) {
    var link = doc.querySelector('.pager a[rel="next"]');
    return link ? new URL(link.getAttribute('href'), window.location.href).href : '';
  }

  var state = { html: [], next: nextOf(document) };
  if (!state.next) return;

  /* ---------------------------------------------------------------- kept */
  /* One list is kept, the one the visitor is on: its address is the key.
   * Storage can be full or switched off, and the list works without it. */
  var PREFIX = 'gx-more:';
  var KEY = PREFIX + window.location.pathname + window.location.search;

  function kept() {
    try {
      var found = JSON.parse(window.sessionStorage.getItem(KEY));
      return found && Array.isArray(found.html) && typeof found.next === 'string' ? found : null;
    } catch (e) { return null; }
  }

  function keep() {
    try {
      Object.keys(window.sessionStorage).forEach(function (key) {
        if (key.indexOf(PREFIX) === 0 && key !== KEY) window.sessionStorage.removeItem(key);
      });
      window.sessionStorage.setItem(KEY, JSON.stringify(state));
    } catch (e) { /* the list is simply not kept */ }
  }

  function forget() {
    try { window.sessionStorage.removeItem(KEY); } catch (e) { /* nothing to forget */ }
  }

  /* --------------------------------------------------------------- cards */
  /* Where a card leads, which is what makes two cards the same design. */
  function addressOf(card) {
    var link = card.querySelector('a[href]');
    return link ? link.getAttribute('href') : '';
  }

  /* Add the cards in `html` that the list does not have yet, and return them.
   *
   * A design is added once. The catalogue can change while the list is being
   * read: a design added to the shop pushes every other one along by a place,
   * and the next page then begins with the card this one ended on.
   *
   * Three things on a card were written for the page it came from and are put
   * right for this one. Its first photographs asked to be loaded at once,
   * because there they were the first screen. Its heart carries the token its
   * page was served with, which a sign-in since then has made stale. And its
   * heart sends a visitor who has to sign in back to that later page, which
   * is not the page they were on. */
  function add(html) {
    var holder = document.createElement('template');
    holder.innerHTML = html;

    var seen = {};
    Array.prototype.forEach.call(grid.children, function (card) {
      var address = addressOf(card);
      if (address) seen[address] = true;
    });
    var fresh = [];
    Array.prototype.slice.call(holder.content.children).forEach(function (card) {
      var address = addressOf(card);
      if (!address || seen[address]) { holder.content.removeChild(card); return; }
      seen[address] = true;
      fresh.push(card);
    });

    var token = document.querySelector('input[name="csrfmiddlewaretoken"]');
    var here = window.location.pathname + window.location.search;
    fresh.forEach(function (card) {
      Array.prototype.forEach.call(card.querySelectorAll('img'), function (img) {
        img.setAttribute('loading', 'lazy');
        img.removeAttribute('fetchpriority');
      });
      Array.prototype.forEach.call(card.querySelectorAll('input[name="csrfmiddlewaretoken"]'),
        function (input) { if (token) input.value = token.value; });
      Array.prototype.forEach.call(card.querySelectorAll('input[name="next"]'),
        function (input) { input.value = here; });
    });

    grid.appendChild(holder.content);
    return fresh;
  }

  /* A row of empty cards while the next page is on its way, so the list is
   * seen to be growing and nothing below it jumps when the cards arrive. */
  function ghosts() {
    var columns = window.getComputedStyle(grid).gridTemplateColumns.split(' ').length || 2;
    var made = [];
    for (var i = 0; i < columns; i += 1) {
      var card = document.createElement('div');
      card.className = 'card';
      card.setAttribute('aria-hidden', 'true');
      card.innerHTML = '<div class="skel skel--media"></div>' +
        '<div class="skel skel--line"></div><div class="skel skel--line is-short"></div>';
      grid.appendChild(card);
      made.push(card);
    }
    return made;
  }

  function drop(nodes) {
    nodes.forEach(function (node) { if (node.parentNode) node.parentNode.removeChild(node); });
  }

  /* ---------------------------------------------------------------- load */
  var busy = false;
  var watcher = null;

  /* The button while its answer is on the way: drawn as waiting, and said to be. */
  function waitingOn(on) {
    retry.classList.toggle('btn--loading', on);
    if (on) retry.setAttribute('aria-busy', 'true');
    else retry.removeAttribute('aria-busy');
  }

  /* `asked` is true when the visitor pressed the button, false when the list
   * loads by itself. Asked for, the answer goes to where the visitor is: the
   * first new design takes the keyboard, or the button keeps it. */
  function load(asked) {
    if (busy || !state.next) return;
    busy = true;
    if (asked) waitingOn(true);
    else fail.hidden = true;
    var waiting = ghosts();

    var stop = window.AbortController ? new window.AbortController() : null;
    var timer = stop ? window.setTimeout(function () { stop.abort(); }, TIMEOUT) : 0;
    var options = { credentials: 'same-origin', headers: { Accept: 'text/html' } };
    if (stop) options.signal = stop.signal;

    window.fetch(state.next, options)
      .then(function (response) {
        if (!response.ok) throw new Error('status ' + response.status);
        return response.text();
      })
      .then(function (text) {
        window.clearTimeout(timer);
        var page = new window.DOMParser().parseFromString(text, 'text/html');
        var cards = page.querySelector('[data-more-grid]');
        if (!cards || !cards.children.length) throw new Error('no cards');
        drop(waiting);
        var fresh = add(cards.innerHTML);
        /* A page that brings nothing new is the end of the list, whatever it
         * says comes after it. The list got shorter while it was being read,
         * and the last page is then handed out for every page asked for. */
        state.next = fresh.length ? nextOf(page) : '';
        state.html.push(cards.innerHTML);
        keep();
        busy = false;
        fail.hidden = true;
        waitingOn(false);
        if (fresh.length) {
          if (window.GX && window.GX.announce) window.GX.announce(box.getAttribute('data-loaded'));
          var first = asked ? fresh[0].querySelector('a[href]') : null;
          if (first) first.focus();
        }
        watch();
      })
      .catch(function () {
        /* The list stops where it is and says so; the button tries again.
         * Nothing is watched until then: taking the empty cards away brings
         * the end of the list back into view, and a list still being watched
         * would ask again at once, and again, for as long as the page failed. */
        window.clearTimeout(timer);
        drop(waiting);
        busy = false;
        if (watcher) { watcher.disconnect(); watcher = null; }
        waitingOn(false);
        fail.hidden = false;
        if (asked) retry.focus();
      });
  }

  /* Watching again asks the browser where the end of the list is now: on a
   * tall screen it can still be in view after a page is added, and nothing
   * would say so otherwise. */
  function watch() {
    if (watcher) watcher.disconnect();
    watcher = null;
    if (!state.next) return;
    watcher = new window.IntersectionObserver(function (entries) {
      if (entries.some(function (entry) { return entry.isIntersecting; })) load(false);
    }, { rootMargin: '0px 0px 800px 0px' });
    watcher.observe(box);
  }

  /* --------------------------------------------------------------- start */
  if (pager) pager.hidden = true;
  retry.addEventListener('click', function () { load(true); });

  var entry = window.performance && window.performance.getEntriesByType
    ? window.performance.getEntriesByType('navigation')[0] : null;
  var before = entry && entry.type === 'back_forward' ? kept() : null;
  if (before) {
    before.html.forEach(add);
    state = before;
  } else {
    forget();
  }

  /* As the page is left, what was added is written down as it stands then,
   * not as it arrived: a heart pressed on one of those cards is still pressed
   * when the list is rebuilt. A heart caught on its way to the server is
   * written down as settled, or it would come back unable to be pressed. */
  window.addEventListener('pagehide', function () {
    if (!state.html.length) return;
    var html = '';
    Array.prototype.slice.call(grid.children, own).forEach(function (card) {
      if (card.getAttribute('aria-hidden') === 'true') return;
      var copy = card.cloneNode(true);
      Array.prototype.forEach.call(copy.querySelectorAll('[aria-busy]'), function (node) {
        node.removeAttribute('aria-busy');
      });
      html += copy.outerHTML;
    });
    state.html = [html];
    keep();
  });

  watch();
})();
