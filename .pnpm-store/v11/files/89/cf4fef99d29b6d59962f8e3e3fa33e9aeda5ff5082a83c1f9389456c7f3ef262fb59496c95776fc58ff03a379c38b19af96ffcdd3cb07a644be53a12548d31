import type { InlineEditHost, InlineEditController } from "./types.js";
import {
  injectFocusOutlineCSS,
  removeFocusOutlineCSS,
  selectText,
  shouldEnterInlineEditingMode,
  isStaticArrayTextElement,
} from "./dom-utils.js";
import { PLUGIN_ELEMENT_ATTR, readElementClasses } from "../../injections/utils.js";

const DEBOUNCE_MS = 500;

export function createInlineEditController(
  host: InlineEditHost
): InlineEditController {
  let currentEditingElement: HTMLElement | null = null;
  let debouncedSendTimeout: ReturnType<typeof setTimeout> | null = null;
  let enabled = false;
  const listenerAbortControllers = new WeakMap<HTMLElement, AbortController>();

  // --- Private helpers ---

  const repositionOverlays = () => {
    const selectedId = host.getSelectedElementId();
    if (!selectedId) return;
    const elements = host.findElementsById(selectedId);
    const overlays = host.getSelectedOverlays();
    overlays.forEach((overlay, i) => {
      if (i < elements.length && elements[i]) {
        host.positionOverlay(overlay, elements[i]);
      }
    });
  };

  const reportEdit = (element: HTMLElement) => {
    const originalContent = element.dataset.originalTextContent;
    const newContent = element.textContent;

    const rect = element.getBoundingClientRect();

    const message: Record<string, unknown> = {
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

  const debouncedReport = (element: HTMLElement) => {
    if (debouncedSendTimeout) clearTimeout(debouncedSendTimeout);
    debouncedSendTimeout = setTimeout(() => reportEdit(element), DEBOUNCE_MS);
  };

  const onTextInput = (element: HTMLElement) => {
    repositionOverlays();
    debouncedReport(element);
  };

  const handleInputEvent = function (this: HTMLElement) {
    onTextInput(this);
  };

  const makeEditable = (element: HTMLElement) => {
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

  const makeNonEditable = (element: HTMLElement) => {
    const abortController = listenerAbortControllers.get(element);
    if (abortController) {
      abortController.abort();
      listenerAbortControllers.delete(element);
    }

    if (!element.isConnected) return;

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
    set enabled(value: boolean) {
      enabled = value;
    },

    isEditing() {
      return currentEditingElement !== null;
    },

    getCurrentElement() {
      return currentEditingElement;
    },

    canEdit(element: Element) {
      return shouldEnterInlineEditingMode(element);
    },

    startEditing(element: HTMLElement) {
      currentEditingElement = element;

      host.getSelectedOverlays().forEach((o) => {
        o.style.display = "none";
      });

      makeEditable(element);

      window.parent.postMessage(
        {
          type: "content-editing-started",
          visualSelectorId: host.getSelectedElementId(),
        },
        "*"
      );
    },

    stopEditing() {
      if (!currentEditingElement) return;

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

      window.parent.postMessage(
        {
          type: "content-editing-ended",
          visualSelectorId: host.getSelectedElementId(),
        },
        "*"
      );

      currentEditingElement = null;
    },

    markElementsSelected(elements: Element[]) {
      elements.forEach((el) => {
        if (el instanceof HTMLElement) {
          el.dataset.selected = "true";
        }
      });
    },

    clearSelectedMarks(elementId: string | null) {
      if (!elementId) return;
      host.findElementsById(elementId).forEach((el) => {
        if (el instanceof HTMLElement) {
          delete el.dataset.selected;
        }
      });
    },

    handleToggleMessage(data: { dataSourceLocation: string; inlineEditingMode: boolean }) {
      if (!enabled) return;

      const elements = host.findElementsById(data.dataSourceLocation);
      if (elements.length === 0 || !(elements[0] instanceof HTMLElement)) return;

      const element = elements[0];

      if (data.inlineEditingMode) {
        if (!shouldEnterInlineEditingMode(element)) return;

        // Select the element first if not already selected
        if (host.getSelectedElementId() !== data.dataSourceLocation) {
          this.stopEditing();
          host.clearSelection();
          this.markElementsSelected(elements);
          host.createSelectionOverlays(elements, data.dataSourceLocation);
        }
        this.startEditing(element);
      } else {
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
