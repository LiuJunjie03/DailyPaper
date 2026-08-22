/**
 * 仪表盘辅助函数 — 日期选择器同步、Summary 卡片状态管理
 */

import { state, dom } from './state.js';
import { localToday } from './utils.js';

/**
 * 导航到指定日期 — 设置状态、同步日期选择器、判断是否跨月。
 * 返回 { monthChanged: true } 表示需要加载新月数据。
 */
export async function navigateToDate(dateStr) {
    const wasMonth = state.currentMonth;
    if (dateStr) {
        state.currentDate = dateStr;
        state.currentMonth = dateStr.slice(0, 7);
        if (dom.dailyDatePicker) dom.dailyDatePicker.value = dateStr;
    } else {
        state.currentDate = '';
        state.currentMonth = 'all';
        if (dom.dailyDatePicker) dom.dailyDatePicker.value = localToday();
    }
    if (dom.monthBtns) {
        dom.monthBtns.forEach(btn => btn.classList.toggle('active', btn.dataset.month === state.currentMonth));
    }
    return { monthChanged: state.currentMonth !== wasMonth };
}

/**
 * 同步日期选择器到指定月份（仅在未手动选日期时生效）
 */
export function syncDailyPickerToMonth(month) {
    if (!dom.dailyDatePicker || state.currentDate) return;
    dom.dailyDatePicker.value = /^\d{4}-\d{2}$/.test(String(month || '')) ? `${month}-01` : localToday();
}

/**
 * 在一组按钮中切换 active 状态（单选逻辑）
 */
export function setSegmentedActive(buttons, key, value) {
    buttons.forEach(btn => btn.classList.toggle('active', btn.dataset[key] === value));
}

/**
 * 判断某个 summary action 卡片当前是否处于激活状态
 */
export function summaryActionIsActive(action) {
    const today = localToday();
    if (action === 'today') return state.currentDate !== '';
    if (action === 'month') return state.currentMonth === today.slice(0, 7) && !state.currentDate;
    if (action === 'pdf') return state.currentPdf === 'available';
    if (action === 'published') return state.currentStatus === 'published';
    if (action === 'smart-cfd') return state.currentCategory === '流体力学 / 智能CFD';
    if (action === 'early-access') return state.currentSpecial === 'early-access';
    return false;
}

/**
 * 动态更新今日新增计数 — 基于论文数据的本地日期
 */
export function updateTodayCount(allPapersData) {
    const today = state.currentDate || localToday();
    const count = allPapersData.filter(p => p.published === today).length;
    const card = document.querySelector('.summary-action[data-summary-action="today"] .summary-value');
    if (card) card.textContent = count;
}

/**
 * 切换「今日新增」卡片的标签：激活时显示「当日新增」，取消时恢复
 */
export function syncTodayCardLabel() {
    const card = document.querySelector('.summary-action[data-summary-action="today"]');
    const labelEl = card?.querySelector('.summary-label');
    if (!labelEl) return;
    if (state.currentDate !== '') {
        labelEl.textContent = '当日新增';
    } else {
        labelEl.textContent = '今日新增';
    }
}

/**
 * 更新所有 summary action 卡片的激活状态样式
 */
export function updateSummaryActionStates() {
    if (!dom.summaryActions) return;
    dom.summaryActions.forEach(card => {
        const action = card.dataset.summaryAction;
        card.classList.toggle('active', summaryActionIsActive(action));
    });
}
