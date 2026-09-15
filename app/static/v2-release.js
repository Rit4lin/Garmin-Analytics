(() => {
  const componentLabels = {
    hrv: "HRV",
    resting_hr: "FC reposo",
    sleep: "Sueño",
    stress: "Estrés",
    body_battery: "Body Battery",
    readiness: "Readiness",
  };

  const safe = value => String(value ?? "—")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const valueText = (value, suffix = "") =>
    value === null || value === undefined ? "—" : `${value}${suffix}`;

  async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) throw Error("No se pudo cargar la métrica v2");
    return response.json();
  }

  function ensureReleasePanel() {
    if (document.querySelector("#release-metrics")) return;
    const section = document.createElement("section");
    section.id = "release-metrics";
    section.className = "analysis-grid release-grid";
    section.innerHTML = `
      <article>
        <div class="section-heading">
          <h2>Recuperación · desglose</h2>
          <span>Qué empuja el Recovery Score</span>
        </div>
        <div id="recovery-components" class="release-components"></div>
      </article>
      <article>
        <div class="section-heading">
          <h2>Métricas adicionales</h2>
          <span>Garmin + estado de entrenamiento</span>
        </div>
        <div id="release-extra-metrics" class="metric-list"></div>
      </article>
    `;
    document.querySelector("#cards")?.after(section);

    const style = document.createElement("style");
    style.textContent = `
      .release-components{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
      .release-component{background:var(--panel2);padding:10px;border-radius:7px;border-left:3px solid var(--line)}
      .release-component.mejorando{border-left-color:var(--accent)}
      .release-component.empeorando{border-left-color:var(--red)}
      .release-component.estable{border-left-color:var(--blue)}
      .release-component strong{display:block;margin:4px 0;font-size:16px}
      .release-component small{color:var(--muted)}
      @media(max-width:520px){.release-components{grid-template-columns:1fr}}
    `;
    document.head.append(style);
  }

  function average(values) {
    const clean = values.filter(value => Number.isFinite(value));
    return clean.length ? clean.reduce((total, value) => total + value, 0) / clean.length : null;
  }

  function fitnessAgeTrend(rows) {
    const values = rows
      .filter(row => Number.isFinite(row.fitness_age) && row.date)
      .map(row => ({date: new Date(row.date), value: Number(row.fitness_age)}))
      .sort((a, b) => a.date - b.date);
    if (!values.length) return {current: null, change: null, status: "sin_datos"};
    const lastDate = values.at(-1).date;
    const recentStart = new Date(lastDate);
    recentStart.setDate(recentStart.getDate() - 13);
    const baselineStart = new Date(recentStart);
    baselineStart.setDate(baselineStart.getDate() - 42);
    const recent = average(values.filter(item => item.date >= recentStart).map(item => item.value));
    const baseline = average(
      values
        .filter(item => item.date >= baselineStart && item.date < recentStart)
        .map(item => item.value),
    );
    const current = values.at(-1).value;
    if (recent === null || baseline === null || baseline === 0) {
      return {current, change: null, status: "sin_datos"};
    }
    const change = -((recent - baseline) / Math.abs(baseline)) * 100;
    const status = change > 1.5 ? "mejorando" : change < -1.5 ? "empeorando" : "estable";
    return {current, change, status};
  }

  function renderRecovery(performance) {
    const target = document.querySelector("#recovery-components");
    if (!target) return;
    const components = performance.recovery?.components || {};
    const cards = Object.entries(componentLabels).map(([key, label]) => {
      const item = components[key] || {};
      const change = item.change_pct;
      const delta = change === null || change === undefined
        ? "Sin baseline suficiente"
        : `${change > 0 ? "+" : ""}${change}% vs baseline`;
      return `
        <div class="release-component ${safe(item.status || "sin_datos")}">
          <span>${safe(label)}</span>
          <strong>${valueText(item.current)}</strong>
          <small>${safe(delta)}</small>
        </div>
      `;
    });
    target.innerHTML = cards.join("");
  }

  function latestWith(rows, field) {
    return [...rows].reverse().find(row => row[field] !== null && row[field] !== undefined);
  }

  function renderExtraMetrics(rawPerformance, training) {
    const target = document.querySelector("#release-extra-metrics");
    if (!target) return;
    const age = fitnessAgeTrend(rawPerformance);
    const hill = latestWith(training, "hill_score")?.hill_score;
    const recovery = latestWith(training, "recovery_time_hours")?.recovery_time_hours;
    const ageTrend = age.change === null
      ? "sin tendencia"
      : `${age.change > 0 ? "+" : ""}${age.change.toFixed(1)}%`;
    target.innerHTML = `
      <div><span>Fitness Age</span><strong>${valueText(age.current, " años")}</strong></div>
      <div><span>Tendencia Fitness Age</span><strong class="${safe(age.status)}">${safe(ageTrend)}</strong></div>
      <div><span>Hill Score</span><strong>${valueText(hill)}</strong></div>
      <div><span>Recovery Time</span><strong>${valueText(recovery, " h")}</strong></div>
    `;
  }

  async function loadReleaseMetrics() {
    ensureReleasePanel();
    try {
      const [performance, rawPerformance, training] = await Promise.all([
        fetchJson("/api/performance?days=180"),
        fetchJson("/api/performance/raw?days=365"),
        fetchJson("/api/training?days=30"),
      ]);
      renderRecovery(performance);
      renderExtraMetrics(rawPerformance, training);
    } catch (_error) {
      // El dashboard principal sigue siendo utilizable aunque una métrica opcional falle.
    }
  }

  const originalShowActivity = window.showActivity;
  if (typeof originalShowActivity === "function") {
    window.showActivity = async id => {
      await originalShowActivity(id);
      try {
        const detail = await fetchJson(`/api/activities/${encodeURIComponent(id)}`);
        const metrics = document.querySelector("#activity-detail .session-metrics");
        if (!metrics || metrics.querySelector("[data-v2-training-effect]")) return;
        const aerobic = document.createElement("div");
        aerobic.dataset.v2TrainingEffect = "aerobic_te";
        aerobic.innerHTML = `<span>Aerobic TE</span><strong>${valueText(detail.aerobic_te)}</strong>`;
        const anaerobic = document.createElement("div");
        anaerobic.dataset.v2TrainingEffect = "anaerobic_te";
        anaerobic.innerHTML = `<span>Anaerobic TE</span><strong>${valueText(detail.anaerobic_te)}</strong>`;
        metrics.append(aerobic, anaerobic);
      } catch (_error) {
        // Training Effect es opcional y no debe impedir abrir el detalle.
      }
    };
  }

  ensureReleasePanel();
  loadReleaseMetrics();
  setInterval(loadReleaseMetrics, 60000);
})();
