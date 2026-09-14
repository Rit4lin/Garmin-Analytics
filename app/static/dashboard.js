let days = 30;
let selectedType = "";

const fmt = (value, suffix = "") =>
  value === null || value === undefined ? "—" : `${value}${suffix}`;
const esc = value => String(value ?? "—")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");
const plot = (id, traces, layout = {}) => Plotly.newPlot(
  id,
  traces,
  {
    paper_bgcolor: "#18201d",
    plot_bgcolor: "#18201d",
    font: {color: "#edf3ef"},
    margin: {l: 46, r: 20, t: 12, b: 38},
    legend: {orientation: "h"},
    xaxis: {gridcolor: "#2b3832"},
    yaxis: {gridcolor: "#2b3832"},
    ...layout,
  },
  {responsive: true, displayModeBar: false},
);

async function json(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw Error("No se pudo cargar");
  return response.json();
}

function card(label, value) {
  const element = document.querySelector("#card").content.cloneNode(true);
  element.querySelector("p").textContent = label;
  element.querySelector("strong").textContent = value;
  return element;
}

function trendArrow(status) {
  if (status === "mejorando") return "↑";
  if (status === "empeorando") return "↓";
  if (status === "estable") return "→";
  return "·";
}

function trendText(item) {
  if (!item || item.current === null || item.current === undefined) return "Sin datos";
  if (item.change_pct === null || item.change_pct === undefined) {
    return String(item.status || "Sin tendencia").replaceAll("_", " ");
  }
  const sign = item.change_pct > 0 ? "+" : "";
  return `${sign}${item.change_pct}% vs baseline`;
}

function trendCard(label, item, suffix = "") {
  const article = document.createElement("article");
  article.className = `trend-card ${item?.status || "sin_datos"}`;
  const current = item?.current;
  article.innerHTML = `
    <div class="trend-label">${esc(label)}</div>
    <div class="trend-value">
      <strong>${fmt(current, suffix)}</strong>
      <span>${trendArrow(item?.status)}</span>
    </div>
    <p>${esc(trendText(item))}</p>
  `;
  return article;
}

function fmtDuration(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  return hours
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
    : `${minutes}:${String(secs).padStart(2, "0")}`;
}

function fmtPace(seconds) {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "—";
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${minutes}:${String(secs).padStart(2, "0")} min/km`;
}

function renderPerformance(perf) {
  const status = perf.status || {};
  document.querySelector("#performance-headline").textContent = status.headline || "Sin datos";
  const detail = status.change_pct === null || status.change_pct === undefined
    ? `Confianza: ${status.confidence || "baja"}`
    : `${status.change_pct > 0 ? "+" : ""}${status.change_pct}% · confianza ${status.confidence}`;
  document.querySelector("#performance-detail").textContent = detail;
  const badge = document.querySelector("#performance-badge");
  badge.className = `status-pill ${status.trend || "sin_datos"}`;
  badge.textContent = (status.trend || "sin datos").replaceAll("_", " ").toUpperCase();

  const trends = document.querySelector("#trend-cards");
  trends.replaceChildren(
    trendCard("Eficiencia aeróbica", perf.fitness?.aerobic_efficiency),
    trendCard("VO₂max", perf.fitness?.vo2max),
    trendCard("Endurance", perf.fitness?.endurance),
    trendCard(
      "Recuperación",
      {
        current: perf.recovery?.score,
        change_pct: null,
        status: perf.recovery?.status,
      },
      "/100",
    ),
    trendCard("Running tolerance", perf.fitness?.running_tolerance),
    trendCard("Peso", perf.fitness?.weight, " kg"),
    trendCard(
      "Fatiga",
      {
        current: perf.load?.fatigue_index,
        change_pct: null,
        status: perf.load?.status,
      },
      "/100",
    ),
  );

  const insights = document.querySelector("#insights");
  insights.replaceChildren(...(perf.insights || []).map(text => {
    const div = document.createElement("div");
    div.className = "insight";
    div.textContent = text;
    return div;
  }));
  if (!insights.children.length) insights.textContent = "Aún no hay suficientes datos.";

  const alerts = document.querySelector("#alerts");
  alerts.replaceChildren(...(perf.alerts || []).map(item => {
    const div = document.createElement("div");
    div.className = `alert ${item.level || "info"}`;
    div.textContent = item.message;
    return div;
  }));
  if (!alerts.children.length) {
    const div = document.createElement("div");
    div.className = "alert positive";
    div.textContent = "No hay señales relevantes que requieran atención.";
    alerts.append(div);
  }

  const disciplines = document.querySelector("#disciplines");
  disciplines.replaceChildren(...(perf.disciplines || []).map(item => {
    const div = document.createElement("div");
    div.className = "discipline-row";
    const signal = item.discipline === "running" ? item.efficiency : item.training_load;
    div.innerHTML = `
      <div><strong>${esc(item.discipline)}</strong><span>${item.sessions} sesiones · ${item.hours} h</span></div>
      <div class="discipline-metrics">
        <span>${item.distance_km} km</span>
        <span>FC ${fmt(item.avg_hr)}</span>
        <span class="mini-trend ${signal?.status || ""}">
          ${trendArrow(signal?.status)} ${esc(trendText(signal))}
        </span>
      </div>
    `;
    return div;
  }));
  if (!disciplines.children.length) disciplines.textContent = "Sin actividades en el periodo.";

  const prediction = perf.predictions || {};
  const threshold = perf.threshold || {};
  const records = perf.records || [];
  const raceSummary = document.querySelector("#race-summary");
  raceSummary.innerHTML = `
    <div class="metric-list">
      <div><span>5K</span><strong>${fmtDuration(prediction["5k_seconds"])}</strong></div>
      <div><span>10K</span><strong>${fmtDuration(prediction["10k_seconds"])}</strong></div>
      <div><span>Media</span><strong>${fmtDuration(prediction.half_seconds)}</strong></div>
      <div><span>Maratón</span><strong>${fmtDuration(prediction.marathon_seconds)}</strong></div>
      <div><span>Umbral</span><strong>${fmtPace(threshold.pace_seconds_km)}</strong></div>
      <div><span>FC umbral</span><strong>${fmt(threshold.hr, " ppm")}</strong></div>
    </div>
    <h3>Récords</h3>
    <div class="records">
      ${records.slice(0, 8).map(record => `
        <span><b>${esc(record.type)}</b> ${esc(
          record.value_seconds !== undefined
            ? fmtDuration(record.value_seconds)
            : fmt(record.value, record.unit ? ` ${record.unit}` : ""),
        )}</span>
      `).join("") || "<span>Sin récords disponibles.</span>"}
    </div>
  `;
}

function renderCharts(data, perf, history) {
  plot("activity-chart", [
    {
      x: data.weekly.map(x => x.week),
      y: data.weekly.map(x => x.activities),
      type: "bar",
      name: "Actividades",
    },
    {
      x: data.weekly.map(x => x.week),
      y: data.weekly.map(x => x.distance / 1000),
      type: "scatter",
      name: "Km",
      yaxis: "y2",
    },
  ], {yaxis2: {overlaying: "y", side: "right", gridcolor: "transparent"}});

  plot("performance-chart", [
    {
      x: data.training.map(x => x.date),
      y: data.training.map(x => x.vo2max),
      name: "VO₂max",
      type: "scatter",
    },
    {
      x: data.training.map(x => x.date),
      y: data.training.map(x => x.load),
      name: "Carga",
      type: "scatter",
      yaxis: "y2",
    },
  ], {yaxis2: {overlaying: "y", side: "right", gridcolor: "transparent"}});

  plot("recovery-chart", [
    {
      x: data.sleep.map(x => x.date),
      y: data.sleep.map(x => x.hours),
      name: "Sueño (h)",
      type: "bar",
    },
    {
      x: data.hrv.map(x => x.date),
      y: data.hrv.map(x => x.value),
      name: "HRV",
      type: "scatter",
      yaxis: "y2",
    },
  ], {yaxis2: {overlaying: "y", side: "right", gridcolor: "transparent"}});

  plot("readiness-chart", [
    {
      x: data.training.map(x => x.date),
      y: data.training.map(x => x.readiness),
      name: "Readiness",
      type: "scatter",
    },
    {
      x: data.training.map(x => x.date),
      y: data.training.map(x => x.acute_load),
      name: "Carga aguda",
      type: "scatter",
      yaxis: "y2",
    },
  ], {yaxis2: {overlaying: "y", side: "right", gridcolor: "transparent"}});

  const race = history.race_predictions || [];
  plot("race-chart", [
    {x: race.map(x => x.date), y: race.map(x => x["5k"] / 60), name: "5K (min)", type: "scatter"},
    {x: race.map(x => x.date), y: race.map(x => x["10k"] / 60), name: "10K (min)", type: "scatter"},
    {x: race.map(x => x.date), y: race.map(x => x.half / 60), name: "Media (min)", type: "scatter"},
  ]);

  const lactate = history.lactate || [];
  const tolerance = history.running_tolerance || [];
  plot("threshold-chart", [
    {
      x: lactate.map(x => x.date),
      y: lactate.map(x => x.speed_mps ? 1000 / x.speed_mps : null),
      name: "Ritmo umbral (s/km)",
      type: "scatter",
    },
    {
      x: tolerance.map(x => x.date),
      y: tolerance.map(x => x.value),
      name: "Running tolerance",
      type: "scatter",
      yaxis: "y2",
    },
  ], {yaxis2: {overlaying: "y", side: "right", gridcolor: "transparent"}});
}

async function showActivity(id) {
  const detail = await json(`/api/activities/${encodeURIComponent(id)}`);
  const comparison = detail.comparison;
  document.querySelector("#activity-detail").innerHTML = `
    <div class="session-title">
      <div><strong>${esc(detail.name)}</strong><span>${esc(detail.type)}</span></div>
      <span>${new Date(detail.date).toLocaleDateString("es-ES")}</span>
    </div>
    <div class="metric-list session-metrics">
      <div><span>Ritmo</span><strong>${esc(detail.pace)}</strong></div>
      <div><span>FC media</span><strong>${fmt(detail.avg_hr, " ppm")}</strong></div>
      <div><span>Eficiencia</span><strong>${fmt(detail.efficiency)}</strong></div>
      <div><span>Deriva aeróbica</span><strong>${fmt(detail.aerobic_decoupling, "%")}</strong></div>
      <div><span>Potencia</span><strong>${fmt(detail.power, " W")}</strong></div>
      <div><span>Cadencia</span><strong>${fmt(detail.cadence)}</strong></div>
    </div>
    <div class="comparison-box">
      <h3>Comparación con sesiones similares</h3>
      ${comparison ? `
        <p class="comparison-result ${comparison.status}">
          ${trendArrow(comparison.status)} ${esc(comparison.status)} · ${comparison.samples} sesiones
        </p>
        <div class="metric-list">
          <div><span>Ritmo</span><strong>${fmt(comparison.pace_change_pct, "%")}</strong></div>
          <div><span>FC</span><strong>${fmt(comparison.hr_change_pct, "%")}</strong></div>
          <div><span>Eficiencia</span><strong>${fmt(comparison.efficiency_change_pct, "%")}</strong></div>
        </div>
      ` : "<p>No hay todavía suficientes sesiones comparables.</p>"}
    </div>
  `;
  document.querySelector("#activity-dialog").showModal();
}

async function load() {
  try {
    const perfDays = Math.max(days, 30);
    const [data, activities, perf, history, state] = await Promise.all([
      json(`/api/summary?days=${days}`),
      json(`/api/activities?days=${days}${selectedType ? `&activity_type=${encodeURIComponent(selectedType)}` : ""}`),
      json(`/api/performance?days=${perfDays}`),
      json(`/api/performance/timeseries?days=${Math.max(days, 365)}`),
      json("/api/sync/status"),
    ]);

    const labels = {
      entrenamientos: "Entrenamientos",
      horas_entrenadas: "Horas entrenadas",
      km: "Km",
      pasos: "Pasos",
      vo2max: "VO₂max",
      fc_reposo: "FC reposo",
      hrv: "HRV",
      sueno_horas: "Sueño",
      training_load: "Training Load",
      readiness: "Readiness",
      endurance_score: "Endurance",
    };
    const cards = document.querySelector("#cards");
    cards.replaceChildren();
    Object.entries(data.cards).forEach(([key, value]) => {
      const suffix = key === "horas_entrenadas" || key === "sueno_horas"
        ? " h"
        : key === "km" ? " km" : "";
      cards.append(card(labels[key] || key, fmt(value, suffix)));
    });

    document.querySelector("#sync-status").textContent = state.status === "running"
      ? `Sincronizando ${state.progress_current}/${state.progress_total}`
      : state.error_message
        ? `${state.error_message}${state.cooldown_seconds ? ` Reintento en ${state.cooldown_seconds}s.` : ""}`
        : `Última sincronización: ${state.last_sync_at || "pendiente"}`;

    renderPerformance(perf);
    renderCharts(data, perf, history);

    const body = document.querySelector("#activities");
    body.replaceChildren(...activities.items.map(activity => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${new Date(activity.date).toLocaleDateString("es-ES")}</td>
        <td>${esc(activity.name)}</td>
        <td>${esc(activity.type)}</td>
        <td>${activity.distance_km} km</td>
        <td>${esc(activity.duration)}</td>
        <td>${esc(activity.pace)}</td>
        <td>${fmt(activity.avg_hr)}</td>
        <td>${fmt(activity.efficiency)}</td>
      `;
      row.onclick = () => showActivity(activity.id).catch(() => {});
      return row;
    }));

    const select = document.querySelector("#type");
    const old = select.value;
    select.replaceChildren(
      new Option("Todos los tipos", ""),
      ...activities.types.map(type => new Option(type, type)),
    );
    select.value = old;
  } catch (error) {
    document.querySelector("#sync-status").textContent = error.message;
  }
}

document.querySelector("#ranges").onclick = event => {
  if (event.target.dataset.days) {
    days = +event.target.dataset.days;
    document.querySelectorAll("#ranges button").forEach(button => {
      button.classList.toggle("active", button === event.target);
    });
    load();
  }
};
document.querySelector("#type").onchange = event => {
  selectedType = event.target.value;
  load();
};
document.querySelector("#sync").onclick = async () => {
  await json("/api/sync", {method: "POST"});
  load();
};
document.querySelector("#dialog-close").onclick = () => {
  document.querySelector("#activity-dialog").close();
};

load();
setInterval(load, 60000);
