/** A read-only, non-secret summary of the runtime values consumed by V9. */
const VALID_MODES = new Set(["monolith", "staged"]);
const OWNER_PATTERN = /^[A-Za-z0-9_-]{6,64}$/;
const MAX_COHORT = 5;

function observe(reader, name) {
  try {
    const value = reader(name);
    return typeof value === "string" ? { known: true, value } : { known: false, value: "" };
  } catch {
    return { known: false, value: "" };
  }
}

function modeOf(observed) {
  if (!observed.known) return "unavailable";
  const mode = observed.value.trim().toLowerCase();
  return mode === "" ? "absent" : VALID_MODES.has(mode) ? mode : "invalid";
}

function cohortOf(observed, expectedOwnerId) {
  if (!observed.known) return { valid: false, state: "unavailable", ownerCount: null, ownerMatch: false, members: [] };
  const raw = observed.value.trim();
  if (!raw) return { valid: true, state: "empty", ownerCount: 0, ownerMatch: false, members: [] };
  const members = raw.split(",").map(item => item.trim());
  const valid = members.length <= MAX_COHORT
    && members.every(item => OWNER_PATTERN.test(item))
    && new Set(members).size === members.length;
  return {
    valid,
    state: valid ? "explicit" : "invalid",
    ownerCount: valid ? members.length : null,
    ownerMatch: valid && members.includes(expectedOwnerId),
    members: valid ? members : [],
  };
}

function gateOf(observed) {
  if (!observed.known) return "unavailable";
  if (observed.value === "true") return "enabled";
  if (observed.value === "false") return "disabled";
  return observed.value === "" ? "absent" : "invalid";
}

/**
 * Only owner membership for the authenticated fixed owner is returned.
 * Never emit raw owner IDs or the secret values. This independent probe
 * cannot prove the deployed startStandardScanJobV9 build or its live instance.
 */
export function summarizeStagedRuntime({ readEnv, readSecret, expectedOwnerId }) {
  if (!OWNER_PATTERN.test(expectedOwnerId)) throw new Error("expected_owner_invalid");
  const envMode = modeOf(observe(readEnv, "SCAN_PIPELINE_MODE"));
  const secretMode = modeOf(observe(readSecret, "SCAN_PIPELINE_MODE"));
  const envOwners = cohortOf(observe(readEnv, "SCAN_STAGED_OWNER_IDS"), expectedOwnerId);
  const secretOwners = cohortOf(observe(readSecret, "SCAN_STAGED_OWNER_IDS"), expectedOwnerId);
  const legacyAlias = cohortOf(observe(readEnv, "SCAN_PIPELINE_OWNER_IDS"), expectedOwnerId);
  const intakeGate = gateOf(observe(readSecret, "BETA_SCAN_INTAKE_ENABLED"));
  const admissionGate = gateOf(observe(readSecret, "BETA_SCAN_ADMISSION_ENABLED"));
  const validModes = VALID_MODES.has(envMode) && VALID_MODES.has(secretMode);
  const cohortsAgree = envOwners.valid && secretOwners.valid
    && envOwners.members.length === secretOwners.members.length
    && envOwners.members.every((member, i) => member === secretOwners.members[i]);
  const legacyAliasClear = legacyAlias.state === "empty" || legacyAlias.state === "unavailable";
  const configConverged = validModes && envMode === secretMode && cohortsAgree && legacyAliasClear;
  const stagedOwnerEnabled = configConverged && envMode === "staged" && envOwners.ownerMatch;
  const intakeDisabledVerified = intakeGate === "disabled";
  return {
    schema_version: "fixlist_staged_runtime_readback_v1",
    config_converged: configConverged,
    env_mode: envMode,
    secret_mode: secretMode,
    env_cohort_state: envOwners.state,
    secret_cohort_state: secretOwners.state,
    cohort_count: configConverged ? envOwners.ownerCount : null,
    owner_match: stagedOwnerEnabled,
    staged_owner_enabled: stagedOwnerEnabled,
    legacy_alias_state: legacyAlias.state,
    intake_gate: intakeGate,
    admission_gate: admissionGate,
    intake_disabled_verified: intakeDisabledVerified,
    new_owner_intake_disabled: intakeDisabledVerified && !stagedOwnerEnabled,
    v9_runtime_attested: false,
  };
}
