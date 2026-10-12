import { ALLOWED_CUSTOM_COMPONENTS } from "./consts.js";
export class JSXUtils {
    static types;
    static init(types) {
        this.types = types;
    }
    static getAttributeName(attr) {
        return this.types.isJSXNamespacedName(attr.name)
            ? `${attr.name.namespace.name}:${attr.name.name.name}`
            : attr.name.name;
    }
    static getElementName(node) {
        const name = node.name;
        if (this.types.isJSXIdentifier(name)) {
            return name.name;
        }
        if (this.types.isJSXNamespacedName(name)) {
            return `${name.namespace.name}:${name.name.name}`;
        }
        if (this.types.isJSXMemberExpression(name)) {
            return this.collectJSXMemberName(name);
        }
        return null;
    }
    static collectJSXMemberName(node) {
        const parts = [node.property.name];
        let current = node.object;
        while (this.types.isJSXMemberExpression(current)) {
            parts.unshift(current.property.name);
            current = current.object;
        }
        if (this.types.isJSXIdentifier(current)) {
            parts.unshift(current.name);
        }
        return parts.join(".");
    }
    static isCustomComponent(name) {
        return name.length > 0 && name.charAt(0) === name.charAt(0).toUpperCase();
    }
    static isAllowedCustomComponent(name) {
        return ALLOWED_CUSTOM_COMPONENTS.includes(name);
    }
    static isDOMElement(name) {
        return name.length > 0 && name.charAt(0) === name.charAt(0).toLowerCase();
    }
    static isDOMOrAllowed(name) {
        return this.isDOMElement(name) || this.isAllowedCustomComponent(name);
    }
    static producesJSX(node) {
        const types = this.types;
        if (types.isJSXElement(node) || types.isJSXFragment(node))
            return true;
        if (types.isConditionalExpression(node)) {
            return (this.producesJSX(node.consequent) || this.producesJSX(node.alternate));
        }
        if (types.isLogicalExpression(node)) {
            return this.producesJSX(node.left) || this.producesJSX(node.right);
        }
        if (types.isCallExpression(node)) {
            if (types.isMemberExpression(node.callee)) {
                const prop = node.callee.property;
                if (types.isIdentifier(prop) &&
                    (prop.name === "map" || prop.name === "flatMap")) {
                    const callback = node.arguments[0];
                    if (callback)
                        return this.callbackProducesJSX(callback);
                }
            }
        }
        if (types.isParenthesizedExpression(node)) {
            return this.producesJSX(node.expression);
        }
        return false;
    }
    static callbackProducesJSX(callback) {
        const types = this.types;
        if (types.isArrowFunctionExpression(callback)) {
            if (types.isBlockStatement(callback.body)) {
                return this.doesBlockReturnJSX(callback.body);
            }
            return this.producesJSX(callback.body);
        }
        if (types.isFunctionExpression(callback)) {
            return this.doesBlockReturnJSX(callback.body);
        }
        return false;
    }
    static doesBlockReturnJSX(block) {
        for (const stmt of block.body) {
            if (this.types.isReturnStatement(stmt) && stmt.argument) {
                if (this.producesJSX(stmt.argument))
                    return true;
            }
        }
        return false;
    }
}
//# sourceMappingURL=jsx-utils.js.map