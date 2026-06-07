// VM Graphics — main.js
// keep it tiny, no frameworks

(() => {
  // ---- mobile drawer ----
  const burger = document.querySelector('[data-burger]');
  const drawer = document.querySelector('[data-drawer]');
  if (burger && drawer) {
    burger.addEventListener('click', () => drawer.classList.toggle('is-open'));
    drawer.querySelectorAll('a').forEach(a => a.addEventListener('click', () => drawer.classList.remove('is-open')));
  }

  // ---- duplicate marquee track for seamless scroll ----
  document.querySelectorAll('.marquee__track').forEach(track => {
    if (track.dataset.dup === '1') return;
    track.dataset.dup = '1';
    track.innerHTML = track.innerHTML + track.innerHTML;
  });

  // ---- qty steppers (item + cart) ----
  document.querySelectorAll('[data-qty]').forEach(box => {
    // IMPORTANT: target the quantity input by name, not just 'input'.
    // On the cart page [data-qty] is a <form> that also contains a hidden
    // CSRF input — querySelector('input') would grab that one and corrupt it.
    const inp = box.querySelector('input[name="quantity"]');
    if (!inp) return;

    const clamp = (n) => Math.max(1, Math.min(99, n));
    const isForm = box.tagName === 'FORM';

    // bump value and (if we're inside a cart form) submit it.
    const bump = (delta) => {
      inp.value = clamp((parseInt(inp.value, 10) || 1) + delta);
      if (isForm) box.submit();
    };

    box.querySelector('[data-qty-dec]')?.addEventListener('click', () => bump(-1));
    box.querySelector('[data-qty-inc]')?.addEventListener('click', () => bump(+1));

    // strip non-digits while typing and cap at 99
    inp.addEventListener('input', () => {
      let v = inp.value.replace(/\D+/g, '');
      if (v === '') { inp.value = ''; return; }
      if (parseInt(v, 10) > 99) v = '99';
      inp.value = v;
    });
    // on blur, snap back to a valid value (no empty inputs left behind).
    // Do NOT auto-submit here — user might have tabbed away without changing it.
    inp.addEventListener('blur', () => {
      const n = parseInt(inp.value, 10);
      inp.value = clamp(isNaN(n) ? 1 : n);
    });
  });

  // ---- variant picker (item page) ----
  // Colour drives the size availability and the price.
  // Data shape from server: { "<colour_id>:<size_id>": {price, available, id}, ... }
  const variantForm = document.querySelector('[data-variant-form]');
  if (variantForm) {
    let variants = {};
    try { variants = JSON.parse(variantForm.dataset.variants || '{}'); } catch (e) { variants = {}; }

    const colourInput = variantForm.querySelector('input[name="colour"]');
    const sizeInput   = variantForm.querySelector('input[name="size"]');
    const priceEl     = document.querySelector('[data-price-display]');
    const submitBtn   = variantForm.querySelector('button[type="submit"]');
    const swatches    = variantForm.querySelectorAll('[data-swatch]');
    const sizes       = variantForm.querySelectorAll('[data-size]');

    const fmtPrice = (n) => `${Math.round(n).toLocaleString('en-US').replace(/,/g, ' ')} UZS`;

    const getVariant = (cId, sId) => variants[`${cId || ''}:${sId || ''}`] || null;

    // Sync the UI after a colour or size change.
    const sync = () => {
      const cId = colourInput?.value || '';
      const sId = sizeInput?.value || '';

      // 1. cross out sizes that aren't available for the chosen colour
      sizes.forEach(el => {
        const v = getVariant(cId, el.dataset.size);
        const isOos = !v || !v.available;
        el.classList.toggle('is-oos', isOos);
        if (isOos) el.classList.remove('is-active');
      });

      // 2. if current size is now OOS, auto-pick first available size for this colour
      let current = getVariant(cId, sId);
      if (!current || !current.available) {
        const firstOk = Array.from(sizes).find(el => !el.classList.contains('is-oos'));
        if (firstOk) {
          sizes.forEach(s => s.classList.remove('is-active'));
          firstOk.classList.add('is-active');
          if (sizeInput) sizeInput.value = firstOk.dataset.size;
          current = getVariant(cId, firstOk.dataset.size);
        } else {
          if (sizeInput) sizeInput.value = '';
          current = null;
        }
      }

      // 3. update price
      if (priceEl) {
        if (current) priceEl.textContent = fmtPrice(current.price);
        else priceEl.textContent = '— UZS';
      }

      // 4. enable/disable submit + swap label
      if (submitBtn) {
        const ok = !!(current && current.available);
        submitBtn.disabled = !ok;
        // remember original label once so we can restore it
        if (!submitBtn.dataset.labelOk) {
          submitBtn.dataset.labelOk = submitBtn.textContent.trim();
        }
        const labelOos = submitBtn.dataset.labelOos || 'Mavjud emas';
        submitBtn.textContent = ok ? submitBtn.dataset.labelOk : labelOos;
      }
    };

    swatches.forEach(el => {
      el.addEventListener('click', () => {
        swatches.forEach(s => s.classList.remove('is-active'));
        el.classList.add('is-active');
        if (colourInput) colourInput.value = el.dataset.swatch;
        sync();
      });
    });

    sizes.forEach(el => {
      el.addEventListener('click', () => {
        if (el.classList.contains('is-oos')) return;
        sizes.forEach(s => s.classList.remove('is-active'));
        el.classList.add('is-active');
        if (sizeInput) sizeInput.value = el.dataset.size;
        sync();
      });
    });

    // run once on load so initial state is consistent with the picked colour
    sync();
  }

  // ---- product gallery carousel ----
  document.querySelectorAll('[data-gallery]').forEach(gallery => {
    const track  = gallery.querySelector('[data-gallery-track]');
    const slides = track ? track.querySelectorAll('.gallery__slide') : [];
    if (!track || slides.length === 0) return;

    const prevBtn = gallery.querySelector('[data-gallery-prev]');
    const nextBtn = gallery.querySelector('[data-gallery-next]');
    const dotsEl  = gallery.querySelector('[data-gallery-dots]');
    const count   = slides.length;
    let index = 0;

    // build dot indicators
    const dots = [];
    if (dotsEl) {
      for (let i = 0; i < count; i++) {
        const d = document.createElement('button');
        d.type = 'button';
        d.className = 'gallery__dot';
        d.setAttribute('aria-label', `image ${i + 1}`);
        d.addEventListener('click', () => goTo(i));
        dotsEl.appendChild(d);
        dots.push(d);
      }
    }

    const render = () => {
      track.style.transform = `translateX(-${index * 100}%)`;
      dots.forEach((d, i) => d.classList.toggle('is-active', i === index));
    };

    const goTo = (i) => {
      index = (i + count) % count; // wrap around
      render();
    };
    const next = () => goTo(index + 1);
    const prev = () => goTo(index - 1);

    if (count <= 1) {
      // single image: hide controls entirely
      prevBtn?.classList.add('is-hidden');
      nextBtn?.classList.add('is-hidden');
      if (dotsEl) dotsEl.style.display = 'none';
    } else {
      prevBtn?.addEventListener('click', prev);
      nextBtn?.addEventListener('click', next);

      // keyboard arrows
      gallery.tabIndex = 0;
      gallery.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowLeft')  { e.preventDefault(); prev(); }
        if (e.key === 'ArrowRight') { e.preventDefault(); next(); }
      });

      // touch swipe
      let startX = 0, dx = 0, swiping = false;
      const viewport = gallery.querySelector('.gallery__viewport');
      viewport?.addEventListener('touchstart', (e) => {
        startX = e.touches[0].clientX; dx = 0; swiping = true;
      }, { passive: true });
      viewport?.addEventListener('touchmove', (e) => {
        if (!swiping) return;
        dx = e.touches[0].clientX - startX;
      }, { passive: true });
      viewport?.addEventListener('touchend', () => {
        if (!swiping) return;
        swiping = false;
        if (dx > 40) prev();
        else if (dx < -40) next();
      });
    }

    render();
  });

  // ---- light client-side validation ----
  document.querySelectorAll('form[data-validate]').forEach(form => {
    form.addEventListener('submit', e => {
      let bad = false;
      form.querySelectorAll('[required]').forEach(inp => {
        const wrap = inp.closest('.field');
        if (!inp.value.trim()) {
          wrap?.classList.add('field--error');
          bad = true;
        } else {
          wrap?.classList.remove('field--error');
        }
      });
      if (bad) e.preventDefault();
    });
  });
})();
