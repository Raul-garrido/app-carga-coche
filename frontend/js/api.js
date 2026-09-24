/**
 * `Api` is picked at startup by detectApi() (see app.js:init()):
 *  - if backend/ (FastAPI) is reachable at the same origin, use it —
 *    state lives in its SQLite file, ready for a future automatic
 *    MyAudi source.
 *  - otherwise (e.g. the app is served as a static PWA from GitHub
 *    Pages, with no backend at all), fall back to a localStorage-backed
 *    implementation with the exact same method shapes, using the JS
 *    calculator port in calculator.js.
 * Every other file in the app only ever calls `Api.*` and never knows
 * which one is active.
 */
var Api = null;

function createNetworkApi() {
  async function request(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail || detail;
      } catch (_) {
        /* no JSON body */
      }
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    if (res.status === 204) return null;
    return res.json();
  }

  return {
    getConfig: () => request("api/config"),
    updateConfig: (payload) =>
      request("api/config", { method: "PUT", body: JSON.stringify(payload) }),

    getBatteryStatus: () => request("api/battery/status"),
    setManualSoc: (percent) =>
      request("api/battery/manual", { method: "POST", body: JSON.stringify({ percent }) }),
    getPlan: (pricePerKwh, targetPercent) =>
      request(
        `api/battery/plan?price_per_kwh=${encodeURIComponent(pricePerKwh)}&target_percent=${encodeURIComponent(targetPercent)}`
      ),

    createSession: (payload) =>
      request("api/sessions", { method: "POST", body: JSON.stringify(payload) }),
    listSessions: () => request("api/sessions"),
    getActiveSession: () => request("api/sessions/active"),
    getSession: (id) => request(`api/sessions/${id}`),
    addReading: (id, kwh) =>
      request(`api/sessions/${id}/readings`, { method: "POST", body: JSON.stringify({ kwh }) }),
    finishSession: (id, finalPercent) =>
      request(`api/sessions/${id}/finish`, {
        method: "POST",
        body: JSON.stringify(finalPercent != null ? { final_percent: finalPercent } : {}),
      }),
    updateSession: (id, payload) =>
      request(`api/sessions/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
    deleteSession: (id) => request(`api/sessions/${id}`, { method: "DELETE" }),
  };
}

function createLocalApi() {
  const CONFIG_KEY = "cargaCoche.config.v1";
  const BATTERY_KEY = "cargaCoche.battery.v1";
  const SESSIONS_KEY = "cargaCoche.sessions.v1";
  const DEFAULT_CONFIG = {
    battery_capacity_kwh: 14.4,
    default_target_percent: 100,
    default_price_per_kwh: null,
  };

  function readJSON(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (_) {
      return fallback;
    }
  }

  function writeJSON(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function httpError(message, status) {
    const err = new Error(message);
    err.status = status;
    return err;
  }

  function getConfigRaw() {
    return { ...DEFAULT_CONFIG, ...readJSON(CONFIG_KEY, {}) };
  }

  function getSessions() {
    return readJSON(SESSIONS_KEY, []);
  }

  function saveSessions(sessions) {
    writeJSON(SESSIONS_KEY, sessions);
  }

  function nextId(items) {
    return items.reduce((max, item) => Math.max(max, item.id), 0) + 1;
  }

  function toSessionOut(session) {
    const lastReading = session.readings[session.readings.length - 1];
    const accumulatedKwh = lastReading ? lastReading.kwh : 0;
    const summary = Calculator.sessionSummary(
      session.battery_capacity_kwh,
      session.initial_percent,
      accumulatedKwh,
      session.price_per_kwh
    );
    const plan = Calculator.chargePlan(
      session.battery_capacity_kwh,
      session.initial_percent,
      session.target_percent,
      session.price_per_kwh
    );
    return {
      ...session,
      accumulated_kwh: summary.accumulatedKwh,
      accumulated_cost: summary.accumulatedCost,
      estimated_final_percent: summary.estimatedFinalPercent,
      target_kwh: plan.targetKwh,
      remaining_kwh_to_target: plan.remainingKwh,
      estimated_cost_to_target: plan.estimatedCost,
    };
  }

  function findSession(sessions, id) {
    const session = sessions.find((s) => s.id === id);
    if (!session) throw httpError("Session not found", 404);
    return session;
  }

  return {
    async getConfig() {
      return { ...getConfigRaw(), myaudi_auto_enabled: false };
    },

    async updateConfig(payload) {
      const cfg = { ...getConfigRaw(), ...payload };
      writeJSON(CONFIG_KEY, cfg);
      return { ...cfg, myaudi_auto_enabled: false };
    },

    async getBatteryStatus() {
      const state = readJSON(BATTERY_KEY, null);
      if (!state) throw httpError("No manual SoC set yet.", 404);
      return state;
    },

    async setManualSoc(percent) {
      const state = { percent, source: "manual", updated_at: nowIso() };
      writeJSON(BATTERY_KEY, state);
      return state;
    },

    async getPlan(pricePerKwh, targetPercent) {
      const battery = await this.getBatteryStatus();
      const cfg = getConfigRaw();
      const plan = Calculator.chargePlan(
        cfg.battery_capacity_kwh,
        battery.percent,
        targetPercent,
        pricePerKwh
      );
      return {
        capacity_kwh: plan.capacityKwh,
        initial_percent: plan.initialPercent,
        target_percent: plan.targetPercent,
        charged_kwh: plan.chargedKwh,
        target_kwh: plan.targetKwh,
        remaining_kwh: plan.remainingKwh,
        estimated_cost: plan.estimatedCost,
      };
    },

    async createSession(payload) {
      const cfg = getConfigRaw();
      const sessions = getSessions();
      const session = {
        id: nextId(sessions),
        status: "active",
        started_at: nowIso(),
        ended_at: null,
        battery_capacity_kwh: payload.battery_capacity_kwh || cfg.battery_capacity_kwh,
        initial_percent: payload.initial_percent,
        target_percent: payload.target_percent,
        final_percent: null,
        price_per_kwh: payload.price_per_kwh,
        readings: [],
      };
      sessions.push(session);
      saveSessions(sessions);
      return toSessionOut(session);
    },

    async listSessions() {
      return getSessions()
        .slice()
        .reverse()
        .map(toSessionOut);
    },

    async getSession(id) {
      return toSessionOut(findSession(getSessions(), id));
    },

    async getActiveSession() {
      const active = getSessions().find((s) => s.status === "active");
      return active ? toSessionOut(active) : null;
    },

    async addReading(id, kwh) {
      const sessions = getSessions();
      const session = findSession(sessions, id);
      if (session.status !== "active") throw httpError("Session already finished", 409);
      session.readings.push({
        id: nextId(session.readings),
        kwh,
        source: "manual",
        timestamp: nowIso(),
      });
      saveSessions(sessions);
      return toSessionOut(session);
    },

    async finishSession(id, finalPercent) {
      const sessions = getSessions();
      const session = findSession(sessions, id);
      if (session.status !== "active") throw httpError("Session already finished", 409);
      const current = toSessionOut(session);
      session.status = "finished";
      session.ended_at = nowIso();
      session.final_percent = finalPercent != null ? finalPercent : current.estimated_final_percent;
      saveSessions(sessions);
      return toSessionOut(session);
    },

    async updateSession(id, payload) {
      const sessions = getSessions();
      const session = findSession(sessions, id);
      if (payload.initial_percent != null) session.initial_percent = payload.initial_percent;
      if (payload.target_percent != null) session.target_percent = payload.target_percent;
      if (payload.price_per_kwh != null) session.price_per_kwh = payload.price_per_kwh;
      if (payload.final_percent != null) session.final_percent = payload.final_percent;
      if (payload.total_kwh != null) {
        session.readings = [
          { id: 1, kwh: payload.total_kwh, source: "manual", timestamp: nowIso() },
        ];
      }
      saveSessions(sessions);
      return toSessionOut(session);
    },

    async deleteSession(id) {
      const sessions = getSessions();
      findSession(sessions, id); // throws 404 if missing
      saveSessions(sessions.filter((s) => s.id !== id));
    },
  };
}

async function detectApi() {
  try {
    const res = await fetch("api/config", { method: "GET", cache: "no-store" });
    if (res.ok) return createNetworkApi();
  } catch (_) {
    /* no backend at this origin — fall back to local storage below */
  }
  return createLocalApi();
}
