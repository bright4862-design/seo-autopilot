/** Shared types for the layer-dropdown module */
export interface LayerInfo {
    element: Element;
    tagName: string;
    selectorId: string | null;
    depth?: number;
}
export type OnLayerSelect = (layer: LayerInfo) => void;
export type OnLayerHover = (layer: LayerInfo) => void;
export type OnLayerHoverEnd = () => void;
export interface DropdownCallbacks {
    onSelect: OnLayerSelect;
    onHover?: OnLayerHover;
    onHoverEnd?: OnLayerHoverEnd;
}
export interface LayerControllerConfig {
    createPreviewOverlay: (element: Element) => HTMLDivElement;
    getSelectedElementId: () => string | null;
    selectElement: (element: Element) => HTMLDivElement | undefined;
    onDeselect: () => void;
}
export interface LayerController {
    attachToOverlay: (overlay: HTMLDivElement | undefined, element: Element) => void;
    cleanup: () => void;
}
//# sourceMappingURL=types.d.ts.map