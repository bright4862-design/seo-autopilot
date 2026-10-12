export interface CollectionInfo {
    id: string;
    references: string[];
}
export interface InlineEditHost {
    findElementsById(id: string | null): Element[];
    getSelectedElementId(): string | null;
    getSelectedOverlays(): HTMLDivElement[];
    positionOverlay(overlay: HTMLDivElement, element: Element, isSelected?: boolean): void;
    clearSelection(): void;
    createSelectionOverlays(elements: Element[], elementId: string): void;
}
export interface ToggleInlineEditData {
    dataSourceLocation: string;
    inlineEditingMode: boolean;
}
export interface InlineEditController {
    enabled: boolean;
    isEditing(): boolean;
    getCurrentElement(): HTMLElement | null;
    canEdit(element: Element): boolean;
    startEditing(element: HTMLElement): void;
    stopEditing(): void;
    markElementsSelected(elements: Element[]): void;
    clearSelectedMarks(elementId: string | null): void;
    handleToggleMessage(data: ToggleInlineEditData): void;
    cleanup(): void;
}
//# sourceMappingURL=types.d.ts.map