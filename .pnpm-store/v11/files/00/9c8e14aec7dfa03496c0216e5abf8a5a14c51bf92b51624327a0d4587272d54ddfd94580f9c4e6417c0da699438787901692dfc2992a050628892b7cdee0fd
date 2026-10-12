import { DATA_COLLECTION_ID, DATA_COLLECTION_REFERENCE, MAX_JSX_DEPTH, } from "../consts.js";
import { JSXUtils } from "../jsx-utils.js";
import { JSXAttributeUtils, PathNavigationUtils, ExpressionAnalysisUtils, } from "./utils/shared-utils.js";
import { CollectionTracingUtils } from "./utils/collection-tracing-utils.js";
export class CollectionIdProcessor {
    types;
    attributeUtils;
    pathUtils;
    expressionUtils;
    tracingUtils;
    constructor(types) {
        this.types = types;
        this.attributeUtils = new JSXAttributeUtils(types);
        this.pathUtils = new PathNavigationUtils(types);
        this.expressionUtils = new ExpressionAnalysisUtils(types);
        this.tracingUtils = new CollectionTracingUtils(types);
    }
    process(path) {
        if (this.attributeUtils.hasAttribute(path, DATA_COLLECTION_ID))
            return;
        const info = this.tryDirectMapInChildren(path) ??
            this.tryGetByIdInChildren(path) ??
            this.tryComponentRootWithCollectionProp(path);
        if (!info)
            return;
        const target = this.pathUtils.findDOMElementTarget(path) ?? path;
        this.attributeUtils.addStringAttribute(target, DATA_COLLECTION_ID, info.id);
        if (info.references.length > 0) {
            this.attributeUtils.addStringAttribute(target, DATA_COLLECTION_REFERENCE, info.references.join(","));
        }
    }
    tryDirectMapInChildren(path) {
        const jsxElement = path.parentPath;
        if (!jsxElement?.isJSXElement())
            return null;
        const children = jsxElement.get("children");
        for (const child of children) {
            if (!child.isJSXExpressionContainer())
                continue;
            const expression = child.get("expression");
            if (expression.isJSXEmptyExpression())
                continue;
            const mapSource = this.extractMapSource(expression);
            if (mapSource)
                return mapSource;
        }
        return null;
    }
    extractMapSource(expr) {
        if (expr.isCallExpression()) {
            return this.traceMapCall(expr);
        }
        if (expr.isLogicalExpression()) {
            if (expr.node.operator === "&&") {
                const right = expr.get("right");
                return this.extractMapSource(right);
            }
        }
        if (expr.isConditionalExpression()) {
            const consequent = expr.get("consequent");
            const alternate = expr.get("alternate");
            return (this.extractMapSource(consequent) ?? this.extractMapSource(alternate));
        }
        if (expr.isOptionalCallExpression()) {
            return this.traceOptionalMapCall(expr);
        }
        return null;
    }
    traceMapCall(callPath) {
        const callee = callPath.get("callee");
        if (!callee.isMemberExpression())
            return null;
        const property = callee.get("property");
        if (!property.isIdentifier() ||
            (property.node.name !== "map" && property.node.name !== "flatMap")) {
            return null;
        }
        if (!this.callbackProducesJSX(callPath))
            return null;
        const arrayObj = callee.get("object");
        return this.tracingUtils.traceCollectionSource(arrayObj);
    }
    traceOptionalMapCall(callPath) {
        const callee = callPath.get("callee");
        if (!callee.isMemberExpression() &&
            !callee.isOptionalMemberExpression()) {
            return null;
        }
        const property = callee.get("property");
        if (!property.isIdentifier() ||
            (property.node.name !== "map" && property.node.name !== "flatMap")) {
            return null;
        }
        const arrayObj = callee.get("object");
        return this.tracingUtils.traceCollectionSource(arrayObj);
    }
    callbackProducesJSX(callPath) {
        const args = callPath.get("arguments");
        const callback = args[0];
        if (!callback)
            return false;
        if (callback.isArrowFunctionExpression()) {
            const body = callback.get("body");
            if (body.isBlockStatement()) {
                return JSXUtils.doesBlockReturnJSX(body.node);
            }
            return JSXUtils.producesJSX(body.node);
        }
        if (callback.isFunctionExpression()) {
            return JSXUtils.doesBlockReturnJSX(callback.node.body);
        }
        return false;
    }
    tryGetByIdInChildren(path, depth = 0) {
        if (depth > MAX_JSX_DEPTH)
            return null;
        const jsxElement = path.parentPath;
        if (!jsxElement?.isJSXElement())
            return null;
        const children = jsxElement.get("children");
        for (const child of children) {
            const info = this.checkChildForGetById(child, depth);
            if (info)
                return info;
        }
        for (const attr of path.node.attributes) {
            if (this.types.isJSXAttribute(attr) &&
                attr.value &&
                this.types.isJSXExpressionContainer(attr.value)) {
                const expr = attr.value.expression;
                if (this.types.isMemberExpression(expr)) {
                    const info = this.tracingUtils.traceGetByIdSource(path);
                    if (info)
                        return info;
                }
            }
        }
        return null;
    }
    checkChildForGetById(child, depth) {
        if (child.isJSXExpressionContainer()) {
            const expr = child.get("expression");
            if (expr.isMemberExpression() ||
                expr.isOptionalMemberExpression()) {
                return this.tracingUtils.traceGetByIdSource(child);
            }
        }
        if (child.isJSXElement()) {
            const childOpening = child.get("openingElement");
            return this.tryGetByIdInChildren(childOpening, depth + 1);
        }
        return null;
    }
    tryComponentRootWithCollectionProp(path) {
        if (!this.pathUtils.isRootReturnElement(path))
            return null;
        const fn = this.pathUtils.findEnclosingFunction(path);
        if (!fn)
            return null;
        let info = null;
        fn.traverse({
            CallExpression: (callPath) => {
                if (info)
                    return;
                const callee = callPath.get("callee");
                if (!callee.isMemberExpression())
                    return;
                const prop = callee.get("property");
                if (!prop.isIdentifier() ||
                    (prop.node.name !== "map" && prop.node.name !== "flatMap")) {
                    return;
                }
                if (!this.callbackProducesJSX(callPath))
                    return;
                // Skip map calls that are directly embedded as JSX children — those
                // are already handled by tryDirectMapInChildren on their immediate
                // parent, so attributing them to the component root would be wrong.
                if (this.isCallInsideJSXChildren(callPath))
                    return;
                const arrayObj = callee.get("object");
                info = this.tracingUtils.traceCollectionSource(arrayObj);
            },
        });
        return info;
    }
    isCallInsideJSXChildren(path) {
        let current = path.parentPath;
        while (current) {
            if (current.isFunction())
                break;
            if (current.isJSXExpressionContainer()) {
                return current.parentPath?.isJSXElement() ?? false;
            }
            current = current.parentPath;
        }
        return false;
    }
}
//# sourceMappingURL=collection-id-processor.js.map