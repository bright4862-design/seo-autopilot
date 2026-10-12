/** Controller that encapsulates layer-dropdown integration logic */

import { readVisualEditTagName, getElementSelectorId } from "../utils.js";
import { buildLayerChain } from "./utils.js";
import {
  enhanceLabelWithChevron,
  showDropdown,
  closeDropdown,
  isDropdownOpen,
} from "./dropdown-ui.js";
import type { LayerInfo, LayerControllerConfig, LayerController } from "./types.js";

export function createLayerController(config: LayerControllerConfig): LayerController {
  let layerPreviewOverlay: HTMLDivElement | null = null;
  let escapeHandler: ((e: KeyboardEvent) => void) | null = null;
  let dropdownSourceLayer: LayerInfo | null = null;

  const clearLayerPreview = () => {
    if (layerPreviewOverlay && layerPreviewOverlay.parentNode) {
      layerPreviewOverlay.remove();
    }
    layerPreviewOverlay = null;
  };

  const showLayerPreview = (layer: LayerInfo) => {
    clearLayerPreview();
    if (getElementSelectorId(layer.element) === config.getSelectedElementId()) return;

    layerPreviewOverlay = config.createPreviewOverlay(layer.element);
  };

  const selectLayer = (layer: LayerInfo) => {
    clearLayerPreview();
    closeDropdown();
    if (escapeHandler) {
      document.removeEventListener("keydown", escapeHandler, true);
      escapeHandler = null;
    }
    dropdownSourceLayer = null;

    const firstOverlay = config.selectElement(layer.element);
    attachToOverlay(firstOverlay, layer.element);
  };

  const restoreSelection = () => {
    if (escapeHandler) {
      document.removeEventListener("keydown", escapeHandler, true);
      escapeHandler = null;
    }
    if (dropdownSourceLayer) {
      selectLayer(dropdownSourceLayer);
      dropdownSourceLayer = null;
    }
  };

  const handleLabelClick = (e: MouseEvent, label: HTMLDivElement, element: Element, layers: LayerInfo[], currentId: string | null) => {
    e.stopPropagation();
    e.preventDefault();
    if (isDropdownOpen()) {
      closeDropdown();
      restoreSelection();
    } else {
      dropdownSourceLayer = {
        element,
        tagName: readVisualEditTagName(element).toLowerCase(),
        selectorId: currentId,
      };
      config.onDeselect();

      escapeHandler = (ev: KeyboardEvent) => {
        if (ev.key === "Escape") {
          ev.stopPropagation();
          closeDropdown();
          restoreSelection();
        }
      };
      document.addEventListener("keydown", escapeHandler, true);

      showDropdown(label, layers, element, { onSelect: selectLayer, onHover: showLayerPreview, onHoverEnd: clearLayerPreview });
    }
  };

  const attachToOverlay = (
    overlay: HTMLDivElement | undefined,
    element: Element
  ) => {
    if (!overlay) return;

    const label = overlay.querySelector("div") as HTMLDivElement | null;
    if (!label) return;

    const layers = buildLayerChain(element);
    if (layers.length <= 1) return;

    const currentId = getElementSelectorId(element);
    enhanceLabelWithChevron(label);

    label.addEventListener("click", (e: MouseEvent) => {
      handleLabelClick(e, label, element, layers, currentId);
    });
  };

  const cleanup = () => {
    clearLayerPreview();
    closeDropdown();
  };

  return { attachToOverlay, cleanup };
}
