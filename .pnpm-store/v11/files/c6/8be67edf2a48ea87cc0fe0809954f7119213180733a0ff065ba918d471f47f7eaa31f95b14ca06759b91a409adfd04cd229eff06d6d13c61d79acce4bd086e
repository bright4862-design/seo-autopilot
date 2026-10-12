/** Dropdown UI component for layer navigation */

import {
  DROPDOWN_CONTAINER_STYLES,
  DROPDOWN_ITEM_BASE_STYLES,
  DROPDOWN_ITEM_ACTIVE_COLOR,
  DROPDOWN_ITEM_ACTIVE_BG,
  DROPDOWN_ITEM_ACTIVE_FONT_WEIGHT,
  DROPDOWN_ITEM_HOVER_BG,
  DEPTH_INDENT_PX,
  BASE_PADDING_PX,
  CHEVRON_COLLAPSED,
  CHEVRON_EXPANDED,
  CHEVRON_ATTR,
  LAYER_DROPDOWN_ATTR,
} from "./consts.js";
import { applyStyles, getLayerDisplayName } from "./utils.js";
import type { LayerInfo, DropdownCallbacks } from "./types.js";
import { PLUGIN_ELEMENT_ATTR } from "../utils.js";

let activeDropdown: HTMLDivElement | null = null;
let activeLabel: HTMLDivElement | null = null;
let outsideMousedownHandler: ((e: MouseEvent) => void) | null = null;
let activeOnHoverEnd: (() => void) | null = null;
let activeKeydownHandler: ((e: KeyboardEvent) => void) | null = null;

function createDropdownItem(
  layer: LayerInfo,
  isActive: boolean,
  { onSelect, onHover, onHoverEnd }: DropdownCallbacks
): HTMLDivElement {
  const item = document.createElement("div");
  item.textContent = getLayerDisplayName(layer);
  applyStyles(item, DROPDOWN_ITEM_BASE_STYLES);

  const depth = layer.depth ?? 0;
  if (depth > 0) {
    item.style.paddingLeft = `${BASE_PADDING_PX + depth * DEPTH_INDENT_PX}px`;
  }

  if (isActive) {
    item.style.color = DROPDOWN_ITEM_ACTIVE_COLOR;
    item.style.backgroundColor = DROPDOWN_ITEM_ACTIVE_BG;
    item.style.fontWeight = DROPDOWN_ITEM_ACTIVE_FONT_WEIGHT;
  }

  item.addEventListener("mouseenter", () => {
    if (!isActive) item.style.backgroundColor = DROPDOWN_ITEM_HOVER_BG;
    if (onHover) onHover(layer);
  });

  item.addEventListener("mouseleave", () => {
    if (!isActive) item.style.backgroundColor = "transparent";
    if (onHoverEnd) onHoverEnd();
  });

  item.addEventListener("click", (e: MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    onSelect(layer);
  });

  return item;
}

/** Create the dropdown DOM element with layer items */
export function createDropdownElement(
  layers: LayerInfo[],
  currentElement: Element | null,
  callbacks: DropdownCallbacks
): HTMLDivElement {
  const container = document.createElement("div");
  container.setAttribute(LAYER_DROPDOWN_ATTR, "true");
  container.setAttribute(PLUGIN_ELEMENT_ATTR, "true");
  applyStyles(container, DROPDOWN_CONTAINER_STYLES);

  layers.forEach((layer) => {
    const isActive = layer.element === currentElement;
    container.appendChild(createDropdownItem(layer, isActive, callbacks));
  });

  return container;
}

/** Add chevron indicator and pointer-events to the label */
export function enhanceLabelWithChevron(label: HTMLDivElement): void {
  if (label.querySelector(`[${CHEVRON_ATTR}]`)) return;

  const chevron = document.createElement("span");
  chevron.setAttribute(CHEVRON_ATTR, "true");
  chevron.style.display = "inline-flex";
  chevron.innerHTML = CHEVRON_COLLAPSED;
  label.appendChild(chevron);

  label.style.display = "inline-flex";
  label.style.alignItems = "center";
  label.style.cursor = "pointer";
  label.style.userSelect = "none";
  label.style.whiteSpace = "nowrap";
  label.style.pointerEvents = "auto";
  label.setAttribute(LAYER_DROPDOWN_ATTR, "true");
  label.setAttribute(PLUGIN_ELEMENT_ATTR, "true");
}

function setupKeyboardNavigation(
  dropdown: HTMLDivElement,
  layers: LayerInfo[],
  currentElement: Element | null,
  { onSelect, onHover, onHoverEnd }: DropdownCallbacks
): void {
  const items = Array.from(dropdown.children) as HTMLDivElement[];
  let focusedIndex = layers.findIndex((l) => l.element === currentElement);

  const setFocusedItem = (index: number) => {
    if (focusedIndex >= 0 && focusedIndex < items.length) {
      const prev = items[focusedIndex]!;
      if (prev.style.color !== DROPDOWN_ITEM_ACTIVE_COLOR) {
        prev.style.backgroundColor = "transparent";
      }
    }
    focusedIndex = index;
    if (focusedIndex >= 0 && focusedIndex < items.length) {
      const cur = items[focusedIndex]!;
      if (cur.style.color !== DROPDOWN_ITEM_ACTIVE_COLOR) {
        cur.style.backgroundColor = DROPDOWN_ITEM_HOVER_BG;
      }
      cur.scrollIntoView({ block: "nearest" });
      if (onHover && focusedIndex >= 0 && focusedIndex < layers.length) {
        onHover(layers[focusedIndex]!);
      }
    }
  };

  activeKeydownHandler = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      e.stopPropagation();
      setFocusedItem(focusedIndex < items.length - 1 ? focusedIndex + 1 : 0);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      e.stopPropagation();
      setFocusedItem(focusedIndex > 0 ? focusedIndex - 1 : items.length - 1);
    } else if (e.key === "Enter" && focusedIndex >= 0 && focusedIndex < layers.length) {
      e.preventDefault();
      e.stopPropagation();
      if (onHoverEnd) onHoverEnd();
      onSelect(layers[focusedIndex]!);
      closeDropdown();
    }
  };
  document.addEventListener("keydown", activeKeydownHandler, true);
}

function setupOutsideClickHandler(
  dropdown: HTMLDivElement,
  label: HTMLDivElement
): void {
  let skipFirst = true;
  outsideMousedownHandler = (e: MouseEvent) => {
    if (skipFirst) { skipFirst = false; return; }
    const target = e.target as Node;
    if (!dropdown.contains(target) && target !== label) {
      closeDropdown();
    }
  };
  document.addEventListener("mousedown", outsideMousedownHandler, true);
}

/** Show the dropdown below the label element */
export function showDropdown(
  label: HTMLDivElement,
  layers: LayerInfo[],
  currentElement: Element | null,
  callbacks: DropdownCallbacks
): void {
  closeDropdown();

  const dropdown = createDropdownElement(
    layers,
    currentElement,
    {
      ...callbacks,
      onSelect: (layer) => {
        if (callbacks.onHoverEnd) callbacks.onHoverEnd();
        callbacks.onSelect(layer);
        closeDropdown();
      },
    }
  );

  const overlay = label.parentElement;
  if (!overlay) return;

  dropdown.style.top = `${label.offsetTop + label.offsetHeight + 2}px`;
  dropdown.style.left = `${label.offsetLeft}px`;

  overlay.appendChild(dropdown);
  activeDropdown = dropdown;
  activeLabel = label;
  const chevronEl = label.querySelector(`[${CHEVRON_ATTR}]`);
  if (chevronEl) {
    chevronEl.innerHTML = CHEVRON_EXPANDED;
  }
  activeOnHoverEnd = callbacks.onHoverEnd ?? null;

  setupKeyboardNavigation(dropdown, layers, currentElement, callbacks);
  setupOutsideClickHandler(dropdown, label);
}

/** Close the active dropdown and clean up listeners */
export function closeDropdown(): void {
  const chevronEl = activeLabel?.querySelector(`[${CHEVRON_ATTR}]`);
  if (chevronEl) {
    chevronEl.innerHTML = CHEVRON_COLLAPSED;
  }
  activeLabel = null;

  if (activeOnHoverEnd) {
    activeOnHoverEnd();
    activeOnHoverEnd = null;
  }

  if (activeDropdown && activeDropdown.parentNode) {
    activeDropdown.remove();
  }
  activeDropdown = null;

  if (outsideMousedownHandler) {
    document.removeEventListener("mousedown", outsideMousedownHandler, true);
    outsideMousedownHandler = null;
  }

  if (activeKeydownHandler) {
    document.removeEventListener("keydown", activeKeydownHandler, true);
    activeKeydownHandler = null;
  }
}

/** Check if a dropdown is currently visible */
export function isDropdownOpen(): boolean {
  return activeDropdown !== null;
}
