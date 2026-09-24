const Api = (() => {
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
    getConfig: () => request("/api/config"),
    updateConfig: (payload) =>
      request("/api/config", { method: "PUT", body: JSON.stringify(payload) }),

    getBatteryStatus: () => request("/api/battery/status"),
    setManualSoc: (percent) =>
      request("/api/battery/manual", { method: "POST", body: JSON.stringify({ percent }) }),
    getPlan: (pricePerKwh, targetPercent) =>
      request(
        `/api/battery/plan?price_per_kwh=${encodeURIComponent(pricePerKwh)}&target_percent=${encodeURIComponent(targetPercent)}`
      ),

    createSession: (payload) =>
      request("/api/sessions", { method: "POST", body: JSON.stringify(payload) }),
    listSessions: () => request("/api/sessions"),
    getSession: (id) => request(`/api/sessions/${id}`),
    addReading: (id, kwh) =>
      request(`/api/sessions/${id}/readings`, { method: "POST", body: JSON.stringify({ kwh }) }),
    finishSession: (id, finalPercent) =>
      request(`/api/sessions/${id}/finish`, {
        method: "POST",
        body: JSON.stringify(finalPercent != null ? { final_percent: finalPercent } : {}),
      }),
  };
})();
