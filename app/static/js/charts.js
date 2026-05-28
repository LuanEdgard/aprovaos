(function () {
  const A = window.AprovaOS;
  const charts = {};

  function renderChart(id, type, labels, datasets, options = {}) {
    const canvas = document.getElementById(id);
    if (!canvas || !window.Chart) return;
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(canvas, {
      type,
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: getComputedStyle(document.documentElement).getPropertyValue("--muted") } } },
        scales: {
          x: { ticks: { color: getComputedStyle(document.documentElement).getPropertyValue("--muted") }, grid: { color: "rgba(148, 163, 184, 0.12)" } },
          y: { ticks: { color: getComputedStyle(document.documentElement).getPropertyValue("--muted") }, grid: { color: "rgba(148, 163, 184, 0.12)" } },
        },
        ...options,
      },
    });
  }

  A.renderChart = renderChart;
})();

