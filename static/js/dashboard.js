/* Gráficos del dashboard (datos calculados por Flask desde SQLite y el modelo) */
(() => {
  const data = SS.readJSON("dashboardData");
  if (!data) return;

  new Chart(document.getElementById("salesChart"), {
    type: "line",
    data: {
      labels: data.sales.labels.map(SS.shortDate),
      datasets: [{
        label: "Unidades vendidas", data: data.sales.units, borderColor: SS.colors.primary,
        backgroundColor: SS.colors.primarySoft, fill: true, tension: .3, pointRadius: 0, borderWidth: 2,
      }],
    },
    options: {
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: false } },
      scales: { x: { ticks: { maxTicksLimit: 10 }, grid: { display: false } }, y: { beginAtZero: true } },
    },
  });

  // Barras horizontales: stock actual por producto, con el mínimo como referencia
  const stockColors = data.inventory.stock.map((stock, i) =>
    stock === 0 ? SS.colors.darkRed : stock <= data.inventory.minimum[i] ? SS.colors.amber : SS.colors.primary);
  new Chart(document.getElementById("inventoryChart"), {
    type: "bar",
    data: {
      labels: data.inventory.labels,
      datasets: [
        { label: "Stock actual", data: data.inventory.stock, backgroundColor: stockColors, borderRadius: 4, barPercentage: .7 },
        { label: "Stock mínimo", data: data.inventory.minimum, type: "line", showLine: false, pointStyle: "line",
          pointRadius: 8, pointBorderWidth: 2, borderColor: "#0f172a", backgroundColor: "#0f172a" },
      ],
    },
    options: {
      indexAxis: "y",
      plugins: { tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${SS.number(ctx.parsed.x)} u.` } } },
      scales: { x: { beginAtZero: true }, y: { grid: { display: false }, ticks: { autoSkip: false, font: { size: 11 } } } },
    },
  });

  const riskCanvas = document.getElementById("riskChart");
  if (riskCanvas) {
    const levels = ["crítico", "alto", "medio", "bajo"];
    new Chart(riskCanvas, {
      type: "doughnut",
      data: {
        labels: levels.map((level) => level[0].toUpperCase() + level.slice(1)),
        datasets: [{
          data: levels.map((level) => data.risk[level]),
          backgroundColor: [SS.colors.darkRed, SS.colors.red, SS.colors.amber, SS.colors.green],
          borderWidth: 2, borderColor: "#fff",
        }],
      },
      options: { cutout: "62%", plugins: { legend: { position: "bottom" },
        tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${ctx.parsed} productos` } } } },
    });
  }
})();
