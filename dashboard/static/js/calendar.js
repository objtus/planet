/**
 * Planet Dashboard — calendar.js
 * HEATMAP, SOURCES, TODAY は calendar.html の <script> で定義済み
 */

// =========================================================
// 定数・状態
// =========================================================

const MONTHS   = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];
const DOW_HEADERS = ['月','火','水','木','金','土','日'];

// SOURCES を id → オブジェクト の Map に変換
const SOURCE_MAP = new Map(SOURCES.map(s => [s.id, s]));

// 初期状態
const todayDate = new Date(TODAY + 'T00:00:00');
let cur = {
  year:  todayDate.getFullYear(),
  month: todayDate.getMonth(),       // 0-indexed
  selDay: todayDate.getDate(),        // 選択中の日（1-indexed）
  selWeek: null,                      // 選択中の週 {year, week}
  viewMode: 'day',                    // 'day' | 'week' | 'month' | 'year'
};

// フィルター: アクティブな source_id の Set（初期値：全 ON）
let activeIds = new Set(SOURCES.map(s => s.id));

// =========================================================
// ISO 週番号
// =========================================================

function isoWeek(d) {
  const t  = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dn = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - dn);
  const y  = t.getUTCFullYear();
  const w1 = new Date(Date.UTC(y, 0, 4));
  return {
    week: 1 + Math.round(((t - w1) / 86400000 - 3 + (w1.getUTCDay() || 7)) / 7),
    year: y,
  };
}

function dateStr(y, m, d) {
  return `${y}-${String(m+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
}

function heatLevel(count) {
  if (!count)   return 0;
  if (count < 3)  return 1;
  if (count < 10) return 2;
  if (count < 25) return 3;
  if (count < 60) return 4;
  return 5;
}

// =========================================================
// カレンダーグリッド構築
// =========================================================

function buildCal() {
  // セレクト更新
  const selM = document.getElementById('sel-month');
  const selY = document.getElementById('sel-year');
  selM.innerHTML = MONTHS.map((m,i) =>
    `<option value="${i}"${i===cur.month?' selected':''}>${m}</option>`
  ).join('');
  const thisYear = new Date().getFullYear();
  selY.innerHTML = Array.from({length: thisYear - 2016}, (_,i) => 2017 + i)
    .concat([thisYear + 1])
    .map(y => `<option value="${y}"${y===cur.year?' selected':''}>${y}年</option>`)
    .join('');

  // グリッド生成
  const body  = document.getElementById('cal-body');
  body.innerHTML = '';

  const first    = new Date(cur.year, cur.month, 1);
  const last     = new Date(cur.year, cur.month + 1, 0);
  const startDow = (first.getDay() + 6) % 7;  // 月曜=0
  const today    = new Date();

  // セル配列（null = 空）
  const cells = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 1; d <= last.getDate(); d++) cells.push(d);
  while (cells.length % 7) cells.push(null);

  for (let r = 0; r < cells.length / 7; r++) {
    const tr   = document.createElement('tr');

    // 週番号セル（最左列）
    const refDay = cells[r*7] ?? (cells.find((c,i) => i >= r*7 && c !== null));
    const { week: wn, year: wy } = isoWeek(new Date(cur.year, cur.month, refDay));
    const isSelWeek = cur.selWeek && cur.selWeek.week === wn && cur.selWeek.year === wy;
    const tdW = document.createElement('td');
    tdW.className = 'wn-cell';
    const wnBtn = document.createElement('button');
    wnBtn.className = `wn-btn${isSelWeek ? ' selected' : ''}`;
    wnBtn.textContent = `W${wn}`;
    wnBtn.title = `${wy}年 第${wn}週を表示`;
    wnBtn.addEventListener('click', () => selectWeek(wy, wn));
    tdW.appendChild(wnBtn);
    tr.appendChild(tdW);

    // 7日分
    for (let c = 0; c < 7; c++) {
      const d  = cells[r*7+c];
      const td = document.createElement('td');
      if (!d) {
        td.innerHTML = '<div class="day empty"></div>';
      } else {
        const ds      = dateStr(cur.year, cur.month, d);
        const count   = HEATMAP[ds] ?? 0;
        const level   = heatLevel(count);
        const isToday = d === today.getDate()
                     && cur.month === today.getMonth()
                     && cur.year  === today.getFullYear();
        const isSel   = d === cur.selDay && cur.viewMode === 'day';

        let cls = `day h${level}`;
        if (isToday) cls += ' today';
        if (isSel)   cls += ' selected';

        td.innerHTML = `<div class="${cls}" title="${ds} ${count}件">${d}</div>`;
        td.querySelector('.day').addEventListener('click', () => selectDay(d));
      }
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }

  updateDetailTitle();
}

// =========================================================
// 選択操作
// =========================================================

function selectDay(d) {
  cur.selDay  = d;
  cur.selWeek = null;
  cur.viewMode = 'day';
  setActiveTab('tab-day');
  buildCal();
  loadDay();
}

function selectWeek(year, week) {
  cur.selWeek = { year, week };
  cur.selDay  = null;
  cur.viewMode = 'week';
  setActiveTab('tab-week');
  buildCal();
  loadWeek(year, week);
}

function setViewMode(mode) {
  cur.viewMode = mode;
  buildCal();
  if (mode === 'day')   loadDay();
  if (mode === 'week' && cur.selWeek) loadWeek(cur.selWeek.year, cur.selWeek.week);
  if (mode === 'month') loadMonth();
  if (mode === 'year')  loadYear();
}

function setActiveTab(id) {
  document.querySelectorAll('.view-tabs button').forEach(b => b.classList.remove('active'));
  document.getElementById(id)?.classList.add('active');
}

function updateDetailTitle() {
  const el = document.getElementById('detail-title');
  if (!el) return;
  if (cur.viewMode === 'day' && cur.selDay) {
    const d   = new Date(cur.year, cur.month, cur.selDay);
    const dow = ['日','月','火','水','木','金','土'][d.getDay()];
    el.textContent = `${cur.month+1}月${cur.selDay}日（${dow}）`;
  } else if (cur.viewMode === 'week' && cur.selWeek) {
    el.textContent = `${cur.selWeek.year}年 第${cur.selWeek.week}週`;
  } else if (cur.viewMode === 'month') {
    el.textContent = `${cur.year}年${cur.month+1}月`;
  } else if (cur.viewMode === 'year') {
    el.textContent = `${cur.year}年`;
  }
}

// =========================================================
// ナビゲーション
// =========================================================

function shiftMonth(n) {
  cur.month += n;
  if (cur.month < 0)  { cur.month = 11; cur.year--; }
  if (cur.month > 11) { cur.month = 0;  cur.year++; }
  buildCal();
}
function shiftYear(n)  { cur.year += n; buildCal(); }
function goToday() {
  const t = new Date();
  cur = { ...cur, year: t.getFullYear(), month: t.getMonth(),
          selDay: t.getDate(), selWeek: null, viewMode: 'day' };
  setActiveTab('tab-day');
  buildCal();
  loadDay();
}
function onSelChange() {
  cur.month = parseInt(document.getElementById('sel-month').value);
  cur.year  = parseInt(document.getElementById('sel-year').value);
  buildCal();
}

// =========================================================
// データ取得
// =========================================================

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function showTimelineLoading() {
  document.getElementById('timeline').innerHTML =
    '<div class="tl-loading">読み込み中…</div>';
  document.getElementById('no-items').style.display = 'none';
}

async function loadDay() {
  if (!cur.selDay) return;
  const ds = dateStr(cur.year, cur.month, cur.selDay);
  showTimelineLoading();
  clearStats();
  try {
    const [tl, stats] = await Promise.all([
      fetchJSON(`/api/timeline?period=day&date=${ds}`),
      fetchJSON(`/api/stats?date=${ds}`),
    ]);
    renderStats(stats);
    renderTimeline(tl.entries, 'day');
  } catch(e) {
    showTimelineError(e.message);
  }
}

async function loadWeek(year, week) {
  showTimelineLoading();
  clearStats();
  const weekStr = `${year}-W${String(week).padStart(2,'0')}`;
  try {
    const tl = await fetchJSON(`/api/timeline?period=week&date=${weekStr}`);
    renderTimeline(tl.entries, 'week');
  } catch(e) {
    showTimelineError(e.message);
  }
}

async function loadMonth() {
  showTimelineLoading();
  clearStats();
  const monthStr = `${cur.year}-${String(cur.month+1).padStart(2,'0')}`;
  try {
    const tl = await fetchJSON(`/api/timeline?period=month&date=${monthStr}`);
    renderTimeline(tl.entries, 'month');
  } catch(e) {
    showTimelineError(e.message);
  }
}

async function loadYear() {
  showTimelineLoading();
  clearStats();
  try {
    const tl = await fetchJSON(`/api/timeline?period=year&date=${cur.year}`);
    renderTimeline(tl.entries, 'year');
  } catch(e) {
    showTimelineError(e.message);
  }
}

// =========================================================
// 統計カード
// =========================================================

function clearStats() {
  ['stat-posts','stat-plays','stat-steps','stat-weather'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.querySelector('.stat-val').textContent = '—'; el.querySelector('.stat-src').textContent = ''; }
  });
}

function renderStats(s) {
  const set = (id, val, sub) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.querySelector('.stat-val').textContent = val ?? '—';
    el.querySelector('.stat-src').textContent = sub ?? '';
  };

  set('stat-posts',
    s.posts != null ? s.posts.toLocaleString() : '—',
    s.posts_breakdown ?? '');

  set('stat-plays',
    s.plays != null ? s.plays.toLocaleString() : '—',
    'Last.fm');

  set('stat-steps',
    s.steps != null ? s.steps.toLocaleString() : '—',
    'Apple Watch');

  if (s.weather) {
    const desc = s.weather.desc ?? '';
    const temp = s.weather.temp != null ? `${s.weather.temp}°` : '';
    set('stat-weather',
      [desc, temp].filter(Boolean).join(' ') || '—',
      s.weather.location ?? '');
  } else {
    set('stat-weather', '—', '');
  }
}

// =========================================================
// タイムライン描画
// =========================================================

function badgeHTML(source) {
  if (!source) return '<span class="tl-badge b-rss"><span class="bicon">🌐</span>?</span>';
  const cls = `b-${source.cls}`;
  // favicon を img で試みる（失敗時は emoji にフォールバック）
  const icon = source.favicon_url
    ? `<img src="${source.favicon_url}" onerror="this.style.display='none';this.nextSibling.style.display='inline'" alt="">`
      + `<span class="bicon" style="display:none">${source.emoji}</span>`
    : `<span class="bicon">${source.emoji}</span>`;
  return `<span class="tl-badge ${cls}">${icon}${esc(source.short_name)}</span>`;
}

function esc(s) {
  return (s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function renderTimeline(entries, mode) {
  const container = document.getElementById('timeline');
  const noItems   = document.getElementById('no-items');

  if (!entries.length) {
    container.innerHTML = '';
    noItems.style.display = 'block';
    return;
  }
  noItems.style.display = 'none';

  const html = entries.map(e => {
    const source = SOURCE_MAP.get(e.source_id);
    const badge  = badgeHTML(source);

    let mainHTML;
    if (e.cw) {
      mainHTML = `<details><summary>${esc(e.cw)}</summary><div class="tl-text">${esc(e.content)}</div></details>`;
    } else if (e.is_boost && e.content) {
      const prefix = source?.type === 'mastodon' ? 'BT' : 'RN';
      mainHTML = `<div class="tl-sub">${prefix}: ${esc(e.content)}</div>`;
    } else {
      mainHTML = `<div class="tl-text">${esc(e.content)}</div>`;
    }

    const timeLabel = mode === 'week' || mode === 'month'
      ? `${e.date.slice(5)} ${e.time}`
      : e.time;

    const linkHTML = e.url
      ? ` <a href="${esc(e.url)}" target="_blank" rel="noopener" style="color:var(--color-text-info);font-size:10px">↗</a>`
      : '';

    return `<div class="tl-item" data-src="${e.source_id}">
      ${badge}
      <div class="tl-content">
        ${mainHTML}${linkHTML}
        <div class="tl-time">${timeLabel}</div>
      </div>
    </div>`;
  }).join('');

  container.innerHTML = html;
  applyFilter();
}

function showTimelineError(msg) {
  document.getElementById('timeline').innerHTML =
    `<div class="tl-loading" style="color:#A32D2D">エラー: ${esc(msg)}</div>`;
}

// =========================================================
// フィルター
// =========================================================

function toggleFilter(btn) {
  const id = parseInt(btn.dataset.src);
  if (activeIds.has(id)) activeIds.delete(id);
  else                   activeIds.add(id);
  btn.classList.toggle('on', activeIds.has(id));
  applyFilter();
}

function filterAll() {
  SOURCES.forEach(s => activeIds.add(s.id));
  document.querySelectorAll('.ftag').forEach(b => b.classList.add('on'));
  applyFilter();
}

function applyFilter() {
  let visible = 0;
  document.querySelectorAll('#timeline .tl-item').forEach(item => {
    const id   = parseInt(item.dataset.src);
    const show = activeIds.has(id);
    item.classList.toggle('hidden', !show);
    if (show) visible++;
  });
  document.getElementById('no-items').style.display =
    (visible === 0 && document.querySelectorAll('#timeline .tl-item').length > 0)
      ? 'block' : 'none';
}

// =========================================================
// フィルターバー構築（JS で動的生成）
// =========================================================

function buildFilterBar() {
  const bar = document.getElementById('filter-bar');
  if (!bar) return;

  const allBtn = document.createElement('button');
  allBtn.className = 'filter-all';
  allBtn.textContent = 'すべて';
  allBtn.onclick = filterAll;
  bar.appendChild(allBtn);

  SOURCES.forEach(s => {
    const btn = document.createElement('button');
    btn.className = `ftag f-${s.cls} on`;
    btn.dataset.src = s.id;
    btn.title = s.name;
    btn.onclick = () => toggleFilter(btn);

    const icon = document.createElement('span');
    icon.className = 'ficon';
    icon.textContent = s.emoji;
    btn.appendChild(icon);
    btn.appendChild(document.createTextNode(s.short_name));
    bar.appendChild(btn);
  });
}

// =========================================================
// 初期化
// =========================================================

buildFilterBar();
buildCal();
loadDay();
