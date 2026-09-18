# GEO architecture research and implementation decisions

Research date: 18 September 2026. Status: initial primary-source investigation and experimental scoring core; not a validated customer rating or production release.

## Recommendation

Extend Standard 150 with an evidence adapter and a deterministic evaluator in the existing Python process. Keep SEO health, GEO readiness and actual AI visibility as separate measurements. Use the existing authenticated persistence and entitlement mechanisms for eventual delivery. No additional crawler, microservice, vector database, model judge or queue is needed for the first readiness release.

This is an engineering recommendation based on current product constraints. The sources below do not prescribe FixList's score, dimensions, numerical weights or coverage thresholds.

## What the primary sources support

| Source | Finding | Consequence for FixList |
| --- | --- | --- |
| [Google AI features](https://developers.google.com/search/docs/appearance/ai-features) | Existing search fundamentals apply; special AI files/schema are not required; eligibility does not guarantee inclusion. | Assess observable prerequisites without promising citations or penalising missing llms.txt. |
| [OpenAI crawler documentation](https://developers.openai.com/api/docs/bots) | Search and training crawler settings are independent. User-initiated visits are a separate use case. | Record provider/use-case policy separately; do not deduct for a training opt-out. |
| [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html) | Robots rules are crawler instructions, not access authorization. | Owner robots overrides cannot establish firewall access or another crawler's access. |
| [Google structured-data policies](https://developers.google.com/search/docs/appearance/structured-data/sd-policies) | Structured information must represent the page content and comply with relevance/quality requirements. | Compare supplied markup with visible facts; schema presence alone is not success. |
| [GEO paper, v3](https://arxiv.org/html/2311.09735v3) | Measures visibility in generated responses; tested interventions vary by domain. Its limitations include evolving engines and queries and no evaluation of effects on search rankings. | Treat source attribution as a contextual readiness signal. Do not convert reported experimental gains into customer forecasts or universal weights. |
| [ALCE paper](https://arxiv.org/abs/2305.14627) | Evaluates generated answers along correctness, fluency and citation quality. | Future visibility monitoring should distinguish an observed citation from whether it actually supports an answer. It is a different evaluation pipeline. |
| [W3C PROV-DM](https://www.w3.org/TR/prov-dm/) | Models entities, activities, agents and derivation relationships. | Borrow the provenance concepts for evidence lineage; a full semantic-web stack is unnecessary. |
| [OWASP prompt injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) | External website content can manipulate model behavior; retrieval does not eliminate that risk. | Keep numerical evaluation in deterministic code. Future language-generation components get no operational permissions and cannot invent findings. |

The two papers are foundational research from 2023/2024, not evidence of every provider's current ranking behavior. Provider documentation is current guidance observed during this investigation. Neither validates our proposed 0-100 composite against business outcomes.

## Architectures considered

| Approach | Strength | Cost/risk | Decision |
| --- | --- | --- | --- |
| Existing crawl, pure rule evaluator, existing seal/projection | Reuses accepted evidence and existing reliability boundaries; reproducible; no additional requests | Requires careful adapter and historical snapshot compatibility | Recommended for readiness |
| Separate asynchronous GEO analysis service | Independent scaling and retry budget for expensive analysis | Another queue/lifecycle, stale-result joins, cancellation and authority complexity | Defer until a measured workload requires isolation |
| LLM-as-judge produces one score from HTML | Fast prototype for subjective analysis | Variable scoring, weak provenance, prompt injection, latency/cost, no empirical score calibration | Reject as score authority; possible later bounded explanation helper |

The pure evaluator has a typed, bounded interface that can move to a separate process later without rewriting the crawler. The present need is a trustworthy assessment, not independent infrastructure.

## Evidence architecture

An accepted observation needs page identity, exact requested URL provenance, final URL/redirect provenance, observation time, extraction version, check ID and evidence reference. Records distinguish observed absence from extractor incapability. Do not fabricate authorship, factual accuracy or a provider fetch from a JSON-LD block, successful FixList request or robots Allow rule.

Maintain separate facts for crawl success, robots policy, observed indexing directives, external index status and actual answer inclusion. A local crawl can directly measure only some of these. Unknown Search Console status stays unknown. Ironwood's SiteGround challenge is an access limitation for the tested client; its noindex header describes the challenge response.

The adapter must use existing accepted evidence rather than initiate a second crawl. Raw/rendered sources retain their own provenance. An unavailable renderer is not proof that content is missing. Challenge pages, truncated responses and unverified metadata cannot become negative page-quality evidence.

Search-facing scope is determined before scoring. Intentional noindex utility pages, duplicated canonical variants, page families and archived material need explicit applicability rules. The supplied blueprint's blanket suppression of all accessibility findings on noindex pages is too broad: accessibility may still matter, but it should not be presented as an AI-search eligibility defect.

## Scoring and missingness

Initial weights and display thresholds are policy assumptions, labelled experimental. Four dimensions have equal weight, and eligible checks within each dimension have equal weight. Per check, divide passed and verified counts by applicable-plus-unknown pages. Average those fractions over eligible checks and then across four dimensions. Let the resulting passed and verified masses be P and V.

- Coverage = V; score on assessed evidence = round_half_up(100 * P / V).
- Display gates: accepted entry, authoritative parent, V >= 0.80 and each dimension coverage >= 0.50.
- Missing dimensions, empty scans and all-N/A data cannot pass the gates.
- An unresolved-outcome range is [100P, 100(P + 1 - V)]. It is not a statistical confidence interval and does not predict unseen pages.
- N/A requires an explicit reason; omitted observations become unknown. Duplicates and unknown rule IDs are rejected.

Example: eleven passing checks and one unknown check can produce an assessed-evidence score of 100 at 91.67% coverage, with an unresolved range of 91.67-100. Therefore a bare green 100 is not an acceptable customer presentation. UI must present score and coverage together, with no "perfect site" claim. An alternative is showing only a range for incomplete evidence; evaluate that presentation during customer-facing design.

The first 150 pages are not necessarily a random sample. The score describes assessed scope, not a statistically representative estimate of all pages. A large blog can dominate within-check page counts. Compare equal-page and template-balanced results on labelled fixtures and freeze the intended sampling semantics. The integration sensitivity check is recorded in geo-release-acceptance.md; it is synthetic, not population calibration. Do not switch weights silently between scans.

## Validation strategy

Three levels of validation are distinct:

1. Arithmetic correctness: independent numerical fixtures, missingness boundaries, order invariance, duplicate rejection, bounded inputs and deterministic output.
2. Measurement correctness: labelled raw/rendered fixtures proving each adapter derives the right state, including negative examples. Avoid universal word-count, author, FAQ, fresh-year or citation-count requirements.
3. Product usefulness: domain-stratified review of the proposed top fixes and score dimensions. Compare reviewers' judgments and investigate disagreements before selecting weights or thresholds for public use.

Use the attached report's five-site examples as hypotheses. Reproduce scanner artifacts before converting reported counts into golden assertions. Include lending, editorial, restaurant/location, utility, multilingual, JavaScript-heavy and access-limited cases. Explicitly test training opt-outs and legitimate historical material.

The original core slice tested level 1 only. Integration now adds labelled synthetic adapter fixtures, independent authority arithmetic/seal tests and presentation checks. Those fixtures support the narrow structural measurement contract, but do not establish provider inclusion, conversion gains or commercial value; those claims remain unverified.

## Integration and failure boundaries

The local V6 authority snapshot includes a whole-payload HMAC and explicit historical reconstruction versions. Customer projections use field allowlists. Consequently GEO needs a defined authenticated snapshot revision and old-reader compatibility, not an arbitrary extra frontend field. Historical scans must remain verifiable without score recomputation.

Keep a single evidence snapshot per scan and bind GEO version/results to it. Neither the browser nor a prose-generation model may become a second score writer. The existing queue, retry, cancellation and admission-release behavior remain authoritative.

The core deliberately returns authority_verified=false: a caller-supplied parent_authoritative boolean is a gating input, not a cryptographic proof. Only existing trusted persistence can establish customer authority. Do not expose this experimental module directly as a public endpoint.

An evaluator fault should result in a validated GEO evaluation-error state if the SEO result independently qualifies. Tampering, malformed score arithmetic or invalid provenance must fail integrity validation. Customer projection must respect paid/preview access for GEO evidence as well as SEO findings. Deduplicate shared repair actions instead of showing one SEO fix plus an identical GEO fix.

## Limits and next decisions

Implementation update: the fixed registry, exact aggregation, bounded accepted-HTML adapter, explicit applicability, authenticated snapshot compatibility and customer presentation are implemented and task-reviewed. The separate GEO findings do not create additional SEO FixItems. Scanner blueprint corrections and combined release gates remain in progress. Production deployment and empirical product calibration are not established by these tests.

Release gates are unchanged; this document does not attest to live activation. The first release uses equal page weight within each check over the retained bounded sample, with explicit unknowns and applicability exclusions. Template-balanced weighting was compared on a two-template synthetic sensitivity fixture; broader population calibration remains follow-on work. It must not silently replace this versioned model. Weight and threshold calibration remains a product experiment; no primary source supplies a scientifically validated universal GEO score.
