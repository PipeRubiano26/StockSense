/* Simulador de escenarios: envía los supuestos al servidor y compara los resultados del modelo */
(() => {
  const form = document.getElementById("scenarioForm");
  const button = document.getElementById("scenarioButton");
  const errorBox = document.getElementById("scenarioError");
  const charts = {};
  let timer = null;

  function parameters() {
    const data = Object.fromEntries(new FormData(form).entries());
    Object.keys(data).forEach((key) => { data[key] = Number(data[key]); });
    return data;
  }

  function card(scenario) {
    const a = scenario.analysis;
    const color = SS.scenarioColors[scenario.key];
    const days = a.days_to_stockout === null ? `> ${a.horizon_days}` : SS.number(a.days_to_stockout, 1);
    const source = scenario.source === "modelo"
      ? `<span class="ss-badge source-modelo">modelo</span>` : `<span class="ss-badge source-supuesto">modelo + supuesto</span>`;
    return `<div>
      <div class="ss-scenario" style="border-top: 4px solid ${color}">
        <div class="ss-scenario-head"><div class="fw-bold mb-1">${SS.escape(scenario.name)}</div>${source}</div>
        <div class="ss-scenario-body">
          <dl>
            <dt>Unidades (7 días)</dt><dd>${SS.number(a.demand_7d)}</dd>
            <dt>Unidades (30 días)</dt><dd>${SS.number(a.demand_30d)}</dd>
            <dt>Días hasta agotarse</dt><dd>${days}</dd>
            <dt>Fecha agotamiento</dt><dd>${a.stockout_date ? SS.shortDate(a.stockout_date) : "—"}</dd>
            <dt>Entrega</dt><dd>${a.lead_time_days} días</dd>
            <dt>Reposición</dt><dd>${SS.number(a.recommended_quantity)} u.</dd>
          </dl>
          <div class="mt-2">${SS.riskBadge(a.risk)}</div>
          <ul class="ss-assumptions">${scenario.assumptions.map((text) => `<li>${SS.escape(text)}</li>`).join("")}</ul>
        </div>
      </div></div>`;
  }

  function render(result) {
    document.getElementById("scenarioEmpty").classList.add("d-none");
    document.getElementById("scenarioResult").classList.remove("d-none");
    document.getElementById("scenarioWarnings").innerHTML = result.warnings.map((text) =>
      `<div class="alert alert-warning py-2"><i class="bi bi-exclamation-triangle"></i> ${SS.escape(text)}</div>`).join("");
    document.getElementById("scenarioCards").innerHTML = result.scenarios.map(card).join("");

    const n = SS.projectionWindow(result.scenarios.map((s) => s.analysis), result.dates.length);
    const labels = result.dates.slice(0, n).map(SS.shortDate);
    charts.stock?.destroy();
    charts.stock = new Chart(document.getElementById("scenarioStockChart"), {
      type: "line",
      data: {
        labels,
        datasets: [
          ...result.scenarios.filter((s) => s.key !== "supplier_delay").map((s) => ({
            label: s.name, data: s.analysis.stock_projection.slice(0, n), borderColor: SS.scenarioColors[s.key],
            backgroundColor: SS.scenarioColors[s.key], pointRadius: 0, borderWidth: 2, tension: .15,
          })),
          { label: "Stock mínimo", data: labels.map(() => result.product.minimum_stock), borderColor: "#0f172a",
            borderDash: [5, 4], pointRadius: 0, borderWidth: 1 },
        ],
      },
      options: { interaction: { mode: "index", intersect: false },
        scales: { x: { ticks: { maxTicksLimit: 10 }, grid: { display: false } }, y: { beginAtZero: true, title: { display: true, text: "unidades" } } } },
    });

    const horizon = result.parameters.horizon;
    charts.days?.destroy();
    charts.days = new Chart(document.getElementById("scenarioDaysChart"), {
      type: "bar",
      data: {
        labels: result.scenarios.map((s) => s.name),
        datasets: [
          { label: "Días hasta agotarse", borderRadius: 4,
            data: result.scenarios.map((s) => s.analysis.days_to_stockout ?? horizon),
            backgroundColor: result.scenarios.map((s) => SS.scenarioColors[s.key]) },
          { label: "Tiempo de entrega", borderRadius: 4,
            data: result.scenarios.map((s) => s.analysis.lead_time_days), backgroundColor: "#cbd5e1" },
        ],
      },
      options: {
        indexAxis: "y",
        plugins: { tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${SS.number(ctx.parsed.x, 1)} días` } } },
        scales: { x: { beginAtZero: true, title: { display: true, text: "días" } }, y: { grid: { display: false } } },
      },
    });
  }

  async function run(event) {
    event?.preventDefault();
    const params = parameters();
    if (!params.product_id) return;
    button.disabled = true;
    errorBox.classList.add("d-none");
    try {
      render(await SS.postJSON(window.SCENARIO_URL, params));
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove("d-none");
    } finally {
      button.disabled = false;
    }
  }

  form.addEventListener("submit", run);
  form.querySelectorAll("input[type=range]").forEach((input) => {
    input.addEventListener("input", () => {
      document.getElementById(input.id + "Value").textContent = input.value;
      clearTimeout(timer);
      timer = setTimeout(run, 350);   // recalcula al soltar el control
    });
  });
  form.querySelectorAll("select").forEach((select) => select.addEventListener("change", run));
  if (document.getElementById("scenarioProduct").value) run();
})();
