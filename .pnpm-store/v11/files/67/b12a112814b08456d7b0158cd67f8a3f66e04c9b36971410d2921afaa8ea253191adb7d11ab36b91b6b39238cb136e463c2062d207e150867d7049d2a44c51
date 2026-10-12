/** DOM utilities for the layer-dropdown module */

import { readVisualEditTagName, isInstrumentedElement, getElementSelectorId } from "../utils.js";
import { MAX_PARENT_DEPTH, MAX_CHILD_DEPTH } from "./consts.js";

import type { LayerInfo } from "./types.js";

/** Apply a style map to an element */
export function applyStyles(element: HTMLElement, styles: Record<string, string>): void {
  for (const key of Object.keys(styles)) {
    element.style.setProperty(
      key.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`),
      styles[key]!
    );
  }
}

/** Display name for a layer — just the real tag name */
export function getLayerDisplayName(layer: LayerInfo): string {
  return layer.tagName;
}

function toLayerInfo(element: Element, depth?: number): LayerInfo {
  const info: LayerInfo = {
    element,
    tagName: readVisualEditTagName(element).toLowerCase(),
    selectorId: getElementSelectorId(element),
  };
  if (depth !== undefined) info.depth = depth;
  return info;
}

/**
 * Collect instrumented descendants up to `maxDepth` instrumented nesting levels.
 * Non-instrumented wrappers are walked through without counting toward depth.
 * Results are in DOM order.
 * When `startDepth` is provided, assigns `depth` to each item during collection.
 */
export function getInstrumentedDescendants(
  parent: Element,
  maxDepth: number,
  startDepth?: number
): LayerInfo[] {
  const result: LayerInfo[] = [];

  function walk(el: Element, instrDepth: number): void {
    if (instrDepth > maxDepth) return;
    for (let i = 0; i < el.children.length; i++) {
      const child = el.children[i]!;
      if (isInstrumentedElement(child)) {
        const info: LayerInfo = {
          element: child,
          tagName: readVisualEditTagName(child).toLowerCase(),
          selectorId: getElementSelectorId(child),
        };
        if (startDepth !== undefined) {
          info.depth = startDepth + instrDepth - 1;
        }
        result.push(info);
        walk(child, instrDepth + 1);
      } else {
        walk(child, instrDepth);
      }
    }
  }

  walk(parent, 1);
  return result;
}

/** Collect instrumented ancestors from selected element up to MAX_PARENT_DEPTH (outermost first). */
function collectInstrumentedParents(selectedElement: Element): LayerInfo[] {
  const parents: LayerInfo[] = [];
  let current = selectedElement.parentElement;
  while (
    current &&
    current !== document.documentElement &&
    current !== document.body &&
    parents.length < MAX_PARENT_DEPTH
  ) {
    if (isInstrumentedElement(current)) {
      parents.push(toLayerInfo(current));
    }
    current = current.parentElement;
  }
  parents.reverse();
  return parents;
}

/** Add parents to chain with depth 0, 1, …; returns depth of selected (parents.length). */
function addParentsToChain(chain: LayerInfo[], parents: LayerInfo[]): number {
  parents.forEach((p, i) => {
    chain.push({ ...p, depth: i });
  });
  return parents.length;
}

/** Add selected element and its descendants at the given depth. */
function addSelfAndDescendantsToChain(
  chain: LayerInfo[],
  selectedElement: Element,
  selfDepth: number
): void {
  chain.push(toLayerInfo(selectedElement, selfDepth));
  const descendants = getInstrumentedDescendants(
    selectedElement,
    MAX_CHILD_DEPTH,
    selfDepth + 1
  );
  chain.push(...descendants);
}

/** Get the innermost instrumented parent's DOM element, or null if none. */
function getImmediateInstrParent(parents: LayerInfo[]): Element | null {
  return parents.at(-1)?.element ?? null;
}

/** Collect instrumented siblings of the selected element from its parent (DOM order). */
function collectSiblings(parent: Element, selectedElement: Element): LayerInfo[] {
  const siblings = getInstrumentedDescendants(parent, 1);
  if (!siblings.some((s) => s.element === selectedElement)) {
    siblings.push(toLayerInfo(selectedElement));
  }
  return siblings;
}

/** Add siblings at selfDepth, expanding children only for the selected element. */
function appendSiblingsWithSelected(
  chain: LayerInfo[],
  siblings: LayerInfo[],
  selectedElement: Element,
  selfDepth: number
): void {
  const selectedSelectorId = getElementSelectorId(selectedElement);
  const seen = new Set<string>();
  for (const sibling of siblings) {
    if (sibling.element === selectedElement) {
      addSelfAndDescendantsToChain(chain, selectedElement, selfDepth);
      if (selectedSelectorId) seen.add(selectedSelectorId);
    } else {
      const id = sibling.selectorId;
      if (id != null) {
        if (id === selectedSelectorId || seen.has(id)) continue;
        seen.add(id);
      }
      chain.push({ ...sibling, depth: selfDepth });
    }
  }
}

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
export function buildLayerChain(selectedElement: Element): LayerInfo[] {
  const parents = collectInstrumentedParents(selectedElement);
  const chain: LayerInfo[] = [];
  const selfDepth = addParentsToChain(chain, parents);

  const instrParent = getImmediateInstrParent(parents);
  if (instrParent) {
    const siblings = collectSiblings(instrParent, selectedElement);
    appendSiblingsWithSelected(chain, siblings, selectedElement, selfDepth);
  } else {
    addSelfAndDescendantsToChain(chain, selectedElement, selfDepth);
  }

  return chain;
}
