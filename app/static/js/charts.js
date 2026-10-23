/**
 * Kua Chart.js Dashboard Integrations — Celeste Marino Palette (#0083B0)
 */

window.vivaVoceCharts = {
    performanceChartInstance: null,
    radarChartInstance: null,
    sm2ChartInstance: null,

    renderPerformanceChart(canvasId, timeline) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;

        if (this.performanceChartInstance) {
            this.performanceChartInstance.destroy();
        }

        const labels = timeline.length > 0
            ? timeline.map((item, idx) => `Sesión ${idx + 1}`)
            : ['Sesión 1', 'Sesión 2'];
        
        const scores = timeline.length > 0
            ? timeline.map(item => item.overall_score || 0)
            : [85, 92];

        const clarities = timeline.length > 0
            ? timeline.map(item => item.session_clarity || 0)
            : [88, 94];

        this.performanceChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Puntaje Oral',
                        data: scores,
                        borderColor: '#0083B0',
                        backgroundColor: 'rgba(0, 131, 176, 0.12)',
                        borderWidth: 3,
                        pointBackgroundColor: '#0083B0',
                        pointRadius: 5,
                        pointHoverRadius: 7,
                        tension: 0.35,
                        fill: true
                    },
                    {
                        label: 'Índice de Claridad',
                        data: clarities,
                        borderColor: '#00B4DB',
                        backgroundColor: 'rgba(0, 180, 219, 0.08)',
                        borderWidth: 2.5,
                        pointBackgroundColor: '#00B4DB',
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        tension: 0.35,
                        fill: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            font: { family: "'Outfit', sans-serif", weight: '600' },
                            usePointStyle: true,
                            boxWidth: 8
                        }
                    },
                    tooltip: {
                        backgroundColor: '#0F172A',
                        titleFont: { family: "'Outfit', sans-serif" },
                        bodyFont: { family: "'Outfit', sans-serif" },
                        padding: 12,
                        cornerRadius: 12
                    }
                },
                scales: {
                    y: {
                        min: 0,
                        max: 100,
                        grid: { color: 'rgba(226, 238, 244, 0.7)' },
                        ticks: {
                            font: { family: "'Outfit', sans-serif" },
                            callback: value => value + ' pts'
                        }
                    },
                    x: {
                        grid: { display: false },
                        ticks: { font: { family: "'Outfit', sans-serif" } }
                    }
                }
            }
        });
    },

    renderSkillsRadarChart(canvasId, stats) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;

        if (this.radarChartInstance) {
            this.radarChartInstance.destroy();
        }

        const avgScore = stats.avg_oral_score || 85;
        const avgClarity = stats.avg_clarity || 88;
        const fluencyScore = Math.max(50, Math.min(100, Math.round(100 - (stats.avg_fillers_per_ans || 1) * 6)));
        const conceptualScore = Math.min(100, Math.round(avgScore * 1.02));
        const synthesisScore = Math.round((avgScore + avgClarity) / 2);

        this.radarChartInstance = new Chart(ctx, {
            type: 'radar',
            data: {
                labels: ['Dominio Conceptual', 'Claridad', 'Fluidez Verbal', 'Vocabulario', 'Síntesis'],
                datasets: [{
                    label: 'Perfil de Competencias',
                    data: [conceptualScore, avgClarity, fluencyScore, 86, synthesisScore],
                    backgroundColor: 'rgba(0, 131, 176, 0.20)',
                    borderColor: '#0083B0',
                    borderWidth: 2.5,
                    pointBackgroundColor: '#0083B0',
                    pointBorderColor: '#fff',
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    r: {
                        min: 30,
                        max: 100,
                        ticks: { display: false, stepSize: 20 },
                        grid: { color: 'rgba(200, 225, 235, 0.8)' },
                        pointLabels: {
                            font: { family: "'Outfit', sans-serif", weight: '600', size: 12 },
                            color: '#334155'
                        }
                    }
                }
            }
        });
    },

    renderSm2DistributionChart(canvasId, stats) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;

        if (this.sm2ChartInstance) {
            this.sm2ChartInstance.destroy();
        }

        const mastered = stats.mastered_cards || 0;
        const learning = stats.learning_cards || 0;
        const dueToday = stats.cards_due_today || 0;

        this.sm2ChartInstance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Dominadas (SM-2)', 'En Aprendizaje', 'Pendientes Hoy'],
                datasets: [{
                    data: [mastered, learning, dueToday],
                    backgroundColor: ['#0083B0', '#00B4DB', '#F59E0B'],
                    borderWidth: 3,
                    borderColor: '#FFFFFF'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '72%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            font: { family: "'Outfit', sans-serif", weight: '500' },
                            usePointStyle: true,
                            boxWidth: 8
                        }
                    }
                }
            }
        });
    }
};
