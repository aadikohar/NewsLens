/* ──────────────────────────────────────────────────────────────
   NewsLens – Dashboard JavaScript
   ────────────────────────────────────────────────────────────── */

const API = '/api';

// ── State ────────────────────────────────────────────────────────
let allTopics             = [];
let allSources            = [];
let currentView           = 'topics'; // 'topics' | 'sources' | 'compare'
let currentCategoryFilter = 'all';
let modalAvailableArticles = [];
let selectedArticleIds     = new Set();

const CATEGORY_MAP = {
    cyclone:  ['cyclone', 'arnab', 'weather', 'rain', 'flood', 'shelter', 'odisha', 'andhra'],
    election: ['election', 'poll', 'vote', 'bjp', 'congress', 'mlc', 'india bloc', 'party', 'fadnavis', 'stalin'],
    court:    ['court', 'hc', 'judge', 'arrest', 'police', 'cbi', 'ed', 'dvac', 'bail', 'case', 'murder', 'law'],
    market:   ['market', 'stock', 'ipo', 'bank', 'pnb', 'crore', 'economy', 'gold', 'invest', 'rupee', 'profit'],
    modi:     ['modi', 'pm', 'centre', 'minister', 'jaishankar', 'govt', 'delhi', 'union'],
};

// ── DOM refs ─────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

const els = {
    topicsSection:        $('topics-section'),
    sourcesSection:       $('sources-section'),
    compareSection:       $('compare-section'),
    topicsContainer:      $('topics-container'),
    topicsSkeleton:       $('topics-skeleton'),
    topicsEmpty:          $('topics-empty'),
    topicsCountLbl:       $('topics-count-label'),
    sourcesContainer:     $('sources-container'),
    sourcesSkeleton:      $('sources-skeleton'),
    sourcesEmpty:         $('sources-empty'),
    sourcesCountLbl:      $('sources-count-label'),
    compareContainer:     $('compare-container'),
    compareSkeleton:      $('compare-skeleton'),
    compareEmpty:         $('compare-empty'),
    compareTitle:         $('compare-title'),
    compareSubtitle:      $('compare-subtitle'),
    statsBar:             $('stats-bar'),
    spectrumWrap:         $('spectrum-wrap'),
    spectrumMarkers:      $('spectrum-markers'),
    backBtn:              $('back-btn'),
    searchInput:          $('search-input'),
    searchClear:          $('search-clear'),
    sortSelect:           $('sort-select'),
    navTopicsBtn:         $('nav-topics-btn'),
    navSourcesBtn:        $('nav-sources-btn'),
    statusDot:            $('status-dot'),
    statusLabel:          $('status-label'),
    toast:                $('toast'),

    // Add topic & clustering actions
    addTopicBtn:          $('add-topic-btn'),
    clusterTopicsBtn:     $('cluster-topics-btn'),
    topicFilterPills:     $('topic-filter-pills'),

    // Add Topic Modal
    addTopicModal:        $('add-topic-modal'),
    modalCloseBtn:        $('modal-close-btn'),
    modalCancelBtn:       $('modal-cancel-btn'),
    addTopicForm:         $('add-topic-form'),
    topicTitleInput:      $('topic-title-input'),
    tabKeywordBtn:        $('tab-keyword-btn'),
    tabSelectBtn:         $('tab-select-btn'),
    tabKeywordContent:    $('tab-keyword-content'),
    tabSelectContent:     $('tab-select-content'),
    topicKeywordInput:    $('topic-keyword-input'),
    keywordMatchPreview:  $('keyword-match-preview'),
    matchPreviewCount:    $('match-preview-count'),
    articleSearchInput:   $('article-search-input'),
    modalArticlesList:    $('modal-articles-list'),
    selectionCount:       $('selection-count'),
    selectAllBtn:         $('select-all-btn'),
    modalSubmitBtn:       $('modal-submit-btn'),
};

// ── Toast notification ────────────────────────────────────────────
let toastTimer;
function showToast(msg, isError = false) {
    clearTimeout(toastTimer);
    els.toast.textContent = msg;
    els.toast.classList.toggle('error', isError);
    els.toast.classList.remove('hidden');
    toastTimer = setTimeout(() => els.toast.classList.add('hidden'), 3500);
}

// ── Health check ──────────────────────────────────────────────────
async function checkHealth() {
    try {
        const res = await fetch(`${API}/health`);
        if (res.ok) {
            els.statusDot.className   = 'status-dot online';
            els.statusLabel.textContent = 'Live';
        } else {
            throw new Error('Non-OK');
        }
    } catch {
        els.statusDot.className    = 'status-dot offline';
        els.statusLabel.textContent = 'Offline';
    }
}

// ── Helpers ──────────────────────────────────────────────────────
function sentClass(val) {
    if (val === null || val === undefined || isNaN(val)) return 'neu';
    if (val > 0.05) return 'pos';
    if (val < -0.05) return 'neg';
    return 'neu';
}

function fmtSent(val) {
    if (val === null || val === undefined || isNaN(val)) return 'N/A';
    return (val >= 0 ? '+' : '') + Number(val).toFixed(3);
}

function fmtDate(str) {
    if (!str) return '';
    try {
        return new Date(str).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    } catch {
        return str;
    }
}

function biasColor(loadedPct) {
    if (loadedPct === null || loadedPct === undefined) return 'var(--border)';
    if (loadedPct < 10) return 'var(--positive)';
    if (loadedPct < 25) return 'var(--highlight)';
    if (loadedPct < 45) return 'var(--warn)';
    return 'var(--negative)';
}

// ── Topics ───────────────────────────────────────────────────────
async function loadTopics() {
    els.topicsSkeleton.classList.remove('hidden');
    els.topicsContainer.classList.add('hidden');
    els.topicsEmpty.classList.add('hidden');

    try {
        const res  = await fetch(`${API}/topics`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        allTopics = await res.json();
        renderTopics(allTopics);
    } catch (err) {
        console.error(err);
        showToast('Failed to load topics. Is the server running?', true);
        els.topicsSkeleton.classList.add('hidden');
        els.topicsEmpty.classList.remove('hidden');
    }
}

function sortTopics(topics) {
    const key = els.sortSelect.value;
    return [...topics].sort((a, b) => {
        if (key === 'article_count') return (b.article_count || 0) - (a.article_count || 0);
        if (key === 'title') return (a.title || '').localeCompare(b.title || '');
        if (key === 'created_at') return (b.created_at || '').localeCompare(a.created_at || '');
        return 0;
    });
}

function renderTopics(topics) {
    els.topicsSkeleton.classList.add('hidden');
    const query = els.searchInput.value.trim().toLowerCase();

    // 1. Text Search Filter
    let filtered = query
        ? topics.filter(t => (t.title || '').toLowerCase().includes(query))
        : topics;

    // 2. Category Pill Filter
    if (currentCategoryFilter !== 'all') {
        const keywords = CATEGORY_MAP[currentCategoryFilter] || [];
        filtered = filtered.filter(t => {
            const titleLower = (t.title || '').toLowerCase();
            return keywords.some(kw => titleLower.includes(kw));
        });
    }

    const sorted = sortTopics(filtered);

    els.topicsCountLbl.textContent = `${sorted.length} topic${sorted.length !== 1 ? 's' : ''} available`;

    if (!sorted.length) {
        els.topicsContainer.classList.add('hidden');
        els.topicsEmpty.classList.remove('hidden');
        return;
    }

    els.topicsEmpty.classList.add('hidden');
    els.topicsContainer.innerHTML = '';
    sorted.forEach(t => els.topicsContainer.appendChild(createTopicCard(t)));
    els.topicsContainer.classList.remove('hidden');
}

function createTopicCard(topic) {
    const card = document.createElement('div');
    card.className = 'topic-card';
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    card.setAttribute('aria-label', `View topic: ${topic.title || 'Untitled'}`);

    const count = topic.article_count || 0;
    card.innerHTML = `
        <div class="topic-card-top">
            <div class="topic-badge">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                Topic #${topic.topic_id}
            </div>
            <button class="topic-delete-btn" title="Delete this topic" aria-label="Delete topic">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
        </div>
        <div class="topic-title">${escHtml(topic.title || 'Untitled Topic')}</div>
        <div class="topic-meta">
            <span class="topic-count">${count} article${count !== 1 ? 's' : ''}</span>
            <div class="topic-arrow">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            </div>
        </div>
    `;

    const delBtn = card.querySelector('.topic-delete-btn');
    delBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteTopic(topic.topic_id, topic.title);
    });

    const open = () => loadCompareTopic(topic.topic_id, topic.title || 'Untitled Topic');
    card.addEventListener('click', open);
    card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') open(); });

    return card;
}

// ── Delete Topic ──────────────────────────────────────────────────
async function deleteTopic(topicId, title) {
    if (!confirm(`Are you sure you want to delete topic #${topicId} ("${title || 'Untitled'}")?\n\nIts articles will be unlinked and available for new topics.`)) {
        return;
    }
    try {
        const res = await fetch(`${API}/topics/${topicId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        showToast(`Topic #${topicId} deleted.`);
        await loadTopics();
    } catch (err) {
        console.error(err);
        showToast(`Failed to delete topic: ${err.message}`, true);
    }
}

// ── Auto-Cluster Action ───────────────────────────────────────────
async function triggerAutoCluster() {
    const origText = els.clusterTopicsBtn.innerHTML;
    els.clusterTopicsBtn.disabled = true;
    els.clusterTopicsBtn.innerHTML = `<span>Clustering…</span>`;

    try {
        const res = await fetch(`${API}/topics/cluster`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ similarity_threshold: 0.22 })
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        showToast(`Auto-clustering complete! ${data.new_topics} new topics detected.`);
        await loadTopics();
    } catch (err) {
        console.error(err);
        showToast('Auto-clustering failed.', true);
    } finally {
        els.clusterTopicsBtn.disabled = false;
        els.clusterTopicsBtn.innerHTML = origText;
    }
}

// ── Add Topic Modal ───────────────────────────────────────────────
function openAddTopicModal() {
    els.addTopicModal.classList.remove('hidden');
    els.topicTitleInput.value = '';
    els.topicKeywordInput.value = '';
    els.keywordMatchPreview.classList.add('hidden');
    selectedArticleIds.clear();
    updateSelectionCount();

    // Default to keyword tab
    switchModalTab('keyword');
    els.topicTitleInput.focus();

    // Fetch available articles for selection tab
    loadModalArticles();
}

function closeAddTopicModal() {
    els.addTopicModal.classList.add('hidden');
}

function switchModalTab(tab) {
    if (tab === 'keyword') {
        els.tabKeywordBtn.classList.add('active');
        els.tabSelectBtn.classList.remove('active');
        els.tabKeywordContent.classList.remove('hidden');
        els.tabSelectContent.classList.add('hidden');
    } else {
        els.tabSelectBtn.classList.add('active');
        els.tabKeywordBtn.classList.remove('active');
        els.tabSelectContent.classList.remove('hidden');
        els.tabKeywordContent.classList.add('hidden');
    }
}

let keywordDebounceTimer;
function onKeywordInputChange() {
    clearTimeout(keywordDebounceTimer);
    const kw = els.topicKeywordInput.value.trim();
    if (!kw) {
        els.keywordMatchPreview.classList.add('hidden');
        return;
    }
    keywordDebounceTimer = setTimeout(async () => {
        try {
            const res = await fetch(`${API}/articles/match-keywords?keywords=${encodeURIComponent(kw)}`);
            if (res.ok) {
                const data = await res.json();
                els.matchPreviewCount.textContent = data.count || 0;
                els.keywordMatchPreview.classList.remove('hidden');
            }
        } catch (e) {
            console.error(e);
        }
    }, 350);
}

async function loadModalArticles() {
    els.modalArticlesList.innerHTML = '<div class="loading-spinner" style="padding: 1rem; color: var(--text-muted);">Loading articles…</div>';
    try {
        const res = await fetch(`${API}/articles?limit=120`);
        if (!res.ok) throw new Error('Failed to load articles');
        const data = await res.json();
        modalAvailableArticles = data.articles || [];
        renderModalArticlesList(modalAvailableArticles);
    } catch (err) {
        els.modalArticlesList.innerHTML = '<div style="padding: 1rem; color: var(--negative);">Failed to load articles.</div>';
    }
}

function renderModalArticlesList(articles) {
    const q = (els.articleSearchInput.value || '').trim().toLowerCase();
    const filtered = q
        ? articles.filter(a => (a.headline || '').toLowerCase().includes(q))
        : articles;

    if (!filtered.length) {
        els.modalArticlesList.innerHTML = '<div style="padding: 1rem; color: var(--text-muted); text-align: center;">No matching articles.</div>';
        return;
    }

    els.modalArticlesList.innerHTML = '';
    filtered.forEach(a => {
        const item = document.createElement('label');
        item.className = 'modal-article-item';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = a.article_id;
        checkbox.checked = selectedArticleIds.has(a.article_id);

        checkbox.addEventListener('change', () => {
            if (checkbox.checked) selectedArticleIds.add(a.article_id);
            else selectedArticleIds.delete(a.article_id);
            updateSelectionCount();
        });

        const info = document.createElement('div');
        info.className = 'modal-article-info';
        info.innerHTML = `
            <div class="modal-article-title">${escHtml(a.headline)}</div>
            <div class="modal-article-meta">
                <span class="modal-article-src">${escHtml(a.source_name)}</span>
                <span>${fmtDate(a.publication_date)}</span>
            </div>
        `;

        item.appendChild(checkbox);
        item.appendChild(info);
        els.modalArticlesList.appendChild(item);
    });
}

function updateSelectionCount() {
    els.selectionCount.textContent = `${selectedArticleIds.size} article${selectedArticleIds.size !== 1 ? 's' : ''} selected`;
}

async function submitAddTopic(e) {
    e.preventDefault();
    const title = els.topicTitleInput.value.trim();
    if (!title) {
        showToast('Please enter a topic title.', true);
        return;
    }

    const payload = {
        title: title,
        keywords: els.topicKeywordInput.value.trim(),
        article_ids: Array.from(selectedArticleIds)
    };

    const submitBtn = els.modalSubmitBtn;
    const origText = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span>Creating…</span>';

    try {
        const res = await fetch(`${API}/topics`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || `HTTP ${res.status}`);
        }
        const data = await res.json();
        const count = data.topic ? data.topic.article_count : 0;
        showToast(`Topic "${title}" added with ${count} articles!`);
        closeAddTopicModal();
        await loadTopics();
    } catch (err) {
        console.error(err);
        showToast(`Failed to create topic: ${err.message}`, true);
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = origText;
    }
}

// ── Sources ──────────────────────────────────────────────────────
async function loadSources() {
    els.sourcesSkeleton.classList.remove('hidden');
    els.sourcesContainer.classList.add('hidden');
    els.sourcesEmpty.classList.add('hidden');

    try {
        const res = await fetch(`${API}/sources`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        allSources = await res.json();
        renderSources(allSources);
    } catch (err) {
        console.error(err);
        showToast('Failed to load sources.', true);
        els.sourcesSkeleton.classList.add('hidden');
        els.sourcesEmpty.classList.remove('hidden');
    }
}

function renderSources(sources) {
    els.sourcesSkeleton.classList.add('hidden');
    els.sourcesCountLbl.textContent = `${sources.length} source${sources.length !== 1 ? 's' : ''} configured`;

    if (!sources.length) {
        els.sourcesContainer.classList.add('hidden');
        els.sourcesEmpty.classList.remove('hidden');
        return;
    }

    els.sourcesEmpty.classList.add('hidden');
    els.sourcesContainer.innerHTML = '';
    sources.forEach(s => els.sourcesContainer.appendChild(createSourceCard(s)));
    els.sourcesContainer.classList.remove('hidden');
}

function createSourceCard(src) {
    const card = document.createElement('div');
    card.className = 'source-card';
    const isEnabled = src.enabled === 1 || src.enabled === true;
    card.innerHTML = `
        <div class="source-card-header">
            <div class="source-card-name">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 11a9 9 0 0 1 9 9"/><path d="M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1"/></svg>
                ${escHtml(src.name)}
            </div>
            <span class="source-status-badge ${isEnabled ? 'enabled' : 'disabled'}">${isEnabled ? 'Active' : 'Disabled'}</span>
        </div>
        <a class="source-feed-url" href="${escHtml(src.feed_url)}" target="_blank" rel="noopener noreferrer">${escHtml(src.feed_url)}</a>
        <div class="source-timestamps">
            ${src.last_success ? `<span class="source-ts-ok">✓ Last success: ${fmtDate(src.last_success)}</span>` : '<span>No successful fetch recorded</span>'}
            ${src.last_error   ? `<span class="source-ts-err">✗ Last error: ${escHtml(src.last_error)}</span>` : ''}
        </div>
    `;
    return card;
}

// ── Compare Topic ─────────────────────────────────────────────────
async function loadCompareTopic(topicId, title) {
    showView('compare');
    els.compareTitle.textContent     = title;
    els.compareSubtitle.textContent  = 'Loading articles…';
    els.statsBar.classList.add('hidden');
    els.spectrumWrap.classList.add('hidden');
    els.compareContainer.innerHTML   = '';
    els.compareEmpty.classList.add('hidden');
    els.compareSkeleton.classList.remove('hidden');

    try {
        const res = await fetch(`${API}/topics/${topicId}/compare`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        els.compareSkeleton.classList.add('hidden');
        renderCompare(data, title);
    } catch (err) {
        console.error(err);
        els.compareSkeleton.classList.add('hidden');
        showToast(`Failed to load topic #${topicId}.`, true);
        els.compareEmpty.classList.remove('hidden');
    }
}

function renderCompare(data, title) {
    const articles = data.articles || [];
    els.compareSubtitle.textContent = `${articles.length} article${articles.length !== 1 ? 's' : ''} from ${new Set(articles.map(a => a.source_name)).size} source${new Set(articles.map(a => a.source_name)).size !== 1 ? 's' : ''}`;

    if (!articles.length) {
        els.compareEmpty.classList.remove('hidden');
        return;
    }

    const analyzed = articles.filter(a => a.headline_sentiment !== null && a.headline_sentiment !== undefined);
    const avgSent  = analyzed.length ? analyzed.reduce((s, a) => s + (a.headline_sentiment || 0), 0) / analyzed.length : null;
    const avgLoad  = analyzed.length ? analyzed.reduce((s, a) => s + (a.loaded_wording_pct || 0), 0) / analyzed.length : null;
    const mostLoadedSrc = analyzed.length ? analyzed.reduce((m, a) => (a.loaded_wording_pct || 0) > (m.loaded_wording_pct || 0) ? a : m, analyzed[0]) : null;

    $('stat-sources-val').textContent    = new Set(articles.map(a => a.source_name)).size;
    $('stat-sentiment-val').textContent  = avgSent !== null ? fmtSent(avgSent) : 'N/A';
    $('stat-loaded-val').textContent     = avgLoad !== null ? avgLoad.toFixed(1) + '%' : 'N/A';
    $('stat-most-biased-val').textContent = mostLoadedSrc ? escHtml(mostLoadedSrc.source_name) : 'N/A';
    els.statsBar.classList.remove('hidden');

    buildSpectrum(analyzed);

    articles.forEach(a => els.compareContainer.appendChild(createArticleCard(a)));
}

function buildSpectrum(articles) {
    els.spectrumMarkers.innerHTML = '';
    if (!articles.length) return;

    articles.forEach(a => {
        const score = a.headline_sentiment ?? 0;
        const pct = ((score + 1) / 2) * 100;
        const dot = document.createElement('div');
        dot.className = 'spectrum-dot';
        dot.style.left = `${pct}%`;
        dot.style.background = score > 0.05 ? 'var(--positive)' : score < -0.05 ? 'var(--negative)' : 'var(--neutral)';
        dot.title = `${a.source_name}: ${fmtSent(score)}`;
        els.spectrumMarkers.appendChild(dot);
    });

    els.spectrumWrap.classList.remove('hidden');
}

function createArticleCard(article) {
    const card = document.createElement('div');
    card.className = 'article-card';

    const loadedPct = article.loaded_wording_pct ?? 0;
    card.style.setProperty('--bias-color', biasColor(loadedPct));

    const headSent = article.headline_sentiment;
    const bodySent = article.body_sentiment;
    const flagged  = Array.isArray(article.flagged_sentences) ? article.flagged_sentences : [];

    card.innerHTML = `
        <div class="article-source-row">
            <span class="article-source">${escHtml(article.source_name || 'Unknown')}</span>
            <span class="article-date">${fmtDate(article.publication_date)}</span>
        </div>

        <div class="article-headline">
            <a href="${escHtml(article.url || '#')}" target="_blank" rel="noopener noreferrer">${escHtml(article.headline || 'No headline')}</a>
        </div>

        <div class="article-metrics">
            <div class="metric-chip">
                <span class="metric-chip-label">Headline</span>
                <span class="sent-badge ${sentClass(headSent)}">${fmtSent(headSent)}</span>
            </div>
            <div class="metric-chip">
                <span class="metric-chip-label">Body</span>
                <span class="sent-badge ${sentClass(bodySent)}">${fmtSent(bodySent)}</span>
            </div>
            <div class="metric-chip bias-chip">
                <span class="metric-chip-label">Loaded Words</span>
                <span class="bias-pct">${loadedPct.toFixed(1)}%</span>
            </div>
        </div>

        ${flagged.length ? `
            <div class="flagged-section">
                <div class="flagged-header">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg>
                    Flagged Sentences (${flagged.length})
                </div>
                <ul class="flagged-list">
                    ${flagged.slice(0, 3).map(s => `<li>${escHtml(s)}</li>`).join('')}
                    ${flagged.length > 3 ? `<li class="flagged-more">+${flagged.length - 3} more sentence${flagged.length - 3 !== 1 ? 's' : ''}</li>` : ''}
                </ul>
            </div>
        ` : ''}

        <div class="article-card-footer">
            <a class="article-read-btn" href="${escHtml(article.url || '#')}" target="_blank" rel="noopener noreferrer">
                Read Original
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            </a>
        </div>
    `;

    return card;
}

// ── View switching ────────────────────────────────────────────────
function showView(view) {
    currentView = view;

    els.topicsSection.classList.toggle('hidden',  view !== 'topics');
    els.sourcesSection.classList.toggle('hidden', view !== 'sources');
    els.compareSection.classList.toggle('hidden', view !== 'compare');

    els.navTopicsBtn.classList.toggle('active',  view === 'topics');
    els.navSourcesBtn.classList.toggle('active', view === 'sources');

    document.querySelector('.hero').style.display = view === 'compare' ? 'none' : '';

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── Event listeners ───────────────────────────────────────────────
els.navTopicsBtn.addEventListener('click', () => {
    showView('topics');
    if (!allTopics.length) loadTopics();
});

els.navSourcesBtn.addEventListener('click', () => {
    showView('sources');
    if (!allSources.length) loadSources();
});

els.backBtn.addEventListener('click', () => {
    showView('topics');
});

// Search
els.searchInput.addEventListener('input', () => {
    const q = els.searchInput.value;
    els.searchClear.classList.toggle('hidden', !q);
    renderTopics(allTopics);
});

els.searchClear.addEventListener('click', () => {
    els.searchInput.value = '';
    els.searchClear.classList.add('hidden');
    renderTopics(allTopics);
    els.searchInput.focus();
});

// Sort
els.sortSelect.addEventListener('change', () => renderTopics(allTopics));

// Add Topic & Auto-Cluster Buttons
els.addTopicBtn.addEventListener('click', openAddTopicModal);
els.clusterTopicsBtn.addEventListener('click', triggerAutoCluster);

// Modal Controls
els.modalCloseBtn.addEventListener('click', closeAddTopicModal);
els.modalCancelBtn.addEventListener('click', closeAddTopicModal);
els.addTopicModal.addEventListener('click', (e) => {
    if (e.target === els.addTopicModal) closeAddTopicModal();
});
els.tabKeywordBtn.addEventListener('click', () => switchModalTab('keyword'));
els.tabSelectBtn.addEventListener('click', () => switchModalTab('select'));
els.topicKeywordInput.addEventListener('input', onKeywordInputChange);
els.articleSearchInput.addEventListener('input', () => renderModalArticlesList(modalAvailableArticles));
els.selectAllBtn.addEventListener('click', () => {
    const q = (els.articleSearchInput.value || '').trim().toLowerCase();
    const filtered = q
        ? modalAvailableArticles.filter(a => (a.headline || '').toLowerCase().includes(q))
        : modalAvailableArticles;
    filtered.forEach(a => selectedArticleIds.add(a.article_id));
    renderModalArticlesList(modalAvailableArticles);
    updateSelectionCount();
});
els.addTopicForm.addEventListener('submit', submitAddTopic);

// Category filter pills
els.topicFilterPills.addEventListener('click', (e) => {
    const btn = e.target.closest('.pill-btn');
    if (!btn) return;
    document.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentCategoryFilter = btn.dataset.filter || 'all';
    renderTopics(allTopics);
});

// ── Escape HTML ───────────────────────────────────────────────────
function escHtml(str) {
    return String(str ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// ── Init ──────────────────────────────────────────────────────────
(async function init() {
    await checkHealth();
    await loadTopics();
})();
