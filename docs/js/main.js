document.addEventListener('DOMContentLoaded', function() {
    const DEBUG = false;
    const debugLog = (...args) => {
if (DEBUG) console.log(...args);
    };

    // 获取DOM元素
    const monthBtns = document.querySelectorAll('.month-btn');
    const statusBtns = document.querySelectorAll('.status-btn');
    const pdfBtns = document.querySelectorAll('.pdf-btn');
    let categoryBtns = document.querySelectorAll('.category-btn');
    const categoryFilters = document.querySelector('.category-filters');
    const sortBtns = document.querySelectorAll('.sort-btn');
    const searchInput = document.getElementById('searchInput');
    const exportBtn = document.getElementById('exportBtn');
    const selectAllBtn = document.getElementById('selectAllBtn');
    const clearAllBtn = document.getElementById('clearAllBtn');
    const selectedCount = document.getElementById('selectedCount');
    const resultsCount = document.getElementById('resultsCount');
    const papersContainer = document.getElementById('papers-container');
    const dailyDatePicker = document.getElementById('dailyDatePicker');
    const summaryActions = document.querySelectorAll('.summary-action');

    debugLog('DOM elements:', {
monthBtns: monthBtns.length,
statusBtns: statusBtns.length,
pdfBtns: pdfBtns.length,
categoryBtns: categoryBtns.length,
sortBtns: sortBtns.length,
searchInput: !!searchInput,
exportBtn: !!exportBtn,
selectAllBtn: !!selectAllBtn,
clearAllBtn: !!clearAllBtn,
resultsCount: !!resultsCount,
papersContainer: !!papersContainer
    });

    // 状态变量
    let allPapersData = [];  // 所有论文数据
    let currentMonth = 'all';  // 当前选中的月份
    let currentStatus = 'all';
    let currentPdf = 'all';
    let currentCategory = 'all';
    let currentSort = 'date-desc';
    let currentDate = '';
    let currentSpecial = '';
    let searchTerm = '';
    let filteredPapers = [];
    let loadedCount = 0;
    const initialBatchSize = 20;  // 第一次加载20个
    const subsequentBatchSize = 10;  // 后续每次加载10个
    let isLoading = false;
    let observer = null;
    let monthsCache = {};  // 缓存已加载的月份数据
    let selectedPaperIds = new Set();
    let searchTimer = null;

    // 配置里的分类列表（从Python传入）
    
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
return CATEGORIES.filter(category => {
    if (!parent) return categoryDepth(category) === 1;
    return parentCategory(category) === parent && categoryDepth(category) === parentDepth + 1;
});
    }

    function categoryCount(category) {
return allPapersData.filter(paper => {
    const status = isPreprint(paper) ? 'preprint' : 'published';
    const tags = paper.tags || [];
    const matchPdf = currentPdf === 'all' || (currentPdf === 'available' ? hasPDF(paper) : !hasPDF(paper));
    return (currentStatus === 'all' || status === currentStatus) && matchPdf && tags.includes(category);
}).length;
    }

    function renderCategoryNav() {
if (!categoryFilters) return;
const visibleCategories = childCategories(currentCategory);
const currentLabel = currentCategory === 'all' ? '全部领域' : categoryLabel(currentCategory);
const backTarget = currentCategory === 'all' ? '' : parentCategory(currentCategory) || 'all';
const currentCount = currentCategory === 'all'
    ? allPapersData.filter(paper => {
        const status = isPreprint(paper) ? 'preprint' : 'published';
        const matchPdf = currentPdf === 'all' || (currentPdf === 'available' ? hasPDF(paper) : !hasPDF(paper));
        return (currentStatus === 'all' || status === currentStatus) && matchPdf;
    }).length
    : categoryCount(currentCategory);

let html = `<div class="category-breadcrumb">`;
if (currentCategory !== 'all') {
    html += `<button class="filter-btn category-back-btn" data-category-back="${escapeAttribute(backTarget)}">返回上一级</button>`;
}
html += `<button class="filter-btn category-btn active" data-category="${escapeAttribute(currentCategory)}">${escapeHTML(currentLabel)} (${currentCount})</button>`;
html += `</div>`;

if (visibleCategories.length > 0) {
    const depth = splitCategory(currentCategory).length;
    html += `<div class="category-children" data-depth="${depth}">`;
    visibleCategories.forEach(category => {
        html += `<button class="filter-btn category-btn" data-category="${escapeAttribute(category)}">${escapeHTML(categoryLabel(category))} (${categoryCount(category)})</button>`;
    });
    html += `</div>`;
}

categoryFilters.innerHTML = html;
categoryBtns = document.querySelectorAll('.category-btn');
    }

    function escapeHTML(value) {
return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
}[char]));
    }

    function escapeAttribute(value) {
return escapeHTML(value).replace(/`/g, '&#96;');
    }

    function safeURL(value, fallback = '#') {
try {
    const url = new URL(String(value || ''), window.location.href);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : fallback;
} catch (e) {
    return fallback;
}
    }

    function dataURL(path) {
const version = window.DATA_VERSION || 'dev';
const separator = path.includes('?') ? '&' : '?';
return `${path}${separator}v=${encodeURIComponent(version)}`;
    }

    function isPreprint(paper) {
return paper.is_preprint === true || paper.publication_type === 'preprint' || (!paper.venue && !paper.conference);
    }

    function formatDate(dateStr) {
	if (!dateStr) return '未知';
	if (/^\d{4}$/.test(dateStr)) return dateStr + '年';
	if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
	    const [y, m, d] = dateStr.split('-');
	    return y + '年' + parseInt(m) + '月' + parseInt(d) + '日';
	}
	return dateStr;
    }

    function parseDate(dateStr) {
	if (!isCompleteDate(dateStr)) return new Date(0);
	return new Date(dateStr + 'T00:00:00Z');
    }

    function isCompleteDate(dateStr) {
	return /^\d{4}-\d{2}-\d{2}$/.test(String(dateStr || ''));
    }

    function syncDailyPickerToMonth(month) {
if (!dailyDatePicker || currentDate) return;
dailyDatePicker.value = /^\d{4}-\d{2}$/.test(String(month || '')) ? `${month}-01` : '';
    }

    function setSegmentedActive(buttons, key, value) {
buttons.forEach(btn => btn.classList.toggle('active', btn.dataset[key] === value));
    }

    function summaryActionIsActive(action) {
if (action === 'month') return currentMonth === new Date().toISOString().slice(0, 7) && !currentDate;
if (action === 'pdf') return currentPdf === 'available';
if (action === 'published') return currentStatus === 'published';
if (action === 'smart-cfd') return currentCategory === '流体力学 / 智能CFD';
if (action === 'early-access') return currentSpecial === 'early-access';
return false;
    }

    function updateSummaryActionStates() {
summaryActions.forEach(card => {
    card.classList.toggle('is-active', summaryActionIsActive(card.dataset.summaryAction));
});
    }

    function sortTimestamp(paper) {
	const parsed = parseDate(paper.published);
	const value = parsed.getTime();
	return Number.isNaN(value) ? 0 : value;
    }

    function hasPDF(paper) {
return Boolean(paper.pdf_url || paper.preprint_pdf_url || paper.arxiv_id);
    }

    function sourceLabel(source, paper = {}) {
if (source === 'semantic_scholar') return 'Semantic Scholar';
if (source === 'arxiv') return 'arXiv';
if (source === 'google_scholar') {
    return String(paper.paper_url || '').includes('nature.com') ? 'Nature' : 'Google Scholar';
}
if (String(paper.paper_url || '').includes('nature.com')) return 'Nature';
if (paper.semantic_scholar_id || String(paper.paper_url || '').includes('semanticscholar.org')) return 'Semantic Scholar';
if (paper.arxiv_id || String(paper.arxiv_url || paper.paper_url || '').includes('arxiv.org')) return 'arXiv';
return source ? String(source) : 'Literature';
    }

    function publicationTypeLabel(type, preprint) {
if (preprint) return 'Preprint';
if (type === 'journal') return 'Journal';
if (type === 'conference') return 'Conference';
return 'Published';
    }

    function sourceScore(paper) {
const source = paper.source || '';
if (source === 'semantic_scholar') return 10;
if (source === 'arxiv') return 8;
if (source === 'google_scholar' && paper.abstract_status === 'enriched') return 7;
if (source === 'google_scholar') return 4;
return 5;
    }

    function daysSincePublished(paper) {
if (!isCompleteDate(paper.published)) return 365;
const date = parseDate(paper.published);
if (Number.isNaN(date.getTime())) return 365;
return Math.max(0, Math.floor((Date.now() - date.getTime()) / 86400000));
    }

    function tagScore(paper) {
const tags = paper.tags || [];
let score = 0;
if (tags.includes('流体力学 / 智能CFD')) score += 8;
if (tags.includes('机器学习')) score += 3;
if (tags.some(tag => tag.includes('流动控制与强化学习'))) score += 3;
return score;
    }

    function recommendationDetails(paper) {
const citation = Number(paper.citation_count || 0);
const citationScore = citation > 0 ? Math.min(14, Math.log10(citation + 1) * 6) : 0;
const recencyScore = Math.max(0, 12 - Math.min(daysSincePublished(paper), 180) / 15);
const publishedScore = isPreprint(paper) ? 2 : 8;
const pdfScore = hasPDF(paper) ? 6 : 0;
const abstractScore = paper.abstract && paper.abstract_status !== 'unreliable_google_scholar_snippet' ? 5 : 0;
const keywordScore = Array.isArray(paper.keywords) && paper.keywords.length > 0 ? 3 : 0;
const score = sourceScore(paper) + citationScore + recencyScore + publishedScore + pdfScore + abstractScore + keywordScore + tagScore(paper);
const reasons = [];
if (!isPreprint(paper)) reasons.push('已发表');
if (hasPDF(paper)) reasons.push('有PDF');
if (paper.abstract && paper.abstract_status !== 'unreliable_google_scholar_snippet') reasons.push('摘要可靠');
if ((paper.tags || []).includes('流体力学 / 智能CFD')) reasons.push('智能CFD');
if (citation > 0) reasons.push(`引用${citation}`);
if (citation === 0 && !paper.impact_factor) reasons.push('数据不足按日期补偿');
return { score, reasons };
    }

    function recommendationScore(paper) {
return recommendationDetails(paper).score;
    }

    function tagClass(tag) {
if (tag.includes('智能CFD')) return 'tag-smart';
if (tag.includes('机器学习')) return 'tag-ml';
if (tag.includes('湍流')) return 'tag-turbulence';
if (tag.includes('多相流')) return 'tag-multiphase';
if (tag.includes('流动控制')) return 'tag-control';
return 'tag-fluid';
    }

    // 加载月份索引
    async function loadMonthsIndex() {
try {
    const response = await fetch(dataURL('data/index.json'));
    const monthsIndex = await response.json();
    debugLog('Months index loaded:', monthsIndex);

    // 默认加载：如果 URL 指定了月份则加载对应月份，否则加载全部
    if (monthsIndex.length > 0) {
        const hash = window.location.hash.slice(1);
        const params = new URLSearchParams(hash);

        // 恢复 URL 中的筛选状态（月份按钮高亮在 loadStateFromURL 中处理）
        if (params.has('status')) {
            currentStatus = params.get('status');
            document.querySelectorAll('.status-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.status === currentStatus);
            });
        }
        if (params.has('pdf')) {
            currentPdf = params.get('pdf');
            document.querySelectorAll('.pdf-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.pdf === currentPdf);
            });
        }
        if (params.has('category')) {
            currentCategory = params.get('category');
        }
        if (params.has('sort')) {
            currentSort = params.get('sort');
            document.querySelectorAll('.sort-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.sort === currentSort);
            });
        }
        if (params.has('date')) {
            currentDate = params.get('date');
            if (dailyDatePicker) dailyDatePicker.value = currentDate;
        }
        if (params.has('q')) {
            searchTerm = params.get('q').toLowerCase();
            const searchInput = document.getElementById('searchInput');
            if (searchInput) searchInput.value = params.get('q');
        }

        const initialMonth = currentDate ? currentDate.slice(0, 7) : (params.has('month') ? params.get('month') : 'all');
        // 高亮正确的月份按钮
        document.querySelectorAll('.month-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.month === initialMonth);
        });
        syncDailyPickerToMonth(initialMonth);
        await loadMonthData(initialMonth);
    }
} catch (e) {
    console.error('Failed to load months index:', e);
}
    }

    // 加载指定月份的数据
    async function loadMonthData(month) {
if (month === 'all') {
    // 加载所有月份
    try {
        const response = await fetch(dataURL('data/index.json'));
        const monthsIndex = await response.json();

        // 加载所有月份数据
        allPapersData = [];
        for (const monthInfo of monthsIndex) {
            if (!monthsCache[monthInfo.month]) {
                const monthResponse = await fetch(dataURL(`data/${monthInfo.month}.json`));
                monthsCache[monthInfo.month] = await monthResponse.json();
            }
            allPapersData.push(...monthsCache[monthInfo.month]);
        }
        debugLog(`Loaded all months, total ${allPapersData.length} papers`);
    } catch (e) {
        console.error('Failed to load all months data:', e);
    }
} else {
    // 加载单个月份
    if (!monthsCache[month]) {
        try {
            const response = await fetch(dataURL(`data/${month}.json`));
            monthsCache[month] = await response.json();
            debugLog(`Loaded month ${month}, ${monthsCache[month].length} papers`);
        } catch (e) {
            console.error(`Failed to load month ${month}:`, e);
            return;
        }
    }
    allPapersData = monthsCache[month];
    debugLog(`Using cached data for ${month}, ${allPapersData.length} papers`);
}

// 数据加载完成后，触发筛选
filterAndSortPapers();
    }

    // 生成论文HTML（包含引用数/影响因子渲染）
    function createPaperHTML(paper) {
const paperId = String(paper.id || '');
const escapedId = escapeAttribute(paperId);
const title = escapeHTML(paper.title);
const authors = escapeHTML(paper.authors);
const hasReliableAbstract = Boolean(String(paper.abstract || '').trim())
    && paper.abstract_status !== 'unreliable_google_scholar_snippet';
const abstract = hasReliableAbstract
    ? escapeHTML(paper.abstract)
    : '暂无可靠摘要。Google Scholar 仅提供搜索片段，已隐藏原始片段以避免误读。';
const abstractSummary = hasReliableAbstract ? '查看摘要' : '摘要待补全';
const published = escapeHTML(paper.published);
const publishedFormatted = formatDate(paper.published);
const dateFlag = (paper.date_status === 'year_only' || paper.date_status === 'unreliable')
    ? '<span class="date-flag" title="日期待核实">⚠</span>' : '';
// 预出版论文：显示 badge + "暂未出版"
const earlyAccessBadge = paper.is_early_access
    ? '<span class="early-access-badge" title="预出版 / Ahead of Print">预出版</span>' : '';
const tags = paper.tags ? paper.tags.map(tag => `<span class="tag ${tagClass(tag)}">${escapeHTML(categoryLabel(tag))}</span>`).join('') : '';
const keywords = paper.keywords ? paper.keywords.map(kw => `<span class="tag keyword">${escapeHTML(kw)}</span>`).join('') : '';
const checked = selectedPaperIds.has(paperId) ? 'checked' : '';
const paperURL = safeURL(paper.paper_url || paper.arxiv_url, paperId ? `https://arxiv.org/abs/${encodeURIComponent(paperId)}` : '#');
const keywordsSection = keywords ? `<div class="paper-keywords"><span class="keyword-label">关键词：</span>${keywords}</div>` : '';
const preprint = isPreprint(paper);
const status = preprint ? 'preprint' : 'published';
const venue = paper.venue || paper.conference || '';
const publicationType = publicationTypeLabel(paper.publication_type, preprint);
const sourceBadge = `<span class="meta-item">${escapeHTML(sourceLabel(paper.source, paper))}</span>`;
const typeBadge = `<span class="meta-item">${escapeHTML(publicationType)}</span>`;
const doiLink = paper.doi ? `<a href="${escapeAttribute(safeURL(`https://doi.org/${paper.doi}`))}" target="_blank" rel="noopener noreferrer" class="code-link">DOI</a>` : '';
const sourcePageLink = paper.paper_url ? `<a href="${escapeAttribute(safeURL(paper.paper_url))}" target="_blank" rel="noopener noreferrer" class="code-link">${escapeHTML(sourceLabel(paper.source, paper))}</a>` : '';
const arxivLink = paper.arxiv_url ? `<a href="${escapeAttribute(safeURL(paper.arxiv_url))}" target="_blank" rel="noopener noreferrer" class="code-link">arXiv</a>` : '';
const pdfLink = paper.pdf_url ? `<a href="${escapeAttribute(safeURL(paper.pdf_url))}" target="_blank" rel="noopener noreferrer" class="code-link">PDF</a>` : '';
const preprintPdfLink = paper.preprint_pdf_url ? `<a href="${escapeAttribute(safeURL(paper.preprint_pdf_url))}" target="_blank" rel="noopener noreferrer" class="code-link">Preprint PDF</a>` : '';

// 提取代码链接
let codeLink = '';
if (paper.code_link) {
    codeLink = `<a href="${paper.code_link}" target="_blank" class="code-link">📄 Code/Project</a>`;
}

// 获取会议徽章
if (paper.code_link) {
    codeLink = `<a href="${escapeAttribute(safeURL(paper.code_link))}" target="_blank" rel="noopener noreferrer" class="code-link">Code/Project</a>`;
}

let venueBadge = '';
if (venue) {
    const badgeInfo = getVenueBadge(venue);
    if (badgeInfo) {
        venueBadge = `<span class="venue-badge ${badgeInfo.class}">${escapeHTML(badgeInfo.text)}</span>`;
    }
}

const safeCitationText = paper.citation_count ? `引用数: ${escapeHTML(paper.citation_count)}` : '';
const recommendation = recommendationDetails(paper);
const safeScoreText = recommendation.score.toFixed(1);
const scoreReasons = recommendation.reasons.length ? recommendation.reasons.join(' · ') : '数据不足时按日期补偿';

return `
    <article class="paper-card" data-date="${published}" data-status="${status}" data-tags="${paper.tags ? escapeAttribute(paper.tags.join(',')) : ''}" data-paper-id="${escapedId}">
        <div class="paper-select">
            <input type="checkbox" class="paper-checkbox" id="check-${escapedId}" data-paper-id="${escapedId}" ${checked}>
            <label for="check-${escapedId}"></label>
        </div>
        <div class="paper-content">
            <h2 class="paper-title">
                <a href="${escapeAttribute(paperURL)}" target="_blank" rel="noopener noreferrer">${title}</a>
            </h2>
            <div class="paper-meta">
                ${paper.is_early_access
                    ? `${earlyAccessBadge}<span class="early-access-date">暂未出版</span>`
                    : `<span class="meta-item" title="${published}">${publishedFormatted}</span>${dateFlag}`
                }
                ${sourceBadge}
                ${typeBadge}
                ${venueBadge}
                ${safeCitationText ? `<span class="meta-item">${safeCitationText}</span>` : ''}
                <span class="score-pill" title="${escapeAttribute(scoreReasons)}">推荐分 ${safeScoreText}</span>
                ${sourcePageLink}
                ${doiLink}
                ${arxivLink}
                ${pdfLink}
                ${preprintPdfLink}
                ${codeLink}
            </div>
            <div class="paper-authors">
                ${authors}
            </div>
            <div class="paper-tags">
                ${tags}
            </div>
            ${keywordsSection}
            <div class="paper-abstract">
                <details>
                    <summary>${abstractSummary}</summary>
                    <p>${abstract}</p>
                </details>
            </div>
        </div>
    </article>
`;
    }

    // 获取会议徽章信息
    function getVenueBadge(conference) {
if (!conference) return null;

const conferenceUpper = conference.toUpperCase();
let badgeClass = 'badge-published';

if (conferenceUpper.includes('NEURIPS')) {
    badgeClass = 'badge-neurips';
} else if (conferenceUpper.includes('ICLR')) {
    badgeClass = 'badge-iclr';
} else if (conferenceUpper.includes('ICML')) {
    badgeClass = 'badge-icml';
} else if (conferenceUpper.includes('CVPR')) {
    badgeClass = 'badge-cvpr';
} else if (conferenceUpper.includes('ICCV')) {
    badgeClass = 'badge-iccv';
} else if (conferenceUpper.includes('ECCV')) {
    badgeClass = 'badge-eccv';
} else if (conferenceUpper.includes('ACL')) {
    badgeClass = 'badge-acl';
} else if (conferenceUpper.includes('EMNLP')) {
    badgeClass = 'badge-emnlp';
} else if (conferenceUpper.includes('NAACL')) {
    badgeClass = 'badge-naacl';
} else if (conferenceUpper.includes('AAAI')) {
    badgeClass = 'badge-aaai';
} else if (conferenceUpper.includes('IJCAI')) {
    badgeClass = 'badge-ijcai';
}

return { class: badgeClass, text: conference };
    }

    // 更新发表状态按钮的数量
    function updateStatusButtonCounts() {
const categoryFilteredPapers = allPapersData.filter(paper => {
    const tags = paper.tags || [];
    const matchCategory = currentCategory === 'all' || tags.includes(currentCategory);
    const matchPdf = currentPdf === 'all' || (currentPdf === 'available' ? hasPDF(paper) : !hasPDF(paper));
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

statusBtns.forEach(btn => {
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

    // 更新研究领域按钮的数量
    function updateCategoryButtonCounts() {
renderCategoryNav();
    }

    // ===== URL 状态管理 =====
    // 将筛选状态保存到 URL hash（不产生浏览器历史记录）
    function saveStateToURL() {
        const params = new URLSearchParams();
        if (currentMonth !== 'all') params.set('month', currentMonth);
        if (currentStatus !== 'all') params.set('status', currentStatus);
        if (currentPdf !== 'all') params.set('pdf', currentPdf);
        if (currentCategory !== 'all') params.set('category', currentCategory);
        if (currentSort !== 'date-desc') params.set('sort', currentSort);
        if (currentDate) params.set('date', currentDate);
        if (currentSpecial) params.set('special', currentSpecial);
        if (searchTerm) params.set('q', searchTerm);
        const hash = params.toString();
        history.replaceState(null, '', hash ? '#' + hash : window.location.pathname);
    }

    // 从 URL hash 恢复筛选状态
    function loadStateFromURL() {
        const hash = window.location.hash.slice(1);
        if (!hash) return false;
        const params = new URLSearchParams(hash);

        if (params.has('month')) {
            currentMonth = params.get('month');
            // 更新月份按钮高亮
            document.querySelectorAll('.month-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.month === currentMonth);
            });
        }
        if (params.has('status')) {
            currentStatus = params.get('status');
            document.querySelectorAll('.status-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.status === currentStatus);
            });
        }
        if (params.has('pdf')) {
            currentPdf = params.get('pdf');
            document.querySelectorAll('.pdf-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.pdf === currentPdf);
            });
        }
        if (params.has('category')) {
            currentCategory = params.get('category');
            // 分类按钮由 renderCategoryNav 管理，此处仅设值
        }
        if (params.has('sort')) {
            currentSort = params.get('sort');
            document.querySelectorAll('.sort-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.sort === currentSort);
            });
        }
        if (params.has('date')) {
            currentDate = params.get('date');
            if (dailyDatePicker) dailyDatePicker.value = currentDate;
        }
        if (params.has('special')) {
            currentSpecial = params.get('special');
        }
        if (params.has('q')) {
            searchTerm = params.get('q').toLowerCase();
            const searchInput = document.getElementById('searchInput');
            if (searchInput) searchInput.value = params.get('q');
        }
        return true;
    }

    // 筛选和排序论文（包含重要程度排序）
    function filterAndSortPapers() {
debugLog('Filtering papers:', { currentStatus, currentPdf, currentCategory, searchTerm, currentSort });

// 筛选
filteredPapers = allPapersData.filter(paper => {
    const status = isPreprint(paper) ? 'preprint' : 'published';
    const tags = paper.tags || [];
    const text = `${paper.title} ${paper.authors} ${paper.abstract}`.toLowerCase();

    const matchStatus = currentStatus === 'all' || status === currentStatus;
    const matchPdf = currentPdf === 'all' || (currentPdf === 'available' ? hasPDF(paper) : !hasPDF(paper));
    const matchCategory = currentCategory === 'all' || tags.includes(currentCategory);
    const matchSearch = searchTerm === '' || text.includes(searchTerm);
    const matchDate = !currentDate || paper.published === currentDate;
    const matchSpecial = currentSpecial !== 'early-access' || paper.is_early_access === true;

    return matchStatus && matchPdf && matchCategory && matchSearch && matchDate && matchSpecial;
});

debugLog(`Filtered to ${filteredPapers.length} papers`);

// 排序（新增重要程度排序）
filteredPapers.sort((a, b) => {
    const dateA = sortTimestamp(a);
    const dateB = sortTimestamp(b);

    if (currentSort === 'date-desc') {
        return dateB - dateA;
    } else if (currentSort === 'date-asc') {
        return dateA - dateB;
    } else if (currentSort === 'importance-desc') {
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
if (resultsCount) {
    resultsCount.textContent = currentDate
        ? `${currentDate} 新增 ${filteredPapers.length} 篇论文`
        : `显示 ${filteredPapers.length} 篇论文`;
}

// 重置懒加载
loadedCount = 0;
if (papersContainer) {
    papersContainer.innerHTML = '';
}
if (observer) {
    observer.disconnect();
}

// 加载第一批
loadMorePapers();

// 将筛选状态保存到 URL hash
saveStateToURL();
    }

    // 加载更多论文
    function loadMorePapers() {
if (isLoading || loadedCount >= filteredPapers.length) {
    debugLog('Skip loading:', { isLoading, loadedCount, total: filteredPapers.length });
    return;
}

isLoading = true;
const batchSize = loadedCount === 0 ? initialBatchSize : subsequentBatchSize;
const endIndex = Math.min(loadedCount + batchSize, filteredPapers.length);
const fragment = document.createDocumentFragment();

for (let i = loadedCount; i < endIndex; i++) {
    const paperHTML = createPaperHTML(filteredPapers[i]);
    const temp = document.createElement('div');
    temp.innerHTML = paperHTML;
    fragment.appendChild(temp.firstElementChild);
}

// 移除旧加载指示器
const oldIndicator = document.getElementById('loading-indicator');
if (oldIndicator) {
    oldIndicator.remove();
}

papersContainer.appendChild(fragment);
loadedCount = endIndex;
isLoading = false;

// 设置加载触发器
if (loadedCount < filteredPapers.length) {
    setupLoadTrigger();
}
    }

    // 设置加载触发器
    function setupLoadTrigger() {
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
    papersContainer.appendChild(indicator);
}

if (observer) {
    observer.disconnect();
}

observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            loadMorePapers();
        }
    });
}, { rootMargin: '200px' });

observer.observe(indicator);
    }

    // 绑定事件
    monthBtns.forEach(btn => {
btn.addEventListener('click', async function() {
    monthBtns.forEach(b => b.classList.remove('active'));
    this.classList.add('active');
    currentMonth = this.dataset.month;
    currentDate = '';
    currentSpecial = '';
    syncDailyPickerToMonth(currentMonth);

    resultsCount.textContent = '加载中...';
    papersContainer.innerHTML = '<div style="text-align: center; padding: 40px; color: #666;">加载中...</div>';

    await loadMonthData(currentMonth);
});
    });

    if (dailyDatePicker) {
dailyDatePicker.addEventListener('change', async function() {
    currentDate = this.value || '';
    currentSpecial = '';
    if (!currentDate) {
        currentMonth = 'all';
        document.querySelectorAll('.month-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.month === 'all');
        });
        await loadMonthData('all');
        return;
    }

    currentMonth = currentDate.slice(0, 7);
    document.querySelectorAll('.month-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.month === currentMonth);
    });
    if (resultsCount) resultsCount.textContent = '加载中...';
    if (papersContainer) {
        papersContainer.innerHTML = '<div style="text-align: center; padding: 40px; color: #666;">加载中...</div>';
    }
    await loadMonthData(currentMonth);
});
    }

    summaryActions.forEach(card => {
card.addEventListener('click', async function() {
    const action = this.dataset.summaryAction;
    const wasActive = summaryActionIsActive(action);
    currentDate = '';
    currentSpecial = '';
    if (dailyDatePicker) dailyDatePicker.value = '';

    if (action === 'month') {
        currentMonth = wasActive ? 'all' : new Date().toISOString().slice(0, 7);
        setSegmentedActive(monthBtns, 'month', currentMonth);
        syncDailyPickerToMonth(currentMonth);
        await loadMonthData(currentMonth);
        return;
    }

    if (action === 'pdf') {
        currentPdf = wasActive ? 'all' : 'available';
        setSegmentedActive(pdfBtns, 'pdf', currentPdf);
    } else if (action === 'published') {
        currentStatus = wasActive ? 'all' : 'published';
        setSegmentedActive(statusBtns, 'status', currentStatus);
    } else if (action === 'smart-cfd') {
        currentCategory = wasActive ? 'all' : '流体力学 / 智能CFD';
    } else if (action === 'early-access') {
        currentSpecial = wasActive ? '' : 'early-access';
    }

    filterAndSortPapers();
});
    });

    statusBtns.forEach(btn => {
btn.addEventListener('click', function() {
    statusBtns.forEach(b => b.classList.remove('active'));
    this.classList.add('active');
    currentStatus = this.dataset.status;
    currentSpecial = '';
    filterAndSortPapers();
});
    });

    pdfBtns.forEach(btn => {
btn.addEventListener('click', function() {
    pdfBtns.forEach(b => b.classList.remove('active'));
    this.classList.add('active');
    currentPdf = this.dataset.pdf;
    currentSpecial = '';
    filterAndSortPapers();
});
    });

    categoryBtns.forEach(btn => {
btn.addEventListener('click', function() {
    categoryBtns.forEach(b => b.classList.remove('active'));
    this.classList.add('active');
    currentCategory = this.dataset.category;
    filterAndSortPapers();
});
    });

    if (categoryFilters) {
categoryFilters.addEventListener('click', function(e) {
    const backButton = e.target.closest('[data-category-back]');
    const categoryButton = e.target.closest('.category-btn');

    if (backButton) {
        currentCategory = backButton.dataset.categoryBack || 'all';
        filterAndSortPapers();
        return;
    }

    if (categoryButton) {
        currentCategory = categoryButton.dataset.category || 'all';
        currentSpecial = '';
        filterAndSortPapers();
    }
});
    }

    function updatePDFButtonCounts() {
const statusCategoryFilteredPapers = allPapersData.filter(paper => {
    const status = isPreprint(paper) ? 'preprint' : 'published';
    const tags = paper.tags || [];
    const matchStatus = currentStatus === 'all' || status === currentStatus;
    const matchCategory = currentCategory === 'all' || tags.includes(currentCategory);
    return matchStatus && matchCategory;
});

const availableCount = statusCategoryFilteredPapers.filter(hasPDF).length;
const missingCount = statusCategoryFilteredPapers.length - availableCount;

pdfBtns.forEach(btn => {
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

    sortBtns.forEach(btn => {
btn.addEventListener('click', function(e) {
    e.preventDefault();
    sortBtns.forEach(b => b.classList.remove('active'));
    this.classList.add('active');
    currentSort = this.dataset.sort;
    currentSpecial = '';
    filterAndSortPapers();
});
    });

    if (searchInput) {
searchInput.addEventListener('input', function() {
    searchTerm = this.value.toLowerCase();
    currentSpecial = '';
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(filterAndSortPapers, 180);
});
    }

    // 更新选中数量
    function updateSelectedCount() {
if (selectedCount) {
    selectedCount.textContent = selectedPaperIds.size;
}
    }

    if (papersContainer) {
papersContainer.addEventListener('change', function(e) {
    if (e.target.classList.contains('paper-checkbox')) {
        if (e.target.checked) {
            selectedPaperIds.add(e.target.dataset.paperId);
        } else {
            selectedPaperIds.delete(e.target.dataset.paperId);
        }
        updateSelectedCount();
    }
});
    }

    if (selectAllBtn) {
selectAllBtn.addEventListener('click', function() {
    filteredPapers.slice(0, loadedCount).forEach(paper => selectedPaperIds.add(String(paper.id || '')));
    document.querySelectorAll('.paper-checkbox').forEach(cb => cb.checked = true);
    updateSelectedCount();
});
    }

    if (clearAllBtn) {
clearAllBtn.addEventListener('click', function() {
    selectedPaperIds.clear();
    document.querySelectorAll('.paper-checkbox').forEach(cb => cb.checked = false);
    updateSelectedCount();
});
    }

    // 导出功能
    if (exportBtn) {
exportBtn.addEventListener('click', function(e) {
    e.preventDefault();
    downloadSelectedPDFs();
});
    }

    function getPaperPDFUrl(paper) {
if (paper.pdf_url) return safeURL(paper.pdf_url, '');
if (paper.preprint_pdf_url) return safeURL(paper.preprint_pdf_url, '');
if (paper.arxiv_id) return safeURL(`https://arxiv.org/pdf/${paper.arxiv_id}`, '');
return '';
    }

    function sanitizeFilename(value) {
return String(value || 'paper')
    .replace(/[\\\\/:*?"<>|]+/g, '_')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 120) || 'paper';
    }

    function downloadSelectedPDFs() {
if (selectedPaperIds.size === 0) {
    alert('请至少选择一篇论文下载！');
    return;
}

const selectedPapers = allPapersData.filter(paper => selectedPaperIds.has(String(paper.id || '')));
const missing = [];
let downloadCount = 0;

selectedPapers.forEach((paper, index) => {
    const pdfUrl = getPaperPDFUrl(paper);
    if (!pdfUrl) {
        missing.push(paper.title || paper.id || `paper ${index + 1}`);
        return;
    }

    const link = document.createElement('a');
    link.href = pdfUrl;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.download = `${sanitizeFilename(paper.title || paper.id || `paper_${index + 1}`)}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    downloadCount += 1;
});

if (missing.length > 0) {
    alert(`已尝试下载 ${downloadCount} 个 PDF；${missing.length} 篇没有可用 PDF 链接。`);
}
    }

    function downloadFile(content, filename, contentType) {
const blob = new Blob([content], { type: contentType });
const url = URL.createObjectURL(blob);
const link = document.createElement('a');
link.href = url;
link.download = filename;
document.body.appendChild(link);
link.click();
document.body.removeChild(link);
URL.revokeObjectURL(url);
    }

    // 复制选中论文的 DOI 到剪贴板，方便导入 Zotero
    function copySelectedDOIs() {
if (selectedPaperIds.size === 0) {
    alert('请至少选择一篇论文！');
    return;
}
const selectedPapers = allPapersData.filter(p => selectedPaperIds.has(String(p.id || '')));

// 提取 DOI
const dois = selectedPapers
    .map(p => (p.doi || '').trim())
    .filter(d => d.length > 0);

// 提取 arXiv URL：优先 arxiv_id，其次从 id 或 arxiv_url 推断
const arxivUrls = selectedPapers
    .map(p => {
        // 已有明确的 arxiv_id
        const aid = (p.arxiv_id || '').trim();
        if (aid) return `https://arxiv.org/abs/${aid}`;
        // 从 arxiv_url 提取
        const aurl = (p.arxiv_url || '').trim();
        if (aurl && aurl.includes('arxiv.org')) return aurl;
        // 从 id 字段推断（形如 2605.25679v1）
        const pid = String(p.id || '');
        const m = pid.match(/^(\d{4}\.\d{4,5})/);
        if (m) return `https://arxiv.org/abs/${m[1]}`;
        return '';
    })
    .filter(u => u.length > 0);

// 去重
const uniqueDois = [...new Set(dois)];
const uniqueArxiv = [...new Set(arxivUrls)];
const finalArxiv = uniqueArxiv;

if (uniqueDois.length === 0 && finalArxiv.length === 0) {
    alert('选中论文中没有可用的 DOI 或 arXiv ID。');
    return;
}

let text = '';
if (uniqueDois.length > 0) {
    text += '=== DOI ===\\n';
    text += uniqueDois.join('\\n');
}
if (finalArxiv.length > 0) {
    if (text) text += '\\n\\n';
    text += '=== arXiv URL ===\\n';
    text += finalArxiv.join('\\n');
}

navigator.clipboard.writeText(text).then(() => {
    const total = uniqueDois.length + finalArxiv.length;
    const msg = `已复制 ${total} 个标识符（${uniqueDois.length} DOI + ${finalArxiv.length} arXiv）。`;
    alert(msg);
}).catch(() => {
    // Fallback: 用 textarea 复制
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    alert(`已复制 ${uniqueDois.length} 个 DOI + ${finalArxiv.length} 个 arXiv 链接`);
});
    }

    // 绑定"复制DOI"按钮
    const copyDoiBtn = document.getElementById('copyDoiBtn');
    if (copyDoiBtn) {
copyDoiBtn.addEventListener('click', function(e) {
    e.preventDefault();
    copySelectedDOIs();
});
    }

    // 初始化
    debugLog('Initializing...');
    loadMonthsIndex();
});
