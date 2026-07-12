# Renderer-study replacement policy

The renderer-risk study requires ten measurement-eligible sites in each customer segment. A site may be replaced only when it cannot contribute valid incidence evidence because the scan repeatedly fails or renderer coverage is explicitly insufficient.

## Guardrails

- Replace within the same stratum only.
- Do not replace a site because its renderer result is inconvenient or surprising.
- Select and document the replacement before viewing its renderer evidence.
- Keep successful, measurement-eligible records unchanged.
- Preserve the original failure or exclusion evidence in the prior workflow artifact.
- A record marked `insufficient_raw_html_evidence` remains auditable but does not count toward calibration, incidence, or measurement completeness.
- The final report still requires at least ten eligible sites in every stratum and thirty eligible sites overall.

## July 12, 2026 replacements

| Removed site | Stratum | Eligibility reason | Preselected replacement |
|---|---|---|---|
| Figma | SaaS/JS | Repeated scanner HTTP 503 | Asana |
| Canva | SaaS/JS | Repeated scanner HTTP 503 | Miro |
| IKEA US | Ecommerce/marketplace | Repeated scanner HTTP 503 | Patagonia |
| Etsy | Ecommerce/marketplace | Insufficient evaluable HTML | REI |
| Airbnb | Ecommerce/marketplace | Repeated request failure | LEGO Shop |
| Booking.com | Ecommerce/marketplace | Insufficient evaluable HTML | Back Market |
| Decathlon France | Ecommerce/marketplace | Repeated scanner HTTP 503 | GetYourGuide |
| Fnac | Ecommerce/marketplace | Insufficient evaluable HTML | Warby Parker |
| eBay | Ecommerce/marketplace | Insufficient evaluable HTML | Glossier |

The replacements were selected for segment fit and accessible public marketing/catalog pages. Their renderer evidence had not been collected when this mapping was committed.
