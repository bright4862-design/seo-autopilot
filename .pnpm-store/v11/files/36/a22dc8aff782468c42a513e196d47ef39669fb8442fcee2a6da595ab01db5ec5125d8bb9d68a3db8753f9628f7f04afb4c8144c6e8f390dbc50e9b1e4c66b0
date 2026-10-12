import { readVisualEditTagName, findElementsById, updateElementClasses, updateElementAttribute, collectAllowedAttributes, readElementClasses, ALLOWED_ATTRIBUTES, getElementSelectorId, stopAnimations, resumeAnimations, findInstrumentedElement, resolveHoverTarget, positionLabel, injectFontFaceCss } from "./utils.js";
import { createLayerController } from "./layer-dropdown/controller.js";
import { LAYER_DROPDOWN_ATTR } from "./layer-dropdown/consts.js";
import { createInlineEditController } from "../capabilities/inline-edit/index.js";
import { THEME_FONT_PREVIEW_ID } from "../consts.js";
import { createCanvasWheelZoomBridgeController } from "./canvas-wheel-zoom-bridge.js";
import { createPageHeightBridgeController } from "./page-height-bridge.js";
import { createAutoPopupSuppressorController } from "./auto-popup-suppressor.js";

const REPOSITION_DELAY_MS = 50;

export function setupVisualEditAgent() {
  const canvasWheelZoomBridge = createCanvasWheelZoomBridgeController();
  const pageHeightBridge = createPageHeightBridgeController();
  const autoPopupSuppressor = createAutoPopupSuppressorController();

  // State variables (replacing React useState/useRef)
  let isVisualEditMode = false;
  let isPopoverDragging = false;
  let isDropdownOpen = false;
  let hoverOverlays: HTMLDivElement[] = [];
  let selectedOverlays: HTMLDivElement[] = [];
  let currentHighlightedElements: Element[] = [];
  let selectedElementId: string | null = null;
  let selectedElement: Element | null = null;

  // Create overlay element
  const createOverlay = (isSelected = false): HTMLDivElement => {
    const overlay = document.createElement("div");
    overlay.style.position = "absolute";
    overlay.style.pointerEvents = "none";
    overlay.style.transition = "all 0.1s ease-in-out";
    overlay.style.zIndex = "9999";

    if (isSelected) {
      overlay.style.border = "2px solid #2563EB";
    } else {
      overlay.style.border = "2px solid #95a5fc";
      overlay.style.backgroundColor = "rgba(99, 102, 241, 0.05)";
    }

    return overlay;
  };

  // Position overlay relative to element
  const positionOverlay = (
    overlay: HTMLDivElement,
    element: Element,
    isSelected = false
  ) => {
    if (!element || !isVisualEditMode) return;

    const htmlElement = element as HTMLElement;
    // Force layout recalculation
    void htmlElement.offsetWidth;

    const rect = element.getBoundingClientRect();
    overlay.style.top = `${rect.top + window.scrollY}px`;
    overlay.style.left = `${rect.left + window.scrollX}px`;
    overlay.style.width = `${rect.width}px`;
    overlay.style.height = `${rect.height}px`;

    // Check if label already exists in overlay
    let label = overlay.querySelector("div") as HTMLDivElement | null;

    if (!label) {
      label = document.createElement("div");
      label.textContent = readVisualEditTagName(element).toLowerCase();
      label.style.position = "absolute";
      label.style.left = "-2px";
      label.style.padding = "2px 8px";
      label.style.fontSize = "11px";
      label.style.fontWeight = isSelected ? "500" : "400";
      label.style.color = isSelected ? "#ffffff" : "#526cff";
      label.style.backgroundColor = isSelected ? "#2563EB" : "#DBEAFE";
      label.style.borderRadius = "3px";
      label.style.minWidth = "24px";
      label.style.textAlign = "center";
      overlay.appendChild(label);
    }

    positionLabel(label, rect);
  };

  // --- Inline edit controller ---
  const inlineEdit = createInlineEditController({
    findElementsById,
    getSelectedElementId: () => selectedElementId,
    getSelectedOverlays: () => selectedOverlays,
    positionOverlay,
    clearSelection: () => {
      inlineEdit.clearSelectedMarks(selectedElementId);
      clearSelectedOverlays();
      selectedElementId = null;
      selectedElement = null;
    },
    createSelectionOverlays: (elements, elementId) => {
      elements.forEach((el) => {
        const overlay = createOverlay(true);
        document.body.appendChild(overlay);
        selectedOverlays.push(overlay);
        positionOverlay(overlay, el, true);
      });
      selectedElementId = elementId;
    },
  });

  const clearSelection = () => {
    inlineEdit.clearSelectedMarks(selectedElementId);
    clearSelectedOverlays();
    selectedElementId = null;
    selectedElement = null;
  };

  // Clear hover overlays
  const clearHoverOverlays = () => {
    hoverOverlays.forEach((overlay) => {
      if (overlay && overlay.parentNode) {
        overlay.remove();
      }
    });
    hoverOverlays = [];
    currentHighlightedElements = [];
  };

  const clearSelectedOverlays = () => {
    selectedOverlays.forEach((overlay) => {
      if (overlay && overlay.parentNode) {
        overlay.remove();
      }
    });
    selectedOverlays = [];
  };

  const TEXT_TAGS = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'a', 'label'];

  const notifyElementSelected = (element: Element) => {
    const htmlElement = element as HTMLElement;
    const rect = element.getBoundingClientRect();
    const isTextElement = TEXT_TAGS.includes(readVisualEditTagName(element).toLowerCase());

    const arrEl = htmlElement.closest("[data-arr-variable-name]") as HTMLElement | null;
    const staticArrayName = arrEl?.dataset?.arrVariableName || null;
    const rawIdx = arrEl?.dataset?.arrIndex;
    const staticArrayIndex = rawIdx != null ? parseInt(rawIdx, 10) : null;
    const staticArrayField = htmlElement.dataset?.arrField || null;

    const collectionEl = htmlElement.closest("[data-collection-id]") as HTMLElement | null;
    const itemFieldEl = htmlElement.closest("[data-collection-item-field]") as HTMLElement | null;
    const itemIdEl = htmlElement.closest("[data-collection-item-id]") as HTMLElement | null;

    window.parent.postMessage({
      type: "element-selected",
      tagName: readVisualEditTagName(element),
      classes: readElementClasses(element),
      visualSelectorId: getElementSelectorId(element),
      content: isTextElement ? htmlElement.innerText : undefined,
      dataSourceLocation: htmlElement.dataset.sourceLocation,
      isDynamicContent: htmlElement.dataset.dynamicContent === "true",
      linenumber: htmlElement.dataset.linenumber,
      filename: htmlElement.dataset.filename,
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
      attributes: collectAllowedAttributes(element, ALLOWED_ATTRIBUTES),
      isTextElement,
      staticArrayName,
      staticArrayIndex,
      staticArrayField,
      collectionId: collectionEl?.dataset?.collectionId || null,
      collectionItemField: itemFieldEl?.dataset?.collectionItemField || null,
      collectionItemId: itemIdEl?.dataset?.collectionItemId || null,
    }, "*");
  };

  // Select an element: create overlays, update state, notify parent
  const selectElement = (element: Element, notifyParent = true): HTMLDivElement | undefined => {
    const visualSelectorId = getElementSelectorId(element);

    clearSelectedOverlays();

    const elements = findElementsById(visualSelectorId || null);
    elements.forEach((el) => {
      const overlay = createOverlay(true);
      document.body.appendChild(overlay);
      selectedOverlays.push(overlay);
      positionOverlay(overlay, el, true);
    });

    selectedElementId = visualSelectorId || null;
    selectedElement = element;
    clearHoverOverlays();
    if (notifyParent) notifyElementSelected(element);

    return selectedOverlays[0];
  };

  const notifyDeselection = (): void => {
    selectedElementId = null;
    window.parent.postMessage({ type: "unselect-element" }, "*");
  };

  // Hover detection via mousemove + elementFromPoint (since app elements have pointer-events: none)
  let lastHoveredSelectorId: string | null = null;
  let pendingMouseMoveRaf: number | null = null;

  const clearHoverState = () => {
    clearHoverOverlays();
    lastHoveredSelectorId = null;
  };

  const applyHoverOverlays = (selectorId: string) => {
    const elements = findElementsById(selectorId);
    clearHoverOverlays();

    elements.forEach((el) => {
      const overlay = createOverlay(false);
      document.body.appendChild(overlay);
      hoverOverlays.push(overlay);
      positionOverlay(overlay, el);
    });

    currentHighlightedElements = elements;
    lastHoveredSelectorId = selectorId;
  };

  const handleMouseMove = (e: MouseEvent) => {
    if (!isVisualEditMode || isPopoverDragging || inlineEdit.isEditing()) return;

    if (pendingMouseMoveRaf !== null) return;
    pendingMouseMoveRaf = requestAnimationFrame(() => {
      pendingMouseMoveRaf = null;

      if (isDropdownOpen) { clearHoverState(); return; }

      const selectorId = resolveHoverTarget(e.clientX, e.clientY, selectedElementId);
      if (!selectorId) { clearHoverState(); return; }
      if (lastHoveredSelectorId === selectorId) return;

      applyHoverOverlays(selectorId);
    });
  };

  // Clear hover overlays when mouse leaves the viewport
  const handleMouseLeave = () => {
    if (pendingMouseMoveRaf !== null) {
      cancelAnimationFrame(pendingMouseMoveRaf);
      pendingMouseMoveRaf = null;
    }
    clearHoverState();
  };

  // Handle element click
  const handleElementClick = (e: MouseEvent) => {
    if (!isVisualEditMode) return;

    const target = e.target as Element;

    // Let layer dropdown clicks pass through without interference
    if (target.closest(`[${LAYER_DROPDOWN_ATTR}]`)) return;

    // Let clicks inside the editable element pass through to the browser
    // so the user can reposition the cursor and select text naturally.
    if (inlineEdit.enabled && target instanceof HTMLElement && target.contentEditable === "true") {
      return;
    }

    // Clicking outside the editable element exits inline editing mode.
    if (inlineEdit.isEditing()) {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      inlineEdit.stopEditing();
      return;
    }

    // Close dropdowns when clicking anywhere in iframe if a dropdown is open
    if (isDropdownOpen) {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();

      window.parent.postMessage({ type: "close-dropdowns" }, "*");
      return;
    }

    // Prevent default behavior immediately when in visual edit mode
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();

    const element = findInstrumentedElement(e.clientX, e.clientY);
    if (!element) {
      return;
    }

    const htmlElement = element as HTMLElement;
    const visualSelectorId = getElementSelectorId(element);

    const isAlreadySelected =
      selectedElementId === visualSelectorId &&
      htmlElement.dataset.selected === "true";

    if (isAlreadySelected && inlineEdit.enabled && inlineEdit.canEdit(htmlElement)) {
      inlineEdit.startEditing(htmlElement);
      return;
    }

    inlineEdit.stopEditing();

    if (inlineEdit.enabled) {
      inlineEdit.markElementsSelected(findElementsById(visualSelectorId));
    }

    const selectedOverlay = selectElement(element);
    layerController.attachToOverlay(selectedOverlay, element);
  };

  const unselectElement = () => {
    inlineEdit.stopEditing();
    clearSelection();
  };

  const updateElementClassesAndReposition = (visualSelectorId: string, classes: string) => {
    const elements = findElementsById(visualSelectorId);
    if (elements.length === 0) return;

    updateElementClasses(elements, classes);

    // Use a small delay to allow the browser to recalculate layout before repositioning
    setTimeout(() => {
      // Reposition selected overlays
      if (selectedElementId === visualSelectorId) {
        selectedOverlays.forEach((overlay, index) => {
          if (index < elements.length) {
            positionOverlay(overlay, elements[index]!);
          }
        });
      }

      // Reposition hover overlays if needed
      if (currentHighlightedElements.length > 0) {
        const hoveredElement = currentHighlightedElements[0] as HTMLElement;
        const hoveredId = hoveredElement?.dataset?.visualSelectorId;
        if (hoveredId === visualSelectorId) {
          hoverOverlays.forEach((overlay, index) => {
            if (index < currentHighlightedElements.length) {
              positionOverlay(overlay, currentHighlightedElements[index]!);
            }
          });
        }
      }
    }, REPOSITION_DELAY_MS);
  };

  // Update element attribute by visual selector ID
  const updateElementAttributeAndReposition = (
    visualSelectorId: string,
    attribute: string,
    value: string,
    arrIndex?: number | string
  ) => {
    const elements = findElementsById(visualSelectorId);
    if (elements.length === 0) return;

    const targetArrIndex =
      arrIndex ??
      (selectedElementId === visualSelectorId
        ? (selectedElement as HTMLElement | null)?.dataset.arrIndex
        : undefined);

    updateElementAttribute(elements, attribute, value, targetArrIndex);

    // Reposition overlays after attribute change (e.g. image src swap can affect layout)
    setTimeout(() => {
      if (selectedElementId === visualSelectorId) {
        const currentElements = findElementsById(visualSelectorId);
        if (selectedElement && !selectedElement.isConnected) {
          const selectedIndex = (selectedElement as HTMLElement).dataset.arrIndex;
          const replacement = currentElements.find(
            (element) => (element as HTMLElement).dataset.arrIndex === selectedIndex
          );
          if (replacement) {
            const overlay = selectElement(replacement, false);
            layerController.attachToOverlay(overlay, replacement);
          }
        }
        selectedOverlays.forEach((overlay, index) => {
          if (index < currentElements.length) {
            positionOverlay(overlay, currentElements[index]!);
          }
        });
      }
    }, REPOSITION_DELAY_MS);
  };

  const updateElementContent = (visualSelectorId: string, content: string, arrIndex?: number) => {
    let elements = findElementsById(visualSelectorId);

    if (elements.length === 0) {
      return;
    }

    if (arrIndex != null) {
      elements = elements.filter(
        (el) => (el as HTMLElement).dataset.arrIndex === String(arrIndex)
      );
    }

    elements.forEach((element) => {
      (element as HTMLElement).innerText = content;
    });

    setTimeout(() => {
      if (selectedElementId === visualSelectorId) {
        selectedOverlays.forEach((overlay, index) => {
          if (index < elements.length) {
            positionOverlay(overlay, elements[index]!);
          }
        });
      }
    }, REPOSITION_DELAY_MS);
  };

  // --- Layer dropdown controller ---
  const layerController = createLayerController({
    createPreviewOverlay: (element: Element) => {
      const overlay = createOverlay(false);
      overlay.style.zIndex = "9998";
      document.body.appendChild(overlay);
      positionOverlay(overlay, element);
      return overlay;
    },
    getSelectedElementId: () => selectedElementId,
    selectElement,
    onDeselect: notifyDeselection,
  });

  // Toggle visual edit mode
  const toggleVisualEditMode = (isEnabled: boolean) => {
    isVisualEditMode = isEnabled;

    if (!isEnabled) {
      canvasWheelZoomBridge.disable();
      resumeAnimations();
      inlineEdit.stopEditing();
      clearSelection();
      layerController.cleanup();
      handleMouseLeave();
      document.body.style.cursor = "default";

      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseleave", handleMouseLeave);
      document.removeEventListener("click", handleElementClick, true);
    } else {
      document.body.style.cursor = "crosshair";
      stopAnimations();
      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseleave", handleMouseLeave);
      document.addEventListener("click", handleElementClick, true);
    }
  };

  // Handle scroll events to update popover position
  const handleScroll = () => {
    if (selectedElementId) {
      const element = selectedElement;
      if (element && element.isConnected) {
        const rect = element.getBoundingClientRect();

        const viewportHeight = window.innerHeight;
        const viewportWidth = window.innerWidth;
        const isInViewport =
          rect.top < viewportHeight &&
          rect.bottom > 0 &&
          rect.left < viewportWidth &&
          rect.right > 0;

        const elementPosition = {
          top: rect.top,
          left: rect.left,
          right: rect.right,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
          centerX: rect.left + rect.width / 2,
          centerY: rect.top + rect.height / 2,
        };

        window.parent.postMessage(
          {
            type: "element-position-update",
            position: elementPosition,
            isInViewport: isInViewport,
            visualSelectorId: selectedElementId,
          },
          "*"
        );
      }
    }
  };

  // Handle messages from parent window
  const handleMessage = (event: MessageEvent) => {
    const message = event.data;

    switch (message.type) {
      case "toggle-visual-edit-mode":
        toggleVisualEditMode(message.data.enabled);
        if (message.data.specs?.newInlineEditEnabled !== undefined) {
          inlineEdit.enabled = message.data.specs.newInlineEditEnabled;
        }
        break;

      case "update-classes":
        if (message.data && message.data.classes !== undefined) {
          updateElementClassesAndReposition(
            message.data.visualSelectorId,
            message.data.classes
          );
        } else {
          console.warn(
            "[VisualEditAgent] Invalid update-classes message:",
            message
          );
        }
        break;

      case "update-attribute":
        if (
          message.data &&
          message.data.visualSelectorId &&
          message.data.attribute !== undefined &&
          message.data.value !== undefined
        ) {
          updateElementAttributeAndReposition(
            message.data.visualSelectorId,
            message.data.attribute,
            message.data.value,
            message.data.arrIndex
          );
        } else {
          console.warn(
            "[VisualEditAgent] Invalid update-attribute message:",
            message
          );
        }
        break;

      case "unselect-element":
        unselectElement();
        break;

      case "refresh-page":
        window.location.reload();
        break;

      case "update-content":
        if (message.data && message.data.content !== undefined) {
          updateElementContent(
            message.data.visualSelectorId,
            message.data.content,
            message.data.arrIndex
          );
        } else {
          console.warn(
            "[VisualEditAgent] Invalid update-content message:",
            message
          );
        }
        break;

      case "request-element-position":
        if (selectedElementId && selectedElement && selectedElement.isConnected) {
          const rect = selectedElement.getBoundingClientRect();

          const viewportHeight = window.innerHeight;
          const viewportWidth = window.innerWidth;
          const isInViewport =
            rect.top < viewportHeight &&
            rect.bottom > 0 &&
            rect.left < viewportWidth &&
            rect.right > 0;

          const elementPosition = {
            top: rect.top,
            left: rect.left,
            right: rect.right,
            bottom: rect.bottom,
            width: rect.width,
            height: rect.height,
            centerX: rect.left + rect.width / 2,
            centerY: rect.top + rect.height / 2,
          };

          window.parent.postMessage(
            {
              type: "element-position-update",
              position: elementPosition,
              isInViewport: isInViewport,
              visualSelectorId: selectedElementId,
            },
            "*"
          );
        }
        break;

      case "popover-drag-state":
        if (message.data && message.data.isDragging !== undefined) {
          isPopoverDragging = message.data.isDragging;
          if (message.data.isDragging) {
            clearHoverOverlays();
          }
        }
        break;

      case "dropdown-state":
        if (message.data && message.data.isOpen !== undefined) {
          isDropdownOpen = message.data.isOpen;
          if (message.data.isOpen) {
            clearHoverOverlays();
          }
        }
        break;

      case "update-theme-variables":
        if (message.data?.variables) {
          const target = message.data.mode === 'dark'
            ? document.querySelector('.dark') as HTMLElement
            : document.documentElement;
          if (target) {
            for (const [name, value] of Object.entries(message.data.variables)) {
              target.style.setProperty(name, value as string);
            }
          }
        }
        break;

      case "inject-font-import":
        if (message.data?.fontUrl) {
          let fontStyle = document.getElementById(THEME_FONT_PREVIEW_ID) as HTMLStyleElement | null;
          if (!fontStyle) {
            fontStyle = document.createElement('style');
            fontStyle.id = THEME_FONT_PREVIEW_ID;
            document.head.appendChild(fontStyle);
          }
          fontStyle.textContent = `@import url('${message.data.fontUrl}');`;
        }
        break;

      case "inject-font-face":
        if (message.data) {
          injectFontFaceCss(message.data.id, message.data.css);
        }
        break;

      case "toggle-inline-edit-mode":
        if (message.data) {
          inlineEdit.handleToggleMessage(message.data);
        }
        break;

      case "freeze-vh-units":
        pageHeightBridge.freezeVhUnits(
          typeof message.referenceVhBase === "number"
            ? message.referenceVhBase
            : undefined
        );
        break;

      case "measure-page-height":
        pageHeightBridge.measurePageHeight(
          event.origin && event.origin !== "null" ? event.origin : "*",
          typeof message.settleMs === "number" ? message.settleMs : undefined
        );
        break;

      case "suppress-auto-popups":
        autoPopupSuppressor.suppress();
        break;

      case "toggle-canvas-wheel-zoom-bridge":
        canvasWheelZoomBridge.enable();
        break;

      default:
        break;
    }
  };

  // Handle window resize to reposition overlays
  const handleResize = () => {
    if (selectedElementId) {
      const elements = findElementsById(selectedElementId);
      selectedOverlays.forEach((overlay, index) => {
        if (index < elements.length) {
          positionOverlay(overlay, elements[index]!);
        }
      });
    }

    if (currentHighlightedElements.length > 0) {
      hoverOverlays.forEach((overlay, index) => {
        if (index < currentHighlightedElements.length) {
          positionOverlay(overlay, currentHighlightedElements[index]!);
        }
      });
    }
  };

  // Initialize: Add IDs to elements that don't have them but have linenumbers
  const elementsWithLineNumber = document.querySelectorAll(
    "[data-linenumber]:not([data-visual-selector-id])"
  );
  elementsWithLineNumber.forEach((el, index) => {
    const htmlEl = el as HTMLElement;
    const id = `visual-id-${htmlEl.dataset.filename}-${htmlEl.dataset.linenumber}-${index}`;
    htmlEl.dataset.visualSelectorId = id;
  });

  // Create mutation observer to detect layout changes
  const mutationObserver = new MutationObserver((mutations) => {
    const needsUpdate = mutations.some((mutation) => {
      const hasVisualId = (node: Node): boolean => {
        if (node.nodeType === Node.ELEMENT_NODE) {
          const el = node as HTMLElement;
          if (el.dataset && el.dataset.visualSelectorId) {
            return true;
          }
          for (let i = 0; i < el.children.length; i++) {
            if (hasVisualId(el.children[i]!)) {
              return true;
            }
          }
        }
        return false;
      };

      const isLayoutChange =
        mutation.type === "attributes" &&
        (mutation.attributeName === "style" ||
          mutation.attributeName === "class" ||
          mutation.attributeName === "width" ||
          mutation.attributeName === "height");

      return isLayoutChange && hasVisualId(mutation.target);
    });

    if (needsUpdate) {
      setTimeout(handleResize, REPOSITION_DELAY_MS);
    }
  });

  // Set up event listeners
  window.addEventListener("message", handleMessage);
  window.addEventListener("scroll", handleScroll, true);
  document.addEventListener("scroll", handleScroll, true);
  window.addEventListener("resize", handleResize);
  window.addEventListener("scroll", handleResize);

  // Start observing DOM mutations
  mutationObserver.observe(document.body, {
    attributes: true,
    childList: true,
    subtree: true,
    attributeFilter: ["style", "class", "width", "height"],
  });

  // Send ready message to parent
  window.parent.postMessage({ type: "visual-edit-agent-ready" }, "*");
}
