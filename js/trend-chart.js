/**
 * Smart CFD subcategory trend chart.
 *
 * Default view: selected year, month-by-month.
 * Quarter view: all available quarters.
 * Chart type can switch between line and grouped bar.
 */

function readTrendData() {
    if (window.SMART_CFD_TRENDS) return window.SMART_CFD_TRENDS;
    const dataEl = document.getElementById('smartCfdTrendsData');
    if (!dataEl) return null;
    try {
        return JSON.parse(dataEl.textContent || '{}');
    } catch (error) {
        console.warn('Failed to parse Smart CFD trend data', error);
        return null;
    }
}

const trends = readTrendData();
if (trends) {
    window.SMART_CFD_TRENDS = trends;
}

const canvas = document.getElementById('trendChart');
const modeButtons = Array.from(document.querySelectorAll('[data-trend-mode]'));
const typeButtons = Array.from(document.querySelectorAll('[data-chart-type]'));
const yearSelect = document.getElementById('trendYearSelect');
const yearSelectWrap = document.querySelector('.trend-year-select-wrap');
let trendChart = null;
let currentMode = 'year';
let currentChartType = 'line';

const palette = [
    '#2563eb',
    '#db2777',
    '#16a34a',
    '#f97316',
    '#7c3aed',
    '#0891b2',
    '#ca8a04',
    '#475569',
];

function availableYears() {
    return (trends?.years || []).filter(Boolean);
}

function fillYearOptions() {
    if (!yearSelect) return;
    const years = availableYears();
    yearSelect.innerHTML = '';
    years.forEach(year => {
        const option = document.createElement('option');
        option.value = year;
        option.textContent = year;
        yearSelect.appendChild(option);
    });
    if (trends?.default_year && years.includes(trends.default_year)) {
        yearSelect.value = trends.default_year;
    } else if (years.length) {
        yearSelect.value = years[years.length - 1];
    }
}

function datasetFor(subdir, values, index) {
    const color = palette[index % palette.length];
    const label = (trends?.short_names || {})[subdir] || subdir.split('/').pop().trim();
    return {
        label,
        data: values || [],
        borderColor: color,
        backgroundColor: currentChartType === 'bar' ? `${color}b8` : `${color}20`,
        borderWidth: currentChartType === 'bar' ? 1 : 2,
        borderRadius: currentChartType === 'bar' ? 5 : 0,
        pointRadius: currentChartType === 'bar' ? 0 : 3,
        pointHoverRadius: currentChartType === 'bar' ? 0 : 5,
        tension: 0.28,
        fill: false,
    };
}

function setActiveMode(mode) {
    currentMode = mode;
    modeButtons.forEach(button => {
        button.classList.toggle('active', button.dataset.trendMode === mode);
    });
    if (yearSelectWrap) {
        yearSelectWrap.classList.toggle('is-hidden', mode !== 'year');
    }
}

function setActiveChartType(type) {
    currentChartType = type === 'bar' ? 'bar' : 'line';
    typeButtons.forEach(button => {
        button.classList.toggle('active', button.dataset.chartType === currentChartType);
    });
}

function currentChartData() {
    const subdirs = trends?.subdirs || [];
    if (currentMode === 'quarter') {
        const quarterData = trends?.quarters || {};
        return {
            labels: quarterData.labels || [],
            xTitle: '季度',
            datasets: subdirs.map((subdir, index) => datasetFor(
                subdir,
                (quarterData.trends || {})[subdir],
                index,
            )),
        };
    }

    const selectedYear = yearSelect?.value || trends?.default_year;
    const yearData = trends?.yearly?.[selectedYear] || {};
    return {
        labels: yearData.display_labels || yearData.labels || [],
        xTitle: `${selectedYear || ''} 年月份`,
        datasets: subdirs.map((subdir, index) => datasetFor(
            subdir,
            (yearData.trends || {})[subdir],
            index,
        )),
    };
}

function renderTrendChart() {
    if (!canvas || typeof Chart === 'undefined') return;
    const chartData = currentChartData();
    if (!chartData.labels.length || !chartData.datasets.length) return;

    if (trendChart) {
        trendChart.destroy();
    }

    trendChart = new Chart(canvas, {
        type: currentChartType,
        data: {
            labels: chartData.labels,
            datasets: chartData.datasets,
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            aspectRatio: 2.45,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        boxWidth: 12,
                        padding: 12,
                        font: { size: 11 },
                    },
                },
                tooltip: {
                    callbacks: {
                        title(items) {
                            return items[0]?.label || '';
                        },
                    },
                },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1,
                        precision: 0,
                    },
                    title: {
                        display: true,
                        text: '论文数量',
                    },
                },
                x: {
                    title: {
                        display: true,
                        text: chartData.xTitle,
                    },
                },
            },
        },
    });
}

if (trends && canvas) {
    fillYearOptions();
    setActiveMode('year');
    setActiveChartType('line');
    renderTrendChart();

    modeButtons.forEach(button => {
        button.addEventListener('click', () => {
            setActiveMode(button.dataset.trendMode || 'year');
            renderTrendChart();
        });
    });

    typeButtons.forEach(button => {
        button.addEventListener('click', () => {
            setActiveChartType(button.dataset.chartType || 'line');
            renderTrendChart();
        });
    });

    yearSelect?.addEventListener('change', renderTrendChart);
    document.querySelector('.trend-panel')?.addEventListener('toggle', () => {
        trendChart?.resize();
    });
}
