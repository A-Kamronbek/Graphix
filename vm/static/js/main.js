// VM Graphics — main.js
// keep it tiny, no frameworks

(() => {
  // ---- mobile drawer ----
  const burger = document.querySelector('[data-burger]');
  const drawer = document.querySelector('[data-drawer]');
  const navEl  = document.querySelector('.nav');
  if (burger && drawer) {
    // Anchor the drawer right below the nav. On the home page a marquee sits
    // above the nav, so the nav bottom isn't a fixed offset from the top —
    // measure it at open time instead of trusting a constant.
    const positionDrawer = () => {
      const bottom = navEl ? Math.max(0, Math.round(navEl.getBoundingClientRect().bottom)) : 80;
      drawer.style.top = bottom + 'px';
    };
    const openDrawer = () => {
      positionDrawer();
      drawer.classList.add('is-open');
      document.body.classList.add('drawer-open');
    };
    const closeDrawer = () => {
      drawer.classList.remove('is-open');
      document.body.classList.remove('drawer-open');
    };
    burger.addEventListener('click', () => {
      if (drawer.classList.contains('is-open')) closeDrawer();
      else openDrawer();
    });
    drawer.querySelectorAll('a').forEach(a => a.addEventListener('click', closeDrawer));
  }

  // ---- duplicate marquee track for seamless scroll ----
  document.querySelectorAll('.marquee__track').forEach(track => {
    if (track.dataset.dup === '1') return;
    track.dataset.dup = '1';
    track.innerHTML = track.innerHTML + track.innerHTML;
  });

  // ---- shop filter dropdowns (mobile) ----
  // Tapping a group head (Bo'limlar / O'lcham / Filter) opens its options.
  // On desktop the lists are always shown via CSS, so toggling does nothing.
  document.querySelectorAll('[data-fgroup]').forEach(head => {
    head.addEventListener('click', () => {
      head.closest('.fgroup')?.classList.toggle('is-open');
    });
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

  // ---- OTP / phone verification page ----
  (function initOtp() {
    const wrap = document.querySelector('[data-otp]');
    if (!wrap) return;
    const cells = Array.from(wrap.querySelectorAll('.otp__cell'));
    const hidden = document.getElementById('id_code');
    const form = document.getElementById('otpForm');
    if (!cells.length || !hidden || !form) return;

    if (hidden.value) {
      hidden.value.split('').slice(0, cells.length).forEach((ch, i) => {
        cells[i].value = ch;
        cells[i].classList.toggle('is-filled', !!ch);
      });
    }

    const syncHidden = () => { hidden.value = cells.map(c => c.value).join(''); };
    const focusCell = (i) => { if (i >= 0 && i < cells.length) cells[i].focus(); };

    cells.forEach((cell, idx) => {
      cell.addEventListener('input', () => {
        cell.value = cell.value.replace(/\D/g, '').slice(-1);
        cell.classList.toggle('is-filled', !!cell.value);
        syncHidden();
        if (cell.value && idx < cells.length - 1) focusCell(idx + 1);
        if (cells.every(c => c.value)) form.requestSubmit();
      });

      cell.addEventListener('keydown', (e) => {
        if (e.key === 'Backspace') {
          if (!cell.value && idx > 0) {
            e.preventDefault();
            cells[idx - 1].value = '';
            cells[idx - 1].classList.remove('is-filled');
            syncHidden();
            focusCell(idx - 1);
          }
        } else if (e.key === 'ArrowLeft')  { e.preventDefault(); focusCell(idx - 1); }
        else if   (e.key === 'ArrowRight') { e.preventDefault(); focusCell(idx + 1); }
      });

      cell.addEventListener('paste', (e) => {
        e.preventDefault();
        const text = (e.clipboardData || window.clipboardData).getData('text') || '';
        const digits = text.replace(/\D/g, '').slice(0, cells.length);
        if (!digits) return;
        digits.split('').forEach((ch, i) => {
          if (cells[i]) {
            cells[i].value = ch;
            cells[i].classList.add('is-filled');
          }
        });
        syncHidden();
        focusCell(Math.min(digits.length, cells.length - 1));
        if (cells.every(c => c.value)) form.requestSubmit();
      });
    });

    // Expiry countdown. Server is the source of truth; this is visual only.
    // On hitting zero, submit the (CSRF-protected) expire form. The server
    // re-checks the absolute expiry before doing anything, so a forged/early
    // POST can't delete a user whose code is still valid.
    const timerEl = document.getElementById('otpTimer');
    if (timerEl) {
      let left = parseInt(timerEl.dataset.ttl, 10) || 0;
      let fired = false;
      const expireForm = document.getElementById('otpExpireForm');
      const tick = () => {
        if (left < 0) {
          timerEl.textContent = '00:00';
          if (!fired && expireForm) {
            fired = true;
            expireForm.submit();
          }
          return;
        }
        const m = String(Math.floor(left / 60)).padStart(2, '0');
        const s = String(left % 60).padStart(2, '0');
        timerEl.textContent = `${m}:${s}`;
        left -= 1;
      };
      tick();
      setInterval(tick, 1000);
    }

    // Resend cooldown
    const resendBtn = document.getElementById('otpResend');
    if (resendBtn) {
      let cd = parseInt(resendBtn.dataset.cooldown, 10) || 0;
      if (cd > 0) {
        const baseLabel = 'Qayta yuborish';
        const iv = setInterval(() => {
          if (cd <= 0) {
            resendBtn.disabled = false;
            resendBtn.textContent = baseLabel;
            clearInterval(iv);
            return;
          }
          resendBtn.textContent = `${baseLabel} (${cd}s)`;
          cd -= 1;
        }, 1000);
      }
    }
  })();

  // ---- signup draft persistence -------------------------------------------
  // Keep the non-sensitive fields (username, name, phone) when the user pops
  // out to the Terms page and comes back. Passwords are deliberately NOT saved.
  (function initSignupPersist() {
    const form = document.getElementById('signupForm');
    if (!form) return;

    const KEY = 'vm_signup_draft';
    const FIELDS = ['username', 'first_name', 'phone'];

    // Restore — only into fields the server left empty, so values re-rendered
    // after a validation error always take precedence over the saved draft.
    let saved = {};
    try { saved = JSON.parse(sessionStorage.getItem(KEY)) || {}; } catch (e) {}
    FIELDS.forEach(name => {
      const el = form.elements[name];
      if (el && !el.value && saved[name]) el.value = saved[name];
    });

    // Save on every edit. (sessionStorage clears itself when the tab closes,
    // so the draft never outlives the browsing session.)
    form.addEventListener('input', () => {
      const data = {};
      FIELDS.forEach(name => {
        const el = form.elements[name];
        if (el) data[name] = el.value;
      });
      try { sessionStorage.setItem(KEY, JSON.stringify(data)); } catch (e) {}
    });
  })();
})();
