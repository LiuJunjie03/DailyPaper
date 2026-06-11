/**
 * DailyPaper 前端入口 — ES module
 * 职责：DOM 查询、事件绑定、初始化调度
 */

import { state, dom } from './state.js';
import { debugLog, sanitizeFilename, safeURL, localToday } from './utils.js';
import { hasPDF, getPaperPDFUrl } from './paper-card.js';
import { loadMonthsIndex, loadMonthData } from './data-loader.js';
import { filterAndSortPapers, saveStateToURL } from './filters.js';
import { syncDailyPickerToMonth, setSegmentedActive, summaryActionIsActive } from './dashboard.js';

// ===== DOM 元素查询 =====

dom.monthBtns = document.querySelectorAll('.month-btn');
dom.statusBtns = document.querySelectorAll('.status-btn');
dom.pdfBtns = document.querySelectorAll('.pdf-btn');
dom.categoryBtns = document.querySelectorAll('.category-btn');
dom.categoryFilters = document.querySelector('.category-filters');
dom.sortBtns = document.querySelectorAll('.sort-btn');
dom.searchInput = document.getElementById('searchInput');
dom.exportBtn = document.getElementById('exportBtn');
dom.selectAllBtn = document.getElementById('selectAllBtn');
dom.clearAllBtn = document.getElementById('clearAllBtn');
dom.selectedCount = document.getElementById('selectedCount');
dom.resultsCount = document.getElementById('resultsCount');
dom.papersContainer = document.getElementById('papers-container');
dom.dailyDatePicker = document.getElementById('dailyDatePicker');
dom.summaryActions = document.querySelectorAll('.summary-action');

// ===== 辅助函数（仅本模块使用） =====

function updateSelectedCount() {
    if (dom.selectedCount) {
        dom.selectedCount.textContent = state.selectedPaperIds.size;
    }
}

function downloadSelectedPDFs() {
    if (state.selectedPaperIds.size === 0) {
        alert('请至少选择一篇论文下载！');
        return;
    }

    const selectedPapers = state.allPapersData.filter(paper => state.selectedPaperIds.has(String(paper.id || '')));
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

function copySelectedDOIs() {
    if (state.selectedPaperIds.size === 0) {
        alert('请至少选择一篇论文！');
        return;
    }
    const selectedPapers = state.allPapersData.filter(p => state.selectedPaperIds.has(String(p.id || '')));

    // 提取 DOI
    const dois = selectedPapers
        .map(p => (p.doi || '').trim())
        .filter(d => d.length > 0);

    // 提取 arXiv URL
    const arxivUrls = selectedPapers
        .map(p => {
            const aid = (p.arxiv_id || '').trim();
            if (aid) return `https://arxiv.org/abs/${aid}`;
            const aurl = (p.arxiv_url || '').trim();
            if (aurl && aurl.includes('arxiv.org')) return aurl;
            const pid = String(p.id || '');
            const m = pid.match(/^(\d{4}\.\d{4,5})/);
            if (m) return `https://arxiv.org/abs/${m[1]}`;
            return '';
        })
        .filter(u => u.length > 0);

    const uniqueDois = [...new Set(dois)];
    const uniqueArxiv = [...new Set(arxivUrls)];
    const finalArxiv = uniqueArxiv;

    if (uniqueDois.length === 0 && finalArxiv.length === 0) {
        alert('选中论文中没有可用的 DOI 或 arXiv ID。');
        return;
    }

    let text = '';
    if (uniqueDois.length > 0) {
        text += '=== DOI ===\n';
        text += uniqueDois.join('\n');
    }
    if (finalArxiv.length > 0) {
        if (text) text += '\n\n';
        text += '=== arXiv URL ===\n';
        text += finalArxiv.join('\n');
    }

    navigator.clipboard.writeText(text).then(() => {
        const total = uniqueDois.length + finalArxiv.length;
        const msg = `已复制 ${total} 个标识符（${uniqueDois.length} DOI + ${finalArxiv.length} arXiv）。`;
        alert(msg);
    }).catch(() => {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        alert(`已复制 ${uniqueDois.length} 个 DOI + ${finalArxiv.length} 个 arXiv 链接`);
    });
}

// ===== 事件绑定 =====

// 月份按钮（事件委托，兼容后续动态渲染/折叠区域）
document.addEventListener('click', async function(e) {
    const monthBtn = e.target.closest('.month-btn');
    if (!monthBtn) return;

    document.querySelectorAll('.month-btn').forEach(b => b.classList.remove('active'));
    monthBtn.classList.add('active');
    state.currentMonth = monthBtn.dataset.month;
    state.currentDate = '';
    state.currentSpecial = '';
    syncDailyPickerToMonth(state.currentMonth);

    dom.resultsCount.textContent = '加载中...';
    dom.papersContainer.innerHTML = '<div style="text-align: center; padding: 40px; color: #666;">加载中...</div>';

    await loadMonthData(state.currentMonth);
});

// 日期选择器
if (dom.dailyDatePicker) {
    dom.dailyDatePicker.addEventListener('change', async function() {
        state.currentDate = this.value || '';
        state.currentSpecial = '';
        if (!state.currentDate) {
            state.currentMonth = 'all';
            document.querySelectorAll('.month-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.month === 'all');
            });
            await loadMonthData('all');
            return;
        }

        state.currentMonth = state.currentDate.slice(0, 7);
        document.querySelectorAll('.month-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.month === state.currentMonth);
        });
        if (dom.resultsCount) dom.resultsCount.textContent = '加载中...';
        if (dom.papersContainer) {
            dom.papersContainer.innerHTML = '<div style="text-align: center; padding: 40px; color: #666;">加载中...</div>';
        }
        await loadMonthData(state.currentMonth);
    });
}

// Summary action 卡片
dom.summaryActions.forEach(card => {
    card.addEventListener('click', async function() {
        const action = this.dataset.summaryAction;
        const wasActive = summaryActionIsActive(action);
        state.currentSpecial = '';

        if (action === 'today') {
            const today = localToday();
            if (wasActive) {
                // 再次点击：恢复默认
                state.currentDate = '';
                state.currentMonth = 'all';
                if (dom.dailyDatePicker) dom.dailyDatePicker.value = '';
                setSegmentedActive(document.querySelectorAll('.month-btn'), 'month', 'all');
                await loadMonthData('all');
            } else {
                // 首次点击：跳转到今日
                state.currentDate = today;
                state.currentMonth = today.slice(0, 7);
                if (dom.dailyDatePicker) dom.dailyDatePicker.value = today;
                setSegmentedActive(document.querySelectorAll('.month-btn'), 'month', state.currentMonth);
                if (dom.resultsCount) dom.resultsCount.textContent = '加载中...';
                if (dom.papersContainer) {
                    dom.papersContainer.innerHTML = '<div style="text-align: center; padding: 40px; color: #666;">加载中...</div>';
                }
                await loadMonthData(state.currentMonth);
            }
            return;
        }

        state.currentDate = '';
        if (dom.dailyDatePicker) dom.dailyDatePicker.value = '';

        if (action === 'month') {
            state.currentMonth = wasActive ? 'all' : localToday().slice(0, 7);
            setSegmentedActive(document.querySelectorAll('.month-btn'), 'month', state.currentMonth);
            syncDailyPickerToMonth(state.currentMonth);
            await loadMonthData(state.currentMonth);
            return;
        }

        if (action === 'pdf') {
            state.currentPdf = wasActive ? 'all' : 'available';
            setSegmentedActive(dom.pdfBtns, 'pdf', state.currentPdf);
        } else if (action === 'published') {
            state.currentStatus = wasActive ? 'all' : 'published';
            setSegmentedActive(dom.statusBtns, 'status', state.currentStatus);
        } else if (action === 'smart-cfd') {
            state.currentCategory = wasActive ? 'all' : '流体力学 / 智能CFD';
        } else if (action === 'early-access') {
            state.currentSpecial = wasActive ? '' : 'early-access';
        }

        filterAndSortPapers();
    });
});

// 发表状态按钮
dom.statusBtns.forEach(btn => {
    btn.addEventListener('click', function() {
        dom.statusBtns.forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        state.currentStatus = this.dataset.status;
        state.currentSpecial = '';
        filterAndSortPapers();
    });
});

// PDF 按钮
dom.pdfBtns.forEach(btn => {
    btn.addEventListener('click', function() {
        dom.pdfBtns.forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        state.currentPdf = this.dataset.pdf;
        state.currentSpecial = '';
        filterAndSortPapers();
    });
});

// 分类导航 — 事件委托（由 renderCategoryNav 生成的按钮）
if (dom.categoryFilters) {
    dom.categoryFilters.addEventListener('click', function(e) {
        const backButton = e.target.closest('[data-category-back]');
        const categoryButton = e.target.closest('.category-btn');

        if (backButton) {
            state.currentCategory = backButton.dataset.categoryBack || 'all';
            filterAndSortPapers();
            return;
        }

        if (categoryButton) {
            state.currentCategory = categoryButton.dataset.category || 'all';
            state.currentSpecial = '';
            filterAndSortPapers();
        }
    });
}

// 排序按钮
dom.sortBtns.forEach(btn => {
    btn.addEventListener('click', function(e) {
        e.preventDefault();
        dom.sortBtns.forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        state.currentSort = this.dataset.sort;
        state.currentSpecial = '';
        filterAndSortPapers();
    });
});

// 搜索输入
if (dom.searchInput) {
    dom.searchInput.addEventListener('input', function() {
        state.searchTerm = this.value.toLowerCase();
        state.currentSpecial = '';
        window.clearTimeout(state.searchTimer);
        state.searchTimer = window.setTimeout(filterAndSortPapers, 180);
    });
}

// 论文复选框 — 事件委托
if (dom.papersContainer) {
    dom.papersContainer.addEventListener('change', function(e) {
        if (e.target.classList.contains('paper-checkbox')) {
            if (e.target.checked) {
                state.selectedPaperIds.add(e.target.dataset.paperId);
            } else {
                state.selectedPaperIds.delete(e.target.dataset.paperId);
            }
            updateSelectedCount();
        }
    });
}

// 全选/清空按钮
if (dom.selectAllBtn) {
    dom.selectAllBtn.addEventListener('click', function() {
        state.filteredPapers.slice(0, state.loadedCount).forEach(paper => state.selectedPaperIds.add(String(paper.id || '')));
        document.querySelectorAll('.paper-checkbox').forEach(cb => cb.checked = true);
        updateSelectedCount();
    });
}

if (dom.clearAllBtn) {
    dom.clearAllBtn.addEventListener('click', function() {
        state.selectedPaperIds.clear();
        document.querySelectorAll('.paper-checkbox').forEach(cb => cb.checked = false);
        updateSelectedCount();
    });
}

// 导出按钮
if (dom.exportBtn) {
    dom.exportBtn.addEventListener('click', function(e) {
        e.preventDefault();
        downloadSelectedPDFs();
    });
}

// 复制 DOI 按钮
const copyDoiBtn = document.getElementById('copyDoiBtn');
if (copyDoiBtn) {
    copyDoiBtn.addEventListener('click', function(e) {
        e.preventDefault();
        copySelectedDOIs();
    });
}

// ===== 初始化 =====
debugLog('Initializing...');
loadMonthsIndex();
