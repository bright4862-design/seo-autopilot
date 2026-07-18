# Page evidence gate v1 candidate

This candidate prevents fetch failures, redirects, non-HTML responses and incomplete HTML from being interpreted as missing page elements.

- HTML-dependent findings require `page_evidence_class: usable_html`.
- A failed seed request emits one non-scoring `site_access_limited` finding with `needs_verification`.
- Fewer than four usable HTML pages produces `health_score: null`.
- Existing evidence-state labels remain unchanged when the numeric score is unavailable.
- The FixList UI renders an unavailable score state and does not claim checks passed when usable evidence is insufficient.
- Candidate fingerprint: `4a560c34a3d68c6b`.

Validation passed for frontend checks, scanner regressions, the scanner API suite and revision consistency.

Deployment order: Cloud Run first, verify `/health` and `/revision`, then publish Base44 and rerun Funbooker plus a successful control.
