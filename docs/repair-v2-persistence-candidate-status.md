# Repair v2 persistence candidate — gate status

This branch is a child of the green UX/shadow integration branch.

Runtime activation: **OFF**  
Deployment/Base44 publish: **OFF**  
Scanner/crawler changes: **NONE**

Current candidate proves only the signed data contract:

- optional FixList/FixItem v2 schema fields, with no historical defaults
- complete snapshot-level repair authority
- canonical customer order persisted separately from deterministic `fix_id` serialization
- explicit passed-check evaluation ledger
- real authority HMAC round-trip using existing seal/row helpers
- historical rows remain byte-for-byte legacy when no v2 parent contract exists
- partial/mixed v2 state fails closed
- tampered v2 repair evidence invalidates the authority proof

The v2 transformer/reconstructor is intentionally not imported by live scanner, review, persistence, customer-result, or Grok authority runtime yet.

Next gate after exact-head CI: only if all frontend + scanner + frozen revision + image-build checks remain green, consider a separately reviewed conditional runtime insertion that is a no-op for legacy scans.
