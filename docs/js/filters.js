/**
 * 筛选/排序/分类导航/URL状态管理
 */

import { state, dom } from './state.js';
import { debugLog, escapeHTML, escapeAttribute } from './utils.js';
import { isPreprint, hasPDF, recommendationScore, sortTimestamp, createPaperHTML } from './paper-card.js';
import { updateSummaryActionStates } from './dashboard.js';

// ===== 分类辅助函数 =====

function splitCategory(category) {
    return category.split('/').map(part => part.trim()).filter(Boolean);
}

function categoryDepth(category) {
    return category === 'all' ? 0 : splitCategory(category).length;
}

function categoryLabel(category) {
    if (category === 'all') return '全部';
    const parts = splitCategory(category);
    return parts[parts.length - 1] || category;
}

function parentCategory(category) {
    const parts = splitCategory(category);
    if (parts.length <= 1) return '';
    return parts.slice(0, -1).join(' / ');
}

function childCategories(parent) {
    parent = parent === 'all' ? '' : parent;
    const parentDepth = parent ? categoryDepth(parent) : 0;
    return window.CATEGORIES.filter(category => {
        if (!parent) return categoryDepth(category) === 1;
        return parentCategory(category) === parent && categoryDepth(category) === parentDepth + 1;
    });
}

function categoryCount(category) {
    return state.allPapersData.filter(paper => {
        const status = isPreprint(paper) ? 'preprint' : 'published';
        const tags = paper.tags || [];
        const matchPdf = state.currentPdf === 'all' || (state.currentPdf === 'available' ? hasPDF(paper) : !hasPDF(paper));
        return (state.currentStatus === 'all' || status === state.currentStatus) && matchPdf && tags.includes(category);
    }).length;
}

// ===== 分类导航渲染 =====

export function renderCategoryNav() {
    if (!dom.categoryFilters) return;
    const visibleCategories = childCategories(state.currentCategory);
    const currentLabel = state.currentCategory === 'all' ? '全部领域' : categoryLabel(state.currentCategory);
    const backTarget = state.currentCategory === 'all' ? '' : parentCategory(state.currentCategory) || 'all';
    const currentCount = state.currentCategory === 'all'
        ? state.allPapersData.filter(paper => {
            const status = isPreprint(paper) ? 'preprint' : 'published';
            const matchPdf = state.currentPdf === 'all' || (state.currentPdf === 'available' ? hasPDF(paper) : !hasPDF(paper));
            return (state.currentStatus === 'all' || status === state.currentStatus) && matchPdf;
        }).length
        : categoryCount(state.currentCategory);

    let html = `<div class="category-breadcrumb">`;
    if (state.currentCategory !== 'all') {
        html += `<button class="filter-btn category-back-btn" data-category-back="${escapeAttribute(backTarget)}">返回上一级</button>`;
    }
    html += `<button class="filter-btn category-btn active" data-category="${escapeAttribute(state.currentCategory)}">${escapeHTML(currentLabel)} (${currentCount})</button>`;
    html += `</div>`;

    if (visibleCategories.length > 0) {
        const depth = splitCategory(state.currentCategory).length;
        html += `<div class="category-children" data-depth="${depth}">`;
        visibleCategories.forEach(category => {
            html += `<button class="filter-btn category-btn" data-category="${escapeAttribute(category)}">${escapeHTML(categoryLabel(category))} (${categoryCount(category)})</button>`;
        });
        html += `</div>`;
    }

    dom.categoryFilters.innerHTML = html;
    dom.categoryBtns = document.querySelectorAll('.category-btn');
}

// ===== 按钮计数更新 =====

export function updateStatusButtonCounts() {
    const categoryFilteredPapers = state.allPapersData.filter(paper => {
        const tags = paper.tags || [];
        const matchCategory = state.currentCategory === 'all' || tags.includes(state.currentCategory);
        const matchPdf = state.currentPdf === 'all' || (state.currentPdf === 'available' ? hasPDF(paper) : !hasPDF(paper));
        return matchCategory && matchPdf;
    });

    let publishedCount = 0;
    let preprintCount = 0;
    categoryFilteredPapers.forEach(paper => {
        if (!isPreprint(paper)) {
            publishedCount++;
        } else {
            preprintCount++;
        }
    });

    dom.statusBtns.forEach(btn => {
        const status = btn.dataset.status;
        if (status === 'all') {
            btn.textContent = `全部 (${categoryFilteredPapers.length})`;
        } else if (status === 'published') {
            btn.textContent = `已发表 (${publishedCount})`;
        } else if (status === 'preprint') {
            btn.textContent = `预印本 (${preprintCount})`;
        }
    });
}

export function updateCategoryButtonCounts() {
    renderCategoryNav();
}

export function updatePDFButtonCounts() {
    const statusCategoryFilteredPapers = state.allPapersData.filter(paper => {
        const status = isPreprint(paper) ? 'preprint' : 'published';
        const tags = paper.tags || [];
        const matchStatus = state.currentStatus === 'all' || status === state.currentStatus;
        const matchCategory = state.currentCategory === 'all' || tags.includes(state.currentCategory);
        return matchStatus && matchCategory;
    });

    const availableCount = statusCategoryFilteredPapers.filter(hasPDF).length;
    const missingCount = statusCategoryFilteredPapers.length - availableCount;

    dom.pdfBtns.forEach(btn => {
        const pdf = btn.dataset.pdf;
        if (pdf === 'all') {
            btn.textContent = `全部 (${statusCategoryFilteredPapers.length})`;
        } else if (pdf === 'available') {
            btn.textContent = `有PDF (${availableCount})`;
        } else if (pdf === 'missing') {
            btn.textContent = `无PDF (${missingCount})`;
        }
    });
}

// ===== URL 状态管理 =====

export function saveStateToURL() {
    const params = new URLSearchParams();
    if (state.currentMonth !== 'all') params.set('month', state.currentMonth);
    if (state.currentStatus !== 'all') params.set('status', state.currentStatus);
    if (state.currentPdf !== 'all') params.set('pdf', state.currentPdf);
    if (state.currentCategory !== 'all') params.set('category', state.currentCategory);
    if (state.currentSort !== 'date-desc') params.set('sort', state.currentSort);
    if (state.currentDate) params.set('date', state.currentDate);
    if (state.currentSpecial) params.set('special', state.currentSpecial);
    if (state.searchTerm) params.set('q', state.searchTerm);
    const hash = params.toString();
    history.replaceState(null, '', hash ? '#' + hash : window.location.pathname);
}

// ===== 筛选和排序 =====

export function filterAndSortPapers() {
    debugLog('Filtering papers:', { currentStatus: state.currentStatus, currentPdf: state.currentPdf, currentCategory: state.currentCategory, searchTerm: state.searchTerm, currentSort: state.currentSort });

    // 筛选
    state.filteredPapers = state.allPapersData.filter(paper => {
        const status = isPreprint(paper) ? 'preprint' : 'published';
        const tags = paper.tags || [];
        const text = `${paper.title} ${paper.authors} ${paper.abstract}`.toLowerCase();

        const matchStatus = state.currentStatus === 'all' || status === state.currentStatus;
        const matchPdf = state.currentPdf === 'all' || (state.currentPdf === 'available' ? hasPDF(paper) : !hasPDF(paper));
        const matchCategory = state.currentCategory === 'all' || tags.includes(state.currentCategory);
        const matchSearch = state.searchTerm === '' || text.includes(state.searchTerm);
        const matchDate = !state.currentDate || paper.published === state.currentDate;
        const matchSpecial = state.currentSpecial !== 'early-access' || paper.is_early_access === true;

        return matchStatus && matchPdf && matchCategory && matchSearch && matchDate && matchSpecial;
    });

    debugLog(`Filtered to ${state.filteredPapers.length} papers`);

    // 排序
    state.filteredPapers.sort((a, b) => {
        const dateA = sortTimestamp(a);
        const dateB = sortTimestamp(b);

        if (state.currentSort === 'date-desc') {
            return dateB - dateA;
        } else if (state.currentSort === 'date-asc') {
            return dateA - dateB;
        } else if (state.currentSort === 'importance-desc') {
            const scoreDiff = recommendationScore(b) - recommendationScore(a);
            if (scoreDiff !== 0) return scoreDiff;
            return dateB - dateA;
        }
        return 0;
    });

    // 更新按钮数量和显示
    updateStatusButtonCounts();
    updatePDFButtonCounts();
    updateCategoryButtonCounts();
    updateSummaryActionStates();
    if (dom.resultsCount) {
        dom.resultsCount.textContent = state.currentDate
            ? `${state.currentDate} 新增 ${state.filteredPapers.length} 篇论文`
            : `显示 ${state.filteredPapers.length} 篇论文`;
    }

    // 重置懒加载
    state.loadedCount = 0;
    if (dom.papersContainer) {
        dom.papersContainer.innerHTML = '';
    }
    if (state.observer) {
        state.observer.disconnect();
    }

    // 加载第一批
    loadMorePapers();

    // 将筛选状态保存到 URL hash
    saveStateToURL();
}

// ===== 懒加载 =====

export function loadMorePapers() {
    if (state.isLoading || state.loadedCount >= state.filteredPapers.length) {
        debugLog('Skip loading:', { isLoading: state.isLoading, loadedCount: state.loadedCount, total: state.filteredPapers.length });
        return;
    }

    state.isLoading = true;
    const batchSize = state.loadedCount === 0 ? state.initialBatchSize : state.subsequentBatchSize;
    const endIndex = Math.min(state.loadedCount + batchSize, state.filteredPapers.length);
    const fragment = document.createDocumentFragment();

    for (let i = state.loadedCount; i < endIndex; i++) {
        const paperHTML = createPaperHTML(state.filteredPapers[i]);
        const temp = document.createElement('div');
        temp.innerHTML = paperHTML;
        fragment.appendChild(temp.firstElementChild);
    }

    // 移除旧加载指示器
    const oldIndicator = document.getElementById('loading-indicator');
    if (oldIndicator) {
        oldIndicator.remove();
    }

    dom.papersContainer.appendChild(fragment);
    state.loadedCount = endIndex;
    state.isLoading = false;

    // 设置加载触发器
    if (state.loadedCount < state.filteredPapers.length) {
        setupLoadTrigger();
    }
}

export function setupLoadTrigger() {
    let indicator = document.getElementById('loading-indicator');
    if (!indicator) {
        indicator = document.createElement('div');
        indicator.id = 'loading-indicator';
        indicator.className = 'loading-indicator';
        indicator.style.height = '100px';
        indicator.style.margin = '20px 0';
        indicator.style.textAlign = 'center';
        indicator.style.color = '#666';
        indicator.textContent = '加载更多...';
        dom.papersContainer.appendChild(indicator);
    }

    if (state.observer) {
        state.observer.disconnect();
    }

    state.observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                loadMorePapers();
            }
        });
    }, { rootMargin: '200px' });

    state.observer.observe(indicator);
}
