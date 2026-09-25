(() => {
  'use strict';

  const catalog = window.DF.load();
  const params = new URLSearchParams(window.location.search);
  const requested = params.get('id');
  const item = catalog.news.find(news => news.id === requested) || catalog.news.find(news => news.featured) || catalog.news[0];
  const $ = selector => document.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHTML = value => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');

  function setupTheme() {
    const html = document.documentElement;
    const saved = localStorage.getItem('df-theme');
    if (saved === 'light' || saved === 'dark') html.dataset.theme = saved;
    $('#theme-toggle')?.addEventListener('click', () => {
      const next = html.dataset.theme === 'light' ? 'dark' : 'light';
      html.dataset.theme = next;
      localStorage.setItem('df-theme', next);
    });
  }

  function setupHeader() {
    $$('[data-page-link="news"]').forEach(link => {
      link.classList.add('current');
      link.setAttribute('aria-current', 'page');
    });
    const menu = $('#main-nav');
    const toggle = $('#menu-toggle');
    if (menu && toggle) {
      toggle.addEventListener('click', () => {
        const open = menu.classList.toggle('open');
        toggle.setAttribute('aria-expanded', String(open));
      });
      $$('a', menu).forEach(link => link.addEventListener('click', () => { menu.classList.remove('open'); toggle.setAttribute('aria-expanded', 'false'); }));
    }
    $$('[data-zalo-phone]').forEach(node => { node.textContent = catalog.settings.zalo || '0394781498'; });
    $('#year').textContent = new Date().getFullYear();
  }

  function renderDetail() {
    const empty = $('#news-detail-empty');
    if (!item) { if (empty) empty.hidden = false; return; }
    $('#news-detail-empty')?.setAttribute('hidden', '');
    const set = (selector, value) => { const node = $(selector); if (node) node.textContent = value; };
    set('#news-detail-category', item.category || 'TIN TỨC');
    set('#news-detail-date', item.date || '');
    set('#news-detail-title', item.title);
    set('#news-detail-summary', item.summary || '');
    const image = $('#news-detail-image');
    if (image) { image.src = item.image || ''; image.alt = item.title; }
    const content = $('#news-detail-content');
    if (content) content.innerHTML = String(item.content || item.summary || '').split(/\n\n+/).filter(Boolean).map(paragraph => `<p>${escapeHTML(paragraph)}</p>`).join('');
    const related = $('#related-news');
    if (related) related.innerHTML = catalog.news.filter(news => news.id !== item.id).slice(0, 3).map(news => `<a class="df-news-related" href="tin-tuc.html?id=${encodeURIComponent(news.id)}"><span>${escapeHTML(news.date || '')}</span><strong>${escapeHTML(news.title)}</strong><em>Xem chi tiết ↗</em></a>`).join('');
  }

  renderDetail();
})();
