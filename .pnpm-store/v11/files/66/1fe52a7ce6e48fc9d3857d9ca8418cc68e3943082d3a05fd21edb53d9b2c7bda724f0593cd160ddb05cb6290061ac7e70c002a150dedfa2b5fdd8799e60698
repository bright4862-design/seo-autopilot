import { injectFocusOutlineCSS, removeFocusOutlineCSS, selectText, shouldEnterInlineEditingMode, isStaticArrayTextElement, } from "./dom-utils.js";
import { PLUGIN_ELEMENT_ATTR, readElementClasses } from "../../injections/utils.js";
const DEBOUNCE_MS = 500;
export function createInlineEditController(host) {
    let currentEditingElement = null;
    let debouncedSendTimeout = null;
    let enabled = false;
    const listenerAbortControllers = new WeakMap();
    // --- Private helpers ---
    const repositionOverlays = () => {
        const selectedId = host.getSelectedElementId();
        if (!selectedId)
            return;
        const elements = host.findElementsById(selectedId);
        const overlays = host.getSelectedOverlays();
        overlays.forEach((overlay, i) => {
            if (i < elements.length && elements[i]) {
                host.positionOverlay(overlay, elements[i]);
            }
        });
    };
    const reportEdit = (element) => {
        const originalContent = element.dataset.originalTextContent;
        const newContent = element.textContent;
        const rect = element.getBoundingClientRect();
        const message = {
            type: "inline-edit",
            elementInfo: {
                tagName: element.tagName,
                classes: readElementClasses(element),
                visualSelectorId: host.getSelectedElementId(),
                content: newContent,
                dataSourceLocation: element.dataset.sourceLocation,
                isDynamicContent: element.dataset.dynamicContent === "true",
                linenumber: element.dataset.linenumber,
                filename: element.dataset.filename,
                position: {
                    top: rect.top,
                    left: rect.left,
                    right: rect.right,
                    bottom: rect.bottom,
                    width: rect.width,
                    height: rect.height,
                    centerX: rect.left + rect.width / 2,
                    centerY: rect.top + rect.height / 2,
                },
            },
            originalContent,
            newContent,
        };
        if (isStaticArrayTextElement(element)) {
            message.arrIndex = element.dataset.arrIndex;
            message.arrVariableName = element.dataset.arrVariableName;
            message.arrField = element.dataset.arrField;
        }
        window.parent.postMessage(message, "*");
        element.dataset.originalTextContent = newContent || "";
    };
    const debouncedReport = (element) => {
        if (debouncedSendTimeout)
            clearTimeout(debouncedSendTimeout);
        debouncedSendTimeout = setTimeout(() => reportEdit(element), DEBOUNCE_MS);
    };
    const onTextInput = (element) => {
        repositionOverlays();
        debouncedReport(element);
    };
    const handleInputEvent = function () {
        onTextInput(this);
    };
    const makeEditable = (element) => {
        injectFocusOutlineCSS();
        element.dataset.originalTextContent = element.textContent || "";
        element.dataset.originalCursor = element.style.cursor;
        element.contentEditable = "true";
        element.setAttribute(PLUGIN_ELEMENT_ATTR, "true");
        const abortController = new AbortController();
        listenerAbortControllers.set(element, abortController);
        element.addEventListener("input", handleInputEvent, {
            signal: abortController.signal,
        });
        element.style.cursor = "text";
        selectText(element);
        setTimeout(() => {
            if (element.isConnected) {
                element.focus();
            }
        }, 0);
    };
    const makeNonEditable = (element) => {
        const abortController = listenerAbortControllers.get(element);
        if (abortController) {
            abortController.abort();
            listenerAbortControllers.delete(element);
        }
        if (!element.isConnected)
            return;
        removeFocusOutlineCSS();
        element.contentEditable = "false";
        element.removeAttribute(PLUGIN_ELEMENT_ATTR);
        delete element.dataset.originalTextContent;
        if (element.dataset.originalCursor !== undefined) {
            element.style.cursor = element.dataset.originalCursor;
            delete element.dataset.originalCursor;
        }
    };
    // --- Public API ---
    return {
        get enabled() {
            return enabled;
        },
        set enabled(value) {
            enabled = value;
        },
        isEditing() {
            return currentEditingElement !== null;
        },
        getCurrentElement() {
            return currentEditingElement;
        },
        canEdit(element) {
            return shouldEnterInlineEditingMode(element);
        },
        startEditing(element) {
            currentEditingElement = element;
            host.getSelectedOverlays().forEach((o) => {
                o.style.display = "none";
            });
            makeEditable(element);
            window.parent.postMessage({
                type: "content-editing-started",
                visualSelectorId: host.getSelectedElementId(),
            }, "*");
        },
        stopEditing() {
            if (!currentEditingElement)
                return;
            if (debouncedSendTimeout) {
                clearTimeout(debouncedSendTimeout);
                debouncedSendTimeout = null;
            }
            const element = currentEditingElement;
            makeNonEditable(element);
            host.getSelectedOverlays().forEach((o) => {
                o.style.display = "";
            });
            repositionOverlays();
            window.parent.postMessage({
                type: "content-editing-ended",
                visualSelectorId: host.getSelectedElementId(),
            }, "*");
            currentEditingElement = null;
        },
        markElementsSelected(elements) {
            elements.forEach((el) => {
                if (el instanceof HTMLElement) {
                    el.dataset.selected = "true";
                }
            });
        },
        clearSelectedMarks(elementId) {
            if (!elementId)
                return;
            host.findElementsById(elementId).forEach((el) => {
                if (el instanceof HTMLElement) {
                    delete el.dataset.selected;
                }
            });
        },
        handleToggleMessage(data) {
            if (!enabled)
                return;
            const elements = host.findElementsById(data.dataSourceLocation);
            if (elements.length === 0 || !(elements[0] instanceof HTMLElement))
                return;
            const element = elements[0];
            if (data.inlineEditingMode) {
                if (!shouldEnterInlineEditingMode(element))
                    return;
                // Select the element first if not already selected
                if (host.getSelectedElementId() !== data.dataSourceLocation) {
                    this.stopEditing();
                    host.clearSelection();
                    this.markElementsSelected(elements);
                    host.createSelectionOverlays(elements, data.dataSourceLocation);
                }
                this.startEditing(element);
            }
            else {
                if (currentEditingElement === element) {
                    this.stopEditing();
                }
            }
        },
        cleanup() {
            this.stopEditing();
        },
    };
}
//# sourceMappingURL=controller.js.map