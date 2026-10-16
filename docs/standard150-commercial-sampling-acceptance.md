# Standard 150 commercial page selection: offline evidence

**Status: CANDIDATE — production acceptance NOT met.**

This is an offline verification record dated 2026-10-16. It is not a production
acceptance report or release authorization. The canonical candidate record keeps
`acceptance_report: ""`, `git_commit: ""`, and `status: "candidate"` until the
required live evidence exists.

| Identity | Value |
| --- | --- |
| Baseline commit | `2bdfe700bbc1cd1b515cc713da314a097bee2fb1` |
| Candidate fingerprint | `e0eca935c350e590` |
| Historical baseline fingerprint | `01ebe8e90df1e6bd` |
| Sampling version | `balanced_sitemap_buckets_v7_commercial_hubs_before_repeated_leaves` |
| Page cap | 150, unchanged |
| Scope | Sitemap discovery order, commercial page selection, observed market preference |

The user chose to retain Standard 150 and improve which pages receive the scan
budget, with category and city pages as the Funbooker example. These rules infer
commercial importance from URL structure. They do not measure revenue, prove a
page's conversion value, or guarantee that any website will finish 150 pages.

## Behavior and evidence

| Requirement or risk | Offline evidence | Result |
| --- | --- | --- |
| Reach category, city/location, service, and pricing pages early | `test_sampling_commercial_selection.py`: early-prefix, hub allocation, service/pricing and misleading-token cases | Pass |
| Keep representative commercial leaf pages and diagnostic/trust pages | Hub-reserve tests preserve activity pages; trust and utility cases preserve diagnostic evidence | Pass |
| Avoid spending the useful sample on translated or query copies | Fresh-route, locale-repeat, query-multiplicity and preferred-market cases | Pass |
| Retain exact request URLs | Query, path case, trailing slash, gzip and child-URL identity fixtures | Pass |
| Avoid broadening or narrowing scope from a preference | Invalid-market, exact-boundary, cross-origin and unsuccessful-landing cases | Pass |
| Reach different sitemap structures before repeated language/number siblings | `test_sitemap_business_structure_order.py`: bounded-fetch discovery, separate listing/listing.other/search structures and unchanged inventory buckets | Pass |
| Preserve small-site selection and selected-versus-checked semantics | Under-budget exact-order fixture and independent 150-selected/12-checked fixture | Pass |
| Align generated candidate identity across runtimes | Exact diff audit, all changed build IDs independently recomputed, generator and fingerprint checks | Pass |
| Complete the intended live 150-page crawl | No candidate live crawl was run | Pending |
| Preserve production authority, historical reads, and customer results after release | Local regression coverage exists; no deployed candidate acceptance was run | Pending |

The selection changes do not change the template classifier's authority semantics,
request-URL identity, robots policy, origin/SSRF protections, crawl caps, timeout
constants, concurrency, or deployment resources. A separate timeout investigation
is still required before claiming improved completion counts under production
deadlines.

## Reproduced synthetic comparisons

Both versions were executed against the same inputs with `select_balanced_urls`,
the scanner's path-based `classify_template` callback, and a budget of 150. The
baseline implementation was read directly from the baseline Git commit. The
candidate implementation was imported from the working tree. No network requests
or customer scans were made.

| Synthetic inventory, in input order | Historical baseline | Candidate |
| --- | --- | --- |
| 1,000 `/fr/annonce/activity-N/voir`, then 50 `/fr/category/theme-N`, then 50 `/fr/ville/city-N` | 134 activities, 8 categories, 8 cities | 73 activities, 39 categories, 38 cities |
| First 15 selected from that marketplace inventory | 15 activities | 3 activities, 6 categories, 6 cities |
| 1,000 `/blog/article-N`, then 25 `/services/service-N`, then `/pricing`, `/contact`, `/privacy`, `/terms` | 141 blogs, 6 services, 0 pricing, 3 trust | 121 blogs, 25 services, 1 pricing, 3 trust |
| First 15 selected from that service inventory | 9 blogs, 3 services, 3 trust | 3 blogs, 8 services, 1 pricing, 3 trust |

The old selector is input-order-sensitive: putting the category inventory first
instead produced 28 categories, 8 cities and 114 activities. The candidate still
produced 39 categories, 38 cities and 73 activities. These are synthetic examples,
not measurements of the current Funbooker sitemap or evidence of revenue gains.

## Local validation

The local environment used the bundled Node 24.19.0 runtime and Python 3.12 virtual
environment, with their binaries explicitly placed on `PATH`. The host shell is
macOS Bash 3.2.57. The repository CI uses Ubuntu, Node 20, and Python 3.12.

| Command | Observed result |
| --- | --- |
| `cd scanner-api && python -m pytest -q tests/` | Coordinator's fresh log: **2,474 passed, 18 skipped**, 3,299 BeautifulSoup deprecation warnings, 39.86 seconds. Source hashes below match the reviewed state. This suite was not redundantly rerun by the verifier. |
| `python -m pytest -q tests/` from repository root | **420 passed**, 16 BeautifulSoup deprecation warnings, 1.72 seconds |
| `node --test tests/frontend/*.test.mjs` | Initial final-candidate run: **1,890 passed, 18 failed**, 1,908 total, 47.94 seconds. Three were candidate-record defects, corrected as described below; 15 were reproduced on unchanged baseline under macOS Bash 3.2. |
| `node --test tests/frontend/*.test.mjs` after candidate-record and historical-read compatibility corrections | **1,913 passed, 15 failed**, 1,928 total, 34.41 seconds. All 15 failures are the same independently reproduced macOS Bash 3 cases; the Linux run of those cases passed. |
| `node --test tests/frontend/betaAcceptanceRecord.test.mjs tests/frontend/releaseContractCanonical.test.mjs` after correction | **15 passed, 0 failed** |
| `node --test tests/frontend/customerHistoricalReleaseReadExecutable.test.mjs` after the historical-read fix | Independent rerun: **22 passed, 0 failed**; the implementing reviewer also ran seven related test files together, **150 passed, 0 failed** |
| `node node_modules/eslint/bin/eslint.js . --quiet` | Exit 0 |
| `node node_modules/typescript/bin/tsc -p ./jsconfig.json` | Exit 0 |
| `node node_modules/vite/bin/vite.js build` | Exit 0, 20.84 seconds; existing warning for a minified chunk larger than 500 kB |
| `node scripts/generate_release_contracts.mjs --check` | Exit 0 after candidate-record correction |
| `cd scanner-api && python scripts/freeze_beta_revision.py --check` | Exit 0; local source fingerprint `e0eca935c350e590`, deployed commit unset |
| `python scanner-api/tests/test_stage1_blueprint_corpus.py --output /private/tmp/intelligent-standard150-stage1-corpus.json` then `node scripts/assertCorpusRun.mjs /private/tmp/intelligent-standard150-stage1-corpus.json` | Exit 0; **14 synthetic cases, 55 assertions**; genuine 30-site gate explicitly not assessed |
| `python -m pytest -q dispatch-gateway/test_gateway.py` | Collection blocked by missing Flask in the local virtual environment. CI installs `dispatch-gateway/requirements.txt`; no gateway pass is claimed. |
| `git diff --check` | Exit 0 |
| Linux Node 20 container, network disabled, read-only source mount: `node --test tests/frontend/base44V3RuntimeRecovery.test.mjs tests/frontend/base44V3RuntimeRecoverySept14.test.mjs tests/frontend/staticEgressProbeSafety.test.mjs` | **27 passed, 0 failed**, 6.49 seconds; the same three test files that produced 15 host-shell failures |
| `DOCKER_BUILDKIT=0 docker --config <isolated-empty-config> build --pull=false --tag fixlist-scanner:intelligent-standard150-offline .` | Exit 0; production Dockerfile built Linux amd64 image `sha256:9be085593ac1b03c65bf4d692c626707ac9a8373c41ff0712eab046004f9508d` |
| `docker run --rm --network none fixlist-scanner:intelligent-standard150-offline python -c ...` importing `app.main` and hashing the three changed scanner modules | Exit 0; sampling version and all three source SHA-256 values match the table below |

An initial attempt to invoke `npm run test:frontend` exited 127 because npm is not
on the configured local path. The full frontend suite above was then invoked
directly through Node using the exact package script's command. Lint, typecheck
and build likewise used the package script binaries directly.

The first Docker BuildKit attempt stalled in Docker's credential helper while
resolving public base-image metadata. A second legacy-builder attempt also stalled
in the credential helper. Both specific build processes were explicitly stopped
and observed terminal before another attempt. The successful build used a
temporary empty Docker configuration and the cached public Python 3.12 base image,
leaving the user's Docker configuration unchanged. Dependencies were installed
inside the build container. Docker warned that the amd64 image was being built on
an arm64 host; this is build evidence, not a production resource or timing test.

The three candidate-record failures were meaningful: `acceptance_report` had been
set to this offline document despite the candidate contract requiring an empty
field, and `docs/beta-acceptance.md` still named the previous candidate. The
coordinator restored the empty acceptance field and updated the current candidate
description while retaining the historical record. The two existing contract test
files then passed all 15 tests. No tests were weakened.

The 15 host-shell failures are confined to
`base44V3RuntimeRecovery.test.mjs` (6),
`base44V3RuntimeRecoverySept14.test.mjs` (2), and
`staticEgressProbeSafety.test.mjs` (7). A clean archive of baseline commit
`2bdfe700bbc1cd1b515cc713da314a097bee2fb1`, tested with the same local runtime,
reproduced exactly those 15 failures (27 targeted tests: 12 passed, 15 failed).
Errors include the shell's associative-array handling and process-substitution
parsing. This baseline comparison establishes that these failures predate this
candidate. The targeted Linux container run then passed all 27 tests. A complete
exact-final-commit CI run remains required.

## Historical report transition found and corrected during review

Before correction, the V8 reader's
`isReadableAuthorityReleaseFingerprint("01ebe8e90df1e6bd", "e0eca935c350e590")`
returned `false`. Its explicit historical allowlist did not contain the prior
current fingerprint. The reader uses this gate for result access at
`base44/functions/getCustomerScanResultV8/entry.ts`, including full results and
preview candidates. An explicitly allowlisted historical fingerprint such as
`9e4901da590017e1` still returns `true`.

That would have rejected saved reports using the prior current fingerprint after
the candidate was published. The independent reviewer added exactly
`01ebe8e90df1e6bd` to the canonical and V2–V8 reader registries (eight identical
files), with no change to reader versions or proof and ownership guards. No
arbitrary or wildcard release acceptance was introduced.

The new regression executes the real canonical and active V8 handlers against
sealed prior-current rows. Before the fix, its 22 cases produced 6 passes and 16
failures. Afterward, the independent rerun passed all 22 cases: the saved original
fingerprint and repair remain intact, `release_contract_current` is false, and
unknown releases, foreign owners, missing/wrong signing keys, changed signed
scores, mismatched row identities, missing fix rows and changed saved instructions
are rejected. Seven related test files together passed 150 cases. All 41 changed
package build IDs were independently recomputed again after the eight reader
build IDs were regenerated; all matched.

This establishes the bounded local compatibility behavior. The prior fingerprint
comes from the baseline revision manifest, not an independent claim about live
stored reports. Fresh live historical-report acceptance remains pending. The
earlier passing suites alone had missed this release-transition case.

## Generated identity audit

All 42 changed Base44 `entry.ts` files differ only in the
`BASE44_HANDLER_RELEASE_FINGERPRINT` marker. All 45 changed
`generatedReleaseContract.js` files differ only in fingerprint and sampling
version. All 41 changed `generatedBuildId.js` package hashes were recomputed from
the sorted package files, excluding the build-ID file, and matched exactly. The
canonical manifest retains candidate status and empty deployed-commit and
acceptance-report fields; only the sampling component version changed. The eight
explicit historical reader registries additionally carry the bounded compatibility
fix described above.

This propagation is required to keep scanner and Base44 identities consistent.
It does not mean those functions have been published. The candidate requires a
coordinated release and verification of the active scanner, Base44 routes and
customer-facing bundle.

| Reviewed source | SHA-256 |
| --- | --- |
| `scanner-api/app/sampling.py` | `0fa8b1c747aa8c6c30a0dd4e5b58b002baa0fdef95f5d9a0d0c23b59c04e0e3c` |
| `scanner-api/app/sitemap.py` | `47ac98752dab87b401e71fa8817de112c5057da89a73c7ea053ce3a9b6750ddb` |
| `scanner-api/app/scanner.py` | `88053b3330197efc4e8a4528fb72795a1993ddaf2ad0c322edd36686f690c86e` |

## Remaining acceptance

- Run exact-final-commit CI on the supported Ubuntu environment, including the
  gateway dependencies and production image build, and complete independent review.
- Verify the intended scanner, Base44 runtime/build identities and served frontend
  after the coordinated release; local source is not proof of a deployed repair.
- Run fresh authorized candidate acceptance scans, including Funbooker and other
  materially different site structures. Record discovered, selected, checked,
  retained and failed pages separately, along with queue order, elapsed time,
  deadline reasons, resource usage and result authority.
- Verify saved historical reports and new full/limited reports at the customer
  boundary. Confirm that page selection improvements preserve truthful scores and
  evidence, and do not conceal incomplete coverage.
- Keep the 150-page cap. The proposed timeout alignment and any future 500-page
  plan require their own review and evidence.

No deployment, traffic change, cloud mutation or candidate production scan was
performed as part of this offline verification.
