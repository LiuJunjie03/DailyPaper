/**
 * 共享状态对象 + DOM 引用
 * 所有模块通过此对象共享可变状态，避免全局变量污染
 */

export const state = {
    allPapersData: [],
    currentMonth: 'all',
    currentStatus: 'all',
    currentPdf: 'all',
    currentLanguage: 'all',
    currentCategory: 'all',
    currentSort: 'date-desc',
    currentDate: '',
    currentSpecial: '',
    searchTerm: '',
    filteredPapers: [],
    loadedCount: 0,
    isLoading: false,
    observer: null,
    monthsCache: {},
    selectedPaperIds: new Set(),
    searchTimer: null,
    initialBatchSize: 20,
    subsequentBatchSize: 10,
};

// DOM 元素引用，在 main.js 初始化时填充
export const dom = {};
