/**
 * 纯工具函数 — 无状态依赖，可独立测试
 */

export function debugLog(...args) {
    if (window.DEBUG) console.log(...args);
}

export function escapeHTML(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }[char]));
}

export function escapeAttribute(value) {
    return escapeHTML(value).replace(/`/g, '&#96;');
}

export function safeURL(value, fallback = '#') {
    try {
        const url = new URL(String(value || ''), window.location.href);
        return ['http:', 'https:'].includes(url.protocol) ? url.href : fallback;
    } catch (e) {
        return fallback;
    }
}

export function formatDate(dateStr) {
    if (!dateStr) return '未知';
    if (/^\d{4}$/.test(dateStr)) return dateStr + '年';
    if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
        const [y, m, d] = dateStr.split('-');
        return y + '年' + parseInt(m) + '月' + parseInt(d) + '日';
    }
    return dateStr;
}

export function parseDate(dateStr) {
    if (!isCompleteDate(dateStr)) return new Date(0);
    return new Date(dateStr + 'T00:00:00Z');
}

export function isCompleteDate(dateStr) {
    return /^\d{4}-\d{2}-\d{2}$/.test(String(dateStr || ''));
}

export function sanitizeFilename(value) {
    return String(value || 'paper')
        .replace(/[\\/:*?"<>|]+/g, '_')
        .replace(/\s+/g, ' ')
        .trim()
        .slice(0, 120) || 'paper';
}

export function tagClass(tag) {
    if (tag.includes('智能CFD')) return 'tag-smart';
    if (tag.includes('机器学习')) return 'tag-ml';
    if (tag.includes('湍流')) return 'tag-turbulence';
    if (tag.includes('多相流')) return 'tag-multiphase';
    if (tag.includes('流动控制')) return 'tag-control';
    return 'tag-fluid';
}

export function dataURL(path) {
    const version = window.DATA_VERSION || 'dev';
    const separator = path.includes('?') ? '&' : '?';
    return `${path}${separator}v=${encodeURIComponent(version)}`;
}

/**
 * 返回本地日期字符串 "YYYY-MM-DD"（避免 toISOString 的 UTC 偏移问题）
 */
export function localToday() {
    if (window.TODAY) return window.TODAY;
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
