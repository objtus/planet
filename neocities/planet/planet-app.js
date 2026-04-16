/**
 * Planet ページ: data.idoko.org の JSON を fetch して描画
 * Neocities: /planet/index.html + /planet/planet-app.js をアップロード
 */
'use strict';

const PLANET_META_URL = 'https://data.idoko.org/planet-meta.json';
const PLANET_DATA_URL = 'https://data.idoko.org/planet-data.json';
const ICON_BASE = '/planet/icons/';

/** meta の favicon は拡張子付き。JSON が .webp でも Neocities に .svg だけある場合に順に試す */
const ICON_EXT_FALLBACKS = ['.svg', '.webp', '.png'];

/** 空文字: 簡素な家形インライン SVG。例: '/planet/icons/visibility-semi-public.png' でビットマップ可 */
const SEMI_VISIBILITY_ICON_URL = '';
const SEMI_VISIBILITY_TITLE =
  '公開タイムラインには出ない半公開（Misskey ホーム相当・Mastodon 未収載）';

const DAYS_JA = ['日', '月', '火', '水', '木', '金', '土'];

/** 時刻をソース URL へリンクしない src_type（ログ行の url があっても本文リンクにしない） */
const TL_TIME_PLAIN_TYPES = new Set(['health', 'photo', 'weather', 'netflix', 'prime', 'screen_time']);

let planetMeta = null;
let planetData = null;
let CAL_LATEST = new Date();
let CAL_WINDOW_DAYS = 30;
let calSelectedIso;
let calendarWeekMondays = [];
let calViewMode = 'day';
let calSelectedWeekMonday = null;
let FILTER_SOURCE_TOTAL = 0;
let listenersBound = false;

function pad2(n) {
  return String(n).padStart(2, '0');
}

function isoFromDate(d) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function startOfDay(d) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function dayCmp(a, b) {
  return startOfDay(a).getTime() - startOfDay(b).getTime();
}

function getMonday(d) {
  const x = startOfDay(d);
  const dow = (x.getDay() + 6) % 7;
  x.setDate(x.getDate() - dow);
  return x;
}

function parseIsoLocal(iso) {
  const p = iso.split('-').map(Number);
  return new Date(p[0], p[1] - 1, p[2]);
}

function applyMetaWindow(meta) {
  const p = meta.latest_date.split('-').map(Number);
  CAL_LATEST = new Date(p[0], p[1] - 1, p[2]);
  const po = meta.oldest_date.split('-').map(Number);
  const oldestD = new Date(po[0], po[1] - 1, po[2]);
  CAL_WINDOW_DAYS = Math.round((CAL_LATEST - oldestD) / 86400000) + 1;
}

function getCalLatestIso() {
  return isoFromDate(new Date(CAL_LATEST));
}

function getCalOldestIso() {
  const latest = new Date(CAL_LATEST);
  const oldest = new Date(latest);
  oldest.setDate(oldest.getDate() - (CAL_WINDOW_DAYS - 1));
  return isoFromDate(oldest);
}

function isAfterLatestDataDay(d) {
  return dayCmp(startOfDay(d), startOfDay(new Date(CAL_LATEST))) > 0;
}

function dataMetric(iso, metric) {
  const day = planetMeta.days[iso];
  if (!day) {
    if (metric === 'steps') return null;
    return 0;
  }
  switch (metric) {
    case 'posts':
      return day.posts ?? 0;
    case 'plays':
      return day.plays ?? 0;
    case 'steps':
      return day.steps ?? null;
    case 'weather':
      return day.weather?.temp_max ?? 0;
    default:
      return 0;
  }
}

function countMisskeyMastodonTimelineForDay(iso) {
  let mk = 0;
  let mast = 0;
  for (const e of planetData.timeline) {
    if (e.date !== iso) continue;
    if (e.src_type === 'misskey') mk++;
    else if (e.src_type === 'mastodon') mast++;
  }
  return { mk, mast };
}

function realWeatherCell(iso) {
  const d = parseIsoLocal(iso);
  const dowJa = DAYS_JA[d.getDay()];
  const md = `${d.getMonth() + 1}/${pad2(d.getDate())}`;
  if (isAfterLatestDataDay(d)) {
    return {
      title: 'データなし',
      dow: dowJa,
      date: md,
      icon: '🌡',
      hi: '—',
      lo: '—',
      desc: '—',
    };
  }
  const wx = planetMeta.days[iso]?.weather;
  if (!wx) {
    return { title: '', dow: dowJa, date: md, icon: '🌡', hi: '—', lo: '—', desc: '—' };
  }
  const hi = wx.temp_max != null ? `${wx.temp_max}°` : '—';
  return {
    title: wx.desc || '',
    dow: dowJa,
    date: md,
    icon: wx.icon || '🌡',
    hi,
    lo: '—',
    desc: wx.desc || '—',
  };
}

function setTimelineStatCard(cardId, val, src) {
  const card = document.getElementById(cardId);
  if (!card) return;
  const v = card.querySelector('.stat-val');
  const s = card.querySelector('.stat-src');
  if (v) v.textContent = val;
  if (s) s.textContent = src;
}

function updateTimelineStatsForDay(iso) {
  const posts = dataMetric(iso, 'posts');
  const plays = dataMetric(iso, 'plays');
  const steps = dataMetric(iso, 'steps');
  const w = planetMeta.days[iso]?.weather;
  const { mk, mast } = countMisskeyMastodonTimelineForDay(iso);
  setTimelineStatCard(
    'stat-posts',
    String(posts),
    `ヒートマップ集計。タイムライン表示: Misskey ${mk} / Mastodon ${mast}`,
  );
  setTimelineStatCard('stat-plays', String(plays), 'Last.fm');
  setTimelineStatCard(
    'stat-steps',
    steps != null ? steps.toLocaleString('ja-JP') : '—',
    'Apple Watch',
  );
  if (w && (w.desc || w.temp_max != null)) {
    const line = `${w.icon || ''} ${w.desc || ''} ${w.temp_max != null ? w.temp_max + '°' : ''}`.trim();
    setTimelineStatCard('stat-weather', line || '—', 'Nagoya');
  } else {
    setTimelineStatCard('stat-weather', '—', 'Nagoya');
  }
}

function setTimelineViewWeek(mondayIso) {
  const el = document.getElementById('timeline-view-date');
  if (!el || !mondayIso) return;
  const mon = parseIsoLocal(mondayIso);
  const sun = new Date(mon);
  sun.setDate(mon.getDate() + 6);
  const wk = isoWeekNumber(mon);
  const y = mon.getFullYear();
  const full = `${y}年 第${wk}週（${mon.getMonth() + 1}月${mon.getDate()}日〜${sun.getMonth() + 1}月${sun.getDate()}日）`;
  el.textContent = full;
  el.title = full;
  el.dataset.date = mondayIso;
  el.dataset.view = 'week';
  el.classList.add('timeline-date-value--week');
}

function isoWeekNumber(d) {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const day = (x.getDay() + 6) % 7;
  x.setDate(x.getDate() - day + 3);
  const y = new Date(x.getFullYear(), 0, 4);
  return 1 + Math.round((x - y) / 604800000);
}

function updateWeekPanel(mondayIso) {
  if (!mondayIso) return;
  setTimelineViewWeek(mondayIso);
  const mon = parseIsoLocal(mondayIso);
  let sumPosts = 0;
  let sumPlays = 0;
  let sumSteps = 0;
  const temps = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(mon);
    d.setDate(mon.getDate() + i);
    const iso = isoFromDate(d);
    sumPosts += dataMetric(iso, 'posts');
    sumPlays += dataMetric(iso, 'plays');
    const st = dataMetric(iso, 'steps');
    if (st != null) sumSteps += st;
    if (!isAfterLatestDataDay(d)) {
      const t = dataMetric(iso, 'weather');
      if (t) temps.push(Number(t));
    }
  }
  let weatherVal = '—';
  let weatherSrc = '—  Nagoya';
  if (temps.length) {
    const avgT = (temps.reduce((a, b) => a + b, 0) / temps.length).toFixed(1);
    const minT = Math.min(...temps);
    const maxT = Math.max(...temps);
    weatherVal = `平均 ${avgT}°`;
    weatherSrc = `${minT}° – ${maxT}°  Nagoya`;
  }
  let mkW = 0;
  let mastW = 0;
  for (let i = 0; i < 7; i++) {
    const d = new Date(mon);
    d.setDate(mon.getDate() + i);
    const iso = isoFromDate(d);
    const c = countMisskeyMastodonTimelineForDay(iso);
    mkW += c.mk;
    mastW += c.mast;
  }
  setTimelineStatCard(
    'stat-posts',
    String(sumPosts),
    `合計（ヒートマップ）。タイムライン: Misskey ${mkW} / Mastodon ${mastW}`,
  );
  setTimelineStatCard('stat-plays', String(sumPlays), 'Last.fm 合計');
  setTimelineStatCard('stat-steps', sumSteps.toLocaleString('ja-JP'), 'Apple Watch 合計');
  setTimelineStatCard('stat-weather', weatherVal, weatherSrc);

  const row = document.getElementById('week-weather-row');
  if (row) {
    row.innerHTML = '';
    for (let i = 0; i < 7; i++) {
      const d = new Date(mon);
      d.setDate(mon.getDate() + i);
      const iso = isoFromDate(d);
      const wx = realWeatherCell(iso);
      const cell = document.createElement('div');
      cell.className = 'ww-cell';
      cell.title = wx.title || wx.desc;
      cell.innerHTML =
        `<div class="ww-dow">${wx.dow}</div>` +
        `<div class="ww-date">${wx.date}</div>` +
        `<div class="ww-icon" aria-hidden="true">${wx.icon}</div>` +
        `<div class="ww-temp">${wx.hi} / ${wx.lo}</div>` +
        `<div class="ww-desc">${wx.desc}</div>`;
      row.appendChild(cell);
    }
  }
}

function setWeekPanelVisible(show) {
  const panel = document.getElementById('week-view-panel');
  if (!panel) return;
  panel.classList.toggle('is-hidden', !show);
}

function heatLevel(val, arr, metric) {
  if (metric !== 'weather' && val === 0) return 0;
  const vmin = Math.min(...arr);
  const vmax = Math.max(...arr);
  if (vmin === vmax) return metric !== 'weather' && val === 0 ? 0 : 3;
  const t = (val - vmin) / (vmax - vmin);
  const lv = Math.ceil(t * 5);
  return Math.max(1, Math.min(5, lv === 0 ? 1 : lv));
}

function formatMetricTitle(iso, val, metric) {
  if (metric === 'steps') return `${iso}  ${val.toLocaleString('ja-JP')}歩`;
  if (metric === 'weather') return `${iso}  最高 ${val}°C`;
  const u = metric === 'posts' ? '件' : '曲';
  return `${iso}  ${val}${u}`;
}

function buildCalendarHeat() {
  const body = document.getElementById('cal-body');
  const titleEl = document.getElementById('cal-month-title');
  const metricEl = document.getElementById('heat-metric');
  if (!body || !titleEl || !metricEl || !planetMeta) return;

  const latest = new Date(CAL_LATEST);
  const oldest = new Date(latest);
  oldest.setDate(oldest.getDate() - (CAL_WINDOW_DAYS - 1));
  const metric = metricEl.value;

  titleEl.textContent =
    `直近${CAL_WINDOW_DAYS}日（${oldest.getMonth() + 1}/${oldest.getDate()}〜${latest.getMonth() + 1}/${latest.getDate()}）· 最新 ${latest.getFullYear()}-${pad2(latest.getMonth() + 1)}-${pad2(latest.getDate())}`;

  const inWindowDates = [];
  const iter = new Date(oldest);
  while (dayCmp(iter, latest) <= 0) {
    inWindowDates.push(isoFromDate(new Date(iter)));
    iter.setDate(iter.getDate() + 1);
  }

  const valuesInWindow = inWindowDates.map((iso) => {
    const v = dataMetric(iso, metric);
    return v == null ? 0 : v;
  });

  if (!calSelectedIso || !inWindowDates.includes(calSelectedIso)) {
    calSelectedIso = isoFromDate(latest);
  }

  const topMonday = getMonday(oldest);
  const bottomMonday = getMonday(latest);
  body.setAttribute('aria-busy', 'true');
  body.innerHTML = '';
  calendarWeekMondays = [];

  if (calSelectedWeekMonday === null) {
    calSelectedWeekMonday = isoFromDate(bottomMonday);
  }

  const cur = new Date(topMonday);
  while (dayCmp(cur, bottomMonday) <= 0) {
    const monIso = isoFromDate(new Date(cur));
    calendarWeekMondays.push(monIso);
    const tr = document.createElement('tr');
    const wnTd = document.createElement('td');
    wnTd.className = 'wn-cell';
    const wnBtn = document.createElement('button');
    wnBtn.type = 'button';
    wnBtn.className = 'wn-btn';
    const wk = isoWeekNumber(cur);
    wnBtn.textContent = `W${wk}`;
    wnBtn.title = `${cur.getFullYear()}年 第${wk}週を表示`;
    wnBtn.dataset.weekStart = monIso;
    wnBtn.classList.toggle('selected', calViewMode === 'week' && calSelectedWeekMonday === monIso);
    wnBtn.addEventListener('click', function () {
      calViewMode = 'week';
      calSelectedWeekMonday = this.dataset.weekStart;
      setWeekPanelVisible(true);
      updateWeekPanel(calSelectedWeekMonday);
      renderTimeline();
      buildCalendarHeat();
    });
    wnTd.appendChild(wnBtn);
    tr.appendChild(wnTd);
    tr.classList.toggle('cal-week-selected', calViewMode === 'week' && calSelectedWeekMonday === monIso);

    const rowStart = new Date(cur);
    for (let i = 0; i < 7; i++) {
      const d = new Date(rowStart);
      d.setDate(rowStart.getDate() + i);
      const iso = isoFromDate(d);
      const inWindow = dayCmp(d, oldest) >= 0 && dayCmp(d, latest) <= 0;
      const isLatestDay =
        d.getFullYear() === latest.getFullYear() &&
        d.getMonth() === latest.getMonth() &&
        d.getDate() === latest.getDate();
      const td = document.createElement('td');
      const div = document.createElement('div');
      div.className = 'day';
      div.textContent = String(d.getDate());
      if (inWindow) {
        const raw = dataMetric(iso, metric);
        const val = raw == null ? 0 : raw;
        const lv = heatLevel(val, valuesInWindow, metric);
        div.classList.add(`h${lv}`);
        div.dataset.date = iso;
        div.title = formatMetricTitle(iso, val, metric);
        if (calViewMode === 'day' && iso === calSelectedIso) div.classList.add('selected');
        if (isLatestDay) div.classList.add('today');
        const isoClick = iso;
        div.addEventListener('click', function () {
          calSelectedIso = isoClick;
          calViewMode = 'day';
          calSelectedWeekMonday = isoFromDate(getMonday(parseIsoLocal(isoClick)));
          setWeekPanelVisible(false);
          updateTimelineStatsForDay(isoClick);
          renderTimeline();
          const p = isoClick.split('-').map(Number);
          setTimelineViewDate(new Date(p[0], p[1] - 1, p[2]));
          buildCalendarHeat();
        });
      } else {
        div.classList.add('h0', 'out-of-range');
        if (dayCmp(d, latest) > 0) {
          div.title = `${iso}（最新日より後·閲覧外）`;
        } else {
          div.title = `${iso}（直近${CAL_WINDOW_DAYS}日より前·閲覧外）`;
        }
      }
      td.appendChild(div);
      tr.appendChild(td);
    }
    cur.setDate(cur.getDate() + 7);
    body.appendChild(tr);
  }

  if (calendarWeekMondays.length && calSelectedWeekMonday && !calendarWeekMondays.includes(calSelectedWeekMonday)) {
    calSelectedWeekMonday = calendarWeekMondays[calendarWeekMondays.length - 1];
  }
  if (calViewMode === 'week' && calSelectedWeekMonday) {
    updateWeekPanel(calSelectedWeekMonday);
    setWeekPanelVisible(true);
    renderTimeline();
  } else {
    setWeekPanelVisible(false);
    updateTimelineStatsForDay(calSelectedIso);
    renderTimeline();
    const p = calSelectedIso.split('-').map(Number);
    setTimelineViewDate(new Date(p[0], p[1] - 1, p[2]));
  }
  updateTimelineNavButtons();
  body.setAttribute('aria-busy', 'false');
  requestAnimationFrame(function () {
    const wrap = body.closest('.cal-scroll');
    if (wrap) wrap.scrollTop = wrap.scrollHeight;
  });
}

function goCalLatest() {
  calSelectedIso = isoFromDate(new Date(CAL_LATEST));
  calViewMode = 'day';
  calSelectedWeekMonday = isoFromDate(getMonday(new Date(CAL_LATEST)));
  setWeekPanelVisible(false);
  setTimelineViewDate(new Date(CAL_LATEST));
  updateTimelineStatsForDay(calSelectedIso);
  renderTimeline();
  buildCalendarHeat();
}

function syncViewDateFromCal() {
  if (calViewMode === 'week' && calSelectedWeekMonday) {
    updateWeekPanel(calSelectedWeekMonday);
    renderTimeline();
    return;
  }
  if (!calSelectedIso) {
    setTimelineViewDate(new Date(CAL_LATEST));
    updateTimelineStatsForDay(isoFromDate(new Date(CAL_LATEST)));
    renderTimeline();
    return;
  }
  const p = calSelectedIso.split('-').map(Number);
  setTimelineViewDate(new Date(p[0], p[1] - 1, p[2]));
  updateTimelineStatsForDay(calSelectedIso);
  renderTimeline();
}

function formatTimelineViewDate(d) {
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}（${DAYS_JA[d.getDay()]}）`;
}

function setTimelineViewDate(date) {
  const el = document.getElementById('timeline-view-date');
  if (!el) return;
  const d = date instanceof Date ? date : new Date();
  const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  el.dataset.date = iso;
  el.dataset.view = 'day';
  el.textContent = formatTimelineViewDate(d);
  el.classList.remove('timeline-date-value--week');
  el.removeAttribute('title');
}

function updateTimelineNavButtons() {
  const prev = document.getElementById('timeline-nav-prev');
  const next = document.getElementById('timeline-nav-next');
  const todayBtn = document.getElementById('timeline-nav-today');
  const latest = getCalLatestIso();
  const curIso = calSelectedIso || latest;
  const onLatestDay = calViewMode === 'day' && curIso === latest;
  if (todayBtn) {
    todayBtn.disabled = onLatestDay;
    todayBtn.title = onLatestDay ? 'すでに最新日を表示中' : '最新日のビューへ';
    todayBtn.setAttribute('aria-label', todayBtn.title);
  }
  if (!prev || !next) return;
  if (calViewMode === 'week' && calSelectedWeekMonday && calendarWeekMondays.length) {
    const idx = calendarWeekMondays.indexOf(calSelectedWeekMonday);
    prev.disabled = idx <= 0;
    next.disabled = idx < 0 || idx >= calendarWeekMondays.length - 1;
    prev.title = '前の週';
    next.title = '次の週';
    prev.setAttribute('aria-label', '前の週');
    next.setAttribute('aria-label', '次の週');
    return;
  }
  const oldest = getCalOldestIso();
  const iso = curIso;
  prev.disabled = iso <= oldest;
  next.disabled = iso >= latest;
  prev.title = '前の日';
  next.title = '次の日';
  prev.setAttribute('aria-label', '前の日');
  next.setAttribute('aria-label', '次の日');
}

function shiftTimelineView(delta) {
  if (calViewMode === 'week' && calSelectedWeekMonday && calendarWeekMondays.length) {
    const idx = calendarWeekMondays.indexOf(calSelectedWeekMonday);
    if (idx < 0) return;
    const ni = idx + delta;
    if (ni < 0 || ni >= calendarWeekMondays.length) return;
    calSelectedWeekMonday = calendarWeekMondays[ni];
    updateWeekPanel(calSelectedWeekMonday);
    renderTimeline();
    buildCalendarHeat();
    return;
  }
  const curIso = calSelectedIso || getCalLatestIso();
  const d = parseIsoLocal(curIso);
  d.setDate(d.getDate() + delta);
  const iso = isoFromDate(d);
  const oldest = getCalOldestIso();
  const latest = getCalLatestIso();
  if (iso < oldest || iso > latest) return;
  calSelectedIso = iso;
  calViewMode = 'day';
  calSelectedWeekMonday = isoFromDate(getMonday(d));
  setWeekPanelVisible(false);
  setTimelineViewDate(d);
  updateTimelineStatsForDay(iso);
  renderTimeline();
  buildCalendarHeat();
}

function updateFilterCount() {
  const el = document.getElementById('filter-count');
  if (!el) return;
  const n = document.querySelectorAll('#filter-source-row .ftag.on').length;
  el.textContent = n === FILTER_SOURCE_TOTAL ? `全${FILTER_SOURCE_TOTAL}` : `${n}/${FILTER_SOURCE_TOTAL}`;
}

function toggleFilter(btn) {
  btn.classList.toggle('on');
  applyFilter();
}

function filterToSingleSourceFromBadge(btn) {
  const item = btn.closest('.tl-item');
  if (!item || item.dataset.src === undefined) return;
  const id = String(item.dataset.src);
  const onFtags = [...document.querySelectorAll('#filter-source-row .ftag.on')];
  const onlyThisSource = onFtags.length === 1 && String(onFtags[0].dataset.src) === id;
  if (onlyThisSource) {
    filterAll();
    return;
  }
  filterToSingleSource(id);
}

function filterToSingleSource(src) {
  const id = String(src);
  document.querySelectorAll('#filter-source-row .ftag').forEach((b) => {
    b.classList.toggle('on', b.dataset.src === id);
  });
  const mediaBtn = document.getElementById('media-filter-btn');
  if (mediaBtn) mediaBtn.classList.remove('on');
  applyFilter();
}

function toggleMediaFilter(btn) {
  btn.classList.toggle('on');
  applyFilter();
}

function filterAll() {
  document.querySelectorAll('#filter-source-row .ftag').forEach((b) => b.classList.add('on'));
  applyFilter();
}

function applyFilter() {
  updateFilterCount();
  const active = new Set(
    [...document.querySelectorAll('#filter-source-row .ftag.on')].map((b) => String(b.dataset.src ?? '')),
  );
  const mediaOnly = document.getElementById('media-filter-btn')?.classList.contains('on');
  document.querySelectorAll('#timeline .tl-item').forEach((item) => {
    const sid = String(item.dataset.src ?? '');
    let show = active.has(sid);
    if (show && mediaOnly) show = item.getAttribute('data-has-media') === 'true';
    item.classList.toggle('hidden', !show);
  });
  document.querySelectorAll('#timeline .tl-run').forEach((run) => {
    const items = run.querySelectorAll('.tl-item');
    const visCount = [...items].filter((it) => !it.classList.contains('hidden')).length;
    run.classList.toggle('hidden', visCount === 0);
    const sum = run.querySelector('.tl-run-summary-row');
    const extras = run.querySelector('.tl-run-extras');
    if (sum && extras) {
      if (visCount <= 1) {
        sum.classList.add('hidden');
        extras.hidden = true;
      } else {
        sum.classList.remove('hidden');
      }
    }
  });
  let visible = 0;
  document.querySelectorAll('#timeline .tl-item').forEach((item) => {
    if (item.classList.contains('hidden')) return;
    if (item.closest('.tl-run.hidden')) return;
    visible++;
  });
  const noEl = document.getElementById('no-items');
  if (noEl) noEl.style.display = visible === 0 ? 'block' : 'none';
}

function ftagClass(st) {
  if (st === 'misskey') return 'f-msk';
  if (st === 'mastodon') return 'f-mst';
  if (st === 'lastfm') return 'f-lfm';
  if (st === 'health' || st === 'photo' || st === 'screen_time') return 'f-hlth';
  return 'f-rss';
}

/** @returns {string[]} 先頭は meta のファイル名そのまま、続けて同一ベース名の別拡張子 */
function faviconUrlCandidates(favicon) {
  const name = String(favicon || '').trim();
  if (!name) return [];
  const dot = name.lastIndexOf('.');
  const base = dot > 0 ? name.slice(0, dot) : name;
  const ext = dot > 0 ? name.slice(dot).toLowerCase() : '';
  const out = [];
  const seen = new Set();
  function add(n) {
    const k = n.toLowerCase();
    if (!seen.has(k)) {
      seen.add(k);
      out.push(n);
    }
  }
  add(name);
  for (const e of ICON_EXT_FALLBACKS) {
    if (e !== ext) add(base + e);
  }
  return out;
}

/** 404 時に次の拡張子へ。すべて失敗したら onExhausted */
function bindIconSrcWithFallback(img, favicon, onExhausted) {
  const cands = faviconUrlCandidates(favicon);
  if (cands.length === 0) {
    onExhausted();
    return;
  }
  let i = 0;
  function onError() {
    i += 1;
    if (i >= cands.length) {
      img.removeEventListener('error', onError);
      onExhausted();
      return;
    }
    img.src = ICON_BASE + cands[i];
  }
  img.addEventListener('error', onError);
  img.src = ICON_BASE + cands[0];
}

function emojiForType(st) {
  const m = {
    misskey: '🍣',
    mastodon: '🐘',
    lastfm: '🎵',
    rss: '🌐',
    github: '🐱',
    youtube: '▶️',
    weather: '☁️',
    health: '🍎',
    photo: '📷',
    scrapbox: '📓',
    netflix: '🎬',
    prime: '📺',
    screen_time: '📱',
  };
  return m[st] || '🌐';
}

/**
 * planet-meta sources[] の表示（build_feed + settings の上書き）
 * - icon_emoji: 画像なし、この文字のみ
 * - icon_url: 絶対 URL を img に（ICON_BASE なし）
 * - favicon: /planet/icons/ 下のファイル名（拡張子フォールバックあり）
 */
function appendSourceIcon(container, s, opts) {
  const size = opts.size || 16;
  const filterRow = !!opts.filterRow;
  const typeFallback = emojiForType(s.type);
  const em = document.createElement('span');
  em.className = 'ficon';

  if (s.icon_emoji) {
    em.textContent = s.icon_emoji;
    em.hidden = false;
    container.appendChild(em);
    return;
  }

  em.textContent = typeFallback;
  if (filterRow) em.hidden = true;
  else em.style.display = 'none';

  if (s.icon_url) {
    const img = document.createElement('img');
    img.className = 'src-icon';
    img.width = size;
    img.height = size;
    img.alt = '';
    if (opts.lazy) img.loading = 'lazy';
    img.src = s.icon_url;
    img.addEventListener('error', function () {
      img.style.display = 'none';
      if (filterRow) em.hidden = false;
      else em.style.display = 'inline';
    });
    container.appendChild(img);
    container.appendChild(em);
    return;
  }

  if (s.favicon) {
    const img = document.createElement('img');
    img.className = 'src-icon';
    img.width = size;
    img.height = size;
    img.alt = '';
    if (opts.lazy) img.loading = 'lazy';
    bindIconSrcWithFallback(img, s.favicon, function () {
      img.style.display = 'none';
      if (filterRow) em.hidden = false;
      else em.style.display = 'inline';
    });
    container.appendChild(img);
    container.appendChild(em);
    return;
  }

  em.hidden = false;
  if (!filterRow) em.style.display = 'inline';
  container.appendChild(em);
}

function buildFilterButtons() {
  const row = document.getElementById('filter-source-row');
  if (!row || !planetMeta) return;
  row.innerHTML = '';
  FILTER_SOURCE_TOTAL = planetMeta.sources.length;
  for (const s of planetMeta.sources) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `ftag ${ftagClass(s.type)} on`;
    btn.dataset.src = String(s.id);
    btn.title = s.name;
    appendSourceIcon(btn, s, { size: 16, filterRow: true, lazy: true });
    btn.appendChild(document.createTextNode(s.short_name));
    btn.addEventListener('click', function () {
      toggleFilter(this);
    });
    row.appendChild(btn);
  }
}

function entrySortKey(e) {
  return e.date + 'T' + (e.time || '00:00');
}

function formatHm(t) {
  const s = t || '00:00';
  return s.length >= 5 ? s.slice(0, 5) : s;
}

function isSemiPublicVisibility(v) {
  return v === 'home' || v === 'unlisted';
}

/** Luminous 用: 画像 URL っぽいものだけ（動画・gifv は除外） */
function mediaItemIsImageForLightbox(m) {
  if (!m || typeof m !== 'object') return false;
  const t = String(m.type || '').toLowerCase();
  if (t.startsWith('video/') || t === 'gifv') return false;
  if (t.startsWith('image/')) return true;
  const path = String(m.url || m.thumb || '')
    .split('?')[0]
    .toLowerCase();
  return /\.(jpe?g|png|gif|webp|bmp|avif|svg)$/.test(path);
}

function appendTimelineMediaThumbs(content, entry) {
  const list = entry.media;
  if (!Array.isArray(list) || list.length === 0) return;
  const row = document.createElement('div');
  row.className = 'tl-media-row';
  for (const m of list) {
    if (!mediaItemIsImageForLightbox(m)) continue;
    const href = m.url;
    const src = m.thumb || m.url;
    if (!href || !src) continue;
    const a = document.createElement('a');
    a.className = 'planet-tl-lb';
    a.href = href;
    const img = document.createElement('img');
    img.src = src;
    img.alt = '';
    img.loading = 'lazy';
    img.decoding = 'async';
    img.className = 'tl-media-thumb';
    a.appendChild(img);
    row.appendChild(a);
  }
  if (row.childElementCount > 0) content.appendChild(row);
}

/** タイムライン再描画のたびに Luminous を付け直す（動的 DOM 用） */
function initTimelineLightbox() {
  if (typeof LuminousGallery === 'undefined') return;
  const nodes = document.querySelectorAll('#timeline a.planet-tl-lb');
  if (nodes.length === 0) return;
  try {
    new LuminousGallery(nodes);
  } catch (err) {
    console.warn('LuminousGallery init failed', err);
  }
}

/** 半公開（home / unlisted）用の目印。SEMI_VISIBILITY_ICON_URL があれば img、なければ SVG */
function createSemiVisibilityMark() {
  const wrap = document.createElement('span');
  wrap.className = 'tl-vis-semi';
  wrap.title = SEMI_VISIBILITY_TITLE;
  wrap.setAttribute('aria-label', SEMI_VISIBILITY_TITLE);
  if (SEMI_VISIBILITY_ICON_URL) {
    const img = document.createElement('img');
    img.className = 'tl-vis-semi__img';
    img.src = SEMI_VISIBILITY_ICON_URL;
    img.alt = '';
    img.width = 12;
    img.height = 12;
    img.decoding = 'async';
    wrap.appendChild(img);
  } else {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'tl-vis-semi__svg');
    svg.setAttribute('viewBox', '0 0 16 16');
    svg.setAttribute('width', '12');
    svg.setAttribute('height', '12');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    const p1 = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    p1.setAttribute(
      'd',
      'M2 14V7.5L8 2l6 5.5V14H2z'
    );
    p1.setAttribute('fill', 'none');
    p1.setAttribute('stroke', 'currentColor');
    p1.setAttribute('stroke-width', '1.25');
    p1.setAttribute('stroke-linecap', 'round');
    p1.setAttribute('stroke-linejoin', 'round');
    const p2 = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    p2.setAttribute('d', 'M6 14V10h4v4');
    p2.setAttribute('fill', 'none');
    p2.setAttribute('stroke', 'currentColor');
    p2.setAttribute('stroke-width', '1.25');
    p2.setAttribute('stroke-linecap', 'round');
    p2.setAttribute('stroke-linejoin', 'round');
    svg.appendChild(p1);
    svg.appendChild(p2);
    wrap.appendChild(svg);
  }
  return wrap;
}

/** 畳んだブロックの時刻範囲（同日は HH:mm–HH:mm、跨ぎは M/D HH:mm–M/D HH:mm） */
function formatCollapseTimeRange(oldest, newest) {
  const od = oldest.date;
  const nd = newest.date;
  const ot = formatHm(oldest.time);
  const nt = formatHm(newest.time);
  if (od === nd) {
    return `${ot}\u2013${nt}`;
  }
  const po = od.split('-').map(Number);
  const pn = nd.split('-').map(Number);
  return `${po[1]}/${po[2]} ${ot}\u2013${pn[1]}/${pn[2]} ${nt}`;
}

function getTimelineCollapseConfig() {
  const tc = planetMeta && planetMeta.timeline_collapse;
  if (!tc || !Array.isArray(tc.types) || tc.types.length === 0) return null;
  const types = new Set(tc.types.map((t) => String(t).trim()).filter(Boolean));
  let minRun = parseInt(String(tc.min_run), 10);
  if (Number.isNaN(minRun) || minRun < 2) minRun = 3;
  return { types, minRun };
}

function partitionTimelineRuns(entries, cfg) {
  if (!cfg) return entries.map((e) => ({ kind: 'one', entries: [e] }));
  const { types, minRun } = cfg;
  const out = [];
  let i = 0;
  while (i < entries.length) {
    const e = entries[i];
    const st = e.src_type || '';
    if (!types.has(st)) {
      out.push({ kind: 'one', entries: [e] });
      i++;
      continue;
    }
    let j = i + 1;
    while (j < entries.length) {
      const next = entries[j];
      if ((next.src_type || '') !== st || !types.has(next.src_type || '')) break;
      j++;
    }
    const run = entries.slice(i, j);
    if (run.length >= minRun) out.push({ kind: 'collapsed', entries: run });
    else for (const x of run) out.push({ kind: 'one', entries: [x] });
    i = j;
  }
  return out;
}

function createTlItem(e, srcMap) {
  const div = document.createElement('div');
  div.className = 'tl-item';
  div.dataset.src = String(e.src_id);
  div.dataset.srcType = e.src_type || '';
  if (e.has_media) div.setAttribute('data-has-media', 'true');
  const useLink = e.url && !TL_TIME_PLAIN_TYPES.has(e.src_type);
  const timeEl = document.createElement(useLink ? 'a' : 'span');
  timeEl.className = 'tl-time';
  if (useLink) {
    timeEl.href = e.url;
    timeEl.target = '_blank';
    timeEl.rel = 'noopener noreferrer';
    timeEl.title = '投稿を開く';
  }
  timeEl.textContent = e.time || '';
  const badge = document.createElement('button');
  badge.type = 'button';
  badge.className = 'tl-badge tl-badge--filter';
  badge.title = 'ソースで絞り込み（もう一度クリックで解除）';
  badge.addEventListener('click', function () {
    filterToSingleSourceFromBadge(this);
  });
  const sinfo = srcMap[String(e.src_id)];
  if (sinfo) {
    appendSourceIcon(badge, sinfo, { size: 12, filterRow: false, lazy: false });
  } else {
    const em = document.createElement('span');
    em.className = 'ficon';
    em.textContent = '·';
    badge.appendChild(em);
  }
  const content = document.createElement('div');
  content.className = 'tl-content';
  const text = document.createElement('div');
  text.className = 'tl-text';
  text.textContent = e.text || '';
  content.appendChild(text);
  appendTimelineMediaThumbs(content, e);
  div.appendChild(timeEl);
  div.appendChild(badge);
  div.appendChild(content);
  if (isSemiPublicVisibility(e.visibility)) {
    const vis = createSemiVisibilityMark();
    vis.classList.add('tl-vis-semi--end');
    div.appendChild(vis);
  }
  return div;
}

function appendCollapsedRun(tl, run, srcMap) {
  const wrap = document.createElement('div');
  wrap.className = 'tl-run';
  wrap.appendChild(createTlItem(run[0], srcMap));
  const summaryRow = document.createElement('div');
  summaryRow.className = 'tl-run-summary-row';
  const gutter = document.createElement('span');
  gutter.className = 'tl-run-gutter';
  gutter.setAttribute('aria-hidden', 'true');
  const body = document.createElement('div');
  body.className = 'tl-run-summary-body';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'tl-run-toggle';
  const extras = document.createElement('div');
  extras.className = 'tl-run-extras';
  extras.hidden = true;
  const nHidden = run.length - 1;
  const oldest = run[run.length - 1];
  const newest = run[0];
  const range = formatCollapseTimeRange(oldest, newest);
  const sid0 = String(run[0].src_id);
  const label = (srcMap[sid0] && srcMap[sid0].short_name) || run[0].src_type || 'source';
  function paintCollapsedState(collapsed) {
    btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    extras.hidden = collapsed;
    if (collapsed) {
      btn.textContent = `ほか ${label} ${nHidden}件（${range}） 展開`;
    } else {
      btn.textContent = '折りたたむ';
    }
  }
  paintCollapsedState(true);
  btn.addEventListener('click', function () {
    paintCollapsedState(!extras.hidden);
  });
  for (let k = 1; k < run.length; k++) {
    extras.appendChild(createTlItem(run[k], srcMap));
  }
  body.appendChild(btn);
  summaryRow.appendChild(gutter);
  summaryRow.appendChild(body);
  wrap.appendChild(summaryRow);
  wrap.appendChild(extras);
  tl.appendChild(wrap);
}

function timelineEntriesForCurrentView() {
  if (calViewMode === 'week' && calSelectedWeekMonday) {
    const mon = parseIsoLocal(calSelectedWeekMonday);
    const dates = new Set();
    for (let i = 0; i < 7; i++) {
      const d = new Date(mon);
      d.setDate(mon.getDate() + i);
      dates.add(isoFromDate(d));
    }
    return planetData.timeline.filter((e) => dates.has(e.date));
  }
  const iso = calSelectedIso || getCalLatestIso();
  return planetData.timeline.filter((e) => e.date === iso);
}

function renderTimeline() {
  const tl = document.getElementById('timeline');
  if (!tl || !planetData) return;
  tl.innerHTML = '';
  const entries = timelineEntriesForCurrentView().sort((a, b) => entrySortKey(b).localeCompare(entrySortKey(a)));
  const srcMap = Object.fromEntries(planetMeta.sources.map((s) => [String(s.id), s]));
  const cfg = getTimelineCollapseConfig();
  const blocks = partitionTimelineRuns(entries, cfg);
  for (const block of blocks) {
    if (block.kind === 'one') {
      tl.appendChild(createTlItem(block.entries[0], srcMap));
    } else {
      appendCollapsedRun(tl, block.entries, srcMap);
    }
  }
  applyFilter();
  initTimelineLightbox();
}

async function loadPlanetData() {
  const [mr, dr] = await Promise.all([fetch(PLANET_META_URL), fetch(PLANET_DATA_URL)]);
  if (!mr.ok) throw new Error(`meta ${mr.status}`);
  if (!dr.ok) throw new Error(`data ${dr.status}`);
  planetMeta = await mr.json();
  planetData = await dr.json();
}

function bindStaticListeners() {
  if (listenersBound) return;
  listenersBound = true;
  document.getElementById('heat-metric')?.addEventListener('change', function () {
    const m = this.value;
    const card = document.getElementById('cal-card');
    if (card) {
      card.dataset.metric = m;
      card.className = 'card cal-card cal-heat-' + m;
    }
    const axis = document.getElementById('heat-legend-axis');
    if (axis) axis.textContent = m === 'weather' ? '低 → 高' : '少 → 多';
    buildCalendarHeat();
  });
  document.getElementById('cal-btn-latest')?.addEventListener('click', goCalLatest);
  document.getElementById('filter-toggle')?.addEventListener('click', function () {
    const row = document.getElementById('filter-source-row');
    const arrow = document.getElementById('filter-arrow');
    const toggleBtn = document.getElementById('filter-toggle');
    if (!row || !arrow || !toggleBtn) return;
    row.classList.toggle('filter-source-row--collapsed');
    const collapsed = row.classList.contains('filter-source-row--collapsed');
    arrow.textContent = collapsed ? '▾' : '▴';
    toggleBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
  });
  document.getElementById('timeline-nav-prev')?.addEventListener('click', function () {
    shiftTimelineView(-1);
  });
  document.getElementById('timeline-nav-next')?.addEventListener('click', function () {
    shiftTimelineView(1);
  });
  document.getElementById('timeline-nav-today')?.addEventListener('click', goCalLatest);
}

async function initPlanet() {
  const err = document.getElementById('planet-load-error');
  bindStaticListeners();
  try {
    await loadPlanetData();
    if (err) {
      err.hidden = true;
      err.textContent = '';
    }
    applyMetaWindow(planetMeta);
    const dm = document.getElementById('detail-meta');
    if (dm) dm.textContent = '// generated_at ' + (planetMeta.generated_at || '');
    buildFilterButtons();
    calSelectedIso = getCalLatestIso();
    calViewMode = 'day';
    calSelectedWeekMonday = null;
    setWeekPanelVisible(false);
    buildCalendarHeat();
    syncViewDateFromCal();
  } catch (e) {
    if (err) {
      err.hidden = false;
      err.textContent =
        'データを読み込めませんでした（' +
        (e.message || e) +
        '）。しばらくしてから再読み込みしてください。';
    }
  }
}

document.addEventListener('DOMContentLoaded', initPlanet);
