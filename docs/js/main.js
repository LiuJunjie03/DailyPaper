// 筛选、搜索、排序和懒加载功能
document.addEventListener('DOMContentLoaded', function() {
    console.log('JavaScript loaded');
    
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
    
    console.log('DOM elements:', {
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
    let currentCategoryParent = '';
    let currentSort = 'date-desc';
    let searchTerm = '';
    let filteredPapers = [];
    let loadedCount = 0;
    const initialBatchSize = 20;  // 第一次加载20个
    const subsequentBatchSize = 10;  // 后续每次加载10个
    let isLoading = false;
    let observer = null;
    let monthsCache = {};  // 缓存已加载的月份数据
    let selectedPaperIds = new Set();
    
    // 配置里的分类列表（从Python传入）
    const CATEGORIES = ["\u673a\u5668\u5b66\u4e60", "\u6d41\u4f53\u529b\u5b66", "\u6d41\u4f53\u529b\u5b66 / \u667a\u80fdCFD / \u4ee3\u7406\u6a21\u578b\u4e0e\u7b97\u5b50\u5b66\u4e60", "\u6d41\u4f53\u529b\u5b66 / \u667a\u80fdCFD / \u6e4d\u6d41\u5efa\u6a21\u4e0e\u95ed\u5408", "\u6d41\u4f53\u529b\u5b66 / \u667a\u80fdCFD / \u6570\u503c\u65b9\u6cd5\u589e\u5f3a", "\u6d41\u4f53\u529b\u5b66 / \u667a\u80fdCFD / \u52a0\u901f\u6c42\u89e3\u4e0e\u8d85\u5206\u8fa8", "\u6d41\u4f53\u529b\u5b66 / \u667a\u80fdCFD / \u7269\u7406\u4fe1\u606f\u795e\u7ecf\u7f51\u7edc", "\u6d41\u4f53\u529b\u5b66 / \u667a\u80fdCFD / \u6d41\u573a\u91cd\u5efa\u4e0e\u6570\u636e\u9a71\u52a8", "\u6d41\u4f53\u529b\u5b66 / \u667a\u80fdCFD / \u6d41\u52a8\u63a7\u5236\u4e0e\u5f3a\u5316\u5b66\u4e60", "\u6d41\u4f53\u529b\u5b66 / \u6c14\u52a8\u4f18\u5316\u8bbe\u8ba1", "\u6d41\u4f53\u529b\u5b66 / \u6e4d\u6d41\u4e0e\u6d41\u52a8\u673a\u7406", "\u6d41\u4f53\u529b\u5b66 / \u591a\u76f8\u6d41\u7406\u8bba", "\u6d41\u4f53\u529b\u5b66 / \u7a7a\u6c14\u52a8\u529b\u5b66\u7406\u8bba", "\u6d41\u4f53\u529b\u5b66 / \u73af\u5883\u4e0e\u5730\u7403\u7269\u7406\u6d41\u4f53", "\u6d41\u4f53\u529b\u5b66 / \u751f\u7269\u4e0e\u533b\u5b66\u6d41\u4f53", "\u6d41\u4f53\u529b\u5b66 / \u71c3\u70e7\u4e0e\u4f20\u70ed", "\u6d41\u4f53\u529b\u5b66 / \u98ce\u80fd\u4e0e\u6d77\u6d0b\u5de5\u7a0b\u6d41\u4f53", "\u6d41\u4f53\u529b\u5b66 / \u8ba1\u7b97\u6d41\u4f53\u529b\u5b66\u65b9\u6cd5", "\u6d41\u4f53\u529b\u5b66 / \u5176\u4ed6"];

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
            html += `<div class="category-children">`;
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

    function escapeBibTeX(value) {
        const backslash = String.fromCharCode(92);
        const text = String(value ?? '').trim();
        let escaped = '';
        for (const char of text) {
            escaped += ['{', '}', backslash].includes(char) ? backslash + char : char;
        }
        return escaped.split(/\s+/).join(' ');
    }

    function isPreprint(paper) {
        return paper.is_preprint === true || paper.publication_type === 'preprint' || (!paper.venue && !paper.conference);
    }

    function hasPDF(paper) {
        return Boolean(paper.pdf_url || paper.preprint_pdf_url || paper.arxiv_id);
    }

    function sourceLabel(source, paper = {}) {
        if (source === 'semantic_scholar') return 'Semantic Scholar';
        if (source === 'arxiv') return 'arXiv';
        if (paper.semantic_scholar_id || paper.doi || String(paper.paper_url || '').includes('semanticscholar.org')) return 'Semantic Scholar';
        if (paper.arxiv_id || String(paper.arxiv_url || paper.paper_url || '').includes('arxiv.org')) return 'arXiv';
        return source ? String(source) : 'Literature';
    }

    function publicationTypeLabel(type, preprint) {
        if (preprint) return 'Preprint';
        if (type === 'journal') return 'Journal';
        if (type === 'conference') return 'Conference';
        return 'Published';
    }
    
    // 加载月份索引
    async function loadMonthsIndex() {
        try {
            const response = await fetch('data/index.json');
            const monthsIndex = await response.json();
            console.log('Months index loaded:', monthsIndex);
            
            // 默认加载最新月份的数据
            if (monthsIndex.length > 0) {
                await loadMonthData('all');
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
                const response = await fetch('data/index.json');
                const monthsIndex = await response.json();
                
                // 加载所有月份数据
                allPapersData = [];
                for (const monthInfo of monthsIndex) {
                    if (!monthsCache[monthInfo.month]) {
                        const monthResponse = await fetch(`data/${monthInfo.month}.json`);
                        monthsCache[monthInfo.month] = await monthResponse.json();
                    }
                    allPapersData.push(...monthsCache[monthInfo.month]);
                }
                console.log(`Loaded all months, total ${allPapersData.length} papers`);
            } catch (e) {
                console.error('Failed to load all months data:', e);
            }
        } else {
            // 加载单个月份
            if (!monthsCache[month]) {
                try {
                    const response = await fetch(`data/${month}.json`);
                    monthsCache[month] = await response.json();
                    console.log(`Loaded month ${month}, ${monthsCache[month].length} papers`);
                } catch (e) {
                    console.error(`Failed to load month ${month}:`, e);
                    return;
                }
            }
            allPapersData = monthsCache[month];
            console.log(`Using cached data for ${month}, ${allPapersData.length} papers`);
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
        const abstract = escapeHTML(paper.abstract);
        const published = escapeHTML(paper.published);
        const tags = paper.tags ? paper.tags.map(tag => `<span class="tag">${escapeHTML(categoryLabel(tag))}</span>`).join('') : '';
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
        
        // 新增：渲染引用数和影响因子
        const citationText = paper.citation_count ? `📊 引用数: ${paper.citation_count}` : "📊 引用数: 暂无";
        const impactText = paper.impact_factor ? `🌟 影响因子: ${paper.impact_factor}` : "🌟 影响因子: 暂无";
        
        const safeCitationText = paper.citation_count ? `引用数: ${escapeHTML(paper.citation_count)}` : "引用数: 暂无";
        const safeImpactText = paper.impact_factor ? `推荐分: ${escapeHTML(paper.impact_factor)}` : "推荐分: 暂无";
        const firstCategory = paper.categories && paper.categories.length > 0 ? paper.categories[0] : '';
        
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
                        <span class="meta-item">${published}</span>
                        ${sourceBadge}
                        ${typeBadge}
                        ${venueBadge}
                        <span class="meta-item">${safeCitationText}</span>
                        <span class="meta-item">${safeImpactText}</span>
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
                            <summary>查看摘要</summary>
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
        return;
        const statusFilteredPapers = allPapersData.filter(paper => {
            const status = isPreprint(paper) ? 'preprint' : 'published';
            return currentStatus === 'all' || status === currentStatus;
        });
        
        const categoryCounts = { 'all': statusFilteredPapers.length };
        CATEGORIES.forEach(category => {
            categoryCounts[category] = 0;
        });
        
        statusFilteredPapers.forEach(paper => {
            const tags = paper.tags || [];
            tags.forEach(tag => {
                if (categoryCounts.hasOwnProperty(tag)) {
                    categoryCounts[tag]++;
                }
            });
        });
        
        categoryBtns.forEach(btn => {
            const category = btn.dataset.category;
            const displayName = category === 'all' ? '全部' : 
                               category.replace("Natural Language Processing", "NLP");
            const count = categoryCounts[category] || 0;
            btn.textContent = `${displayName} (${count})`;
        });
    }
    
    // 筛选和排序论文（包含重要程度排序）
    function filterAndSortPapers() {
        console.log('Filtering papers:', { currentStatus, currentPdf, currentCategory, searchTerm, currentSort });
        
        // 筛选
        filteredPapers = allPapersData.filter(paper => {
            const status = isPreprint(paper) ? 'preprint' : 'published';
            const tags = paper.tags || [];
            const text = `${paper.title} ${paper.authors} ${paper.abstract}`.toLowerCase();
            
            const matchStatus = currentStatus === 'all' || status === currentStatus;
            const matchPdf = currentPdf === 'all' || (currentPdf === 'available' ? hasPDF(paper) : !hasPDF(paper));
            const matchCategory = currentCategory === 'all' || tags.includes(currentCategory);
            const matchSearch = searchTerm === '' || text.includes(searchTerm);
            
            return matchStatus && matchPdf && matchCategory && matchSearch;
        });
        
        console.log(`Filtered to ${filteredPapers.length} papers`);
        
        // 排序（新增重要程度排序）
        filteredPapers.sort((a, b) => {
            const dateA = new Date(a.published);
            const dateB = new Date(b.published);
            
            if (currentSort === 'date-desc') {
                return dateB - dateA;
            } else if (currentSort === 'date-asc') {
                return dateA - dateB;
            } else if (currentSort === 'importance-desc') {
                // 重要程度：先按影响因子降序，再按引用数降序
                const impactA = a.impact_factor || 0;
                const impactB = b.impact_factor || 0;
                if (impactA !== impactB) {
                    return impactB - impactA;
                }
                const citeA = a.citation_count || 0;
                const citeB = b.citation_count || 0;
                return citeB - citeA;
            }
            return 0;
        });
        
        // 更新按钮数量和显示
        updateStatusButtonCounts();
        updatePDFButtonCounts();
        updateCategoryButtonCounts();
        if (resultsCount) {
            resultsCount.textContent = `显示 ${filteredPapers.length} 篇论文`;
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
    }
    
    // 加载更多论文
    function loadMorePapers() {
        if (isLoading || loadedCount >= filteredPapers.length) {
            console.log('Skip loading:', { isLoading, loadedCount, total: filteredPapers.length });
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
            
            resultsCount.textContent = '加载中...';
            papersContainer.innerHTML = '<div style="text-align: center; padding: 40px; color: #666;">加载中...</div>';
            
            await loadMonthData(currentMonth);
        });
    });
    
    statusBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            statusBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentStatus = this.dataset.status;
            filterAndSortPapers();
        });
    });

    pdfBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            pdfBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentPdf = this.dataset.pdf;
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
            filterAndSortPapers();
        });
    });
    
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            searchTerm = this.value.toLowerCase();
            filterAndSortPapers();
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
            filteredPapers.forEach(paper => selectedPaperIds.add(String(paper.id || '')));
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
            .replace(/[\\/:*?"<>|]+/g, '_')
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
    
    // 初始化
    console.log('Initializing...');
    loadMonthsIndex();
});
