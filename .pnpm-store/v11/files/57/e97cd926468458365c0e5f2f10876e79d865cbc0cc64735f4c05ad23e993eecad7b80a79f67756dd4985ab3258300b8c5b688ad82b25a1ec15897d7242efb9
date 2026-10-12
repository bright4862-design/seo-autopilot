// page-height-bridge — postMessage protocol the iframe exposes to its parent.
// Inert until the parent posts a message; no observers, rewrites, or timers
// fire on their own.
//
//   parent → child  { type: "freeze-vh-units", referenceVhBase?: number }
//     Rewrites every viewport-height unit (`vh`/`dvh`/`svh`/`lvh`) in
//     <style> + CSSOM to a CSS variable-backed expression (kills the
//     vh ↔ auto-resize feedback loop). Repeated calls update the variable,
//     so callers can rebase without recovering raw CSS. Idempotent; covers
//     HMR-added styles too. Fire-and-forget.
//
//   parent → child  { type: "measure-page-height", settleMs?: number }
//     After `settleMs` (default 2000) posts the page's measured content height
//     as `{ type: "page-height-measured", height }` to the requester.

type IncomingMessage = {
  type?: string;
  settleMs?: number;
  referenceVhBase?: number;
};

type IndexableCssRule = CSSRule & {
  cssRules?: CSSRuleList;
  style?: CSSStyleDeclaration;
};

type Debouncer = { trigger: () => void; cancel: () => void };

export type PageHeightBridgeController = {
  freezeVhUnits: (override?: number) => void;
  measurePageHeight: (origin: string, settleMs?: number) => void;
  teardown: () => void;
};

const FALLBACK_VHBASE: number = 900;
const MIN_VHBASE: number = 400;
const DEFAULT_SETTLE_MS: number = 2000;
const NEUTRALIZE_DEBOUNCE_MS: number = 16;
// Three consecutive same-height samples ≈ ~50ms of "no change". Three is
// enough to filter single-frame jitter from layout passes but short enough
// that responses arrive promptly when the DOM is already settled.
const STABILITY_SAMPLES: number = 3;
// Interval between stability samples. ~1 frame at 60Hz; chosen as a plain
// setTimeout (not rAF) because jsdom rAFs are unreliably timed for tests and
// in real browsers a 16ms tick is post-layout for any layout work that fits
// inside one frame.
const STABILITY_TICK_MS: number = 16;
// Hard cap on the stability poll past settleMs. Pages that genuinely never
// stabilize (looping height-animating content) reply with their last sample
// rather than hanging the parent's resize logic.
const STABILITY_MAX_WAIT_MS: number = 1500;
const REFERENCE_VH_BASE_VAR: string = "--base44-reference-vh-base";

const noop: () => void = (): void => {};

let started: boolean = false;

/**
 * Installs the parent-driven message listener. Returns a teardown that
 * removes the listener, disconnects any observers attached as a result of
 * `freeze-vh-units`, and clears any pending response timer. Returns a
 * no-op when bailed (already started, SSR, top window).
 */
export function setupPageHeightBridge(): () => void {
  if (started) return noop;
  if (typeof window === "undefined") return noop;
  if (window.self === window.top) return noop;
  started = true;

  const controller: PageHeightBridgeController = createPageHeightBridgeController();

  const onMessage = (event: MessageEvent): void => {
    const data: IncomingMessage | null = (event.data ?? null) as IncomingMessage | null;
    if (!data || typeof data !== "object") return;
    switch (data.type) {
      case "freeze-vh-units": {
        const override: number | undefined =
          typeof data.referenceVhBase === "number" ? data.referenceVhBase : undefined;
        controller.freezeVhUnits(override);
        return;
      }
      case "measure-page-height": {
        const settleMs: number =
          typeof data.settleMs === "number" ? data.settleMs : DEFAULT_SETTLE_MS;
        const origin: string =
          event.origin && event.origin !== "null" ? event.origin : "*";
        controller.measurePageHeight(origin, settleMs);
        return;
      }
    }
  };

  window.addEventListener("message", onMessage);

  let torn: boolean = false;
  return (): void => {
    if (torn) return;
    torn = true;
    started = false;
    window.removeEventListener("message", onMessage);
    controller.teardown();
  };
}

export function createPageHeightBridgeController(): PageHeightBridgeController {
  let vhCleanups: Array<() => void> | null = null;
  let vhForceRun: (() => void) | null = null;
  let pendingSettle: number | undefined;
  let pendingTick: number | undefined;
  let pendingOrigin: string = "*";

  const cancelPending = (): void => {
    if (pendingSettle !== undefined) {
      window.clearTimeout(pendingSettle);
      pendingSettle = undefined;
    }
    if (pendingTick !== undefined) {
      window.clearTimeout(pendingTick);
      pendingTick = undefined;
    }
  };

  return {
    freezeVhUnits: (override: number | undefined): void => {
      const referenceVhBase: number = resolveReferenceVhBase(override);
      setReferenceVhBase(referenceVhBase);
      if (vhCleanups) {
        vhForceRun?.();
        return;
      }
      vhCleanups = [];
      vhForceRun = startVhNeutralizer(vhCleanups);
    },

    // Target the requester's origin so the height isn't broadcast to anyone
    // who happens to embed us. Falls back to "*" when origin is unavailable
    // (jsdom default, sandboxed iframes with `null` origin).
    //
    // Stability-wait response: after `settleMs`, poll measureContentHeight at
    // STABILITY_TICK_MS intervals until it's unchanged for STABILITY_SAMPLES
    // consecutive ticks, then send exactly one reply. Catches late React
    // mounts (sticky-positioned sections committing after settleMs), debounced
    // neutralizer mutations not yet flushed, image/font-driven layout shifts.
    // STABILITY_MAX_WAIT_MS caps the poll so a page that genuinely never
    // settles still replies eventually.
    measurePageHeight: (origin: string, settleMs: number = DEFAULT_SETTLE_MS): void => {
      pendingOrigin = origin;
      cancelPending();

      pendingSettle = window.setTimeout((): void => {
        pendingSettle = undefined;
        // Flush any debounced unscroll / inline-vh rewrites NOW so the first
        // sample sees a DOM that reflects every mutation triggered during the
        // settle window. Without this, an `overflow-y: scroll` container that
        // mounted mid-settle can still be hiding its children at sample time.
        vhForceRun?.();

        const deadline: number = nowMs() + STABILITY_MAX_WAIT_MS;
        let lastHeight: number = -1;
        let stableSamples: number = 0;

        const respond = (height: number): void => {
          pendingTick = undefined;
          window.parent.postMessage({ type: "page-height-measured", height }, pendingOrigin);
        };

        const tick = (): void => {
          pendingTick = undefined;
          const height: number = measureContentHeight();
          if (height === lastHeight) {
            stableSamples++;
          } else {
            stableSamples = 1;
            lastHeight = height;
          }
          if (stableSamples >= STABILITY_SAMPLES || nowMs() >= deadline) {
            respond(height);
            return;
          }
          pendingTick = window.setTimeout(tick, STABILITY_TICK_MS);
        };

        tick();
      }, settleMs);
    },

    teardown: (): void => {
      if (vhCleanups) {
        for (const c of vhCleanups) c();
        vhCleanups = null;
        vhForceRun = null;
      }
      cancelPending();
    },
  };
}

function nowMs(): number {
  if (typeof performance !== "undefined" && typeof performance.now === "function") {
    return performance.now();
  }
  return Date.now();
}

function resolveReferenceVhBase(override: number | undefined): number {
  if (override !== undefined) return override;
  const detected: number = window.innerHeight || 0;
  return detected >= MIN_VHBASE ? detected : FALLBACK_VHBASE;
}

function setReferenceVhBase(referenceVhBase: number): void {
  document.documentElement.style.setProperty(REFERENCE_VH_BASE_VAR, `${referenceVhBase}px`);
}

// Caches keep work proportional to *new* CSS, not total CSS. <head> observer
// catches `<style>`/`<link>` adds; per-element observers catch HMR text edits.
// Returns a `forceRun` so the caller can re-trigger neutralization on later
// parent requests (idempotent — already-rewritten text is skipped via the
// processed sets).
function startVhNeutralizer(cleanups: Array<() => void>): () => void {
  // Match vh + the dynamic/small/large variants. Tailwind v4 emits `h-screen`
  // as `100dvh`; all four collapse to the same frozen `referenceVhBase`.
  const VH_RE: RegExp = /(\d+(?:\.\d+)?)(?:d|s|l)?vh\b/g;
  const processedStyles: WeakSet<HTMLStyleElement> = new WeakSet();
  const processedSheets: WeakMap<CSSStyleSheet, number> = new WeakMap();
  const watchedStyles: WeakSet<HTMLStyleElement> = new WeakSet();
  const styleObservers: Set<MutationObserver> = new Set();

  const unscrolled: WeakSet<Element> = new WeakSet();

  const rewrite = (input: string): string =>
    input.replace(VH_RE, (_match: string, n: string): string =>
      `calc(var(${REFERENCE_VH_BASE_VAR}) * ${formatVhFactor(n)})`,
    );

  // Defeats internal vertical scrollers. The canvas wants the whole page laid
  // out top-to-bottom, but `<div class="overflow-y-auto" style={{height:
  // "100vh"}}>` hides its children behind an internal scrollbar — only the
  // first child appears in the preview. Forcing `overflow-y: visible` lets
  // children paint outside the parent's box; block flow positions them at
  // their natural offsets so document.body extends to include them. `auto`
  // and `scroll` only — `hidden` and `clip` express intentional clipping (UI
  // chrome, rounded-corner masks) we shouldn't undo.
  const unscrollY = (el: Element): void => {
    if (unscrolled.has(el)) return;
    const computedStyle: CSSStyleDeclaration = window.getComputedStyle(el);
    const ovY: string = computedStyle.overflowY;
    if (ovY !== "auto" && ovY !== "scroll") return;
    unscrolled.add(el);
    (el as HTMLElement).style.setProperty("overflow-y", "visible", "important");
  };

  const unscrollSubtree = (root: Element): void => {
    unscrollY(root);
    root.querySelectorAll<HTMLElement>("*").forEach(unscrollY);
  };

  // Rewrites vh-bearing properties on a single element's inline style. Covers
  // React's `style={{ height: "100vh" }}` and imperative `el.style.h = ".vh"`
  // — both bypass <style> tags and CSSOM. Per-property setProperty preserves
  // `!important`. Snapshotting prop names first guards against iteration-time
  // mutation of `style.length`.
  const rewriteInlineStyle = (el: Element): void => {
    const style: CSSStyleDeclaration | undefined = (el as HTMLElement).style;
    if (!style || style.length === 0) return;
    const props: string[] = [];
    for (let i: number = 0; i < style.length; i++) {
      const prop: string | undefined = style[i];
      if (prop) props.push(prop);
    }
    for (const prop of props) {
      const value: string = style.getPropertyValue(prop);
      if (!value || value.indexOf("vh") === -1) continue;
      const next: string = rewrite(value);
      if (next !== value) style.setProperty(prop, next, style.getPropertyPriority(prop));
    }
  };

  const neutralize = (): void => {
    document.querySelectorAll<HTMLStyleElement>("style").forEach((el: HTMLStyleElement): void => {
      watchStyleEl(el);
      if (processedStyles.has(el)) return;
      processedStyles.add(el);
      const text: string | null = el.textContent;
      if (!text || text.indexOf("vh") === -1) return;
      const next: string = rewrite(text);
      if (next !== text) el.textContent = next;
    });

    for (let i: number = 0; i < document.styleSheets.length; i++) {
      const sheet: CSSStyleSheet | undefined = document.styleSheets[i];
      if (!sheet) continue;
      let rules: CSSRuleList;
      try {
        rules = sheet.cssRules;
      } catch {
        continue; // CORS-protected
      }
      if (processedSheets.get(sheet) === rules.length) continue;
      rewriteVhInRules(rules, rewrite);
      processedSheets.set(sheet, rules.length);
    }

    // Initial sweep of inline `style="...vh..."` attributes already in the DOM
    // at freeze time. Future inline-style mutations (React commits, motion
    // libraries, imperative assignments) are picked up by inlineStyleObserver.
    document.querySelectorAll<HTMLElement>('[style*="vh"]').forEach(rewriteInlineStyle);

    // Defeat internal scrollers — same dual coverage (initial sweep here,
    // subtree additions in inlineStyleObserver).
    if (document.body) unscrollSubtree(document.body);
  };

  const debouncer: Debouncer = createDebouncer(neutralize, NEUTRALIZE_DEBOUNCE_MS);
  const debouncedNeutralize: () => void = debouncer.trigger;
  cleanups.push(debouncer.cancel);

  const watchStyleEl = (el: HTMLStyleElement): void => {
    if (watchedStyles.has(el)) return;
    watchedStyles.add(el);
    const obs: MutationObserver = new MutationObserver((): void => {
      processedStyles.delete(el);
      debouncedNeutralize();
    });
    obs.observe(el, { characterData: true, childList: true, subtree: true });
    styleObservers.add(obs);
  };
  cleanups.push((): void => {
    for (const obs of styleObservers) obs.disconnect();
    styleObservers.clear();
  });

  debouncedNeutralize();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", debouncedNeutralize);
    cleanups.push((): void => document.removeEventListener("DOMContentLoaded", debouncedNeutralize));
  }
  window.addEventListener("load", debouncedNeutralize);
  cleanups.push((): void => window.removeEventListener("load", debouncedNeutralize));

  const headObserver: MutationObserver = new MutationObserver((mutations: MutationRecord[]): void => {
    for (const m of mutations) {
      if (containsStylesheetNode(m.addedNodes) || containsStylesheetNode(m.removedNodes)) {
        debouncedNeutralize();
        return;
      }
    }
  });
  cleanups.push((): void => headObserver.disconnect());

  const attachHeadObserver = (): void => {
    if (document.head) headObserver.observe(document.head, { childList: true, subtree: false });
  };
  if (document.head) {
    attachHeadObserver();
  } else {
    document.addEventListener("DOMContentLoaded", attachHeadObserver);
    cleanups.push((): void => document.removeEventListener("DOMContentLoaded", attachHeadObserver));
  }

  // Pass 3: inline `style` attributes. One global observer covers every
  // element — past, present, and future — without per-node tracking. Two
  // mutation kinds matter:
  //   • attributes: React/JS sets `style` on an element already in the tree
  //     (`el.style.h = "..vh"`, re-render diff). After rewrite the value has
  //     no "vh", so the next mutation gates out — single-tick convergence.
  //   • childList: a node is mounted with its `style` attribute already set
  //     off-tree (React's initial mount path uses createElement+setAttribute
  //     BEFORE appendChild, so attribute mutations never fire for them). Scan
  //     the added subtree for `[style*="vh"]` and rewrite.
  // Microtask delivery means rewrites land before layout, so no flash.
  const scanSubtreeForInlineVh = (node: Node): void => {
    if (!(node instanceof Element)) return;
    const attr: string | null = node.getAttribute("style");
    if (attr && attr.indexOf("vh") !== -1) rewriteInlineStyle(node);
    node.querySelectorAll<HTMLElement>('[style*="vh"]').forEach(rewriteInlineStyle);
    // New subtrees may introduce overflow-y: auto|scroll containers (route
    // changes, conditional UI). Catch them here too.
    unscrollSubtree(node);
  };
  const inlineStyleObserver: MutationObserver = new MutationObserver(
    (mutations: MutationRecord[]): void => {
      for (const m of mutations) {
        if (m.type === "attributes") {
          const target: Node = m.target;
          if (!(target instanceof Element)) continue;
          const attr: string | null = target.getAttribute("style");
          if (!attr || attr.indexOf("vh") === -1) continue;
          rewriteInlineStyle(target);
        } else if (m.type === "childList") {
          for (let i: number = 0; i < m.addedNodes.length; i++) {
            const node: Node | undefined = m.addedNodes[i];
            if (node) scanSubtreeForInlineVh(node);
          }
        }
      }
    },
  );
  cleanups.push((): void => inlineStyleObserver.disconnect());

  const attachInlineStyleObserver = (): void => {
    const root: Element | null = document.documentElement;
    if (!root) return;
    inlineStyleObserver.observe(root, {
      attributes: true,
      attributeFilter: ["style"],
      childList: true,
      subtree: true,
    });
  };
  attachInlineStyleObserver();

  return debouncedNeutralize;
}

function formatVhFactor(value: string): string {
  return String(Number((parseFloat(value) / 100).toFixed(6)));
}

function rewriteVhInRules(rules: CSSRuleList, rewrite: (value: string) => string): void {
  for (let i: number = 0; i < rules.length; i++) {
    const rule: IndexableCssRule | undefined = rules[i] as IndexableCssRule | undefined;
    if (!rule) continue;
    if (rule.cssRules) rewriteVhInRules(rule.cssRules, rewrite);
    const style: CSSStyleDeclaration | undefined = rule.style;
    if (!style) continue;
    for (let j: number = 0; j < style.length; j++) {
      const prop: string | undefined = style[j];
      if (!prop) continue;
      const value: string = style.getPropertyValue(prop);
      if (!value || value.indexOf("vh") === -1) continue;
      const next: string = rewrite(value);
      if (next !== value) style.setProperty(prop, next, style.getPropertyPriority(prop));
    }
  }
}

function containsStylesheetNode(nodes: NodeList): boolean {
  for (let i: number = 0; i < nodes.length; i++) {
    const node: Node | undefined = nodes[i];
    if (node instanceof HTMLStyleElement || node instanceof HTMLLinkElement) return true;
  }
  return false;
}

function measureContentHeight(): number {
  const scrollHeight: number = Math.max(
    document.documentElement.scrollHeight,
    document.body?.scrollHeight ?? 0,
  );
  const referenceVhBase: number = readReferenceVhBase();
  // Excludes `body.clientHeight`: it grows with content, which makes
  // viewportBottom land at the document bottom and trips the stretched-
  // container heuristic on the last section. `referenceVhBase` keeps the
  // h-screen-wrapper case covered when the iframe is shorter than 100vh.
  const viewportHeight: number = Math.max(
    window.innerHeight || 0,
    document.documentElement.clientHeight,
    referenceVhBase,
  );
  const contentBottom: number = measureElementContentBottom(viewportHeight);
  if (contentBottom > 0) return Math.ceil(Math.max(contentBottom, referenceVhBase));
  return Math.ceil(Math.max(scrollHeight, referenceVhBase));
}

function readReferenceVhBase(): number {
  const value: string = document.documentElement.style.getPropertyValue(REFERENCE_VH_BASE_VAR);
  const parsed: number = parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function measureElementContentBottom(viewportHeight: number): number {
  if (!document.body) return 0;
  const elements: Element[] = [document.body, ...Array.from(document.body.querySelectorAll("*"))];
  const contentBottoms: WeakMap<Element, number> = new WeakMap();
  const viewportBottom: number = window.scrollY + viewportHeight;

  for (let i: number = elements.length - 1; i >= 0; i--) {
    const el: Element | undefined = elements[i];
    if (!el) continue;
    const childContentBottom: number = readChildrenContentBottom(el, contentBottoms);
    const metrics: ElementMetrics = readElementMetrics(el);
    const selfBottom: number = isViewportStretchedContainer(
      metrics,
      childContentBottom,
      viewportHeight,
      viewportBottom,
    )
      ? 0
      : metrics.bottom;
    contentBottoms.set(el, Math.max(childContentBottom, selfBottom));
  }

  return contentBottoms.get(document.body) ?? 0;
}

function readChildrenContentBottom(
  el: Element,
  contentBottoms: WeakMap<Element, number>,
): number {
  let childContentBottom: number = 0;
  for (let i: number = 0; i < el.children.length; i++) {
    const child: Element | undefined = el.children[i];
    if (!child) continue;
    childContentBottom = Math.max(childContentBottom, contentBottoms.get(child) ?? 0);
  }
  return childContentBottom;
}

type ElementMetrics = { bottom: number; height: number };

function readElementMetrics(el: Element): ElementMetrics {
  const computedStyle: CSSStyleDeclaration = window.getComputedStyle(el);
  if (isOutOfFlowDecoration(computedStyle)) return { bottom: 0, height: 0 };
  const rect: DOMRect = el.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return { bottom: 0, height: 0 };
  return {
    bottom: rect.bottom + window.scrollY + readMarginBottom(computedStyle),
    height: rect.height,
  };
}

function readMarginBottom(computedStyle: CSSStyleDeclaration): number {
  const marginBottom: number = parseFloat(computedStyle.marginBottom);
  return Number.isFinite(marginBottom) ? marginBottom : 0;
}

function isOutOfFlowDecoration(computedStyle: CSSStyleDeclaration): boolean {
  if (computedStyle.position === "fixed") return true;
  return computedStyle.position === "absolute" && computedStyle.pointerEvents === "none";
}

// A "stretched container" spans the full viewport top-to-bottom. Requires
// BOTH `bottom ≈ viewportBottom` AND `height ≈ viewportHeight` — otherwise an
// in-flow section that just happens to end at viewportBottom (e.g. when the
// iframe has been content-sized to the previous measurement) gets falsely
// filtered, undermeasuring the page.
function isViewportStretchedContainer(
  metrics: ElementMetrics,
  childBottom: number,
  viewportHeight: number,
  viewportBottom: number,
): boolean {
  return (
    childBottom > 0 &&
    Math.abs(metrics.bottom - viewportBottom) <= 1 &&
    Math.abs(metrics.height - viewportHeight) <= 1 &&
    metrics.bottom - childBottom > 8
  );
}

function createDebouncer(fn: () => void, delayMs: number): Debouncer {
  let timer: number | undefined;
  return {
    trigger: (): void => {
      if (timer !== undefined) window.clearTimeout(timer);
      timer = window.setTimeout(fn, delayMs);
    },
    cancel: (): void => {
      if (timer !== undefined) {
        window.clearTimeout(timer);
        timer = undefined;
      }
    },
  };
}
