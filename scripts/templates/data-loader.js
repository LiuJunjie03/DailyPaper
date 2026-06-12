/**
 * 数据加载与缓存 — 月份索引、月度 JSON 加载
 */

import { state, dom } from './state.js';
import { dataURL, debugLog } from './utils.js';
import { filterAndSortPapers } from './filters.js';
import { syncDailyPickerToMonth } from './dashboard.js';

/**
 * 带状态检查的 fetch + JSON 解析
 */
async function fetchJSON(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status} loading ${url}`);
    return response.json();
}

/**
 * 加载月份索引，解析 URL hash 恢复筛选状态，触发初始数据加载
 */
export async function loadMonthsIndex() {
    try {
        const monthsIndex = await fetchJSON(dataURL('data/index.json'));
        debugLog('Months index loaded:', monthsIndex);

        if (monthsIndex.length > 0) {
            const hash = window.location.hash.slice(1);
            const params = new URLSearchParams(hash);

            // 恢复 URL 中的筛选状态
            if (params.has('status')) {
                state.currentStatus = params.get('status');
                dom.statusBtns.forEach(btn => {
                    btn.classList.toggle('active', btn.dataset.status === state.currentStatus);
                });
            }
            if (params.has('pdf')) {
                state.currentPdf = params.get('pdf');
                dom.pdfBtns.forEach(btn => {
                    btn.classList.toggle('active', btn.dataset.pdf === state.currentPdf);
                });
            }
            if (params.has('category')) {
                state.currentCategory = params.get('category');
            }
            if (params.has('sort')) {
                state.currentSort = params.get('sort');
                dom.sortBtns.forEach(btn => {
                    btn.classList.toggle('active', btn.dataset.sort === state.currentSort);
                });
            }
            if (params.has('date')) {
                state.currentDate = params.get('date');
                if (dom.dailyDatePicker) dom.dailyDatePicker.value = state.currentDate;
            }
            if (params.has('q')) {
                state.searchTerm = params.get('q').toLowerCase();
                const searchInput = document.getElementById('searchInput');
                if (searchInput) searchInput.value = params.get('q');
            }

            const initialMonth = state.currentDate ? state.currentDate.slice(0, 7) : (params.has('month') ? params.get('month') : 'all');
            state.currentMonth = initialMonth;
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

/**
 * 加载指定月份的数据（或全部月份）
 */
export async function loadMonthData(month) {
    if (month === 'all') {
        // 加载所有月份
        try {
            const monthsIndex = await fetchJSON(dataURL('data/index.json'));

            state.allPapersData = [];
            for (const monthInfo of monthsIndex) {
                if (!state.monthsCache[monthInfo.month]) {
                    state.monthsCache[monthInfo.month] = await fetchJSON(dataURL(`data/${monthInfo.month}.json`));
                }
                state.allPapersData.push(...state.monthsCache[monthInfo.month]);
            }
            debugLog(`Loaded all months, total ${state.allPapersData.length} papers`);
        } catch (e) {
            console.error('Failed to load all months data:', e);
        }
    } else {
        // 加载单个月份
        if (!state.monthsCache[month]) {
            try {
                state.monthsCache[month] = await fetchJSON(dataURL(`data/${month}.json`));
                debugLog(`Loaded month ${month}, ${state.monthsCache[month].length} papers`);
            } catch (e) {
                console.error(`Failed to load month ${month}:`, e);
                return;
            }
        }
        state.allPapersData = state.monthsCache[month];
        debugLog(`Using cached data for ${month}, ${state.allPapersData.length} papers`);
    }

    // 数据加载完成后，触发筛选
    filterAndSortPapers();
}
