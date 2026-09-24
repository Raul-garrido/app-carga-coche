/**
 * JS port of backend/app/calculator.py, used when there is no backend to
 * call (see api.js: createLocalApi). Keep the two in sync — same formulas,
 * same field names (camelCase here vs snake_case there).
 */
const Calculator = (() => {
  function kwhFromPercent(capacityKwh, percent) {
    return (capacityKwh * percent) / 100;
  }

  function percentFromKwh(capacityKwh, kwh) {
    if (capacityKwh <= 0) throw new Error("capacity_kwh must be positive");
    const percent = (kwh / capacityKwh) * 100;
    return Math.max(0, Math.min(100, percent));
  }

  function chargePlan(capacityKwh, initialPercent, targetPercent, pricePerKwh) {
    if (capacityKwh <= 0) throw new Error("capacity_kwh must be positive");
    const chargedKwh = kwhFromPercent(capacityKwh, initialPercent);
    const targetKwh = kwhFromPercent(capacityKwh, targetPercent);
    const remainingKwh = Math.max(targetKwh - chargedKwh, 0);
    const estimatedCost = remainingKwh * pricePerKwh;
    return {
      capacityKwh,
      initialPercent,
      targetPercent,
      chargedKwh,
      targetKwh,
      remainingKwh,
      estimatedCost,
    };
  }

  function sessionCost(accumulatedKwh, pricePerKwh) {
    return accumulatedKwh * pricePerKwh;
  }

  function sessionSummary(capacityKwh, initialPercent, accumulatedKwh, pricePerKwh) {
    const estimatedFinalPercent = percentFromKwh(
      capacityKwh,
      kwhFromPercent(capacityKwh, initialPercent) + accumulatedKwh
    );
    return {
      accumulatedKwh,
      accumulatedCost: sessionCost(accumulatedKwh, pricePerKwh),
      estimatedFinalPercent,
    };
  }

  return { kwhFromPercent, percentFromKwh, chargePlan, sessionCost, sessionSummary };
})();

if (typeof module !== "undefined") {
  module.exports = Calculator;
}
