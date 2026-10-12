/// <reference lib="dom" />
// Make HTMLElement available in non-browser environments
const { HTMLElement = class {
} } = globalThis;
export class ErrorOverlay extends HTMLElement {
    static getOverlayHTML() {
        return `
      <div>
			</div>
    `;
    }
    close() {
        this.parentNode?.removeChild(this);
    }
    static sendErrorToParent(error, title, details, componentName) {
        // Send error to parent using framewire
        if (globalThis.window?.parent) {
            try {
                globalThis.window.parent?.postMessage({
                    type: "app_error",
                    error: { title, details, componentName, originalError: error, stack: error?.stack },
                }, "*");
            }
            catch (error) {
                console.warn("Failed to send error to iframe parent:", error?.message);
            }
        }
    }
    constructor(error) {
        super();
        const stack = error?.stack;
        let componentName = stack?.match(/at\s+(\w+)\s+\(eval/)?.[1];
        if (componentName === "eval") {
            componentName = undefined;
        }
        const title = componentName
            ? `in ${componentName}: ${error.message?.toString()}`
            : error.message?.toString();
        const details = error?.stack;
        // Call editor frame with the error (via post message)
        ErrorOverlay.sendErrorToParent(error, title, details, componentName);
        // Create the overlay element using HTML template
        const overlay = document.createElement("div");
        overlay.innerHTML = ErrorOverlay.getOverlayHTML();
        // Add to DOM
        document.body.appendChild(overlay);
    }
}
// vite/react-plugin transpiles classes with _SomeClass, so we need to replace all _ErrorOverlay with ErrorOverlay
export const errorOverlayCode = ErrorOverlay.toString().replaceAll("_ErrorOverlay", "ErrorOverlay");
//# sourceMappingURL=ErrorOverlay.js.map