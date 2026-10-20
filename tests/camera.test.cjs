const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const confirmationPath = '/submit-patient-details/saved/11111111-1111-4111-8111-111111111111/';
const source = fs.readFileSync('static/users/camera.js', 'utf8');

function browser(uploadsEnabled = true) {
  class Element {
    constructor() { this.listeners = {}; this.children = []; this.disabled = false; this.textContent = ''; this.dataset = {}; }
    addEventListener(name, listener) { this.listeners[name] = listener; }
    emit(name) { return this.listeners[name]({preventDefault() {}}); }
    scrollIntoView() { this.scrolled = true; }
    focus() { this.focused = true; }
    append(...children) { this.children.push(...children); }
    remove() { this.removed = true; }
  }
  const ids = Object.fromEntries(['patient-form', 'camera-preview', 'start-camera', 'capture-photo', 'stop-camera',
    'camera-status', 'submit-status', 'submit-button', 'photo-previews', 'id_consent_confirmed'].map(id => [id, new Element()]));
  ids['patient-form'].action = 'https://clinic.example.test/submit-patient-details/';
  ids['patient-form'].dataset = {uploadsEnabled: String(uploadsEnabled)};
  ids['patient-form'].reportValidity = () => true;
  ids['camera-preview'].videoWidth = 4096;
  ids['camera-preview'].videoHeight = 3072;
  ids['camera-preview'].play = async () => {};
  ids['id_consent_confirmed'].checked = true;
  const state = {cameraCalls: 0, stops: 0, urls: [], revoked: [], submissions: [], canvases: [], navigations: []};
  const document = new Element();
  document.getElementById = id => ids[id];
  document.createElement = name => {
    const element = new Element();
    if (name === 'canvas') {
      element.getContext = () => ({drawImage() {}});
      element.toBlob = callback => callback(new Blob(['synthetic-camera-data'], {type:'image/jpeg'}));
      state.canvases.push(element);
    }
    return element;
  };
  const window = new Element();
  window.isSecureContext = true;
  window.location = {assign: url => state.navigations.push(url)};
  const navigator = {mediaDevices: {getUserMedia: async () => {
    state.cameraCalls++; return {getTracks: () => [{stop: () => state.stops++}]};
  }}};
  class MemoryURL extends URL {
    static createObjectURL() { const url = `blob:${state.urls.length}`; state.urls.push(url); return url; }
    static revokeObjectURL(url) { state.revoked.push(url); }
  }
  class MemoryFormData {
    constructor() { this.fields = []; }
    append(...args) { this.fields.push(args); }
  }
  state.response = {redirected:true, url:'https://clinic.example.test' + confirmationPath};
  const context = {document, window, navigator, URL:MemoryURL, FormData:MemoryFormData, Blob, AbortController,
    setTimeout, clearTimeout, TypeError,
    fetch: async (url, options) => {state.submissions.push(options); if (state.fetchError) throw state.fetchError; return state.response;}};
  vm.runInNewContext(source, context);
  return {ids, state, window, document, navigator};
}

test('camera requires patient consent and secure context', async () => {
  const b = browser();
  b.ids.id_consent_confirmed.checked = false;
  await b.ids['start-camera'].emit('click');
  assert.equal(b.state.cameraCalls, 0);
  assert.match(b.ids['camera-status'].textContent, /consent/);
  b.ids.id_consent_confirmed.checked = true;
  b.window.isSecureContext = false;
  await b.ids['start-camera'].emit('click');
  assert.equal(b.state.cameraCalls, 0);
  assert.match(b.ids['camera-status'].textContent, /HTTPS/);
});

test('capture resizes in memory, submits JPEG blobs and stops camera', async () => {
  const b = browser();
  await b.ids['start-camera'].emit('click');
  await b.ids['capture-photo'].emit('click');
  assert.equal(b.state.canvases[0].width, 2048);
  assert.equal(b.state.canvases[0].height, 1536);
  await b.ids['patient-form'].emit('submit');
  assert.equal(b.state.submissions.length, 1);
  const [field, blob, filename] = b.state.submissions[0].body.fields[0];
  assert.equal(field, 'patient_images');
  assert.equal(blob.type, 'image/jpeg');
  assert.equal(filename, 'capture-1.jpg');
  assert.equal(b.state.stops, 1);
  assert.equal(b.state.revoked.length, 1);
  assert.deepEqual(b.state.navigations, ['https://clinic.example.test' + confirmationPath]);
});

test('remove prevents submitting deleted capture and revokes its preview', async () => {
  const b = browser();
  await b.ids['start-camera'].emit('click');
  await b.ids['capture-photo'].emit('click');
  b.ids['photo-previews'].children[0].children[1].emit('click');
  await b.ids['patient-form'].emit('submit');
  assert.equal(b.state.submissions.length, 0);
  assert.equal(b.state.revoked.length, 1);
  assert.match(b.ids['submit-status'].textContent, /at least one/);
  assert.equal(b.ids['camera-status'].textContent, '0 photographs ready.');
});

test('photo count follows removal from four to one and the next capture', async () => {
  const b = browser();
  await b.ids['start-camera'].emit('click');
  for (let i = 0; i < 4; i++) await b.ids['capture-photo'].emit('click');
  assert.equal(b.ids['camera-status'].textContent, '4 photographs ready.');
  for (let i = 0; i < 3; i++) b.ids['photo-previews'].children[i].children[1].emit('click');
  assert.equal(b.ids['camera-status'].textContent, '1 photograph ready.');
  await b.ids['capture-photo'].emit('click');
  assert.equal(b.ids['camera-status'].textContent, '2 photographs ready.');
});

test('failed save preserves capture for safe retry and restores controls', async () => {
  const b = browser();
  b.state.response = {redirected:false, status:503};
  await b.ids['start-camera'].emit('click');
  await b.ids['capture-photo'].emit('click');
  await b.ids['patient-form'].emit('submit');
  assert.equal(b.ids['submit-button'].disabled, false);
  assert.equal(b.state.revoked.length, 0);
  assert.match(b.ids['submit-status'].textContent, /try again/);
  b.state.response = {redirected:true, url:'https://clinic.example.test' + confirmationPath};
  await b.ids['patient-form'].emit('submit');
  assert.equal(b.state.submissions[1].body.fields.length, 1);
});

test('login redirect is not treated as successful save', async () => {
  const b = browser();
  b.state.response = {redirected:true, url:'https://clinic.example.test/accounts/google/login/'};
  await b.ids['start-camera'].emit('click');
  await b.ids['capture-photo'].emit('click');
  await b.ids['patient-form'].emit('submit');
  assert.equal(b.state.navigations.length, 0);
  assert.equal(b.state.revoked.length, 0);
  assert.match(b.ids['submit-status'].textContent, /sign in again/);
});

test('JSON save opens a persistent private confirmation page', async () => {
  const b = browser();
  b.state.response = {status:201, json:async () => ({redirect_url:confirmationPath})};
  await b.ids['start-camera'].emit('click');
  await b.ids['capture-photo'].emit('click');
  await b.ids['patient-form'].emit('submit');
  assert.equal(b.state.submissions[0].headers.Accept, 'application/json');
  assert.deepEqual(b.state.navigations, [confirmationPath]);
  assert.equal(b.state.revoked.length, 1);
});

test('backgrounding stops camera, leaving the page clears in-memory previews', async () => {
  const b = browser();
  await b.ids['start-camera'].emit('click');
  await b.ids['capture-photo'].emit('click');
  b.document.hidden = true;
  b.document.emit('visibilitychange');
  assert.equal(b.state.stops, 1);
  b.window.emit('pagehide');
  assert.equal(b.state.revoked.length, 1);
});

test('preview allows camera capture but never sends an upload', async () => {
  const b = browser(false);
  await b.ids['start-camera'].emit('click');
  await b.ids['capture-photo'].emit('click');
  assert.equal(b.state.cameraCalls, 1);
  assert.equal(b.ids['submit-button'].disabled, true);
  await b.ids['patient-form'].emit('submit');
  assert.equal(b.state.submissions.length, 0);
  assert.match(b.ids['submit-status'].textContent, /disabled in this preview/);
});


test('network errors and malformed responses retain photos and expose only plain retry guidance', async () => {
  for (const response of [
    {status:201, json:async () => { throw new SyntaxError('technical parser detail'); }},
    {status:201, json:async () => ({redirect_url:'https://other.example.test/'})},
    {status:500, redirected:false},
  ]) {
    const b = browser(); b.state.response = response;
    await b.ids['start-camera'].emit('click');
    await b.ids['capture-photo'].emit('click');
    await b.ids['patient-form'].emit('submit');
    assert.match(b.ids['submit-status'].textContent, /Keep this page open and try again/);
    assert.doesNotMatch(b.ids['submit-status'].textContent, /parser|technical/);
    assert.equal(b.ids['submit-status'].scrolled, true);
    assert.equal(b.ids['submit-status'].focused, true);
    assert.equal(b.state.navigations.length, 0);
    assert.equal(b.state.revoked.length, 0);
    assert.equal(b.ids['submit-button'].disabled, false);
  }
});


test('lost connection gives plain retry guidance without discarding captures', async () => {
  const b = browser();
  b.state.fetchError = new TypeError('technical fetch failure');
  await b.ids['start-camera'].emit('click');
  await b.ids['capture-photo'].emit('click');
  await b.ids['patient-form'].emit('submit');
  assert.match(b.ids['submit-status'].textContent, /Your photos are still here/);
  assert.doesNotMatch(b.ids['submit-status'].textContent, /technical/);
  assert.equal(b.state.revoked.length, 0);
  b.state.fetchError = null;
  b.state.response = {status:201, json:async () => ({redirect_url:confirmationPath})};
  await b.ids['patient-form'].emit('submit');
  assert.equal(b.state.submissions[1].body.fields.length, 1);
  assert.deepEqual(b.state.navigations, [confirmationPath]);
});
