# P1-B1 Focused Same-Origin Folder Scans — Design

Date: 2026-08-31

## Goal

Let a FixList customer deliberately scan one same-origin folder such as `/fr/`, `/en/`, or `/shop/` as a separate Standard 150 scan, without changing the Standard 150 crawl cap, weakening ownership/robots/SSRF protections, or allowing scoped and full-site scans to collide in durable admission/replay.

## Scope

This design implements **P1-B1 only**.

Included:
- same-origin path-prefix scopes;
- explicit customer confirmation;
- distinct durable request/admission identity per scope;
- persisted parent/scope lineage on ScanRun;
- separate 150-page budget, ScanRun, FixList, authority decision, reload/history entry;
- focused-scan CTA derived from trustworthy same-origin market/folder evidence already present in the completed parent scan;
- history labels that distinguish full-site and focused scans.

Excluded:
- subdomain scanning;
- registrable-domain trust shortcuts;
- cross-origin crawling;
- silent automatic child scans;
- extra page budget for the parent scan;
- changing robots.txt, SSRF, admission coordinator, authority or 150-page limits;
- P1-B2 subdomain ownership design.

## Existing safe foundation

The Python scanner already accepts `path_prefix`, resolves it through `resolve_crawl_scope()`, rejects URLs that are not `same_origin()`, and rejects paths outside `path_within_scope()`. It still loads robots.txt for the requested origin and keeps Standard 150 limits.

The missing safety boundary is durable identity. Today both browser identity and Base44 admission fingerprint are based on `standard_150|website_url`; `path_prefix` is not included. Therefore a full-site scan and a focused scan of the same origin can collide in replay/admission.

## Public scope contract

A focused path scan sends:

```json
{
  "parent_scan_id": "<authoritative parent ScanRun id>",
  "scope_type": "path_prefix",
  "requested_origin": "https://www.example.com",
  "requested_path_prefix": "/fr/",
  "discovered_from": "sampling_market",
  "user_confirmed": true
}
```

The existing `website_url` remains the same-origin seed URL. For a focused scan, the canonical seed is the requested origin plus the normalized path prefix.

### Normalization

`normalizeFocusedPathPrefix(value)` must:
- accept a path only, never a full URL;
- remove query and fragment;
- collapse duplicate slashes;
- require a leading slash;
- normalize an empty/root value to `/`;
- preserve case rather than inventing server semantics;
- end non-root prefixes with `/`;
- reject dot segments `.` and `..`;
- reject backslashes, encoded path separators, control characters and non-HTTP concepts.

`/` is the full-site scope and is not offered as a focused scan.

## Durable identity

The canonical identity becomes:

`standard_150|<normalized_target>|scope:path_prefix:<normalized_prefix>`

for focused scans, and remains backward compatible for full-site scans:

`standard_150|<normalized_target>`

The server admission fingerprint uses the same logical scope inputs before hashing.

Consequences:
- full site and `/fr/` are distinct;
- `/fr/` and `/en/` are distinct;
- duplicate submission of the same `/fr/` scope still coalesces/replays;
- an old full-site request fingerprint remains valid for historical rows.

## Server validation

`startStandardScanJob` is the authoritative validator.

For `scope_type=path_prefix` it must require:
1. `user_confirmed === true`;
2. non-root valid `requested_path_prefix`;
3. valid `parent_scan_id`;
4. parent ScanRun belongs to the same authenticated owner;
5. parent is terminal and has a trustworthy saved result (`complete` authoritative or verified `limited`);
6. parent `project_id` equals the requested project;
7. parent origin/domain equals the current project/website origin;
8. `requested_origin` exactly equals the normalized current origin;
9. focused seed path lies inside the requested prefix;
10. requested prefix is same-origin and contains no authority/host component.

Failure is fail-closed with customer-safe codes; no ScanRun is created and no admission claim is retained.

## Persistence

Add optional ScanRun fields:

- `parent_scan_id: string`
- `scope_type: "path_prefix" | ""`
- `requested_origin: string`
- `requested_path_prefix: string`
- `discovered_from: string`
- `user_confirmed: boolean`

Keep existing `path_prefix` as the effective worker crawl boundary for compatibility.

A child scan gets its own:
- request/idempotency key;
- admission claim;
- ScanRun id;
- 150-page budget;
- review/classification;
- authority seal;
- FixList/FixItems;
- terminal lifecycle.

Parent and child results are never merged.

## Discovery and customer CTA

The first release offers focused scans only from trustworthy same-origin folder evidence already returned by sampling v2.

A new pure helper `focusedPathScopes(record)` derives candidates from sampling evidence, preferring market/language prefixes that:
- are explicit path prefixes (for example `/fr/`, `/de-at/`);
- are not root;
- are on the current scan origin;
- were discovered in the parent inventory;
- are materially under-sampled or represent a meaningful multi-market section.

The helper returns a bounded list (maximum 6) with:
- `path_prefix`;
- `label`;
- `discovered`;
- `sampled`;
- `reason`;
- `discovered_from: "sampling_market"`.

If evidence does not contain a trustworthy path prefix, FixList shows no focused-scan CTA. It never guesses a folder from a human-readable market label.

## UI

On a useful completed/verified parent FixList, when candidates exist, show a compact **Site sections discovered** panel below the sampling disclosure.

Each row shows:
- section label/path;
- sampled vs discovered counts when known;
- short reason;
- **Scan this section separately** button.

Clicking the CTA:
1. shows an explicit confirmation state naming the exact folder and 150-page separate budget;
2. on confirmation, starts a new Standard 150 scan with the scope payload;
3. navigates to the child scan by its server-created scan id.

No automatic scan starts from discovery alone.

## History and reload

`getCustomerScanResult` may expose the non-sensitive lineage fields in exact and history projections.

History presents:
- full-site scan: existing hostname/date display;
- child scan: hostname plus `· /fr/` (or equivalent);
- optional relation text `Focused scan`.

Reload reads the child ScanRun by exact id and displays its own FixList. Parent linkage is metadata only and does not authorize access.

## Error handling

New fail-closed failure codes:
- `focused_scope_confirmation_required`
- `focused_scope_invalid`
- `focused_scope_origin_mismatch`
- `focused_scope_parent_not_found`
- `focused_scope_parent_not_ready`
- `focused_scope_project_mismatch`

Customer copy states that the section scan was not started and the original scan remains unchanged.

## Security invariants

- no cross-origin target may be accepted;
- no subdomain inheritance;
- no scheme/host/port embedded in `requested_path_prefix`;
- no weakening of `validatePublicHttpUrl`;
- no weakening of BusinessProject ownership;
- no weakening of parent ScanRun ownership;
- no robots override;
- no SSRF relaxation;
- no background child submission;
- no increased crawl cap;
- no browser-created ScanRun identity.

## Tests / acceptance

Must prove:
- `/` and `/fr/` have different fingerprints;
- `/fr/` duplicate requests replay the same durable run;
- `/fr/` and `/en/` do not replay one another;
- malformed/cross-origin prefixes fail before admission;
- parent ownership/project/origin mismatches fail closed;
- worker receives normalized `path_prefix`;
- scanner excludes `/en/` while scanning `/fr/`;
- child metadata survives exact result projection and account history;
- refresh/history reopen the same child scan;
- each child remains capped at 150;
- existing full-site identity/replay tests remain green;
- existing robots/SSRF tests remain green.

## Release strategy

P1-B1 stays on its own branch/PR and is not merged into or deployed with the current `7a95768cc8ee2076` production candidate.

After the current release is accepted, P1-B1 can be rebased onto the accepted main, assigned a new release fingerprint, deployed as one exact release, and production-tested on Musement/Pretto/Meilleurtaux path scopes.

P1-B2 subdomains begins only after P1-B1 passes production acceptance.
