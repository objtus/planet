/**
 * サマリー用 Markdown → 安全な HTML（marked + DOMPurify）。
 * 依存: 先に purify.min.js と marked.min.js を読み込むこと。
 */
(function () {
  'use strict';

  /**
   * @param {string} md
   * @returns {HTMLElement}
   */
  function renderSummaryMarkdown(md) {
    const text = md == null ? '' : String(md);
    const wrap = document.createElement('div');
    wrap.className = 'summary-md';

    if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
      const pre = document.createElement('pre');
      pre.className = 'summary-panel-text summary-md-fallback';
      pre.textContent = text;
      return pre;
    }

    try {
      const raw = marked.parse(text, { async: false });
      wrap.innerHTML = DOMPurify.sanitize(raw, { USE_PROFILES: { html: true } });
    } catch (err) {
      wrap.textContent = text;
    }
    return wrap;
  }

  window.renderSummaryMarkdown = renderSummaryMarkdown;

  function initSummariesPage() {
    document.querySelectorAll('.summary-item').forEach((item) => {
      const raw = item.querySelector('.summary-md-raw');
      const out = item.querySelector('.summary-md-rendered');
      if (!raw || !out) return;
      out.replaceChildren(renderSummaryMarkdown(raw.textContent));
      raw.remove();
    });
  }

  window.initSummariesPageMarkdown = initSummariesPage;
})();
