# Page evidence gate v1 candidate

This candidate prevents fetch failures, redirects, non-HTML responses and incomplete HTML from being interpreted as missing page elements.

- HTML-dependent findings require `page_evidence_class: usable_html`.
- A failed seed request emits one non-scoring `site_access_limited` finding with `needs_verification`.
- Fewer than four usable HTML pages produces `health_score: null`.
- Candidate fingerprint: `4a560c34a3d68c6b`.

Deployment order: Cloud Run first, verify `/health` and `/revision`, then publish Base44 and rerun Funbooker plus a successful control.
