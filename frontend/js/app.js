const state = {
  config: null,
  battery: null, // { percent, source, updated_at } | null
  activeSessionId: loadActiveSessionId(),
};

function loadActiveSessionId() {
  const raw = localStorage.getItem("activeSessionId");
  return raw ? Number(raw) : null;
}

function saveActiveSessionId(id) {
  if (id == null) {
    localStorage.removeItem("activeSessionId");
  } else {
    localStorage.setItem("activeSessionId", String(id));
  }
}

function fmtKwh(value) {
  return `${Number(value).toFixed(2)} kWh`;
}

function roundMoney(value) {
  // Avoid binary floating-point cases like 5.5 * 0.15 = 0.8250000000000001
  // (or 0.8249999999999999) displaying as 0,82 instead of 0,83.
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function fmtEuro(value) {
  return `${roundMoney(Number(value)).toFixed(2).replace(".", ",")} €`;
}

function fmtPercent(value) {
  return `${Number(value).toFixed(1)} %`;
}

function showError(message) {
  const banner = document.getElementById("error-banner");
  banner.textContent = message;
  banner.classList.remove("hidden");
  setTimeout(() => banner.classList.add("hidden"), 6000);
}

async function refreshBatteryStatus() {
  try {
    state.battery = await Api.getBatteryStatus();
  } catch (err) {
    state.battery = null;
  }
  renderBattery();
}

function renderBattery() {
  const capacity = state.config ? state.config.battery_capacity_kwh : 14.4;
  const percentEl = document.getElementById("battery-percent");
  const sourceEl = document.getElementById("battery-source");
  const chargedEl = document.getElementById("battery-charged-kwh");
  const remainingEl = document.getElementById("battery-remaining-kwh");
  const targetInput = document.getElementById("target-input");
  const chargingStatusEl = document.getElementById("charging-status");
  const socLabelEl = document.getElementById("soc-input-label");

  if (!state.battery) {
    percentEl.textContent = "—";
    sourceEl.textContent = "sin datos";
    chargedEl.textContent = "—";
    remainingEl.textContent = "—";
    chargingStatusEl.classList.add("hidden");
    return;
  }

  const target = Number(targetInput.value) || 100;
  percentEl.textContent = fmtPercent(state.battery.percent);
  const isAuto = state.battery.source === "myaudi";
  sourceEl.textContent = isAuto ? "MyAudi auto" : "manual";
  const charged = (capacity * state.battery.percent) / 100;
  const remaining = Math.max((capacity * target) / 100 - charged, 0);
  chargedEl.textContent = fmtKwh(charged);
  remainingEl.textContent = fmtKwh(remaining);

  socLabelEl.textContent = isAuto ? "Corregir % a mano (si Audi falla)" : "% actual (MyAudi)";

  if (state.battery.charging) {
    const minutes = state.battery.remaining_minutes;
    const timeText =
      minutes != null
        ? ` — según Audi, quedan ${minutes >= 60 ? `${Math.floor(minutes / 60)} h ${minutes % 60} min` : `${minutes} min`}`
        : "";
    chargingStatusEl.textContent = `Cargando ahora${timeText}`;
    chargingStatusEl.classList.remove("hidden");
  } else {
    chargingStatusEl.classList.add("hidden");
  }

  document.getElementById("soc-input").value = state.battery.percent;
}

async function loadConfig() {
  state.config = await Api.getConfig();
  if (state.config.default_price_per_kwh != null) {
    document.getElementById("price-input").value = state.config.default_price_per_kwh;
  }
  document.getElementById("target-input").value = state.config.default_target_percent;
}

async function handleSocSubmit(event) {
  event.preventDefault();
  const percent = Number(document.getElementById("soc-input").value);
  try {
    state.battery = await Api.setManualSoc(percent);
    renderBattery();
  } catch (err) {
    showError(`No se pudo actualizar el %: ${err.message}`);
  }
}

async function handlePlanSubmit(event) {
  event.preventDefault();
  const price = Number(document.getElementById("price-input").value);
  const target = Number(document.getElementById("target-input").value);
  try {
    const plan = await Api.getPlan(price, target);
    document.getElementById("plan-remaining").textContent = fmtKwh(plan.remaining_kwh);
    document.getElementById("plan-cost").textContent = fmtEuro(plan.estimated_cost);
    renderBattery();
  } catch (err) {
    showError(`No se pudo calcular: ${err.message}`);
  }

  // Best-effort: this is also the price/objetivo an auto-opened session
  // (MyAudi backend mode) will use, so keep it saved as the default.
  try {
    state.config = await Api.updateConfig({
      default_price_per_kwh: price,
      default_target_percent: target,
    });
  } catch (err) {
    /* not fatal — the plan above already showed, this just persists it */
  }
}

async function handleStartSession() {
  if (!state.battery) {
    showError("Introduce primero el % actual de MyAudi.");
    return;
  }
  const price = Number(document.getElementById("price-input").value);
  const target = Number(document.getElementById("target-input").value);
  if (!price) {
    showError("Introduce el precio por kWh antes de iniciar la sesión.");
    return;
  }
  try {
    const session = await Api.createSession({
      initial_percent: state.battery.percent,
      target_percent: target,
      price_per_kwh: price,
    });
    state.activeSessionId = session.id;
    saveActiveSessionId(session.id);
    renderSession(session);
  } catch (err) {
    showError(`No se pudo iniciar la sesión: ${err.message}`);
  }
}

async function handleAddReading(event) {
  event.preventDefault();
  if (!state.activeSessionId) return;
  const kwh = Number(document.getElementById("reading-input").value);
  try {
    const session = await Api.addReading(state.activeSessionId, kwh);
    renderSession(session);
    document.getElementById("reading-input").value = "";
  } catch (err) {
    showError(`No se pudo añadir la lectura: ${err.message}`);
  }
}

async function handleFinishSession(event) {
  event.preventDefault();
  if (!state.activeSessionId) return;
  const raw = document.getElementById("final-percent-input").value;
  const finalPercent = raw === "" ? null : Number(raw);
  try {
    await Api.finishSession(state.activeSessionId, finalPercent);
    state.activeSessionId = null;
    saveActiveSessionId(null);
    document.getElementById("final-percent-input").value = "";
    showIdleSession();
    await loadHistory();
  } catch (err) {
    showError(`No se pudo finalizar la sesión: ${err.message}`);
  }
}

function renderSession(session) {
  document.getElementById("session-idle").classList.add("hidden");
  document.getElementById("session-active").classList.remove("hidden");

  document.getElementById("session-kwh").textContent = session.accumulated_kwh.toFixed(2);
  document.getElementById("session-cost").textContent = fmtEuro(session.accumulated_cost);
  document.getElementById("session-final-percent").textContent = fmtPercent(
    session.estimated_final_percent
  );

  const list = document.getElementById("readings-list");
  list.innerHTML = "";
  session.readings.forEach((reading) => {
    const li = document.createElement("li");
    const time = new Date(reading.timestamp).toLocaleTimeString();
    li.textContent = `${time} — ${reading.kwh.toFixed(2)} kWh (${reading.source})`;
    list.appendChild(li);
  });
}

function showIdleSession() {
  document.getElementById("session-idle").classList.remove("hidden");
  document.getElementById("session-active").classList.add("hidden");
}

let editingSessionId = null;

async function loadHistory() {
  const sessions = await Api.listSessions();
  const finished = sessions.filter((s) => s.status === "finished");
  const body = document.getElementById("history-body");
  body.innerHTML = "";

  if (finished.length === 0) {
    body.innerHTML = '<tr><td colspan="5" class="hint">Sin sesiones todavía.</td></tr>';
    return;
  }

  finished.forEach((session) => {
    const tr = document.createElement("tr");
    const date = new Date(session.started_at).toLocaleDateString();
    const finalPercent = session.final_percent ?? session.estimated_final_percent;

    if (editingSessionId === session.id) {
      tr.innerHTML = `
        <td>${date}</td>
        <td>
          <input type="number" class="edit-final-percent" min="0" max="100" step="1" value="${finalPercent.toFixed(0)}" />
        </td>
        <td><input type="number" class="edit-kwh" min="0" step="0.01" value="${session.accumulated_kwh.toFixed(2)}" /></td>
        <td><input type="number" class="edit-price" min="0" step="0.0001" value="${session.price_per_kwh}" /></td>
        <td class="row-actions">
          <button type="button" data-action="save" data-id="${session.id}">Guardar</button>
          <button type="button" class="ghost" data-action="cancel">Cancelar</button>
        </td>
      `;
    } else {
      tr.innerHTML = `
        <td>${date}</td>
        <td>${session.initial_percent.toFixed(0)}% → ${finalPercent.toFixed(0)}%</td>
        <td>${session.accumulated_kwh.toFixed(2)} kWh</td>
        <td>${fmtEuro(session.accumulated_cost)}</td>
        <td class="row-actions">
          <button type="button" class="ghost" data-action="edit" data-id="${session.id}">Editar</button>
          <button type="button" class="ghost danger-text" data-action="delete" data-id="${session.id}">Borrar</button>
        </td>
      `;
    }
    body.appendChild(tr);
  });
}

async function handleHistoryClick(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const { action, id } = button.dataset;

  if (action === "edit") {
    editingSessionId = Number(id);
    await loadHistory();
    return;
  }

  if (action === "cancel") {
    editingSessionId = null;
    await loadHistory();
    return;
  }

  if (action === "delete") {
    if (!confirm("¿Borrar esta sesión del historial? No se puede deshacer.")) return;
    try {
      await Api.deleteSession(Number(id));
      await loadHistory();
    } catch (err) {
      showError(`No se pudo borrar: ${err.message}`);
    }
    return;
  }

  if (action === "save") {
    const row = button.closest("tr");
    const finalPercent = Number(row.querySelector(".edit-final-percent").value);
    const totalKwh = Number(row.querySelector(".edit-kwh").value);
    const pricePerKwh = Number(row.querySelector(".edit-price").value);
    try {
      await Api.updateSession(Number(id), {
        final_percent: finalPercent,
        total_kwh: totalKwh,
        price_per_kwh: pricePerKwh,
      });
      editingSessionId = null;
      await loadHistory();
    } catch (err) {
      showError(`No se pudo guardar: ${err.message}`);
    }
  }
}

async function restoreActiveSession() {
  // Prefer asking "is there an active session at all" — catches one opened
  // automatically by the backend's MyAudi poller, not just one this
  // browser itself started (which is all the old localStorage id could see).
  try {
    const active = await Api.getActiveSession();
    if (active) {
      state.activeSessionId = active.id;
      saveActiveSessionId(active.id);
      renderSession(active);
      return;
    }
  } catch (err) {
    /* endpoint not available on this Api implementation — fall through */
  }

  if (!state.activeSessionId) return;
  try {
    const session = await Api.getSession(state.activeSessionId);
    if (session.status === "active") {
      renderSession(session);
    } else {
      state.activeSessionId = null;
      saveActiveSessionId(null);
    }
  } catch (err) {
    state.activeSessionId = null;
    saveActiveSessionId(null);
  }
}

async function init() {
  Api = await detectApi();

  document.getElementById("soc-form").addEventListener("submit", handleSocSubmit);
  document.getElementById("plan-form").addEventListener("submit", handlePlanSubmit);
  document.getElementById("start-session-btn").addEventListener("click", handleStartSession);
  document.getElementById("reading-form").addEventListener("submit", handleAddReading);
  document.getElementById("finish-form").addEventListener("submit", handleFinishSession);
  document.getElementById("target-input").addEventListener("input", renderBattery);
  document.getElementById("history-body").addEventListener("click", handleHistoryClick);

  await loadConfig();
  await refreshBatteryStatus();
  await restoreActiveSession();
  await loadHistory();

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("service-worker.js").catch(() => {
      /* PWA install just won't be offline-capable; not fatal */
    });
  }

  // Only while idle: pick up a session the backend's MyAudi poller might
  // have opened on its own, without the user having to reload the page.
  // Skipped once a session is showing, so it doesn't stomp on an in-progress
  // reading the user is typing.
  setInterval(async () => {
    if (state.activeSessionId) return;
    await refreshBatteryStatus();
    await restoreActiveSession();
  }, 20000);
}

init();
