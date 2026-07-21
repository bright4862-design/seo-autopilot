# Hartzler absolute single-label canonical resolution v2

## Exact live evidence

- Requested URL: `https://hartzlerdairy.com/chocolate-milk`
- Redirect: `301` to `https://www.hartzlerdairy.com/chocolate-milk/`
- Final URL: `https://www.hartzlerdairy.com/chocolate-milk/`
- Raw canonical tag: `<link rel="canonical" href="http://chocolate-milk" />`
- Raw href: `http://chocolate-milk`

## Scope

- Repairs an absolute `http(s)://<single-label>` canonical only when the single label reconstructs the exact final page path.
- Retains the earlier scheme-relative same-path repair.
- Dotted external domains and single-label values that reconstruct a different path remain cross-domain verification findings.

## Candidate

- Canonical href resolution: `canonical_href_resolution_v2_absolute_single_label_same_path`
- Fingerprint: `d69d625dbeaee154`

## Production acceptance

1. Hartzler `/chocolate-milk` has no `canonical_cross_domain` finding.
2. Hartzler remains complete and authoritative.
3. Funbooker remains an authoritative control.
4. Lamanna remains provisional for default-route discovery quality.
