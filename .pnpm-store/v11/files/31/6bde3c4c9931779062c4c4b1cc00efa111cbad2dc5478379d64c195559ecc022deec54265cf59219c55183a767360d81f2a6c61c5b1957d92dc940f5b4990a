import type { NodePath } from "@babel/traverse";
import type * as t from "@babel/types";
import { JSXUtils } from "../../jsx-utils.js";
import { ALLOWED_CUSTOM_COMPONENTS, EXCLUDED_FIELDS } from "../../consts.js";

export class JSXAttributeUtils {
  constructor(private types: typeof t) {}

  hasAttribute(
    path: NodePath<t.JSXOpeningElement>,
    attributeName: string
  ): boolean {
    return path.node.attributes.some(
      (attr: t.JSXAttribute | t.JSXSpreadAttribute) =>
        this.types.isJSXAttribute(attr) &&
        JSXUtils.getAttributeName(attr) === attributeName
    );
  }

  getAttributeValue(
    path: NodePath<t.JSXOpeningElement>,
    attributeName: string
  ): t.JSXAttribute["value"] | null {
    for (const attr of path.node.attributes) {
      if (
        this.types.isJSXAttribute(attr) &&
        JSXUtils.getAttributeName(attr) === attributeName
      ) {
        return attr.value;
      }
    }
    return null;
  }

  getAttributeStringValue(
    path: NodePath<t.JSXOpeningElement>,
    attributeName: string
  ): string | null {
    const value = this.getAttributeValue(path, attributeName);
    if (value && this.types.isStringLiteral(value)) {
      return value.value;
    }
    return null;
  }

  addStringAttribute(
    path: NodePath<t.JSXOpeningElement>,
    attributeName: string,
    value: string
  ): void {
    if (!this.hasAttribute(path, attributeName)) {
      path.node.attributes.push(
        this.types.jsxAttribute(
          this.types.jsxIdentifier(attributeName),
          this.types.stringLiteral(value)
        )
      );
    }
  }

  addExpressionAttribute(
    path: NodePath<t.JSXOpeningElement>,
    attributeName: string,
    expression: t.Expression
  ): void {
    if (!this.hasAttribute(path, attributeName)) {
      path.node.attributes.push(
        this.types.jsxAttribute(
          this.types.jsxIdentifier(attributeName),
          this.types.jsxExpressionContainer(expression)
        )
      );
    }
  }

  findAncestorWithAttribute(
    path: NodePath,
    attributeName: string
  ): NodePath<t.JSXOpeningElement> | null {
    let current: NodePath | null = path.parentPath;
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
  constructor(private types: typeof t) {}

  findParentJSXElement(
    path: NodePath
  ): NodePath<t.JSXElement> | null {
    let current: NodePath | null = path.parentPath;
    while (current) {
      if (current.isJSXElement()) return current;
      current = current.parentPath;
    }
    return null;
  }

  findEnclosingFunction(
    path: NodePath
  ): NodePath<t.Function> | null {
    let current: NodePath | null = path.parentPath;
    while (current) {
      if (current.isFunction()) return current as NodePath<t.Function>;
      current = current.parentPath;
    }
    return null;
  }

  findReturnStatement(
    path: NodePath
  ): NodePath<t.ReturnStatement> | null {
    let current: NodePath | null = path.parentPath;
    while (current) {
      if (current.isReturnStatement()) return current;
      current = current.parentPath;
    }
    return null;
  }

  isRootReturnElement(
    path: NodePath<t.JSXOpeningElement>
  ): boolean {
    const jsxElement = path.parentPath;
    if (!jsxElement?.isJSXElement()) return false;

    const parent = jsxElement.parentPath;
    if (!parent) return false;

    if (parent.isReturnStatement()) return true;

    if (parent.isArrowFunctionExpression()) return true;

    if (parent.isParenthesizedExpression()) {
      const grandparent = parent.parentPath;
      if (grandparent?.isReturnStatement()) return true;
      if (grandparent?.isArrowFunctionExpression()) return true;
    }

    return false;
  }

  findDOMElementTarget(
    path: NodePath<t.JSXOpeningElement>
  ): NodePath<t.JSXOpeningElement> | null {
    if (this.isDOMOrAllowedElement(path)) return path;

    let current: NodePath | null = path.parentPath;
    while (current) {
      if (current.isJSXElement()) {
        const opening = current.get("openingElement");
        if (this.isDOMOrAllowedElement(opening)) return opening;
      }
      current = current.parentPath;
    }
    return null;
  }

  private isDOMOrAllowedElement(
    path: NodePath<t.JSXOpeningElement>
  ): boolean {
    const name = JSXUtils.getElementName(path.node);
    if (!name) return false;

    if (name.charAt(0) === name.charAt(0).toLowerCase()) return true;

    return ALLOWED_CUSTOM_COMPONENTS.includes(name);
  }
}

export class ExpressionAnalysisUtils {
  constructor(private types: typeof t) {}

  isIdAccess(node: t.Expression): boolean {
    if (!this.types.isMemberExpression(node)) return false;
    if (this.types.isIdentifier(node.property)) {
      return node.property.name === "_id" || node.property.name === "id";
    }
    if (this.types.isStringLiteral(node.property)) {
      return node.property.value === "_id" || node.property.value === "id";
    }
    return false;
  }

  isItemsAccess(node: t.Expression): boolean {
    return (
      this.types.isMemberExpression(node) &&
      this.types.isIdentifier(node.property) &&
      node.property.name === "items"
    );
  }

  isLengthAccess(node: t.Expression): boolean {
    return (
      this.types.isMemberExpression(node) &&
      this.types.isIdentifier(node.property) &&
      node.property.name === "length"
    );
  }

  extractRootIdentifier(node: t.Expression): t.Identifier | null {
    if (this.types.isIdentifier(node)) return node;
    if (this.types.isMemberExpression(node)) {
      return this.extractRootIdentifier(node.object as t.Expression);
    }
    if (this.types.isOptionalMemberExpression(node)) {
      return this.extractRootIdentifier(node.object as t.Expression);
    }
    if (this.types.isCallExpression(node) && this.types.isMemberExpression(node.callee)) {
      return this.extractRootIdentifier(node.callee.object as t.Expression);
    }
    return null;
  }

  unwrapLogicalExpression(node: t.Expression): t.Expression {
    if (this.types.isLogicalExpression(node)) {
      if (node.operator === "&&") return node.right as t.Expression;
      if (node.operator === "||" || node.operator === "??") {
        return node.left as t.Expression;
      }
    }
    return node;
  }

  collectMemberExpressionPath(node: t.Expression): string[] {
    const parts: string[] = [];
    let current: t.Expression = node;

    while (
      this.types.isMemberExpression(current) ||
      this.types.isOptionalMemberExpression(current)
    ) {
      const prop = (current as t.MemberExpression).property;
      if (this.types.isIdentifier(prop)) {
        parts.unshift(prop.name);
      } else if (this.types.isStringLiteral(prop)) {
        parts.unshift(prop.value);
      }
      current = (current as t.MemberExpression).object as t.Expression;
    }

    if (this.types.isIdentifier(current)) {
      parts.unshift(current.name);
    }

    return parts;
  }

  createOptionalChainExpression(
    node: t.MemberExpression
  ): t.OptionalMemberExpression {
    const object = this.types.isOptionalMemberExpression(node.object)
      ? node.object
      : this.types.isMemberExpression(node.object)
        ? this.createOptionalChainExpression(node.object)
        : node.object;

    const property = node.property as t.Expression;

    return this.types.optionalMemberExpression(
      object,
      property,
      node.computed,
      true
    );
  }

  getFieldPathFromExpression(
    node: t.Expression,
    rootName: string
  ): string | null {
    const parts = this.collectMemberExpressionPath(node);
    if (parts.length < 2) return null;
    if (parts[0] !== rootName) return null;

    const fieldParts = parts.slice(1);
    const fieldPath = fieldParts.join(".");

    if (EXCLUDED_FIELDS.includes(fieldPath)) return null;
    return fieldPath;
  }
}

export class BindingUtils {
  constructor(private types: typeof t) {}

  isFunctionParameter(
    identifierName: string,
    path: NodePath
  ): boolean {
    const fn = path.getFunctionParent();
    if (!fn) return false;

    const params = fn.get("params");
    for (const param of (Array.isArray(params) ? params : [params])) {
      if (param.isIdentifier() && param.node.name === identifierName) {
        return true;
      }
      if (param.isObjectPattern()) {
        for (const prop of param.get("properties")) {
          if (
            prop.isObjectProperty() &&
            this.types.isIdentifier(prop.node.value) &&
            prop.node.value.name === identifierName
          ) {
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

  isUseStateCall(
    init: NodePath<t.Node>
  ): { stateIndex: number; setterName: string | null } | null {
    if (!init.isCallExpression()) return null;

    const callee = init.get("callee");
    if (!callee.isIdentifier() || callee.node.name !== "useState") return null;

    const declarator = init.parentPath;
    if (!declarator?.isVariableDeclarator()) return null;

    const id = declarator.get("id");
    if (!id.isArrayPattern()) return null;

    const elements = id.get("elements");
    const setterEl = elements[1];
    const setterName =
      setterEl && setterEl.isIdentifier() ? setterEl.node.name : null;

    return { stateIndex: 0, setterName };
  }

  isPromiseAllCall(
    init: NodePath<t.Node>
  ): boolean {
    if (!init.isAwaitExpression()) {
      if (init.isCallExpression()) {
        const callee = init.get("callee");
        return this.isPromiseAllCallee(callee);
      }
      return false;
    }

    const argument = init.get("argument");
    if (!argument.isCallExpression()) return false;

    const callee = argument.get("callee");
    return this.isPromiseAllCallee(callee);
  }

  private isPromiseAllCallee(callee: NodePath): boolean {
    if (!callee.isMemberExpression()) return false;
    const obj = callee.get("object") as NodePath;
    const prop = callee.get("property") as NodePath;
    return (
      obj.isIdentifier() &&
      obj.node.name === "Promise" &&
      prop.isIdentifier() &&
      prop.node.name === "all"
    );
  }

  extractDestructuredProperties(
    pattern: t.ObjectPattern
  ): string[] {
    const properties: string[] = [];
    for (const prop of pattern.properties) {
      if (this.types.isObjectProperty(prop)) {
        if (this.types.isIdentifier(prop.key)) {
          properties.push(prop.key.name);
        } else if (this.types.isStringLiteral(prop.key)) {
          properties.push(prop.key.value);
        }
      }
    }
    return properties;
  }

  findSetterCallInScope(
    setterName: string,
    scope: NodePath
  ): NodePath<t.CallExpression> | null {
    let result: NodePath<t.CallExpression> | null = null;

    scope.traverse({
      CallExpression(callPath) {
        if (result) return;
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
  constructor(private types: typeof t) {}

  isGetAllCall(
    node: t.CallExpression
  ): { collectionName: string; references: string[] } | null {
    const callee = node.callee;
    if (!this.types.isMemberExpression(callee)) return null;

    const obj = callee.object;
    const prop = callee.property;

    if (
      !this.types.isIdentifier(obj) ||
      !this.types.isIdentifier(prop) ||
      prop.name !== "getAll"
    ) {
      return null;
    }

    const args = node.arguments;
    if (args.length < 1) return null;

    const firstArg = args[0];
    if (!this.types.isStringLiteral(firstArg)) return null;

    const collectionName = firstArg.value;
    const references = this.extractReferencesFromArg(args[1]);

    return { collectionName, references };
  }

  isGetByIdCall(
    node: t.CallExpression
  ): {
    collectionName: string;
    multiRefFields: string[];
  } | null {
    const callee = node.callee;
    if (!this.types.isMemberExpression(callee)) return null;

    const obj = callee.object;
    const prop = callee.property;

    if (
      !this.types.isIdentifier(obj) ||
      !this.types.isIdentifier(prop) ||
      prop.name !== "getById"
    ) {
      return null;
    }

    const args = node.arguments;
    if (args.length < 1) return null;

    const firstArg = args[0];
    if (!this.types.isStringLiteral(firstArg)) return null;

    const collectionName = firstArg.value;
    const multiRefFields = this.extractMultiRefFromOptions(args[2]);

    return { collectionName, multiRefFields };
  }

  private extractReferencesFromArg(
    arg: t.Expression | t.SpreadElement | t.ArgumentPlaceholder | undefined
  ): string[] {
    if (!arg || !this.types.isArrayExpression(arg)) return [];

    return arg.elements
      .filter((el): el is t.StringLiteral => this.types.isStringLiteral(el))
      .map((el) => el.value);
  }

  private extractMultiRefFromOptions(
    arg: t.Expression | t.SpreadElement | t.ArgumentPlaceholder | undefined
  ): string[] {
    if (!arg || !this.types.isObjectExpression(arg)) return [];

    for (const prop of arg.properties) {
      if (
        this.types.isObjectProperty(prop) &&
        this.types.isIdentifier(prop.key) &&
        prop.key.name === "multiRef" &&
        this.types.isArrayExpression(prop.value)
      ) {
        return prop.value.elements
          .filter((el): el is t.StringLiteral =>
            this.types.isStringLiteral(el)
          )
          .map((el) => el.value);
      }
    }
    return [];
  }

  isArrayMethod(
    node: t.CallExpression,
    methodName: string
  ): boolean {
    const callee = node.callee;
    return (
      this.types.isMemberExpression(callee) &&
      this.types.isIdentifier(callee.property) &&
      callee.property.name === methodName
    );
  }

  isChainedArrayMethod(node: t.CallExpression): boolean {
    const chainMethods = ["filter", "sort", "slice", "concat", "reverse", "flat"];
    return chainMethods.some((m) => this.isArrayMethod(node, m));
  }

  /**
   * Detect base44.entities.EntityName.list() or .getAll() patterns.
   * Returns the entity name as the collection name.
   */
  isBase44EntityListCall(
    node: t.CallExpression
  ): { collectionName: string } | null {
    const callee = node.callee;
    if (!this.types.isMemberExpression(callee)) return null;

    const method = callee.property;
    if (
      !this.types.isIdentifier(method) ||
      (method.name !== "list" && method.name !== "getAll" && method.name !== "filter")
    ) {
      return null;
    }

    const entityAccess = callee.object;
    if (!this.types.isMemberExpression(entityAccess)) return null;

    const entityName = entityAccess.property;
    if (!this.types.isIdentifier(entityName)) return null;

    const entitiesAccess = entityAccess.object;
    if (!this.types.isMemberExpression(entitiesAccess)) return null;

    const entitiesProp = entitiesAccess.property;
    if (
      !this.types.isIdentifier(entitiesProp) ||
      entitiesProp.name !== "entities"
    ) {
      return null;
    }

    return { collectionName: entityName.name };
  }

  /**
   * Detect base44.entities.EntityName.getById() or .get() patterns.
   */
  isBase44EntityGetCall(
    node: t.CallExpression
  ): { collectionName: string } | null {
    const callee = node.callee;
    if (!this.types.isMemberExpression(callee)) return null;

    const method = callee.property;
    if (
      !this.types.isIdentifier(method) ||
      (method.name !== "get" && method.name !== "getById")
    ) {
      return null;
    }

    const entityAccess = callee.object;
    if (!this.types.isMemberExpression(entityAccess)) return null;

    const entityName = entityAccess.property;
    if (!this.types.isIdentifier(entityName)) return null;

    const entitiesAccess = entityAccess.object;
    if (!this.types.isMemberExpression(entitiesAccess)) return null;

    const entitiesProp = entitiesAccess.property;
    if (
      !this.types.isIdentifier(entitiesProp) ||
      entitiesProp.name !== "entities"
    ) {
      return null;
    }

    return { collectionName: entityName.name };
  }

  getCallbackArgument(
    callExpr: t.CallExpression
  ): t.ArrowFunctionExpression | t.FunctionExpression | null {
    const firstArg = callExpr.arguments[0];
    if (
      this.types.isArrowFunctionExpression(firstArg) ||
      this.types.isFunctionExpression(firstArg)
    ) {
      return firstArg;
    }
    return null;
  }
}

export class StaticValueUtils {
  constructor(private types: typeof t) {}

  isPrimitiveLiteral(path: NodePath<t.Node>): boolean {
    return (
      path.isStringLiteral() ||
      path.isNumericLiteral() ||
      path.isBooleanLiteral() ||
      path.isNullLiteral()
    );
  }

  isStaticValue(
    path: NodePath<t.Node>,
    visited: Set<string> = new Set()
  ): boolean {
    if (this.isPrimitiveLiteral(path)) return true;
    if (path.isIdentifier()) return this.isStaticIdentifier(path, visited);
    if (path.isObjectExpression()) return this.isStaticObject(path, visited);
    if (path.isArrayExpression())
      return this.isStaticArrayExpression(path, visited);
    return false;
  }

  isStaticIdentifier(
    path: NodePath<t.Identifier>,
    visited: Set<string> = new Set()
  ): boolean {
    const binding = path.scope.getBinding(path.node.name);
    if (!binding) return false;

    if (binding.kind === "module") return true;

    if (binding.kind === "const" && binding.path.isVariableDeclarator()) {
      const name = path.node.name;
      if (visited.has(name)) return false;
      visited.add(name);

      const init = binding.path.get("init");
      if (init.hasNode()) {
        return this.isStaticValue(init as NodePath<t.Node>, visited);
      }
    }

    return false;
  }

  isStaticObject(
    path: NodePath<t.ObjectExpression>,
    visited: Set<string> = new Set()
  ): boolean {
    return path.get("properties").every((prop: NodePath) => {
      if (!prop.isObjectProperty()) return false;
      return this.isStaticValue(prop.get("value") as NodePath<t.Node>, visited);
    });
  }

  isStaticArrayExpression(
    arrayExpression: NodePath<t.ArrayExpression>,
    visited: Set<string> = new Set()
  ): boolean {
    return arrayExpression.get("elements").every((element) => {
      if (!element.node || element.isSpreadElement()) return true;
      return this.isStaticValue(element as unknown as NodePath<t.Node>, visited);
    });
  }

  isDerivedFromStaticData(
    identifierName: string,
    path: NodePath
  ): boolean {
    const binding = path.scope.getBinding(identifierName);
    if (!binding) return false;

    if (binding.path.isVariableDeclarator()) {
      const init = binding.path.get("init");
      if (init.isArrayExpression() || init.isObjectExpression()) {
        return this.isStaticValue(init as NodePath<t.Node>);
      }
    }

    const fnParent = path.getFunctionParent();
    if (!fnParent) return false;

    const params = fnParent.get("params");
    for (const param of (Array.isArray(params) ? params : [params])) {
      if (param.isIdentifier() && param.node.name === identifierName) {
        const mapCall = fnParent.parentPath;
        if (mapCall?.isCallExpression()) {
          const callee = mapCall.get("callee");
          if (
            callee.isMemberExpression() &&
            (callee.get("property") as NodePath).isIdentifier()
          ) {
            const propName = ((callee.get("property") as NodePath).node as t.Identifier).name;
            if (propName === "map" || propName === "flatMap") {
              const arrayObj = callee.get("object") as NodePath<t.Expression>;
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
  constructor(private types: typeof t) {}

  isArrayIsArrayCheck(node: t.Expression): boolean {
    if (!this.types.isCallExpression(node)) return false;

    const callee = node.callee;
    return (
      this.types.isMemberExpression(callee) &&
      this.types.isIdentifier(callee.object) &&
      callee.object.name === "Array" &&
      this.types.isIdentifier(callee.property) &&
      callee.property.name === "isArray"
    );
  }

  isTypeofObjectCheck(node: t.Expression): boolean {
    if (!this.types.isBinaryExpression(node)) return false;
    if (node.operator !== "===" && node.operator !== "==") return false;

    const isTypeof = (side: t.Expression) =>
      this.types.isUnaryExpression(side) && side.operator === "typeof";
    const isObjectString = (side: t.Expression) =>
      this.types.isStringLiteral(side) && side.value === "object";

    return (
      (isTypeof(node.left as t.Expression) &&
        isObjectString(node.right as t.Expression)) ||
      (isObjectString(node.left as t.Expression) &&
        isTypeof(node.right as t.Expression))
    );
  }

  isReferenceTypeCheck(node: t.Expression): boolean {
    return this.isArrayIsArrayCheck(node) || this.isTypeofObjectCheck(node);
  }

  isLengthCheck(node: t.Expression): boolean {
    if (this.types.isMemberExpression(node)) {
      return (
        this.types.isIdentifier(node.property) &&
        node.property.name === "length"
      );
    }
    if (this.types.isOptionalMemberExpression(node)) {
      return (
        this.types.isIdentifier(node.property) &&
        node.property.name === "length"
      );
    }
    return false;
  }
}
