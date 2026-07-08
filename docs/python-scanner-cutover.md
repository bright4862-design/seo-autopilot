# Python scanner cutover plan

Pretto benchmark gate cleared in GitHub Actions:

- in-scope pages: 21 > Deno baseline 9
- findings: 1 > Deno baseline 0
- artifacts: 50 <= 50 cap, versus Deno 500
- wall-clock: 3.1s

## Current state

The Python scanner service lives under `scanner-api/` and exposes:

- `GET /health`
- `POST /scan`

`POST /scan` accepts:

```json
{
  "website_url": "https://www.example.com/section/",
  "path_prefix": "/section",
  "scan_mode": "advanced",
  "business_name": "optional",
  "cms_platform": "optional"
}
```

If `SCANNER_API_KEY` is set in the scanner service environment, requests must include:

```text
x-scanner-key: <same secret>
```

## Base44 wrapper

`base44/functions/runPythonScanner/entry.ts` is a thin wrapper around the external Python scanner API.

It requires these Base44/server env vars before use:

```text
SCANNER_API_URL=https://<deployed-python-scanner-host>
SCANNER_API_KEY=<shared-secret>
```

`PYTHON_SCANNER_API_URL` and `PYTHON_SCANNER_API_KEY` are also supported aliases.

The wrapper preserves the scanner response contract and annotates responses with:

```json
{
  "wrapper_version": "runPythonScanner_wrapper_v1",
  "scanner_backend": "python_scanner_api"
}
```

## Safe rollout sequence

1. Deploy `scanner-api/` to a controlled host.
2. Set `SCANNER_API_KEY` on the scanner service.
3. Set `SCANNER_API_URL` and `SCANNER_API_KEY` in the Base44 function environment.
4. Invoke `runPythonScanner` manually against Pretto and one or two other challenge sites.
5. Compare FixList UI output against `runAdvancedScan`.
6. After output is confirmed, route `runAdvancedScan` to the Python backend or switch the frontend call to `runPythonScanner`.

## Production caution

The scanner is ready for controlled benchmark and staging use. Before accepting arbitrary public URLs at scale, finish the DNS-rebinding hardening tracked in `scanner-api/SECURITY_BACKLOG.md`.
