# Focused acceptance follow-up v8

Candidate fixes from the 5/8 production acceptance on representative evidence v8.

- Infrastructure/platform SaaS identity uses diverse product routes plus developer structure.
- Markdown is treated as non-HTML page evidence for generic page-level findings.
- Site-wide collapsed findings select their headline URL with archetype-aware business ranking while preserving one source example per affected family.
- Classifier candidate: `archetype_classifier_v8_platform_product_routes`.
- Representative-page candidate: `business_representative_page_v3_sitewide_archetype_ranking`.
- Page-level asset candidate: `page_level_asset_evidence_v3_markdown`.
- Candidate fingerprint: `430813f2b15afa8f`.

Guarded validation passed the three production-shaped regressions, all 13 root scanner regressions, all 348 scanner-api tests, frozen-revision verification, frontend lint, typecheck, contract tests, and production build. Normal CI must pass again on this direct-source commit before merge.

Focused production acceptance remains Stripe, Warby Parker, Center Street Lending, plus the five previously passing controls. The full matrix remains paused.
Independent normal-CI verification passed on the clean direct-source branch.
