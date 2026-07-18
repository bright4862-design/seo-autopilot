from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, value: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


path = "src/pages/FixList.jsx"
text = read(path)
text = replace_once(
    text,
    "  const healthScore = getHealthScore(scanRecord);\n  const pagesScanned = getPagesScanned(scanRecord, pages);\n  const hasUsefulScan = Boolean(scanRecord && (recommendations.length > 0 || pages.length > 0 || healthScore > 0));\n",
    "  const healthScore = getHealthScore(scanRecord);\n  const scoreUnavailable = isHealthScoreUnavailable(scanRecord);\n  const pagesScanned = getPagesScanned(scanRecord, pages);\n  const hasUsefulScan = Boolean(scanRecord && (recommendations.length > 0 || pages.length > 0 || (healthScore !== null && healthScore > 0)));\n",
    "derive unavailable score state",
)
text = replace_once(
    text,
    "  const passedChecks = hasUsefulScan ? buildPassedChecks(recommendations) : [];\n",
    "  const passedChecks = hasUsefulScan && !scoreUnavailable ? buildPassedChecks(recommendations) : [];\n",
    "suppress passed checks without evidence",
)
text = replace_once(
    text,
    "              <ScoreRing score={healthScore} />\n",
    "              <ScoreRing score={healthScore} unavailable={scoreUnavailable} />\n",
    "pass unavailable state to score ring",
)
text = replace_once(
    text,
    "                  {getHeroHeadline({ healthScore, noHighConfidenceFindings, activeCount: active.length, doneCount: doneItems.length })}\n",
    "                  {getHeroHeadline({ healthScore, scoreUnavailable, noHighConfidenceFindings, activeCount: active.length, doneCount: doneItems.length })}\n",
    "pass unavailable state to headline",
)
text = replace_once(
    text,
    "function getHeroHeadline({ healthScore, noHighConfidenceFindings, activeCount, doneCount }) {\n  if (noHighConfidenceFindings && activeCount === 0 && doneCount === 0) return \"Nothing to fix in this sample.\";\n",
    "function getHeroHeadline({ healthScore, scoreUnavailable, noHighConfidenceFindings, activeCount, doneCount }) {\n  if (scoreUnavailable) return \"Score unavailable.\";\n  if (noHighConfidenceFindings && activeCount === 0 && doneCount === 0) return \"Nothing to fix in this sample.\";\n",
    "unavailable score headline",
)
text = replace_once(
    text,
    "function getLimitationNote(record) {\n  const limitation = cleanString(record?.limitation);\n",
    "function getLimitationNote(record) {\n  if (isHealthScoreUnavailable(record)) return \"We couldn't verify enough usable pages to calculate a reliable score. The access item below describes the scan limitation, not a confirmed on-page SEO defect.\";\n  const limitation = cleanString(record?.limitation);\n",
    "unavailable score limitation",
)
text = replace_once(
    text,
    '''function getHealthScore(record) {
  const score = Number(record?.health_score || record?.seo_score || record?.website_health_report?.health_score || record?.scan_summary?.health_score || record?.scan_summary?.score || 0);
  return Number.isFinite(score) ? Math.round(score) : 0;
}
''',
    '''function isHealthScoreUnavailable(record) {
  const status = cleanString(
    record?.health_score_status
      || record?.website_health_report?.health_score_status
      || record?.scan_summary?.health_score_status,
  );
  if (status === "insufficient_evidence") return true;
  return record?.health_score === null && record?.seo_score === null;
}

function getHealthScore(record) {
  if (isHealthScoreUnavailable(record)) return null;
  const candidates = [
    record?.health_score,
    record?.seo_score,
    record?.website_health_report?.health_score,
    record?.scan_summary?.health_score,
    record?.scan_summary?.score,
  ];
  const raw = candidates.find((value) => value !== null && value !== undefined && value !== "");
  const score = Number(raw);
  return Number.isFinite(score) ? Math.round(score) : null;
}
''',
    "preserve null health score",
)
text = replace_once(
    text,
    '''function getBestSummary(record, healthScore, pagesScanned, issueCount) {
  const summary = cleanString(record?.customer_summary || record?.simple_summary || record?.website_health_report?.overall_explanation || record?.scan_summary?.plain_english_summary || record?.scan_summary?.summary);
  if (summary) return normalizeCoverageSummary(summary, pagesScanned);
  const label = getScoreBand(healthScore).label;
  return `Your website health is ${label.toLowerCase()} with a score of ${healthScore || 0}/100. FixList reviewed ${pagesScanned || 0} pages and found ${issueCount || 0} recommendations. Start with the highest-impact items first.`;
}
''',
    '''function getBestSummary(record, healthScore, pagesScanned, issueCount) {
  const summary = cleanString(record?.customer_summary || record?.simple_summary || record?.website_health_report?.overall_explanation || record?.scan_summary?.plain_english_summary || record?.scan_summary?.summary);
  if (summary) return normalizeCoverageSummary(summary, pagesScanned);
  if (isHealthScoreUnavailable(record)) {
    return `FixList could not verify enough usable pages to calculate a reliable score. It retained ${issueCount || 0} access or verification item${issueCount === 1 ? "" : "s"} from this scan.`;
  }
  const label = getScoreBand(healthScore).label;
  return `Your website health is ${label.toLowerCase()} with a score of ${healthScore || 0}/100. FixList reviewed ${pagesScanned || 0} pages and found ${issueCount || 0} recommendations. Start with the highest-impact items first.`;
}
''',
    "nullable score summary fallback",
)
write(path, text)

score_ring = '''import React, { useEffect, useRef, useState } from "react";

const CIRCUMFERENCE = 2 * Math.PI * 42;

function ringColor(score) {
  return score >= 85 ? "#15803D" : "#B45309";
}

// Animated health-score ring. When evidence is insufficient, the component
// renders a neutral unavailable state instead of inventing a zero score.
export default function ScoreRing({ score = null, size = 96, unavailable = false }) {
  const numericScore = Number(score);
  const hasScore = !unavailable && score !== null && score !== undefined && Number.isFinite(numericScore);
  const target = hasScore ? Math.max(0, Math.min(100, Math.round(numericScore))) : 0;
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const [displayed, setDisplayed] = useState(reduced ? target : 0);
  const [offset, setOffset] = useState(hasScore && reduced ? CIRCUMFERENCE * (1 - target / 100) : CIRCUMFERENCE);
  const frame = useRef(null);

  useEffect(() => {
    if (!hasScore) {
      setDisplayed(0);
      setOffset(CIRCUMFERENCE);
      return undefined;
    }
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
        {hasScore ? displayed : "—"}
      </div>
    </div>
  );
}
'''
write("src/components/fixlist/ScoreRing.jsx", score_ring)

test_source = '''import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const fixListSource = await readFile(new URL("../../src/pages/FixList.jsx", import.meta.url), "utf8");
const scoreRingSource = await readFile(new URL("../../src/components/fixlist/ScoreRing.jsx", import.meta.url), "utf8");

test("insufficient evidence never becomes a zero score in the FixList UI", () => {
  assert.match(fixListSource, /const scoreUnavailable = isHealthScoreUnavailable\(scanRecord\)/);
  assert.match(fixListSource, /<ScoreRing score=\{healthScore\} unavailable=\{scoreUnavailable\} \/>/);
  assert.match(fixListSource, /hasUsefulScan && !scoreUnavailable \? buildPassedChecks/);
  assert.match(fixListSource, /if \(scoreUnavailable\) return "Score unavailable\."/);
  assert.match(fixListSource, /if \(isHealthScoreUnavailable\(record\)\) return null/);
  assert.doesNotMatch(fixListSource, /Number\(record\?\.health_score \|\|/);
});

test("score ring renders an explicit unavailable state", () => {
  assert.match(scoreRingSource, /unavailable = false/);
  assert.match(scoreRingSource, /const hasScore = !unavailable/);
  assert.match(scoreRingSource, /Site health score unavailable/);
  assert.match(scoreRingSource, /\{hasScore \? displayed : "—"\}/);
});
'''
write("tests/frontend/nullableScorePresentation.test.mjs", test_source)

print("Applied nullable score UI contract")
