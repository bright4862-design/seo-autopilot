import { repairSuggestion } from "./repairSuggestions.js";
import { repairRoleExplanation } from "./repairRoleExplanations.js";

/**
 * Additive presentation seam for role-specific explanation copy.
 *
 * Scanner-authored remediation remains authoritative because this helper does
 * not synthesize or replace it: `repairSuggestion()` is returned intact, with
 * its existing `suggestedFixSource` and suggestion-library versions. The role
 * explanation is separate presentation context authored in the deterministic
 * role library. Neither helper mutates the repair row.
 */
export const REPAIR_ROLE_PRESENTATION_VERSION = "repair_role_presentation_v1";

export function repairRolePresentation(item = {}, role = "") {
  const suggestion = repairSuggestion(item);
  const explanation = repairRoleExplanation(item, role);

  return Object.freeze({
    version: REPAIR_ROLE_PRESENTATION_VERSION,
    role: explanation.role,
    suggestion,
    explanation,
  });
}
