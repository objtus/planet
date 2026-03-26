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

// タイムラインに実際に表示されている期間のタイトル（カレンダーナビと分離）
let tlTitle = '';

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

/** ISO 週の月〜日を「M月d日〜…」形式で表示（年をまたぐときは年も付与） */
function isoWeekDateRangeLabel(isoYear, isoWeekNum) {
  const mon = isoWeekFirstDay(isoYear, isoWeekNum);
  const sun = new Date(mon.getFullYear(), mon.getMonth(), mon.getDate() + 6);
  const y1 = mon.getFullYear(), m1 = mon.getMonth() + 1, d1 = mon.getDate();
  const y2 = sun.getFullYear(), m2 = sun.getMonth() + 1, d2 = sun.getDate();
  if (y1 !== y2) {
    return `${y1}年${m1}月${d1}日〜${y2}年${m2}月${d2}日`;
  }
  if (m1 === m2) {
    return `${m1}月${d1}日〜${d2}日`;
  }
  return `${m1}月${d1}日〜${m2}月${d2}日`;
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

  // 前月・翌月の年月
  const prevLast  = new Date(cur.year, cur.month, 0);
  const prevYear  = prevLast.getFullYear();
  const prevMonth = prevLast.getMonth();
  const nextYear  = cur.month === 11 ? cur.year + 1 : cur.year;
  const nextMonth = cur.month === 11 ? 0 : cur.month + 1;

  // セルを {d, y, m, other} の形式で構築（null を使わない）
  const cells = [];
  for (let i = 0; i < startDow; i++) {
    const d = prevLast.getDate() - startDow + 1 + i;
    cells.push({ d, y: prevYear, m: prevMonth, other: true });
  }
  for (let d = 1; d <= last.getDate(); d++) {
    cells.push({ d, y: cur.year, m: cur.month, other: false });
  }
  let nday = 1;
  while (cells.length % 7) {
    cells.push({ d: nday++, y: nextYear, m: nextMonth, other: true });
  }

  for (let r = 0; r < cells.length / 7; r++) {
    const tr = document.createElement('tr');

    // 週番号セル（行の先頭セルの実際の日付から ISO 週を計算）
    const firstCell = cells[r * 7];
    const { week: wn, year: wy } = isoWeek(new Date(firstCell.y, firstCell.m, firstCell.d));
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
      const cell = cells[r * 7 + c];
      const td   = document.createElement('td');

      const ds      = dateStr(cell.y, cell.m, cell.d);
      const isToday = cell.d === today.getDate()
                   && cell.m === today.getMonth()
                   && cell.y === today.getFullYear();
      // 選択状態は当月のみ（他月の同じ日番号を誤ってハイライトしない）
      const isSel   = !cell.other && cur.viewMode === 'day' && cell.d === cur.selDay;

      // ヒートマップは当月のみ表示（他月は常に h0 で無色）
      const level = cell.other ? 0 : heatLevel(HEATMAP[ds] ?? 0);
      const count = cell.other ? 0 : (HEATMAP[ds] ?? 0);

      let cls = `day h${level}`;
      if (cell.other) cls += ' other';
      if (isToday)    cls += ' today';
      if (isSel)      cls += ' selected';

      const title = cell.other ? ds : `${ds}  ${count}件`;
      td.innerHTML = `<div class="${cls}" title="${title}">${cell.d}</div>`;
      td.querySelector('.day').addEventListener(
        'click',
        cell.other
          ? () => selectOtherDay(cell.y, cell.m, cell.d)
          : () => selectDay(cell.d),
      );
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }

  updateDetailTitle();
  updateCalHeaderButtons();
}

/** カレンダーヘッダーの月・年ボタンのラベルを現在表示中の年月に合わせる */
function updateCalHeaderButtons() {
  const btnM = document.getElementById('btn-cal-month');
  const btnY = document.getElementById('btn-cal-year');
  if (btnM) btnM.textContent = `${cur.month + 1}月`;
  if (btnY) btnY.textContent = `${cur.year}年`;
}

/**
 * カレンダーヘッダーの「N月」ボタン用。
 * setViewMode('month') は year→month 遷移時に cur.month=0（1月）にする
 * 仕様があるため、カレンダー表示中の月をそのまま維持する専用関数を使う。
 */
function goCalMonth() {
  cur.selDay   = null;
  cur.selWeek  = null;
  cur.viewMode = 'month';
  setActiveTab('tab-month');
  syncTabLabel();
  buildCal();
  loadMonth();
}

/** カレンダーヘッダーの「N年」ボタン用。 */
function goCalYear() {
  cur.selDay   = null;
  cur.selWeek  = null;
  cur.viewMode = 'year';
  setActiveTab('tab-year');
  syncTabLabel();
  buildCal();
  loadYear();
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

/** 他月の日付セルをクリック: カレンダーをその月に切り替えてから日選択 */
function selectOtherDay(year, month, day) {
  cur.year     = year;
  cur.month    = month;
  cur.selDay   = day;
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

/** タイムラインのタイトルを確定して保存し DOM に反映する */
function setTlTitle(text) {
  tlTitle = text;
  const el = document.getElementById('detail-title');
  if (el) el.textContent = text;
}

/** buildCal() から呼ばれる。カレンダーナビで cur が変化しても保存済みの値を復元するだけ */
function updateDetailTitle() {
  const el = document.getElementById('detail-title');
  if (el && tlTitle) el.textContent = tlTitle;
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
  const _d  = new Date(cur.year, cur.month, cur.selDay);
  const dow = ['日','月','火','水','木','金','土'][_d.getDay()];
  setTlTitle(`${cur.year}年${cur.month + 1}月${cur.selDay}日（${dow}）`);
  showTimelineLoading();
  clearStats();
  showFilterBarForTimeline(true);
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
  const range = isoWeekDateRangeLabel(year, week);
  setTlTitle(`${year}年 第${week}週（${range}）`);
  showTimelineLoading();
  clearStats();
  showFilterBarForTimeline(true);
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
  setTlTitle(`${cur.year}年${cur.month + 1}月`);
  showTimelineLoading();
  clearStats();
  showFilterBarForTimeline(true);
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

function showFilterBarForTimeline(show) {
  const bar = document.getElementById('filter-bar');
  if (bar) bar.style.display = show ? '' : 'none';
}

/** 年ビュー: 投稿一覧は取得・表示しない（負荷対策。将来サマリー一覧を表示予定） */
function renderYearTimelinePlaceholder() {
  const container = document.getElementById('timeline');
  const noItems   = document.getElementById('no-items');
  if (!container) return;
  noItems.style.display = 'none';
  container.innerHTML = `<div class="tl-year-placeholder">
    <p class="tl-year-placeholder-title">投稿一覧は表示していません</p>
    <p class="tl-year-placeholder-note">年単位では件数が多いためタイムラインを省略しています。今後、サマリー一覧をここに表示する予定です。</p>
  </div>`;
}

async function loadYear() {
  setTlTitle(`${cur.year}年`);
  showTimelineLoading();
  clearStats();
  showFilterBarForTimeline(false);
  try {
    const stats = await fetchJSON(`/api/stats?period=year&date=${cur.year}`);
    renderStats(stats);
    renderYearTimelinePlaceholder();
  } catch (e) {
    showTimelineError(e.message);
  }
}

// =========================================================
// 統計カード
// =========================================================

/** OpenWeatherMap / WMO 由来の main・日本語 desc から天気絵文字 */
function weatherEmoji(main, desc) {
  const d = desc || '';
  if (/激しい雷雨|雷雨/.test(d)) return '⛈';
  if (/雹/.test(d)) return '⛈';
  if (/雪|霰|小雪|大雪/.test(d)) return '❄️';
  if (/雨|小雨|強い雨|にわか|霧雨|着氷性の雨/.test(d)) return '🌧';
  if (/霧|着氷霧/.test(d)) return '🌫';
  if (/快晴|ほぼ晴れ/.test(d)) return '☀️';
  if (/晴れ時々曇り|時々曇/.test(d)) return '🌤';
  if (/曇り|くもり|薄い雲|曇がち|雲/.test(d) && !/晴/.test(d)) return '☁️';

  const m = String(main || '').toLowerCase();
  if (m === 'thunderstorm') return '⛈';
  if (m === 'drizzle') return '🌦';
  if (m === 'rain') return '🌧';
  if (m === 'snow') return '❄️';
  if (['mist', 'fog', 'haze', 'smoke', 'dust', 'sand', 'ash', 'squall'].includes(m)) return '🌫';
  if (m === 'tornado') return '🌪';
  if (m === 'clear') return '☀️';
  if (m === 'clouds') return '☁️';

  const low = d.toLowerCase();
  if (/thunder|storm/.test(low)) return '⛈';
  if (/drizzle/.test(low)) return '🌦';
  if (/rain|shower/.test(low)) return '🌧';
  if (/snow/.test(low)) return '❄️';
  if (/fog|mist|haze/.test(low)) return '🌫';
  if (/clear/.test(low)) return '☀️';
  if (/cloud/.test(low)) return '☁️';

  return '🌡';
}

function clearStats() {
  ['stat-posts','stat-plays','stat-steps','stat-weather'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.querySelector('.stat-val').textContent = '—';
    el.querySelector('.stat-src').textContent = '';
  });
  const strip = document.getElementById('week-weather-strip');
  if (strip) {
    strip.innerHTML = '';
    strip.hidden = true;
  }
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
    const em   = weatherEmoji(s.weather.main, desc);
    const line = [em, desc, temp].filter(Boolean).join(' ');
    set('stat-weather', line.trim() || '—', s.weather.location ?? '');
  } else if (period !== 'day' && s.weather) {
    // 週・月・年: 平均気温 + min–max
    const avg  = s.weather.avg_temp != null ? `平均 ${s.weather.avg_temp}°` : '—';
    const minT = s.weather.min_temp != null ? `${Math.round(s.weather.min_temp)}°` : '?';
    const maxT = s.weather.max_temp != null ? `${Math.round(s.weather.max_temp)}°` : '?';
    set('stat-weather', avg, `${minT} – ${maxT}  ${s.weather.location ?? ''}`);
  } else {
    set('stat-weather', '—', '');
  }

  renderWeekWeatherStrip(period, s);
}

/** ISO 週の7日分（月曜始まり）を stat-row の直下に表示 */
const WW_DOW = ['月', '火', '水', '木', '金', '土', '日'];

function renderWeekWeatherStrip(period, s) {
  const strip = document.getElementById('week-weather-strip');
  if (!strip) return;

  if (period !== 'week' || !Array.isArray(s.weather_days) || !s.weather_days.length) {
    strip.innerHTML = '';
    strip.hidden = true;
    return;
  }

  let loc = s.weather?.location ?? '';
  if (!loc) {
    for (const d of s.weather_days) {
      if (d.location) { loc = d.location; break; }
    }
  }

  const parts = s.weather_days.map((d, i) => {
    const md = d.date ? d.date.slice(5).replace('-', '/') : '';
    let temp = '—';
    if (d.temp_min != null || d.temp_max != null) {
      const lo = d.temp_min != null ? Math.round(d.temp_min) : '—';
      const hi = d.temp_max != null ? Math.round(d.temp_max) : '—';
      temp = `${lo}° / ${hi}°`;
    }
    const rawDesc = (d.desc || '').trim();
    const desc    = rawDesc || '—';
    const em      = weatherEmoji(d.main, rawDesc);
    return `<div class="ww-cell" title="${escapeHtml(d.desc || '')}">
      <div class="ww-dow">${WW_DOW[i]}</div>
      <div class="ww-date">${escapeHtml(md)}</div>
      <div class="ww-icon" aria-hidden="true">${em}</div>
      <div class="ww-temp">${temp}</div>
      <div class="ww-desc">${escapeHtml(desc)}</div>
    </div>`;
  });

  strip.innerHTML = `
    <div class="ww-head">
      <span class="ww-title">この週の天気</span>
      ${loc ? `<span class="ww-loc">${escapeHtml(loc)}</span>` : ''}
    </div>
    <div class="ww-row">${parts.join('')}</div>`;
  strip.hidden = false;
}

function escapeHtml(t) {
  return String(t)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
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

// =========================================================
// ライトボックス
// =========================================================

let _lbUrls = [];
let _lbIdx  = 0;

function openLightbox(urls, idx) {
  _lbUrls = urls;
  _lbIdx  = idx;
  _updateLightbox();
  document.getElementById('lightbox').style.display = 'flex';
  document.addEventListener('keydown', _onLbKey);
}

function _updateLightbox() {
  document.getElementById('lb-img').src = _lbUrls[_lbIdx];
  const multi   = _lbUrls.length > 1;
  const prev    = document.querySelector('.lb-prev');
  const next    = document.querySelector('.lb-next');
  const counter = document.getElementById('lb-counter');
  if (prev)    prev.classList.toggle('lb-hidden', !multi);
  if (next)    next.classList.toggle('lb-hidden', !multi);
  if (counter) {
    counter.classList.toggle('lb-hidden', !multi);
    if (multi) counter.textContent = `${_lbIdx + 1} / ${_lbUrls.length}`;
  }
}

function _closeLightbox() {
  document.getElementById('lightbox').style.display = 'none';
  document.getElementById('lb-img').src = '';
  document.removeEventListener('keydown', _onLbKey);
}

function closeLightbox(e) {
  if (e && e.target !== e.currentTarget) return;
  _closeLightbox();
}

function navigateLightbox(dir) {
  _lbIdx = (_lbIdx + dir + _lbUrls.length) % _lbUrls.length;
  _updateLightbox();
}

function _onLbKey(e) {
  if      (e.key === 'Escape')      _closeLightbox();
  else if (e.key === 'ArrowLeft')   navigateLightbox(-1);
  else if (e.key === 'ArrowRight')  navigateLightbox(1);
}

/** メディア添付の HTML を生成 */
function mediaHTML(mediaList) {
  if (!mediaList || !mediaList.length) return '';

  // ライトボックス用: 画像のみの URL リストを収集
  const imageUrls = mediaList
    .filter(m => !(m.type || '').startsWith('video') && m.type !== 'gifv')
    .map(m => m.url || m.thumb)
    .filter(Boolean);

  let imgIdx = 0;
  const imgs = mediaList.map(m => {
    const isVideo = (m.type || '').startsWith('video') || m.type === 'video' || m.type === 'gifv';
    const thumb   = m.thumb || m.url;
    if (isVideo) {
      return `<a href="${esc(m.url)}" target="_blank" rel="noopener" class="tl-media-video" title="動画を開く">
                <span class="tl-media-play">▶</span>
                <img src="${esc(thumb)}" loading="lazy" alt="">
              </a>`;
    }
    // 画像: ライトボックスで開く
    const urlsAttr = JSON.stringify(imageUrls).replace(/"/g, '&quot;');
    const idx      = imgIdx++;
    return `<button class="tl-media-btn" data-urls="${urlsAttr}" data-idx="${idx}"
                    onclick="openLightbox(JSON.parse(this.dataset.urls), parseInt(this.dataset.idx))"
                    title="画像を拡大">
              <img src="${esc(thumb)}" loading="lazy" alt="" class="tl-media-img">
            </button>`;
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
