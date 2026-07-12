# Renderer-risk validation study

This study decides whether FixList should deploy a private browser renderer or keep the current transparent raw-HTML limitation.

The decision must be based on the customer segments FixList intends to serve, not one blended list of convenient websites.

## Stage 1: calibrate the detector on five sites

Before trusting incidence data, manually check at least five sites.

For each site:

1. Run the advanced scan.
2. Record `render_evidence.pages_evaluated`.
3. Record `render_evidence.client_rendering_suspected_pages`.
4. Record `render_evidence.evidence_state`.
5. Open representative pages with JavaScript disabled.
6. Record whether material page content disappears.

Use these manual verdicts:

- `content_sufficient`: primary content and page purpose remain understandable without JavaScript.
- `material_content_missing`: primary product, service, listing, article, navigation, heading, or structured page content is absent without JavaScript.
- `inconclusive`: the manual check could not establish a reliable result.
- `not_reviewed`: the site is part of the measurement set but was not manually checked.

Do not classify analytics, chat widgets, animations, cosmetic interactions, or optional personalization as material content loss.

The detector passes calibration only when:

- at least five manual reviews are conclusive;
- agreement is at least 80%;
- there are no false negatives.

A false negative is more serious than a false positive because it means FixList would fail to disclose a site whose important content was not visible in raw HTML.

## Stage 2: stratified 30-site measurement

Collect at least ten sites in each stratum:

- `smb_cms`: WordPress, Squarespace, Wix, Webflow, and similar small-business CMS sites;
- `saas_js`: SaaS, app, membership, Next.js-era, and heavily hydrated sites;
- `ecommerce_marketplace`: ecommerce, marketplace, booking, directory, and listing-heavy sites.

Report incidence separately for each stratum and overall.

Do not replace the per-stratum result with one blended percentage. A low overall rate can hide a high rate in a strategically important customer segment.

## Pre-committed decision rules

The study tool applies these rules only after detector calibration and a complete stratified sample:

- build when material rendering risk is at least 25% overall;
- build for a strategic segment when SaaS/JS or ecommerce/marketplace incidence is at least 25%;
- defer when incidence is below 10% overall and in every stratum;
- revisit with customer evidence when incidence is between 10% and 25%;
- recalibrate before measuring when the detector fails the manual agreement gate.

Do not change these thresholds after viewing the study results.

## JSONL record format

Store one JSON object per line:

```json
{"site":"example-saas","stratum":"saas_js","render_evidence":{"pages_evaluated":30,"client_rendering_suspected_pages":8,"evidence_state":"material_client_rendering_risk"},"manual_js_disabled_verdict":"material_content_missing","notes":"Product dashboard copy disappeared without JavaScript."}
```

The `render_evidence` object should be copied directly from the scan result. Do not manually recalculate or restamp the scanner evidence state.

## Run the report

From the repository root:

```bash
python scanner-api/scripts/render_risk_study.py data/renderer-risk-study.jsonl
```

JSON output:

```bash
python scanner-api/scripts/render_risk_study.py data/renderer-risk-study.jsonl --format json
```

Write a Markdown report:

```bash
python scanner-api/scripts/render_risk_study.py \
  data/renderer-risk-study.jsonl \
  --format markdown \
  --output reports/renderer-risk-study.md
```

The report includes:

- calibration agreement;
- false positives and false negatives;
- material-risk incidence by stratum;
- overall incidence;
- measurement completeness;
- the pre-committed build, defer, or revisit decision.

## Product guardrail

Even when a renderer is eventually deployed, rendered evidence remains informational in v1:

- it must not suppress raw-HTML findings;
- it must not change the health score;
- it must not overwrite raw page evidence;
- renderer failure must not fail the scan.
