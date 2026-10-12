import type { NodePath } from "@babel/traverse";
import type * as t from "@babel/types";
import {
  DATA_COLLECTION_ITEM_FIELD,
  DATA_COLLECTION_ITEM_ID,
  EXCLUDED_FIELDS,
} from "../consts.js";
import { JSXUtils } from "../jsx-utils.js";
import {
  JSXAttributeUtils,
  ExpressionAnalysisUtils,
  StaticValueUtils,
} from "./utils/shared-utils.js";

export class DataItemFieldProcessor {
  private attributeUtils: JSXAttributeUtils;
  private expressionUtils: ExpressionAnalysisUtils;
  private staticUtils: StaticValueUtils;

  constructor(private types: typeof t) {
    this.attributeUtils = new JSXAttributeUtils(types);
    this.expressionUtils = new ExpressionAnalysisUtils(types);
    this.staticUtils = new StaticValueUtils(types);
  }

  process(path: NodePath<t.JSXOpeningElement>): void {
    if (this.attributeUtils.hasAttribute(path, DATA_COLLECTION_ITEM_FIELD)) {
      return;
    }

    const jsxElement = path.parentPath;
    if (!jsxElement?.isJSXElement()) return;

    const result = this.extractFieldFromChildren(jsxElement);
    if (!result) return;

    this.attributeUtils.addStringAttribute(
      path,
      DATA_COLLECTION_ITEM_FIELD,
      result.fieldPath
    );

    this.tryAddItemId(path, result.rootIdentifier, result.fieldPath);
  }

  private extractFieldFromChildren(
    jsxElement: NodePath<t.JSXElement>
  ): { fieldPath: string; rootIdentifier: t.Identifier } | null {
    const children = jsxElement.get("children");

    for (const child of children) {
      const result = this.extractFieldFromChild(child);
      if (result) return result;
    }

    return null;
  }

  private extractFieldFromChild(
    child: NodePath
  ): { fieldPath: string; rootIdentifier: t.Identifier } | null {
    if (child.isJSXExpressionContainer()) {
      return this.extractFromExpressionContainer(child);
    }

    if (child.isJSXElement()) {
      return this.extractFromChildElement(child);
    }

    return null;
  }

  private extractFromExpressionContainer(
    container: NodePath<t.JSXExpressionContainer>
  ): { fieldPath: string; rootIdentifier: t.Identifier } | null {
    const expression = container.get("expression");

    if (expression.isJSXEmptyExpression()) return null;

    const expr = expression as NodePath<t.Expression>;

    if (expr.isMemberExpression() || expr.isOptionalMemberExpression()) {
      return this.extractFromMemberExpression(expr);
    }

    if (expr.isLogicalExpression() && expr.node.operator === "&&") {
      const left = expr.get("left") as NodePath<t.Expression>;
      if (
        left.isMemberExpression() ||
        left.isOptionalMemberExpression()
      ) {
        return this.extractFromMemberExpression(left);
      }
    }

    if (expr.isCallExpression()) {
      const callee = expr.get("callee");
      if (callee.isMemberExpression()) {
        const obj = callee.get("object") as NodePath<t.Expression>;
        if (obj.isMemberExpression() || obj.isOptionalMemberExpression()) {
          return this.extractFromMemberExpression(obj);
        }
      }
    }

    if (expr.isIdentifier()) {
      return this.extractFromSimpleIdentifier(expr);
    }

    return null;
  }

  private extractFromMemberExpression(
    expr: NodePath<t.MemberExpression | t.OptionalMemberExpression>
  ): { fieldPath: string; rootIdentifier: t.Identifier } | null {
    const rootId = this.expressionUtils.extractRootIdentifier(
      expr.node as t.Expression
    );
    if (!rootId) return null;

    if (this.staticUtils.isDerivedFromStaticData(rootId.name, expr)) {
      return null;
    }

    const parts = this.expressionUtils.collectMemberExpressionPath(
      expr.node as t.Expression
    );
    if (parts.length < 2) return null;

    const fieldParts = parts.slice(1);
    const fieldPath = fieldParts.join(".");

    if (EXCLUDED_FIELDS.includes(fieldPath)) return null;
    if (fieldParts.some((p) => EXCLUDED_FIELDS.includes(p))) return null;

    return { fieldPath, rootIdentifier: rootId };
  }

  private extractFromSimpleIdentifier(
    expr: NodePath<t.Identifier>
  ): { fieldPath: string; rootIdentifier: t.Identifier } | null {
    const name = expr.node.name;
    if (EXCLUDED_FIELDS.includes(name)) return null;
    if (this.staticUtils.isDerivedFromStaticData(name, expr)) return null;

    return { fieldPath: name, rootIdentifier: expr.node };
  }

  private extractFromChildElement(
    child: NodePath<t.JSXElement>
  ): { fieldPath: string; rootIdentifier: t.Identifier } | null {
    const elementName = JSXUtils.getElementName(child.node.openingElement);
    if (!elementName) return null;

    if (elementName === "Image" || elementName === "img") {
      return this.extractFromImageElement(child);
    }

    const logicalParent = child.parentPath;
    if (logicalParent?.isJSXExpressionContainer()) {
      const logicalExpr = logicalParent.parentPath;
      if (logicalExpr?.isLogicalExpression()) {
        return this.extractFromConditionalImage(child);
      }
    }

    return null;
  }

  private extractFromImageElement(
    imageElement: NodePath<t.JSXElement>
  ): { fieldPath: string; rootIdentifier: t.Identifier } | null {
    const openingElement = imageElement.get("openingElement");
    const attrs = openingElement.node.attributes;

    for (const attr of attrs) {
      if (
        this.types.isJSXAttribute(attr) &&
        this.types.isJSXIdentifier(attr.name) &&
        attr.name.name === "src"
      ) {
        if (
          attr.value &&
          this.types.isJSXExpressionContainer(attr.value) &&
          this.types.isExpression(attr.value.expression) &&
          !this.types.isJSXEmptyExpression(attr.value.expression)
        ) {
          const expr = attr.value.expression;
          if (
            this.types.isMemberExpression(expr) ||
            this.types.isOptionalMemberExpression(expr)
          ) {
            const rootId = this.expressionUtils.extractRootIdentifier(expr);
            if (!rootId) return null;

            const parts = this.expressionUtils.collectMemberExpressionPath(expr);
            if (parts.length < 2) return null;

            const fieldPath = parts.slice(1).join(".");
            if (EXCLUDED_FIELDS.includes(fieldPath)) return null;

            return { fieldPath, rootIdentifier: rootId };
          }
        }
      }
    }

    return null;
  }

  private extractFromConditionalImage(
    child: NodePath<t.JSXElement>
  ): { fieldPath: string; rootIdentifier: t.Identifier } | null {
    const elementName = JSXUtils.getElementName(child.node.openingElement);
    if (elementName === "Image" || elementName === "img") {
      return this.extractFromImageElement(child);
    }
    return null;
  }

  private tryAddItemId(
    path: NodePath<t.JSXOpeningElement>,
    rootIdentifier: t.Identifier,
    fieldPath: string
  ): void {
    if (this.attributeUtils.hasAttribute(path, DATA_COLLECTION_ITEM_ID)) {
      return;
    }

    const idField = this.resolveIdFieldName(path);

    if (rootIdentifier.name === fieldPath) {
      this.tryAddItemIdFromDestructuredParams(path, idField);
      return;
    }

    const idExpr = this.buildIdExpression(rootIdentifier.name, idField);

    const binding = path.scope.getBinding(rootIdentifier.name);
    if (!binding) {
      this.tryAddItemIdFromParentComponent(path, rootIdentifier, idField);
      return;
    }

    if (
      binding.path.isVariableDeclarator() ||
      binding.kind === "param"
    ) {
      this.attributeUtils.addExpressionAttribute(
        path,
        DATA_COLLECTION_ITEM_ID,
        idExpr
      );
    }
  }

  /**
   * Build the ID expression for a given root object name.
   * If a specific idField was resolved from a key attribute, generates root?.id (or root?._id).
   * If unknown (cross-file component), generates root?.id || root?._id to cover both conventions.
   */
  private buildIdExpression(
    rootName: string,
    idField: string | null
  ): t.Expression {
    if (idField) {
      return this.types.optionalMemberExpression(
        this.types.identifier(rootName),
        this.types.identifier(idField),
        false,
        true
      );
    }

    return this.types.logicalExpression(
      "||",
      this.types.optionalMemberExpression(
        this.types.identifier(rootName),
        this.types.identifier("id"),
        false,
        true
      ),
      this.types.optionalMemberExpression(
        this.types.identifier(rootName),
        this.types.identifier("_id"),
        false,
        true
      )
    );
  }

  /**
   * Walk up the JSX tree to find a key attribute that accesses .id or ._id.
   * Returns null when no key is found (e.g. cross-file component receiving props).
   */
  private resolveIdFieldName(
    path: NodePath<t.JSXOpeningElement>
  ): string | null {
    let current: NodePath | null = path.parentPath;
    while (current) {
      if (current.isJSXElement()) {
        const opening = current.get("openingElement");
        const field = this.extractIdFieldFromKey(opening);
        if (field) return field;
      }
      current = current.parentPath;
    }
    return null;
  }

  private extractIdFieldFromKey(
    path: NodePath<t.JSXOpeningElement>
  ): string | null {
    for (const attr of path.node.attributes) {
      if (
        this.types.isJSXAttribute(attr) &&
        this.types.isJSXIdentifier(attr.name) &&
        attr.name.name === "key" &&
        attr.value &&
        this.types.isJSXExpressionContainer(attr.value)
      ) {
        const expr = attr.value.expression;
        if (
          this.types.isMemberExpression(expr) &&
          this.types.isIdentifier(expr.property)
        ) {
          const name = expr.property.name;
          if (name === "id" || name === "_id") return name;
        }
      }
    }
    return null;
  }

  /**
   * For simple identifiers from destructured component props like ({ name, price }),
   * find or inject the id field in the ObjectPattern so we can reference it directly.
   */
  private tryAddItemIdFromDestructuredParams(
    path: NodePath<t.JSXOpeningElement>,
    idField: string | null
  ): void {
    const fn = path.getFunctionParent();
    if (!fn) return;

    const params = fn.get("params");
    for (const param of Array.isArray(params) ? params : [params]) {
      if (!param.isObjectPattern()) continue;

      for (const prop of param.get("properties")) {
        if (!prop.isObjectProperty()) continue;
        const key = (prop.node as t.ObjectProperty).key;
        const val = (prop.node as t.ObjectProperty).value;

        // Reuse a forwarding param already injected by processRootElement
        if (
          this.types.isStringLiteral(key) &&
          key.value === DATA_COLLECTION_ITEM_ID &&
          this.types.isIdentifier(val)
        ) {
          this.attributeUtils.addExpressionAttribute(
            path,
            DATA_COLLECTION_ITEM_ID,
            this.types.identifier(val.name)
          );
          return;
        }

        // Use an existing id / _id destructured prop
        if (
          this.types.isIdentifier(key) &&
          (key.name === "id" || key.name === "_id") &&
          this.types.isIdentifier(val)
        ) {
          this.attributeUtils.addExpressionAttribute(
            path,
            DATA_COLLECTION_ITEM_ID,
            this.types.identifier(val.name)
          );
          return;
        }
      }

      const fieldToInject = idField ?? "id";

      // Never inject a param whose name is already bound where the JSX
      // element sits. A function-scope binding (e.g. `const { id } =
      // useParams()`) makes the output fail to compile — "The symbol 'id'
      // has already been declared" — an outer-scope binding would be
      // silently shadowed by an undefined prop, and a block-scope binding
      // between the element and the function would make the emitted
      // attribute read the wrong value. Anchoring on the element's scope
      // chain covers all three; skipping just degrades visual-edit tracing
      // for this element.
      if (path.scope.hasBinding(fieldToInject)) return;

      const newProp = this.types.objectProperty(
        this.types.identifier(fieldToInject),
        this.types.identifier(fieldToInject),
        false,
        true
      );

      const props = param.node.properties;
      const lastProp = props[props.length - 1];
      if (lastProp && this.types.isRestElement(lastProp)) {
        props.splice(props.length - 1, 0, newProp);
      } else {
        props.push(newProp);
      }
      this.attributeUtils.addExpressionAttribute(
        path,
        DATA_COLLECTION_ITEM_ID,
        this.types.identifier(fieldToInject)
      );
      return;
    }
  }

  private tryAddItemIdFromParentComponent(
    path: NodePath<t.JSXOpeningElement>,
    rootIdentifier: t.Identifier,
    idField: string | null
  ): void {
    let current: NodePath | null = path.parentPath;
    while (current) {
      if (current.isJSXElement()) {
        const opening = current.get("openingElement");
        const name = JSXUtils.getElementName(opening.node);
        if (name && JSXUtils.isCustomComponent(name)) {
          const keyAttr = this.findKeyWithId(opening);
          if (keyAttr) {
            const idExpr = this.buildIdExpression(
              rootIdentifier.name,
              idField
            );
            this.attributeUtils.addExpressionAttribute(
              path,
              DATA_COLLECTION_ITEM_ID,
              idExpr
            );
            return;
          }
        }
      }
      current = current.parentPath;
    }
  }

  private findKeyWithId(
    path: NodePath<t.JSXOpeningElement>
  ): boolean {
    for (const attr of path.node.attributes) {
      if (
        this.types.isJSXAttribute(attr) &&
        this.types.isJSXIdentifier(attr.name) &&
        attr.name.name === "key" &&
        attr.value &&
        this.types.isJSXExpressionContainer(attr.value)
      ) {
        const expr = attr.value.expression;
        if (this.types.isExpression(expr)) {
          return this.expressionUtils.isIdAccess(expr);
        }
      }
    }
    return false;
  }
}
