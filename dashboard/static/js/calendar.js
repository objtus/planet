/**
 * Planet Dashboard — calendar.js
 * HEATMAP, SOURCES, TODAY は calendar.html の <script> で定義済み
 */

// =========================================================
// 定数・状態
// =========================================================

const MONTHS = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];

const SOURCE_MAP = new Map(SOURCES.map(s => [s.id, s]));

const todayDate = new Date(TODAY + 'T00:00:00');
let cur = {
  year:     todayDate.getFullYear(),
  month:    todayDate.getMonth(),   // 0-indexed
  selDay:   todayDate.getDate(),    // 選択中の日（1-indexed）、日ビュー以外は null
  selWeek:  null,                   // 選択中の週 {year, week}
  viewMode: 'day',                  // 'day' | 'week' | 'month' | 'year'
};

let activeIds     = new Set(SOURCES.map(s => s.id));
let mediaFilter   = false;  // true = メディアあり投稿のみ表示

// =========================================================
// ISO 週番号ユーティリティ
// =========================================================

/** Date → {week, year} */
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

/** ISO年・週番号 → その週の月曜日の Date */
function isoWeekFirstDay(isoYear, isoWeekNum) {
  const jan4    = new Date(isoYear, 0, 4);
  const jan4Dow = (jan4.getDay() + 6) % 7;       // Mon=0 … Sun=6
  const week1Mon = new Date(isoYear, 0, 4 - jan4Dow);
  return new Date(week1Mon.getFullYear(), week1Mon.getMonth(),
                  week1Mon.getDate() + (isoWeekNum - 1) * 7);
}

function dateStr(y, m, d) {
  return `${y}-${String(m+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
}

function heatLevel(count) {
  if (!count)    return 0;
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
  selM.innerHTML = MONTHS.map((m, i) =>
    `<option value="${i}"${i === cur.month ? ' selected' : ''}>${m}</option>`
  ).join('');
  const thisYear = new Date().getFullYear();
  selY.innerHTML = Array.from({length: thisYear - 2016}, (_, i) => 2017 + i)
    .concat([thisYear + 1])
    .map(y => `<option value="${y}"${y === cur.year ? ' selected' : ''}>${y}年</option>`)
    .join('');

  // グリッド生成
  const body     = document.getElementById('cal-body');
  body.innerHTML = '';

  const first    = new Date(cur.year, cur.month, 1);
  const last     = new Date(cur.year, cur.month + 1, 0);
  const startDow = (first.getDay() + 6) % 7;  // 月曜=0
  const today    = new Date();

  const cells = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 1; d <= last.getDate(); d++) cells.push(d);
  while (cells.length % 7) cells.push(null);

  for (let r = 0; r < cells.length / 7; r++) {
    const tr = document.createElement('tr');

    // 週番号セル
    const refDay = cells.slice(r * 7, r * 7 + 7).find(c => c !== null);
    const { week: wn, year: wy } = isoWeek(new Date(cur.year, cur.month, refDay));
    const isSelWeek = cur.selWeek && cur.selWeek.week === wn && cur.selWeek.year === wy;

    const tdW   = document.createElement('td');
    tdW.className = 'wn-cell';
    const wnBtn = document.createElement('button');
    wnBtn.className   = `wn-btn${isSelWeek ? ' selected' : ''}`;
    wnBtn.textContent = `W${wn}`;
    wnBtn.title       = `${wy}年 第${wn}週を表示`;
    wnBtn.addEventListener('click', () => selectWeek(wy, wn));
    tdW.appendChild(wnBtn);
    tr.appendChild(tdW);

    // 7日分セル
    for (let c = 0; c < 7; c++) {
      const d  = cells[r * 7 + c];
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
        const isSel   = cur.viewMode === 'day' && d === cur.selDay;

        let cls = `day h${level}`;
        if (isToday) cls += ' today';
        if (isSel)   cls += ' selected';

        td.innerHTML = `<div class="${cls}" title="${ds}  ${count}件">${d}</div>`;
        td.querySelector('.day').addEventListener('click', () => selectDay(d));
      }
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }

  updateDetailTitle();
}

// =========================================================
// 選択操作（カレンダー側から）
// =========================================================

/** カレンダーの日付セルをクリック */
function selectDay(d) {
  cur.selDay   = d;
  cur.selWeek  = null;
  cur.viewMode = 'day';
  syncTabLabel();
  setActiveTab('tab-day');
  buildCal();
  loadDay();
}

/** カレンダーの週番号ボタンをクリック */
function selectWeek(year, week) {
  cur.selWeek  = { year, week };
  cur.selDay   = null;
  cur.viewMode = 'week';
  syncTabLabel();
  setActiveTab('tab-week');
  buildCal();
  loadWeek(year, week);
}

// =========================================================
// view-tabs から切り替え（双方向連動）
// =========================================================

/**
 * 遷移表（前モード → 後モード）で選択状態とカレンダー位置を決定する。
 *
 * 縮小方向（day←week←month←year）:
 *   ← より細かい単位の先頭を選択
 *   例: year → month = 1月を選択、month → week = 第1週を選択、week → day = 週の月曜を選択
 *
 * 拡大方向（day→week→month→year）:
 *   → 選択中の期間を含む上位単位に移動
 *   例: day → week = その日を含む週を選択
 */
function setViewMode(mode) {
  const prev = cur.viewMode;
  if (prev === mode) return;

  // ---- 拡大方向 ------------------------------------------------
  if (mode === 'week') {
    if (prev === 'day' && cur.selDay !== null) {
      cur.selWeek = isoWeek(new Date(cur.year, cur.month, cur.selDay));
    } else if (prev === 'month') {
      cur.selWeek = isoWeek(new Date(cur.year, cur.month, 1));
    } else if (prev === 'year') {
      cur.month   = 0;
      cur.selWeek = isoWeek(new Date(cur.year, 0, 1));
      // Jan 1 が前年の週に入る場合も想定してカレンダーを週の月曜の月に合わせる
      const mon = isoWeekFirstDay(cur.selWeek.year, cur.selWeek.week);
      cur.year  = mon.getFullYear();
      cur.month = mon.getMonth();
    }
    cur.selDay   = null;
    cur.viewMode = 'week';
    setActiveTab('tab-week');
    syncTabLabel();
    buildCal();
    if (cur.selWeek) loadWeek(cur.selWeek.year, cur.selWeek.week);

  } else if (mode === 'month') {
    if (prev === 'week' && cur.selWeek) {
      // 選択週の月曜が属する月へ移動
      const mon  = isoWeekFirstDay(cur.selWeek.year, cur.selWeek.week);
      cur.year   = mon.getFullYear();
      cur.month  = mon.getMonth();
    } else if (prev === 'year') {
      cur.month  = 0;
    }
    cur.selDay   = null;
    cur.selWeek  = null;
    cur.viewMode = 'month';
    setActiveTab('tab-month');
    syncTabLabel();
    buildCal();
    loadMonth();

  } else if (mode === 'year') {
    // どこからでも: cur.year は維持
    cur.selDay   = null;
    cur.selWeek  = null;
    cur.viewMode = 'year';
    setActiveTab('tab-year');
    syncTabLabel();
    buildCal();
    loadYear();

  // ---- 縮小方向 ------------------------------------------------
  } else if (mode === 'day') {
    if (prev === 'week' && cur.selWeek) {
      // 選択週の月曜を選択
      const mon  = isoWeekFirstDay(cur.selWeek.year, cur.selWeek.week);
      cur.year   = mon.getFullYear();
      cur.month  = mon.getMonth();
      cur.selDay = mon.getDate();
    } else if (prev === 'month') {
      cur.selDay = 1;                  // 月の1日を選択
    } else if (prev === 'year') {
      cur.month  = 0;
      cur.selDay = 1;                  // 1月1日を選択
    }
    cur.selWeek  = null;
    cur.viewMode = 'day';
    setActiveTab('tab-day');
    syncTabLabel();
    buildCal();
    loadDay();
  }
}

// =========================================================
// タブ UI ヘルパー
// =========================================================

function setActiveTab(id) {
  document.querySelectorAll('.view-tabs button').forEach(b => b.classList.remove('active'));
  document.getElementById(id)?.classList.add('active');
}

/** 週タブのラベルに現在の週番号を反映（"週 W12" など） */
function syncTabLabel() {
  const weekTab = document.getElementById('tab-week');
  if (!weekTab) return;
  weekTab.textContent = (cur.viewMode === 'week' && cur.selWeek)
    ? `週 W${cur.selWeek.week}`
    : '週';
}

function updateDetailTitle() {
  const el = document.getElementById('detail-title');
  if (!el) return;
  if (cur.viewMode === 'day' && cur.selDay !== null) {
    const d   = new Date(cur.year, cur.month, cur.selDay);
    const dow = ['日','月','火','水','木','金','土'][d.getDay()];
    el.textContent = `${cur.month + 1}月${cur.selDay}日（${dow}）`;
  } else if (cur.viewMode === 'week' && cur.selWeek) {
    el.textContent = `${cur.selWeek.year}年 第${cur.selWeek.week}週`;
  } else if (cur.viewMode === 'month') {
    el.textContent = `${cur.year}年${cur.month + 1}月`;
  } else if (cur.viewMode === 'year') {
    el.textContent = `${cur.year}年`;
  }
}

// =========================================================
// ナビゲーション（カレンダー上部の «‹›» 操作）
// =========================================================

function shiftMonth(n) {
  cur.month += n;
  if (cur.month < 0)  { cur.month = 11; cur.year--; }
  if (cur.month > 11) { cur.month = 0;  cur.year++; }
  buildCal();
}
function shiftYear(n) { cur.year += n; buildCal(); }

/**
 * view-tabs の ‹ / › ボタン。現在の viewMode に応じて前後の単位へ移動する。
 * n = -1: 前へ  /  n = +1: 次へ
 */
function shiftView(n) {
  if (cur.viewMode === 'day') {
    // 前日 / 次の日
    const d = new Date(cur.year, cur.month, (cur.selDay ?? 1) + n);
    cur.year   = d.getFullYear();
    cur.month  = d.getMonth();
    cur.selDay = d.getDate();
    cur.selWeek = null;
    syncTabLabel();
    buildCal();
    loadDay();

  } else if (cur.viewMode === 'week') {
    // 前週 / 次週
    if (!cur.selWeek) return;
    const mon     = isoWeekFirstDay(cur.selWeek.year, cur.selWeek.week);
    const nextMon = new Date(mon.getFullYear(), mon.getMonth(), mon.getDate() + n * 7);
    cur.selWeek  = isoWeek(nextMon);
    cur.year     = nextMon.getFullYear();
    cur.month    = nextMon.getMonth();
    cur.selDay   = null;
    syncTabLabel();
    buildCal();
    loadWeek(cur.selWeek.year, cur.selWeek.week);

  } else if (cur.viewMode === 'month') {
    // 先月 / 次の月
    cur.month += n;
    if (cur.month < 0)  { cur.month = 11; cur.year--; }
    if (cur.month > 11) { cur.month = 0;  cur.year++; }
    buildCal();
    loadMonth();

  } else if (cur.viewMode === 'year') {
    // 前年 / 次の年
    cur.year += n;
    buildCal();
    loadYear();
  }
}

function goToday() {
  const t = new Date();
  cur = {
    year: t.getFullYear(), month: t.getMonth(),
    selDay: t.getDate(), selWeek: null, viewMode: 'day',
  };
  setActiveTab('tab-day');
  syncTabLabel();
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
  if (cur.selDay === null) return;
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
  } catch (e) {
    showTimelineError(e.message);
  }
}

async function loadWeek(year, week) {
  showTimelineLoading();
  clearStats();
  const weekStr = `${year}-W${String(week).padStart(2, '0')}`;
  try {
    const [tl, stats] = await Promise.all([
      fetchJSON(`/api/timeline?period=week&date=${weekStr}`),
      fetchJSON(`/api/stats?period=week&date=${weekStr}`),
    ]);
    renderStats(stats);
    renderTimeline(tl.entries, 'week');
  } catch (e) {
    showTimelineError(e.message);
  }
}

async function loadMonth() {
  showTimelineLoading();
  clearStats();
  const monthStr = `${cur.year}-${String(cur.month + 1).padStart(2, '0')}`;
  try {
    const [tl, stats] = await Promise.all([
      fetchJSON(`/api/timeline?period=month&date=${monthStr}`),
      fetchJSON(`/api/stats?period=month&date=${monthStr}`),
    ]);
    renderStats(stats);
    renderTimeline(tl.entries, 'month');
  } catch (e) {
    showTimelineError(e.message);
  }
}

async function loadYear() {
  showTimelineLoading();
  clearStats();
  try {
    const [tl, stats] = await Promise.all([
      fetchJSON(`/api/timeline?period=year&date=${cur.year}`),
      fetchJSON(`/api/stats?period=year&date=${cur.year}`),
    ]);
    renderStats(stats);
    renderTimeline(tl.entries, 'year');
  } catch (e) {
    showTimelineError(e.message);
  }
}

// =========================================================
// 統計カード
// =========================================================

function clearStats() {
  ['stat-posts','stat-plays','stat-steps','stat-weather'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.querySelector('.stat-val').textContent = '—';
    el.querySelector('.stat-src').textContent = '';
  });
}

function renderStats(s) {
  const period = s.period ?? 'day';
  const suffix = { day: '', week: '合計', month: '合計', year: '合計' }[period] ?? '';

  const set = (id, val, sub) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.querySelector('.stat-val').textContent = val ?? '—';
    el.querySelector('.stat-src').textContent = sub ?? '';
  };

  set('stat-posts',
    s.posts != null ? s.posts.toLocaleString() : '—',
    suffix ? `${suffix}  ${s.posts_breakdown ?? ''}` : (s.posts_breakdown ?? ''));

  set('stat-plays',
    s.plays != null ? s.plays.toLocaleString() : '—',
    suffix ? `Last.fm ${suffix}` : 'Last.fm');

  set('stat-steps',
    s.steps != null ? s.steps.toLocaleString() : '—',
    suffix ? `Apple Watch ${suffix}` : 'Apple Watch');

  if (period === 'day' && s.weather) {
    const desc = s.weather.desc ?? '';
    const temp = s.weather.temp != null ? `${s.weather.temp}°` : '';
    set('stat-weather', [desc, temp].filter(Boolean).join(' ') || '—',
      s.weather.location ?? '');
  } else if (period !== 'day' && s.weather) {
    // 週・月・年: 平均気温 + min–max
    const avg  = s.weather.avg_temp != null ? `平均 ${s.weather.avg_temp}°` : '—';
    const minT = s.weather.min_temp != null ? `${Math.round(s.weather.min_temp)}°` : '?';
    const maxT = s.weather.max_temp != null ? `${Math.round(s.weather.max_temp)}°` : '?';
    set('stat-weather', avg, `${minT} – ${maxT}  ${s.weather.location ?? ''}`);
  } else {
    set('stat-weather', '—', '');
  }
}

// =========================================================
// favicon フォールバック（グローバル関数として onerror から呼ぶ）
// =========================================================

window.onFaviconLoad = function(img) {
  // naturalSize が 0 なら実質失敗（1x1 トラッキングピクセル等）と見なす
  if (img.naturalWidth <= 1 && img.naturalHeight <= 1) {
    window.onFaviconError(img);
  }
};

window.onFaviconError = function(img) {
  img.style.display = 'none';
  const fallback = img.nextElementSibling;
  if (fallback) fallback.style.removeProperty('display');
};

// =========================================================
// タイムライン描画
// =========================================================

function faviconImgHTML(faviconUrl, emoji, extraCls) {
  if (!faviconUrl) return `<span class="bicon${extraCls ? ' ' + extraCls : ''}">${emoji}</span>`;
  return `<img src="${faviconUrl}" onload="onFaviconLoad(this)" onerror="onFaviconError(this)" alt="" loading="lazy">`
       + `<span class="bicon" style="display:none">${emoji}</span>`;
}

function badgeHTML(source) {
  if (!source) return '<span class="tl-badge b-rss"><span class="bicon">🌐</span>?</span>';
  const cls  = `b-${source.cls}`;
  const icon = faviconImgHTML(source.favicon_url, source.emoji);
  return `<button class="tl-badge ${cls}" onclick="soloSource(${source.id})" title="${esc(source.name)}のみ表示（もう一度で解除）">${icon}${esc(source.short_name)}</button>`;
}

/**
 * バッジクリック: そのソースだけ表示する（ソロ）。
 * すでにそのソースのみ表示中ならすべて解除する（トグル）。
 */
function soloSource(id) {
  const activeSources = SOURCES.filter(s => s.is_active !== false);
  const onlyThis = activeSources.every(s => s.id === id ? activeIds.has(s.id) : !activeIds.has(s.id));

  if (onlyThis) {
    // すでにソロ状態 → すべて解除（filterAll）
    activeSources.forEach(s => activeIds.add(s.id));
  } else {
    // ソロにする
    activeSources.forEach(s => {
      if (s.id === id) activeIds.add(s.id);
      else             activeIds.delete(s.id);
    });
  }

  // フィルターバーのボタンを同期
  document.querySelectorAll('.ftag[data-src]').forEach(btn => {
    btn.classList.toggle('on', activeIds.has(parseInt(btn.dataset.src)));
  });

  applyFilter();
}

function esc(s) {
  return (s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** メディア添付の HTML を生成 */
function mediaHTML(mediaList) {
  if (!mediaList || !mediaList.length) return '';
  const imgs = mediaList.map(m => {
    const isVideo = (m.type || '').startsWith('video') || m.type === 'video' || m.type === 'gifv';
    const thumb   = m.thumb || m.url;
    if (isVideo) {
      return `<a href="${esc(m.url)}" target="_blank" rel="noopener" class="tl-media-video" title="動画を開く">
                <span class="tl-media-play">▶</span>
                <img src="${esc(thumb)}" loading="lazy" alt="">
              </a>`;
    }
    return `<a href="${esc(m.url)}" target="_blank" rel="noopener">
              <img src="${esc(thumb)}" loading="lazy" alt="" class="tl-media-img">
            </a>`;
  });
  return `<div class="tl-media">${imgs.join('')}</div>`;
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

    const timeLabel = (mode === 'week' || mode === 'month' || mode === 'year')
      ? `${e.date.slice(5)} ${e.time}`
      : e.time;

    const linkHTML = e.url
      ? ` <a href="${esc(e.url)}" target="_blank" rel="noopener"
              style="color:var(--color-text-info);font-size:10px">↗</a>`
      : '';

    // メディアフラグ（data 属性で applyFilter から参照）
    const mediaMark = e.has_media ? ' data-media="1"' : '';

    // メディア表示: URL あり→サムネイル、なし(has_media フラグのみ)→小アイコン
    const mediaSection = e.media && e.media.length
      ? mediaHTML(e.media)
      : (e.has_media && e.url
          ? `<span class="tl-media-hint" title="添付あり（投稿を開くと確認できます）">📎</span>`
          : '');

    return `<div class="tl-item" data-src="${e.source_id}"${mediaMark}>
      ${badge}
      <div class="tl-content">
        ${mainHTML}${linkHTML}
        ${mediaSection}
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

let filterBarOpen = false;  // ソース一覧の展開状態

function toggleFilter(btn) {
  const id = parseInt(btn.dataset.src);
  if (activeIds.has(id)) activeIds.delete(id);
  else                   activeIds.add(id);
  btn.classList.toggle('on', activeIds.has(id));
  applyFilter();
}

function filterAll() {
  SOURCES.filter(s => s.is_active !== false).forEach(s => activeIds.add(s.id));
  document.querySelectorAll('.ftag[data-src]').forEach(b => b.classList.add('on'));
  applyFilter();
}

/** フィルター集計バッジを更新 */
function updateFilterCount() {
  const el     = document.getElementById('filter-count');
  if (!el) return;
  const activeSources = SOURCES.filter(s => s.is_active !== false);
  const on  = activeSources.filter(s => activeIds.has(s.id)).length;
  const tot = activeSources.length;
  el.textContent = on === tot ? `全${tot}` : `${on}/${tot}`;
  // 絞り込み中はトグルボタンをハイライト
  const toggle = document.getElementById('filter-toggle');
  if (toggle) toggle.classList.toggle('filtering', on < tot || mediaFilter);
}

function applyFilter() {
  let visible = 0;
  document.querySelectorAll('#timeline .tl-item').forEach(item => {
    const id         = parseInt(item.dataset.src);
    const srcMatch   = activeIds.has(id);
    const mediaMatch = !mediaFilter || item.dataset.media === '1';
    const show = srcMatch && mediaMatch;
    item.classList.toggle('hidden', !show);
    if (show) visible++;
  });
  const total = document.querySelectorAll('#timeline .tl-item').length;
  document.getElementById('no-items').style.display =
    (visible === 0 && total > 0) ? 'block' : 'none';

  const mediaBtn = document.getElementById('media-filter-btn');
  if (mediaBtn) mediaBtn.classList.toggle('on', mediaFilter);
  updateFilterCount();
}

function toggleMediaFilter() {
  mediaFilter = !mediaFilter;
  applyFilter();
}

/** ソース一覧行の展開/折りたたみ */
function toggleFilterBar() {
  filterBarOpen = !filterBarOpen;
  const row    = document.getElementById('filter-source-row');
  const arrow  = document.getElementById('filter-arrow');
  if (row)   row.style.display   = filterBarOpen ? 'flex' : 'none';
  if (arrow) arrow.textContent   = filterBarOpen ? '▴' : '▾';
}

// =========================================================
// フィルターバー（動的生成）
// =========================================================

function buildFilterBar() {
  const bar = document.getElementById('filter-bar');
  if (!bar) return;

  // ---- ヘッダー行 ----------------------------------------
  const header = document.createElement('div');
  header.className = 'filter-header';

  // トグルボタン
  const toggle = document.createElement('button');
  toggle.id        = 'filter-toggle';
  toggle.className = 'filter-toggle-btn';
  toggle.title     = 'ソースフィルターを展開/折りたたむ';
  toggle.onclick   = toggleFilterBar;
  toggle.innerHTML = 'フィルター <span id="filter-count">全0</span>'
                   + ' <span id="filter-arrow">▾</span>';
  header.appendChild(toggle);

  // すべて解除
  const allBtn = document.createElement('button');
  allBtn.className   = 'filter-all';
  allBtn.textContent = 'すべて';
  allBtn.onclick     = filterAll;
  header.appendChild(allBtn);

  // セパレーター
  const sep = document.createElement('span');
  sep.className = 'filter-sep';
  header.appendChild(sep);

  // メディアフィルター
  const mediaBtn = document.createElement('button');
  mediaBtn.id        = 'media-filter-btn';
  mediaBtn.className = 'ftag f-rss';
  mediaBtn.title     = '画像・動画が添付された投稿のみ表示';
  mediaBtn.onclick   = toggleMediaFilter;
  mediaBtn.innerHTML = '<span class="ficon">📷</span>メディア';
  header.appendChild(mediaBtn);

  bar.appendChild(header);

  // ---- ソース一覧行（デフォルト折りたたみ）--------------
  const sourceRow = document.createElement('div');
  sourceRow.id        = 'filter-source-row';
  sourceRow.className = 'filter-source-row';
  sourceRow.style.display = 'none';

  SOURCES.filter(s => s.is_active !== false).forEach(s => {
    const btn       = document.createElement('button');
    btn.className   = `ftag f-${s.cls} on`;
    btn.dataset.src = s.id;
    btn.title       = s.name;
    btn.onclick     = () => toggleFilter(btn);

    if (s.favicon_url) {
      const img   = document.createElement('img');
      img.src     = s.favicon_url;
      img.alt     = '';
      img.loading = 'lazy';
      img.addEventListener('load',  () => window.onFaviconLoad(img));
      img.addEventListener('error', () => window.onFaviconError(img));
      const emojiSpan       = document.createElement('span');
      emojiSpan.className   = 'ficon';
      emojiSpan.textContent = s.emoji;
      emojiSpan.style.display = 'none';
      btn.appendChild(img);
      btn.appendChild(emojiSpan);
    } else {
      const icon       = document.createElement('span');
      icon.className   = 'ficon';
      icon.textContent = s.emoji;
      btn.appendChild(icon);
    }

    btn.appendChild(document.createTextNode(s.short_name));
    sourceRow.appendChild(btn);
  });

  bar.appendChild(sourceRow);

  // 初期カウント表示
  updateFilterCount();
}

// =========================================================
// 初期化
// =========================================================

buildFilterBar();
buildCal();
loadDay();
