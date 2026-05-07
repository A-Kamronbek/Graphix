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

  // ---- qty steppers (cart) ----
  document.querySelectorAll('[data-qty]').forEach(box => {
    const inp = box.querySelector('input');
    box.querySelector('[data-qty-dec]')?.addEventListener('click', () => {
      const v = Math.max(1, (parseInt(inp.value, 10) || 1) - 1);
      inp.value = v;
      inp.dispatchEvent(new Event('change', { bubbles: true }));
    });
    box.querySelector('[data-qty-inc]')?.addEventListener('click', () => {
      const v = Math.min(99, (parseInt(inp.value, 10) || 1) + 1);
      inp.value = v;
      inp.dispatchEvent(new Event('change', { bubbles: true }));
    });
  });

  // ---- variant picker (item page) ----
  // sets hidden inputs when user clicks a swatch / size
  const variantForm = document.querySelector('[data-variant-form]');
  if (variantForm) {
    const colourInput = variantForm.querySelector('input[name="colour"]');
    const sizeInput = variantForm.querySelector('input[name="size"]');

    variantForm.querySelectorAll('[data-swatch]').forEach(el => {
      el.addEventListener('click', () => {
        variantForm.querySelectorAll('[data-swatch]').forEach(s => s.classList.remove('is-active'));
        el.classList.add('is-active');
        if (colourInput) colourInput.value = el.dataset.swatch;
      });
    });
    variantForm.querySelectorAll('[data-size]').forEach(el => {
      el.addEventListener('click', () => {
        if (el.classList.contains('is-oos')) return;
        variantForm.querySelectorAll('[data-size]').forEach(s => s.classList.remove('is-active'));
        el.classList.add('is-active');
        if (sizeInput) sizeInput.value = el.dataset.size;
      });
    });
  }

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
