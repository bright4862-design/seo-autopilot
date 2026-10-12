import { PLUGIN_ELEMENT_ATTR } from "./utils.js";

type CanvasWheelPanData = {
  deltaX: number;
  deltaY: number;
  deltaMode: number;
  clientX: number;
  clientY: number;
  shiftKey: boolean;
  ctrlKey: false;
  metaKey: false;
};

function elementFromEventTarget(target: EventTarget | null): Element | null {
  if (target instanceof Element) return target;
  if (target instanceof Node) return target.parentElement;
  return null;
}

function isPluginOwnedTarget(target: EventTarget | null): boolean {
  return elementFromEventTarget(target)?.closest(`[${PLUGIN_ELEMENT_ATTR}]`) != null;
}

export function createCanvasWheelZoomBridgeController() {
  let isEnabled = false;

  const onWheel = (event: WheelEvent): void => {
    if (isPluginOwnedTarget(event.target)) return;

    event.preventDefault();
    if (event.ctrlKey || event.metaKey) {
      window.parent.postMessage({
        type: "canvas-wheel-zoom",
        data: {
          deltaY: event.deltaY,
          deltaMode: event.deltaMode,
          clientX: event.clientX,
          clientY: event.clientY,
          ctrlKey: event.ctrlKey,
          metaKey: event.metaKey,
        },
      }, "*");
      return;
    }

    const panData: CanvasWheelPanData = {
      deltaX: event.deltaX,
      deltaY: event.deltaY,
      deltaMode: event.deltaMode,
      clientX: event.clientX,
      clientY: event.clientY,
      shiftKey: event.shiftKey,
      ctrlKey: false,
      metaKey: false,
    };
    window.parent.postMessage({
      type: "canvas-wheel-pan",
      data: panData,
    }, "*");
  };

  const enable = (): void => {
    if (isEnabled) return;
    isEnabled = true;
    window.addEventListener("wheel", onWheel, { capture: true, passive: false });
  };

  const disable = (): void => {
    if (!isEnabled) return;
    isEnabled = false;
    window.removeEventListener("wheel", onWheel, true);
  };

  return {
    enable,
    disable,
  };
}
