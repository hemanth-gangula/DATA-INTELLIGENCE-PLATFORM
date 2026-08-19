/**
 * DataIntelligence — Frontend Application
 * Single-page app managing all views, API calls, charts and agent chat.
 */

'use strict';

// ═══════════════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════════════
const State = {
  datasetId:      null,
  datasetName:    '',
  currentVersion: null,   // full version object
  versions:       [],
  currentPage:    'upload',
  tableState:     { page: 1, perPage: 50, sortCol: '', sortDir: 'asc', search: '', filterCol: '', filterVal: '' },
  charts:         {},     // Chart.js instances keyed by canvas id
  agentBusy:      false,
};

// ═══════════════════════════════════════════════════════════════════
// API helpers
// ═══════════════════════════════════════════════════════════════════
const API = {
  async post(url, data, isFormData = false) {
    const opts = { method: 'POST' };
    if (isFormData) {
      opts.body = data;
    } else {
      opts.headers = { 'Content-Type': 'application/json' };
      opts.body = JSON.stringify(data);
    }
    const res = await fetch(url, opts);
    return res.json();
  },
  async get(url) {
    const res = await fetch(url);
    return res.json();
  },
};

// ═══════════════════════════════════════════════════════════════════
// MAIN APP
// ═══════════════════════════════════════════════════════════════════
const App = {

  // ── Initialisation ──────────────────────────────────────────────
  init() {
    feather.replace();
    this.bindSidebar();
    this.bindUpload();
    this.bindVersionSelector();
    this.bindTableSearch();
    this.bindAgentEnter();
    this.loadTools();
    this.showPage('upload');
  },

  // ── Navigation ───────────────────────────────────────────────────
  showPage(name) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

    const page = document.getElementById(`page-${name}`);
    if (page) page.classList.add('active');

    const navItem = document.querySelector(`.nav-item[data-page="${name}"]`);
    if (navItem) navItem.classList.add('active');

    const titles = {
      upload: 'Upload', dashboard: 'Dashboard', data: 'Excel Data',
      agent: 'AI Agent', insights: 'AI Insights', reports: 'Reports', history: 'History',
    };
    document.getElementById('pageTitle').textContent = titles[name] || name;
    State.currentPage = name;

    if (State.datasetId) {
      document.getElementById('versionSelectorWrap').style.display = 'flex';
    }

    // Lazy load page data
    if (name === 'dashboard' && State.datasetId)  this.loadDashboard();
    if (name === 'data'      && State.datasetId)  this.loadTable();
    if (name === 'insights'  && State.datasetId)  this.loadInsights(false);
    if (name === 'reports'   && State.datasetId)  this.loadReport();
    if (name === 'history'   && State.datasetId)  this.loadHistory();
  },

  bindSidebar() {
    document.querySelectorAll('.nav-item').forEach(item => {
      item.addEventListener('click', e => {
        e.preventDefault();
        const page = item.dataset.page;
        if (page === 'dashboard' && !State.datasetId) {
          this.showPage('upload');
        } else {
          this.showPage(page);
        }
      });
    });
    document.getElementById('uploadNewBtn').addEventListener('click', () => {
      document.getElementById('fileInput').click();
    });
    document.getElementById('sidebarToggle').addEventListener('click', () => {
      document.getElementById('sidebar').classList.toggle('open');
    });
  },

  // ── Upload ───────────────────────────────────────────────────────
  bindUpload() {
    const fileInput = document.getElementById('fileInput');
    const dropzone  = document.getElementById('dropzone');

    fileInput.addEventListener('change', e => {
      if (e.target.files.length) this.processUpload(e.target.files[0]);
    });

    dropzone.addEventListener('dragover', e => {
      e.preventDefault();
      dropzone.classList.add('drag-over');
    });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
    dropzone.addEventListener('drop', e => {
      e.preventDefault();
      dropzone.classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (file) this.processUpload(file);
    });
  },

  async processUpload(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    if (!['xlsx', 'xls'].includes(ext)) {
      this.notify('Only .xlsx and .xls files are supported.', 'error');
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      this.notify('File exceeds the 50 MB limit.', 'error');
      return;
    }

    // Show progress
    const progress  = document.getElementById('uploadProgress');
    const content   = document.getElementById('dropzoneContent');
    const statusTxt = document.getElementById('uploadStatusText');
    const pBar      = document.getElementById('progressBar');
    const steps     = document.getElementById('progressSteps');

    content.style.display  = 'none';
    progress.style.display = 'flex';

    const stepList = [
      'Uploading file…',
      'Detecting workbook structure…',
      'Analysing data quality…',
      'Applying safe automatic cleaning…',
      'Saving to Supabase…',
      'Generating AI insights…',
      'Finalising…',
    ];
    let stepIdx = 0;
    const stepTimer = setInterval(() => {
      if (stepIdx < stepList.length) {
        statusTxt.textContent = stepList[stepIdx];
        pBar.style.width = `${Math.min(90, (stepIdx + 1) / stepList.length * 90)}%`;
        steps.innerHTML = stepList.slice(0, stepIdx + 1)
          .map((s, i) => `<div style="color:${i === stepIdx ? 'var(--primary)' : 'var(--text-dim)'}">✓ ${s}</div>`)
          .join('');
        stepIdx++;
      }
    }, 600);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const result = await API.post('/api/upload/', formData, true);
      clearInterval(stepTimer);
      pBar.style.width = '100%';
      statusTxt.textContent = 'Complete!';

      if (!result.success) {
        this.uploadError(result.error || 'Upload failed.', content, progress);
        return;
      }

      // Persist state
      State.datasetId   = result.dataset_id;
      State.datasetName = result.dataset_name;

      await this.refreshVersions();
      this.updateSidebarBadge();
      this.showUploadModal(result);

    } catch (err) {
      clearInterval(stepTimer);
      this.uploadError(`Network error: ${err.message}`, content, progress);
    }
  },

  uploadError(msg, content, progress) {
    if (content && progress) {
      content.style.display  = 'flex';
      progress.style.display = 'none';
    }
    this.notify(msg, 'error');
  },

  showUploadModal(result) {
    const cr = result.cleaning_report || {};
    const isClean = !cr.cleaning_required;

    const icon = isClean
      ? `<div class="upload-result-icon clean"><i data-feather="check-circle"></i></div>`
      : `<div class="upload-result-icon success"><i data-feather="shield"></i></div>`;

    const statusBadge = isClean
      ? `<span style="color:var(--green);font-weight:600;">✓ Data is already clean — no changes made</span>`
      : `<span style="color:var(--primary);font-weight:600;">✓ Automatic cleaning completed</span>`;

    const statsHtml = `
      <div class="upload-stats-grid">
        <div class="upload-stat-box">
          <div class="label">Original Rows</div>
          <div class="value">${fmt(cr.original_rows)}</div>
        </div>
        <div class="upload-stat-box">
          <div class="label">Final Rows</div>
          <div class="value" style="color:var(--green)">${fmt(cr.final_rows)}</div>
        </div>
        <div class="upload-stat-box">
          <div class="label">Duplicates Removed</div>
          <div class="value" style="color:var(--red)">${fmt(cr.duplicates_removed)}</div>
        </div>
        <div class="upload-stat-box">
          <div class="label">Blank Rows Removed</div>
          <div class="value" style="color:var(--orange)">${fmt(cr.blank_rows_removed)}</div>
        </div>
        <div class="upload-stat-box">
          <div class="label">Missing Values</div>
          <div class="value">${fmt(cr.missing_values_remaining)}</div>
        </div>
        <div class="upload-stat-box">
          <div class="label">Columns Modified</div>
          <div class="value">${fmt(cr.columns_modified_count)}</div>
        </div>
      </div>`;

    const opsHtml = (cr.operations || []).length
      ? `<div style="font-size:.82rem;color:var(--text-muted);margin-bottom:12px">
           ${cr.operations.map(o => `<div>• ${esc(o)}</div>`).join('')}
         </div>`
      : '';

    const dlHtml = `
      <div style="display:flex;gap:10px;margin-top:4px;">
        <a href="/api/downloads/excel/${State.datasetId}" class="btn btn-outline-green btn-sm">
          <i data-feather="download"></i> Download Excel
        </a>
        <a href="/api/downloads/csv/${State.datasetId}" class="btn btn-outline-blue btn-sm">
          <i data-feather="download"></i> Download CSV
        </a>
      </div>`;

    document.getElementById('uploadModalTitle').textContent = `Upload Complete — ${esc(result.dataset_name)}`;
    document.getElementById('uploadModalBody').innerHTML = `
      <div class="upload-result-header">
        ${icon}
        <div>
          <div style="font-weight:700;margin-bottom:4px;">${esc(result.original_filename)}</div>
          <div style="font-size:.8rem;color:var(--text-muted)">${esc(result.sheet_name)} · ${esc(String(result.workbook_meta?.total_sheets || 1))} sheet(s)</div>
        </div>
      </div>
      <div style="margin-bottom:12px">${statusBadge}</div>
      ${statsHtml}
      ${opsHtml}
      ${dlHtml}
    `;

    document.getElementById('uploadResultModal').style.display = 'flex';
    feather.replace();
  },

  closeModal(id) {
    document.getElementById(id).style.display = 'none';
  },

  goToDashboard() {
    this.closeModal('uploadResultModal');
    this.showPage('dashboard');
  },

  // ── Version selector ─────────────────────────────────────────────
  bindVersionSelector() {
    document.getElementById('versionSelector').addEventListener('change', async (e) => {
      const versionId = e.target.value;
      const v = State.versions.find(v => v.id === versionId);
      if (v) {
        State.currentVersion = v;
        this.updateSidebarBadge();
        if (State.currentPage !== 'upload') this.showPage(State.currentPage);
      }
    });
  },

  async refreshVersions() {
    if (!State.datasetId) return;
    const result = await API.get(`/api/history/${State.datasetId}`);
    if (result.success) {
      State.versions = result.history || [];
      const current = State.versions.find(v => v.is_current) || State.versions[State.versions.length - 1];
      State.currentVersion = current || null;
      this.populateVersionSelector();
    }
  },

  populateVersionSelector() {
    const sel = document.getElementById('versionSelector');
    sel.innerHTML = State.versions.map(v =>
      `<option value="${v.id}" ${v.is_current ? 'selected' : ''}>
        v${v.version_number} — ${esc(v.label?.substring(0, 40))}
       </option>`
    ).join('');
    document.getElementById('versionSelectorWrap').style.display = 'flex';
  },

  currentVersionId() {
    return State.currentVersion?.id || null;
  },

  updateSidebarBadge() {
    if (!State.datasetId) return;
    document.getElementById('sidebarDatasetBadge').style.display = 'flex';
    document.getElementById('sidebarDatasetName').textContent = State.datasetName;
    const v = State.currentVersion;
    document.getElementById('sidebarVersionLabel').textContent = v ? `v${v.version_number} · ${v.label?.substring(0, 30)}` : '—';
    feather.replace();
  },

  // ── DASHBOARD ────────────────────────────────────────────────────
  async loadDashboard() {
    const vid = this.currentVersionId();
    const url = `/api/dashboard/${State.datasetId}` + (vid ? `?version_id=${vid}` : '');

    try {
      const result = await API.get(url);
      if (!result.success) { this.notify(result.error, 'error'); return; }
      const d = result.dashboard;

      // KPIs
      this.renderKpis(d.kpis || []);
      // Charts
      this.renderCharts(d.charts || []);
      // Cleaning banner
      this.showCleaningBanner();
      // Download bar
      const dlBar = document.getElementById('dashDownloadBar');
      dlBar.style.display = 'flex';
      document.getElementById('dashDlExcel').onclick = () =>
        window.location = `/api/downloads/excel/${State.datasetId}${vid ? '?version_id=' + vid : ''}`;
      document.getElementById('dashDlCsv').onclick = () =>
        window.location = `/api/downloads/csv/${State.datasetId}${vid ? '?version_id=' + vid : ''}`;

    } catch (err) {
      this.notify('Dashboard load failed: ' + err.message, 'error');
    }
  },

  renderKpis(kpis) {
    const grid = document.getElementById('kpiGrid');
    if (!kpis.length) {
      grid.innerHTML = '<p style="color:var(--text-muted);padding:20px">No KPIs available.</p>';
      return;
    }
    grid.innerHTML = kpis.map(k => `
      <div class="kpi-card ${k.color || 'blue'}">
        <div class="kpi-header">
          <span class="kpi-label">${esc(k.label)}</span>
          <div class="kpi-icon"><i data-feather="${k.icon || 'bar-chart-2'}"></i></div>
        </div>
        <div class="kpi-value">${esc(String(k.value))}</div>
        <div class="kpi-sub">${esc(k.sub_label || '')}</div>
      </div>
    `).join('');
    feather.replace();
  },

  renderCharts(charts) {
    // Destroy previous chart instances
    Object.values(State.charts).forEach(c => { try { c.destroy(); } catch(e){} });
    State.charts = {};

    const grid1 = document.getElementById('chartsGrid');
    const grid2 = document.getElementById('chartsGrid2');
    grid1.innerHTML = '';
    grid2.innerHTML = '';

    if (!charts.length) {
      grid1.innerHTML = '<p style="color:var(--text-muted);padding:20px">No charts available for this dataset.</p>';
      return;
    }

    charts.forEach((chart, idx) => {
      const canvasId = `chart_${chart.id || idx}`;
      const card = document.createElement('div');
      card.className = 'chart-card';
      card.innerHTML = `
        <div class="chart-title">${esc(chart.title)}</div>
        <div class="chart-container"><canvas id="${canvasId}"></canvas></div>
      `;
      if (idx < 2) grid1.appendChild(card);
      else         grid2.appendChild(card);
    });

    // Create Chart.js instances after DOM is updated
    requestAnimationFrame(() => {
      charts.forEach((chart, idx) => {
        const canvasId = `chart_${chart.id || idx}`;
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        const instance = this.createChart(canvas, chart);
        if (instance) State.charts[canvasId] = instance;
      });
    });
  },

  createChart(canvas, spec) {
    const type = spec.type === 'area' ? 'line' : spec.type;
    const colors = [
      '#6366f1','#10b981','#3b82f6','#f59e0b','#ef4444',
      '#a855f7','#14b8a6','#f97316','#ec4899','#84cc16',
    ];
    const bgColors = colors.map(c => c + '33');

    const isLine = type === 'line';
    const isPie  = type === 'pie' || type === 'doughnut';

    const datasets = [{
      label: spec.y_label || 'Value',
      data:  spec.values  || [],
      backgroundColor: isPie ? colors.slice(0, spec.values?.length || 8) : (isLine ? bgColors[0] : colors[0] + '99'),
      borderColor:     isPie ? colors.slice(0, spec.values?.length || 8) : colors[0],
      borderWidth: isLine ? 2 : 1,
      fill: spec.type === 'area',
      tension: 0.4,
      pointRadius: isLine ? 3 : 0,
    }];

    try {
      return new Chart(canvas, {
        type: isPie ? 'doughnut' : (type || 'bar'),
        data: { labels: spec.labels || [], datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: isPie,
              labels: { color: '#8892a4', font: { size: 11 }, boxWidth: 12 },
            },
            tooltip: {
              backgroundColor: '#1c2233',
              borderColor: '#2a3042',
              borderWidth: 1,
              titleColor: '#e2e8f0',
              bodyColor: '#8892a4',
              padding: 10,
            },
          },
          scales: isPie ? {} : {
            x: {
              ticks: { color: '#8892a4', font: { size: 10 }, maxRotation: 45 },
              grid:  { color: '#2a304233' },
            },
            y: {
              ticks: { color: '#8892a4', font: { size: 10 } },
              grid:  { color: '#2a304255' },
            },
          },
        },
      });
    } catch(e) {
      console.warn('Chart creation failed:', e);
      return null;
    }
  },

  showCleaningBanner() {
    // This would be shown when loading the dashboard right after upload
    // It's populated from the upload result stored client-side
    const banner = document.getElementById('cleaningBanner');
    banner.style.display = 'none'; // Will be shown by upload flow
  },

  // ── DATA TABLE ───────────────────────────────────────────────────
  async loadTable() {
    const s = State.tableState;
    const vid = this.currentVersionId();
    const params = new URLSearchParams({
      page:        s.page,
      per_page:    s.perPage,
      search:      s.search,
      sort_col:    s.sortCol,
      sort_dir:    s.sortDir,
      filter_col:  s.filterCol,
      filter_val:  s.filterVal,
    });
    if (vid) params.set('version_id', vid);

    try {
      const result = await API.get(`/api/data/preview/${State.datasetId}?${params}`);
      if (!result.success) { this.notify(result.error, 'error'); return; }

      this.renderTable(result);
      this.renderPagination(result.page, result.total_pages, result.total_rows);
      this.renderFilterOptions(result.columns);
      document.getElementById('tableStats').textContent =
        `${fmt(result.total_rows)} rows · ${result.total_columns} columns · ${result.version_label || ''}`;

      const dlVid = vid || '';
      document.getElementById('dataDlExcel').onclick = () =>
        window.location = `/api/downloads/excel/${State.datasetId}?version_id=${dlVid}`;
      document.getElementById('dataDlCsv').onclick = () =>
        window.location = `/api/downloads/csv/${State.datasetId}?version_id=${dlVid}`;
    } catch(err) {
      this.notify('Table load failed: ' + err.message, 'error');
    }
  },

  renderTable(result) {
    const table   = document.getElementById('dataTable');
    const empty   = document.getElementById('tableEmpty');
    const thead   = document.getElementById('dataTableHead');
    const tbody   = document.getElementById('dataTableBody');
    const s       = State.tableState;

    if (!result.rows.length) {
      table.style.display = 'none';
      empty.style.display = 'flex';
      return;
    }
    empty.style.display = 'none';
    table.style.display = 'table';

    thead.innerHTML = `<tr>${result.columns.map(col => {
      const isSorted = s.sortCol === col;
      const icon = isSorted ? (s.sortDir === 'asc' ? '↑' : '↓') : '';
      return `<th onclick="App.sortTable('${esc(col)}')">${esc(col)} <span style="color:var(--primary)">${icon}</span></th>`;
    }).join('')}</tr>`;

    tbody.innerHTML = result.rows.map(row =>
      `<tr>${result.columns.map(col => {
        const v = row[col];
        const display = v === null || v === undefined || v === ''
          ? `<span class="null-cell">—</span>`
          : esc(String(v).substring(0, 120));
        return `<td title="${v !== null && v !== undefined ? esc(String(v)) : ''}">${display}</td>`;
      }).join('')}</tr>`
    ).join('');
  },

  renderPagination(page, totalPages, totalRows) {
    const pag = document.getElementById('pagination');
    if (totalPages <= 1) { pag.innerHTML = ''; return; }

    const pages = this.pageRange(page, totalPages);
    pag.innerHTML = [
      `<button class="page-btn" onclick="App.goToPage(${page - 1})" ${page === 1 ? 'disabled' : ''}>‹</button>`,
      ...pages.map(p => p === '...'
        ? `<span class="page-btn" style="pointer-events:none">…</span>`
        : `<button class="page-btn ${p === page ? 'active' : ''}" onclick="App.goToPage(${p})">${p}</button>`
      ),
      `<button class="page-btn" onclick="App.goToPage(${page + 1})" ${page === totalPages ? 'disabled' : ''}>›</button>`,
    ].join('');
  },

  pageRange(current, total) {
    const delta = 2;
    const range = [], rangeWithDots = [];
    for (let i = Math.max(2, current - delta); i <= Math.min(total - 1, current + delta); i++) range.push(i);
    if (current - delta > 2) range.unshift('...');
    if (current + delta < total - 1) range.push('...');
    range.unshift(1);
    if (total !== 1) range.push(total);
    return range;
  },

  renderFilterOptions(columns) {
    const sel = document.getElementById('filterColSelect');
    sel.innerHTML = `<option value="">Filter column…</option>` +
      columns.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
    if (State.tableState.filterCol) sel.value = State.tableState.filterCol;
  },

  bindTableSearch() {
    let timer;
    document.getElementById('tableSearch').addEventListener('input', e => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        State.tableState.search = e.target.value;
        State.tableState.page   = 1;
        if (State.datasetId) this.loadTable();
      }, 350);
    });
  },

  sortTable(col) {
    const s = State.tableState;
    if (s.sortCol === col) {
      s.sortDir = s.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      s.sortCol = col;
      s.sortDir = 'asc';
    }
    s.page = 1;
    this.loadTable();
  },

  goToPage(p) {
    State.tableState.page = p;
    this.loadTable();
  },

  applyTableFilter() {
    State.tableState.filterCol = document.getElementById('filterColSelect').value;
    State.tableState.filterVal = document.getElementById('filterValInput').value;
    State.tableState.page = 1;
    this.loadTable();
  },

  clearTableFilter() {
    State.tableState.filterCol = '';
    State.tableState.filterVal = '';
    document.getElementById('filterColSelect').value = '';
    document.getElementById('filterValInput').value  = '';
    State.tableState.page = 1;
    this.loadTable();
  },

  // ── AI AGENT ────────────────────────────────────────────────────
  bindAgentEnter() {
    document.getElementById('agentInput').addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendAgentCommand();
      }
    });
  },

  setAgentCommand(cmd) {
    document.getElementById('agentInput').value = cmd;
    document.getElementById('agentInput').focus();
  },

  async sendAgentCommand() {
    if (State.agentBusy) return;
    if (!State.datasetId) {
      this.notify('Please upload a dataset first.', 'error');
      return;
    }

    const input = document.getElementById('agentInput');
    const cmd = input.value.trim();
    if (!cmd) return;

    input.value = '';
    State.agentBusy = true;

    const dot = document.getElementById('agentStatusDot');
    dot.classList.add('busy');
    document.getElementById('agentSendBtn').disabled = true;

    // Add user message
    this.appendChatMessage('user', cmd);

    // Add thinking indicator
    const thinkId = this.appendChatMessage('thinking', '');

    try {
      const result = await API.post('/api/agent/run', {
        dataset_id: State.datasetId,
        command:    cmd,
        version_id: this.currentVersionId(),
      });

      this.removeChatMessage(thinkId);

      if (!result.success) {
        this.appendChatMessage('error', result.error || 'Agent failed.');
      } else {
        const r = result.result;
        this.appendAgentResult(r);

        // Refresh state if data was modified
        if (!r.is_read_only && r.new_version_id) {
          await this.refreshVersions();
          this.updateSidebarBadge();
          this.notify(`Version v${r.new_version_number} created.`, 'success');
        }
      }
    } catch (err) {
      this.removeChatMessage(thinkId);
      this.appendChatMessage('error', `Network error: ${err.message}`);
    } finally {
      State.agentBusy = false;
      dot.classList.remove('busy');
      document.getElementById('agentSendBtn').disabled = false;
    }
  },

  appendChatMessage(type, content) {
    const container = document.getElementById('chatMessages');
    const id = 'msg_' + Date.now() + '_' + Math.random().toString(36).slice(2);

    let html = '';
    if (type === 'user') {
      html = `
        <div class="chat-message user" id="${id}">
          <div class="message-avatar user">👤</div>
          <div class="message-bubble">${esc(content)}</div>
        </div>`;
    } else if (type === 'thinking') {
      html = `
        <div class="chat-message system" id="${id}">
          <div class="message-avatar sys"><i data-feather="cpu"></i></div>
          <div class="message-bubble" style="display:flex;align-items:center;gap:10px">
            <div class="progress-spinner" style="width:16px;height:16px;border-width:2px"></div>
            <span style="color:var(--text-muted)">Thinking…</span>
          </div>
        </div>`;
    } else if (type === 'error') {
      html = `
        <div class="chat-message system" id="${id}">
          <div class="message-avatar err"><i data-feather="alert-circle"></i></div>
          <div class="message-bubble" style="border-color:var(--red);color:var(--red)">${esc(content)}</div>
        </div>`;
    } else {
      html = `
        <div class="chat-message system" id="${id}">
          <div class="message-avatar sys"><i data-feather="cpu"></i></div>
          <div class="message-bubble">${content}</div>
        </div>`;
    }

    container.insertAdjacentHTML('beforeend', html);
    feather.replace();
    container.scrollTop = container.scrollHeight;
    return id;
  },

  appendAgentResult(r) {
    const dlHtml = (r.download_excel || r.download_csv) ? `
      <div class="agent-download-row">
        ${r.download_excel ? `<a href="${r.download_excel}" class="btn btn-sm btn-outline-green" download><i data-feather="download"></i> Excel</a>` : ''}
        ${r.download_csv   ? `<a href="${r.download_csv}"   class="btn btn-sm btn-outline-blue"  download><i data-feather="download"></i> CSV</a>` : ''}
      </div>` : '';

    const rowsChanged = r.rows_before !== r.rows_after
      ? `<div class="agent-result-row">
           <span class="key">Rows</span>
           <span class="val ${r.rows_after < r.rows_before ? 'red' : 'green'}">
             ${fmt(r.rows_before)} → ${fmt(r.rows_after)}
           </span>
         </div>` : '';

    const versionHtml = r.new_version_number
      ? `<div class="agent-result-row">
           <span class="key">New Version</span>
           <span class="val green">v${r.new_version_number}</span>
         </div>` : '';

    const content = `
      <div>${esc(r.ai_explanation || r.result_summary)}</div>
      <div class="agent-result-card">
        <div class="agent-result-row">
          <span class="key">Tool Used</span>
          <span class="val" style="color:var(--primary)">${esc(r.tool_used || '—')}</span>
        </div>
        ${rowsChanged}
        ${versionHtml}
      </div>
      ${dlHtml}
    `;
    this.appendChatMessage('system', content);

    // Update last action panel
    const card   = document.getElementById('lastActionCard');
    const detail = document.getElementById('lastActionDetail');
    card.style.display = 'block';
    detail.innerHTML = `
      <div style="font-size:.82rem">
        <div style="margin-bottom:6px"><strong>Tool:</strong> ${esc(r.tool_used)}</div>
        <div style="margin-bottom:6px;color:var(--text-muted)">${esc(r.intent || '')}</div>
        <div style="color:var(--text-muted);font-size:.78rem">${esc(r.result_summary)}</div>
      </div>`;
    feather.replace();
  },

  removeChatMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  },

  async loadTools() {
    try {
      const result = await API.get('/api/agent/tools');
      if (result.success) {
        document.getElementById('toolsList').innerHTML =
          result.tools.map(t => `<span class="tool-tag">${esc(t)}</span>`).join('');
      }
    } catch(e) {}
  },

  // ── AI INSIGHTS ─────────────────────────────────────────────────
  async loadInsights(refresh = false) {
    const vid = this.currentVersionId();
    const params = new URLSearchParams({ refresh: String(refresh) });
    if (vid) params.set('version_id', vid);

    document.getElementById('insightsLoading').style.display = 'flex';
    document.getElementById('insightsContent').style.display = 'none';
    document.getElementById('statsGrid').innerHTML = '';

    try {
      const result = await API.get(`/api/insights/${State.datasetId}?${params}`);
      if (!result.success) { this.notify(result.error, 'error'); return; }

      // Insight text
      document.getElementById('insightsLoading').style.display = 'none';
      document.getElementById('insightsContent').style.display = 'block';
      document.getElementById('insightsText').textContent = result.insight_text || 'No insights available.';

      // Stats
      const stats = result.stats || {};
      this.renderStatsGrid(stats);
      this.renderNumericStats(stats.numeric_summaries || []);
      this.renderCategoricalStats(stats.categorical_summaries || []);
    } catch(err) {
      this.notify('Insights load failed: ' + err.message, 'error');
    }
  },

  refreshInsights() {
    if (State.datasetId) this.loadInsights(true);
  },

  renderStatsGrid(stats) {
    const grid = document.getElementById('statsGrid');
    const items = [
      { label: 'Total Rows',      value: fmt(stats.total_rows || 0),           sub: 'records' },
      { label: 'Total Columns',   value: fmt(stats.total_columns || 0),        sub: 'fields' },
      { label: 'Missing Values',  value: fmt(stats.missing_values_total || 0), sub: 'across all columns', color: stats.missing_values_total > 0 ? 'var(--orange)' : 'var(--green)' },
      { label: 'Duplicate Rows',  value: fmt(stats.duplicate_rows || 0),       sub: 'exact duplicates',   color: stats.duplicate_rows > 0 ? 'var(--red)' : 'var(--green)' },
    ];
    grid.innerHTML = items.map(i => `
      <div class="stat-card">
        <div class="stat-card-label">${i.label}</div>
        <div class="stat-card-value" style="${i.color ? 'color:'+i.color : ''}">${i.value}</div>
        <div class="stat-card-sub">${i.sub}</div>
      </div>`).join('');
  },

  renderNumericStats(summaries) {
    const panel = document.getElementById('numericStatsPanel');
    if (!summaries.length) { panel.innerHTML = '<p style="color:var(--text-dim);font-size:.8rem">No numeric columns.</p>'; return; }
    panel.innerHTML = summaries.map(s => `
      <div class="numeric-stat-item">
        <div class="stat-col-name">${esc(s.column)}</div>
        <div class="stat-row"><span>Total</span><span class="num">${fmtNum(s.total)}</span></div>
        <div class="stat-row"><span>Mean</span><span class="num">${fmtNum(s.mean)}</span></div>
        <div class="stat-row"><span>Min / Max</span><span class="num">${fmtNum(s.min)} / ${fmtNum(s.max)}</span></div>
      </div>`).join('');
  },

  renderCategoricalStats(summaries) {
    const panel = document.getElementById('categoricalStatsPanel');
    if (!summaries.length) { panel.innerHTML = '<p style="color:var(--text-dim);font-size:.8rem">No categorical columns.</p>'; return; }
    panel.innerHTML = summaries.map(s => `
      <div class="cat-stat-item">
        <div class="stat-col-name">${esc(s.column)} <span style="color:var(--text-dim);font-weight:400">(${fmt(s.unique)} unique)</span></div>
        ${Object.entries(s.top_values || {}).slice(0, 3).map(([k, v]) =>
          `<div class="stat-row"><span>${esc(String(k).substring(0, 20))}</span><span class="num">${fmt(v)}</span></div>`
        ).join('')}
      </div>`).join('');
  },

  // ── REPORTS ─────────────────────────────────────────────────────
  async loadReport() {
    const vid = this.currentVersionId();
    const params = vid ? `?version_id=${vid}` : '';
    document.getElementById('reportGrid').innerHTML = `
      <div class="report-loading"><div class="progress-spinner"></div><p>Generating report…</p></div>`;

    try {
      const result = await API.get(`/api/reports/${State.datasetId}${params}`);
      if (!result.success) { this.notify(result.error, 'error'); return; }

      const r = result.report;
      document.getElementById('reportSubtitle').textContent =
        `${r.dataset.name} · ${r.current_version.label}`;

      this.renderReport(r);
    } catch(err) {
      this.notify('Report load failed: ' + err.message, 'error');
    }
  },

  renderReport(r) {
    const grid = document.getElementById('reportGrid');
    const ds   = r.data_summary   || {};
    const cs   = r.cleaning_summary || {};
    const as_  = r.agent_summary  || {};
    const cv   = r.current_version || {};

    grid.innerHTML = `
      <!-- Dataset Info -->
      <div class="report-section">
        <h3><i data-feather="database"></i> Dataset</h3>
        ${rRow('Name', r.dataset.name)}
        ${rRow('File', r.dataset.original_filename)}
        ${rRow('Sheet', r.dataset.sheet_name)}
        ${rRow('Uploaded', fmtDate(r.dataset.created_at))}
        ${rRow('Current Version', `v${cv.version_number} — ${cv.label || ''}`)}
        ${rRow('Version Type', cv.version_type || '')}
        <div style="margin-top:12px;display:flex;gap:8px">
          ${cv.download_excel ? `<a href="${cv.download_excel}" class="btn btn-sm btn-outline-green"><i data-feather="download"></i> Excel</a>` : ''}
          ${cv.download_csv   ? `<a href="${cv.download_csv}"   class="btn btn-sm btn-outline-blue"><i data-feather="download"></i> CSV</a>` : ''}
        </div>
      </div>

      <!-- Data Summary -->
      <div class="report-section">
        <h3><i data-feather="table"></i> Data Summary</h3>
        ${rRow('Total Rows',    fmt(ds.total_rows))}
        ${rRow('Total Columns', fmt(ds.total_columns))}
        ${rRow('Missing Values', fmt(ds.missing_values), ds.missing_values > 0 ? 'orange' : 'green')}
        ${rRow('Duplicates',    fmt(ds.duplicate_rows),  ds.duplicate_rows > 0 ? 'red' : 'green')}
        ${rRow('Numeric Cols',  fmt(ds.numeric_columns))}
        ${rRow('Category Cols', fmt(ds.categorical_columns))}
      </div>

      <!-- Cleaning Summary -->
      <div class="report-section">
        <h3><i data-feather="shield"></i> Cleaning</h3>
        ${rRow('Cleaning Required', cs.cleaning_required ? 'Yes' : 'No', cs.cleaning_required ? 'orange' : 'green')}
        ${rRow('Duplicates Removed', fmt(cs.duplicates_removed), cs.duplicates_removed > 0 ? 'green' : '')}
        ${rRow('Blank Rows Removed', fmt(cs.blank_rows_removed), cs.blank_rows_removed > 0 ? 'green' : '')}
        ${rRow('Empty Cols Removed', fmt(cs.empty_columns_removed))}
        ${rRow('Whitespace Fixed', fmt(cs.whitespace_fixed))}
        ${rRow('Columns Modified', fmt(cs.columns_modified))}
        <div style="margin-top:10px;font-size:.8rem;color:var(--text-muted)">${esc(cs.cleaning_summary || '')}</div>
      </div>

      <!-- AI Agent Summary -->
      <div class="report-section">
        <h3><i data-feather="cpu"></i> AI Agent</h3>
        ${rRow('Total Operations', fmt(as_.total_operations))}
        ${(as_.operations || []).map(op => `
          <div style="font-size:.78rem;color:var(--text-muted);padding:4px 0;border-bottom:1px solid var(--border)">
            <strong style="color:var(--text)">${esc(op.tool)}</strong> — ${esc(op.command?.substring(0,50))}
            <span style="float:right">${fmt(op.rows_before)}→${fmt(op.rows_after)}</span>
          </div>`).join('')}
      </div>

      <!-- KPIs -->
      <div class="report-section">
        <h3><i data-feather="trending-up"></i> KPIs</h3>
        ${(r.kpis || []).map(k =>
          `<div class="report-row"><span class="rkey">${esc(k.label)}</span><span class="rval">${esc(String(k.value))}</span></div>`
        ).join('')}
      </div>

      <!-- AI Insights -->
      <div class="report-section" style="grid-column:1/-1">
        <h3><i data-feather="zap"></i> AI Insights</h3>
        <div style="font-size:.85rem;line-height:1.8;white-space:pre-line;color:var(--text)">${esc(r.insights || 'No insights generated yet.')}</div>
      </div>
    `;
    feather.replace();
  },

  // ── HISTORY ─────────────────────────────────────────────────────
  async loadHistory() {
    try {
      const result = await API.get(`/api/history/${State.datasetId}`);
      if (!result.success) { this.notify(result.error, 'error'); return; }

      const history = result.history || [];
      const empty   = document.getElementById('historyEmpty');
      const timeline = document.getElementById('historyTimeline');

      if (!history.length) {
        empty.style.display = 'flex';
        timeline.innerHTML = '';
        return;
      }
      empty.style.display = 'none';

      timeline.innerHTML = history.map(v => {
        const isCurrent = v.is_current;
        const dotClass  = v.version_type === 'original' ? 'original'
                        : v.version_type === 'auto_cleaned' ? 'cleaned' : 'agent';
        const badgeType = v.version_type === 'original' ? 'original'
                        : v.version_type === 'auto_cleaned' ? 'cleaned' : 'agent';
        const icon      = v.version_type === 'original' ? 'upload-cloud'
                        : v.version_type === 'auto_cleaned' ? 'shield' : 'cpu';
        const delta = v.rows_delta !== 0
          ? `<span style="color:${v.rows_delta < 0 ? 'var(--red)' : 'var(--green)'}">${v.rows_delta > 0 ? '+' : ''}${v.rows_delta} rows</span>`
          : '';

        return `
          <div class="history-item">
            <div class="history-dot ${dotClass} ${isCurrent ? 'current' : ''}">
              <i data-feather="${icon}"></i>
            </div>
            <div class="history-card ${isCurrent ? 'is-current' : ''}">
              <div class="history-card-header">
                <div>
                  <div class="history-version">Version ${v.version_number}</div>
                  <div class="history-label">${esc(v.label || '')}</div>
                </div>
                <div style="display:flex;gap:6px;align-items:center">
                  ${isCurrent ? '<span class="badge current">Current</span>' : ''}
                  <span class="badge ${badgeType}">${badgeType}</span>
                </div>
              </div>
              <div class="history-meta">
                <span><i data-feather="calendar"></i> ${fmtDate(v.created_at)}</span>
                <span><i data-feather="rows"></i> ${fmt(v.rows_after)} rows</span>
                ${v.user_command ? `<span><i data-feather="terminal"></i> "${esc(v.user_command?.substring(0,40))}"</span>` : ''}
                ${delta ? `<span>${delta}</span>` : ''}
              </div>
              ${v.processing_summary ? `<p style="font-size:.8rem;color:var(--text-muted);margin-bottom:10px">${esc(v.processing_summary)}</p>` : ''}
              <div class="history-actions">
                ${v.storage_url_excel ? `<a href="${v.storage_url_excel}" class="btn btn-sm btn-outline-green" download><i data-feather="download"></i> Excel</a>` : ''}
                ${v.storage_url_csv   ? `<a href="${v.storage_url_csv}"   class="btn btn-sm btn-outline-blue"  download><i data-feather="download"></i> CSV</a>` : ''}
                ${!isCurrent ? `<button class="btn btn-sm btn-ghost" onclick="App.revertToVersion('${v.id}')"><i data-feather="rotate-ccw"></i> Revert</button>` : ''}
              </div>
            </div>
          </div>`;
      }).join('');
      feather.replace();
    } catch(err) {
      this.notify('History load failed: ' + err.message, 'error');
    }
  },

  async revertToVersion(versionId) {
    if (!confirm('Revert to this version? The current active version will change.')) return;
    try {
      const result = await API.post('/api/history/revert', {
        dataset_id: State.datasetId,
        version_id: versionId,
      });
      if (result.success) {
        this.notify(result.message, 'success');
        await this.refreshVersions();
        this.updateSidebarBadge();
        this.loadHistory();
      } else {
        this.notify(result.error, 'error');
      }
    } catch(err) {
      this.notify('Revert failed: ' + err.message, 'error');
    }
  },

  // ── Notifications ────────────────────────────────────────────────
  notify(message, type = 'info') {
    const bar  = document.getElementById('notificationBar');
    const text = document.getElementById('notificationText');
    text.textContent = message;
    bar.style.display = 'flex';
    bar.style.background = type === 'error'   ? 'var(--red-soft)'
                         : type === 'success' ? 'var(--green-soft)'
                         : 'var(--blue-soft)';
    bar.style.borderBottomColor = type === 'error'   ? 'var(--red)'
                                : type === 'success' ? 'var(--green)'
                                : 'var(--blue)';
    bar.style.color = type === 'error'   ? 'var(--red)'
                    : type === 'success' ? 'var(--green)'
                    : 'var(--blue)';
    if (type !== 'error') setTimeout(() => { bar.style.display = 'none'; }, 5000);
    feather.replace();
  },

  // ── Loading overlay ──────────────────────────────────────────────
  showLoading(text = 'Processing…') {
    document.getElementById('loadingText').textContent = text;
    document.getElementById('loadingOverlay').style.display = 'flex';
  },
  hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
  },
};

// ═══════════════════════════════════════════════════════════════════
// UTILITY FUNCTIONS
// ═══════════════════════════════════════════════════════════════════

function esc(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function fmt(v) {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  if (isNaN(n)) return String(v);
  return n.toLocaleString();
}

function fmtNum(v) {
  if (v === null || v === undefined) return '—';
  const n = parseFloat(v);
  if (isNaN(n)) return '—';
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(2) + 'M';
  if (Math.abs(n) >= 1_000)     return (n / 1_000).toFixed(1) + 'K';
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch(e) { return iso; }
}

function rRow(label, value, colorClass = '') {
  return `
    <div class="report-row">
      <span class="rkey">${esc(label)}</span>
      <span class="rval ${colorClass}">${esc(String(value ?? '—'))}</span>
    </div>`;
}

// ═══════════════════════════════════════════════════════════════════
// BOOT
// ═══════════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => App.init());
