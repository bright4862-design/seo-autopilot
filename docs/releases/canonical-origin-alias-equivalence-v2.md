# Canonical origin-alias equivalence v2

## Scope

Canonical validation now uses the same apex/`www` host equivalence as redirect validation when the scheme and port are unchanged.

## Safety boundaries

- Genuine external domains still produce `canonical_cross_domain` verification tasks.
- HTTP-to-HTTPS changes are not treated as transport aliases by this rule.
- Redirected, failed, noindexed, robots-blocked, chained, looped, and malformed canonical targets keep their existing findings.
- Alias provenance remains attached to page evidence through `canonical_origin_alias_*` fields.

## Production acceptance

1. Hartzler Dairy must no longer emit `canonical_cross_domain` solely for apex-to-`www` canonical declarations.
2. Funbooker must remain complete and authoritative.
