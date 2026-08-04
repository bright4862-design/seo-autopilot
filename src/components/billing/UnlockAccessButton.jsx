import React, { useState } from "react";
import { base44 } from "@/api/base44Client";
import { UNLOCK_PRICE_LABEL } from "@/lib/access";

export default function UnlockAccessButton({ label = `Unlock full access — ${UNLOCK_PRICE_LABEL}`, solid = true }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function startCheckout() {
    if (window.self !== window.top) {
      setError("Checkout only works in the published app. Open your site in a new tab and try again.");
      return;
    }
    setError("");
    setLoading(true);
    const response = await base44.functions
      .invoke("createAccessCheckout", { origin: window.location.origin })
      .catch(() => null);
    const url = response?.data?.url;
    if (url) {
      window.location.href = url;
      return;
    }
    setError("We couldn't start checkout. Please try again in a moment.");
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