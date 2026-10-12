import { DATA_ARR_INDEX, DATA_ARR_VARIABLE_NAME, DATA_ARR_FIELD, MAX_JSX_DEPTH, } from "../consts.js";
import { JSXAttributeUtils, StaticValueUtils } from "./utils/shared-utils.js";
const GENERATED_INDEX_PARAM = "__arrIdx__";
export class StaticArrayProcessor {
    types;
    attributeUtils;
    staticValueUtils;
    constructor(types) {
        this.types = types;
        this.attributeUtils = new JSXAttributeUtils(types);
        this.staticValueUtils = new StaticValueUtils(types);
    }
    process(path) {
        const arrayInfo = this.findParentArrayMap(path);
        if (!arrayInfo)
            return;
        if (!this.isStaticArray(arrayInfo.arrayExpression))
            return;
        const indexIdentifier = this.ensureIndexParam(arrayInfo);
        this.addDataAttributes(path, arrayInfo, indexIdentifier);
    }
    addDataAttributes(path, arrayInfo, indexIdentifier) {
        this.attributeUtils.addExpressionAttribute(path, DATA_ARR_INDEX, this.types.identifier(indexIdentifier));
        if (arrayInfo.arrayVariableName) {
            this.attributeUtils.addStringAttribute(path, DATA_ARR_VARIABLE_NAME, arrayInfo.arrayVariableName);
        }
        const fieldPath = this.findTextContentFieldPath(path, arrayInfo.callbackParam);
        if (fieldPath) {
            this.attributeUtils.addStringAttribute(path, DATA_ARR_FIELD, fieldPath);
        }
    }
    findTextContentFieldPath(path, callbackParam) {
        const imageSrcFieldPath = this.findImageSrcFieldPath(path, callbackParam);
        if (imageSrcFieldPath)
            return imageSrcFieldPath;
        const parentElement = path.parentPath;
        if (!parentElement?.isJSXElement())
            return null;
        for (const child of parentElement.get("children")) {
            const fieldPath = this.extractFieldPathFromChild(child, callbackParam);
            if (fieldPath)
                return fieldPath;
        }
        return null;
    }
    findImageSrcFieldPath(path, callbackParam) {
        const elementName = this.types.isJSXIdentifier(path.node.name)
            ? path.node.name.name
            : null;
        if (elementName !== "img" && elementName !== "Image")
            return null;
        for (const attr of path.get("attributes")) {
            if (!attr.isJSXAttribute())
                continue;
            const attrName = attr.get("name");
            if (!attrName.isJSXIdentifier() || attrName.node.name !== "src") {
                continue;
            }
            const value = attr.get("value");
            if (!value.isJSXExpressionContainer())
                return null;
            const expression = value.get("expression");
            if (!expression.isMemberExpression())
                return null;
            return this.extractFieldPath(expression, callbackParam);
        }
        return null;
    }
    extractFieldPathFromChild(child, callbackParam) {
        if (!child.isJSXExpressionContainer())
            return null;
        const expression = child.get("expression");
        if (!expression.isMemberExpression())
            return null;
        return this.extractFieldPath(expression, callbackParam);
    }
    extractFieldPath(expr, callbackParam) {
        const keyedLookup = this.extractKeyedLookupFieldPath(expr, callbackParam);
        if (keyedLookup)
            return keyedLookup;
        const parts = this.collectMemberExpressionParts(expr);
        if (!parts)
            return null;
        const { rootName, propertyNames } = parts;
        return rootName === callbackParam ? propertyNames.join(".") : null;
    }
    extractKeyedLookupFieldPath(expr, callbackParam) {
        const object = expr.get("object");
        if (!expr.node.computed || !object.isIdentifier())
            return null;
        const property = expr.get("property");
        if (!property.isMemberExpression())
            return null;
        const keyFieldPath = this.extractFieldPath(property, callbackParam);
        return keyFieldPath ? `${object.node.name}[${keyFieldPath}]` : null;
    }
    collectMemberExpressionParts(expr) {
        const propertyNames = [];
        let current = expr;
        while (current.isMemberExpression()) {
            const property = current.get("property");
            if (!property.isIdentifier())
                return null;
            propertyNames.unshift(property.node.name);
            current = current.get("object");
        }
        if (!current.isIdentifier())
            return null;
        return { rootName: current.node.name, propertyNames };
    }
    ensureIndexParam(arrayInfo) {
        if (arrayInfo.indexParam) {
            return arrayInfo.indexParam;
        }
        this.addIndexParamToCallback(arrayInfo.mapCallPath);
        return GENERATED_INDEX_PARAM;
    }
    addIndexParamToCallback(mapCallPath) {
        const callback = this.getMapCallback(mapCallPath);
        if (!callback)
            return;
        const params = callback.get("params");
        if (params.length === 1) {
            callback.node.params.push(this.types.identifier(GENERATED_INDEX_PARAM));
        }
    }
    getMapCallback(mapCallPath) {
        const args = mapCallPath.get("arguments");
        const firstArg = args[0];
        if (firstArg && firstArg.isFunction()) {
            return firstArg;
        }
        return null;
    }
    findParentArrayMap(path, maxDepth = MAX_JSX_DEPTH) {
        let currentPath = path;
        let depth = 0;
        while (currentPath.parentPath && depth < maxDepth) {
            const mapInfo = this.tryExtractMapInfo(currentPath.parentPath);
            if (mapInfo)
                return mapInfo;
            currentPath = currentPath.parentPath;
            depth++;
        }
        return null;
    }
    tryExtractMapInfo(parent) {
        if (!parent.isCallExpression())
            return null;
        if (!this.isMapCall(parent))
            return null;
        return this.extractArrayMapInfo(parent);
    }
    isMapCall(callExpr) {
        const callee = callExpr.get("callee");
        if (!callee.isMemberExpression())
            return false;
        const property = callee.get("property");
        return property.isIdentifier() && property.node.name === "map";
    }
    extractArrayMapInfo(mapCall) {
        const callback = this.getMapCallback(mapCall);
        if (!callback)
            return null;
        const params = callback.get("params");
        const firstParam = params[0];
        if (!firstParam || !firstParam.isIdentifier())
            return null;
        const callee = mapCall.get("callee");
        const arrayExpression = callee.get("object");
        return {
            arrayExpression,
            callbackParam: firstParam.node.name,
            indexParam: this.extractIndexParam(params),
            arrayVariableName: this.extractArrayVariableName(arrayExpression),
            mapCallPath: mapCall,
        };
    }
    extractIndexParam(params) {
        const secondParam = params[1];
        return secondParam && secondParam.isIdentifier()
            ? secondParam.node.name
            : null;
    }
    extractArrayVariableName(arrayExpression) {
        return arrayExpression.isIdentifier() ? arrayExpression.node.name : null;
    }
    isStaticArray(arrayExpression) {
        const arrayExpr = this.resolveArrayExpression(arrayExpression);
        return arrayExpr ? this.isStaticArrayExpression(arrayExpr) : false;
    }
    resolveArrayExpression(expression) {
        if (expression.isArrayExpression()) {
            return expression;
        }
        if (expression.isIdentifier()) {
            return this.resolveIdentifierToArray(expression);
        }
        return null;
    }
    resolveIdentifierToArray(identifier) {
        const binding = identifier.scope.getBinding(identifier.node.name);
        if (!binding?.path.isVariableDeclarator())
            return null;
        const init = binding.path.get("init");
        return init.isArrayExpression() ? init : null;
    }
    isStaticArrayExpression(arrayExpression) {
        return this.staticValueUtils.isStaticArrayExpression(arrayExpression);
    }
}
//# sourceMappingURL=static-array-processor.js.map