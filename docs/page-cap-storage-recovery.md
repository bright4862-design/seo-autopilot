# Page-cap and browser-storage recovery

Production validation reproduced two release blockers on Center Street Lending:

- an advanced scan reported 151 crawled pages despite the 150-page contract;
- the scanner and Python Review completed, but an oversized duplicated browser-storage record caused the completed scan to be marked failed before durable persistence and dashboard routing.

This recovery change enforces the selected page cap at the Python, Base44, review-input, and persistence boundaries. It also makes ScanRun/FixList/FixItem persistence authoritative, reduces browser storage to one canonical per-scan record plus compact indexes, prunes stale per-scan keys on quota pressure, and reopens durable results when the local cache is unavailable.

The 20-site production audit must remain paused until a fresh Center Street Lending gate completes with no more than 150 pages and reopens by scan ID.
