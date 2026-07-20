# Evidence quality gate v1

## Scope

The release gate now distinguishes mechanical crawl completion from representative business evidence.

- Clear default-route dominance on a very small crawl becomes provisional.
- Zero usable HTML evidence becomes provisional.
- Meaningful one-page sites remain supported.
- Small brochure sites without default-route dominance remain complete.
- Existing access-limited and incomplete results keep their original status and limitation.

## Production acceptance

1. Lamanna Bakery becomes non-authoritative with `discovery_quality_state: default_route_dominated`.
2. Hartzler Dairy remains complete and authoritative.
3. Funbooker remains complete and authoritative at the 150-page cap.
