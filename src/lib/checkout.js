const CHECKOUT_MESSAGE_BY_CODE = Object.freeze({
  checkout_paused: "Paid beta checkout is temporarily paused. No payment was started.",
  checkout_not_invited: "This paid beta cohort is currently invite-only.",
  checkout_access_not_preprovisioned: "Your beta invitation is still being activated. No payment was started.",
  checkout_configuration_invalid: "Paid beta checkout is temporarily unavailable. No payment was started.",
  checkout_origin_not_allowed: "Checkout must be opened from the published FixList app.",
  already_active: "Your paid access is already active. Refresh this page to continue.",
  checkout_payment_processing: "Your payment is already being processed. Do not start another checkout.",
  duplicate_access: "Your access record needs support before checkout can continue.",
  access_conflict: "Your access record needs support before checkout can continue.",
  checkout_session_conflict: "Your checkout needs support before it can continue.",
});

function payloads(value) {
  return [
    value?.response?.data?.data,
    value?.response?.data,
    value?.data?.data,
    value?.data,
    value,
  ].filter((candidate) => candidate && typeof candidate === "object");
}

export function checkoutFailureCode(...values) {
  for (const value of values) {
    for (const payload of payloads(value)) {
      const code = String(payload.code || payload.error_code || payload.error?.code || "")
        .trim()
        .toLowerCase();
      if (code) return code;
    }
  }
  return "checkout_failed";
}

export function checkoutFailureMessage(code) {
  return CHECKOUT_MESSAGE_BY_CODE[String(code || "").trim().toLowerCase()]
    || "We couldn't start checkout. Please try again later. No payment was started.";
}
