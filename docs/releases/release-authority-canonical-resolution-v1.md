# Release authority and canonical resolution v1

## Scope

- Compact browser recovery imports the same release-authority contract used by durable ScanRun persistence.
- A scheme-relative, single-label canonical is repaired as a local path only when reconstructing it exactly matches the page's final path.
- Genuine scheme-relative external domains remain cross-domain verification findings.

## Candidate

- Canonical href resolution: `canonical_href_resolution_v1_hostless_same_path`
- Fingerprint: `6fe5526e10adf27d`

## Production acceptance

1. Hartzler `/chocolate-milk` has no `canonical_cross_domain` finding.
2. An authoritative control reports `release_gate_eligible: true` in compact browser diagnostics.
3. Lamanna remains provisional and reports `release_gate_eligible: false` for evidence-quality reasons.
