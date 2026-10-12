import { JSXUtils } from "../../jsx-utils.js";
import { ALLOWED_CUSTOM_COMPONENTS, EXCLUDED_FIELDS } from "../../consts.js";
export class JSXAttributeUtils {
    types;
    constructor(types) {
        this.types = types;
    }
    hasAttribute(path, attributeName) {
        return path.node.attributes.some((attr) => this.types.isJSXAttribute(attr) &&
            JSXUtils.getAttributeName(attr) === attributeName);
    }
    getAttributeValue(path, attributeName) {
        for (const attr of path.node.attributes) {
            if (this.types.isJSXAttribute(attr) &&
                JSXUtils.getAttributeName(attr) === attributeName) {
                return attr.value;
            }
        }
        return null;
    }
    getAttributeStringValue(path, attributeName) {
        const value = this.getAttributeValue(path, attributeName);
        if (value && this.types.isStringLiteral(value)) {
            return value.value;
        }
        return null;
    }
    addStringAttribute(path, attributeName, value) {
        if (!this.hasAttribute(path, attributeName)) {
            path.node.attributes.push(this.types.jsxAttribute(this.types.jsxIdentifier(attributeName), this.types.stringLiteral(value)));
        }
    }
    addExpressionAttribute(path, attributeName, expression) {
        if (!this.hasAttribute(path, attributeName)) {
            path.node.attributes.push(this.types.jsxAttribute(this.types.jsxIdentifier(attributeName), this.types.jsxExpressionContainer(expression)));
        }
    }
    findAncestorWithAttribute(path, attributeName) {
        let current = path.parentPath;
        while (current) {
            if (current.isJSXElement()) {
                const opening = current.get("openingElement");
                if (this.hasAttribute(opening, attributeName)) {
                    return opening;
                }
            }
            current = current.parentPath;
        }
        return null;
    }
}
export class PathNavigationUtils {
    types;
    constructor(types) {
        this.types = types;
    }
    findParentJSXElement(path) {
        let current = path.parentPath;
        while (current) {
            if (current.isJSXElement())
                return current;
            current = current.parentPath;
        }
        return null;
    }
    findEnclosingFunction(path) {
        let current = path.parentPath;
        while (current) {
            if (current.isFunction())
                return current;
            current = current.parentPath;
        }
        return null;
    }
    findReturnStatement(path) {
        let current = path.parentPath;
        while (current) {
            if (current.isReturnStatement())
                return current;
            current = current.parentPath;
        }
        return null;
    }
    isRootReturnElement(path) {
        const jsxElement = path.parentPath;
        if (!jsxElement?.isJSXElement())
            return false;
        const parent = jsxElement.parentPath;
        if (!parent)
            return false;
        if (parent.isReturnStatement())
            return true;
        if (parent.isArrowFunctionExpression())
            return true;
        if (parent.isParenthesizedExpression()) {
            const grandparent = parent.parentPath;
            if (grandparent?.isReturnStatement())
                return true;
            if (grandparent?.isArrowFunctionExpression())
                return true;
        }
        return false;
    }
    findDOMElementTarget(path) {
        if (this.isDOMOrAllowedElement(path))
            return path;
        let current = path.parentPath;
        while (current) {
            if (current.isJSXElement()) {
                const opening = current.get("openingElement");
                if (this.isDOMOrAllowedElement(opening))
                    return opening;
            }
            current = current.parentPath;
        }
        return null;
    }
    isDOMOrAllowedElement(path) {
        const name = JSXUtils.getElementName(path.node);
        if (!name)
            return false;
        if (name.charAt(0) === name.charAt(0).toLowerCase())
            return true;
        return ALLOWED_CUSTOM_COMPONENTS.includes(name);
    }
}
export class ExpressionAnalysisUtils {
    types;
    constructor(types) {
        this.types = types;
    }
    isIdAccess(node) {
        if (!this.types.isMemberExpression(node))
            return false;
        if (this.types.isIdentifier(node.property)) {
            return node.property.name === "_id" || node.property.name === "id";
        }
        if (this.types.isStringLiteral(node.property)) {
            return node.property.value === "_id" || node.property.value === "id";
        }
        return false;
    }
    isItemsAccess(node) {
        return (this.types.isMemberExpression(node) &&
            this.types.isIdentifier(node.property) &&
            node.property.name === "items");
    }
    isLengthAccess(node) {
        return (this.types.isMemberExpression(node) &&
            this.types.isIdentifier(node.property) &&
            node.property.name === "length");
    }
    extractRootIdentifier(node) {
        if (this.types.isIdentifier(node))
            return node;
        if (this.types.isMemberExpression(node)) {
            return this.extractRootIdentifier(node.object);
        }
        if (this.types.isOptionalMemberExpression(node)) {
            return this.extractRootIdentifier(node.object);
        }
        if (this.types.isCallExpression(node) && this.types.isMemberExpression(node.callee)) {
            return this.extractRootIdentifier(node.callee.object);
        }
        return null;
    }
    unwrapLogicalExpression(node) {
        if (this.types.isLogicalExpression(node)) {
            if (node.operator === "&&")
                return node.right;
            if (node.operator === "||" || node.operator === "??") {
                return node.left;
            }
        }
        return node;
    }
    collectMemberExpressionPath(node) {
        const parts = [];
        let current = node;
        while (this.types.isMemberExpression(current) ||
            this.types.isOptionalMemberExpression(current)) {
            const prop = current.property;
            if (this.types.isIdentifier(prop)) {
                parts.unshift(prop.name);
            }
            else if (this.types.isStringLiteral(prop)) {
                parts.unshift(prop.value);
            }
            current = current.object;
        }
        if (this.types.isIdentifier(current)) {
            parts.unshift(current.name);
        }
        return parts;
    }
    createOptionalChainExpression(node) {
        const object = this.types.isOptionalMemberExpression(node.object)
            ? node.object
            : this.types.isMemberExpression(node.object)
                ? this.createOptionalChainExpression(node.object)
                : node.object;
        const property = node.property;
        return this.types.optionalMemberExpression(object, property, node.computed, true);
    }
    getFieldPathFromExpression(node, rootName) {
        const parts = this.collectMemberExpressionPath(node);
        if (parts.length < 2)
            return null;
        if (parts[0] !== rootName)
            return null;
        const fieldParts = parts.slice(1);
        const fieldPath = fieldParts.join(".");
        if (EXCLUDED_FIELDS.includes(fieldPath))
            return null;
        return fieldPath;
    }
}
export class BindingUtils {
    types;
    constructor(types) {
        this.types = types;
    }
    isFunctionParameter(identifierName, path) {
        const fn = path.getFunctionParent();
        if (!fn)
            return false;
        const params = fn.get("params");
        for (const param of (Array.isArray(params) ? params : [params])) {
            if (param.isIdentifier() && param.node.name === identifierName) {
                return true;
            }
            if (param.isObjectPattern()) {
                for (const prop of param.get("properties")) {
                    if (prop.isObjectProperty() &&
                        this.types.isIdentifier(prop.node.value) &&
                        prop.node.value.name === identifierName) {
                        return true;
                    }
                }
            }
            if (param.isArrayPattern()) {
                for (const el of param.get("elements")) {
                    if (el.isIdentifier() && el.node.name === identifierName) {
                        return true;
                    }
                }
            }
        }
        return false;
    }
    isUseStateCall(init) {
        if (!init.isCallExpression())
            return null;
        const callee = init.get("callee");
        if (!callee.isIdentifier() || callee.node.name !== "useState")
            return null;
        const declarator = init.parentPath;
        if (!declarator?.isVariableDeclarator())
            return null;
        const id = declarator.get("id");
        if (!id.isArrayPattern())
            return null;
        const elements = id.get("elements");
        const setterEl = elements[1];
        const setterName = setterEl && setterEl.isIdentifier() ? setterEl.node.name : null;
        return { stateIndex: 0, setterName };
    }
    isPromiseAllCall(init) {
        if (!init.isAwaitExpression()) {
            if (init.isCallExpression()) {
                const callee = init.get("callee");
                return this.isPromiseAllCallee(callee);
            }
            return false;
        }
        const argument = init.get("argument");
        if (!argument.isCallExpression())
            return false;
        const callee = argument.get("callee");
        return this.isPromiseAllCallee(callee);
    }
    isPromiseAllCallee(callee) {
        if (!callee.isMemberExpression())
            return false;
        const obj = callee.get("object");
        const prop = callee.get("property");
        return (obj.isIdentifier() &&
            obj.node.name === "Promise" &&
            prop.isIdentifier() &&
            prop.node.name === "all");
    }
    extractDestructuredProperties(pattern) {
        const properties = [];
        for (const prop of pattern.properties) {
            if (this.types.isObjectProperty(prop)) {
                if (this.types.isIdentifier(prop.key)) {
                    properties.push(prop.key.name);
                }
                else if (this.types.isStringLiteral(prop.key)) {
                    properties.push(prop.key.value);
                }
            }
        }
        return properties;
    }
    findSetterCallInScope(setterName, scope) {
        let result = null;
        scope.traverse({
            CallExpression(callPath) {
                if (result)
                    return;
                const callee = callPath.get("callee");
                if (callee.isIdentifier() && callee.node.name === setterName) {
                    result = callPath;
                }
            },
        });
        return result;
    }
}
export class CallExpressionUtils {
    types;
    constructor(types) {
        this.types = types;
    }
    isGetAllCall(node) {
        const callee = node.callee;
        if (!this.types.isMemberExpression(callee))
            return null;
        const obj = callee.object;
        const prop = callee.property;
        if (!this.types.isIdentifier(obj) ||
            !this.types.isIdentifier(prop) ||
            prop.name !== "getAll") {
            return null;
        }
        const args = node.arguments;
        if (args.length < 1)
            return null;
        const firstArg = args[0];
        if (!this.types.isStringLiteral(firstArg))
            return null;
        const collectionName = firstArg.value;
        const references = this.extractReferencesFromArg(args[1]);
        return { collectionName, references };
    }
    isGetByIdCall(node) {
        const callee = node.callee;
        if (!this.types.isMemberExpression(callee))
            return null;
        const obj = callee.object;
        const prop = callee.property;
        if (!this.types.isIdentifier(obj) ||
            !this.types.isIdentifier(prop) ||
            prop.name !== "getById") {
            return null;
        }
        const args = node.arguments;
        if (args.length < 1)
            return null;
        const firstArg = args[0];
        if (!this.types.isStringLiteral(firstArg))
            return null;
        const collectionName = firstArg.value;
        const multiRefFields = this.extractMultiRefFromOptions(args[2]);
        return { collectionName, multiRefFields };
    }
    extractReferencesFromArg(arg) {
        if (!arg || !this.types.isArrayExpression(arg))
            return [];
        return arg.elements
            .filter((el) => this.types.isStringLiteral(el))
            .map((el) => el.value);
    }
    extractMultiRefFromOptions(arg) {
        if (!arg || !this.types.isObjectExpression(arg))
            return [];
        for (const prop of arg.properties) {
            if (this.types.isObjectProperty(prop) &&
                this.types.isIdentifier(prop.key) &&
                prop.key.name === "multiRef" &&
                this.types.isArrayExpression(prop.value)) {
                return prop.value.elements
                    .filter((el) => this.types.isStringLiteral(el))
                    .map((el) => el.value);
            }
        }
        return [];
    }
    isArrayMethod(node, methodName) {
        const callee = node.callee;
        return (this.types.isMemberExpression(callee) &&
            this.types.isIdentifier(callee.property) &&
            callee.property.name === methodName);
    }
    isChainedArrayMethod(node) {
        const chainMethods = ["filter", "sort", "slice", "concat", "reverse", "flat"];
        return chainMethods.some((m) => this.isArrayMethod(node, m));
    }
    /**
     * Detect base44.entities.EntityName.list() or .getAll() patterns.
     * Returns the entity name as the collection name.
     */
    isBase44EntityListCall(node) {
        const callee = node.callee;
        if (!this.types.isMemberExpression(callee))
            return null;
        const method = callee.property;
        if (!this.types.isIdentifier(method) ||
            (method.name !== "list" && method.name !== "getAll" && method.name !== "filter")) {
            return null;
        }
        const entityAccess = callee.object;
        if (!this.types.isMemberExpression(entityAccess))
            return null;
        const entityName = entityAccess.property;
        if (!this.types.isIdentifier(entityName))
            return null;
        const entitiesAccess = entityAccess.object;
        if (!this.types.isMemberExpression(entitiesAccess))
            return null;
        const entitiesProp = entitiesAccess.property;
        if (!this.types.isIdentifier(entitiesProp) ||
            entitiesProp.name !== "entities") {
            return null;
        }
        return { collectionName: entityName.name };
    }
    /**
     * Detect base44.entities.EntityName.getById() or .get() patterns.
     */
    isBase44EntityGetCall(node) {
        const callee = node.callee;
        if (!this.types.isMemberExpression(callee))
            return null;
        const method = callee.property;
        if (!this.types.isIdentifier(method) ||
            (method.name !== "get" && method.name !== "getById")) {
            return null;
        }
        const entityAccess = callee.object;
        if (!this.types.isMemberExpression(entityAccess))
            return null;
        const entityName = entityAccess.property;
        if (!this.types.isIdentifier(entityName))
            return null;
        const entitiesAccess = entityAccess.object;
        if (!this.types.isMemberExpression(entitiesAccess))
            return null;
        const entitiesProp = entitiesAccess.property;
        if (!this.types.isIdentifier(entitiesProp) ||
            entitiesProp.name !== "entities") {
            return null;
        }
        return { collectionName: entityName.name };
    }
    getCallbackArgument(callExpr) {
        const firstArg = callExpr.arguments[0];
        if (this.types.isArrowFunctionExpression(firstArg) ||
            this.types.isFunctionExpression(firstArg)) {
            return firstArg;
        }
        return null;
    }
}
export class StaticValueUtils {
    types;
    constructor(types) {
        this.types = types;
    }
    isPrimitiveLiteral(path) {
        return (path.isStringLiteral() ||
            path.isNumericLiteral() ||
            path.isBooleanLiteral() ||
            path.isNullLiteral());
    }
    isStaticValue(path, visited = new Set()) {
        if (this.isPrimitiveLiteral(path))
            return true;
        if (path.isIdentifier())
            return this.isStaticIdentifier(path, visited);
        if (path.isObjectExpression())
            return this.isStaticObject(path, visited);
        if (path.isArrayExpression())
            return this.isStaticArrayExpression(path, visited);
        return false;
    }
    isStaticIdentifier(path, visited = new Set()) {
        const binding = path.scope.getBinding(path.node.name);
        if (!binding)
            return false;
        if (binding.kind === "module")
            return true;
        if (binding.kind === "const" && binding.path.isVariableDeclarator()) {
            const name = path.node.name;
            if (visited.has(name))
                return false;
            visited.add(name);
            const init = binding.path.get("init");
            if (init.hasNode()) {
                return this.isStaticValue(init, visited);
            }
        }
        return false;
    }
    isStaticObject(path, visited = new Set()) {
        return path.get("properties").every((prop) => {
            if (!prop.isObjectProperty())
                return false;
            return this.isStaticValue(prop.get("value"), visited);
        });
    }
    isStaticArrayExpression(arrayExpression, visited = new Set()) {
        return arrayExpression.get("elements").every((element) => {
            if (!element.node || element.isSpreadElement())
                return true;
            return this.isStaticValue(element, visited);
        });
    }
    isDerivedFromStaticData(identifierName, path) {
        const binding = path.scope.getBinding(identifierName);
        if (!binding)
            return false;
        if (binding.path.isVariableDeclarator()) {
            const init = binding.path.get("init");
            if (init.isArrayExpression() || init.isObjectExpression()) {
                return this.isStaticValue(init);
            }
        }
        const fnParent = path.getFunctionParent();
        if (!fnParent)
            return false;
        const params = fnParent.get("params");
        for (const param of (Array.isArray(params) ? params : [params])) {
            if (param.isIdentifier() && param.node.name === identifierName) {
                const mapCall = fnParent.parentPath;
                if (mapCall?.isCallExpression()) {
                    const callee = mapCall.get("callee");
                    if (callee.isMemberExpression() &&
                        callee.get("property").isIdentifier()) {
                        const propName = callee.get("property").node.name;
                        if (propName === "map" || propName === "flatMap") {
                            const arrayObj = callee.get("object");
                            if (arrayObj.isIdentifier()) {
                                return this.isDerivedFromStaticData(arrayObj.node.name, arrayObj);
                            }
                            if (arrayObj.isArrayExpression()) {
                                return this.isStaticArrayExpression(arrayObj);
                            }
                        }
                    }
                }
            }
        }
        return false;
    }
}
export class TypeCheckUtils {
    types;
    constructor(types) {
        this.types = types;
    }
    isArrayIsArrayCheck(node) {
        if (!this.types.isCallExpression(node))
            return false;
        const callee = node.callee;
        return (this.types.isMemberExpression(callee) &&
            this.types.isIdentifier(callee.object) &&
            callee.object.name === "Array" &&
            this.types.isIdentifier(callee.property) &&
            callee.property.name === "isArray");
    }
    isTypeofObjectCheck(node) {
        if (!this.types.isBinaryExpression(node))
            return false;
        if (node.operator !== "===" && node.operator !== "==")
            return false;
        const isTypeof = (side) => this.types.isUnaryExpression(side) && side.operator === "typeof";
        const isObjectString = (side) => this.types.isStringLiteral(side) && side.value === "object";
        return ((isTypeof(node.left) &&
            isObjectString(node.right)) ||
            (isObjectString(node.left) &&
                isTypeof(node.right)));
    }
    isReferenceTypeCheck(node) {
        return this.isArrayIsArrayCheck(node) || this.isTypeofObjectCheck(node);
    }
    isLengthCheck(node) {
        if (this.types.isMemberExpression(node)) {
            return (this.types.isIdentifier(node.property) &&
                node.property.name === "length");
        }
        if (this.types.isOptionalMemberExpression(node)) {
            return (this.types.isIdentifier(node.property) &&
                node.property.name === "length");
        }
        return false;
    }
}
//# sourceMappingURL=shared-utils.js.map