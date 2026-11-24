/* StockSense — utilidades compartidas del frontend */
const SS = {
  colors: {
    primary: "#4f46e5", primarySoft: "rgba(79, 70, 229, .12)", teal: "#0d9488", amber: "#d97706",
    red: "#dc2626", darkRed: "#991b1b", green: "#059669", slate: "#94a3b8", grid: "#eef2f7",
  },
  // Colores fijos por escenario (se usan en tarjetas y gráficos)
  scenarioColors: {
    normal: "#4f46e5", promotion: "#0d9488", high_demand: "#dc2626", low_demand: "#059669", supplier_delay: "#d97706",
  },

  number(value, decimals = 0) {
    if (value === null || value === undefined || Number.isNaN(value)) return "—";
    return Number(value).toLocaleString("es-CO", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  },
  money(value) { return "$ " + SS.number(value); },
  date(iso) {
    if (!iso) return "—";
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString("es-CO", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  },
  shortDate(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString("es-CO", { day: "numeric", month: "short" });
  },
  riskBadge(risk) {
    const css = risk.replace("í", "i");
    return `<span class="ss-badge risk-${css}">Riesgo ${risk}</span>`;
  },
  // Días a mostrar en una proyección de stock: hasta unos días después del agotamiento
  projectionWindow(analyses, total) {
    const days = analyses.map((a) => a.days_to_stockout).filter((d) => d !== null);
    if (days.length < analyses.length) return total;
    return Math.min(total, Math.max(21, Math.ceil(Math.max(...days)) + 10));
  },
  escape(text) {
    const div = document.createElement("div");
    div.textContent = text ?? "";
    return div.innerHTML;
  },
  readJSON(id) {
    const element = document.getElementById(id);
    return element ? JSON.parse(element.textContent) : null;
  },
  async postJSON(url, payload) {
    const response = await fetch(url, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({ error: "Respuesta inválida del servidor" }));
    if (!response.ok) {
      const fields = data.fields ? Object.values(data.fields).join(" ") : "";
      throw new Error(`${data.error || "Error"}${fields ? ": " + fields : ""}`);
    }
    return data;
  },
};

if (window.Chart) {
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.font.size = 12;
  Chart.defaults.locale = "es-CO";
  Chart.defaults.color = "#64748b";
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 8;
  Chart.defaults.plugins.tooltip.backgroundColor = "#0f172a";
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.scale.grid.color = SS.colors.grid;
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.animation.duration = 400;
}

// Búsqueda instantánea en tablas: <input data-table-search="#idTabla">
document.querySelectorAll("[data-table-search]").forEach((input) => {
  const table = document.querySelector(input.dataset.tableSearch);
  if (!table) return;
  input.addEventListener("input", () => {
    const term = input.value.trim().toLowerCase();
    table.querySelectorAll("tbody tr[data-row]").forEach((row) => {
      row.hidden = term && !row.textContent.toLowerCase().includes(term);
    });
  });
});

// Confirmación antes de acciones destructivas: <form data-confirm="mensaje">
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});
