# Stage-one evidence release candidate

Status: implementation candidate; independent review complete and its four Important findings corrected. The final local source gate passed; exact-source CI and production acceptance remain pending. User-authorized milestone: merge, deploy and publish after complete stage-one acceptance. The full B01–B28 goal continues after this milestone.

Candidate fingerprint: `01ebe8e90df1e6bd`. The canonical record remains `candidate`, with no accepted commit or production acceptance report. No stage-one production deployment has occurred.

## Requirement evidence

| Scope | Implemented behavior | Direct verification |
| --- | --- | --- |
| B01/B02 | Case, trailing slash, reserved escapes, meaningful query order, literal Unicode and foreign origins retain observed identity. Only verified redirects share destination content. | Shared Python/JS identity fixtures; real extraction/local review → writer → sealed rows → customer and chat readers → rendered card/modal, actual CSV/copy/JSON and PDF annotations. Three independent routes and eleven literal spellings retain counts; redirect aliases retain one final content page. |
| B03 | Missing attributes differ from empty alt; explicit semantic evidence supports material repairs. Uncertain purpose produces a separate non-scoring review. | Per-image fixtures, material/uncertain/excluded counts, mixed pages and mixed images on one page; signed observation tampering and preview no-leak. |
| B04 | General visible placeholders, runtime values and conservative unfinished shells retain bounded placement/excerpts. Hidden/code examples are excluded. | Detector positives/negatives, wrong-location compatibility, one repair per content cause/family, authenticated excerpts through customer output. |
| B05 | Intentional noindex and validated canonical-away suppress independent search metadata; explicit search intent produces an index-or-drop decision. | Scanner/postprocess/review integration; stable repeated canonical annotation; query-bearing canonical target validation; relevant heading/accessibility evidence retained. |
| B25, stage-one portion | Named synthetic corpus runs actual extraction, canonical validation and review; mocked HTTP exercises redirects and SiteGround. | 14 explicitly synthetic cases, 55 observed-output predicates; validator rejects missing cases, false provenance and failing observations. |
| B27 | Original historical GEO signatures and preview boundaries remain unchanged. | Frozen literal historical fixture; writer/customer/chat parity; new seal rejects unknown versions and tampered counts/metadata; preview remains bounded to two findings. |
| B28 | Existing V6 release mechanism and security/crawl limits retained. | Package closure/generated contracts pass. Exact-source CI, controlled production cutover, six V6 functions/site/worker verification and live acceptance remain required. |

Named hosts: pretto.fr, centerstreetlending.com, www.ikessandwich.com, locations.ikessandwich.com, getfixlist.com and ironwoodcrecapital.com. The fixtures are newly authored synthetic inputs; they do not claim current live findings. Ironwood challenge HTML cannot create content defects or an authoritative GEO score. No bypass, extra probe pool or new crawl limits are introduced.

## Verification before independent review

Linux/Bash 5, Node 20.19.5 and Python 3.12:

- Scanner suite: 1,767 passed, 18 intentional skips; existing dependency deprecation warnings remain.
- Frontend suite: 1,479 passed, no failures/skips.
- Root Python regression gate, lint, typecheck, production build, package closure, generated contracts, frozen component check and release-manifest determinism passed.
- First integration runs exposed query/slash canonical equivalence, redirect content attribution, missing template grouping and uncertainty copy; each received a reproducing regression before correction.

## Decisions and limits

- New observed evidence uses absolute keys resolved from trusted scan origin. Historical report reconstruction uses its original rules.
- Content repairs use a verified redirect destination only when successful parsed redirect evidence matches it. Standard-family coverage remains unknown if no comparable denominator exists.
- Heading evidence remains visitor-facing; the search-metadata exclusion applies to titles, descriptions, canonical optimization and their duplicates.
- Image uncertainty stays separate from confirmed repairs. Materiality relies on retained raw-HTML semantics, not image count, dimensions, filename or main placement alone.
- Raw HTML cannot establish external stylesheet/computed visibility. The detector conservatively excludes explicit hidden/code content and does not claim browser-rendered assessment.
- B06–B24, later scoring/ranking/local-entity work and the genuine paired 30-site full-blueprint gate remain open. Synthetic corpus success cannot satisfy those gates.

## Release status

The source-sharing checkpoint was `a51fa796cf6c41ccb17cb7a658ce74e8626c67a5`. The prior staged worker for `7a744a5` is stale for this candidate and must not be promoted for it. Production source, Base44 synchronization/app credentials, exact runtime identities and admission state must be revalidated at release time. Do not disconnect the repository, rotate secrets, broadly push schemas or publish a stale snapshot.

## Independent review corrections

The [fresh-context whole-branch review](stage-one-independent-review.md) reproduced four Important defects. Current producers now preserve observed origins, semicolon parameters, empty queries and exact quality-summary URLs. Redirect content attribution uses a shared matched successful-HTML proof. Real apex-to-www and query-specific soft-404 scans retain exact targets through signed persistence, customer/chat readers and actual exports.

Material image repairs and uncertain-image reviews have different semantic dedup identities, including unequal overlapping groups and group/singleton suppression. Grouped noindex conflicts retain declared-only, sitemap-only and mixed intent provenance, without invented redirects or sitemap claims. Each correction has a reproducing RED regression followed by focused GREEN checks. The final full gate passed: 1,798 scanner tests passed with 18 intentional skips; 1,479 frontend tests passed; root Python tests, lint, typecheck, production build, package closure, generated contracts, frozen revision and manifest determinism passed. The release script reported `SOURCE READY` and `DEPLOYMENT ENVIRONMENT BLOCKED` (missing local cloud tooling/credentials). Existing hosted release access is required; this is not an accepted production release.
