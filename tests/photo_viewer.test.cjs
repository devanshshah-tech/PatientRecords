const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('static/users/photo_viewer.js', 'utf8');
function browser() {
  class Element {
    constructor() {
      this.listeners = {}; this.style = {}; this.dataset = {}; this.classes = new Set();
      this.classList = {add: v => this.classes.add(v), remove: v => this.classes.delete(v),
        toggle: (v, on) => on ? this.classes.add(v) : this.classes.delete(v)};
    }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    emit(name, extra = {}) {
      const event = {preventDefault() { this.prevented = true; }, ...extra};
      this.listeners[name]?.(event); return event;
    }
    showModal() { this.open = true; }
    close() { this.open = false; this.emit('close'); }
    focus(options) { this.focusOptions = options; }
    removeAttribute(name) { delete this[name]; }
    setPointerCapture(id) { this.pointer = id; }
    hasPointerCapture(id) { return this.pointer === id; }
    releasePointerCapture() { delete this.pointer; }
  }
  const ids = Object.fromEntries(['photo-viewer', 'photo-viewer-stage', 'photo-viewer-image',
    'photo-viewer-status', 'photo-viewer-caption', 'photo-zoom-out', 'photo-zoom-in',
    'photo-fit', 'photo-zoom-level', 'photo-viewer-close'].map(id => [id, new Element()]));
  const document = new Element(), window = new Element();
  document.documentElement = {style: {overflow: 'auto'}};
  document.getElementById = id => ids[id];
  ids['photo-viewer-stage'].clientWidth = 800; ids['photo-viewer-stage'].clientHeight = 600;
  const image = ids['photo-viewer-image']; image.naturalWidth = 1600; image.naturalHeight = 1200;
  const link = new Element(); link.path = '/photos/11111111-1111-4111-8111-111111111111/';
  link.getAttribute = () => link.path; link.closest = () => link;
  link.dataset.caption = '<script>synthetic caption</script>';
  vm.runInNewContext(source, {document, window});
  const open = () => document.emit('click', {target: link, button: 0});
  return {ids, document, window, image, link, open};
}
test('opens private photo, fits dimensions and restores focus without scrolling on close', () => {
  const b = browser(); assert.equal(b.open().prevented, true);
  assert.equal(b.ids['photo-viewer'].open, true);
  assert.equal(b.document.documentElement.style.overflow, 'hidden');
  assert.equal(b.ids['photo-viewer-caption'].textContent, b.link.dataset.caption);
  b.image.emit('load'); assert.equal(b.image.style.width, '800px');
  assert.equal(b.image.hidden, false);
  b.ids['photo-viewer-close'].emit('click');
  assert.equal(b.image.src, undefined); assert.equal(b.image.hidden, true);
  assert.equal(b.document.documentElement.style.overflow, 'auto');
  assert.equal(b.link.focusOptions.preventScroll, true);
});
test('zoom and mouse/touch pointer pan stay bounded; fit and resize work', () => {
  const b = browser(); b.open(); b.image.emit('load');
  b.ids['photo-zoom-in'].emit('click'); b.ids['photo-zoom-in'].emit('click');
  const stage = b.ids['photo-viewer-stage'];
  stage.emit('pointerdown', {button: 0, pointerId: 4, clientX: 0, clientY: 0});
  stage.emit('pointermove', {pointerId: 4, clientX: 5000, clientY: -5000});
  assert.equal(b.image.style.transform, 'translate(400px, -300px) scale(2)');
  stage.emit('pointercancel', {pointerId: 4}); assert.equal(stage.pointer, undefined);
  for (let i = 0; i < 20; i++) b.ids['photo-zoom-in'].emit('click');
  assert.equal(b.ids['photo-zoom-level'].textContent, '600%');
  assert.equal(b.ids['photo-zoom-in'].disabled, true);
  stage.clientWidth = 400; b.window.emit('resize'); assert.equal(b.image.style.width, '400px');
  b.ids['photo-fit'].emit('click'); assert.equal(b.image.style.transform, 'translate(0px, 0px) scale(1)');
  b.ids['photo-zoom-out'].emit('click'); assert.equal(b.ids['photo-zoom-level'].textContent, '100%');
});
test('keyboard zoom/pan, Escape and load failure retain usable exit', () => {
  const b = browser(); b.open(); b.image.emit('load'); const dialog = b.ids['photo-viewer'];
  dialog.emit('keydown', {key: '+'}); dialog.emit('keydown', {key: 'ArrowLeft'});
  assert.equal(b.image.style.transform, 'translate(50px, 0px) scale(1.5)');
  dialog.emit('keydown', {key: '0'}); assert.equal(b.ids['photo-zoom-level'].textContent, '100%');
  dialog.emit('cancel'); assert.equal(dialog.open, false);
  b.open(); b.image.emit('error'); assert.match(b.ids['photo-viewer-status'].textContent, /try again/);
  assert.equal(b.ids['photo-zoom-in'].disabled, true);
  b.ids['photo-viewer-close'].emit('click'); assert.equal(dialog.open, false);
});
test('external and modified links retain normal navigation', () => {
  const b = browser(); b.link.path = 'https://external.example/photos/11111111-1111-4111-8111-111111111111/';
  assert.equal(b.open().prevented, undefined); assert.equal(b.image.src, undefined);
  b.link.path = '/photos/11111111-1111-4111-8111-111111111111/';
  assert.equal(b.document.emit('click', {target: b.link, ctrlKey: true}).prevented, undefined);
});
