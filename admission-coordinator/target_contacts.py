"""Decisions for exclusive, bounded access to an HTTP origin."""

from datetime import datetime, timezone
import hashlib
import json
import re

import admission


ACQUIRE_ACTION = "acquire_target_contact_v1"
SETTLE_ACTION = "settle_target_contact_v1"
MAX_CONTACT_SECONDS = 420
RECEIPT_GRACE_SECONDS = 5
MAX_ORIGINS_PER_DELIVERY = 128
MAX_OPEN_DELIVERIES = 4
MAX_SAFE_INTEGER = (1 << 53) - 1
CLAIM_FIELDS = ("owner_user_id", "request_id", "scan_id", "barrier_generation", "claim_sequence")
DELIVERY_FIELDS = (*CLAIM_FIELDS, "scan_target_origin", "attempt_count", "delivery_id")
ORIGIN_BUSY = "target_contact_busy"
ORIGIN_UNCONFIRMED = "target_contact_unconfirmed"
CONTACTS_DRAINING = "target_contacts_draining"
CONTACT_CONFLICT = "target_contact_claim_conflict"
CONTACT_CLOSED = "target_contact_closed"
INVALID_CONTACT = "invalid_target_contact"


def _integer(value, minimum=1):
    return type(value) is int and minimum <= value <= MAX_SAFE_INTEGER


def validate(payload, *, action):
    details = "delivery_cutoff" if action == ACQUIRE_ACTION else "receipt"
    if set(payload) != {*DELIVERY_FIELDS, "target_origin", "action", details} or payload["action"] != action:
        raise admission.AdmissionError(INVALID_CONTACT)
    if any(not isinstance(payload[name], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", payload[name])
           for name in CLAIM_FIELDS[:3]):
        raise admission.AdmissionError(INVALID_CONTACT)
    if not isinstance(payload["delivery_id"], str) or not re.fullmatch(r"[0-9a-f]{32}", payload["delivery_id"]):
        raise admission.AdmissionError(INVALID_CONTACT)
    for name in ("barrier_generation", "claim_sequence", "attempt_count"):
        if not _integer(payload[name], 0 if name == "barrier_generation" else 1):
            raise admission.AdmissionError(INVALID_CONTACT)
    for name in ("target_origin", "scan_target_origin"):
        if admission.normalize_target_origin(payload[name]) != payload[name]:
            raise admission.AdmissionError(INVALID_CONTACT)
    if action == ACQUIRE_ACTION:
        if not _integer(payload[details]):
            raise admission.AdmissionError(INVALID_CONTACT)
    else:
        _validate_receipt(payload[details])


def _validate_receipt(receipt):
    if not isinstance(receipt, dict) or set(receipt) != {"drained_at", "observation"} or not _integer(receipt["drained_at"]):
        raise admission.AdmissionError(INVALID_CONTACT)
    value = receipt["observation"]
    if value is None:
        return
    if (
        not isinstance(value, dict)
        or set(value) != {"status_code", "observed_at", "retry_after_seconds", "expires_source"}
        or type(value["status_code"]) is not int or value["status_code"] != 429
        or not _integer(value["observed_at"]) or value["observed_at"] > receipt["drained_at"]
        or not _integer(value["retry_after_seconds"])
        or value["retry_after_seconds"] > admission.MAX_TARGET_COOLDOWN_SECONDS
        or value["expires_source"] not in ("retry_after", "default")
    ):
        raise admission.AdmissionError(INVALID_CONTACT)


def delivery_key(payload):
    identity = [payload[field] for field in DELIVERY_FIELDS]
    return hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode("ascii")).hexdigest()


def origin_key(origin):
    return hashlib.sha256(origin.encode("ascii")).hexdigest()


def _keep_through(cutoff):
    return datetime.fromtimestamp(
        cutoff + RECEIPT_GRACE_SECONDS + admission.MAX_TARGET_COOLDOWN_SECONDS + 3600, tz=timezone.utc,
    )


def _contact_map(owner):
    active = owner.get("target_contact_deliveries", {})
    if (
        not isinstance(active, dict) or len(active) > MAX_OPEN_DELIVERIES
        or any(not re.fullmatch(r"[0-9a-f]{64}", key) or not _integer(deadline) for key, deadline in active.items())
    ):
        raise RuntimeError("Invalid stored contact obligations")
    return active


def _gate(gate):
    if gate is None:
        return {"holder": "", "cutoff": 0, "protection_until": 0}
    if (
        not isinstance(gate.get("holder"), str)
        or (gate["holder"] and not re.fullmatch(r"[0-9a-f]{64}", gate["holder"]))
        or not _integer(gate.get("cutoff"), int(bool(gate["holder"])))
        or not _integer(gate.get("protection_until"), 0)
    ):
        raise RuntimeError("Invalid stored origin contact gate")
    return gate


def origin_wait(gate, cooldown, *, now, own_delivery=""):
    """Evaluate the verified site instruction and the independent contact gate."""
    confirmed_until = admission.target_cooldown_expires_at(cooldown)
    if confirmed_until > now:
        return {
            "error": "target_cooldown_active", "retry_after_seconds": confirmed_until - now,
            "expires_source": cooldown.get("expires_source", "retry_after"),
        }
    gate = _gate(gate)
    if gate["holder"] and (gate["holder"] != own_delivery or now >= gate["cutoff"]):
        drain_until = gate["cutoff"] + RECEIPT_GRACE_SECONDS
        protection_until = drain_until + admission.MAX_TARGET_COOLDOWN_SECONDS
        if now < drain_until:
            return {"error": ORIGIN_BUSY, "retry_after_seconds": drain_until - now}
    else:
        protection_until = 0
    protection_until = max(protection_until, gate["protection_until"])
    if protection_until > now:
        return {"error": ORIGIN_UNCONFIRMED, "retry_after_seconds": protection_until - now}
    return {}


def _matches_claim(owner, payload):
    return (
        owner and all(owner.get(field) == payload[field] for field in CLAIM_FIELDS)
        and owner.get("target_origin", payload["scan_target_origin"]) == payload["scan_target_origin"]
    )


def decide_acquire(owner, delivery, gate, cooldown, payload, *, now):
    if not _matches_claim(owner, payload):
        return {"error": CONTACT_CONFLICT}
    if owner["state"] != admission.STATE_BOUND or owner.get("target_contacts_fenced", False):
        return {"error": CONTACT_CLOSED}
    cutoff = payload["delivery_cutoff"]
    if delivery is not None and delivery["cutoff"] != cutoff:
        return {"error": CONTACT_CONFLICT}
    if not now < cutoff <= now + MAX_CONTACT_SECONDS:
        return {"error": CONTACT_CLOSED}

    key = delivery_key(payload)
    origin = origin_key(payload["target_origin"])
    contacts = delivery["contacts"] if delivery is not None else {}
    prior = contacts.get(origin)
    if prior and prior.get("receipt"):
        return {"error": CONTACT_CLOSED}
    wait = origin_wait(gate, cooldown, now=now, own_delivery=key if prior else "")
    if wait:
        return wait
    if prior:
        if _gate(gate)["holder"] != key:
            raise RuntimeError("Stored contact grant detached from its origin")
        return {"outcome": "acquired", "seconds_remaining": cutoff - now}
    active = {k: v for k, v in _contact_map(owner).items() if v > now}
    if len(contacts) >= MAX_ORIGINS_PER_DELIVERY or (key not in active and len(active) >= MAX_OPEN_DELIVERIES):
        return {"error": "target_contact_capacity"}
    return {
        "outcome": "acquired", "seconds_remaining": cutoff - now,
        "owner_write": {
            **owner, "target_origin": payload["scan_target_origin"],
            "target_contact_deliveries": {**active, key: cutoff + RECEIPT_GRACE_SECONDS},
        },
        "delivery_write": {
            "cutoff": cutoff, "contacts": {**contacts, origin: {"opened_at": now}},
            "purge_after": _keep_through(cutoff),
        },
        "gate_write": {**_gate(gate), "holder": key, "cutoff": cutoff, "purge_after": _keep_through(cutoff)},
    }


def decide_settle(owner, delivery, gate, cooldown, payload, *, now):
    origin = origin_key(payload["target_origin"])
    entry = delivery["contacts"].get(origin) if delivery is not None else None
    if entry is None:
        return {"error": CONTACT_CONFLICT}
    cutoff = delivery["cutoff"]
    receipt = payload["receipt"]
    drained_at = receipt["drained_at"]
    observation = receipt["observation"]
    if drained_at < entry["opened_at"] or drained_at > now + RECEIPT_GRACE_SECONDS:
        return {"error": INVALID_CONTACT}
    if observation and observation["observed_at"] < entry["opened_at"]:
        return {"error": INVALID_CONTACT}

    prior = entry.get("receipt")
    if receipt == prior:
        return {"outcome": entry["outcome"]}
    key = delivery_key(payload)
    gate = _gate(gate)
    on_time = (
        prior is None and gate["holder"] == key
        and drained_at <= cutoff and now < cutoff + RECEIPT_GRACE_SECONDS
    )
    result = {"outcome": "settled" if on_time else "protection_retained"}
    if observation:
        expiry = observation["observed_at"] + observation["retry_after_seconds"]
        if expiry > max(now, admission.target_cooldown_expires_at(cooldown)):
            result["cooldown_write"] = {
                "version": admission.TARGET_COOLDOWN_VERSION,
                "expires_at": datetime.fromtimestamp(expiry, tz=timezone.utc),
                "expires_source": observation["expires_source"],
            }
    if drained_at > cutoff:
        protection = drained_at + admission.MAX_TARGET_COOLDOWN_SECONDS
        if protection > max(now, gate["protection_until"]):
            result["gate_write"] = {
                **gate, "protection_until": protection,
                "purge_after": max(_keep_through(drained_at), gate.get("purge_after", _keep_through(cutoff))),
            }
    if prior is None:
        contacts = {**delivery["contacts"], origin: {**entry, "receipt": receipt, "outcome": result["outcome"]}}
        result["delivery_write"] = {**delivery, "contacts": contacts}
    if on_time:
        result["gate_write"] = {**gate, "holder": "", "cutoff": 0}
        if _matches_claim(owner, payload) and all(item.get("outcome") == "settled" for item in contacts.values()):
            active = _contact_map(owner)
            if key in active:
                result["owner_write"] = {**owner, "target_contact_deliveries": {k: v for k, v in active.items() if k != key}}
    return result


def terminal_fence(owner, decision, *, now):
    """Hold a terminal admission until all known contacts drain or time out."""
    if not owner or "target_contact_deliveries" not in owner:
        return decision
    active = {k: v for k, v in _contact_map(owner).items() if v > now}
    if active:
        return {
            "error": CONTACTS_DRAINING,
            "retry_after_seconds": max(active.values()) - now,
            "write": {**owner, "target_contacts_fenced": True, "target_contact_deliveries": active},
        }
    if decision.get("write"):
        decision["write"] = {**decision["write"], "target_contacts_fenced": True, "target_contact_deliveries": {}}
    return decision
