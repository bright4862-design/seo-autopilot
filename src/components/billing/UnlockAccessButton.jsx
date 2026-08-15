import React, { useRef, useState } from "react";
import { base44 } from "@/api/base44Client";
import { UNLOCK_PRICE_LABEL } from "@/lib/access";
import { queueEvent } from "@/lib/analytics";
import { checkoutFailureCode, checkoutFailureMessage } from "@/lib/checkout";

export default function UnlockAccessButton({ label = `Unlock full access — ${UNLOCK_PRICE_LABEL}`, solid = true }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const checkoutStartedRef = useRef(false);

  async function startCheckout() {
    if (checkoutStartedRef.current) return;
    if (window.self !== window.top) {
      setError("Checkout only works in the published app. Open your site in a new tab and try again.");
      return;
    }
    setError("");
    checkoutStartedRef.current = true;
    setLoading(true);
    queueEvent("checkout_started", { plan: "standard_150" });
    let failure = null;
    const response = await base44.functions
      .invoke("createAccessCheckout", { origin: window.location.origin })
      .catch((error) => {
        failure = error;
        return null;
      });
    const url = response?.data?.url;
    if (url) {
      window.location.href = url;
      return;
    }
    setError(checkoutFailureMessage(checkoutFailureCode(response, failure)));
    checkoutStartedRef.current = false;
    setLoading(false);
  }

  return (
    <div>
      <button
        type="button"
        onClick={startCheckout}
        disabled={loading}
        className={`rounded-full px-4 py-1.5 text-[13px] font-medium transition-colors disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink ${
          solid ? "bg-ink text-paper hover:opacity-80" : "border border-hairline text-ink hover:bg-ink/[0.04]"
        }`}
      >
        {loading ? "Opening checkout…" : label}
      </button>
      {error ? <p className="mt-2 text-[12.5px] leading-relaxed text-crit">{error}</p> : null}
    </div>
  );
}
