(() => {
  'use strict';

  const state = {
    catalog: window.DF.load(),
    page: document.body.dataset.page || 'home',
    accountCategory: 'all',
    accountPage: 1,
    servicePage: 1,
    newsCategory: 'all',
    product: null
  };
  let headerReady = false;
  const PAGE_SIZE = 15;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHTML = value => String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');

  function imageMarkup(url, alt, fallback) {
    const source = String(url || '').trim();
    const fallbackText = String(fallback || '').trim();
    return `<img src="${escapeHTML(source)}" alt="${escapeHTML(alt)}" loading="lazy">${fallbackText ? `<span class="df-product-fallback" hidden>${escapeHTML(fallbackText)}</span>` : ''}`;
  }

  function newsImageMarkup(item) {
    return `<img src="${escapeHTML(item.image || '')}" alt="${escapeHTML(item.title)}" loading="lazy"><span class="df-news-image-fallback" hidden aria-hidden="true"></span>`;
  }

  function hydrateImages(root = document) {
    $$('img', root).forEach(image => {
      if (image.dataset.fallbackBound) return;
      const fallback = image.nextElementSibling;
      if (!fallback?.matches('.df-product-fallback, .df-news-image-fallback')) return;
      image.dataset.fallbackBound = '1';
      const setImageState = loaded => {
        image.hidden = !loaded;
        fallback.hidden = loaded;
      };
      image.addEventListener('error', () => setImageState(false));
      image.addEventListener('load', () => setImageState(true));
      // Cached images can finish loading before these listeners are attached.
      if (image.complete) setImageState(image.naturalWidth > 0);
    });
  }

  function openDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.showModal === 'function') {
      if (!dialog.open) dialog.showModal();
    } else {
      dialog.setAttribute('open', '');
    }
  }

  function closeDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.close === 'function') dialog.close();
    else dialog.removeAttribute('open');
  }

  function setupTheme() {
    const html = document.documentElement;
    const saved = localStorage.getItem('df-theme');
    if (saved === 'light' || saved === 'dark') html.dataset.theme = saved;
    const button = $('#theme-toggle');
    if (!button) return;
    button.addEventListener('click', () => {
      const next = html.dataset.theme === 'light' ? 'dark' : 'light';
      html.dataset.theme = next;
      localStorage.setItem('df-theme', next);
    });
  }

  function setupHeader() {
    const page = state.page;
    $$('[data-page-link]').forEach(link => {
      link.classList.toggle('current', link.dataset.pageLink === page);
      if (link.dataset.pageLink === page) link.setAttribute('aria-current', 'page');
    });
    const menu = $('#main-nav');
    const toggle = $('#menu-toggle');
    if (!headerReady) {
      if (toggle && menu) {
        const closeMenu = () => {
          menu.classList.remove('open');
          toggle.setAttribute('aria-expanded', 'false');
        };
        toggle.addEventListener('click', () => {
          const open = menu.classList.toggle('open');
          toggle.setAttribute('aria-expanded', String(open));
        });
        $$('a', menu).forEach(link => link.addEventListener('click', closeMenu));
        document.addEventListener('click', event => {
          if (!event.target.closest('.main-nav, .menu-toggle')) closeMenu();
        });
        document.addEventListener('keydown', event => {
          if (event.key === 'Escape') { closeMenu(); toggle.focus(); }
        });
        window.addEventListener('resize', () => {
          if (window.innerWidth > 800) closeMenu();
        });
      }
      headerReady = true;
    }
    $$('[data-zalo-link]').forEach(link => {
      link.href = window.DF.zaloURL(state.catalog.settings.zalo);
    });
    $$('[data-social-link]').forEach(link => {
      const key = link.dataset.socialLink;
      const fallback = key === 'facebook' ? 'https://www.facebook.com/' : (key === 'tiktok' ? 'https://www.tiktok.com/@phi_hng8' : '');
      const href = String(state.catalog.settings[key] || fallback).trim();
      if (href) {
        link.href = href;
        link.hidden = false;
      } else {
        link.hidden = true;
        link.removeAttribute('href');
      }
    });
    $$('[data-zalo-phone]').forEach(node => {
      node.textContent = state.catalog.settings.zalo || '0394781498';
    });
    const year = $('#year');
    if (year) year.textContent = new Date().getFullYear();
  }

  function categoryLabel(id) {
    return window.DF.categoryName(state.catalog, id);
  }

  function productCard(product) {
    const label = categoryLabel(product.category);
    const status = product.status || 'Hỏi shop';
    const statusKey = status.toLocaleLowerCase('vi-VN');
    const stockClass = statusKey.includes('hết') ? 'is-out' : statusKey.includes('còn') ? 'is-in' : 'is-check';
    const stockText = statusKey.includes('hết') ? 'HẾT HÀNG' : statusKey.includes('còn') ? 'CÒN HÀNG' : 'KIỂM TRA';
    return `<article class="df-product-card">
      <div class="df-product-rail" aria-hidden="true"><span>${escapeHTML(product.id)}</span></div>
      <button class="df-product-media" type="button" data-detail="${escapeHTML(product.id)}" aria-label="Xem ${escapeHTML(product.name)}">
        ${imageMarkup(product.image, product.name)}
        <span class="df-product-stock ${stockClass}">${stockText}</span>
      </button>
      <div class="df-product-body">
        <span class="df-product-eyebrow">${escapeHTML(label)}</span>
        <h3>${escapeHTML(product.name)}</h3>
        <p>${escapeHTML(product.description || 'Thông tin chi tiết được xác nhận cùng shop trước khi giao dịch.')}</p>
        <div class="df-product-bottom">
          <strong class="df-product-price">${escapeHTML(window.DF.money(product.price))}</strong>
          <button class="df-product-detail-link" type="button" data-detail="${escapeHTML(product.id)}">Xem chi tiết</button>
        </div>
      </div>
    </article>`;
  }

  function serviceCard(service) {
    return `<article class="df-service-card">
      <div class="df-service-media">${imageMarkup(service.image, service.name, 'SV')}<span class="df-service-code">${escapeHTML(service.id || 'SV')}</span></div>
      <div class="df-service-body"><small>SERVICE / DELTA FORCE</small><h3>${escapeHTML(service.name)}</h3><p>${escapeHTML(service.description || 'Shop sẽ xác nhận phạm vi và thời gian trước khi nhận.')}</p><div class="df-service-price">${escapeHTML(service.price || 'Liên hệ')}</div><button class="button button-small button-outline" type="button" data-service-id="${escapeHTML(service.id)}">Hỏi dịch vụ <span>↗</span></button></div>
    </article>`;
  }

  function newsCard(item, variant = 'list') {
    return `<a class="df-news-item df-news-item-${variant}" href="tin-tuc.html?id=${encodeURIComponent(item.id)}">
      <div class="df-news-rail" aria-hidden="true">${escapeHTML(item.category || 'NEWS')} // ${escapeHTML(item.id || 'UPDATE')}</div>
      <div class="df-news-item-wrap">${newsImageMarkup(item)}<span class="df-news-pinned${item.pinned ? ' is-visible' : ''}" aria-hidden="true"></span><div class="df-news-info"><div class="df-news-date">${escapeHTML(item.date || '')} · ${escapeHTML(item.category || 'TIN TỨC')}</div><div class="df-news-title">${escapeHTML(item.title)}</div><div class="df-news-summary">${escapeHTML(item.summary || '')}</div><div class="df-news-read-more">Xem chi tiết <span>↗</span></div></div></div>
    </a>`;
  }

  function renderHome() {
    const productGrid = $('#home-product-grid');
    if (productGrid) {
      const featured = state.catalog.products.filter(item => item.featured);
      productGrid.innerHTML = (featured.length ? featured : state.catalog.products).slice(0, 4).map(productCard).join('');
      hydrateImages(productGrid);
    }
    const serviceGrid = $('#home-service-grid');
    if (serviceGrid) {
      const featured = state.catalog.services.filter(item => item.featured);
      serviceGrid.innerHTML = (featured.length ? featured : state.catalog.services).slice(0, 3).map(serviceCard).join('');
      hydrateImages(serviceGrid);
    }
    const gift = state.catalog.giftcodes[0] || {};
    const total = $('#home-gift-total');
    const price = $('#home-gift-price');
    const giftTotal = state.catalog.settings.giftTotal ?? 300;
    if (total) total.textContent = giftTotal;
    const amount = Number(gift.price ?? state.catalog.settings.giftPrice ?? 20000);
    if (price) {
      price.textContent = amount > 0 ? `${window.DF.money(amount)} / ${giftTotal} code` : 'Liên hệ';
    }
    const totalStat = $('#home-gift-total-stat');
    const totalQueue = $('#home-gift-total-queue');
    if (totalStat) totalStat.textContent = state.catalog.settings.giftTotal ?? 300;
    if (totalQueue) totalQueue.textContent = state.catalog.settings.giftTotal ?? 300;
    const priceStat = $('#home-gift-price-stat');
    const priceLabel = $('#home-gift-price-label');
    if (priceStat) priceStat.textContent = window.DF.money(amount).replace(/\s/g, '');
    if (priceLabel) priceLabel.textContent = `trọn ${state.catalog.settings.giftTotal ?? 300} code`;
  }

  function renderNews() {
    const featureNode = $('#news-feature');
    const listNode = $('#news-list');
    if (!featureNode && !listNode) return;
    const allNews = Array.isArray(state.catalog.news) ? state.catalog.news : [];
    const filtered = state.newsCategory === 'all' ? allNews : allNews.filter(item => item.category === state.newsCategory);
    const items = filtered.length ? filtered : allNews;
    const feature = items.find(item => item.featured) || items[0];
    if (featureNode) featureNode.innerHTML = feature ? newsCard(feature, 'feature') : '<div class="df-news-empty">Chưa có tin tức.</div>';
    if (listNode) listNode.innerHTML = items.filter(item => item.id !== feature?.id).slice(0, 4).map(item => newsCard(item, 'list')).join('');
    $$('[data-news-filter]').forEach(button => {
      const active = button.dataset.newsFilter === state.newsCategory;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    if (featureNode) hydrateImages(featureNode);
    if (listNode) hydrateImages(listNode);
  }

  function renderAccountTabs() {
    const tabs = $('#account-tabs');
    if (!tabs) return;
    const groups = state.catalog.categories.filter(category => category.kind === 'account' || !category.kind);
    const all = [{ id: 'all', name: 'TẤT CẢ ACC' }, ...groups];
    tabs.innerHTML = all.map(item => `<button class="df-tab${state.accountCategory === item.id ? ' active' : ''}" type="button" data-account-category="${escapeHTML(item.id)}" aria-pressed="${state.accountCategory === item.id}">${escapeHTML(item.name)}</button>`).join('');
    $$('[data-account-category]', tabs).forEach(tab => tab.addEventListener('click', () => {
      state.accountCategory = tab.dataset.accountCategory;
      state.accountPage = 1;
      renderAccountTabs();
      renderAccounts();
    }));
  }

  function renderPagination(nav, total, page, onPage, scrollTarget) {
    if (!nav) return;
    const pageCount = Math.ceil(total / PAGE_SIZE);
    nav.replaceChildren();
    nav.hidden = pageCount <= 1;
    if (pageCount <= 1) return;
    const addButton = (label, target, title, current = false) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `df-page-button${current ? ' is-current' : ''}`;
      button.textContent = label;
      button.setAttribute('aria-label', title);
      if (current) button.setAttribute('aria-current', 'page');
      button.disabled = target < 1 || target > pageCount;
      button.addEventListener('click', () => {
        onPage(target);
        nav.querySelector('[aria-current="page"]')?.focus({ preventScroll: true });
        const top = $(scrollTarget);
        if (top?.scrollIntoView) top.scrollIntoView({ behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ? 'instant' : 'smooth', block: 'start' });
      });
      nav.append(button);
    };
    addButton('‹', page - 1, 'Trang trước');
    const pages = [...new Set([1, page - 1, page, page + 1, pageCount].filter(n => n >= 1 && n <= pageCount))].sort((a, b) => a - b);
    pages.forEach((number, index) => {
      if (index && number - pages[index - 1] > 1) {
        const dots = document.createElement('span');
        dots.className = 'df-page-dots';
        dots.textContent = '…';
        dots.setAttribute('aria-hidden', 'true');
        nav.append(dots);
      }
      addButton(String(number), number, `Trang ${number}`, number === page);
    });
    addButton('›', page + 1, 'Trang sau');
  }

  function renderAccounts() {
    const grid = $('#account-grid');
    if (!grid) return;
    const search = ($('#account-search')?.value || '').trim().toLocaleLowerCase('vi');
    const sort = $('#account-sort')?.value || 'featured';
    let products = state.catalog.products.filter(item => state.accountCategory === 'all' || item.category === state.accountCategory);
    if (search) products = products.filter(item => `${item.id} ${item.name} ${item.description} ${categoryLabel(item.category)}`.toLocaleLowerCase('vi').includes(search));
    products.sort((a, b) => {
      if (sort === 'price-asc') return (Number(a.price) || 0) - (Number(b.price) || 0);
      if (sort === 'price-desc') return (Number(b.price) || 0) - (Number(a.price) || 0);
      if (sort === 'name') return String(a.name).localeCompare(String(b.name), 'vi');
      return Number(Boolean(b.featured)) - Number(Boolean(a.featured));
    });
    const total = products.length;
    const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    state.accountPage = Math.min(Math.max(1, state.accountPage), pages);
    const result = $('#account-result');
    if (result) result.textContent = `${total} mục trong kho${pages > 1 ? ` · Trang ${state.accountPage}/${pages}` : ''}`;
    const empty = $('#account-empty');
    if (empty) empty.hidden = total > 0;
    grid.innerHTML = products.slice((state.accountPage - 1) * PAGE_SIZE, state.accountPage * PAGE_SIZE).map(productCard).join('');
    hydrateImages(grid);
    renderPagination($('#account-pagination'), total, state.accountPage, next => { state.accountPage = next; renderAccounts(); }, '#account-result');
  }

  function renderServices() {
    const grid = $('#service-grid');
    if (!grid) return;
    const total = state.catalog.services.length;
    state.servicePage = Math.min(Math.max(1, state.servicePage), Math.max(1, Math.ceil(total / PAGE_SIZE)));
    grid.innerHTML = state.catalog.services.slice((state.servicePage - 1) * PAGE_SIZE, state.servicePage * PAGE_SIZE).map(serviceCard).join('');
    hydrateImages(grid);
    renderPagination($('#service-pagination'), total, state.servicePage, next => { state.servicePage = next; renderServices(); }, '#service-grid');
  }

  function giftTikTokId(link) {
    const match = String(link || '').match(/^https:\/\/(?:www\.)?tiktok\.com\/@[a-zA-Z0-9._]{2,24}\/video\/([0-9]{10,22})(?:[?#].*)?$/);
    return match ? match[1] : '';
  }

  function bindGiftVideo(frame, sound, placeholder) {
    if (frame.dataset.giftBound) return;
    frame.dataset.giftBound = '1';
    const send = type => frame.contentWindow?.postMessage({ type, value: null, 'x-tiktok-player': true }, 'https://www.tiktok.com');
    sound.addEventListener('click', () => {
      frame.dataset.userWantsSound = '1';
      if (frame.dataset.ready === '1') { send('unMute'); send('play'); }
      sound.hidden = true;
    });
    window.addEventListener('message', event => {
      if (event.origin !== 'https://www.tiktok.com' || event.source !== frame.contentWindow || !event.data?.['x-tiktok-player']) return;
      if (event.data.type === 'onPlayerReady') {
        frame.dataset.ready = '1';
        placeholder.hidden = true;
        send('mute');
        if (frame.dataset.visible === '1') send('play');
        if (frame.dataset.userWantsSound === '1') { send('unMute'); sound.hidden = true; }
      } else if (event.data.type === 'onMute') {
        sound.hidden = !event.data.value;
      } else if (event.data.type === 'onPlayerError') {
        if (event.data.value?.errorCode === 3002) {
          sound.hidden = false; // A user click can start playback if autoplay was blocked.
        } else {
          frame.hidden = true;
          sound.hidden = true;
          placeholder.hidden = false;
        }
      }
    });
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver(entries => {
        const visible = entries[0]?.isIntersecting && entries[0].intersectionRatio >= .25;
        frame.dataset.visible = visible ? '1' : '0';
        if (frame.dataset.ready !== '1') return;
        if (visible) { send('mute'); sound.hidden = false; send('play'); }
        else { send('mute'); send('pause'); sound.hidden = false; frame.dataset.userWantsSound = '0'; }
      }, { threshold: [.25] });
      observer.observe(frame);
    } else {
      frame.dataset.visible = '1';
    }
  }

  function renderGiftcode() {
    const gift = state.catalog.giftcodes[0] || {};
    const total = state.catalog.settings.giftTotal ?? 300;
    const priceValue = gift.price ?? state.catalog.settings.giftPrice ?? 20000;
    $$('[data-gift-summary]').forEach(node => { node.textContent = `${total} GIFTCODE · ${window.DF.money(priceValue)} / ${total} CODE`; });
    const photo = $('#gift-hero-image');
    const placeholder = $('#gift-hero-placeholder');
    if (photo && placeholder) {
      const photoFrame = $('#gift-hero-photo');
      const frame = $('#gift-hero-player');
      const sound = $('#gift-video-unmute');
      const sourceLink = $('#gift-video-source');
      const videoLink = state.catalog.settings.giftHeroVideo || '';
      const videoId = state.catalog.settings.giftHeroType === 'video' ? giftTikTokId(videoLink) : '';
      photoFrame?.classList.toggle('is-video', Boolean(videoId));
      if (videoId && frame && sound && sourceLink) {
        photo.removeAttribute('src');
        photo.hidden = true;
        placeholder.hidden = true;
        frame.hidden = false;
        sourceLink.href = videoLink.split(/[?#]/)[0];
        sourceLink.hidden = false;
        sound.hidden = false;
        bindGiftVideo(frame, sound, placeholder);
        const playerUrl = `https://www.tiktok.com/player/v1/${videoId}?autoplay=0&loop=1&controls=1&music_info=0&description=0&rel=0`;
        if (frame.getAttribute('src') !== playerUrl) {
          frame.dataset.ready = '0';
          frame.dataset.userWantsSound = '0';
          frame.src = playerUrl;
        }
      } else {
        if (frame) { frame.hidden = true; frame.removeAttribute('src'); }
        if (sound) sound.hidden = true;
        if (sourceLink) sourceLink.hidden = true;
        const source = state.catalog.settings.giftHeroImage || '';
        const safeSource = /^https:\/\/[^\s]+$/i.test(source) || /^images\/[a-f0-9]{32}\.webp$/.test(source) ? source : '';
        photo.onload = () => { photo.hidden = false; placeholder.hidden = true; };
        photo.onerror = () => { photo.hidden = true; placeholder.hidden = false; };
        if (safeSource) {
          photo.hidden = true;
          placeholder.hidden = false;
          if (photo.getAttribute('src') !== safeSource) photo.src = safeSource;
          else if (photo.complete && photo.naturalWidth > 0) photo.onload();
        } else {
          photo.removeAttribute('src');
          photo.hidden = true;
          placeholder.hidden = false;
        }
      }
    }
    const assignments = {
      '#gift-total': total,
      '#gift-price': `${window.DF.money(priceValue)} / ${total} code`,
      '#gift-headline-total': total,
      '#gift-headline-price': `${window.DF.money(priceValue)} / ${total} code.`,
      '#gift-note': state.catalog.settings.giftNote || gift.description || 'Nhập theo lượt, báo lại mã sai hoặc đã dùng.'
    };
    Object.entries(assignments).forEach(([selector, value]) => { const node = $(selector); if (node) node.textContent = value; });
    const giftTotalStat = $('#gift-total-stat');
    const giftTotalQueue = $('#gift-total-queue');
    const giftPriceStat = $('#gift-price-stat');
    if (giftTotalStat) giftTotalStat.textContent = total;
    if (giftTotalQueue) giftTotalQueue.textContent = total;
    if (giftPriceStat) giftPriceStat.textContent = window.DF.money(priceValue).replace(/\s/g, '');
    const giftPriceLabel = $('#gift-price-label');
    if (giftPriceLabel) giftPriceLabel.textContent = `trọn ${total} code`;
    const list = $('#gift-items');
    if (list) list.innerHTML = state.catalog.giftcodes.map(item => `<div class="df-gift-card"><div><h3>${escapeHTML(item.name)}</h3><p>${escapeHTML(item.description || state.catalog.settings.giftNote || '')}</p></div><strong>${escapeHTML(window.DF.money(item.price ?? priceValue))} / ${escapeHTML(total)} code</strong></div>`).join('');
  }

  function openProduct(product) {
    const modal = $('#product-modal');
    if (!modal || !product) return;
    state.product = product;
    const art = $('#modal-art');
    if (art) {
      art.innerHTML = imageMarkup(product.image, product.name);
      hydrateImages(art);
    }
    const set = (id, value) => { const node = $(`#${id}`); if (node) node.textContent = value; };
    set('modal-category', categoryLabel(product.category));
    set('modal-title', product.name);
    set('modal-price', window.DF.money(product.price));
    set('modal-description', product.description || 'Shop sẽ xác nhận thông tin thực tế trước khi giao dịch.');
    set('modal-code', product.id);
    set('modal-status', product.status || 'Hỏi shop');
    set('modal-note', 'Giá và tình trạng là thông tin tham khảo; hãy hỏi shop để nhận ảnh kho và điều kiện bàn giao mới nhất.');
    openDialog(modal);
  }

  function contactMessage(type, item) {
    if (type === 'giftcode') return `Chào shop Tạp Hóa Delta Force, mình muốn hỏi gói ${state.catalog.settings.giftTotal ?? 300} giftcode với giá trọn gói ${window.DF.money(state.catalog.settings.giftPrice ?? 20000)}. Nhờ shop hướng dẫn giúp.`;
    if (type === 'product' && item) return `Chào shop, mình muốn hỏi ${item.name} (mã ${item.id}). Giá tham khảo trên web: ${window.DF.money(item.price)}. Nhờ shop kiểm tra tồn kho và gửi ảnh/thông tin mới nhất.`;
    if (type === 'service' && item) return `Chào shop, mình muốn hỏi dịch vụ ${item.name} (${item.id}). Nhờ shop tư vấn phạm vi, thời gian và giá chốt.`;
    return 'Chào shop Tạp Hóa Delta Force, mình muốn được tư vấn kho acc và dịch vụ Delta Force.';
  }

  function openContact(type = 'general', item = null) {
    const modal = $('#contact-modal');
    if (!modal) return;
    const title = $('#contact-title');
    if (title) title.textContent = type === 'giftcode' ? 'Nhận nhập giftcode' : type === 'service' ? 'Hỏi dịch vụ' : type === 'product' ? 'Hỏi mua acc' : 'Trao đổi với shop';
    const text = $('#contact-text');
    if (text) text.value = contactMessage(type, item);
    const link = $('#open-zalo');
    if (link) link.href = window.DF.zaloURL(state.catalog.settings.zalo);
    const status = $('#contact-status');
    if (status) { status.hidden = true; status.textContent = ''; }
    openDialog(modal);
  }

  function setupInteractions() {
    document.addEventListener('click', event => {
      const detail = event.target.closest('[data-detail]');
      if (detail) {
        const item = state.catalog.products.find(product => product.id === detail.dataset.detail);
        if (item) openProduct(item);
        return;
      }
      const newsFilter = event.target.closest('[data-news-filter]');
      if (newsFilter) {
        state.newsCategory = newsFilter.dataset.newsFilter || 'all';
        renderNews();
        return;
      }
      const buy = event.target.closest('[data-buy]');
      if (buy) {
        const item = state.catalog.products.find(product => product.id === buy.dataset.buy);
        if (item) openContact('product', item);
        return;
      }
      const service = event.target.closest('[data-service-id]');
      if (service) {
        const item = state.catalog.services.find(entry => entry.id === service.dataset.serviceId);
        if (item) openContact('service', item);
        return;
      }
      const contact = event.target.closest('[data-contact]');
      if (contact) {
        openContact(contact.dataset.contact, contact.dataset.contact === 'product' ? state.product : null);
        return;
      }
      const close = event.target.closest('[data-close-modal]');
      if (close) closeDialog(close.closest('dialog'));
    });
    const modalBuy = $('#modal-buy');
    if (modalBuy) modalBuy.addEventListener('click', () => {
      closeDialog($('#product-modal'));
      if (state.product) openContact('product', state.product);
    });
    const copy = $('#copy-contact');
    if (copy) copy.addEventListener('click', async () => {
      const text = $('#contact-text')?.value || '';
      try {
        await navigator.clipboard.writeText(text);
        const status = $('#contact-status');
        if (status) { status.hidden = false; status.textContent = 'Đã sao chép nội dung tin nhắn.'; }
      } catch {
        const field = $('#contact-text');
        if (field) { field.focus(); field.select(); }
      }
    });
    ['product-modal', 'contact-modal'].forEach(id => {
      const dialog = $(`#${id}`);
      if (dialog) dialog.addEventListener('click', event => { if (event.target === dialog) closeDialog(dialog); });
    });
    const search = $('#account-search');
    const sort = $('#account-sort');
    if (search) search.addEventListener('input', () => { state.accountPage = 1; renderAccounts(); });
    if (sort) sort.addEventListener('change', () => { state.accountPage = 1; renderAccounts(); });
  }

  function renderAll() {
    state.catalog = window.DF.load();
    setupHeader();
    renderHome();
    renderNews();
    renderAccountTabs();
    renderAccounts();
    renderServices();
    renderGiftcode();
    hydrateImages();
  }

  setupTheme();
  setupInteractions();
  renderAll();
  window.addEventListener('df-catalog-updated', renderAll);
})();
