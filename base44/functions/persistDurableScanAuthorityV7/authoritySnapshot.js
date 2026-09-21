import * as legacy from "./authoritySnapshotStage1Legacy.js";
import {
  STAGE3_AUTHORITY_VERSION,
  STAGE3_V7_DELIVERY_VERSION,
  buildAuthoritySnapshotStage3,
  buildPersistedAuthoritySnapshotStage3,
} from "./stage3V7Delivery.js";
import { PUBLISHED_REVIEW_ATTESTATION_VERSION } from "./publishedRepairEvidence.js";

export * from "./authoritySnapshotStage1Legacy.js";

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

function claimsDurableStage3Delivery(review) {
  if (!review || typeof review !== "object" || Array.isArray(review)) return false;
  // The identity-bound B22/B24 sources are the upgrade boundary. B19/B21
  // factors/counts and the identity-agnostic delivery/score decision can be
  // computed in historical/basic review fixtures without a trusted scan id;
  // those fields alone must not silently upgrade the signed authority version.
  // Once either exact-scan source is present, strict Stage-3 validation owns the
  // whole contract, so a partial/malformed new delivery still fails closed.
  return review.stage3_private_preview_source !== undefined
    || review.stage3_handoff_v2_source !== undefined;
}

/**
 * Keep the published-route V7 HMAC version stable while extending its signed
 * payload with the versioned Stage-3 delivery capsule. The nested capsule is
 * itself inside the HMAC bytes, so injecting it into a historical row changes
 * reconstruction and fails verification instead of upgrading that row.
 */
export function buildAuthoritySnapshot(options = {}) {
  if (options?.[INTERNAL_STAGE3_BASE] === true) {
    return legacy.buildAuthoritySnapshot(withoutInternalMarker(options));
  }
  if (!claimsDurableStage3Delivery(options?.review)) {
    return legacy.buildAuthoritySnapshot(options);
  }
  const staged = buildAuthoritySnapshotStage3({
    ...options,
    [INTERNAL_STAGE3_BASE]: true,
  });
  return staged?.version === STAGE3_AUTHORITY_VERSION
    ? { ...staged, version: PUBLISHED_REVIEW_ATTESTATION_VERSION }
    : staged;
}

export function buildPersistedAuthoritySnapshot(args = {}) {
  if (args?.[INTERNAL_STAGE3_BASE] === true) {
    return legacy.buildPersistedAuthoritySnapshot(withoutInternalMarker(args));
  }
  const run = args?.run;
  if (!hasPersistedStage3Delivery(run)) {
    return legacy.buildPersistedAuthoritySnapshot(args);
  }
  const staged = buildPersistedAuthoritySnapshotStage3({
    ...args,
    [INTERNAL_STAGE3_BASE]: true,
    run: { ...run, authority_seal_version: STAGE3_AUTHORITY_VERSION },
  });
  if (staged?.version !== STAGE3_AUTHORITY_VERSION) {
    throw new Error("Persisted Stage3 delivery did not reconstruct the expected authenticated contract");
  }
  return { ...staged, version: PUBLISHED_REVIEW_ATTESTATION_VERSION };
}
