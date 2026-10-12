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
export declare function positionLabel(label: HTMLDivElement, rect: DOMRect): void;
/** Check if an element has instrumentation attributes */
export declare function isInstrumentedElement(element: Element): boolean;
/** Get the selector ID from an element's data attributes (prefers source-location) */
export declare function getElementSelectorId(element: Element): string | null;
export declare function isImageComponent(element: Element): boolean;
export declare function readVisualEditTagName(element: Element): string;
export declare const ALLOWED_ATTRIBUTES: string[];
export declare const PLUGIN_ELEMENT_ATTR = "data-vite-plugin-element";
/** Find elements by ID - first try data-source-location, fallback to data-visual-selector-id */
export declare function findElementsById(id: string | null): Element[];
/**
 * Update element classes by visual selector ID.
 * Uses setAttribute instead of className to support both HTML and SVG elements.
 */
export declare function updateElementClasses(elements: Element[], classes: string): void;
/** Set a single attribute on all provided elements. */
export declare function updateElementAttribute(elements: Element[], attribute: string, value: string, arrIndex?: number | string): void;
/**
 * Read an element's classes as a plain string, safe to postMessage.
 * `element.className` is an SVGAnimatedString on SVG elements, which is not
 * structured-cloneable — posting it throws DataCloneError and the preview hangs.
 */
export declare function readElementClasses(element: Element): string;
/** Collect attribute values from an element for a given allowlist. */
export declare function collectAllowedAttributes(element: Element, allowedAttributes: string[]): Record<string, string>;
/**
 * Freeze all CSS animations and transitions on the page by injecting
 * scoped styles under `[data-visual-edit-active]` and programmatically
 * finishing (or pausing) every running animation.
 *
 * Plugin-owned elements (`[data-vite-plugin-element]`) are excluded so
 * the plugin UI stays animated.
 */
export declare function stopAnimations(): void;
/**
 * Resume all previously frozen animations and remove the injected
 * freeze styles.  Cleans up the `data-visual-edit-active` attribute
 * from `<html>` so scoped selectors no longer match.
 */
export declare function resumeAnimations(): void;
/**
 * Hit-test the page at (`x`, `y`) and walk up the DOM to find the
 * nearest ancestor that carries instrumentation attributes
 * (`data-source-location` or `data-visual-selector-id`).
 *
 * Temporarily disables the pointer-events freeze sheet so the
 * browser's native `elementFromPoint` can reach the real target.
 */
export declare function findInstrumentedElement(x: number, y: number): Element | null;
/**
 * Resolve which element should be hovered at (`x`, `y`), skipping the
 * currently selected element.  Returns the selector ID of the hovered
 * element, or `null` if the point is empty or hits the selected element.
 */
export declare function resolveHoverTarget(x: number, y: number, selectedElementId: string | null): string | null;
export declare function injectFontFaceCss(id: string, css: string): void;
//# sourceMappingURL=utils.d.ts.map