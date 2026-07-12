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

## July 12, 2026 first-round replacements

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

## July 12, 2026 second-round replacements

Run #3 retained twenty-five eligible records. Miro, Patagonia, REI, and Back Market produced insufficient evaluable HTML, while GetYourGuide returned repeated HTTP 503 responses. The following replacements were selected using public-page accessibility only, before their renderer evidence was collected.

| Removed first-round replacement | Stratum | Eligibility reason | Preselected replacement |
|---|---|---|---|
| Miro | SaaS/JS | Insufficient evaluable HTML | GitLab |
| Patagonia | Ecommerce/marketplace | Insufficient evaluable HTML | Bellroy |
| REI | Ecommerce/marketplace | Insufficient evaluable HTML | Cotopaxi |
| Back Market | Ecommerce/marketplace | Insufficient evaluable HTML | Away |
| GetYourGuide | Ecommerce/marketplace | Repeated HTTP 503 | Mejuri |

## July 12, 2026 final SaaS replacement

Run #4 retained twenty-nine eligible records. GitLab produced insufficient evaluable HTML and could not count toward the SaaS/JS incidence denominator. Monday.com was selected for segment fit and accessible public product content before its renderer evidence was collected.

| Removed second-round replacement | Stratum | Eligibility reason | Preselected replacement |
|---|---|---|---|
| GitLab | SaaS/JS | Insufficient evaluable HTML | Monday.com |

All replacements were selected for segment fit and accessible public marketing or catalog pages. Their renderer evidence had not been collected when each mapping was committed.
