import type { NodePath } from "@babel/traverse";
import type * as t from "@babel/types";
import { DATA_COLLECTION_ITEM_ID } from "../consts.js";
import { JSXUtils } from "../jsx-utils.js";
import {
  JSXAttributeUtils,
  ExpressionAnalysisUtils,
  PathNavigationUtils,
} from "./utils/shared-utils.js";

const FORWARDING_PARAM_NAME = "__dataCollectionItemId";

export class DataItemIdProcessor {
  private attributeUtils: JSXAttributeUtils;
  private expressionUtils: ExpressionAnalysisUtils;
  private pathUtils: PathNavigationUtils;

  constructor(private types: typeof t) {
    this.attributeUtils = new JSXAttributeUtils(types);
    this.expressionUtils = new ExpressionAnalysisUtils(types);
    this.pathUtils = new PathNavigationUtils(types);
  }

  process(path: NodePath<t.JSXOpeningElement>): void {
    if (this.attributeUtils.hasAttribute(path, DATA_COLLECTION_ITEM_ID)) {
      return;
    }

    const keyAttr = this.findKeyAttribute(path);
    if (!keyAttr) return;

    const expression = this.extractKeyExpression(keyAttr);
    if (!expression) return;

    if (!this.expressionUtils.isIdAccess(expression)) return;

    const optionalExpr = this.types.isMemberExpression(expression)
      ? this.expressionUtils.createOptionalChainExpression(expression)
      : expression;

    this.attributeUtils.addExpressionAttribute(
      path,
      DATA_COLLECTION_ITEM_ID,
      optionalExpr
    );
  }

  /**
   * Called for every root DOM element of a component. Adds a `data-collection-item-id`
   * forwarding attribute so that when the component is used as a collection item
   * (with `data-collection-item-id` passed as a prop from a parent `.map()`), the
   * attribute flows through to the actual DOM element.
   *
   * Skipped when:
   * - The root element already spreads props (e.g. `{...props}`) — forwarding is automatic
   * - The enclosing function maps over a collection — it's a container, not an item
   */
  processRootElement(path: NodePath<t.JSXOpeningElement>): void {
    if (this.attributeUtils.hasAttribute(path, DATA_COLLECTION_ITEM_ID)) return;

    // Only DOM or allowed custom elements (e.g. motion.div)
    const name = JSXUtils.getElementName(path.node);
    if (!name || !JSXUtils.isDOMOrAllowed(name)) return;

    // Only the root return element of a component function
    if (!this.pathUtils.isRootReturnElement(path)) return;

    // Skip if root element already spreads all props — forwarding is handled naturally
    if (this.hasSpreadAttribute(path)) return;

    const fn = this.pathUtils.findEnclosingFunction(path);
    if (!fn) return;

    // Skip if this function IS a .map()/.flatMap() callback — it's an iteration
    // function, not a component (e.g. [...Array(3)].map((_, i) => <div />))
    if (this.isMapCallbackFunction(fn)) return;

    // Skip if this function maps over a collection — it's a container, not an item
    if (this.functionContainsMapCall(fn)) return;

    const expr = this.buildCollectionItemIdExpression(fn);
    if (!expr) return;

    this.attributeUtils.addExpressionAttribute(path, DATA_COLLECTION_ITEM_ID, expr);
  }

  private hasSpreadAttribute(path: NodePath<t.JSXOpeningElement>): boolean {
    return path.node.attributes.some((attr) =>
      this.types.isJSXSpreadAttribute(attr)
    );
  }

  /**
   * Returns true when `fn` is a direct callback argument to a `.map()` or
   * `.flatMap()` call — i.e. the function is an iteration callback, not a
   * component definition. This prevents injecting prop-forwarding into
   * patterns like `[...Array(3)].map((_, i) => <div />)` where the first
   * param may be `undefined`.
   */
  private isMapCallbackFunction(fn: NodePath<t.Function>): boolean {
    const parent = fn.parentPath;
    if (!parent?.isCallExpression()) return false;
    const callee = parent.node.callee;
    return (
      this.types.isMemberExpression(callee) &&
      this.types.isIdentifier(callee.property) &&
      (callee.property.name === "map" || callee.property.name === "flatMap")
    );
  }

  private functionContainsMapCall(fn: NodePath<t.Function>): boolean {
    let found = false;
    const types = this.types;
    fn.traverse({
      // Stop at nested functions — event handlers / callbacks defined inside the
      // component should not cause it to be treated as a collection container.
      Function(innerFnPath) {
        innerFnPath.skip();
      },
      CallExpression(callPath) {
        if (found) {
          callPath.stop();
          return;
        }
        const callee = callPath.node.callee;
        if (
          types.isMemberExpression(callee) &&
          types.isIdentifier(callee.property) &&
          (callee.property.name === "map" || callee.property.name === "flatMap")
        ) {
          found = true;
        }
      },
    });
    return found;
  }

  /**
   * Returns an expression for reading `data-collection-item-id` from the component's
   * props, modifying the function's params destructuring if necessary.
   */
  private buildCollectionItemIdExpression(
    fn: NodePath<t.Function>
  ): t.Expression | null {
    const params = fn.get("params");
    const firstParam = Array.isArray(params) ? params[0] : params;
    if (!firstParam) return null;

    if (firstParam.isObjectPattern()) {
      // Check if already destructured (key must be a string literal — hyphens in the
      // attribute name rule out a plain identifier)
      for (const prop of firstParam.get("properties")) {
        if (!prop.isObjectProperty()) continue;
        const key = (prop.node as t.ObjectProperty).key;
        const val = (prop.node as t.ObjectProperty).value;
        if (
          this.types.isStringLiteral(key) &&
          key.value === DATA_COLLECTION_ITEM_ID &&
          this.types.isIdentifier(val)
        ) {
          return this.types.identifier(val.name);
        }
      }

      // Add "data-collection-item-id": __dataCollectionItemId to destructuring
      const newProp = this.types.objectProperty(
        this.types.stringLiteral(DATA_COLLECTION_ITEM_ID),
        this.types.identifier(FORWARDING_PARAM_NAME)
      );

      const restIdx = firstParam.node.properties.findIndex((p) =>
        this.types.isRestElement(p)
      );
      if (restIdx === -1) {
        firstParam.node.properties.push(newProp);
      } else {
        firstParam.node.properties.splice(restIdx, 0, newProp);
      }

      return this.types.identifier(FORWARDING_PARAM_NAME);
    }

    if (firstParam.isIdentifier()) {
      // props?.["data-collection-item-id"] — optional access in case param is nullish
      return this.types.optionalMemberExpression(
        this.types.identifier(firstParam.node.name),
        this.types.stringLiteral(DATA_COLLECTION_ITEM_ID),
        true, // computed
        true  // optional
      );
    }

    return null;
  }

  private findKeyAttribute(
    path: NodePath<t.JSXOpeningElement>
  ): t.JSXAttribute | null {
    for (const attr of path.node.attributes) {
      if (
        this.types.isJSXAttribute(attr) &&
        this.types.isJSXIdentifier(attr.name) &&
        attr.name.name === "key"
      ) {
        return attr;
      }
    }
    return null;
  }

  private extractKeyExpression(
    attr: t.JSXAttribute
  ): t.Expression | null {
    if (!attr.value) return null;

    if (this.types.isJSXExpressionContainer(attr.value)) {
      const expr = attr.value.expression;
      if (this.types.isExpression(expr)) return expr;
    }

    return null;
  }
}
