import * as legacy from "./authoritySnapshotStage1Legacy.js";
import {
  STAGE3_AUTHORITY_VERSION,
  authoritySnapshotFromRowsStage3,
} from "./stage3V7Delivery.js";
import { PUBLISHED_REVIEW_ATTESTATION_VERSION } from "./publishedRepairEvidence.js";

export * from "./authoritySnapshotStage1Legacy.js";

const INTERNAL_STAGE3_BASE = "__fixlist_stage3_v7_legacy_base";
const STAGE3_V7_DELIVERY_VERSION = "stage3_v7_delivery_v1";

function withoutInternalMarker(value = {}) {
  const { [INTERNAL_STAGE3_BASE]: _marker, ...rest } = value || {};
  return rest;
}

function hasPersistedStage3Delivery(scan) {
  return Boolean(
    scan?.authority_seal_version === PUBLISHED_REVIEW_ATTESTATION_VERSION
    && scan?.health_score_explanation?.stage3_delivery?.version === STAGE3_V7_DELIVERY_VERSION
  );
}

export function authoritySnapshotFromRows(args = {}) {
  if (args?.[INTERNAL_STAGE3_BASE] === true) {
    const clean = withoutInternalMarker(args);
    const scan = clean?.scan?.authority_seal_version === STAGE3_AUTHORITY_VERSION
      ? { ...clean.scan, authority_seal_version: PUBLISHED_REVIEW_ATTESTATION_VERSION }
      : clean.scan;
    return legacy.authoritySnapshotFromRows({ ...clean, scan });
  }
  if (!hasPersistedStage3Delivery(args?.scan)) {
    return legacy.authoritySnapshotFromRows(args);
  }
  const staged = authoritySnapshotFromRowsStage3({
    ...args,
    [INTERNAL_STAGE3_BASE]: true,
    scan: { ...args.scan, authority_seal_version: STAGE3_AUTHORITY_VERSION },
  });
  if (staged?.version !== STAGE3_AUTHORITY_VERSION) {
    throw new Error("Persisted Stage3 Grok authority did not reconstruct the expected contract");
  }
  return { ...staged, version: PUBLISHED_REVIEW_ATTESTATION_VERSION };
}
