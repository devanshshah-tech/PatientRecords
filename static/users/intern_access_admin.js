(() => {
  'use strict';
  document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('changelist-form');
    const toggle = document.getElementById('action-toggle');
    if (!form || !toggle) return;
    document.getElementById('access-select-all')?.addEventListener('click', () => {
      if (!toggle.checked) toggle.click();
    });
    document.getElementById('access-clear-selection')?.addEventListener('click', () => {
      toggle.checked = true; toggle.click();
    });
    document.getElementById('access-delete-selected')?.addEventListener('click', () => {
      const action = form.querySelector('select[name="action"]');
      const go = form.querySelector('button[name="index"]');
      if (!action || !go) return;
      action.value = 'delete_selected';
      action.dispatchEvent(new Event('change', {bubbles:true}));
      go.click();
    });
  });
})();
