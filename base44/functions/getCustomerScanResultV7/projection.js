import * as legacy from "./projectionStage1Legacy.js";
import {
  STAGE3_AUTHORITY_VERSION,
  STAGE3_V7_DELIVERY_VERSION,
  authoritySnapshotFromRowsStage3,
  buildCustomerProjectionStage3,
} from "./stage3V7Delivery.js";
import { PUBLISHED_REVIEW_ATTESTATION_VERSION } from "./publishedRepairEvidence.js";

export * from "./projectionStage1Legacy.js";

const INTERNAL_STAGE3_BASE = "__fixlist_stage3_v7_legacy_base";

function withoutInternalMarker(value = {}) {
  const { [INTERNAL_STAGE3_BASE]: _marker, ...rest } = value || {};
  return rest;
}

function hasPersistedStage3Delivery(run) {
  return Boolean(
    run?.authority_seal_version === PUBLISHED_REVIEW_ATTESTATION_VERSION
    && run?.health_score_explanation?.stage3_delivery?.version === STAGE3_V7_DELIVERY_VERSION
  );
}

function asTransientStage3Run(run = {}) {
  return { ...run, authority_seal_version: STAGE3_AUTHORITY_VERSION };
}

export function authoritySnapshotFromRows(args = {}) {
  if (args?.[INTERNAL_STAGE3_BASE] === true) {
    const clean = withoutInternalMarker(args);
    const run = clean?.run?.authority_seal_version === STAGE3_AUTHORITY_VERSION
      ? { ...clean.run, authority_seal_version: PUBLISHED_REVIEW_ATTESTATION_VERSION }
      : clean.run;
    return legacy.authoritySnapshotFromRows({ ...clean, run });
  }
  if (!hasPersistedStage3Delivery(args?.run)) {
    return legacy.authoritySnapshotFromRows(args);
  }
  const staged = authoritySnapshotFromRowsStage3({
    ...args,
    [INTERNAL_STAGE3_BASE]: true,
    run: asTransientStage3Run(args.run),
  });
  if (staged?.version !== STAGE3_AUTHORITY_VERSION) {
    throw new Error("Persisted Stage3 customer authority did not reconstruct the expected contract");
  }
  return { ...staged, version: PUBLISHED_REVIEW_ATTESTATION_VERSION };
}

export function buildCustomerProjection(args = {}) {
  if (args?.[INTERNAL_STAGE3_BASE] === true) {
    const clean = withoutInternalMarker(args);
    const run = clean?.run?.authority_seal_version === STAGE3_AUTHORITY_VERSION
      ? { ...clean.run, authority_seal_version: PUBLISHED_REVIEW_ATTESTATION_VERSION }
      : clean.run;
    return legacy.buildCustomerProjection({ ...clean, run });
  }
  if (!hasPersistedStage3Delivery(args?.run)) {
    return legacy.buildCustomerProjection(args);
  }
  return buildCustomerProjectionStage3({
    ...args,
    [INTERNAL_STAGE3_BASE]: true,
    run: asTransientStage3Run(args.run),
  });
}
