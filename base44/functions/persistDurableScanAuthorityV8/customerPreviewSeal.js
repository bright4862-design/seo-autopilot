import * as legacy from "./customerPreviewSealStage1Legacy.js";
import {
  STAGE3_AUTHORITY_VERSION,
  STAGE3_V7_DELIVERY_VERSION,
  stage3PreviewFixIds,
} from "./stage3V7Delivery.js";
import { PUBLISHED_REVIEW_ATTESTATION_VERSION } from "./publishedRepairEvidence.js";

export * from "./customerPreviewSealStage1Legacy.js";

function hasPersistedStage3Delivery(run) {
  return Boolean(
    run?.authority_seal_version === PUBLISHED_REVIEW_ATTESTATION_VERSION
    && run?.health_score_explanation?.stage3_delivery?.version === STAGE3_V7_DELIVERY_VERSION
  );
}

function stage3PreviewItems(run, fixItems) {
  const ids = stage3PreviewFixIds({ ...run, authority_seal_version: STAGE3_AUTHORITY_VERSION });
  if (!Array.isArray(ids) || ids.length > legacy.CUSTOMER_PREVIEW_VISIBLE_FIX_COUNT) {
    throw new Error("Persisted Stage3 preview selection is invalid");
  }
  const rows = Array.isArray(fixItems) ? fixItems : [];
  const byId = new Map();
  for (const row of rows) {
    const id = typeof row?.fix_id === "string" ? row.fix_id.trim() : "";
    if (!id || byId.has(id)) throw new Error("Persisted Stage3 preview rows are ambiguous");
    byId.set(id, row);
  }
  const selected = ids.map((id) => byId.get(id));
  if (selected.some((row) => !row)) {
    throw new Error("Persisted Stage3 preview selection references a missing fix");
  }
  return selected;
}

/**
 * Stage-3 preview selection is produced by Python and authenticated inside the
 * full V7 authority HMAC. Historical rows keep the legacy canonical-rank
 * selection exactly; Stage-3 rows use only the signed two-finding source.
 */
export function buildCustomerPreviewPayload(args = {}) {
  if (!hasPersistedStage3Delivery(args?.run)) {
    return legacy.buildCustomerPreviewPayload(args);
  }
  const selected = stage3PreviewItems(args.run, args.fixItems);
  const payload = legacy.buildCustomerPreviewPayload({
    ...args,
    fixItems: selected,
  });
  if (!selected.length) return payload;
  const order = new Map(selected.map((item, index) => [String(item?.fix_id || "").trim(), index]));
  payload.fixItems = [...payload.fixItems].sort(
    (left, right) => (order.get(String(left?.fix_id || "").trim()) ?? Number.MAX_SAFE_INTEGER)
      - (order.get(String(right?.fix_id || "").trim()) ?? Number.MAX_SAFE_INTEGER),
  );
  return payload;
}
