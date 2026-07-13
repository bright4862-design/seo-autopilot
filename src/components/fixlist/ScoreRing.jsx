import React, { useEffect, useRef, useState } from "react";

const CIRCUMFERENCE = 2 * Math.PI * 42;

function ringColor(score) {
  return score >= 85 ? "#15803D" : "#B45309";
}

// Animated health-score ring: the stroke sweeps in and the number counts up on
// mount. Honors prefers-reduced-motion by snapping straight to the final value.
export default function ScoreRing({ score = 0, size = 96 }) {
  const target = Math.max(0, Math.min(100, Math.round(Number(score) || 0)));
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const [displayed, setDisplayed] = useState(reduced ? target : 0);
  const [offset, setOffset] = useState(reduced ? CIRCUMFERENCE * (1 - target / 100) : CIRCUMFERENCE);
  const frame = useRef(null);

  useEffect(() => {
    if (reduced) {
      setDisplayed(target);
      setOffset(CIRCUMFERENCE * (1 - target / 100));
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setOffset(CIRCUMFERENCE * (1 - target / 100));
      const started = performance.now();
      const duration = 900;
      function step(now) {
        const raw = Math.min((now - started) / duration, 1);
        const eased = 1 - Math.pow(1 - raw, 3);
        setDisplayed(Math.round(target * eased));
        if (raw < 1) frame.current = requestAnimationFrame(step);
      }
      frame.current = requestAnimationFrame(step);
    }, 150);
    return () => {
      window.clearTimeout(timer);
      if (frame.current) cancelAnimationFrame(frame.current);
    };
  }, [target, reduced]);

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox="0 0 96 96" fill="none" aria-hidden="true" className="-rotate-90">
        <circle cx="48" cy="48" r="42" strokeWidth="4" fill="none" stroke="rgba(28,25,23,0.08)" />
        <circle
          cx="48"
          cy="48"
          r="42"
          strokeWidth="4"
          fill="none"
          strokeLinecap="round"
          stroke={ringColor(target)}
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={offset}
          style={{ transition: reduced ? "none" : "stroke-dashoffset 0.9s cubic-bezier(0.22, 1, 0.36, 1)" }}
        />
      </svg>
      <div
        className="absolute inset-0 flex items-center justify-center font-semibold tracking-tight text-ink tabular-nums"
        style={{ fontSize: size / 3 }}
        aria-label={`Site health score ${target}`}
      >
        {displayed}
      </div>
    </div>
  );
}
