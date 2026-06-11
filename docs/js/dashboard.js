/**
 * 仪表盘辅助函数 — 日期选择器同步、Summary 卡片状态管理
 */

import { state, dom } from './state.js';
import { localToday } from './utils.js';

/**
 * 同步日期选择器到指定月份（仅在未手动选日期时生效）
 */
export function syncDailyPickerToMonth(month) {
    if (!dom.dailyDatePicker || state.currentDate) return;
    dom.dailyDatePicker.value = /^\d{4}-\d{2}$/.test(String(month || '')) ? `${month}-01` : '';
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
    if (action === 'today') return state.currentDate === today;
    if (action === 'month') return state.currentMonth === today.slice(0, 7) && !state.currentDate;
    if (action === 'pdf') return state.currentPdf === 'available';
    if (action === 'published') return state.currentStatus === 'published';
    if (action === 'smart-cfd') return state.currentCategory === '流体力学 / 智能CFD';
    if (action === 'early-access') return state.currentSpecial === 'early-access';
    return false;
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
