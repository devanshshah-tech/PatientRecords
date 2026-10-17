(() => {
  'use strict';
  const form = document.getElementById('patient-form');
  const video = document.getElementById('camera-preview');
  const start = document.getElementById('start-camera');
  const capture = document.getElementById('capture-photo');
  const stop = document.getElementById('stop-camera');
  const status = document.getElementById('camera-status');
  const submitStatus = document.getElementById('submit-status');
  const submit = document.getElementById('submit-button');
  const previews = document.getElementById('photo-previews');
  const uploadsEnabled = form.dataset?.uploadsEnabled !== 'false';
  let stream = null;
  let photos = [];
  let busy = false;
  function updatePhotoCount() {
    status.textContent = photos.length === 1 ? '1 photograph ready.' : `${photos.length} photographs ready.`;
  }
  function closeCamera() {
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null; video.srcObject = null; video.hidden = true;
    capture.disabled = true; stop.disabled = true; start.disabled = false;
  }
  start.addEventListener('click', async () => {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      status.textContent = 'Camera requires HTTPS and a supported browser. Ask your administrator for help.';
      return;
    }
    if (!document.getElementById('id_consent_confirmed').checked) {
      status.textContent = 'Confirm patient consent before opening the camera.';
      return;
    }
    start.disabled = true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:'environment'},width:{ideal:2048},height:{ideal:1536}}});
      video.srcObject = stream; video.hidden = false; await video.play();
      capture.disabled = false; stop.disabled = false;
      status.textContent = 'Camera ready. Captures are not saved to your gallery by this application.';
    } catch (error) {
      closeCamera(); status.textContent = 'Unable to open camera. Check camera permission and close other camera apps.';
    }
  });
  stop.addEventListener('click', closeCamera);
  capture.addEventListener('click', async () => {
    if (busy || !video.videoWidth || !stream) return;
    if (!document.getElementById('id_consent_confirmed').checked) {
      closeCamera(); status.textContent = 'Patient consent is required.'; return;
    }
    if (photos.length >= 10) { status.textContent = 'Limit reached: remove a photo before taking another.'; return; }
    busy = true; capture.disabled = true; submit.disabled = true;
    try {
      const canvas = document.createElement('canvas');
      const ratio = Math.min(1, 2048 / Math.max(video.videoWidth, video.videoHeight));
      canvas.width = Math.round(video.videoWidth * ratio); canvas.height = Math.round(video.videoHeight * ratio);
      canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.9));
      if (!blob) throw new Error('Capture failed');
      const photo = {blob, url: URL.createObjectURL(blob)};
      photos.push(photo);
      const card = document.createElement('div'); card.className = 'photo-card';
      const img = document.createElement('img'); img.src = photo.url; img.alt = 'Captured clinical photograph';
      const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'secondary'; remove.textContent = 'Remove';
      remove.addEventListener('click', () => {photos = photos.filter(p => p !== photo); URL.revokeObjectURL(photo.url); card.remove(); updatePhotoCount();});
      card.append(img, remove); previews.append(card); updatePhotoCount();
    } catch (error) { status.textContent = 'Capture failed. Please try again.'; }
    finally { busy = false; capture.disabled = !stream; submit.disabled = !uploadsEnabled; }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!uploadsEnabled) { submitStatus.textContent = 'Saving is disabled in this preview. Use objects only to test the camera.'; return; }
    if (busy || !form.reportValidity()) return;
    if (!photos.length) { submitStatus.textContent = 'Take at least one photograph before submitting.'; return; }
    busy = true; submit.disabled = true; start.disabled = true; capture.disabled = true;
    submit.textContent = 'Saving…'; submitStatus.textContent = ''; closeCamera(); start.disabled = true;
    const data = new FormData(form);
    photos.forEach((photo, i) => data.append('patient_images', photo.blob, `capture-${i + 1}.jpg`));
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120000);
    try {
      const response = await fetch(form.action, {method:'POST', body:data, credentials:'same-origin', signal:controller.signal});
      if (response.redirected) {
        if (new URL(response.url).pathname !== '/') throw new Error('Your session ended. Sign in again before resubmitting.');
        photos.forEach(p => URL.revokeObjectURL(p.url)); photos = []; window.location.assign(response.url); return;
      }
      if (response.status === 200) {
        const documentResult = new DOMParser().parseFromString(await response.text(), 'text/html');
        const errors = [...documentResult.querySelectorAll('.errorlist')].map(e => e.textContent.trim());
        throw new Error(errors.join(' ') || 'Unable to save. Please check the form.');
      }
      throw new Error(response.status === 403 ? 'Access denied. Your session or access may have expired.' : 'Save failed. Your photos remain here; retrying this submission will not create a duplicate visit.');
    } catch (error) {
      submitStatus.textContent = error.name === 'AbortError' || error instanceof TypeError
        ? 'Connection failed or timed out. Your photos remain here; retrying this submission will not create a duplicate visit.'
        : error.message;
    }
    finally { clearTimeout(timeout); busy = false; submit.disabled = false; start.disabled = false; submit.textContent = 'Save patient visit'; }
  });
  window.addEventListener('pagehide', () => { closeCamera(); photos.forEach(p => URL.revokeObjectURL(p.url)); photos = []; });
  document.addEventListener('visibilitychange', () => { if (document.hidden) closeCamera(); });
})();
