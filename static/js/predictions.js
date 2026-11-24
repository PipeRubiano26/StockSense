/* Módulo de predicciones: solicita la inferencia al servidor y muestra los resultados */
(() => {
  const form = document.getElementById("predictionForm");
  const productSelect = document.getElementById("productSelect");
  const horizonSelect = document.getElementById("horizonSelect");
  const button = document.getElementById("predictButton");
  const errorBox = document.getElementById("predictionError");
  const charts = {};

  function kpi(label, value, extra = "") {
    return `<div class="col-6 col-md-4 col-xl-2"><div class="ss-kpi"><div class="ss-kpi-label">${label}</div>
            <div class="ss-kpi-value">${value}</div>${extra}</div></div>`;
  }

  function renderKpis(result) {
    const a = result.analysis;
    const days = a.days_to_stockout === null ? `> ${a.horizon_days}` : SS.number(a.days_to_stockout, 1);
    document.getElementById("kpis").innerHTML = [
      kpi("Demanda estimada hoy", SS.number(a.demand_today, 1),
          result.forecast.sold_today ? `<div class="ss-stat-hint">ya vendidas hoy: ${result.forecast.sold_today}</div>` : ""),
      kpi("Demanda próximos 7 días", SS.number(a.demand_7d)),
      kpi("Demanda próximos 30 días", SS.number(a.demand_30d)),
      kpi("Días hasta agotarse", days, `<div class="ss-stat-hint">stock actual: ${SS.number(a.current_stock)}</div>`),
      kpi("Fecha estimada de agotamiento", `<span class="fs-6">${a.stockout_date ? SS.date(a.stockout_date) : "Fuera del horizonte"}</span>`),
      kpi("Nivel de riesgo", SS.riskBadge(a.risk), `<div class="ss-stat-hint mt-1">${SS.escape(a.risk_reason)}</div>`),
    ].join("");
  }

  function renderWarnings(result) {
    const items = [...result.warnings];
    result.pending_orders.filter((o) => o.delayed).forEach((o) =>
      items.push(`La orden #${o.id} (${o.quantity} u.) debía llegar el ${o.expected_delivery} y sigue pendiente.`));
    document.getElementById("predictionWarnings").innerHTML = items.map((text) =>
      `<div class="alert alert-warning py-2"><i class="bi bi-exclamation-triangle"></i> ${SS.escape(text)}</div>`).join("");
  }

  function renderDemandChart(history, result) {
    const labels = [...history.labels, ...result.forecast.dates];
    const actual = [...history.units, ...result.forecast.dates.map(() => null)];
    const forecast = [...history.labels.map(() => null), ...result.forecast.units];
    charts.demand?.destroy();
    charts.demand = new Chart(document.getElementById("demandChart"), {
      type: "line",
      data: {
        labels: labels.map(SS.shortDate),
        datasets: [
          { label: "Ventas reales", data: actual, borderColor: SS.colors.slate, backgroundColor: SS.colors.slate,
            pointRadius: 0, borderWidth: 1.5, tension: .2 },
          { label: "Demanda estimada (modelo)", data: forecast, borderColor: SS.colors.primary,
            backgroundColor: SS.colors.primarySoft, fill: true, pointRadius: 0, borderWidth: 2, tension: .2 },
        ],
      },
      options: { interaction: { mode: "index", intersect: false }, spanGaps: false,
        scales: { x: { ticks: { maxTicksLimit: 12 }, grid: { display: false } }, y: { beginAtZero: true } } },
    });
  }

  function renderStockChart(result) {
    const a = result.analysis;
    const n = SS.projectionWindow([a], a.stock_projection.length);
    const projection = a.stock_projection.slice(0, n);
    charts.stock?.destroy();
    charts.stock = new Chart(document.getElementById("stockChart"), {
      type: "line",
      data: {
        labels: result.forecast.dates.slice(0, n).map(SS.shortDate),
        datasets: [
          { label: "Stock proyectado", data: projection, borderColor: SS.colors.primary, pointRadius: 0,
            borderWidth: 2, fill: true, backgroundColor: SS.colors.primarySoft },
          { label: "Stock mínimo", data: projection.map(() => a.minimum_stock), borderColor: SS.colors.amber,
            borderDash: [6, 4], pointRadius: 0, borderWidth: 1.5 },
          { label: "Punto de reorden", data: projection.map(() => a.reorder_point), borderColor: SS.colors.red,
            borderDash: [2, 3], pointRadius: 0, borderWidth: 1.5 },
        ],
      },
      options: { interaction: { mode: "index", intersect: false },
        scales: { x: { ticks: { maxTicksLimit: 8 }, grid: { display: false } }, y: { beginAtZero: true } } },
    });
  }

  function renderFactors(result) {
    const e = result.explanation;
    document.getElementById("factorIntro").innerHTML =
      `Como el modelo es lineal, la predicción de hoy se descompone exactamente: intercepto (${SS.number(e.intercept, 2)}) + suma de efectos = <strong>${SS.number(e.raw_prediction, 2)}</strong> unidades. ` +
      `Las variables numéricas se comparan con el promedio del entrenamiento; las categóricas con la referencia (lunes, enero, Abarrotes).`;
    const max = Math.max(...e.factors.map((f) => Math.abs(f.contribution)), 1);
    document.querySelector("#factorTable tbody").innerHTML = e.factors.map((f) => {
      const width = Math.round(Math.abs(f.contribution) / max * 100);
      const color = f.contribution >= 0 ? SS.colors.primary : SS.colors.red;
      const value = f.value === null || f.value === undefined ? "<span class='text-secondary'>derivada</span>"
        : typeof f.value === "number" ? SS.number(f.value, Number.isInteger(f.value) ? 0 : 2) : SS.escape(f.value);
      return `<tr><td>${SS.escape(f.label)}</td><td class="num">${value}</td>
        <td style="min-width:120px"><div class="ss-factor-bar" style="width:${width}%;background:${color}"></div></td>
        <td class="num fw-semibold ${f.contribution >= 0 ? "" : "text-danger"}">${f.contribution >= 0 ? "+" : ""}${SS.number(f.contribution, 2)}</td></tr>`;
    }).join("");
  }

  function renderRecommendation(result) {
    const a = result.analysis;
    const pending = a.pending_quantity ? ` − pendientes ${SS.number(a.pending_quantity)}` : "";
    document.getElementById("recommendation").innerHTML = `
      <div class="d-flex align-items-baseline gap-2 mb-2">
        <span class="ss-kpi-value">${SS.number(a.recommended_quantity)}</span><span class="text-secondary">unidades recomendadas</span>
      </div>
      <dl class="row small mb-3">
        <dt class="col-7 fw-normal text-secondary">Tiempo de entrega</dt><dd class="col-5 text-end">${a.lead_time_days} días</dd>
        <dt class="col-7 fw-normal text-secondary">Demanda durante la entrega</dt><dd class="col-5 text-end">${SS.number(a.demand_lead_time, 1)}</dd>
        <dt class="col-7 fw-normal text-secondary">Punto de reorden</dt><dd class="col-5 text-end">${SS.number(a.reorder_point)}</dd>
        <dt class="col-7 fw-normal text-secondary">¿Requiere reposición?</dt><dd class="col-5 text-end">${a.needs_reorder ? "Sí" : "No"}</dd>
      </dl>
      <div class="ss-notice mb-3">Cantidad = demanda estimada de ${a.lead_time_days} + ${a.coverage_days} días + stock mínimo (${a.minimum_stock}) − stock actual (${a.current_stock})${pending}.</div>
      ${a.recommended_quantity > 0 ? `
      <form method="post" action="${window.PREDICTION_URLS.order.replace("/0/", `/${result.product.id}/`)}">
        <input type="hidden" name="quantity" value="${a.recommended_quantity}">
        <input type="hidden" name="next" value="${window.PREDICTION_URLS.next}?product_id=${result.product.id}">
        <button class="btn btn-outline-primary w-100"><i class="bi bi-cart-plus"></i> Crear orden de compra por ${SS.number(a.recommended_quantity)} u.</button>
      </form>` : ""}`;
  }

  function renderMethod(result) {
    const m = result.model.test_metrics || {};
    document.getElementById("methodNotes").innerHTML = `
      <p class="mb-2">${SS.escape(result.forecast.method)}</p>
      <p class="mb-2">Variables: precio, descuento, promoción, ventas del día anterior, promedios de 7 y 30 días, día de la semana, mes y categoría.
      El inventario <strong>no</strong> es una variable del modelo: solo se usa después para calcular el agotamiento.</p>
      <p class="mb-0 text-secondary">Modelo v${result.model.version} · entrenado ${(result.model.trained_at || "").slice(0, 10)} ·
      prueba: MAE ${SS.number(m.MAE, 2)}, RMSE ${SS.number(m.RMSE, 2)}, R² ${SS.number(m.R2, 3)} (datos sintéticos).</p>`;
  }

  async function run(event) {
    event?.preventDefault();
    const productId = productSelect.value;
    if (!productId) return;
    button.disabled = true;
    button.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Calculando...`;
    errorBox.classList.add("d-none");
    try {
      const [result, history] = await Promise.all([
        SS.postJSON(window.PREDICTION_URLS.forecast, { product_id: Number(productId), horizon: Number(horizonSelect.value) }),
        fetch(window.PREDICTION_URLS.history + productId + "?days=90").then((r) => r.json()),
      ]);
      document.getElementById("predictionEmpty").classList.add("d-none");
      document.getElementById("predictionResult").classList.remove("d-none");
      renderWarnings(result); renderKpis(result); renderDemandChart(history, result);
      renderStockChart(result); renderFactors(result); renderRecommendation(result); renderMethod(result);
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove("d-none");
    } finally {
      button.disabled = false;
      button.innerHTML = `<i class="bi bi-cpu"></i> Generar predicción`;
    }
  }

  form.addEventListener("submit", run);
  if (productSelect.value) run();
})();
