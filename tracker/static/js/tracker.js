(() => {
  const toastEl = document.getElementById('toast');
  let toastTimer;
  function toast(message, isError = false) {
    if (!toastEl) return;
    clearTimeout(toastTimer);
    toastEl.textContent = message;
    toastEl.classList.toggle('error', isError);
    toastEl.classList.add('show');
    toastTimer = setTimeout(() => toastEl.classList.remove('show'), 2200);
  }

  async function jsonFetch(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    });
    const data = response.headers.get('content-type')?.includes('application/json')
      ? await response.json()
      : { error: await response.text() };
    if (!response.ok) throw new Error(data.error || 'Request failed');
    return data;
  }

  // ---------------- Tasks ----------------
  const taskCards = [...document.querySelectorAll('.task-card')];
  if (taskCards.length) {
    document.querySelectorAll('.task-status, .task-owner, .task-revised').forEach((el) => {
      el.addEventListener('change', async () => {
        const tid = el.dataset.task;
        const card = document.querySelector(`.task-card[data-task-id="${CSS.escape(tid)}"]`);
        const status = card.querySelector('.task-status').value;
        const owner = card.querySelector('.task-owner').value;
        const revised = card.querySelector('.task-revised').value;
        try {
          await jsonFetch(`/api/tasks/${encodeURIComponent(tid)}`, {
            method: 'PATCH', body: JSON.stringify({ status, owner, revised }),
          });
          if (el.classList.contains('task-status')) {
            el.className = `field-input status-${status} task-status`;
          }
          toast(`Saved ${tid}`);
        } catch (err) {
          toast(err.message, true);
        }
      });
    });

    const saveAllBtn = document.getElementById('saveAllBtn');
    saveAllBtn?.addEventListener('click', async () => {
      const tasks = taskCards.map((card) => ({
        id: card.dataset.taskId,
        status: card.querySelector('.task-status').value,
        owner: card.querySelector('.task-owner').value,
        revised: card.querySelector('.task-revised').value,
      }));
      try {
        const result = await jsonFetch('/api/tasks/bulk', { method: 'POST', body: JSON.stringify({ tasks }) });
        if (result.errors?.length) toast(result.errors.join('; '), true);
        else toast('All visible changes saved.');
      } catch (err) { toast(err.message, true); }
    });
  }

  // ---------------- Notes modal ----------------
  const modal = document.getElementById('notesModal');
  if (modal) {
    const title = document.getElementById('notesTitle');
    const taskName = document.getElementById('notesTaskName');
    const list = document.getElementById('notesList');
    const dateInput = document.getElementById('noteDate');
    const categoryInput = document.getElementById('noteCategory');
    const textInput = document.getElementById('noteText');
    const editIndex = document.getElementById('noteEditIndex');
    const saveBtn = document.getElementById('saveNoteBtn');
    let currentTask = null;
    let currentNotes = [];

    const categoryLabels = {
      accomplishment: 'Accomplishment', challenge: 'Challenge / Help Needed', goal: 'Goal for Next Week', note: 'General Note'
    };

    function clearForm() {
      editIndex.value = '';
      dateInput.value = new Date().toISOString().slice(0,10);
      categoryInput.value = 'note';
      textInput.value = '';
      saveBtn.textContent = 'Add Note';
    }

    function updateTaskNoteSummary() {
      const countEl = document.querySelector(`[data-note-count="${CSS.escape(currentTask)}"]`);
      if (countEl) countEl.textContent = currentNotes.length;
      const preview = document.querySelector(`[data-note-preview="${CSS.escape(currentTask)}"]`);
      if (preview) {
        if (!currentNotes.length) preview.textContent = 'No notes yet';
        else {
          const n = currentNotes[currentNotes.length - 1];
          preview.textContent = `${n.date || 'undated'} · ${categoryLabels[n.category] || n.category}: ${n.text.slice(0, 90)}${n.text.length > 90 ? '…' : ''}`;
        }
      }
    }

    function renderNotes() {
      list.innerHTML = '';
      if (!currentNotes.length) {
        list.innerHTML = '<div class="empty-state compact">No notes yet.</div>';
        return;
      }
      currentNotes.forEach((note, idx) => {
        const row = document.createElement('div');
        row.className = 'note-row';
        row.innerHTML = `
          <div class="note-row-head">
            <div class="note-row-meta">${note.date || 'undated'} · ${categoryLabels[note.category] || note.category}</div>
            <div class="note-actions">
              <button type="button" data-edit-note="${idx}">Edit</button>
              <button type="button" class="delete" data-delete-note="${idx}">Delete</button>
            </div>
          </div>
          <div class="note-row-text"></div>`;
        row.querySelector('.note-row-text').textContent = note.text;
        list.appendChild(row);
      });

      list.querySelectorAll('[data-edit-note]').forEach((btn) => btn.addEventListener('click', () => {
        const idx = Number(btn.dataset.editNote); const note = currentNotes[idx];
        editIndex.value = String(idx); dateInput.value = note.date || ''; categoryInput.value = note.category; textInput.value = note.text;
        saveBtn.textContent = 'Save Edit'; textInput.focus();
      }));
      list.querySelectorAll('[data-delete-note]').forEach((btn) => btn.addEventListener('click', async () => {
        const idx = Number(btn.dataset.deleteNote);
        if (!confirm('Delete this note entry?')) return;
        try {
          const data = await jsonFetch(`/api/tasks/${encodeURIComponent(currentTask)}/notes/${idx}`, { method: 'DELETE' });
          currentNotes = data.notes; renderNotes(); updateTaskNoteSummary(); clearForm(); toast('Note deleted.');
        } catch (err) { toast(err.message, true); }
      }));
    }

    async function openNotes(tid) {
      try {
        const data = await jsonFetch(`/api/tasks/${encodeURIComponent(tid)}/notes`);
        currentTask = tid; currentNotes = data.notes;
        title.textContent = `Notes — ${tid}`; taskName.textContent = data.task.name;
        renderNotes(); clearForm();
        modal.classList.remove('hidden'); modal.setAttribute('aria-hidden', 'false');
      } catch (err) { toast(err.message, true); }
    }

    document.querySelectorAll('[data-open-notes]').forEach((btn) => btn.addEventListener('click', () => openNotes(btn.dataset.openNotes)));
    document.getElementById('closeNotes')?.addEventListener('click', () => { modal.classList.add('hidden'); modal.setAttribute('aria-hidden','true'); });
    modal.addEventListener('click', (e) => { if (e.target === modal) { modal.classList.add('hidden'); modal.setAttribute('aria-hidden','true'); } });
    document.getElementById('clearNoteBtn')?.addEventListener('click', clearForm);
    saveBtn?.addEventListener('click', async () => {
      const payload = { date: dateInput.value, category: categoryInput.value, text: textInput.value.trim() };
      if (!payload.text) { toast('Enter note text first.', true); return; }
      const idx = editIndex.value;
      try {
        const url = idx === '' ? `/api/tasks/${encodeURIComponent(currentTask)}/notes` : `/api/tasks/${encodeURIComponent(currentTask)}/notes/${idx}`;
        const method = idx === '' ? 'POST' : 'PUT';
        const data = await jsonFetch(url, { method, body: JSON.stringify(payload) });
        currentNotes = data.notes; renderNotes(); updateTaskNoteSummary(); clearForm(); toast(idx === '' ? 'Note added.' : 'Note updated.');
      } catch (err) { toast(err.message, true); }
    });
  }

  // ---------------- Slides page ----------------
  // Detect the Slides DOM directly rather than relying only on a page flag.
  // The previous build loaded tracker.js before the flag was defined, so none
  // of the Load Candidate / Export PPTX click handlers were registered.
  const slidesCandidateList = document.getElementById('candidateList');
  if (slidesCandidateList) {
    const rangeFrom = document.getElementById('rangeFrom');
    const rangeTo = document.getElementById('rangeTo');
    const candidateList = slidesCandidateList;

    const includedOwners = () => [...document.querySelectorAll('.owner-include:checked')].map((x) => x.value);

    async function loadCandidates() {
      const params = new URLSearchParams({ from: rangeFrom.value, to: rangeTo.value });
      includedOwners().forEach((o) => params.append('owner', o));
      candidateList.innerHTML = '<div class="empty-state compact">Loading candidate notes…</div>';
      try {
        const data = await jsonFetch(`/api/slide-candidates?${params}`);
        candidateList.innerHTML = '';
        if (!data.owners.length) {
          candidateList.innerHTML = '<div class="empty-state compact">No accomplishment/challenge/goal notes found for the selected teammates and date range.</div>';
          return;
        }
        data.owners.forEach((owner) => {
          const wrap = document.createElement('div'); wrap.className = 'candidate-owner';
          const h = document.createElement('h3'); h.textContent = `${owner.full_name} — ${owner.role}`; wrap.appendChild(h);
          owner.items.forEach((item) => {
            const label = document.createElement('label'); label.className = 'candidate-item';
            const cb = document.createElement('input'); cb.type = 'checkbox'; cb.className = 'candidate-note'; cb.value = item.token; cb.checked = true;
            const body = document.createElement('div'); body.className = 'candidate-text';
            const main = document.createElement('div'); main.textContent = `${item.tid}: ${item.text}`;
            const meta = document.createElement('div'); meta.className = 'candidate-meta'; meta.textContent = `[${item.date || 'undated'}] ${item.category_label}`;
            body.append(main, meta); label.append(cb, body); wrap.appendChild(label);
          });
          candidateList.appendChild(wrap);
        });
      } catch (err) {
        candidateList.innerHTML = `<div class="empty-state compact error-state">${String(err.message)}</div>`;
        toast(err.message, true);
      }
    }

    document.getElementById('loadCandidates')?.addEventListener('click', loadCandidates);
    document.querySelectorAll('.owner-include').forEach((cb) => cb.addEventListener('change', () => {
      // Keep displayed candidates synchronized once user has loaded them.
      if (candidateList.querySelector('.candidate-owner')) loadCandidates();
    }));

    document.getElementById('recalcWeek')?.addEventListener('click', async () => {
      const d = document.getElementById('meetingDate').value;
      try {
        const data = await jsonFetch(`/api/week-number?date=${encodeURIComponent(d)}`);
        document.getElementById('weekNum').value = data.week_num;
      } catch (err) { toast(err.message, true); }
    });

    document.getElementById('exportPptx')?.addEventListener('click', async () => {
      const exportBtn = document.getElementById('exportPptx');
      const owners = includedOwners();
      const selected_notes = [...document.querySelectorAll('.candidate-note:checked')].map((x) => x.value);
      const payload = {
        meeting_date: document.getElementById('meetingDate').value,
        week_num: Number(document.getElementById('weekNum').value),
        owners, selected_notes,
      };
      if (!selected_notes.length && !confirm('No notes are selected. Export Labor Status only?')) return;
      const priorText = exportBtn?.textContent;
      if (exportBtn) { exportBtn.disabled = true; exportBtn.textContent = 'Generating PPTX…'; }
      try {
        const res = await fetch('/export/pptx', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (!res.ok) {
          let msg = 'Export failed';
          try { msg = (await res.json()).error || msg; } catch (_) { msg = await res.text(); }
          throw new Error(msg);
        }
        const blob = await res.blob();
        const cd = res.headers.get('Content-Disposition') || '';
        const match = cd.match(/filename="?([^";]+)"?/i);
        const filename = match ? match[1] : `TAT_Week${payload.week_num}_Squish_Therapy.pptx`;
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = filename; a.style.display = 'none';
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
        toast('PowerPoint exported.');
      } catch (err) {
        toast(err.message, true);
        alert(`PowerPoint export failed: ${err.message}`);
      } finally {
        if (exportBtn) { exportBtn.disabled = false; exportBtn.textContent = priorText || 'Export PPTX'; }
      }
    });

    // Populate the page immediately so it is obvious that candidate loading works.
    loadCandidates();
  }

  // ---------------- Bill of Materials page ----------------
  const bomTable = document.getElementById('bomTable');
  if (bomTable) {
    const bomBody = document.getElementById('bomBody');
    const bomSort = document.getElementById('bomSort');
    const topScroll = document.getElementById('bomTopScroll');
    const topSpacer = document.getElementById('bomTopScrollSpacer');
    const bodyScroll = document.getElementById('bomScrollBody');

    function money(v) {
      const n = Number(v);
      return Number.isFinite(n) ? `$${n.toFixed(2)}` : '$0.00';
    }

    function applyBomSummary(summary) {
      if (!summary) return;
      const itemCount = document.getElementById('bomItemCount');
      const categoryCount = document.getElementById('bomCategoryCount');
      const knownCost = document.getElementById('bomKnownCost');
      const remaining = document.getElementById('bomRemaining');
      if (itemCount) itemCount.textContent = summary.item_count;
      if (categoryCount) categoryCount.textContent = summary.category_count;
      if (knownCost) knownCost.textContent = money(summary.known_cost);
      if (remaining) {
        remaining.textContent = money(summary.remaining);
        remaining.closest('.bom-kpi')?.classList.toggle('budget-over', Number(summary.remaining) < 0);
      }
    }

    function rowValue(row, field) {
      return (row.querySelector(`[data-field="${field}"]`)?.value || '').trim();
    }

    function textCompare(a, b) {
      return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
    }

    function priceValue(row) {
      const raw = rowValue(row, 'price_link');
      if (!raw) return null;
      if (raw.toUpperCase() === 'FREE') return 0;
      const n = Number(raw.replace(/[$,]/g, '').trim());
      return Number.isFinite(n) ? n : null;
    }

    function sortBomRows() {
      if (!bomBody || !bomSort) return;
      const mode = bomSort.value;
      const rows = [...bomBody.querySelectorAll('.bom-row')];
      const compare = (a, b) => {
        if (mode === 'original') {
          return Number(a.dataset.originalIndex || 0) - Number(b.dataset.originalIndex || 0);
        }
        if (mode === 'price-asc' || mode === 'price-desc') {
          const av = priceValue(a), bv = priceValue(b);
          // Keep blank/non-numeric prices at the bottom in either direction.
          if (av === null && bv === null) return 0;
          if (av === null) return 1;
          if (bv === null) return -1;
          return mode === 'price-asc' ? av - bv : bv - av;
        }
        const [field, direction] = mode.split('-');
        const cmp = textCompare(rowValue(a, field), rowValue(b, field));
        return direction === 'desc' ? -cmp : cmp;
      };
      rows.sort(compare).forEach((row) => bomBody.appendChild(row));
    }

    bomSort?.addEventListener('change', sortBomRows);

    // Sync a larger horizontal scrollbar above the table with the normal one below it.
    function updateTopScrollbar() {
      if (!topScroll || !topSpacer || !bodyScroll) return;
      topSpacer.style.width = `${bodyScroll.scrollWidth}px`;
      topScroll.scrollLeft = bodyScroll.scrollLeft;
    }
    let syncingScroll = false;
    topScroll?.addEventListener('scroll', () => {
      if (syncingScroll || !bodyScroll) return;
      syncingScroll = true;
      bodyScroll.scrollLeft = topScroll.scrollLeft;
      requestAnimationFrame(() => { syncingScroll = false; });
    });
    bodyScroll?.addEventListener('scroll', () => {
      if (syncingScroll || !topScroll) return;
      syncingScroll = true;
      topScroll.scrollLeft = bodyScroll.scrollLeft;
      requestAnimationFrame(() => { syncingScroll = false; });
    });
    requestAnimationFrame(updateTopScrollbar);
    window.addEventListener('resize', updateTopScrollbar);
    if (window.ResizeObserver && bodyScroll) {
      new ResizeObserver(updateTopScrollbar).observe(bodyScroll);
    }

    function refreshOpenLink(row) {
      const input = row?.querySelector('.bom-link-input');
      const open = row?.querySelector('.bom-open-link');
      if (!input || !open) return;
      const value = input.value.trim();
      const usable = /^https?:\/\//i.test(value);
      open.href = usable ? value : '#';
      open.classList.toggle('is-disabled', !usable);
      if (usable) {
        open.removeAttribute('aria-disabled');
        open.removeAttribute('tabindex');
      } else {
        open.setAttribute('aria-disabled', 'true');
        open.setAttribute('tabindex', '-1');
      }
    }

    bomTable.addEventListener('change', async (event) => {
      const field = event.target.closest('.bom-field');
      if (!field) return;
      const row = field.closest('.bom-row');
      const id = row?.dataset.bomId;
      if (!id) return;
      field.classList.add('saving');
      try {
        const data = await jsonFetch(`/api/bom/items/${encodeURIComponent(id)}`, {
          method: 'PATCH',
          body: JSON.stringify({ [field.dataset.field]: field.value }),
        });
        applyBomSummary(data.summary);
        if (field.dataset.field === 'link') refreshOpenLink(row);
        sortBomRows();
        toast(`Saved BOM item ${id}`);
      } catch (err) {
        toast(err.message, true);
      } finally {
        field.classList.remove('saving');
      }
    });

    bomTable.addEventListener('click', async (event) => {
      const btn = event.target.closest('.bom-delete');
      if (!btn) return;
      const row = btn.closest('.bom-row');
      const id = row?.dataset.bomId;
      if (!id || !confirm('Delete this BOM item?')) return;
      btn.disabled = true;
      try {
        const data = await jsonFetch(`/api/bom/items/${encodeURIComponent(id)}`, { method: 'DELETE' });
        row.remove();
        applyBomSummary(data.summary);
        updateTopScrollbar();
        toast('BOM item deleted.');
        if (!document.querySelector('.bom-row')) {
          document.getElementById('bomBody').innerHTML = '<tr id="bomEmptyRow"><td colspan="9" class="empty-table">No BOM items yet. Add one above.</td></tr>';
        }
      } catch (err) {
        btn.disabled = false;
        toast(err.message, true);
      }
    });

    document.getElementById('bomAddForm')?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const formData = new FormData(form);
      const payload = Object.fromEntries(formData.entries());
      try {
        await jsonFetch('/api/bom/items', { method: 'POST', body: JSON.stringify(payload) });
        toast('BOM item added.');
        // Reload keeps the server-rendered table and persisted JSON perfectly in sync.
        window.location.reload();
      } catch (err) { toast(err.message, true); }
    });

    document.getElementById('bomBudget')?.addEventListener('change', async (event) => {
      try {
        const data = await jsonFetch('/api/bom/settings', {
          method: 'PATCH', body: JSON.stringify({ budget: event.target.value }),
        });
        applyBomSummary(data.summary);
        toast('BOM budget saved.');
      } catch (err) { toast(err.message, true); }
    });
  }
})();
