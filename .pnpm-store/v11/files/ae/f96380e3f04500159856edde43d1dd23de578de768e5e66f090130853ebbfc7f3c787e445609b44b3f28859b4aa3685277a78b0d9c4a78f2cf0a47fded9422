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
const FALLBACK_VHBASE = 900;
const MIN_VHBASE = 400;
const DEFAULT_SETTLE_MS = 2000;
const NEUTRALIZE_DEBOUNCE_MS = 16;
// Three consecutive same-height samples ≈ ~50ms of "no change". Three is
// enough to filter single-frame jitter from layout passes but short enough
// that responses arrive promptly when the DOM is already settled.
const STABILITY_SAMPLES = 3;
// Interval between stability samples. ~1 frame at 60Hz; chosen as a plain
// setTimeout (not rAF) because jsdom rAFs are unreliably timed for tests and
// in real browsers a 16ms tick is post-layout for any layout work that fits
// inside one frame.
const STABILITY_TICK_MS = 16;
// Hard cap on the stability poll past settleMs. Pages that genuinely never
// stabilize (looping height-animating content) reply with their last sample
// rather than hanging the parent's resize logic.
const STABILITY_MAX_WAIT_MS = 1500;
const REFERENCE_VH_BASE_VAR = "--base44-reference-vh-base";
const noop = () => { };
let started = false;
/**
 * Installs the parent-driven message listener. Returns a teardown that
 * removes the listener, disconnects any observers attached as a result of
 * `freeze-vh-units`, and clears any pending response timer. Returns a
 * no-op when bailed (already started, SSR, top window).
 */
export function setupPageHeightBridge() {
    if (started)
        return noop;
    if (typeof window === "undefined")
        return noop;
    if (window.self === window.top)
        return noop;
    started = true;
    const controller = createPageHeightBridgeController();
    const onMessage = (event) => {
        const data = (event.data ?? null);
        if (!data || typeof data !== "object")
            return;
        switch (data.type) {
            case "freeze-vh-units": {
                const override = typeof data.referenceVhBase === "number" ? data.referenceVhBase : undefined;
                controller.freezeVhUnits(override);
                return;
            }
            case "measure-page-height": {
                const settleMs = typeof data.settleMs === "number" ? data.settleMs : DEFAULT_SETTLE_MS;
                const origin = event.origin && event.origin !== "null" ? event.origin : "*";
                controller.measurePageHeight(origin, settleMs);
                return;
            }
        }
    };
    window.addEventListener("message", onMessage);
    let torn = false;
    return () => {
        if (torn)
            return;
        torn = true;
        started = false;
        window.removeEventListener("message", onMessage);
        controller.teardown();
    };
}
export function createPageHeightBridgeController() {
    let vhCleanups = null;
    let vhForceRun = null;
    let pendingSettle;
    let pendingTick;
    let pendingOrigin = "*";
    const cancelPending = () => {
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
        freezeVhUnits: (override) => {
            const referenceVhBase = resolveReferenceVhBase(override);
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
        measurePageHeight: (origin, settleMs = DEFAULT_SETTLE_MS) => {
            pendingOrigin = origin;
            cancelPending();
            pendingSettle = window.setTimeout(() => {
                pendingSettle = undefined;
                // Flush any debounced unscroll / inline-vh rewrites NOW so the first
                // sample sees a DOM that reflects every mutation triggered during the
                // settle window. Without this, an `overflow-y: scroll` container that
                // mounted mid-settle can still be hiding its children at sample time.
                vhForceRun?.();
                const deadline = nowMs() + STABILITY_MAX_WAIT_MS;
                let lastHeight = -1;
                let stableSamples = 0;
                const respond = (height) => {
                    pendingTick = undefined;
                    window.parent.postMessage({ type: "page-height-measured", height }, pendingOrigin);
                };
                const tick = () => {
                    pendingTick = undefined;
                    const height = measureContentHeight();
                    if (height === lastHeight) {
                        stableSamples++;
                    }
                    else {
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
        teardown: () => {
            if (vhCleanups) {
                for (const c of vhCleanups)
                    c();
                vhCleanups = null;
                vhForceRun = null;
            }
            cancelPending();
        },
    };
}
function nowMs() {
    if (typeof performance !== "undefined" && typeof performance.now === "function") {
        return performance.now();
    }
    return Date.now();
}
function resolveReferenceVhBase(override) {
    if (override !== undefined)
        return override;
    const detected = window.innerHeight || 0;
    return detected >= MIN_VHBASE ? detected : FALLBACK_VHBASE;
}
function setReferenceVhBase(referenceVhBase) {
    document.documentElement.style.setProperty(REFERENCE_VH_BASE_VAR, `${referenceVhBase}px`);
}
// Caches keep work proportional to *new* CSS, not total CSS. <head> observer
// catches `<style>`/`<link>` adds; per-element observers catch HMR text edits.
// Returns a `forceRun` so the caller can re-trigger neutralization on later
// parent requests (idempotent — already-rewritten text is skipped via the
// processed sets).
function startVhNeutralizer(cleanups) {
    // Match vh + the dynamic/small/large variants. Tailwind v4 emits `h-screen`
    // as `100dvh`; all four collapse to the same frozen `referenceVhBase`.
    const VH_RE = /(\d+(?:\.\d+)?)(?:d|s|l)?vh\b/g;
    const processedStyles = new WeakSet();
    const processedSheets = new WeakMap();
    const watchedStyles = new WeakSet();
    const styleObservers = new Set();
    const unscrolled = new WeakSet();
    const rewrite = (input) => input.replace(VH_RE, (_match, n) => `calc(var(${REFERENCE_VH_BASE_VAR}) * ${formatVhFactor(n)})`);
    // Defeats internal vertical scrollers. The canvas wants the whole page laid
    // out top-to-bottom, but `<div class="overflow-y-auto" style={{height:
    // "100vh"}}>` hides its children behind an internal scrollbar — only the
    // first child appears in the preview. Forcing `overflow-y: visible` lets
    // children paint outside the parent's box; block flow positions them at
    // their natural offsets so document.body extends to include them. `auto`
    // and `scroll` only — `hidden` and `clip` express intentional clipping (UI
    // chrome, rounded-corner masks) we shouldn't undo.
    const unscrollY = (el) => {
        if (unscrolled.has(el))
            return;
        const computedStyle = window.getComputedStyle(el);
        const ovY = computedStyle.overflowY;
        if (ovY !== "auto" && ovY !== "scroll")
            return;
        unscrolled.add(el);
        el.style.setProperty("overflow-y", "visible", "important");
    };
    const unscrollSubtree = (root) => {
        unscrollY(root);
        root.querySelectorAll("*").forEach(unscrollY);
    };
    // Rewrites vh-bearing properties on a single element's inline style. Covers
    // React's `style={{ height: "100vh" }}` and imperative `el.style.h = ".vh"`
    // — both bypass <style> tags and CSSOM. Per-property setProperty preserves
    // `!important`. Snapshotting prop names first guards against iteration-time
    // mutation of `style.length`.
    const rewriteInlineStyle = (el) => {
        const style = el.style;
        if (!style || style.length === 0)
            return;
        const props = [];
        for (let i = 0; i < style.length; i++) {
            const prop = style[i];
            if (prop)
                props.push(prop);
        }
        for (const prop of props) {
            const value = style.getPropertyValue(prop);
            if (!value || value.indexOf("vh") === -1)
                continue;
            const next = rewrite(value);
            if (next !== value)
                style.setProperty(prop, next, style.getPropertyPriority(prop));
        }
    };
    const neutralize = () => {
        document.querySelectorAll("style").forEach((el) => {
            watchStyleEl(el);
            if (processedStyles.has(el))
                return;
            processedStyles.add(el);
            const text = el.textContent;
            if (!text || text.indexOf("vh") === -1)
                return;
            const next = rewrite(text);
            if (next !== text)
                el.textContent = next;
        });
        for (let i = 0; i < document.styleSheets.length; i++) {
            const sheet = document.styleSheets[i];
            if (!sheet)
                continue;
            let rules;
            try {
                rules = sheet.cssRules;
            }
            catch {
                continue; // CORS-protected
            }
            if (processedSheets.get(sheet) === rules.length)
                continue;
            rewriteVhInRules(rules, rewrite);
            processedSheets.set(sheet, rules.length);
        }
        // Initial sweep of inline `style="...vh..."` attributes already in the DOM
        // at freeze time. Future inline-style mutations (React commits, motion
        // libraries, imperative assignments) are picked up by inlineStyleObserver.
        document.querySelectorAll('[style*="vh"]').forEach(rewriteInlineStyle);
        // Defeat internal scrollers — same dual coverage (initial sweep here,
        // subtree additions in inlineStyleObserver).
        if (document.body)
            unscrollSubtree(document.body);
    };
    const debouncer = createDebouncer(neutralize, NEUTRALIZE_DEBOUNCE_MS);
    const debouncedNeutralize = debouncer.trigger;
    cleanups.push(debouncer.cancel);
    const watchStyleEl = (el) => {
        if (watchedStyles.has(el))
            return;
        watchedStyles.add(el);
        const obs = new MutationObserver(() => {
            processedStyles.delete(el);
            debouncedNeutralize();
        });
        obs.observe(el, { characterData: true, childList: true, subtree: true });
        styleObservers.add(obs);
    };
    cleanups.push(() => {
        for (const obs of styleObservers)
            obs.disconnect();
        styleObservers.clear();
    });
    debouncedNeutralize();
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", debouncedNeutralize);
        cleanups.push(() => document.removeEventListener("DOMContentLoaded", debouncedNeutralize));
    }
    window.addEventListener("load", debouncedNeutralize);
    cleanups.push(() => window.removeEventListener("load", debouncedNeutralize));
    const headObserver = new MutationObserver((mutations) => {
        for (const m of mutations) {
            if (containsStylesheetNode(m.addedNodes) || containsStylesheetNode(m.removedNodes)) {
                debouncedNeutralize();
                return;
            }
        }
    });
    cleanups.push(() => headObserver.disconnect());
    const attachHeadObserver = () => {
        if (document.head)
            headObserver.observe(document.head, { childList: true, subtree: false });
    };
    if (document.head) {
        attachHeadObserver();
    }
    else {
        document.addEventListener("DOMContentLoaded", attachHeadObserver);
        cleanups.push(() => document.removeEventListener("DOMContentLoaded", attachHeadObserver));
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
    const scanSubtreeForInlineVh = (node) => {
        if (!(node instanceof Element))
            return;
        const attr = node.getAttribute("style");
        if (attr && attr.indexOf("vh") !== -1)
            rewriteInlineStyle(node);
        node.querySelectorAll('[style*="vh"]').forEach(rewriteInlineStyle);
        // New subtrees may introduce overflow-y: auto|scroll containers (route
        // changes, conditional UI). Catch them here too.
        unscrollSubtree(node);
    };
    const inlineStyleObserver = new MutationObserver((mutations) => {
        for (const m of mutations) {
            if (m.type === "attributes") {
                const target = m.target;
                if (!(target instanceof Element))
                    continue;
                const attr = target.getAttribute("style");
                if (!attr || attr.indexOf("vh") === -1)
                    continue;
                rewriteInlineStyle(target);
            }
            else if (m.type === "childList") {
                for (let i = 0; i < m.addedNodes.length; i++) {
                    const node = m.addedNodes[i];
                    if (node)
                        scanSubtreeForInlineVh(node);
                }
            }
        }
    });
    cleanups.push(() => inlineStyleObserver.disconnect());
    const attachInlineStyleObserver = () => {
        const root = document.documentElement;
        if (!root)
            return;
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
function formatVhFactor(value) {
    return String(Number((parseFloat(value) / 100).toFixed(6)));
}
function rewriteVhInRules(rules, rewrite) {
    for (let i = 0; i < rules.length; i++) {
        const rule = rules[i];
        if (!rule)
            continue;
        if (rule.cssRules)
            rewriteVhInRules(rule.cssRules, rewrite);
        const style = rule.style;
        if (!style)
            continue;
        for (let j = 0; j < style.length; j++) {
            const prop = style[j];
            if (!prop)
                continue;
            const value = style.getPropertyValue(prop);
            if (!value || value.indexOf("vh") === -1)
                continue;
            const next = rewrite(value);
            if (next !== value)
                style.setProperty(prop, next, style.getPropertyPriority(prop));
        }
    }
}
function containsStylesheetNode(nodes) {
    for (let i = 0; i < nodes.length; i++) {
        const node = nodes[i];
        if (node instanceof HTMLStyleElement || node instanceof HTMLLinkElement)
            return true;
    }
    return false;
}
function measureContentHeight() {
    const scrollHeight = Math.max(document.documentElement.scrollHeight, document.body?.scrollHeight ?? 0);
    const referenceVhBase = readReferenceVhBase();
    // Excludes `body.clientHeight`: it grows with content, which makes
    // viewportBottom land at the document bottom and trips the stretched-
    // container heuristic on the last section. `referenceVhBase` keeps the
    // h-screen-wrapper case covered when the iframe is shorter than 100vh.
    const viewportHeight = Math.max(window.innerHeight || 0, document.documentElement.clientHeight, referenceVhBase);
    const contentBottom = measureElementContentBottom(viewportHeight);
    if (contentBottom > 0)
        return Math.ceil(Math.max(contentBottom, referenceVhBase));
    return Math.ceil(Math.max(scrollHeight, referenceVhBase));
}
function readReferenceVhBase() {
    const value = document.documentElement.style.getPropertyValue(REFERENCE_VH_BASE_VAR);
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? parsed : 0;
}
function measureElementContentBottom(viewportHeight) {
    if (!document.body)
        return 0;
    const elements = [document.body, ...Array.from(document.body.querySelectorAll("*"))];
    const contentBottoms = new WeakMap();
    const viewportBottom = window.scrollY + viewportHeight;
    for (let i = elements.length - 1; i >= 0; i--) {
        const el = elements[i];
        if (!el)
            continue;
        const childContentBottom = readChildrenContentBottom(el, contentBottoms);
        const metrics = readElementMetrics(el);
        const selfBottom = isViewportStretchedContainer(metrics, childContentBottom, viewportHeight, viewportBottom)
            ? 0
            : metrics.bottom;
        contentBottoms.set(el, Math.max(childContentBottom, selfBottom));
    }
    return contentBottoms.get(document.body) ?? 0;
}
function readChildrenContentBottom(el, contentBottoms) {
    let childContentBottom = 0;
    for (let i = 0; i < el.children.length; i++) {
        const child = el.children[i];
        if (!child)
            continue;
        childContentBottom = Math.max(childContentBottom, contentBottoms.get(child) ?? 0);
    }
    return childContentBottom;
}
function readElementMetrics(el) {
    const computedStyle = window.getComputedStyle(el);
    if (isOutOfFlowDecoration(computedStyle))
        return { bottom: 0, height: 0 };
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0)
        return { bottom: 0, height: 0 };
    return {
        bottom: rect.bottom + window.scrollY + readMarginBottom(computedStyle),
        height: rect.height,
    };
}
function readMarginBottom(computedStyle) {
    const marginBottom = parseFloat(computedStyle.marginBottom);
    return Number.isFinite(marginBottom) ? marginBottom : 0;
}
function isOutOfFlowDecoration(computedStyle) {
    if (computedStyle.position === "fixed")
        return true;
    return computedStyle.position === "absolute" && computedStyle.pointerEvents === "none";
}
// A "stretched container" spans the full viewport top-to-bottom. Requires
// BOTH `bottom ≈ viewportBottom` AND `height ≈ viewportHeight` — otherwise an
// in-flow section that just happens to end at viewportBottom (e.g. when the
// iframe has been content-sized to the previous measurement) gets falsely
// filtered, undermeasuring the page.
function isViewportStretchedContainer(metrics, childBottom, viewportHeight, viewportBottom) {
    return (childBottom > 0 &&
        Math.abs(metrics.bottom - viewportBottom) <= 1 &&
        Math.abs(metrics.height - viewportHeight) <= 1 &&
        metrics.bottom - childBottom > 8);
}
function createDebouncer(fn, delayMs) {
    let timer;
    return {
        trigger: () => {
            if (timer !== undefined)
                window.clearTimeout(timer);
            timer = window.setTimeout(fn, delayMs);
        },
        cancel: () => {
            if (timer !== undefined) {
                window.clearTimeout(timer);
                timer = undefined;
            }
        },
    };
}
//# sourceMappingURL=page-height-bridge.js.map