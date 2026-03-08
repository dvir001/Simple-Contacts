/* ------------------------------------------------------------------ */
/*  configure.js – Simple Contacts front-end                          */
/* ------------------------------------------------------------------ */

const API = window.location.origin;
let settings = {};

/* ---------- helpers ---------- */

function t(key, fallback, params) {
    let text;
    if (window.i18n && window.i18n.t) {
        const val = window.i18n.t(key);
        text = val !== key ? val : (fallback || key);
    } else {
        text = fallback || key;
    }
    if (params) {
        Object.keys(params).forEach(k => {
            text = text.replace(new RegExp('\\{' + k + '\\}', 'g'), params[k]);
        });
    }
    return text;
}

function flash(messageKey, fallback, isError = false, params) {
    const banner = document.getElementById('flash-banner');
    const msg = document.getElementById('flash-message');
    if (!banner || !msg) return;
    msg.textContent = t(messageKey, fallback, params);
    banner.className = 'flash-banner' + (isError ? ' error' : '');
    banner.style.display = 'flex';
    setTimeout(() => { banner.style.display = 'none'; }, 5000);
}

/* ---------- settings CRUD ---------- */

async function loadSettings() {
    try {
        const res = await fetch(`${API}/api/settings`);
        if (!res.ok) throw new Error(res.statusText);
        settings = await res.json();
        applySettingsToUI();
    } catch (err) {
        console.error('Failed to load settings', err);
    }
}

function applySettingsToUI() {
    toggle('directoryJsonEnabled');
    toggle('directoryXmlEnabled');
    toggle('autoUpdateEnabled');
    setText('directoryJsonFilename');
    setText('directoryXmlFilename');
    renderSwapRows();
    renderContactRows();
    applyTimePicker();
    applyDataUpdateStatus();
    updateUrlPreviews();
    updateSubItemVisibility();
}

function toggle(id) {
    const el = document.getElementById(id);
    if (el) el.checked = !!settings[id];
}

function setText(id) {
    const el = document.getElementById(id);
    if (el) el.value = settings[id] || '';
}

/* ---------- number swap rows ---------- */

function createSwapRow(find = '', replace = '') {
    const row = document.createElement('div');
    row.className = 'swap-row';
    row.draggable = true;
    row.innerHTML = `
        <span class="drag-handle" title="${t('directory.numberSwaps.drag', 'Drag to reorder')}">
            <svg width="10" height="16" viewBox="0 0 10 16" fill="currentColor"><circle cx="2" cy="2" r="1.5"/><circle cx="8" cy="2" r="1.5"/><circle cx="2" cy="8" r="1.5"/><circle cx="8" cy="8" r="1.5"/><circle cx="2" cy="14" r="1.5"/><circle cx="8" cy="14" r="1.5"/></svg>
        </span>
        <input type="text" class="swap-find" placeholder="${t('directory.numberSwaps.findPlaceholder', '+972 31234567,')}">
        <input type="text" class="swap-replace" placeholder="${t('directory.numberSwaps.replacePlaceholder', '(empty = delete)')}">
        <span class="reorder-buttons">
            <button type="button" class="btn-reorder btn-move-up" title="${t('directory.numberSwaps.moveUp', 'Move up')}">
                <svg width="10" height="6" viewBox="0 0 10 6" fill="none"><path d="M1 5l4-4 4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
            <button type="button" class="btn-reorder btn-move-down" title="${t('directory.numberSwaps.moveDown', 'Move down')}">
                <svg width="10" height="6" viewBox="0 0 10 6" fill="none"><path d="M1 1l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
        </span>
        <button type="button" class="btn-remove-row" title="${t('directory.numberSwaps.remove', 'Remove')}">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
        </button>
    `;
    // Set values programmatically to preserve whitespace
    row.querySelector('.swap-find').value = find;
    row.querySelector('.swap-replace').value = replace;
    row.querySelector('.btn-remove-row').addEventListener('click', () => {
        row.classList.add('removing');
        setTimeout(() => { row.remove(); updateSwapCounter(); updateSwapArrowStates(); }, 200);
    });
    row.querySelector('.btn-move-up').addEventListener('click', () => moveRowGeneric(row, -1, '.swap-row', updateSwapArrowStates));
    row.querySelector('.btn-move-down').addEventListener('click', () => moveRowGeneric(row, 1, '.swap-row', updateSwapArrowStates));
    initRowDragGeneric(row, '.swap-row', updateSwapArrowStates);
    return row;
}

function serializeSwaps() {
    const rows = document.querySelectorAll('.swap-row');
    const items = [];
    rows.forEach(row => {
        const find = row.querySelector('.swap-find')?.value || '';
        const replace = row.querySelector('.swap-replace')?.value || '';
        if (find.trim()) items.push({ find, replace });
    });
    return items;
}

function renderSwapRows() {
    const list = document.getElementById('swap-list');
    if (!list) return;
    list.innerHTML = '';
    const raw = settings.directoryNumberSwaps || settings.directoryIgnoredPrefixes || [];
    // Handle legacy formats
    const items = Array.isArray(raw) ? raw : [];
    if (items.length === 0) {
        list.appendChild(createSwapRow());
    } else {
        items.forEach(item => {
            if (typeof item === 'object' && item.find !== undefined) {
                list.appendChild(createSwapRow(item.find, item.replace || ''));
            } else {
                // Legacy plain-string prefix
                list.appendChild(createSwapRow(String(item), ''));
            }
        });
    }
    updateSwapCounter();
    updateSwapArrowStates();
}

function updateSwapArrowStates() {
    const list = document.getElementById('swap-list');
    if (!list) return;
    const rows = list.querySelectorAll('.swap-row');
    rows.forEach((row, i) => {
        const upBtn = row.querySelector('.btn-move-up');
        const downBtn = row.querySelector('.btn-move-down');
        if (upBtn) upBtn.disabled = (i === 0);
        if (downBtn) downBtn.disabled = (i === rows.length - 1);
    });
}

function getMaxSwaps() {
    return 50;
}

function updateSwapCounter() {
    const list = document.getElementById('swap-list');
    const counter = document.getElementById('swap-counter');
    const addBtn = document.getElementById('btn-add-swap');
    if (!list) return;
    const count = list.querySelectorAll('.swap-row').length;
    const max = getMaxSwaps();
    if (counter) counter.textContent = `${count} / ${max}`;
    if (addBtn) {
        addBtn.disabled = count >= max;
        addBtn.title = count >= max ? t('directory.numberSwaps.limitReached', `Limit of ${max} rules reached`, { max }) : '';
    }
}

/* ---------- custom contacts table ---------- */

function parseContactsString(raw) {
    if (!raw) return [];
    return raw.split('\n')
        .map(line => line.trim())
        .filter(line => line && !line.startsWith('#'))
        .map(line => {
            const idx = line.indexOf(',');
            if (idx === -1) return { name: line, number: '' };
            return { name: line.substring(0, idx).trim(), number: line.substring(idx + 1).trim() };
        });
}

function serializeContacts() {
    const rows = document.querySelectorAll('.custom-contact-row');
    const lines = [];
    rows.forEach(row => {
        const name = row.querySelector('.contact-name')?.value.trim() || '';
        const number = row.querySelector('.contact-number')?.value.trim() || '';
        if (name || number) lines.push(`${name}, ${number}`);
    });
    return lines.join('\n');
}

function createContactRow(name = '', number = '') {
    const row = document.createElement('div');
    row.className = 'custom-contact-row';
    row.draggable = true;
    row.innerHTML = `
        <span class="drag-handle" title="${t('directory.custom.drag', 'Drag to reorder')}">
            <svg width="10" height="16" viewBox="0 0 10 16" fill="currentColor"><circle cx="2" cy="2" r="1.5"/><circle cx="8" cy="2" r="1.5"/><circle cx="2" cy="8" r="1.5"/><circle cx="8" cy="8" r="1.5"/><circle cx="2" cy="14" r="1.5"/><circle cx="8" cy="14" r="1.5"/></svg>
        </span>
        <input type="text" class="contact-name" value="${_escAttr(name)}" placeholder="${t('directory.custom.namePlaceholder', 'Contact name')}">
        <input type="text" class="contact-number" value="${_escAttr(number)}" placeholder="${t('directory.custom.numberPlaceholder', 'Extension / number')}">
        <span class="reorder-buttons">
            <button type="button" class="btn-reorder btn-move-up" title="${t('directory.custom.moveUp', 'Move up')}">
                <svg width="10" height="6" viewBox="0 0 10 6" fill="none"><path d="M1 5l4-4 4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
            <button type="button" class="btn-reorder btn-move-down" title="${t('directory.custom.moveDown', 'Move down')}">
                <svg width="10" height="6" viewBox="0 0 10 6" fill="none"><path d="M1 1l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
        </span>
        <button type="button" class="btn-remove-row" title="${t('directory.custom.remove', 'Remove')}">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
        </button>
    `;
    row.querySelector('.btn-remove-row').addEventListener('click', () => {
        row.classList.add('removing');
        setTimeout(() => { row.remove(); updateContactCounter(); updateArrowStates(); }, 200);
    });
    row.querySelector('.btn-move-up').addEventListener('click', () => moveRowGeneric(row, -1, '.custom-contact-row', updateArrowStates));
    row.querySelector('.btn-move-down').addEventListener('click', () => moveRowGeneric(row, 1, '.custom-contact-row', updateArrowStates));
    initRowDragGeneric(row, '.custom-contact-row', updateArrowStates);
    return row;
}

function _escAttr(str) {
    return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ---------- reorder: generic helpers ---------- */

function moveRowGeneric(row, direction, rowSelector, updateFn) {
    const list = row.parentElement;
    if (!list) return;
    const rows = [...list.querySelectorAll(rowSelector)];
    const idx = rows.indexOf(row);
    if (idx < 0) return;
    const targetIdx = idx + direction;
    if (targetIdx < 0 || targetIdx >= rows.length) return;
    if (direction === -1) {
        list.insertBefore(row, rows[targetIdx]);
    } else {
        list.insertBefore(row, rows[targetIdx].nextSibling);
    }
    updateFn();
}

function updateArrowStates() {
    const list = document.getElementById('custom-contacts-list');
    if (!list) return;
    const rows = list.querySelectorAll('.custom-contact-row');
    rows.forEach((row, i) => {
        const upBtn = row.querySelector('.btn-move-up');
        const downBtn = row.querySelector('.btn-move-down');
        if (upBtn) upBtn.disabled = (i === 0);
        if (downBtn) downBtn.disabled = (i === rows.length - 1);
    });
}

let _dragRow = null;

function initRowDragGeneric(row, rowSelector, updateFn) {
    row.addEventListener('dragstart', (e) => {
        if (!e.target.closest('.drag-handle') && e.target !== row) {
            e.preventDefault();
            return;
        }
        _dragRow = row;
        row.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
    });
    row.addEventListener('dragend', () => {
        row.classList.remove('dragging');
        _dragRow = null;
        clearDropIndicators();
        updateFn();
    });
    row.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (!_dragRow || _dragRow === row) return;
        const rect = row.getBoundingClientRect();
        const midY = rect.top + rect.height / 2;
        clearDropIndicators();
        row.classList.add(e.clientY < midY ? 'drop-above' : 'drop-below');
    });
    row.addEventListener('dragleave', () => {
        row.classList.remove('drop-above', 'drop-below');
    });
    row.addEventListener('drop', (e) => {
        e.preventDefault();
        if (!_dragRow || _dragRow === row) return;
        const list = row.parentElement;
        const rect = row.getBoundingClientRect();
        const midY = rect.top + rect.height / 2;
        if (e.clientY < midY) {
            list.insertBefore(_dragRow, row);
        } else {
            list.insertBefore(_dragRow, row.nextSibling);
        }
        clearDropIndicators();
        updateFn();
    });
}

function clearDropIndicators() {
    document.querySelectorAll('.drop-above, .drop-below').forEach(el => {
        el.classList.remove('drop-above', 'drop-below');
    });
}

function renderContactRows() {
    const list = document.getElementById('custom-contacts-list');
    if (!list) return;
    list.innerHTML = '';
    const contacts = parseContactsString(settings.customDirectoryContacts || '');
    if (contacts.length === 0) {
        list.appendChild(createContactRow());
    } else {
        contacts.forEach(c => list.appendChild(createContactRow(c.name, c.number)));
    }
    updateContactCounter();
    updateArrowStates();
}

function getMaxContacts() {
    return settings.maxCustomContacts || 200;
}

function updateContactCounter() {
    const list = document.getElementById('custom-contacts-list');
    const counter = document.getElementById('custom-contacts-counter');
    const addBtn = document.getElementById('btn-add-contact');
    if (!list) return;
    const count = list.querySelectorAll('.custom-contact-row').length;
    const max = getMaxContacts();
    if (counter) counter.textContent = `${count} / ${max}`;
    if (addBtn) {
        addBtn.disabled = count >= max;
        addBtn.title = count >= max ? t('directory.custom.limitReached', `Limit of ${max} contacts reached`, { max }) : '';
    }
}

function collectSettings() {
    // Convert local time back to UTC for storage
    const hourEl = document.getElementById('updateHour');
    const minEl = document.getElementById('updateMinute');
    let updateTime = settings.updateTime || '20:00';
    if (hourEl && minEl) {
        const localStr = `${hourEl.value.padStart(2, '0')}:${minEl.value.padStart(2, '0')}`;
        updateTime = localTimeToUtc(localStr);
    }

    return {
        directoryJsonEnabled: document.getElementById('directoryJsonEnabled')?.checked || false,
        directoryJsonFilename: (document.getElementById('directoryJsonFilename')?.value || 'microsip').trim(),
        directoryXmlEnabled: document.getElementById('directoryXmlEnabled')?.checked || false,
        directoryXmlFilename: (document.getElementById('directoryXmlFilename')?.value || 'yealink').trim(),
        directoryNumberSwaps: serializeSwaps(),
        customDirectoryContacts: serializeContacts(),
        autoUpdateEnabled: document.getElementById('autoUpdateEnabled')?.checked || false,
        updateTime,
    };
}

async function saveSettings() {
    try {
        const payload = collectSettings();
        const res = await fetch(`${API}/api/settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error(res.statusText);
        const data = await res.json();
        settings = data.settings || payload;
        flash('flash.settingsSaved', 'Settings saved successfully.');
    } catch (err) {
        console.error('Save failed', err);
        flash('flash.settingsError', 'Failed to save settings.', true);
    }
}

/* ---------- employee data ---------- */

async function loadAzureStatus() {
    const statusEl = document.getElementById('azure-status-text');
    const syncBtn = document.getElementById('btn-azure-sync');
    try {
        const res = await fetch(`${API}/api/azure/status`);
        if (!res.ok) throw new Error(res.statusText);
        const data = await res.json();
        if (data.configured) {
            if (statusEl) statusEl.textContent = t('employees.azure.ready', 'Azure AD credentials are configured. Click Sync Now to fetch employees.');
            if (syncBtn) syncBtn.disabled = false;
        } else {
            if (statusEl) statusEl.textContent = t('employees.azure.notConfigured', 'Azure AD credentials are not set. Set AZURE_TENANT_ID, AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET in .env to enable.');
            if (syncBtn) syncBtn.disabled = true;
        }
    } catch (err) {
        console.error('Failed to check Azure status', err);
        if (statusEl) statusEl.textContent = t('employees.azure.error', 'Unable to check Azure AD status.');
        if (syncBtn) syncBtn.disabled = true;
    }
}

async function azureSync() {
    const syncBtn = document.getElementById('btn-azure-sync');
    if (syncBtn) { syncBtn.disabled = true; syncBtn.textContent = t('employees.azure.syncing', 'Syncing…'); }
    try {
        const res = await fetch(`${API}/api/azure/sync`, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || res.statusText);
        flash('flash.syncSuccess', `Synced ${data.count} employees from Azure AD.`, false, { count: data.count });
        loadEmployeeStatus();
    } catch (err) {
        console.error('Azure sync failed', err);
        flash('flash.syncError', 'Failed to sync from Azure AD: ' + err.message, true);
    } finally {
        if (syncBtn) { syncBtn.disabled = false; syncBtn.textContent = t('employees.azure.button', 'Sync Now'); }
    }
}

async function loadEmployeeStatus() {
    try {
        const res = await fetch(`${API}/api/employees`);
        if (!res.ok) throw new Error(res.statusText);
        const data = await res.json();
        const el = document.getElementById('employee-status');
        if (el) {
            el.textContent = data.length
                ? t('employees.status.loaded', `${data.length} employees loaded`).replace('{count}', data.length)
                : t('employees.status.none', 'No employee data loaded');
        }
    } catch (err) {
        console.error('Failed to load employee status', err);
    }
}

async function clearEmployees() {
    if (!confirm('Are you sure you want to remove all employee data?')) return;
    try {
        const res = await fetch(`${API}/api/employees`, { method: 'DELETE' });
        if (!res.ok) throw new Error(res.statusText);
        flash('flash.clearSuccess', 'Employee data cleared.');
        loadEmployeeStatus();
    } catch (err) {
        console.error('Clear failed', err);
        flash('flash.clearError', 'Failed to clear employee data.', true);
    }
}

/* ---------- time picker & UTC helpers ---------- */

function initTimePicker() {
    const hourSelect = document.getElementById('updateHour');
    const minSelect = document.getElementById('updateMinute');
    if (!hourSelect || !minSelect) return;

    for (let h = 0; h < 24; h++) {
        const opt = document.createElement('option');
        opt.value = h;
        opt.textContent = String(h).padStart(2, '0');
        hourSelect.appendChild(opt);
    }
    for (let m = 0; m < 60; m++) {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = String(m).padStart(2, '0');
        minSelect.appendChild(opt);
    }
}

function localTimeToUtc(localTimeStr) {
    const [h, m] = localTimeStr.split(':').map(Number);
    const now = new Date();
    const local = new Date(now.getFullYear(), now.getMonth(), now.getDate(), h, m, 0);
    return `${String(local.getUTCHours()).padStart(2, '0')}:${String(local.getUTCMinutes()).padStart(2, '0')}`;
}

function utcTimeToLocal(utcTimeStr) {
    const [h, m] = utcTimeStr.split(':').map(Number);
    const now = new Date();
    const utcMs = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), h, m, 0);
    const local = new Date(utcMs);
    return `${String(local.getHours()).padStart(2, '0')}:${String(local.getMinutes()).padStart(2, '0')}`;
}

function applyTimePicker() {
    const utcTime = settings.updateTime || '20:00';
    const localTime = utcTimeToLocal(utcTime);
    const [lh, lm] = localTime.split(':').map(Number);
    const hourEl = document.getElementById('updateHour');
    const minEl = document.getElementById('updateMinute');
    if (hourEl) hourEl.value = lh;
    if (minEl) minEl.value = lm;
}

/* ---------- data update status ---------- */

let _pollTimer = null;

function applyDataUpdateStatus() {
    const status = settings.dataUpdateStatus || {};
    const el = document.getElementById('sync-status-text');
    if (!el) return;

    if (status.state === 'running') {
        el.textContent = t('autoSync.status.running', 'Syncing…');
        startUpdatePolling();
    } else if (status.success === true && status.finishedAt) {
        const when = new Date(status.finishedAt).toLocaleString();
        el.textContent = t('autoSync.status.success', `Last sync succeeded at ${when}`).replace('{time}', when);
    } else if (status.success === false && status.error) {
        el.textContent = t('autoSync.status.failed', `Last sync failed: ${status.error}`).replace('{error}', status.error);
    } else {
        el.textContent = t('autoSync.status.none', 'No sync has run yet.');
    }
}

async function triggerUpdate() {
    const btn = document.getElementById('btn-trigger-update');
    if (btn) { btn.disabled = true; btn.textContent = t('autoSync.syncing', 'Syncing…'); }
    try {
        const res = await fetch(`${API}/api/update-now`, { method: 'POST' });
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.error || res.statusText);
        }
        startUpdatePolling();
    } catch (err) {
        console.error('Trigger update failed', err);
        flash('flash.syncError', 'Failed to trigger sync: ' + err.message, true);
        if (btn) { btn.disabled = false; btn.textContent = t('autoSync.triggerButton', 'Sync Now'); }
    }
}

function startUpdatePolling() {
    stopUpdatePolling();
    _pollTimer = setInterval(pollUpdateStatus, 3000);
}

function stopUpdatePolling() {
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
}

async function pollUpdateStatus() {
    try {
        const res = await fetch(`${API}/api/settings`);
        if (!res.ok) return;
        const data = await res.json();
        settings.dataUpdateStatus = data.dataUpdateStatus;
        const status = data.dataUpdateStatus || {};

        applyDataUpdateStatus();
        if (status.state !== 'running') {
            stopUpdatePolling();
            const btn = document.getElementById('btn-trigger-update');
            if (btn) { btn.disabled = false; btn.textContent = t('autoSync.triggerButton', 'Sync Now'); }
            loadEmployeeStatus();
            if (status.success) {
                flash('flash.syncSuccess', 'Sync completed successfully.', false, { count: status.count || '?' });
            } else if (status.error) {
                flash('flash.syncError', `Sync failed: ${status.error}`, true);
            }
        }
    } catch (err) {
        console.error('Status poll error', err);
    }
}

/* ---------- URL previews & sub-item visibility ---------- */

function updateUrlPreviews() {
    const jsonName = (document.getElementById('directoryJsonFilename')?.value || 'microsip').trim() || 'microsip';
    const xmlName = (document.getElementById('directoryXmlFilename')?.value || 'yealink').trim() || 'yealink';
    const jsonPreview = document.getElementById('json-url-preview');
    const xmlPreview = document.getElementById('xml-url-preview');
    if (jsonPreview) {
        const jsonPath = `/directory/${jsonName}.json`;
        jsonPreview.textContent = jsonPath;
        jsonPreview.href = jsonPath;
    }
    if (xmlPreview) {
        const xmlPath = `/directory/${xmlName}.xml`;
        xmlPreview.textContent = xmlPath;
        xmlPreview.href = xmlPath;
    }
}

function updateSubItemVisibility() {
    const jsonRow = document.getElementById('json-filename-row');
    const xmlRow = document.getElementById('xml-filename-row');
    const timeRow = document.getElementById('update-time-row');
    if (jsonRow) jsonRow.style.display = document.getElementById('directoryJsonEnabled')?.checked ? 'flex' : 'none';
    if (xmlRow) xmlRow.style.display = document.getElementById('directoryXmlEnabled')?.checked ? 'flex' : 'none';
    if (timeRow) timeRow.style.display = document.getElementById('autoUpdateEnabled')?.checked ? 'flex' : 'none';
}

/* ---------- event wiring ---------- */

document.addEventListener('DOMContentLoaded', () => {
    // Initialise time picker
    initTimePicker();

    // Load data
    loadSettings();
    loadEmployeeStatus();
    loadAzureStatus();

    // Save button
    document.getElementById('btn-save')?.addEventListener('click', saveSettings);

    // Azure sync button
    document.getElementById('btn-azure-sync')?.addEventListener('click', azureSync);

    // Clear button
    document.getElementById('btn-clear-employees')?.addEventListener('click', clearEmployees);

    // Manual trigger
    document.getElementById('btn-trigger-update')?.addEventListener('click', triggerUpdate);

    // Add swap rule button
    document.getElementById('btn-add-swap')?.addEventListener('click', () => {
        const list = document.getElementById('swap-list');
        if (!list) return;
        const count = list.querySelectorAll('.swap-row').length;
        if (count >= getMaxSwaps()) return;
        const row = createSwapRow();
        list.appendChild(row);
        row.querySelector('.swap-find')?.focus();
        updateSwapCounter();
        updateSwapArrowStates();
    });

    // Add contact row button
    document.getElementById('btn-add-contact')?.addEventListener('click', () => {
        const list = document.getElementById('custom-contacts-list');
        if (!list) return;
        const count = list.querySelectorAll('.custom-contact-row').length;
        if (count >= getMaxContacts()) return;
        const row = createContactRow();
        list.appendChild(row);
        row.querySelector('.contact-name')?.focus();
        updateContactCounter();
        updateArrowStates();
    });

    // Toggle sub-items & URL previews
    document.getElementById('directoryJsonEnabled')?.addEventListener('change', updateSubItemVisibility);
    document.getElementById('directoryXmlEnabled')?.addEventListener('change', updateSubItemVisibility);
    document.getElementById('autoUpdateEnabled')?.addEventListener('change', updateSubItemVisibility);
    document.getElementById('directoryJsonFilename')?.addEventListener('input', updateUrlPreviews);
    document.getElementById('directoryXmlFilename')?.addEventListener('input', updateUrlPreviews);
});
