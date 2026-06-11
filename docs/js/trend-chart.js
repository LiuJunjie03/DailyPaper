/**
 * 智能 CFD 子方向月度趋势折线图
 * 依赖：Chart.js（CDN 加载）
 */

const trends = window.SUBDIR_TRENDS;
if (trends && trends.months && trends.months.length > 0 && typeof Chart !== 'undefined') {
    const ctx = document.getElementById('trendChart');
    if (!ctx) throw new Error('#trendChart not found');

    // 子方向颜色调色板
    const palette = [
        '#4dc9f6', '#f67019', '#f53794', '#537bc4',
        '#acc236', '#166a8f', '#00a950', '#58595b',
    ];

    const datasets = trends.subdirs.map((subdir, i) => {
        const shortName = (trends.short_names || {})[subdir] || subdir.split('/').pop().trim();
        const data = trends.months.map(month => (trends.trends[subdir] || {})[month] || 0);
        return {
            label: shortName,
            data: data,
            borderColor: palette[i % palette.length],
            backgroundColor: palette[i % palette.length] + '22',
            borderWidth: 2,
            pointRadius: 3,
            pointHoverRadius: 5,
            tension: 0.3,
            fill: false,
        };
    });

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: trends.months,
            datasets: datasets,
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            aspectRatio: 2.5,
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
                        title: function(items) {
                            return items[0].label;
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
                        text: '月份',
                    },
                },
            },
        },
    });
}
