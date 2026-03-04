/**
 * VN CG Scan Viewer - Main Application
 * PWA for visual novel CG image QA review
 * ES2022+ - Vanilla JavaScript
 */

// ============================================================================
// Application State
// ============================================================================

const AppState = {
  games: [],
  selectedGameId: null,
  images: [],
  totalImages: 0,
  currentPage: 1,
  perPage: 50,
  totalPages: 1,
  filters: { status: '', search: '', sort: 'filename' },
  reviewMode: false,
  reviewIndex: 0,
  undoStack: [],
  sessionId: crypto.randomUUID(),
  tags: [],
  selectedImages: new Set(),
  selectMode: false,
  loading: false,
};

// ============================================================================
// API Layer
// ============================================================================

const API = {
  baseURL: '',

  async request(endpoint, options = {}) {
    const url = `${this.baseURL}/api${endpoint}`;
    try {
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          'X-Session-ID': AppState.sessionId,
          ...options.headers,
        },
        ...options,
      });

      if (!response.ok) {
        let errorMessage = `HTTP ${response.status}`;
        if (response.status === 400) errorMessage = 'Bad request.';
        else if (response.status === 404) errorMessage = 'Not found.';
        else if (response.status === 429) errorMessage = 'Too many requests.';
        else if (response.status >= 500) errorMessage = 'Server error.';

        try {
          const err = await response.json();
          if (err.detail) errorMessage = err.detail;
        } catch (_) {}

        throw new Error(errorMessage);
      }

      if (response.headers.get('content-type')?.includes('application/json')) {
        return await response.json();
      }
      return response;
    } catch (error) {
      if (error instanceof TypeError && error.message.includes('fetch')) {
        showToast('Network error: Unable to connect to server', 'error');
      }
      throw error;
    }
  },

  getGames: function () { return this.request('/games'); },
  getGameDetail: function (id) { return this.request(`/games/${id}`); },

  getImages(params = {}) {
    const qp = { sort: AppState.filters.sort, page: AppState.currentPage, per_page: AppState.perPage, ...params };
    if (AppState.selectedGameId) qp.game_id = AppState.selectedGameId;
    if (AppState.filters.status) qp.status = AppState.filters.status;
    if (AppState.filters.search) qp.search = AppState.filters.search;
    return this.request(`/images?${new URLSearchParams(qp)}`);
  },

  reviewImage(imageId, action, rating) {
    const body = { image_id: imageId, action, ...(rating && { rating }) };
    return this.request('/review', { method: 'POST', body: JSON.stringify(body) });
  },

  undoLast(count = 1) {
    return this.request('/undo', { method: 'POST', body: JSON.stringify({ count }) });
  },

  scanDirectory: function () { return this.request('/scan', { method: 'POST' }); },
  getTags: function () { return this.request('/tags'); },
  getStats: function () { return this.request('/stats'); },

  updateImage(imageId, data) {
    return this.request(`/images/${imageId}`, { method: 'PATCH', body: JSON.stringify(data) });
  },

  bulkAction(imageIds, action, tag) {
    const body = { image_ids: imageIds, action, ...(tag && { tag }) };
    return this.request('/images/bulk', { method: 'POST', body: JSON.stringify(body) });
  },

  purgeRejected(gameId) {
    return this.request(`/images/purge-rejected?game_id=${gameId}`, { method: 'DELETE' });
  },
};

// ============================================================================
// DOM References (matching index.html IDs)
// ============================================================================

const DOM = {};

function cacheDOMRefs() {
  DOM.gameList = document.getElementById('game-list');
  DOM.gameSearch = document.getElementById('game-search');
  DOM.scanBtn = document.getElementById('scan-btn');
  DOM.imageGrid = document.getElementById('image-grid');
  DOM.filterBar = document.getElementById('filter-bar');
  DOM.statusFilter = document.getElementById('status-filter');
  DOM.sortSelect = document.getElementById('sort-select');
  DOM.searchInput = document.getElementById('search-input');
  DOM.reviewModeBtn = document.getElementById('review-mode-btn');
  DOM.statsBtn = document.getElementById('stats-btn');
  DOM.imageCount = document.getElementById('image-count');
  DOM.filterStatus = document.getElementById('filter-status');
  DOM.loadingIndicator = document.getElementById('loading-indicator');
  DOM.emptyState = document.getElementById('empty-state');
  DOM.paginationBar = document.getElementById('pagination-bar');

  // Review overlay (pre-built in HTML)
  DOM.reviewOverlay = document.getElementById('review-overlay');
  DOM.reviewImage = document.getElementById('review-image');
  DOM.reviewImageCounter = document.getElementById('review-image-counter');
  DOM.reviewPrev = document.getElementById('review-prev');
  DOM.reviewNext = document.getElementById('review-next');
  DOM.reviewClose = document.getElementById('review-close');
  DOM.reviewSidebar = document.getElementById('review-sidebar');
  DOM.infoName = document.getElementById('info-name');
  DOM.infoSize = document.getElementById('info-size');
  DOM.infoDimensions = document.getElementById('info-dimensions');
  DOM.infoStatus = document.getElementById('info-status');
  DOM.reviewRating = document.getElementById('review-rating');
  DOM.reviewTags = document.getElementById('review-tags');
  DOM.reviewActions = document.getElementById('review-actions');
  DOM.progressReviewed = document.getElementById('progress-reviewed');
  DOM.progressRemaining = document.getElementById('progress-remaining');
  DOM.progressBar = document.getElementById('progress-bar');

  // Modals
  DOM.tagModal = document.getElementById('tag-modal');
  DOM.closeTagModal = document.getElementById('close-tag-modal');
  DOM.editTagsBtn = document.getElementById('edit-tags-btn');
  DOM.newTagInput = document.getElementById('new-tag');
  DOM.addTagBtn = document.getElementById('add-tag-btn');
  DOM.tagCategories = document.getElementById('tag-categories');
  DOM.statsModal = document.getElementById('stats-modal');
  DOM.closeStatsModal = document.getElementById('close-stats-modal');
  DOM.statsContent = document.getElementById('stats-content');

  // Sidebar stats
  DOM.totalGames = document.getElementById('total-games');
  DOM.totalImages = document.getElementById('total-images');
  DOM.qaProgress = document.getElementById('qa-progress');

  // Selection & Bulk actions
  DOM.selectModeBtn = document.getElementById('select-mode-btn');
  DOM.selectAllBtn = document.getElementById('select-all-btn');
  DOM.deselectAllBtn = document.getElementById('deselect-all-btn');
  DOM.bulkAcceptBtn = document.getElementById('bulk-accept-btn');
  DOM.bulkRejectBtn = document.getElementById('bulk-reject-btn');
  DOM.selectionCount = document.getElementById('selection-count');

  DOM.purgeRejectedBtn = document.getElementById('purge-rejected-btn');

  DOM.sidebarToggle = document.getElementById('sidebar-toggle');

  // Toast
  DOM.toastContainer = document.getElementById('toast-container');
}

// ============================================================================
// Virtual Scroll Grid
// ============================================================================

class VirtualGrid {
  constructor(container, options = {}) {
    this.container = container;
    this.items = [];
    this.visibleItems = new Map();
    this.observer = null;
    this.onItemClick = options.onItemClick || (() => {});
    this.init();
  }

  init() {
    this.observer = new IntersectionObserver(
      (entries) => this.handleIntersection(entries),
      { rootMargin: '200px', threshold: 0.1 }
    );
  }

  setItems(items) {
    this.items = items;
    this.render();
  }

  render() {
    this.container.innerHTML = '';
    this.visibleItems.clear();

    this.items.forEach((item, index) => {
      const card = document.createElement('div');
      card.className = `grid-item status-${item.status}`;
      card.dataset.itemId = item.id;
      card.innerHTML = renderGridItem(item);

      card.addEventListener('click', (e) => {
        if (e.shiftKey || AppState.selectMode) {
          this.toggleSelection(item.id, card);
        } else {
          this.onItemClick(item, index);
        }
      });

      this.observer.observe(card);
      this.container.appendChild(card);
    });
  }

  handleIntersection(entries) {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const id = entry.target.dataset.itemId;
      if (this.visibleItems.has(id)) return;
      this.visibleItems.set(id, true);

      const img = entry.target.querySelector('img[data-lazy]');
      if (img?.dataset.src) {
        img.src = img.dataset.src;
        img.removeAttribute('data-lazy');
      }
    });
  }

  toggleSelection(itemId, el) {
    if (AppState.selectedImages.has(itemId)) {
      AppState.selectedImages.delete(itemId);
      el.classList.remove('selected');
    } else {
      AppState.selectedImages.add(itemId);
      el.classList.add('selected');
    }
    updateBulkActionUI();
  }

  destroy() {
    if (this.observer) { this.observer.disconnect(); this.observer = null; }
    this.container.innerHTML = '';
    this.visibleItems.clear();
    this.items = [];
  }
}

// ============================================================================
// Rendering
// ============================================================================

function renderGameList(games) {
  if (!DOM.gameList) return;

  DOM.gameList.innerHTML = games.map((game) => `
    <div class="game-item ${game.id === AppState.selectedGameId ? 'active' : ''}"
         data-game-id="${game.id}" role="option" tabindex="0"
         aria-label="${escapeHtml(game.name)}, ${game.image_count} images, ${game.reviewed_count || 0} reviewed">
      <div class="game-info">
        <div class="game-name">${escapeHtml(game.name)}</div>
        <div class="game-meta">
          <span>${game.image_count} images</span>
          <span>${game.reviewed_count || 0} reviewed</span>
        </div>
      </div>
    </div>
  `).join('');

  DOM.gameList.querySelectorAll('.game-item').forEach((el) => {
    el.addEventListener('click', () => selectGame(parseInt(el.dataset.gameId)));
  });
}

function renderGridItem(image) {
  const thumbSrc = `/api/images/${image.id}/thumbnail`;
  const displayFilename = image.filename.length > 25 ? image.filename.substring(0, 25) + '...' : image.filename;
  return `
    <img src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 200'%3E%3Crect width='200' height='200' fill='%23252540'/%3E%3C/svg%3E"
         data-src="${thumbSrc}" data-lazy class="thumbnail" alt="${escapeHtml(image.filename)}"
         width="200" height="200" style="aspect-ratio:1;width:100%;height:auto;">
    <div class="item-overlay">
      <span class="status-badge status-${image.status}">${image.status}</span>
      <div class="filename" title="${escapeHtml(image.filename)}">${escapeHtml(displayFilename)}</div>
    </div>
  `;
}

function renderImageGrid(images) {
  if (!DOM.imageGrid) return;

  if (window.virtualGrid) window.virtualGrid.destroy();

  if (images.length === 0) {
    DOM.imageGrid.innerHTML = '';
    DOM.emptyState?.classList.remove('hidden');
    DOM.paginationBar?.classList.add('hidden');
    return;
  }
  DOM.emptyState?.classList.add('hidden');

  window.virtualGrid = new VirtualGrid(DOM.imageGrid, {
    onItemClick: (item) => openReviewMode(item),
  });
  window.virtualGrid.setItems(images);

  // Update count badge
  if (DOM.imageCount) DOM.imageCount.textContent = `${AppState.totalImages} images`;

  // Render pagination controls
  renderPagination();
}

/** Populate the pre-built review overlay with current image data */
function populateReviewOverlay(image) {
  if (!DOM.reviewOverlay || !image) return;

  // Image
  DOM.reviewImage.src = `/api/images/${image.id}/preview`;
  DOM.reviewImage.alt = image.filename;

  // Counter
  DOM.reviewImageCounter.textContent = `${AppState.reviewIndex + 1} / ${AppState.images.length}`;

  // Info panel
  DOM.infoName.textContent = image.filename;
  DOM.infoSize.textContent = formatBytes(image.file_size || 0);
  DOM.infoDimensions.textContent = `${image.width || '?'}×${image.height || '?'}`;
  DOM.infoStatus.textContent = image.status;
  DOM.infoStatus.className = `info-value status-badge status-${image.status}`;

  // Rating buttons
  DOM.reviewRating.querySelectorAll('.rating-btn').forEach((btn) => {
    const r = parseInt(btn.dataset.rating);
    btn.classList.toggle('active', image.rating >= r);
  });

  // Tags
  if (image.tags?.length) {
    DOM.reviewTags.innerHTML = image.tags.map((t) => `<span class="tag">${escapeHtml(t)}</span>`).join('');
  } else {
    DOM.reviewTags.innerHTML = '<span class="tag-empty">No tags</span>';
  }

  // Progress
  const reviewed = AppState.images.filter((i) => i.status !== 'pending').length;
  DOM.progressReviewed.textContent = reviewed;
  DOM.progressRemaining.textContent = AppState.images.length - reviewed;
  const pct = AppState.images.length > 0 ? (reviewed / AppState.images.length) * 100 : 0;
  DOM.progressBar.style.width = `${pct}%`;
}

function renderStats(stats) {
  if (!DOM.statsContent) return;

  let html = `
    <div class="stat-card"><div class="stat-value">${escapeHtml(String(stats.total_images))}</div><div class="stat-label">Total</div></div>
    <div class="stat-card"><div class="stat-value">${escapeHtml(String(stats.reviewed))}</div><div class="stat-label">Reviewed</div></div>
    <div class="stat-card accepted"><div class="stat-value">${escapeHtml(String(stats.accepted))}</div><div class="stat-label">Accepted</div></div>
    <div class="stat-card rejected"><div class="stat-value">${escapeHtml(String(stats.rejected))}</div><div class="stat-label">Rejected</div></div>
    <div class="stat-card flagged"><div class="stat-value">${escapeHtml(String(stats.flagged))}</div><div class="stat-label">Flagged</div></div>
  `;

  if (stats.by_game?.length) {
    html += '<div class="stats-games" style="grid-column:1/-1;margin-top:1rem;">';
    html += '<h4>Per Game</h4><table class="stats-table"><thead><tr><th>Game</th><th>Total</th><th>Reviewed</th><th>Accepted</th></tr></thead><tbody>';
    stats.by_game.forEach((g) => {
      html += `<tr><td>${escapeHtml(g.game_name)}</td><td>${escapeHtml(String(g.total))}</td><td>${escapeHtml(String(g.reviewed))}</td><td>${escapeHtml(String(g.accepted))}</td></tr>`;
    });
    html += '</tbody></table></div>';
  }

  DOM.statsContent.innerHTML = html;
}

function renderTagModal(tags) {
  if (!DOM.tagCategories) return;

  const categories = {};
  tags.forEach((t) => {
    if (!categories[t.category]) categories[t.category] = [];
    categories[t.category].push(t);
  });

  DOM.tagCategories.innerHTML = Object.entries(categories).map(([cat, tagList]) => `
    <div class="tag-category">
      <h4>${escapeHtml(cat)}</h4>
      <div class="tag-list" role="group" aria-label="${escapeHtml(cat)} tags">
        ${tagList.map((t) => `<button class="tag-toggle" data-tag-id="${t.id}" data-tag-name="${escapeHtml(t.name)}" aria-label="Add tag: ${escapeHtml(t.name)} (${t.count} images)">${escapeHtml(t.name)} (${t.count})</button>`).join('')}
      </div>
    </div>
  `).join('');
}

function renderPagination() {
  if (!DOM.paginationBar) return;

  // Show pagination only if there are multiple pages
  if (AppState.totalPages <= 1) {
    DOM.paginationBar.classList.add('hidden');
    return;
  }

  DOM.paginationBar.classList.remove('hidden');

  const prevDisabled = AppState.currentPage === 1;
  const nextDisabled = AppState.currentPage === AppState.totalPages;

  DOM.paginationBar.innerHTML = `
    <div class="pagination-content">
      <button id="pagination-prev" class="pagination-btn" ${prevDisabled ? 'disabled' : ''} aria-label="Go to previous page">
        Previous
      </button>
      <span class="pagination-info">
        Page ${AppState.currentPage} of ${AppState.totalPages}
      </span>
      <button id="pagination-next" class="pagination-btn" ${nextDisabled ? 'disabled' : ''} aria-label="Go to next page">
        Next
      </button>
    </div>
  `;

  // Bind events
  const prevBtn = DOM.paginationBar.querySelector('#pagination-prev');
  const nextBtn = DOM.paginationBar.querySelector('#pagination-next');

  prevBtn?.addEventListener('click', () => {
    if (AppState.currentPage > 1) {
      AppState.currentPage--;
      loadImages();
    }
  });

  nextBtn?.addEventListener('click', () => {
    if (AppState.currentPage < AppState.totalPages) {
      AppState.currentPage++;
      loadImages();
    }
  });
}

// ============================================================================
// Actions & Event Handlers
// ============================================================================

async function selectGame(gameId) {
  AppState.selectedGameId = gameId;
  AppState.currentPage = 1;
  AppState.selectedImages.clear();
  renderGameList(AppState.games); // re-render to update active state
  document.getElementById('sidebar')?.classList.remove('sidebar-open');
  await loadImages();
}

function openReviewMode(image) {
  AppState.reviewIndex = AppState.images.findIndex((i) => i.id === image.id);
  if (AppState.reviewIndex < 0) AppState.reviewIndex = 0;
  AppState.reviewMode = true;
  DOM.reviewOverlay?.classList.remove('hidden');
  populateReviewOverlay(image);
  document.addEventListener('keydown', handleReviewKeyboard);

  // Focus management: move focus to the close button when review mode opens
  // This ensures keyboard users are aware the modal has opened and can easily close it
  setTimeout(() => {
    DOM.reviewClose?.focus();
  }, 0);
}

function exitReviewMode() {
  AppState.reviewMode = false;
  DOM.reviewOverlay?.classList.add('hidden');
  document.removeEventListener('keydown', handleReviewKeyboard);
}

function nextImage() {
  if (AppState.images.length === 0) return;
  AppState.reviewIndex = (AppState.reviewIndex + 1) % AppState.images.length;
  populateReviewOverlay(AppState.images[AppState.reviewIndex]);
}

function previousImage() {
  if (AppState.images.length === 0) return;
  AppState.reviewIndex = (AppState.reviewIndex - 1 + AppState.images.length) % AppState.images.length;
  populateReviewOverlay(AppState.images[AppState.reviewIndex]);
}

async function reviewAction(action) {
  const image = AppState.images[AppState.reviewIndex];
  if (!image) return;

  // Disable action buttons
  DOM.reviewActions?.querySelectorAll('.action-btn').forEach((b) => (b.disabled = true));
  AppState.loading = true;

  try {
    const result = await API.reviewImage(image.id, action);
    AppState.undoStack.push(result.action_id);
    if (AppState.undoStack.length > 50) AppState.undoStack.shift();

    // Update local image state
    const idx = AppState.images.findIndex((i) => i.id === image.id);
    if (idx >= 0) AppState.images[idx].status = result.new_status;

    nextImage();
  } catch (error) {
    console.error('Review action failed:', error);
    showToast(`Failed to ${action} image`, 'error');
  } finally {
    AppState.loading = false;
    DOM.reviewActions?.querySelectorAll('.action-btn').forEach((b) => (b.disabled = false));
  }
}

async function rateImage(rating) {
  const image = AppState.images[AppState.reviewIndex];
  if (!image) return;

  try {
    await API.updateImage(image.id, { rating });
    image.rating = rating;
    populateReviewOverlay(image);
    showToast(`Rated ${rating} star${rating > 1 ? 's' : ''}`, 'info');
  } catch (error) {
    console.error('Rating failed:', error);
    showToast('Failed to save rating', 'error');
  }
}

async function undoLastAction() {
  if (AppState.undoStack.length === 0) {
    showToast('Nothing to undo', 'info');
    return;
  }

  try {
    const result = await API.undoLast(1);
    AppState.undoStack.pop();
    showToast('Action undone', 'success');
    await loadImages();
    if (AppState.reviewMode) populateReviewOverlay(AppState.images[AppState.reviewIndex]);
  } catch (error) {
    console.error('Undo failed:', error);
    showToast('Failed to undo', 'error');
  }
}

function handleReviewKeyboard(e) {
  if (!AppState.reviewMode) return;
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;

  const key = e.key.toLowerCase();

  switch (key) {
    case 'a': e.preventDefault(); reviewAction('accept'); break;
    case 'd': e.preventDefault(); reviewAction('reject'); break;
    case 's': e.preventDefault(); reviewAction('skip'); break;
    case 'f': e.preventDefault(); reviewAction('flag'); break;
    case 'z': e.preventDefault(); undoLastAction(); break;
    case 'escape': e.preventDefault(); exitReviewMode(); break;
    case 'arrowright': case 'e': e.preventDefault(); nextImage(); break;
    case 'arrowleft': case 'q': e.preventDefault(); previousImage(); break;
    default:
      if (e.key >= '1' && e.key <= '5') {
        e.preventDefault();
        rateImage(parseInt(e.key));
      }
  }
}

async function loadImages() {
  setLoading(true);
  try {
    const result = await API.getImages();
    AppState.images = result.items || [];
    AppState.totalImages = result.total || 0;
    AppState.currentPage = result.page || 1;
    AppState.perPage = result.per_page || 50;
    AppState.totalPages = result.pages || 1;
    renderImageGrid(AppState.images);
  } catch (error) {
    console.error('Failed to load images:', error);
    showToast('Failed to load images', 'error');
  } finally {
    setLoading(false);
  }
}

async function loadGames() {
  try {
    const games = await API.getGames();
    AppState.games = games;
    renderGameList(games);

    // Update sidebar stats
    if (DOM.totalGames) DOM.totalGames.textContent = games.length;
    const totalImgs = games.reduce((sum, g) => sum + g.image_count, 0);
    if (DOM.totalImages) DOM.totalImages.textContent = totalImgs;

    if (games.length > 0 && !AppState.selectedGameId) {
      AppState.selectedGameId = games[0].id;
    }
  } catch (error) {
    console.error('Failed to load games:', error);
    showToast('Failed to load games', 'error');
  }
}

async function scanDirectory() {
  if (DOM.scanBtn) { DOM.scanBtn.disabled = true; DOM.scanBtn.textContent = 'Scanning...'; }
  try {
    const result = await API.scanDirectory();
    showToast(`Scan complete: ${result.games_found} games, ${result.new_images} new images`, 'success');
    await loadGames();
    await loadImages();
  } catch (error) {
    console.error('Scan failed:', error);
    showToast('Scan failed', 'error');
  } finally {
    if (DOM.scanBtn) { DOM.scanBtn.disabled = false; DOM.scanBtn.textContent = 'Scan'; }
  }
}

async function purgeRejected() {
  if (!AppState.selectedGameId) {
    showToast('Select a game before purging rejected images', 'error');
    return;
  }

  try {
    const result = await API.purgeRejected(AppState.selectedGameId);
    const count = result.deleted_count ?? 0;
    showToast(`Purged ${count} rejected image${count !== 1 ? 's' : ''}`, 'success');
    await Promise.all([loadImages(), loadGames()]);
  } catch (error) {
    console.error('Purge rejected failed:', error);
    showToast('Failed to purge rejected images', 'error');
  }
}

async function bulkAction(action) {
  if (AppState.selectedImages.size === 0) return;
  const ids = Array.from(AppState.selectedImages);

  try {
    await API.bulkAction(ids, action);
    showToast(`Bulk ${action}: ${ids.length} images`, 'success');
    AppState.selectedImages.clear();
    AppState.selectMode = false;
    await loadImages();
    updateBulkActionUI();
  } catch (error) {
    console.error('Bulk action failed:', error);
    showToast(`Bulk ${action} failed`, 'error');
  }
}

async function loadAndShowStats() {
  try {
    const stats = await API.getStats();
    renderStats(stats);
    DOM.statsModal?.classList.remove('hidden');
  } catch (error) {
    console.error('Stats failed:', error);
    showToast('Failed to load stats', 'error');
  }
}

async function loadAndShowTags() {
  try {
    const tags = await API.getTags();
    AppState.tags = tags;
    renderTagModal(tags);
    DOM.tagModal?.classList.remove('hidden');
  } catch (error) {
    console.error('Tags failed:', error);
    showToast('Failed to load tags', 'error');
  }
}

// ============================================================================
// UI Helpers
// ============================================================================

function updateBulkActionUI() {
  const count = AppState.selectedImages.size;
  const hasSelection = count > 0;
  const inSelectMode = AppState.selectMode;

  if (DOM.selectModeBtn) {
    DOM.selectModeBtn.textContent = inSelectMode ? 'Exit Select' : 'Select';
    DOM.selectModeBtn.classList.toggle('btn-active', inSelectMode);
  }
  if (DOM.selectAllBtn) DOM.selectAllBtn.style.display = inSelectMode ? 'inline-block' : 'none';
  if (DOM.deselectAllBtn) DOM.deselectAllBtn.style.display = inSelectMode && hasSelection ? 'inline-block' : 'none';
  if (DOM.bulkAcceptBtn) DOM.bulkAcceptBtn.style.display = hasSelection ? 'inline-block' : 'none';
  if (DOM.bulkRejectBtn) DOM.bulkRejectBtn.style.display = hasSelection ? 'inline-block' : 'none';
  if (DOM.selectionCount) {
    DOM.selectionCount.style.display = hasSelection ? 'inline-block' : 'none';
    DOM.selectionCount.textContent = `${count} selected`;
  }

  // Visual cue: add class to grid when in select mode
  DOM.imageGrid?.classList.toggle('select-mode', inSelectMode);
}

function toggleSelectMode() {
  AppState.selectMode = !AppState.selectMode;
  if (!AppState.selectMode) {
    // Exiting select mode: clear selection
    AppState.selectedImages.clear();
    DOM.imageGrid?.querySelectorAll('.grid-item.selected').forEach((el) => el.classList.remove('selected'));
  }
  updateBulkActionUI();
}

function selectAllImages() {
  AppState.images.forEach((img) => AppState.selectedImages.add(img.id));
  DOM.imageGrid?.querySelectorAll('.grid-item').forEach((el) => el.classList.add('selected'));
  updateBulkActionUI();
}

function deselectAllImages() {
  AppState.selectedImages.clear();
  DOM.imageGrid?.querySelectorAll('.grid-item.selected').forEach((el) => el.classList.remove('selected'));
  updateBulkActionUI();
}

function setLoading(state) {
  AppState.loading = state;
  DOM.loadingIndicator?.classList.toggle('hidden', !state);
}

function showToast(message, type = 'info') {
  const container = DOM.toastContainer;
  if (!container) { console.log(`[toast] ${type}: ${message}`); return; }

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  toast.style.animation = 'slideIn 0.3s ease';
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

function escapeHtml(text) {
  if (!text) return '';
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return String(text).replace(/[&<>"']/g, (m) => map[m]);
}

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

// ============================================================================
// Event Binding (attach to static HTML elements)
// ============================================================================

function bindEvents() {
  // Filter bar (static HTML elements)
  let searchTimeout;
  DOM.searchInput?.addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      AppState.filters.search = e.target.value;
      AppState.currentPage = 1;
      loadImages();
    }, 300);
  });

  DOM.statusFilter?.addEventListener('change', (e) => {
    AppState.filters.status = e.target.value;
    AppState.currentPage = 1;
    loadImages();
  });

  DOM.sortSelect?.addEventListener('change', (e) => {
    AppState.filters.sort = e.target.value;
    AppState.currentPage = 1;
    loadImages();
  });

  // Game search
  DOM.gameSearch?.addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase();
    const filtered = AppState.games.filter((g) => g.name.toLowerCase().includes(q));
    renderGameList(filtered);
  });

  // Sidebar toggle (mobile)
  DOM.sidebarToggle?.addEventListener('click', () => {
    document.getElementById('sidebar')?.classList.toggle('sidebar-open');
  });

  // Buttons
  DOM.scanBtn?.addEventListener('click', scanDirectory);
  DOM.selectModeBtn?.addEventListener('click', toggleSelectMode);
  DOM.selectAllBtn?.addEventListener('click', selectAllImages);
  DOM.deselectAllBtn?.addEventListener('click', deselectAllImages);
  DOM.bulkAcceptBtn?.addEventListener('click', () => bulkAction('accept'));
  DOM.bulkRejectBtn?.addEventListener('click', () => bulkAction('reject'));
  DOM.reviewModeBtn?.addEventListener('click', () => {
    if (AppState.images.length > 0) {
      openReviewMode(AppState.images[0]);
    } else {
      showToast('No images to review', 'info');
    }
  });
  DOM.purgeRejectedBtn?.addEventListener('click', purgeRejected);
  DOM.statsBtn?.addEventListener('click', loadAndShowStats);

  // Review overlay buttons
  DOM.reviewClose?.addEventListener('click', exitReviewMode);
  DOM.reviewPrev?.addEventListener('click', previousImage);
  DOM.reviewNext?.addEventListener('click', nextImage);

  // Review action buttons (data-action attribute)
  DOM.reviewActions?.querySelectorAll('.action-btn[data-action]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const action = btn.dataset.action;
      if (action === 'undo') undoLastAction();
      else reviewAction(action);
    });
  });

  // Rating buttons
  DOM.reviewRating?.querySelectorAll('.rating-btn[data-rating]').forEach((btn) => {
    btn.addEventListener('click', () => rateImage(parseInt(btn.dataset.rating)));
  });

  // Tag modal
  DOM.editTagsBtn?.addEventListener('click', loadAndShowTags);
  DOM.closeTagModal?.addEventListener('click', () => DOM.tagModal?.classList.add('hidden'));
  DOM.tagModal?.querySelector('.modal-backdrop')?.addEventListener('click', () => DOM.tagModal?.classList.add('hidden'));

  // Stats modal
  DOM.closeStatsModal?.addEventListener('click', () => DOM.statsModal?.classList.add('hidden'));
  DOM.statsModal?.querySelector('.modal-backdrop')?.addEventListener('click', () => DOM.statsModal?.classList.add('hidden'));

  // Touch swipe on review image
  let touchStartX = 0;
  DOM.reviewImage?.addEventListener('touchstart', (e) => { touchStartX = e.touches[0].clientX; });
  DOM.reviewImage?.addEventListener('touchend', (e) => {
    const diff = touchStartX - e.changedTouches[0].clientX;
    if (Math.abs(diff) > 50) {
      if (diff > 0) nextImage();
      else previousImage();
    }
  });

  // Global keydown listener for modals and review mode activation
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      // Close modals first (higher priority)
      if (!DOM.tagModal?.classList.contains('hidden')) {
        DOM.tagModal.classList.add('hidden');
        return;
      }
      if (!DOM.statsModal?.classList.contains('hidden')) {
        DOM.statsModal.classList.add('hidden');
        return;
      }
      // Review mode Escape is handled by handleReviewKeyboard
    }

    // Open review mode with 'R' key (when not in input and images are loaded)
    if (e.key.toLowerCase() === 'r') {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
      if (!AppState.reviewMode && AppState.images.length > 0) {
        e.preventDefault();
        openReviewMode(AppState.images[0]);
      }
    }
  });
}

// ============================================================================
// Global Error Handling
// ============================================================================

window.addEventListener('unhandledrejection', (event) => {
  console.error('Unhandled rejection:', event.reason);
  event.preventDefault();
});

// ============================================================================
// Service Worker
// ============================================================================

function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  navigator.serviceWorker.register('/sw.js', { scope: '/' })
    .then((reg) => {
      console.log('[PWA] SW registered');
      reg.addEventListener('updatefound', () => {
        const newWorker = reg.installing;
        newWorker?.addEventListener('statechange', () => {
          if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
            showToast('New version available! Refreshing...', 'info');
            newWorker.postMessage({ type: 'SKIP_WAITING' });
          }
        });
      });
    })
    .catch((err) => console.warn('[PWA] SW registration failed:', err));

  let refreshing = false;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (refreshing) return;
    refreshing = true;
    window.location.reload();
  });
}

// ============================================================================
// Init
// ============================================================================

async function init() {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
    return;
  }

  cacheDOMRefs();
  bindEvents();

  try {
    await loadGames();
    await loadImages();
    registerServiceWorker();
    showToast('VN CG Viewer loaded', 'success');
  } catch (error) {
    console.error('Init failed:', error);
    showToast('Failed to initialize. Check connection and refresh.', 'error');
  }
}

init();
