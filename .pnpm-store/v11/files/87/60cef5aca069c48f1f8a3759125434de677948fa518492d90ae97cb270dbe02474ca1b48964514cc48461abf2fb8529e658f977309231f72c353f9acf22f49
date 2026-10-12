/** DOM utilities for the layer-dropdown module */
import type { LayerInfo } from "./types.js";
/** Apply a style map to an element */
export declare function applyStyles(element: HTMLElement, styles: Record<string, string>): void;
/** Display name for a layer — just the real tag name */
export declare function getLayerDisplayName(layer: LayerInfo): string;
/**
 * Collect instrumented descendants up to `maxDepth` instrumented nesting levels.
 * Non-instrumented wrappers are walked through without counting toward depth.
 * Results are in DOM order.
 * When `startDepth` is provided, assigns `depth` to each item during collection.
 */
export declare function getInstrumentedDescendants(parent: Element, maxDepth: number, startDepth?: number): LayerInfo[];
/**
 * Build the layer chain for the dropdown:
 *
 *   Parents  – up to MAX_PARENT_DEPTH instrumented ancestors, outer → inner.
 *   Siblings – instrumented children of the immediate parent, at the same depth.
 *   Current  – the selected element (highlighted), with children expanded.
 *   Children – instrumented descendants within MAX_CHILD_DEPTH levels, DOM order.
 *
 * Each item carries a `depth` for visual indentation.
 */
export declare function buildLayerChain(selectedElement: Element): LayerInfo[];
//# sourceMappingURL=utils.d.ts.map