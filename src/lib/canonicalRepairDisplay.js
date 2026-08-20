import { REPAIR_PRESENTATION_MODES, repairPresentationMode } from "./repairContractPresentation.js";
import { repairRowModel } from "./repairPresentation.js";

const CANONICAL_SURFACE_LABELS = Object.freeze({
  "Shared Navigation": "Shared navigation",
  "Xml Sitemap": "XML sitemap",
  "Cms Field": "CMS field",
  "Redirect Server Config": "Redirect/server config",
  "Redirect Server Configuration": "Redirect/server config",
  "Individual Page Content": "Page content",
});

const CANONICAL_EVIDENCE_LABELS = Object.freeze({
  confirmed_problem: "Confirmed problem",
  improvement: "Improvement",
  opportunity: "Review opportunity",
});

function canonicalSurfaceLabel(surface = "") {
  const value = String(surface || "").trim();
  return CANONICAL_SURFACE_LABELS[value] || value;
}

function canonicalEvidenceClassOf(item = {}) {
  return String(
    item.evidenceClass
      || item.evidence_class
      || item.repairEvidenceClass
      || item.repair_evidence_class
      || "",
  ).trim().toLowerCase();
}

function canonicalEvidenceLabel(item = {}) {
  return CANONICAL_EVIDENCE_LABELS[canonicalEvidenceClassOf(item)] || "";
}

function qualifyCanonicalScope(scope = "", affectedPageCount = 0) {
  const value = String(scope || "").trim();
  if (!/^\d+ pages?$/.test(value)) return value;

  const count = Math.max(0, Number(affectedPageCount) || 0);
  if (count === 1) return "1 affected page found in this scan";
  if (count > 1) return `${count} affected pages found in this scan`;
  return value;
}

/**
 * Keep canonical evidence presentation tied to the persisted repair authority.
 *
 * Browser normalization may make harmless customer-copy changes such as a
 * friendlier title, but it must not rewrite the evidence-backed surface, scope,
 * priority reason, evidence class, leverage, or verification state of a
 * canonical repair. Legacy rows retain their existing presentation behavior.
 */
export function canonicalRepairDisplayModel(item = {}, suppliedModel = null) {
  const model = suppliedModel || repairRowModel(item);
  const original = item?.original;

  if (repairPresentationMode(item) !== REPAIR_PRESENTATION_MODES.CANONICAL) {
    return model;
  }

  if (!original || typeof original !== "object") {
    const evidenceClass = canonicalEvidenceClassOf(item);
    return {
      ...model,
      surface: canonicalSurfaceLabel(model.surface),
      scope: qualifyCanonicalScope(model.scope, model.affectedPageCount),
      evidenceClass,
      evidenceLabel: canonicalEvidenceLabel(item),
    };
  }

  const persisted = repairRowModel(original);
  const evidenceClass = canonicalEvidenceClassOf(original);
  return {
    ...model,
    surface: canonicalSurfaceLabel(persisted.surface),
    scope: qualifyCanonicalScope(persisted.scope, persisted.affectedPageCount),
    reason: persisted.reason,
    evidenceClass,
    evidenceLabel: canonicalEvidenceLabel(original),
    leverage: persisted.leverage,
    verification: persisted.verification,
    verificationKind: persisted.verificationKind,
    affectedPageCount: persisted.affectedPageCount,
    sharedRepairConfirmed: persisted.sharedRepairConfirmed,
  };
}
