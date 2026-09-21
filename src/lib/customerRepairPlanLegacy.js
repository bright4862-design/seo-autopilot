const ACTION_ORDER = Object.freeze({
  fix_first: 0,
  important: 1,
  improve: 2,
  review: 3,
});

function clean(value) {
  return String(value ?? "").trim();
}

function actionBand(card = {}) {
  const value = clean(card.actionPriority || card.action_priority).toLowerCase();
  return Object.prototype.hasOwnProperty.call(ACTION_ORDER, value) ? value : "";
}

/**
 * Build the customer work plan from backend-owned action bands only.
 *
 * The server owns the band. The browser is allowed to put those bands in the
 * fixed customer order, but it must preserve the persisted order inside each
 * band and must never promote a repair from technical severity or page count.
 */
export function buildCustomerRepairPlan(cards = [], { fallbackNextBestStep = "" } = {}) {
  const source = Array.isArray(cards) ? cards.filter(Boolean) : [];
  const indexed = source.map((card, index) => ({ card, index, band: actionBand(card) }));
  indexed.sort((left, right) => {
    const leftRank = left.band ? ACTION_ORDER[left.band] : Number.MAX_SAFE_INTEGER;
    const rightRank = right.band ? ACTION_ORDER[right.band] : Number.MAX_SAFE_INTEGER;
    return leftRank - rightRank || left.index - right.index;
  });

  const ordered = indexed.map(({ card }) => card);
  const fixFirstCount = indexed.filter(({ band }) => band === "fix_first").length;
  const first = ordered[0] || {};
  const nextBestStep = clean(first.whatToChange || first.what_to_change || first.title)
    || clean(fallbackNextBestStep);

  return {
    cards: ordered,
    fixFirstCount,
    nextBestStep,
  };
}
