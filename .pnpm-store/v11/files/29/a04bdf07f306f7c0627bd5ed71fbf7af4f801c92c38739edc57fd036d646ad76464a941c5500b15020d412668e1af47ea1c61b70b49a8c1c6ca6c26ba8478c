// auto-popup-suppressor — hides auto-opening modal popups in the canvas
// preview iframe so the page snapshot isn't obscured by overlays the user
// didn't intend to capture. Driven by `{ type: "suppress-auto-popups" }` from
// the parent; inert until that arrives.
//
// Two-stage heuristic:
//
//   1. BACKDROP MATCH — element must be `position: fixed`, cover ≥90% of the
//      viewport on both axes, have a popup-level z-index, and show backdrop-
//      like styles (translucent background OR backdrop-filter). This is the
//      modal-overlay fingerprint.
//
//   2. PANEL SWEEP — once we've hidden any backdrop, sweep the whole document
//      for fixed/high-z elements whose bbox falls in a "modal-shaped" band
//      (15–95% on both axes). Picks up the dialog content panel even when it
//      isn't a direct sibling of the overlay (Radix wraps content in
//      FocusScope + DismissableLayer + focus-guards; shadcn's portals use
//      `asChild`, so structural relationships vary).
//
// A sticky `backdropEverDetected` flag keeps the panel-shape check live for
// later MutationObserver ticks — Content sometimes mounts in a different
// batch than its Overlay.
//
// Why the percentage gates aren't based on window.innerHeight: the canvas
// iframe is auto-sized to the document content (e.g. 4958px), so innerHeight
// is the document height, not the visible viewport. page-height-bridge sets
// `--base44-reference-vh-base` to the canvas tile height — the viewport the
// user actually sees — and that's what our gates use.
const SUPPRESSED_ATTR = "data-base44-suppressed-popup";
const REFERENCE_VH_BASE_VAR = "--base44-reference-vh-base";
const FULL_VIEWPORT_RATIO = 0.9;
const MODAL_PANEL_MIN_RATIO = 0.15;
const MODAL_PANEL_MAX_RATIO = 0.95;
const POPUP_Z_INDEX_THRESHOLD = 40;
// ── Public API ──────────────────────────────────────────────────────────────
export function createAutoPopupSuppressorController() {
    let observer = null;
    let domReadyHandler = null;
    let active = false;
    // Once a backdrop has been seen, modal-shaped panels appearing in later
    // mutation batches are also hidden. Without this, a Content node that
    // mounts after its Overlay's batch wouldn't be matched in-flight.
    let backdropEverDetected = false;
    // Single decision per element. One getComputedStyle call — backdrop and
    // panel checks share the position/z-index preconditions. Without sharing,
    // every non-matching node in a React commit's added subtree would pay for
    // two style recalcs, which is the MutationObserver hot path.
    const classify = (el, vp) => {
        if (!(el instanceof HTMLElement))
            return;
        if (el.hasAttribute(SUPPRESSED_ATTR))
            return;
        const style = window.getComputedStyle(el);
        if (style.position !== "fixed")
            return;
        if (!hasPopupZIndex(style))
            return;
        if (coversFullViewport(el, vp) && hasBackdropLook(el, style)) {
            hideBackdrop(el);
            return;
        }
        if (backdropEverDetected && hasModalShapeBbox(el, vp)) {
            applyHide(el);
        }
    };
    const hideBackdrop = (el) => {
        if (el.hasAttribute(SUPPRESSED_ATTR))
            return;
        applyHide(el);
        backdropEverDetected = true;
        sweepDocumentForModalPanels(viewportForGates());
    };
    const scanSubtree = (root, vp) => {
        classify(root, vp);
        const descendants = root.querySelectorAll(`*:not([${SUPPRESSED_ATTR}])`);
        for (let i = 0; i < descendants.length; i++) {
            const el = descendants[i];
            if (el)
                classify(el, vp);
        }
    };
    const attachObserver = () => {
        if (observer)
            return;
        // viewportForGates is read once per mutation batch, not per added node —
        // a busy React commit can deliver dozens of added subtrees in one tick.
        observer = new MutationObserver((mutations) => {
            const vp = viewportForGates();
            for (const m of mutations) {
                if (m.type !== "childList")
                    continue;
                for (let i = 0; i < m.addedNodes.length; i++) {
                    const node = m.addedNodes[i];
                    if (node instanceof Element)
                        scanSubtree(node, vp);
                }
            }
        });
        observer.observe(document.documentElement, { childList: true, subtree: true });
    };
    const start = () => {
        if (!document.body)
            return;
        scanSubtree(document.body, viewportForGates());
        attachObserver();
    };
    return {
        suppress: () => {
            if (active)
                return;
            active = true;
            if (document.body) {
                start();
            }
            else {
                domReadyHandler = () => {
                    domReadyHandler = null;
                    start();
                };
                document.addEventListener("DOMContentLoaded", domReadyHandler);
            }
        },
        teardown: () => {
            active = false;
            backdropEverDetected = false;
            if (observer) {
                observer.disconnect();
                observer = null;
            }
            if (domReadyHandler) {
                document.removeEventListener("DOMContentLoaded", domReadyHandler);
                domReadyHandler = null;
            }
        },
    };
}
// ── Document-wide panel sweep ───────────────────────────────────────────────
// Triggered once per backdrop hide. Walks the whole document for unhidden
// fixed/high-z elements whose bbox falls inside the modal-shape band — picks
// up content panels regardless of how they're nested or which portal they
// went through.
function sweepDocumentForModalPanels(vp) {
    if (!document.body)
        return;
    if (vp.vw <= 0 || vp.vh <= 0)
        return;
    const candidates = document.body.querySelectorAll(`*:not([${SUPPRESSED_ATTR}])`);
    for (let i = 0; i < candidates.length; i++) {
        const el = candidates[i];
        if (el && isModalPanel(el, vp))
            applyHide(el);
    }
}
function isModalPanel(el, vp) {
    if (el.hasAttribute(SUPPRESSED_ATTR))
        return false;
    const style = window.getComputedStyle(el);
    if (style.position !== "fixed")
        return false;
    if (!hasPopupZIndex(style))
        return false;
    return hasModalShapeBbox(el, vp);
}
// ── Gate predicates ─────────────────────────────────────────────────────────
function coversFullViewport(el, vp) {
    if (vp.vw <= 0 || vp.vh <= 0)
        return false;
    const rect = el.getBoundingClientRect();
    return (rect.width >= vp.vw * FULL_VIEWPORT_RATIO &&
        rect.height >= vp.vh * FULL_VIEWPORT_RATIO);
}
// "Modal-shaped" = small enough not to be a sidebar/full-screen overlay
// (≤95% on both axes), big enough not to be a nav/footer/toast (≥15% on both
// axes). Calibrated against shadcn Dialog content (≈25–50% × 30–50%), top
// nav (height fails ≤15%), sidebar (height fails ≥95%), toast (height fails
// ≤15%).
function hasModalShapeBbox(el, vp) {
    const rect = el.getBoundingClientRect();
    return (rect.width >= vp.vw * MODAL_PANEL_MIN_RATIO &&
        rect.height >= vp.vh * MODAL_PANEL_MIN_RATIO &&
        rect.width <= vp.vw * MODAL_PANEL_MAX_RATIO &&
        rect.height <= vp.vh * MODAL_PANEL_MAX_RATIO);
}
function hasPopupZIndex(style) {
    const z = parseInt(style.zIndex, 10);
    return Number.isFinite(z) && z >= POPUP_Z_INDEX_THRESHOLD;
}
// True if the element looks like a modal backdrop: translucent fill OR a
// backdrop-filter (e.g. blur). Also returns true if the element's own bg is
// transparent but a fixed/high-z descendant paints the backdrop — covers
// dialog wrappers that delegate the backdrop to a child element.
function hasBackdropLook(el, style) {
    if (isTranslucent(style.backgroundColor))
        return true;
    if (style.backdropFilter && style.backdropFilter !== "none")
        return true;
    const descendants = el.querySelectorAll("*");
    for (let i = 0; i < descendants.length; i++) {
        const child = descendants[i];
        if (!child)
            continue;
        const cs = window.getComputedStyle(child);
        if (cs.position !== "fixed" && cs.position !== "absolute")
            continue;
        if (!hasPopupZIndex(cs))
            continue;
        if (isTranslucent(cs.backgroundColor))
            return true;
        if (cs.backdropFilter && cs.backdropFilter !== "none")
            return true;
    }
    return false;
}
function isTranslucent(color) {
    const alpha = parseAlpha(color);
    return alpha !== null && alpha > 0 && alpha < 1;
}
// Extracts the alpha channel from a computed background-color across legacy
// AND modern color syntaxes:
//
//   • `rgb(r, g, b)` / `rgba(r, g, b, a)` — legacy comma syntax.
//   • `<func>(... / a)` / `<func>(... / a%)` — modern slash-alpha (oklch,
//     oklab, lch, lab, hsl, hsla, color, modern rgb). Tailwind v4 / shadcn
//     theme tokens compute to these.
//   • A recognized color function call without explicit alpha → 1.
//
// Returns null when unrecognized; callers treat null as "not a backdrop".
function parseAlpha(value) {
    if (!value)
        return null;
    const comma = /^rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(?:,\s*([0-9.]+)\s*)?\)$/.exec(value);
    if (comma)
        return comma[1] === undefined ? 1 : parseFloat(comma[1]);
    const slash = /\/\s*([0-9.]+)(%?)\s*\)$/.exec(value);
    if (slash) {
        const n = parseFloat(slash[1]);
        return slash[2] === "%" ? n / 100 : n;
    }
    if (/^[a-z]+\s*\(/.test(value))
        return 1;
    return null;
}
// ── Viewport + DOM ops ──────────────────────────────────────────────────────
// Viewport dimensions used for percentage gates. Width comes from
// `innerWidth` (unaffected by canvas auto-fit). Height prefers the reference
// vh set by page-height-bridge — without that, after the iframe auto-resizes
// to document content, `innerHeight` is the document height and every modal
// panel falls below the 15% floor.
function viewportForGates() {
    const vw = window.innerWidth || document.documentElement.clientWidth || 0;
    const refStr = document.documentElement.style.getPropertyValue(REFERENCE_VH_BASE_VAR);
    const ref = parseFloat(refStr);
    const vh = Number.isFinite(ref) && ref > 0
        ? ref
        : (window.innerHeight || document.documentElement.clientHeight || 0);
    return { vw, vh };
}
function applyHide(el) {
    if (el.hasAttribute(SUPPRESSED_ATTR))
        return;
    el.setAttribute(SUPPRESSED_ATTR, "1");
    el.style.setProperty("display", "none", "important");
}
//# sourceMappingURL=auto-popup-suppressor.js.map