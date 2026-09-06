import React, { useEffect, useState } from "react";

const CIRCUMFERENCE = 2 * Math.PI * 42;

function ringColor(score) {
  return score >= 85 ? "#15803D" : "#B45309";
}

/**
 * The health score, with the ring animated and the number held still.
 *
 * The number used to count from 0 up to the score over 900ms. For most of a
 * second the page showed a figure that was not this site's score -- and screen
 * readers were told the real one at the same moment, so what was seen and what
 * was announced disagreed. On a slow render, or a scroll away and back, a
 * customer's first sight of their score was a 0 they had to watch climb.
 *
 * The stroke still sweeps, because that reads as the page arriving rather than
 * as a value changing. The digits are the score from the first paint.
 *
 * When evidence is insufficient this renders a neutral unavailable state rather
 * than inventing a zero.
 */
export default function ScoreRing({ score = null, size = 96, unavailable = false }) {
  const numericScore = Number(score);
  const hasScore = !unavailable && score !== null && score !== undefined && Number.isFinite(numericScore);
  const target = hasScore ? Math.max(0, Math.min(100, Math.round(numericScore))) : 0;
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const [offset, setOffset] = useState(hasScore && reduced ? CIRCUMFERENCE * (1 - target / 100) : CIRCUMFERENCE);

  useEffect(() => {
    if (!hasScore) {
      setOffset(CIRCUMFERENCE);
      return undefined;
    }
    if (reduced) {
      setOffset(CIRCUMFERENCE * (1 - target / 100));
      return undefined;
    }
    // One frame at full offset so the CSS transition has something to sweep
    // from; the number below has been correct the whole time.
    const timer = window.setTimeout(() => setOffset(CIRCUMFERENCE * (1 - target / 100)), 150);
    return () => window.clearTimeout(timer);
  }, [target, reduced, hasScore]);

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox="0 0 96 96" fill="none" aria-hidden="true" className="-rotate-90">
        <circle cx="48" cy="48" r="42" strokeWidth="4" fill="none" stroke="rgba(28,25,23,0.08)" />
        {hasScore ? (
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
        ) : null}
      </svg>
      <div
        className="absolute inset-0 flex items-center justify-center font-semibold tracking-tight text-ink tabular-nums"
        style={{ fontSize: hasScore ? size / 3 : size / 3.6 }}
        aria-label={hasScore ? `Site health score ${target}` : "Site health score unavailable"}
      >
        {hasScore ? target : "—"}
      </div>
    </div>
  );
}
