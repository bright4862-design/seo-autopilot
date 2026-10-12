import { PLUGIN_ELEMENT_ATTR } from "./utils.js";
function elementFromEventTarget(target) {
    if (target instanceof Element)
        return target;
    if (target instanceof Node)
        return target.parentElement;
    return null;
}
function isPluginOwnedTarget(target) {
    return elementFromEventTarget(target)?.closest(`[${PLUGIN_ELEMENT_ATTR}]`) != null;
}
export function createCanvasWheelZoomBridgeController() {
    let isEnabled = false;
    const onWheel = (event) => {
        if (isPluginOwnedTarget(event.target))
            return;
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
        const panData = {
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
    const enable = () => {
        if (isEnabled)
            return;
        isEnabled = true;
        window.addEventListener("wheel", onWheel, { capture: true, passive: false });
    };
    const disable = () => {
        if (!isEnabled)
            return;
        isEnabled = false;
        window.removeEventListener("wheel", onWheel, true);
    };
    return {
        enable,
        disable,
    };
}
//# sourceMappingURL=canvas-wheel-zoom-bridge.js.map