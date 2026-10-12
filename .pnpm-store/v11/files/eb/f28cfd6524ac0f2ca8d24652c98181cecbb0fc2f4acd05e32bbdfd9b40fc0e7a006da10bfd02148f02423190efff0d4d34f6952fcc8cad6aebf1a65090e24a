const LABEL_HEIGHT = 27;

/**
 * Positions an element-tag label relative to its highlighted overlay.
 *
 * Strategy (in priority order):
 *  1. If the element is near the viewport top AND tall enough (>= 2x label height),
 *     place the label **inside** the element at the top-left.
 *  2. If the element is near the viewport top but too short, place the label
 *     **below** the element.
 *  3. Otherwise, place the label **above** the element (default).
 *
 * For full-width elements (spanning nearly the entire viewport), the left offset
 * is nudged inward (6px) to prevent clipping against the viewport edge.
 *
 * @param label - The label div to position (style.top and style.left are set).
 * @param rect  - The bounding client rect of the highlighted element.
 */
export function positionLabel(label: HTMLDivElement, rect: DOMRect): void {
  const nearTop = rect.top < LABEL_HEIGHT;
  const tallEnough = rect.height >= LABEL_HEIGHT * 2;
  const isFullWidth = rect.width >= window.innerWidth - 4;
  const edgeLeft = isFullWidth ? "8px" : "-2px";
  const insideLeft = isFullWidth ? "8px" : "4px";

  if (nearTop && tallEnough) {
    label.style.top = "2px";
    label.style.left = insideLeft;
  } else if (nearTop) {
    label.style.top = `${rect.height + 2}px`;
    label.style.left = edgeLeft;
  } else {
    label.style.top = `-${LABEL_HEIGHT}px`;
    label.style.left = edgeLeft;
  }
}

/** Check if an element has instrumentation attributes */
export function isInstrumentedElement(element: Element): boolean {
  const htmlEl = element as HTMLElement;
  return !!(
    htmlEl.dataset?.sourceLocation || htmlEl.dataset?.visualSelectorId
  );
}

/** Get the selector ID from an element's data attributes (prefers source-location) */
export function getElementSelectorId(element: Element): string | null {
  const htmlEl = element as HTMLElement;
  return (
    htmlEl.dataset?.sourceLocation ||
    htmlEl.dataset?.visualSelectorId ||
    null
  );
}

export function isImageComponent(element: Element): boolean {
  return element.hasAttribute("data-base44-image");
}

export function readVisualEditTagName(element: Element): string {
  return isImageComponent(element) ? "IMG" : element.tagName;
}

export const ALLOWED_ATTRIBUTES: string[] = ["src"];

export const PLUGIN_ELEMENT_ATTR = "data-vite-plugin-element";

/** Find elements by ID - first try data-source-location, fallback to data-visual-selector-id */
export function findElementsById(id: string | null): Element[] {
  if (!id) return [];
  const sourceElements = Array.from(
    document.querySelectorAll(`[data-source-location="${id}"]`)
  );
  if (sourceElements.length > 0) {
    return sourceElements;
  }
  return Array.from(
    document.querySelectorAll(`[data-visual-selector-id="${id}"]`)
  );
}

/**
 * Update element classes by visual selector ID.
 * Uses setAttribute instead of className to support both HTML and SVG elements.
 */
export function updateElementClasses(elements: Element[], classes: string): void {
  elements.forEach((element) => {
    element.setAttribute("class", classes);
  });
}

/** Set a single attribute on all provided elements. */
export function updateElementAttribute(elements: Element[], attribute: string, value: string, arrIndex?: number | string): void {
  if (!ALLOWED_ATTRIBUTES.includes(attribute)) {
    return;
  }

  const targetArrIndex = arrIndex != null ? String(arrIndex) : null;
  elements.forEach((element) => {
    if (
      targetArrIndex === null ||
      (element as HTMLElement).dataset.arrIndex === targetArrIndex
    ) {
      if (attribute === "src" && isImageComponent(element)) {
        element.dispatchEvent(new CustomEvent("base44:image-replace", { detail: { src: value } }));
      } else {
        element.setAttribute(attribute, value);
      }
    }
  });
}

/**
 * Read an element's classes as a plain string, safe to postMessage.
 * `element.className` is an SVGAnimatedString on SVG elements, which is not
 * structured-cloneable — posting it throws DataCloneError and the preview hangs.
 */
export function readElementClasses(element: Element): string {
  return element.getAttribute("class") ?? "";
}

/** Collect attribute values from an element for a given allowlist. */
export function collectAllowedAttributes(element: Element, allowedAttributes: string[]): Record<string, string> {
  const attributes: Record<string, string> = {};
  for (const attr of allowedAttributes) {
    const val = attr === "src" && isImageComponent(element)
      ? element.getAttribute("data-base44-image-src")
      : element.getAttribute(attr);
    if (val !== null) {
      attributes[attr] = val;
    }
  }
  return attributes;
}

/**
 * Freeze all CSS animations and transitions on the page by injecting
 * scoped styles under `[data-visual-edit-active]` and programmatically
 * finishing (or pausing) every running animation.
 *
 * Plugin-owned elements (`[data-vite-plugin-element]`) are excluded so
 * the plugin UI stays animated.
 */
export function stopAnimations(): void {
  if (document.getElementById('freeze-animations')) return;

  document.documentElement.setAttribute('data-visual-edit-active', '');

  const animStyle = document.createElement('style');
  animStyle.id = 'freeze-animations';
  animStyle.textContent = `
    [data-visual-edit-active] *:not([${PLUGIN_ELEMENT_ATTR}]):not([${PLUGIN_ELEMENT_ATTR}] *),
    [data-visual-edit-active] *:not([${PLUGIN_ELEMENT_ATTR}]):not([${PLUGIN_ELEMENT_ATTR}] *)::before,
    [data-visual-edit-active] *:not([${PLUGIN_ELEMENT_ATTR}]):not([${PLUGIN_ELEMENT_ATTR}] *)::after {
      animation-play-state: paused !important;
      transition: none !important;
    }
  `;

  const pointerStyle = document.createElement('style');
  pointerStyle.id = 'freeze-pointer-events';
  pointerStyle.textContent = `
    [data-visual-edit-active] * { pointer-events: none !important; }
    [${PLUGIN_ELEMENT_ATTR}], [${PLUGIN_ELEMENT_ATTR}] * { pointer-events: auto !important; }
  `;

  const target = document.head || document.documentElement;
  target.appendChild(animStyle);
  target.appendChild(pointerStyle);

  document.getAnimations().forEach((a) => {
    // Skip animations on plugin UI elements
    const animTarget = (a.effect as KeyframeEffect)?.target;
    if (animTarget instanceof Element && animTarget.closest(`[${PLUGIN_ELEMENT_ATTR}]`)) return;

    try {
      a.finish();  // fast-forward to end state
    } catch {
      a.pause();   // finish() throws on infinite animations — pause instead
    }
  });
}

/**
 * Resume all previously frozen animations and remove the injected
 * freeze styles.  Cleans up the `data-visual-edit-active` attribute
 * from `<html>` so scoped selectors no longer match.
 */
export function resumeAnimations(): void {
  const animStyle = document.getElementById('freeze-animations');
  if (!animStyle) return;

  animStyle.remove();
  document.getElementById('freeze-pointer-events')?.remove();
  document.documentElement.removeAttribute('data-visual-edit-active');

  document.getAnimations().forEach((a) => {
    if (a.playState === 'paused') {
      try { a.play(); } catch { /* animation target may have been removed */ }
    }
  });
}

/**
 * Hit-test the page at (`x`, `y`) and walk up the DOM to find the
 * nearest ancestor that carries instrumentation attributes
 * (`data-source-location` or `data-visual-selector-id`).
 *
 * Temporarily disables the pointer-events freeze sheet so the
 * browser's native `elementFromPoint` can reach the real target.
 */
export function findInstrumentedElement(x: number, y: number): Element | null {
  const pointerStyle = document.getElementById('freeze-pointer-events') as HTMLStyleElement | null;
  if (pointerStyle) pointerStyle.disabled = true;

  const el = document.elementFromPoint(x, y);

  if (pointerStyle) pointerStyle.disabled = false;

  return el?.closest('[data-source-location], [data-visual-selector-id]') ?? null;
}

/**
 * Resolve which element should be hovered at (`x`, `y`), skipping the
 * currently selected element.  Returns the selector ID of the hovered
 * element, or `null` if the point is empty or hits the selected element.
 */
export function resolveHoverTarget(x: number, y: number, selectedElementId: string | null): string | null {
  const element = findInstrumentedElement(x, y);
  if (!element) return null;

  const selectorId = getElementSelectorId(element);

  if (selectorId === selectedElementId) return null;

  return selectorId;
}

const VISUAL_EDIT_FONT_FACE_ID_PREFIX = "visual-edit-font-face-";

function isValidFontFaceCss(css: string): boolean {
  const trimmed = css.trim();
  if (!trimmed.startsWith("@font-face")) return false;

  if (trimmed.includes("\\")) return false; // Prevent CSS escapes

  const openBraces = (trimmed.match(/{/g) || []).length;
  const closeBraces = (trimmed.match(/}/g) || []).length;
  if (openBraces !== 1 || closeBraces !== 1 || !trimmed.endsWith("}")) return false;

  const chunks = trimmed.split(/url\(/i);
  for (let i = 1; i < chunks.length; i++) {
    const end = chunks[i]!.indexOf(")");
    if (end === -1) return false;
    const url = chunks[i]!.slice(0, end).trim().replace(/^['"]|['"]$/g, "").trim();
    if (!/^https:\/\//i.test(url)) return false;
  }

  return true;
}

export function injectFontFaceCss(id: string, css: string): void {
  if (typeof id !== "string" || !id.trim()) return;
  if (typeof css !== "string" || !isValidFontFaceCss(css)) return;

  const styleId = `${VISUAL_EDIT_FONT_FACE_ID_PREFIX}${id}`;
  if (document.getElementById(styleId)) return;

  const style = document.createElement("style");
  style.id = styleId;
  style.dataset.visualEditFontFace = "true";
  style.textContent = css;
  document.head.appendChild(style);
}
