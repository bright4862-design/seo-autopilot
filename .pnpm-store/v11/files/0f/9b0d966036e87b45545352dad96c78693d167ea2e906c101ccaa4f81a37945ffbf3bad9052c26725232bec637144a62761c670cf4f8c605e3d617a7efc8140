/** Controller that encapsulates layer-dropdown integration logic */
import { readVisualEditTagName, getElementSelectorId } from "../utils.js";
import { buildLayerChain } from "./utils.js";
import { enhanceLabelWithChevron, showDropdown, closeDropdown, isDropdownOpen, } from "./dropdown-ui.js";
export function createLayerController(config) {
    let layerPreviewOverlay = null;
    let escapeHandler = null;
    let dropdownSourceLayer = null;
    const clearLayerPreview = () => {
        if (layerPreviewOverlay && layerPreviewOverlay.parentNode) {
            layerPreviewOverlay.remove();
        }
        layerPreviewOverlay = null;
    };
    const showLayerPreview = (layer) => {
        clearLayerPreview();
        if (getElementSelectorId(layer.element) === config.getSelectedElementId())
            return;
        layerPreviewOverlay = config.createPreviewOverlay(layer.element);
    };
    const selectLayer = (layer) => {
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
    const handleLabelClick = (e, label, element, layers, currentId) => {
        e.stopPropagation();
        e.preventDefault();
        if (isDropdownOpen()) {
            closeDropdown();
            restoreSelection();
        }
        else {
            dropdownSourceLayer = {
                element,
                tagName: readVisualEditTagName(element).toLowerCase(),
                selectorId: currentId,
            };
            config.onDeselect();
            escapeHandler = (ev) => {
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
    const attachToOverlay = (overlay, element) => {
        if (!overlay)
            return;
        const label = overlay.querySelector("div");
        if (!label)
            return;
        const layers = buildLayerChain(element);
        if (layers.length <= 1)
            return;
        const currentId = getElementSelectorId(element);
        enhanceLabelWithChevron(label);
        label.addEventListener("click", (e) => {
            handleLabelClick(e, label, element, layers, currentId);
        });
    };
    const cleanup = () => {
        clearLayerPreview();
        closeDropdown();
    };
    return { attachToOverlay, cleanup };
}
//# sourceMappingURL=controller.js.map