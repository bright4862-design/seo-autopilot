const FOCUS_STYLE_ID = "visual-edit-focus-styles";
const EDITABLE_TAGS = [
    "div", "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "span", "li", "td", "a", "button", "label",
];
export const isStaticArrayTextElement = (element) => {
    return !!element.dataset.arrField;
};
const passesStructuralChecks = (element) => {
    if (!EDITABLE_TAGS.includes(element.tagName.toLowerCase()))
        return false;
    if (!element.textContent?.trim())
        return false;
    if (element.querySelector("img, video, canvas, svg"))
        return false;
    if (element.children?.length > 0)
        return false;
    return true;
};
export const injectFocusOutlineCSS = () => {
    if (document.getElementById(FOCUS_STYLE_ID))
        return;
    const style = document.createElement("style");
    style.id = FOCUS_STYLE_ID;
    style.textContent = `
    [data-selected="true"][contenteditable="true"]:focus {
      outline: none !important;
    }
  `;
    document.head.appendChild(style);
};
export const removeFocusOutlineCSS = () => {
    document.getElementById(FOCUS_STYLE_ID)?.remove();
};
export const selectText = (element) => {
    const range = document.createRange();
    range.selectNodeContents(element);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
};
export const isEditableTextElement = (element) => {
    if (!(element instanceof HTMLElement))
        return false;
    if (!passesStructuralChecks(element))
        return false;
    if (isStaticArrayTextElement(element))
        return true;
    if (element.dataset.dynamicContent === "true")
        return false;
    return true;
};
export const shouldEnterInlineEditingMode = (element) => {
    if (!(element instanceof HTMLElement) || element.dataset.selected !== "true") {
        return false;
    }
    return isEditableTextElement(element);
};
//# sourceMappingURL=dom-utils.js.map