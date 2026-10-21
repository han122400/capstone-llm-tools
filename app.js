import { classifications } from './data.js';
import { ollamaParameters, modelfileParameterValues, parameterInputValue, replaceModelfileParameter } from './ollama-parameters.js';

const icons = {
  shield: '<path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Z"/><path d="m8 12 3 3 5-6"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  layers: '<path d="m12 3 10 5-10 5L2 8l10-5ZM2 12l10 5 10-5M2 16l10 5 10-5"/>',
  settings: '<path d="m9 3-1 3-3 1-2 3 2 2-1 3 3 2 3-1 2 3 3-1 1-3 3-1 2-3-2-2 1-3-3-2-3 1-2-3Z"/><circle cx="12" cy="11" r="3"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18"/>',
  trend: '<path d="m3 17 6-6 4 4 8-10M15 5h6v6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  alert: '<path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v4M12 17h.01"/>',
  external: '<path d="M14 3h7v7M21 3 11 13M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 15v5h16v-5"/>',
  sparkles: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3ZM20 2v4M18 4h4"/>',
  server: '<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01M11 6.5h6M11 17.5h6"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4M12 17h.01"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  copy: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
  code: '<path d="m8 6-6 6 6 6m8-12 6 6-6 6M14 3l-4 18"/>',
  folder: '<path d="M3 7V4h7l2 3h9v13H3V7Z"/>',
  book: '<path d="M12 5C8 2 3 3 3 3v16s5-1 9 2c4-3 9-2 9-2V3s-5-1-9 2Zm0 0v16"/>',
  menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
  activity: '<path d="M2 12h4l3-8 6 16 3-8h4"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
};
const icon = (name, cls = '') => `<svg class="icon ${cls}" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.file}</svg>`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const STORAGE = 'sentinel-ui-reports-v1';
const PREFS = 'sentinel-ui-preferences-v1';
let reports = [];
try {
  const saved = JSON.parse(localStorage.getItem(STORAGE));
  if (Array.isArray(saved)) {
    reports = saved.filter(r => r && r.id && Array.isArray(r.findings) && (r.classification == null || classifications[r.classification]))
      .filter(r => !(r.demo === true && /^RPT-00[1-8]$/.test(r.id) && r.prompt?.includes('[UI 확인용 가상 예시')))
      .map(r => {
        if (!r.previewNote) return r;
        const { demo, previewNote, ...draft } = r;
        return { ...draft, classification: null, findings: [] };
      });
    if (JSON.stringify(reports) !== JSON.stringify(saved)) localStorage.setItem(STORAGE, JSON.stringify(reports));
  }
} catch { reports = []; }
let preferences;
try { preferences = JSON.parse(localStorage.getItem(PREFS)) || {}; } catch { preferences = {}; }
let page = 'dashboard';
let search = '';
let filter = 'all';
let statusFilter = 'all';
let period = '7';
let editorDraft = { title: '', input_data: '' };
let activeModal = null;
let returnFocus = null;
let toastTimer;
let generating = false;
let generationError = '';
let generation = { phase: 'idle', title: '', message: '', stage: '', thinking: '', statuses: [], contentLength: 0, resultId: null, follow: true, scrollTop: 0 };
let generationFrame = null;
let connection = { model_connected: false, checking: true, model: 'hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q4_K_M-GGUF:Q4_K_M', ollama_url: 'http://127.0.0.1:11434' };
let ollamaSettings = { saved: null, draft: null, loading: false, saving: false, error: '', notice: '', models: { url: null, loading: false, checked: false, available: false, names: [], message: '' }, probe: { loading: false, message: '', connected: false } };
let reportTab = 'report';
const app = document.querySelector('#app');
const overlay = document.querySelector('#overlay-root');
const save = () => { try { localStorage.setItem(STORAGE, JSON.stringify(reports)); } catch { toast('브라우저 저장 공간이 부족합니다. 내보내기로 보고서를 보관해주세요.'); } };
const badge = classification => { const c = classifications[classification] || { label: '분석 대기', className: 'informational' }; return `<span class="badge ${c.className}"><span class="badge-dot"></span>${c.label}</span>`; };
const reportInput = r => r.input_data ?? r.prompt ?? '';
const reportPayload = r => r.classification ? { classification: r.classification, findings: r.findings } : { status: 'draft', title: r.title, target: r.target, input_data: reportInput(r), output: null };
const date = value => new Date(value).toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' }).replace(/\. /g, '.').replace(/\.$/, '');
const countFindings = classification => reports.reduce((n, r) => n + r.findings.filter(f => f.classification === classification).length, 0);
const navItems = [['dashboard', 'grid', '대시보드'], ['create', 'plus', '보고서 작성'], ['reports', 'file', '보고서 목록']];
const connectionLabel = () => connection.checking ? '모델 연결 확인 중…' : connection.model_connected ? 'Ollama 연결됨' : connection.error || (connection.ollama_available ? '지정 모델 미설치' : 'Ollama 미연결');

async function refreshConnection(notify = false) {
  try {
    const response = await fetch('/api/health', { signal: AbortSignal.timeout(8000) });
    if (!response.ok) throw new Error('상태 확인 실패');
    connection = { ...connection, ...await response.json(), checking: false, error: null };
  } catch {
    connection = { ...connection, checking: false, model_connected: false, error: '백엔드 미연결' };
  }
  document.querySelectorAll('[data-connection-status]').forEach(el => { el.textContent = connectionLabel(); });
  document.querySelectorAll('[data-connection-dot]').forEach(el => { el.classList.toggle('gray', !connection.model_connected); });
  updateSettingsUI();
  if (notify) toast(connection.model_connected ? '지정한 로컬 Ollama 모델 연결을 확인했습니다.' : connectionLabel());
}

function toast(message) {
  const el = document.querySelector('#toast');
  el.innerHTML = `${icon('check')}<span>${esc(message)}</span>`;
  el.classList.add('visible');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('visible'), 3500);
}

function render() {
  const titles = { dashboard: '대시보드', create: '보고서 작성', reports: '보고서 목록', settings: 'Ollama 설정' };
  app.innerHTML = `<aside class="sidebar" id="sidebar">
    <a class="brand" href="#dashboard" aria-label="Sentinel 대시보드"><span class="brand-mark">${icon('shield')}</span><span>sentinel<span class="brand-period">.</span></span></a>
    <button class="workspace-switch" data-action="workspace"><span class="workspace-avatar">W</span><span class="workspace-text">보안 워크스페이스<small>Personal workspace</small></span>${icon('down')}</button>
    <div class="nav-label">WORKSPACE</div>
    <nav aria-label="주 메뉴">${navItems.map(([id, glyph, label]) => `<a href="#${id}" class="nav-item ${page === id ? 'active' : ''}" ${page === id ? 'aria-current="page"' : ''}>${icon(glyph)}<span>${label}</span>${id === 'reports' ? `<span class="nav-count">${reports.length}</span>` : ''}${page === id ? '<span class="nav-active-dot"></span>' : ''}</a>`).join('')}</nav>
    <div class="sidebar-divider"></div><div class="nav-label">PREFERENCES</div>
    <a href="#settings" class="nav-item ${page === 'settings' ? 'active' : ''}" ${page === 'settings' ? 'aria-current="page"' : ''}>${icon('settings')}<span>Ollama 설정</span></a>
    <button class="nav-item" data-action="help">${icon('help')}<span>도움말 & 가이드</span>${icon('external', 'small')}</button>
    <div class="sidebar-bottom"><div class="local-card"><div class="local-card-title"><span class="local-symbol">${icon('server')}</span>로컬 AI 워크스페이스</div><p>내 데이터는 내 환경에.<br>Ollama와 함께하는 보안 분석.</p><div class="local-card-foot"><span class="status-dot ${connection.model_connected ? '' : 'gray'}" data-connection-dot></span><span data-connection-status>${connectionLabel()}</span><a href="#settings" aria-label="모델 설정">${icon('arrow')}</a></div></div>
    <button class="profile" data-action="profile"><span class="avatar">${icon('folder', 'small')}</span><span>로컬 워크스페이스<small>이 브라우저에 저장</small></span>${icon('more')}</button></div>
  </aside><div class="sidebar-scrim" data-action="close-menu"></div>
  <div class="main-shell"><header class="topbar"><div class="breadcrumbs"><button class="icon-button mobile-menu" data-action="menu" aria-label="메뉴 열기" aria-expanded="false" aria-controls="sidebar">${icon('menu')}</button><span>워크스페이스</span>${icon('chevron')}<strong>${titles[page]}</strong></div><div class="topbar-actions"><button class="demo-pill" data-action="check-connection"><span class="status-dot ${connection.model_connected ? '' : 'gray'}" data-connection-dot></span><span data-connection-status>${connectionLabel()}</span></button><button class="icon-button notification-button" data-action="notifications" aria-label="알림">${icon('bell')}</button><span class="topbar-divider"></span><button class="avatar small-avatar" data-action="profile" aria-label="워크스페이스 정보">${icon('folder', 'small')}</button></div></header>
  <main id="main-content">${page === 'dashboard' ? dashboard() : page === 'reports' ? reportsPage() : page === 'create' ? createPage() : settingsPage()}</main>
  <footer class="page-footer"><span>© 2026 Sentinel. Built for better security.</span><span><span class="status-dot"></span>로컬 환경에서 안전하게</span></footer></div>`;
  bindPageEvents();
  updateGenerationUI(true);
}

function heading(eyebrow, title, subtitle, actions = '') {
  return `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${subtitle}</p></div><div class="heading-actions">${actions}</div></div>`;
}

function dashboard() {
  const completed = reports.filter(r => r.status === '완료').length;
  const confirmed = countFindings('CONFIRMED');
  const pending = countFindings('SUSPECTED') + countFindings('ATTACK_SURFACE');
  const stats = [
    ['전체 보고서', reports.length, 'file', '워크스페이스에 저장된 보고서', 'green'],
    ['확인된 취약점', confirmed, 'shield', '근거와 함께 확인된 항목', 'rose'],
    ['추가 검증 필요', pending, 'alert', '의심 항목 및 공격 표면', 'amber'],
    ['보고서 완료율', reports.length ? Math.round(completed / reports.length * 100) + '<span class="metric-unit">%</span>' : '0<span class="metric-unit">%</span>', 'check', `${completed}개 보고서 작성 완료`, 'green'],
  ];
  return `${heading('SECURITY OVERVIEW', '보안 현황을 한눈에', '취약점 분석부터 보고서 작성까지, 더 명확하고 체계적으로.', `<button class="button secondary" data-action="export-all">${icon('download')}내보내기</button><a href="#create" class="button primary">${icon('plus')}새 보고서</a>`)}
    ${generationPanel()}
    <div class="overview-toolbar"><span class="section-eyebrow"><span class="status-dot"></span>워크스페이스 개요</span><label class="period-select">${icon('calendar')}<select id="period-select" aria-label="분석 현황 기간"><option value="7" ${period === '7' ? 'selected' : ''}>최근 7일</option><option value="30" ${period === '30' ? 'selected' : ''}>최근 30일</option></select>${icon('down')}</label></div>
    <section class="metric-grid" aria-label="보안 현황 요약">${stats.map(([title, number, glyph, foot, color]) => `<article class="metric-card"><div class="metric-top"><span>${title}</span><span class="metric-icon ${color}">${icon(glyph)}</span></div><div class="metric-number">${number}</div><div class="metric-bottom"><span class="metric-line ${color}"></span>${foot}</div></article>`).join('')}</section>
    <section class="chart-grid"><article class="panel trend-panel"><div class="panel-heading"><div><h2>보고서 생성 현황</h2><p>분석 기록의 흐름을 확인하세요.</p></div><span class="chart-legend"><span></span>생성된 보고서</span></div>${trendChart()}<div class="chart-footer">${icon('trend')}<span>이번 기간 <strong>${reportsInPeriod().length}개</strong>의 보고서가 생성되었습니다.</span></div></article>
    <article class="panel distribution-panel"><div class="panel-heading"><div><h2>판정별 분석 결과</h2><p>근거에 따른 항목 분류</p></div><span class="soft-icon">${icon('shield')}</span></div>${distributionChart()}</article></section>
    <section class="panel recent-panel"><div class="panel-heading"><div class="title-with-count"><h2>최근 보고서</h2><span class="count-chip">${reports.length}</span></div><a href="#reports" class="text-link">전체 보기${icon('arrow')}</a></div>${reportTable(reports.slice(0, 4))}</section>
    <section class="bottom-callout"><div class="callout-icon">${icon('sparkles')}</div><div><h3>분석할 데이터를 한 번에 넣어주세요.</h3><p>로컬 모델이 입력 근거를 읽고 일관된 형식으로 정리합니다.</p></div><a href="#create" class="button light">보고서 작성${icon('arrow')}</a><div class="callout-decoration" aria-hidden="true"></div></section>`;
}

function reportsInPeriod() {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - Number(period) + 1);
  return reports.filter(r => new Date(r.createdAt) >= start && new Date(r.createdAt) <= now);
}

function trendChart() {
  if (!reportsInPeriod().length) return '<div class="chart-empty"><span class="soft-icon">'+icon('activity')+'</span><strong>아직 생성된 보고서가 없습니다.</strong><span>보고서를 작성하면 생성 현황이 표시됩니다.</span></div>';
  const now = new Date();
  const days = Number(period) === 7 ? 7 : 10;
  const step = Number(period) === 7 ? 1 : 3;
  const buckets = Array.from({ length: days }, (_, i) => {
    const end = new Date(now.getFullYear(), now.getMonth(), now.getDate() - (days - 1 - i) * step + 1);
    const start = new Date(end); start.setDate(start.getDate() - step);
    return { label: `${start.getMonth() + 1}.${String(start.getDate()).padStart(2, '0')}`, n: reports.filter(r => new Date(r.createdAt) >= start && new Date(r.createdAt) < end).length };
  });
  const max = Math.max(4, ...buckets.map(b => b.n));
  const points = buckets.map((b, i) => [46 + i * 592 / (days - 1), 176 - b.n / max * 136]);
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${p.join(',')}`).join(' ');
  return `<div class="trend-chart"><svg viewBox="0 0 680 220" role="img" aria-label="${esc(buckets.map(b => `${b.label}: ${b.n}개`).join(', '))}"><defs><linearGradient id="chart-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#468771" stop-opacity=".19"/><stop offset="100%" stop-color="#468771" stop-opacity=".01"/></linearGradient></defs>${[0, 1, 2, 3, 4].map(i => `<line x1="46" y1="${176 - i * 34}" x2="640" y2="${176 - i * 34}" stroke="#eef0ed" stroke-dasharray="3 5"/><text x="22" y="${181 - i * 34}" class="axis-label">${Math.round(i * max / 4)}</text>`).join('')}<path d="${line} L638,176 L46,176 Z" fill="url(#chart-fill)"/><path d="${line}" stroke="#35755e" fill="none" stroke-width="2.6" stroke-linejoin="round"/>${points.map((p, i) => `<circle cx="${p[0]}" cy="${p[1]}" r="4" stroke="#35755e" stroke-width="2" fill="#fff"><title>${buckets[i].label}: ${buckets[i].n}개 보고서</title></circle><text x="${p[0]}" y="207" text-anchor="middle" class="axis-label">${buckets[i].label}</text>`).join('')}</svg></div>`;
}

function distributionChart() {
  const keys = ['CONFIRMED', 'SUSPECTED', 'ATTACK_SURFACE', 'INFORMATIONAL'];
  const total = reports.reduce((n, r) => n + r.findings.length, 0);
  const colors = ['#3e735c', '#d2a660', '#90aba0', '#cbd4ce'];
  let offset = 0;
  const segments = keys.map((key, i) => {
    const n = countFindings(key), pct = total ? n / total * 100 : 0;
    const result = `<circle cx="90" cy="90" r="68" fill="none" stroke="${colors[i]}" stroke-width="17" stroke-dasharray="${pct} ${100 - pct}" stroke-dashoffset="${-offset}" pathLength="100" transform="rotate(-90 90 90)"/>`;
    offset += pct; return result;
  }).join('');
  return `<div class="distribution-content"><div class="donut"><svg viewBox="0 0 180 180" role="img" aria-label="전체 ${total}개 분석 항목"><circle cx="90" cy="90" r="68" fill="none" stroke="#edf1ed" stroke-width="17"/>${segments}</svg><div class="donut-label"><strong>${total}</strong><span>전체 분석 항목</span></div></div><div class="distribution-legend">${keys.map((key, i) => `<div><span class="legend-dot" style="background:${colors[i]}"></span><span>${classifications[key].label}</span><strong>${countFindings(key)}</strong><small>${total ? Math.round(countFindings(key) / total * 100) : 0}%</small></div>`).join('')}</div></div><div class="distribution-foot">${icon('help')}판정은 위험도 점수와 별도로 구분됩니다.</div>`;
}

function reportTable(list) {
  if (!list.length) return `<div class="empty-state">${icon('folder')}<h3>표시할 보고서가 없습니다.</h3><p>검색 조건을 바꾸거나 새 보고서를 작성해보세요.</p><a href="#create" class="button secondary">${icon('plus')}보고서 작성</a></div>`;
  return `<div class="table-scroll"><table><thead><tr><th>보고서 이름</th><th>분석 대상</th><th>판정</th><th>항목 수</th><th>생성일</th><th>상태</th><th><span class="sr-only">보고서 열기</span></th></tr></thead><tbody>${list.map(r => `<tr data-report="${esc(r.id)}"><td><button class="report-name" data-action="open-report" data-id="${esc(r.id)}"><span class="file-tile">${icon('file')}</span><span>${esc(r.title)}<small>${esc(r.id)}</small></span></button></td><td class="target-cell">${esc(r.target || '미제공')}</td><td>${badge(r.classification)}</td><td class="numeric-cell">${r.findings.length}<span>개</span></td><td class="date-cell">${date(r.createdAt)}</td><td><span class="report-status ${r.status === '완료' ? 'done' : 'draft'}">${icon(r.status === '완료' ? 'check' : 'clock')}${r.status}</span></td><td><button class="icon-button row-open" data-action="open-report" data-id="${esc(r.id)}" aria-label="${esc(r.title)} 상세 보기">${icon('chevron')}</button></td></tr>`).join('')}</tbody></table></div>`;
}

function filteredReports() {
  const term = search.toLowerCase();
  return reports.filter(r => (filter === 'all' || r.classification === filter) && (statusFilter === 'all' || r.status === statusFilter) && `${r.title} ${r.target} ${r.id}`.toLowerCase().includes(term));
}

function reportsPage() {
  return `${heading('REPORT LIBRARY', '나의 보안 보고서', '분석 기록을 한곳에 모으고, 필요한 보고서를 빠르게 찾아보세요.', `<button class="button secondary" data-action="export-all">${icon('download')}전체 내보내기</button><a href="#create" class="button primary">${icon('plus')}새 보고서</a>`)}<section class="panel library-panel"><div class="library-toolbar"><div class="filter-tabs" role="group" aria-label="보고서 상태 필터">${[['all', '전체'], ['완료', '완료'], ['초안', '초안']].map(([value, label]) => `<button class="filter-tab ${statusFilter === value ? 'active' : ''}" data-action="filter-status" data-value="${value}" aria-pressed="${statusFilter === value}">${label}<span>${value === 'all' ? reports.length : reports.filter(r => r.status === value).length}</span></button>`).join('')}</div><div class="library-search-controls"><label class="search-input">${icon('search')}<input id="report-search" type="search" value="${esc(search)}" placeholder="보고서 이름, 대상 검색" aria-label="보고서 검색" /></label><select id="classification-filter" class="form-select compact" aria-label="판정 필터"><option value="all">모든 판정</option>${Object.entries(classifications).map(([key, c]) => `<option value="${key}" ${filter === key ? 'selected' : ''}>${c.label}</option>`).join('')}</select></div></div><div id="report-results">${reportTable(filteredReports())}</div><div class="table-footer"><span id="results-count">${filteredReports().length}개 보고서</span><span>이 브라우저에 저장됩니다.</span></div></section><div class="info-strip">${icon('help')}보고서는 이 브라우저에 저장되며, 로컬 Ollama의 실제 응답을 사용합니다.</div>`;
}

function createPage() {
  return `${heading('REPORT STUDIO', '데이터를 넣고, 보고서를 만드세요', '점검 내용을 한 번에 붙여넣으면 정형화된 보고서로 정리합니다.')}
    ${generationPanel()}
    <section class="panel editor-panel simple-editor"><form id="report-form"><div class="field"><label for="report-title">제목 <span>*</span></label><input id="report-title" name="title" class="form-input" placeholder="보고서 제목을 입력하세요" value="${esc(editorDraft.title)}" required maxlength="100" /></div><div class="field prompt-field"><label for="report-input-data">입력 데이터 <span>*</span></label><textarea id="report-input-data" name="input_data" required maxlength="20000" placeholder="분석할 내용을 한 번에 붙여넣으세요.

HTTP 요청·응답, HTML, 코드, 로그 등 원본 데이터를 입력할 수 있습니다.">${esc(editorDraft.input_data)}</textarea><div class="textarea-footer"><span>입력 데이터는 로컬 Ollama에서 처리됩니다.</span><span id="character-count">${editorDraft.input_data.length.toLocaleString()} / 20,000</span></div></div><div class="form-demo-note">${icon('help')}설정된 시스템 프롬프트로 분석합니다. 초기 모델 로딩에는 시간이 걸릴 수 있습니다.</div><div class="generation-error" role="alert" ${generationError ? '' : 'hidden'}>${esc(generationError)}</div><button type="submit" class="button primary generate-button" ${generating ? 'disabled' : ''}>${icon('sparkles')}${generating ? '모델 분석 중…' : '보고서 생성'}${icon('arrow')}</button></form></section>`;
}

function settingsPage() {
  return `${heading('LOCAL MODEL', 'Ollama 설정', '연결할 로컬 모델과 Modelfile을 설정하세요. 저장한 설정은 다음 보고서에 적용됩니다.')}
    <div class="settings-grid ollama-settings-grid"><section class="panel settings-panel ollama-settings-panel"><div class="panel-heading"><div><h2>연결과 실행 설정</h2><p>설정은 프로젝트에 저장됩니다.</p></div><span class="settings-state" data-settings-state role="status" aria-live="polite">설정 읽는 중…</span></div>
    <form id="settings-form" novalidate><div class="settings-runtime-fields"><div class="field"><label for="ollama-url">Ollama 서버 주소</label><input id="ollama-url" name="ollama_url" type="url" class="form-input model-field" placeholder="http://127.0.0.1:11434" required aria-describedby="ollama-url-help" /><small id="ollama-url-help">localhost 또는 127.0.0.1 등 이 컴퓨터의 주소를 사용하세요.</small></div><div class="field"><label for="ollama-keep-alive">모델 메모리 유지 시간</label><select id="ollama-keep-alive" name="keep_alive" class="form-select"><option value="0">응답 후 바로 해제</option><option value="1m">1분</option><option value="5m">5분</option><option value="15m">15분</option><option value="1h">1시간</option></select><small>응답이 끝난 뒤 모델을 메모리에 유지하는 시간입니다.</small></div></div>
    <div class="field"><label for="ollama-model">설치된 모델</label><div class="settings-model-controls"><select id="ollama-model" class="form-select model-field" aria-describedby="ollama-model-help"></select><button class="button secondary" type="button" data-action="refresh-ollama-models">${icon('layers')}목록 새로고침</button><button class="button secondary" type="button" data-action="probe-ollama">${icon('server')}연결 확인</button></div><small id="ollama-model-help">선택하면 Modelfile의 FROM 줄이 변경됩니다. 설치된 모델만 목록에 표시됩니다.</small></div>
    <div class="settings-feedback" data-model-feedback role="status" aria-live="polite" hidden></div><div class="settings-feedback" data-probe-feedback role="status" aria-live="polite" hidden></div>
    ${ollamaParameterControls()}
    <div class="field modelfile-field"><div class="label-row"><label for="ollama-modelfile">Modelfile</label><span class="settings-file-label">프로젝트 파일</span></div><textarea id="ollama-modelfile" name="modelfile" class="modelfile-editor" spellcheck="false" autocapitalize="off" autocomplete="off" rows="17" aria-describedby="modelfile-help" required></textarea><div class="textarea-footer"><span>FROM · SYSTEM · PARAMETER</span><span data-modelfile-length></span></div><small id="modelfile-help">FROM에 모델 이름, SYSTEM에 시스템 프롬프트, PARAMETER에 생성 옵션을 입력하세요. 여러 줄 프롬프트는 삼중 따옴표(&quot;&quot;&quot;)로 감쌉니다.</small></div>
    <div class="settings-syntax-note"><span>${icon('help')}</span><p><code>stop</code>은 이 편집기에서만 설정합니다. 종료 문구를 잘못 지정하면 JSON 보고서가 중간에 끊길 수 있습니다.<br>저장한 변경 사항은 서버 재시작 없이 다음 생성부터 적용됩니다.</p></div>
    <div class="settings-error" data-settings-error role="alert" hidden></div><div class="settings-feedback success" data-settings-notice role="status" aria-live="polite" hidden></div><div class="settings-generation-note" data-settings-generation hidden>${icon('clock')}보고서 생성 중에는 저장과 연결 확인이 잠시 대기합니다. 수정한 내용은 유지됩니다.</div>
    <div class="settings-save-row"><span class="settings-save-hint" data-settings-save-hint></span><div class="settings-actions"><button class="button secondary" type="button" data-action="revert-ollama-settings">되돌리기</button><button class="button primary" type="submit">${icon('check')}설정 저장</button></div></div></form></section>
    <aside class="settings-aside"><section class="panel saved-settings-card"><div class="saved-settings-heading"><span class="metric-icon green">${icon('server')}</span><div><h2>저장된 실행 설정</h2><p>다음 보고서에 적용되는 값입니다.</p></div></div><div data-saved-settings-summary></div></section>
    <section class="panel storage-card"><h2>보고서 보관</h2><p>보고서와 내보내기 형식은 현재 브라우저에 저장됩니다.</p><div class="storage-stat"><span>저장된 보고서</span><strong>${reports.length}개</strong></div><div class="field"><label for="output-format">기본 내보내기 형식</label><select id="output-format" class="form-select"><option value="json" ${preferences.format !== 'md' ? 'selected' : ''}>JSON · 구조화된 데이터</option><option value="md" ${preferences.format === 'md' ? 'selected' : ''}>Markdown · 읽기 쉬운 보고서</option></select><small>선택한 형식은 이 브라우저에 바로 저장됩니다.</small></div><button class="button secondary" data-action="export-all">${icon('download')}모든 보고서 내보내기</button></section></aside></div>`;
}

function ollamaParameterField(name) {
  const spec = ollamaParameters[name];
  const seed = name === 'seed';
  return `<div class="parameter-field field"><div class="label-row"><label for="ollama-${name}">${spec.label} <code>${name}</code></label>${seed ? '<label class="seed-toggle" for="ollama-seed-fixed"><input type="checkbox" id="ollama-seed-fixed" />고정 사용</label>' : ''}</div><div class="parameter-input-row"><input id="ollama-${name}" data-ollama-parameter="${name}" class="form-input" type="number" min="${spec.min}" max="${spec.max}" step="${spec.step}" ${spec.optional ? '' : 'required'} placeholder="${seed ? '고정할 숫자' : spec.optional ? '모델 기본값' : spec.initial}" aria-describedby="${name}-description ${name}-guide" />${spec.unit ? `<span class="parameter-unit">${spec.unit}</span>` : ''}</div><p class="parameter-description" id="${name}-description">${spec.description}</p><div class="parameter-range"><span>최소 <strong>${spec.min.toLocaleString('ko-KR')}</strong></span><span>최대 <strong>${spec.max.toLocaleString('ko-KR')}</strong></span><span>시작값 <strong>${spec.recommended}</strong></span></div><small id="${name}-guide">${spec.guide}</small></div>`;
}

function ollamaParameterControls() {
  return `<section class="parameter-section" aria-labelledby="basic-parameters-heading"><div class="parameter-section-heading"><div><h3 id="basic-parameters-heading">기본 설정</h3><p>정형 보고서 생성을 위한 시작값입니다.</p></div><span class="parameter-sync-label">Modelfile과 자동 연동</span></div><div class="parameter-grid basic-parameter-grid">${['temperature', 'num_ctx', 'num_predict'].map(ollamaParameterField).join('')}</div><p class="parameter-limits-note">최소·최대는 앱의 입력 허용 범위입니다. 실제 모델의 지원 범위와 메모리에 맞춰 조절하세요.</p></section><details class="advanced-parameters" id="ollama-advanced" ${ollamaSettings.advancedOpen ? 'open' : ''}><summary><span>${icon('settings')}고급 설정<small>후보 범위 · 반복 · 시드</small></span>${icon('down')}</summary><div class="advanced-parameter-content"><div class="parameter-grid">${['top_p', 'repeat_penalty', 'seed', 'top_k'].map(ollamaParameterField).join('')}</div><a class="parameter-docs-link" href="https://docs.ollama.com/modelfile#valid-parameters-and-values" target="_blank" rel="noopener noreferrer">파라미터 공식 설명${icon('external')}</a></div></details>`;
}

// Locate only a command outside a multiline SYSTEM prompt; keep all other bytes intact.
function modelfileFromRange(text) {
  let multiline = false;
  for (const match of text.matchAll(/([^\r\n]*)(\r\n|\n|\r|$)/g)) {
    const line = match[1];
    if (multiline) { if (line.includes('"""')) multiline = false; continue; }
    const from = line.match(/^(\s*FROM\s+)("(?:[^"\\]|\\.)*"|\S+)(.*)$/i);
    if (from) {
      let model = from[2];
      const quoted = model.startsWith('"') && model.endsWith('"');
      if (quoted) { try { model = JSON.parse(model); } catch { /* Keep invalid text visible until the server validates it. */ } }
      return { model, quoted, start: match.index + from[1].length, end: match.index + from[1].length + from[2].length };
    }
    const system = line.match(/^\s*SYSTEM\s+(.*)$/i)?.[1];
    if (system?.startsWith('"""') && !system.slice(3).includes('"""')) multiline = true;
  }
  return null;
}

function modelFromModelfile(text) { return modelfileFromRange(text)?.model || ''; }

function replaceModelfileModel(text, model) {
  const from = modelfileFromRange(text);
  if (from) return text.slice(0, from.start) + (from.quoted ? JSON.stringify(model) : model) + text.slice(from.end);
  const newline = text.match(/\r\n|\n|\r/)?.[0] || '\n';
  return `FROM ${model}${newline}${text}`;
}

function draftFromSettings(settings) {
  return { ollama_url: settings.ollama_url, modelfile: settings.modelfile, keep_alive: String(settings.keep_alive), revision: settings.revision };
}

function ollamaSettingsDirty() {
  const { saved, draft } = ollamaSettings;
  return Boolean(saved && draft && (draft.ollama_url !== saved.ollama_url || draft.modelfile !== saved.modelfile || draft.keep_alive !== String(saved.keep_alive)));
}

function setOllamaDraft(field, value) {
  if (!ollamaSettings.draft) return;
  // A textarea normalizes line breaks; preserve an existing CRLF file when editing it.
  if (field === 'modelfile' && /\r\n/.test(ollamaSettings.draft.modelfile) && !/(?<!\r)\n/.test(ollamaSettings.draft.modelfile)) value = value.replace(/\r\n|\r|\n/g, '\r\n');
  ollamaSettings.draft[field] = value;
  ollamaSettings.error = ''; ollamaSettings.notice = '';
  if (field === 'ollama_url' || field === 'modelfile') ollamaSettings.probe = { ...ollamaSettings.probe, message: '', connected: false };
  if (field === 'modelfile') syncParameterInputs();
  updateSettingsUI();
}

function syncParameterInputs(force = false) {
  if (!ollamaSettings.draft) return;
  const values = modelfileParameterValues(ollamaSettings.draft.modelfile);
  const seedToggle = document.querySelector('#ollama-seed-fixed');
  if (seedToggle) seedToggle.checked = Object.hasOwn(values, 'seed');
  for (const name of Object.keys(ollamaParameters)) {
    const input = document.querySelector(`#ollama-${name}`);
    if (!input) continue;
    const raw = values[name];
    const value = parameterInputValue(name, raw);
    if (force || document.activeElement !== input) input.value = value;
    input.setCustomValidity(raw != null && !value ? `${name}에 유효한 숫자를 입력해주세요. Modelfile의 PARAMETER 값을 확인하세요.` : '');
    if (name === 'seed') input.required = Object.hasOwn(values, 'seed');
  }
}

function setOllamaParameter(name, value) {
  if (!ollamaSettings.draft) return;
  setOllamaDraft('modelfile', replaceModelfileParameter(ollamaSettings.draft.modelfile, name, value));
  const editor = document.querySelector('#ollama-modelfile');
  if (editor) editor.value = ollamaSettings.draft.modelfile;
}

async function settingsResponse(response) {
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `설정 요청에 실패했습니다. (HTTP ${response.status})`);
  if (!data) throw new Error('서버의 설정 응답을 읽을 수 없습니다.');
  return data;
}

function settingsErrorMessage(error) {
  return error.name === 'TimeoutError' ? '서버 응답 시간이 초과되었습니다. 수정한 내용은 유지됩니다.' : error instanceof TypeError ? '백엔드에 연결할 수 없습니다. FastAPI 실행 상태를 확인해주세요. 수정한 내용은 유지됩니다.' : error.message;
}

async function loadOllamaSettings(revert = false) {
  if (ollamaSettings.loading || ollamaSettings.saving || (ollamaSettings.saved && !revert)) return;
  ollamaSettings.loading = true; ollamaSettings.error = ''; ollamaSettings.notice = '';
  updateSettingsUI();
  try {
    const data = await settingsResponse(await fetch('/api/settings/ollama', { signal: AbortSignal.timeout(10000) }));
    if (typeof data.modelfile !== 'string' || typeof data.ollama_url !== 'string' || data.revision == null) throw new Error('서버의 설정 응답 형식을 확인할 수 없습니다.');
    ollamaSettings.saved = data;
    if (!ollamaSettings.draft || revert) ollamaSettings.draft = draftFromSettings(data);
    if (revert) { ollamaSettings.notice = '저장된 설정으로 되돌렸습니다.'; ollamaSettings.probe = { loading: false, message: '', connected: false }; }
    hydrateSettingsInputs();
  } catch (error) { ollamaSettings.error = settingsErrorMessage(error); }
  finally { ollamaSettings.loading = false; updateSettingsUI(); }
  if (ollamaSettings.saved && (!ollamaSettings.models.checked || ollamaSettings.models.url !== ollamaSettings.draft.ollama_url.trim())) refreshOllamaModels();
}

function hydrateSettingsInputs() {
  const draft = ollamaSettings.draft;
  if (!draft) return;
  for (const [id, value] of [['ollama-url', draft.ollama_url], ['ollama-modelfile', draft.modelfile], ['ollama-keep-alive', draft.keep_alive]]) {
    const input = document.querySelector(`#${id}`);
    if (!input) continue;
    if (id === 'ollama-keep-alive' && ![...input.options].some(option => option.value === value)) {
      const option = document.createElement('option'); option.value = value; option.textContent = `${value} · 저장된 값`; input.append(option);
    }
    input.value = value;
  }
  syncParameterInputs(true);
}

function ollamaModelOptions() {
  const draftModel = modelFromModelfile(ollamaSettings.draft?.modelfile || '');
  const list = ollamaSettings.models;
  const matches = list.url === ollamaSettings.draft?.ollama_url.trim() && list.checked;
  const names = matches ? list.names : [];
  const configuredLabel = matches && list.available ? '미설치' : '설치 여부 미확인';
  return { model: draftModel, entries: [
    ...(!draftModel ? [{ value: '', label: 'Modelfile에 FROM 모델을 입력하세요.' }] : !names.includes(draftModel) ? [{ value: draftModel, label: `${draftModel} · ${configuredLabel}` }] : []),
    ...names.map(name => ({ value: name, label: name })),
  ] };
}

function updateOllamaModelSelect() {
  const select = document.querySelector('#ollama-model');
  if (!select) return;
  const { model, entries } = ollamaModelOptions();
  const signature = JSON.stringify(entries);
  if (select.dataset.options !== signature) {
    select.replaceChildren(...entries.map(entry => {
      const option = document.createElement('option'); option.value = entry.value; option.textContent = entry.label; return option;
    }));
    select.dataset.options = signature;
  }
  select.value = model;
}

function savedOllamaSummary() {
  const saved = ollamaSettings.saved;
  if (!saved) return '<p class="saved-settings-empty">저장된 설정을 읽으면 적용 값이 표시됩니다.</p>';
  const options = Object.entries(saved.options || {});
  return `<dl class="saved-settings-meta"><div><dt>모델</dt><dd class="model-field">${esc(saved.model)}</dd></div><div><dt>메모리 유지</dt><dd>${esc(saved.keep_alive === 0 || saved.keep_alive === '0' ? '응답 후 바로 해제' : saved.keep_alive)}</dd></div>${saved.generation_timeout_seconds ? `<div><dt>생성 제한 시간</dt><dd>${esc(saved.generation_timeout_seconds)}초</dd></div>` : ''}</dl><div class="saved-parameters-heading">PARAMETER</div>${options.length ? `<dl class="saved-parameters">${options.map(([key, value]) => `<div><dt>${esc(key)}</dt><dd>${esc(Array.isArray(value) ? JSON.stringify(value) : value)}</dd></div>`).join('')}</dl>` : '<p class="saved-settings-empty">지정된 PARAMETER가 없습니다. 모델 기본값을 사용합니다.</p>'}<p class="saved-settings-footnote">SYSTEM 프롬프트는 저장된 Modelfile을 사용합니다.</p>`;
}

function updateSettingsUI() {
  const form = document.querySelector('#settings-form');
  if (!form) return;
  const state = ollamaSettings;
  const ready = Boolean(state.draft);
  const dirty = ollamaSettingsDirty();
  const busy = state.loading || state.saving;
  const blocked = busy || generating || state.models.loading || state.probe.loading;
  form.querySelectorAll('input, textarea, select').forEach(input => { input.disabled = !ready || busy; });
  const seedInput = form.querySelector('#ollama-seed');
  if (seedInput) seedInput.disabled = !ready || busy || !form.querySelector('#ollama-seed-fixed').checked;
  const saveButton = form.querySelector('[type="submit"]');
  saveButton.disabled = !ready || !dirty || blocked;
  saveButton.innerHTML = state.saving ? '<span class="spinner"></span>저장 중…' : `${icon('check')}설정 저장`;
  const revertButton = form.querySelector('[data-action="revert-ollama-settings"]');
  revertButton.disabled = blocked || (!state.error && !dirty);
  revertButton.textContent = !state.saved && state.error ? '다시 불러오기' : '되돌리기';
  const modelButton = form.querySelector('[data-action="refresh-ollama-models"]');
  modelButton.disabled = !ready || blocked;
  modelButton.innerHTML = `${icon('layers')}${state.models.loading ? '목록 확인 중…' : '목록 새로고침'}`;
  const probeButton = form.querySelector('[data-action="probe-ollama"]');
  probeButton.disabled = !ready || !modelFromModelfile(state.draft?.modelfile || '') || blocked;
  probeButton.innerHTML = `${icon('server')}${state.probe.loading ? '확인 중…' : '연결 확인'}`;
  const status = document.querySelector('[data-settings-state]');
  status.textContent = state.loading ? '설정 읽는 중…' : state.saving ? '저장 중…' : dirty ? '저장하지 않은 변경' : ready ? '저장된 설정' : '설정 불러오기 실패';
  status.classList.toggle('dirty', dirty); status.classList.toggle('failed', !ready && !state.loading);
  const setFeedback = (selector, text) => { const node = form.querySelector(selector); node.textContent = text; node.hidden = !text; };
  setFeedback('[data-settings-error]', state.error);
  setFeedback('[data-settings-notice]', state.notice);
  setFeedback('[data-model-feedback]', state.models.url === state.draft?.ollama_url.trim() ? state.models.message : '');
  setFeedback('[data-probe-feedback]', state.probe.message);
  form.querySelector('[data-probe-feedback]').classList.toggle('success', state.probe.connected);
  form.querySelector('[data-settings-generation]').hidden = !generating;
  form.querySelector('[data-settings-save-hint]').textContent = dirty ? '수정한 내용은 저장 후 적용됩니다.' : ready ? '저장한 설정으로 보고서를 생성합니다.' : '백엔드에서 설정을 읽고 있습니다.';
  form.querySelector('[data-modelfile-length]').textContent = ready ? `${state.draft.modelfile.length.toLocaleString()}자` : '';
  updateOllamaModelSelect();
  const summary = document.querySelector('[data-saved-settings-summary]');
  const summaryMarkup = savedOllamaSummary();
  if (summary.innerHTML !== summaryMarkup) summary.innerHTML = summaryMarkup;
}

async function refreshOllamaModels() {
  if (!ollamaSettings.draft || generating || ollamaSettings.loading || ollamaSettings.saving || ollamaSettings.models.loading || ollamaSettings.probe.loading) return;
  const url = ollamaSettings.draft.ollama_url.trim();
  const list = { url, loading: true, checked: false, available: false, names: [], message: '' };
  ollamaSettings.models = list; updateSettingsUI();
  try {
    const data = await settingsResponse(await fetch(`/api/ollama/models?ollama_url=${encodeURIComponent(url)}`, { signal: AbortSignal.timeout(15000) }));
    list.available = data.ollama_available === true;
    list.names = [...new Set((data.models || []).map(model => model.name).filter(name => typeof name === 'string' && name))];
    list.checked = true;
    list.message = typeof data.message === 'string' && data.message ? data.message : list.available ? `설치된 모델 ${list.names.length}개를 확인했습니다.` : 'Ollama에 연결할 수 없어 설치된 모델을 확인하지 못했습니다.';
  } catch (error) { list.message = settingsErrorMessage(error); }
  finally { list.loading = false; updateSettingsUI(); }
}

async function probeOllamaDraft() {
  if (!ollamaSettings.draft || generating || ollamaSettings.loading || ollamaSettings.saving || ollamaSettings.models.loading || ollamaSettings.probe.loading) return;
  const url = ollamaSettings.draft.ollama_url.trim();
  const model = modelFromModelfile(ollamaSettings.draft.modelfile);
  if (!model) { ollamaSettings.error = 'Modelfile에 FROM 모델을 입력해주세요.'; updateSettingsUI(); return; }
  ollamaSettings.probe = { loading: true, message: '', connected: false }; updateSettingsUI();
  try {
    const data = await settingsResponse(await fetch('/api/ollama/check', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ollama_url: url, model }), signal: AbortSignal.timeout(15000) }));
    if (ollamaSettings.draft.ollama_url.trim() === url && modelFromModelfile(ollamaSettings.draft.modelfile) === model) {
      ollamaSettings.probe.connected = data.model_connected === true;
      ollamaSettings.probe.message = `현재 입력값 확인: ${data.message || (data.model_connected ? '모델에 연결할 수 있습니다.' : '지정한 모델에 연결할 수 없습니다.')}`;
    }
  } catch (error) {
    if (ollamaSettings.draft.ollama_url.trim() === url && modelFromModelfile(ollamaSettings.draft.modelfile) === model) ollamaSettings.probe.message = settingsErrorMessage(error);
  } finally { ollamaSettings.probe.loading = false; updateSettingsUI(); }
}

async function saveOllamaSettings(event) {
  event.preventDefault();
  if (!ollamaSettings.draft || !ollamaSettingsDirty() || ollamaSettings.saving || ollamaSettings.loading || ollamaSettings.models.loading || ollamaSettings.probe.loading) return;
  if (generating) { ollamaSettings.error = '보고서 생성이 끝난 뒤 설정을 저장해주세요. 수정한 내용은 유지됩니다.'; updateSettingsUI(); return; }
  const invalidParameter = event.target.querySelector?.('[data-ollama-parameter]:invalid');
  const advanced = invalidParameter?.closest('details');
  if (advanced) advanced.open = true;
  if (!event.target.reportValidity()) return;
  const draft = { ...ollamaSettings.draft, ollama_url: ollamaSettings.draft.ollama_url.trim() };
  ollamaSettings.saving = true; ollamaSettings.error = ''; ollamaSettings.notice = ''; updateSettingsUI();
  try {
    const data = await settingsResponse(await fetch('/api/settings/ollama', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(draft), signal: AbortSignal.timeout(15000) }));
    if (typeof data.modelfile !== 'string' || typeof data.ollama_url !== 'string' || data.revision == null) throw new Error('저장 응답을 확인할 수 없습니다. 되돌리기로 서버의 저장 상태를 확인해주세요.');
    ollamaSettings.saved = data; ollamaSettings.draft = draftFromSettings(data);
    ollamaSettings.notice = '설정을 저장했습니다. 다음 보고서부터 적용됩니다.';
    hydrateSettingsInputs();
    await refreshConnection();
  } catch (error) { ollamaSettings.error = `${settingsErrorMessage(error)}${error.message.includes('수정한 내용은 유지') ? '' : ' 수정한 내용은 유지됩니다.'}`; }
  finally { ollamaSettings.saving = false; updateSettingsUI(); }
}

function bindPageEvents() {
  const titleField = document.querySelector('#report-title');
  const inputField = document.querySelector('#report-input-data');
  if (titleField) titleField.value = editorDraft.title;
  if (inputField) inputField.value = editorDraft.input_data;
  document.querySelector('[data-thinking-log]')?.addEventListener('scroll', e => {
    const log = e.currentTarget;
    generation.follow = log.scrollHeight - log.scrollTop - log.clientHeight < 48;
    generation.scrollTop = log.scrollTop;
    const followButton = document.querySelector('[data-action="follow-thinking"]');
    if (followButton) followButton.hidden = generation.follow || !generation.thinking;
  });
  if (generating) document.querySelector('#report-form')?.querySelectorAll('input, textarea, select, button').forEach(el => { el.disabled = true; });
  document.querySelector('#period-select')?.addEventListener('change', e => { period = e.target.value; render(); });
  document.querySelector('#report-search')?.addEventListener('input', e => { search = e.target.value; updateReportResults(); });
  document.querySelector('#classification-filter')?.addEventListener('change', e => { filter = e.target.value; render(); });
  for (const id of ['report-title', 'report-input-data']) document.querySelector(`#${id}`)?.addEventListener('input', e => {
    editorDraft[e.target.name] = e.target.value;
    if (id === 'report-input-data') document.querySelector('#character-count').textContent = `${e.target.value.length.toLocaleString()} / 20,000`;
  });
  document.querySelector('#report-form')?.addEventListener('submit', generateReport);
  const settingsForm = document.querySelector('#settings-form');
  if (settingsForm) {
    hydrateSettingsInputs(); updateSettingsUI();
    settingsForm.addEventListener('submit', saveOllamaSettings);
    for (const [id, field] of [['ollama-url', 'ollama_url'], ['ollama-modelfile', 'modelfile'], ['ollama-keep-alive', 'keep_alive']]) document.querySelector(`#${id}`).addEventListener(field === 'keep_alive' ? 'change' : 'input', e => setOllamaDraft(field, e.target.value));
    document.querySelector('#ollama-model').addEventListener('change', e => {
      if (!e.target.value || !ollamaSettings.draft) return;
      setOllamaDraft('modelfile', replaceModelfileModel(ollamaSettings.draft.modelfile, e.target.value));
      document.querySelector('#ollama-modelfile').value = ollamaSettings.draft.modelfile;
    });
    settingsForm.querySelectorAll('[data-ollama-parameter]').forEach(input => input.addEventListener('input', e => {
      const name = e.target.dataset.ollamaParameter;
      setOllamaParameter(name, name === 'top_k' && !e.target.value && !e.target.validity.badInput ? null : e.target.value);
    }));
    document.querySelector('#ollama-seed-fixed').addEventListener('change', e => {
      setOllamaParameter('seed', e.target.checked ? String(ollamaParameters.seed.initial) : null);
      if (e.target.checked) document.querySelector('#ollama-seed').focus();
    });
    document.querySelector('#ollama-advanced').addEventListener('toggle', e => { ollamaSettings.advancedOpen = e.target.open; });
    loadOllamaSettings();
  }
  document.querySelector('#output-format')?.addEventListener('change', e => {
    const next = { ...preferences, format: e.target.value };
    try { localStorage.setItem(PREFS, JSON.stringify(next)); preferences = next; toast('기본 내보내기 형식을 저장했습니다.'); }
    catch { e.target.value = preferences.format === 'md' ? 'md' : 'json'; toast('설정을 저장할 수 없습니다. 브라우저 저장 공간을 확인해주세요.'); }
  });
}

function updateReportResults() {
  document.querySelector('#report-results').innerHTML = reportTable(filteredReports());
  document.querySelector('#results-count').textContent = `${filteredReports().length}개 보고서`;
}

function generationPanel() {
  return `<section class="panel thinking-panel" data-generation-panel aria-label="모델 생성 진행 상황"><div class="thinking-heading"><div class="thinking-title"><span class="thinking-symbol">${icon('activity')}</span><div><h2>모델 Thinking 로그</h2><p data-thinking-title>보고서를 생성하면 모델의 thinking 응답이 여기에 표시됩니다.</p></div></div><span class="thinking-state" data-thinking-state>대기</span></div><div class="thinking-toolbar"><span class="thinking-source">${icon('server')}Ollama에서 수신한 원문</span><div class="thinking-actions"><button type="button" class="icon-button" data-action="copy-thinking" aria-label="Thinking 로그 복사" disabled>${icon('copy')}</button><button type="button" class="icon-button" data-action="download-thinking" aria-label="Thinking 로그 내보내기" disabled>${icon('download')}</button></div></div><div class="thinking-viewport"><p class="thinking-placeholder" data-thinking-placeholder></p><pre class="thinking-log" data-thinking-log tabindex="0" aria-label="수신된 Thinking 로그" hidden></pre><button type="button" class="thinking-follow" data-action="follow-thinking" hidden>${icon('down')}최신 로그 보기</button></div><div class="thinking-footer"><div class="thinking-status" role="status" aria-live="polite"><span class="status-dot" data-thinking-dot></span><span data-thinking-message></span></div><span class="thinking-count" data-thinking-count></span><button type="button" class="text-link thinking-result" data-action="open-report" data-thinking-result hidden>완성된 보고서 보기${icon('arrow')}</button></div><ol class="thinking-status-history" data-thinking-statuses aria-label="서버 진행 상태" hidden></ol></section>`;
}

function updateGenerationUI(restoreScroll = false, replaceText = false) {
  const panel = document.querySelector('[data-generation-panel]');
  if (!panel) return;
  panel.dataset.phase = generation.phase;
  const active = generation.phase === 'running';
  panel.querySelector('[data-thinking-title]').textContent = generation.title || '보고서를 생성하면 모델의 thinking 응답이 여기에 표시됩니다.';
  panel.querySelector('[data-thinking-state]').textContent = { idle: '대기', running: '생성 중', complete: '완료', error: '오류' }[generation.phase];
  const message = generation.message || '새 보고서를 작성해 분석을 시작하세요.';
  const messageEl = panel.querySelector('[data-thinking-message]');
  if (messageEl.textContent !== message) messageEl.textContent = message;
  panel.querySelector('[data-thinking-dot]').classList.toggle('gray', !active && generation.phase !== 'complete');
  const log = panel.querySelector('[data-thinking-log]');
  const previousScrollTop = log.scrollTop;
  const shouldFollow = restoreScroll ? generation.follow : log.scrollHeight - log.scrollTop - log.clientHeight < 48;
  const renderedLength = Number(log.dataset.renderedLength || 0);
  if (restoreScroll || replaceText || renderedLength > generation.thinking.length) log.textContent = generation.thinking;
  else if (renderedLength < generation.thinking.length) log.append(document.createTextNode(generation.thinking.slice(renderedLength)));
  log.dataset.renderedLength = String(generation.thinking.length);
  log.hidden = !generation.thinking;
  const placeholder = panel.querySelector('[data-thinking-placeholder]');
  placeholder.hidden = Boolean(generation.thinking);
  placeholder.textContent = generation.phase === 'idle' ? '아직 수신된 로그가 없습니다.' : generation.phase === 'complete' ? '이 생성에서는 모델이 thinking 데이터를 보내지 않았습니다.' : generation.phase === 'error' ? 'Thinking 데이터를 받기 전에 생성이 중단되었습니다.' : generation.contentLength ? '보고서 응답을 받고 있습니다. 아직 thinking 데이터는 수신되지 않았습니다.' : '모델의 thinking 응답을 기다리고 있습니다. 초기 로딩에는 시간이 걸릴 수 있습니다.';
  if (generation.thinking) {
    log.scrollTop = shouldFollow ? log.scrollHeight : restoreScroll ? generation.scrollTop : previousScrollTop;
    generation.scrollTop = log.scrollTop;
    generation.follow = shouldFollow;
  }
  panel.querySelector('[data-action="follow-thinking"]').hidden = generation.follow || !generation.thinking;
  panel.querySelectorAll('[data-action="copy-thinking"], [data-action="download-thinking"]').forEach(button => { button.disabled = !generation.thinking; });
  panel.querySelector('[data-thinking-count]').textContent = generation.thinking ? `${generation.thinking.length.toLocaleString()}자 수신` : generation.contentLength ? `JSON 응답 ${generation.contentLength.toLocaleString()}자 수신` : '';
  const resultButton = panel.querySelector('[data-thinking-result]');
  resultButton.hidden = !generation.resultId || !reports.some(r => r.id === generation.resultId);
  resultButton.dataset.id = generation.resultId || '';
  const history = panel.querySelector('[data-thinking-statuses]');
  if (history.dataset.count !== String(generation.statuses.length)) {
    history.replaceChildren(...generation.statuses.slice(-3).map(status => {
      const item = document.createElement('li');
      const time = document.createElement('time');
      time.textContent = status.time;
      const text = document.createElement('span');
      text.textContent = status.message;
      item.append(time, text);
      return item;
    }));
    history.dataset.count = String(generation.statuses.length);
  }
  history.hidden = !generation.statuses.length;
}

function queueGenerationUI() {
  if (generationFrame !== null) return;
  generationFrame = requestAnimationFrame(() => { generationFrame = null; updateGenerationUI(); });
}

function updateGenerationForm() {
  updateSettingsUI();
  const form = document.querySelector('#report-form');
  if (!form) return;
  form.querySelectorAll('input, textarea, select, button').forEach(el => { el.disabled = generating; });
  form.querySelector('[type="submit"]').innerHTML = generating ? '<span class="spinner"></span>로컬 모델 분석 중…' : `${icon('sparkles')}보고서 생성${icon('arrow')}`;
  const errorBox = form.querySelector('.generation-error');
  errorBox.hidden = !generationError;
  errorBox.textContent = generationError;
}

// Keep partial lines and events between network chunks, including split CRLF pairs.
function createSseParser(onEvent) {
  let pending = '', event = 'message', data = [];
  function line(value) {
    if (!value) {
      if (data.length) onEvent(event, data.join('\n'));
      event = 'message'; data = [];
      return;
    }
    if (value.startsWith(':')) return;
    const colon = value.indexOf(':');
    const field = colon < 0 ? value : value.slice(0, colon);
    let content = colon < 0 ? '' : value.slice(colon + 1);
    if (content.startsWith(' ')) content = content.slice(1);
    if (field === 'event') event = content || 'message';
    if (field === 'data') data.push(content);
  }
  function consume(final = false) {
    let start = 0;
    for (let i = 0; i < pending.length; i++) {
      if (pending[i] !== '\n' && pending[i] !== '\r') continue;
      if (pending[i] === '\r' && i === pending.length - 1 && !final) break;
      line(pending.slice(start, i));
      if (pending[i] === '\r' && pending[i + 1] === '\n') i++;
      start = i + 1;
    }
    pending = pending.slice(start);
  }
  return {
    push(chunk) { pending += chunk; consume(); },
    finish() { consume(true); return !pending && !data.length && event === 'message'; },
  };
}

async function readGenerationStream(response, onEvent) {
  if (!response.headers.get('content-type')?.includes('text/event-stream') || !response.body) throw new Error('백엔드의 스트리밍 응답 형식을 확인할 수 없습니다.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let complete = false, ended = false;
  const parser = createSseParser((event, value) => {
    if (complete || !['status', 'thinking', 'content', 'result', 'error'].includes(event)) return;
    let data;
    try { data = JSON.parse(value); } catch { throw new Error('서버의 스트리밍 이벤트를 읽을 수 없습니다.'); }
    complete = onEvent(event, data) === true;
  });
  try {
    while (!complete) {
      const { value, done } = await reader.read();
      if (done) {
        ended = true;
        parser.push(decoder.decode());
        parser.finish();
        if (!complete) throw new Error('최종 보고서를 받기 전에 연결이 종료되었습니다. 수신된 로그와 입력은 유지됩니다.');
        break;
      }
      parser.push(decoder.decode(value, { stream: true }));
    }
  } finally {
    if (!ended) await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

function validGeneratedReport(report) {
  return report && typeof report.id === 'string' && report.id && typeof report.title === 'string' && classifications[report.classification] && Array.isArray(report.findings) && report.findings.every(f => f && classifications[f.classification] && Array.isArray(f.evidence) && f.evidence.every(value => typeof value === 'string'));
}

async function generateReport(e) {
  e.preventDefault();
  if (generating) return;
  const form = e.target;
  if (!form.reportValidity()) return;
  editorDraft = { title: form.elements.title.value, input_data: form.elements.input_data.value };
  const { title, input_data } = editorDraft;
  if (!title.trim() || !input_data.trim()) { toast('제목과 입력 데이터를 넣어주세요.'); return; }
  generating = true;
  generationError = '';
  generation = { phase: 'running', title, stage: 'connecting', message: '로컬 모델에 분석을 요청하고 있습니다.', thinking: '', statuses: [], contentLength: 0, resultId: null, follow: true, scrollTop: 0 };
  updateGenerationForm();
  updateGenerationUI(true, true);
  try {
    const response = await fetch('/api/reports/generate/stream', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, input_data }),
      signal: AbortSignal.timeout(310000),
    });
    if (!response.ok) {
      const failure = await response.json().catch(() => null);
      throw new Error(typeof failure?.detail === 'string' ? failure.detail : typeof failure?.message === 'string' ? failure.message : `보고서 생성 요청에 실패했습니다. (HTTP ${response.status})`);
    }
    let result;
    await readGenerationStream(response, (event, data) => {
      if (event === 'error') throw new Error(typeof data?.message === 'string' ? data.message : '모델 분석 중 오류가 발생했습니다.');
      if (event === 'status') {
        if (typeof data?.message !== 'string') throw new Error('서버 진행 상태의 형식을 확인할 수 없습니다.');
        generation.stage = typeof data.stage === 'string' ? data.stage : '';
        generation.message = data.message;
        generation.statuses.push({ message: data.message, time: new Date().toLocaleTimeString('ko-KR', { hour12: false }) });
      }
      if (event === 'thinking' || event === 'content') {
        if (typeof data?.text !== 'string') throw new Error('모델 스트리밍 데이터의 형식을 확인할 수 없습니다.');
        if (event === 'thinking') { generation.thinking += data.text; generation.message = '모델의 thinking 응답을 받고 있습니다.'; }
        else { generation.contentLength += data.text.length; generation.message = '보고서 JSON 응답을 받고 있습니다.'; }
      }
      if (event === 'result') {
        if (!validGeneratedReport(data?.report)) throw new Error('최종 보고서 응답 형식을 확인할 수 없습니다.');
        result = { ...data.report, thinking: typeof data.report.thinking === 'string' && data.report.thinking ? data.report.thinking : generation.thinking };
        return true;
      }
      queueGenerationUI();
      return false;
    });
    generation.thinking = result.thinking;
    generation.phase = 'complete';
    generation.message = '보고서 생성이 완료되었습니다.';
    generation.resultId = result.id;
    reports.unshift(result); save();
    editorDraft = { title: '', input_data: '' };
    generating = false;
    filter = 'all'; statusFilter = 'all'; search = '';
    if (page === 'create') { location.hash = 'reports'; openReport(result.id); }
    else render();
    toast('로컬 모델의 분석 보고서를 생성했습니다.');
  } catch (error) {
    generationError = error.name === 'TimeoutError' ? '모델 응답 시간이 초과되었습니다. 입력을 줄이거나 Ollama 상태를 확인해주세요.' : error instanceof TypeError ? '백엔드에 연결할 수 없습니다. FastAPI 실행 상태를 확인해주세요.' : error.message;
    generating = false;
    generation.phase = 'error';
    generation.message = generationError;
    updateGenerationForm();
    toast(generationError);
  } finally {
    generating = false;
    if (generationFrame !== null) { cancelAnimationFrame(generationFrame); generationFrame = null; }
    updateGenerationUI(false, true);
    refreshConnection();
  }
}

function modal(title, body, cls = '') {
  if (!overlay.children.length) returnFocus = document.activeElement;
  overlay.innerHTML = `<div class="modal-backdrop"><section class="modal ${cls}" role="dialog" aria-modal="true" aria-labelledby="modal-title" tabindex="-1"><header class="modal-heading"><h2 id="modal-title">${title}</h2><button class="icon-button" data-action="close-modal" aria-label="닫기">${icon('close')}</button></header>${body}</section></div>`;
  document.body.classList.add('modal-open');
  app.inert = true;
  overlay.querySelector('.modal').focus();
}

function closeModal() {
  overlay.innerHTML = ''; document.body.classList.remove('modal-open'); app.inert = false; activeModal = null;
  if (returnFocus?.isConnected) returnFocus.focus();
}

function reportThinkingPanel(report) {
  const hasThinking = typeof report.thinking === 'string' && report.thinking.length > 0;
  return `<div class="report-thinking"><p>${hasThinking ? '생성 당시 Ollama가 반환한 thinking 원문입니다.' : typeof report.thinking === 'string' ? '이 생성에서는 모델이 thinking 데이터를 보내지 않았습니다.' : '이 보고서에는 저장된 thinking 로그가 없습니다.'}</p>${hasThinking ? `<div class="report-thinking-actions"><button class="button secondary" data-action="copy-thinking" data-id="${esc(report.id)}">${icon('copy')}로그 복사</button><button class="button secondary" data-action="download-thinking" data-id="${esc(report.id)}">${icon('download')}로그 내보내기</button></div><pre class="thinking-log report-thinking-log" data-report-thinking tabindex="0" aria-label="저장된 Thinking 로그"></pre>` : ''}</div>`;
}

function openReport(id, preserveTab = false) {
  const r = reports.find(r => r.id === id); if (!r) return;
  activeModal = id;
  if (!preserveTab) reportTab = 'report';
  const json = JSON.stringify(reportPayload(r), null, 2);
  const content = reportTab === 'thinking' ? reportThinkingPanel(r) : reportTab === 'json' ? `<pre class="json-preview"><code>${esc(json)}</code></pre>` : `<div class="report-detail"><div class="report-detail-heading"><span class="eyebrow">WEB SECURITY REPORT</span><h2>${esc(r.title)}</h2><div class="report-meta"><span>${esc(r.id)}</span><span>${date(r.createdAt)}</span></div></div><div class="detail-summary"><div><span>분석 대상</span><strong>${esc(r.target || '미제공')}</strong></div><div><span>최종 판정</span>${badge(r.classification)}</div><div><span>분석 항목</span><strong>${r.findings.length}개</strong></div></div>${r.previewNote ? `<div class="info-strip preview-note">${icon('help')}${esc(r.previewNote)}</div>` : ''}<h3 class="detail-section-title">분석 항목</h3>${r.findings.length ? r.findings.map((f, i) => `<article class="finding"><div class="finding-heading"><span class="finding-number">${String(i + 1).padStart(2, '0')}</span><h3>${esc(f.vulnerability_type || classifications[f.classification].label)}</h3>${badge(f.classification)}</div><dl><div><dt>엔드포인트</dt><dd><code>${esc(f.endpoint || '미제공')}</code></dd></div><div><dt>CWE / OWASP</dt><dd>${esc(f.CWE || '미정')} / ${esc(f.OWASP || '미정')}</dd></div><div><dt>분류 신뢰도</dt><dd>${f.confidence == null ? '미정' : `${Math.round(f.confidence * 100)}%`}</dd></div></dl><div class="evidence-label">기술적 근거</div><pre class="evidence-block">${esc(f.evidence.join('\n'))}</pre>${f.reason_validation_is_needed ? `<div class="validation-note">${icon('alert')}<span>${esc(f.reason_validation_is_needed)}</span></div>` : ''}</article>`).join('') : `<div class="detail-empty">${r.classification ? '모델이 반환한 분석 항목이 없습니다.' : '모델 분석 전에는 분석 항목이 비어 있습니다.'}</div>`}<h3 class="detail-section-title">입력 데이터</h3><pre class="prompt-preview">${esc(reportInput(r))}</pre></div>`;
  modal('보고서 미리보기', `<div class="report-modal-toolbar"><div class="filter-tabs"><button class="filter-tab ${reportTab === 'report' ? 'active' : ''}" data-action="report-tab" data-value="report">${icon('file')}보고서</button><button class="filter-tab ${reportTab === 'json' ? 'active' : ''}" data-action="report-tab" data-value="json">${icon('code')}JSON</button><button class="filter-tab ${reportTab === 'thinking' ? 'active' : ''}" data-action="report-tab" data-value="thinking">${icon('activity')}Thinking</button></div><span class="sample-label">${r.classification ? '로컬 모델 분석 결과' : '분석 전 초안'}</span></div><div class="report-modal-body">${content}</div><footer class="modal-footer"><button class="button secondary danger-text" data-action="delete-report" data-id="${esc(id)}">${icon('trash')}삭제</button><div><button class="button secondary" data-action="copy-report" data-id="${esc(id)}">${icon('copy')}JSON 복사</button><button class="button primary" data-action="download-report" data-id="${esc(id)}">${icon('download')}보고서 내보내기</button></div></footer>`, 'report-modal');
  const thinkingLog = overlay.querySelector('[data-report-thinking]');
  if (thinkingLog) thinkingLog.textContent = r.thinking;
}

function markdown(r) {
  return `# ${r.title}\n\n> ${r.classification ? '로컬 모델 분석 결과' : '분석 전 초안'}\n\n- 대상: ${r.target || '미제공'}\n- 판정: ${r.classification || '분석 대기'}\n- 생성일: ${date(r.createdAt)}\n\n${r.previewNote || ''}\n\n${r.findings.map((f, i) => `## ${i + 1}. ${f.vulnerability_type || f.classification}\n\n- 엔드포인트: ${f.endpoint || '미제공'}\n- CWE: ${f.CWE || '미정'}\n- OWASP: ${f.OWASP || '미정'}\n- 판정: ${f.classification}\n\n### 근거\n\n${f.evidence.join('\n\n')}\n\n${f.reason_validation_is_needed || ''}`).join('\n\n')}\n\n## 입력 데이터\n\n${reportInput(r)}\n${r.thinking ? `\n## 모델 Thinking 로그\n\n${r.thinking}\n` : ''}`;
}

function download(content, filename, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

document.addEventListener('click', async e => {
  const button = e.target.closest('[data-action]');
  if (!button) { if (e.target.classList.contains('modal-backdrop')) closeModal(); return; }
  const action = button.dataset.action;
  if (action === 'open-report') openReport(button.dataset.id);
  if (action === 'close-modal') closeModal();
  if (action === 'report-tab') { reportTab = button.dataset.value; openReport(activeModal, true); }
  if (action === 'filter-status') { statusFilter = button.dataset.value; render(); }
  if (action === 'export-all') { download(JSON.stringify({ reports }, null, 2), 'sentinel-reports.json', 'application/json'); toast('전체 보고서를 내보냈습니다.'); }
  if (action === 'download-report') { const r = reports.find(r => r.id === button.dataset.id); if (preferences.format === 'md') download(markdown(r), `${r.id}.md`, 'text/markdown;charset=utf-8'); else download(JSON.stringify({ title: r.title, target: r.target, model: r.model || null, output: r.classification ? reportPayload(r) : null, input_data: reportInput(r), thinking: r.thinking ?? null }, null, 2), `${r.id}.json`, 'application/json'); toast('보고서를 내보냈습니다.'); }
  if (action === 'copy-report') { const r = reports.find(r => r.id === button.dataset.id); try { await navigator.clipboard.writeText(JSON.stringify(reportPayload(r), null, 2)); toast('보고서 JSON을 복사했습니다.'); } catch { toast('복사할 수 없습니다. 내보내기를 사용해주세요.'); } }
  if (action === 'copy-thinking' || action === 'download-thinking') {
    const text = button.dataset.id ? reports.find(r => r.id === button.dataset.id)?.thinking : generation.thinking;
    if (!text) return;
    if (action === 'download-thinking') { download(text, `${button.dataset.id || 'sentinel'}-thinking.txt`, 'text/plain;charset=utf-8'); toast('Thinking 로그를 내보냈습니다.'); }
    else { try { await navigator.clipboard.writeText(text); toast('Thinking 로그를 복사했습니다.'); } catch { toast('복사할 수 없습니다. 로그 내보내기를 사용해주세요.'); } }
  }
  if (action === 'follow-thinking') {
    generation.follow = true;
    const log = document.querySelector('[data-thinking-log]');
    if (log) log.scrollTop = log.scrollHeight;
    button.hidden = true;
  }
  if (action === 'delete-report') { const id = button.dataset.id; modal('보고서 삭제', `<div class="simple-modal-body"><p>이 브라우저에서 보고서를 삭제합니다. 필요한 사본은 먼저 내보내주세요.</p></div><footer class="modal-footer"><button class="button secondary" data-action="open-report" data-id="${esc(id)}">취소</button><button class="button danger" data-action="confirm-delete" data-id="${esc(id)}">삭제하기</button></footer>`, 'small-modal'); }
  if (action === 'confirm-delete') { reports = reports.filter(r => r.id !== button.dataset.id); save(); closeModal(); render(); toast('보고서를 삭제했습니다.'); }
  if (action === 'menu') { const open = document.querySelector('#sidebar').classList.toggle('open'); button.setAttribute('aria-expanded', String(open)); }
  if (action === 'close-menu') { document.querySelector('#sidebar').classList.remove('open'); document.querySelector('[data-action="menu"]').setAttribute('aria-expanded', 'false'); }
  if (action === 'check-connection') await refreshConnection(true);
  if (action === 'refresh-ollama-models') await refreshOllamaModels();
  if (action === 'probe-ollama') await probeOllamaDraft();
  if (action === 'revert-ollama-settings' && !generating) await loadOllamaSettings(true);
  if (action === 'notifications') modal('워크스페이스 상태', `<div class="simple-modal-body"><div class="notice-item"><span class="metric-icon green">${icon('folder')}</span><div><h3>저장된 보고서 ${reports.length}개</h3><p>직접 작성한 보고서는 이 브라우저에서 관리합니다.</p></div></div><div class="notice-item"><span class="metric-icon ${connection.model_connected ? 'green' : 'amber'}">${icon('server')}</span><div><h3>${connectionLabel()}</h3><p>${esc(connection.model)}</p></div></div></div>`, 'small-modal');
  if (action === 'help') modal('Sentinel 사용 가이드', `<div class="simple-modal-body help-body"><span class="eyebrow">GETTING STARTED</span><h3>제목과 데이터만 입력하세요.</h3><ol><li><strong>제목 입력</strong><p>보고서를 구분할 제목을 입력하세요. 제목은 모델의 분석 입력에 포함되지 않습니다.</p></li><li><strong>입력 데이터 붙여넣기</strong><p>HTTP 요청·응답, HTML, 코드, 로그 등 원본 데이터를 한 번에 넣으세요.</p></li><li><strong>보고서 생성</strong><p>설정된 시스템 프롬프트와 입력 데이터로 로컬 모델을 호출합니다.</p></li><li><strong>확인 및 내보내기</strong><p>판정과 근거를 검토하고 JSON 또는 Markdown으로 내보내세요.</p></li></ol></div>`, 'small-modal');
  if (action === 'profile' || action === 'workspace') modal('보안 워크스페이스', `<div class="simple-modal-body"><div class="workspace-profile"><span class="avatar">${icon('folder')}</span><div><h3>로컬 워크스페이스</h3><p>브라우저 저장소 · 로컬 Ollama</p></div></div><p>개인 로컬 워크스페이스에서 보고서를 관리합니다.</p><a class="button secondary" href="#settings" data-action="close-modal">${icon('settings')}워크스페이스 설정</a></div>`, 'small-modal');
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeModal(); document.querySelector('#sidebar')?.classList.remove('open'); document.querySelector('[data-action="menu"]')?.setAttribute('aria-expanded', 'false'); }
  if (e.key === 'Tab' && overlay.children.length) {
    const focusable = [...overlay.querySelectorAll('button, a[href], input, select, textarea, [tabindex="0"]')].filter(el => !el.disabled);
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (e.shiftKey && (document.activeElement === first || document.activeElement.classList.contains('modal'))) { e.preventDefault(); last?.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
  }
});

function route() {
  const next = location.hash.slice(1) || 'dashboard';
  page = ['dashboard', 'create', 'reports', 'settings'].includes(next) ? next : 'dashboard';
  render(); window.scrollTo({ top: 0 });
}
window.addEventListener('hashchange', route);
route();

refreshConnection();
