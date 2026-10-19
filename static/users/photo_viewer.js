(() => {
  'use strict';
  const get = id => document.getElementById(id);
  const dialog = get('photo-viewer');
  if (!dialog || typeof dialog.showModal !== 'function') return;
  const stage = get('photo-viewer-stage'), image = get('photo-viewer-image');
  const status = get('photo-viewer-status'), caption = get('photo-viewer-caption');
  const minus = get('photo-zoom-out'), plus = get('photo-zoom-in'), fit = get('photo-fit');
  const level = get('photo-zoom-level'), close = get('photo-viewer-close');
  let zoom = 1, x = 0, y = 0, width = 0, height = 0, loaded = false;
  let opener = null, overflow = '', drag = null;
  function render() {
    const maxX = Math.max(0, (width * zoom - stage.clientWidth) / 2);
    const maxY = Math.max(0, (height * zoom - stage.clientHeight) / 2);
    x = Math.max(-maxX, Math.min(maxX, x));
    y = Math.max(-maxY, Math.min(maxY, y));
    image.style.transform = `translate(${x}px, ${y}px) scale(${zoom})`;
    level.textContent = `${Math.round(zoom * 100)}%`;
    minus.disabled = !loaded || zoom <= 1;
    plus.disabled = !loaded || zoom >= 6;
    fit.disabled = !loaded;
    stage.classList.toggle('is-zoomed', loaded && zoom > 1);
  }
  function size() {
    if (!loaded) return;
    const ratio = Math.min(stage.clientWidth / image.naturalWidth, stage.clientHeight / image.naturalHeight);
    width = image.naturalWidth * ratio;
    height = image.naturalHeight * ratio;
    image.style.width = `${width}px`;
    image.style.height = `${height}px`;
    render();
  }
  function changeZoom(value) {
    if (!loaded) return;
    zoom = Math.max(1, Math.min(6, value));
    render();
  }
  function stopDrag() {
    const previous = drag;
    drag = null;
    if (previous && stage.hasPointerCapture(previous.id)) stage.releasePointerCapture(previous.id);
    stage.classList.remove('is-dragging');
  }
  document.addEventListener('click', event => {
    const link = event.target.closest('[data-photo-viewer]');
    if (!link || event.button > 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const path = link.getAttribute('href');
    if (!/^\/photos\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/$/i.test(path)) return;
    event.preventDefault();
    if (dialog.open) return;
    opener = link;
    overflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = 'hidden';
    zoom = 1; x = 0; y = 0; loaded = false;
    image.hidden = true;
    caption.textContent = link.dataset.caption || '';
    status.textContent = 'Loading photograph…';
    render();
    dialog.showModal();
    image.src = path;
  });
  image.addEventListener('load', () => {
    if (!dialog.open || !image.naturalWidth || !image.naturalHeight) return;
    loaded = true;
    size();
    image.hidden = false;
    status.textContent = '';
  });
  image.addEventListener('error', () => {
    if (!dialog.open) return;
    loaded = false;
    image.hidden = true;
    status.textContent = 'We couldn’t open this photo. Close the viewer and try again. If this continues, refresh the page and sign in again.';
    render();
  });
  plus.addEventListener('click', () => changeZoom(zoom + 0.5));
  minus.addEventListener('click', () => changeZoom(zoom - 0.5));
  fit.addEventListener('click', () => { x = 0; y = 0; changeZoom(1); });
  close.addEventListener('click', () => dialog.close());
  dialog.addEventListener('cancel', event => { event.preventDefault(); dialog.close(); });
  dialog.addEventListener('close', () => {
    stopDrag();
    loaded = false;
    image.hidden = true;
    image.removeAttribute('src');
    document.documentElement.style.overflow = overflow;
    if (opener) opener.focus({preventScroll: true});
    opener = null;
  });
  stage.addEventListener('pointerdown', event => {
    if (!loaded || zoom <= 1 || drag || event.button !== 0) return;
    event.preventDefault();
    drag = {id: event.pointerId, startX: event.clientX, startY: event.clientY, x, y};
    stage.setPointerCapture(event.pointerId);
    stage.classList.add('is-dragging');
  });
  stage.addEventListener('pointermove', event => {
    if (!drag || event.pointerId !== drag.id) return;
    x = drag.x + event.clientX - drag.startX;
    y = drag.y + event.clientY - drag.startY;
    render();
  });
  for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    stage.addEventListener(name, event => { if (drag && event.pointerId === drag.id) stopDrag(); });
  }
  dialog.addEventListener('keydown', event => {
    if (['+', '=', '-', '0', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
      event.preventDefault();
      if (event.key === '+' || event.key === '=') changeZoom(zoom + 0.5);
      else if (event.key === '-') changeZoom(zoom - 0.5);
      else if (event.key === '0') { x = 0; y = 0; changeZoom(1); }
      else {
        x += event.key === 'ArrowLeft' ? 50 : event.key === 'ArrowRight' ? -50 : 0;
        y += event.key === 'ArrowUp' ? 50 : event.key === 'ArrowDown' ? -50 : 0;
        render();
      }
    }
  });
  window.addEventListener('resize', size);
})();
