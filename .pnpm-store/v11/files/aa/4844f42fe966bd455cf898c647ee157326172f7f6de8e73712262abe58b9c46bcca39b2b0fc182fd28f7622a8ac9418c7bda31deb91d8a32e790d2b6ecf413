import type { NodePath } from "@babel/traverse";
import type * as t from "@babel/types";
import type { CollectionInfo } from "../capabilities/inline-edit/types.js";
import {
  DATA_COLLECTION_ID,
  DATA_COLLECTION_REFERENCE,
  MAX_JSX_DEPTH,
} from "../consts.js";
import { JSXUtils } from "../jsx-utils.js";
import {
  JSXAttributeUtils,
  PathNavigationUtils,
  ExpressionAnalysisUtils,
} from "./utils/shared-utils.js";
import { CollectionTracingUtils } from "./utils/collection-tracing-utils.js";

export class CollectionIdProcessor {
  private attributeUtils: JSXAttributeUtils;
  private pathUtils: PathNavigationUtils;
  private expressionUtils: ExpressionAnalysisUtils;
  private tracingUtils: CollectionTracingUtils;

  constructor(private types: typeof t) {
    this.attributeUtils = new JSXAttributeUtils(types);
    this.pathUtils = new PathNavigationUtils(types);
    this.expressionUtils = new ExpressionAnalysisUtils(types);
    this.tracingUtils = new CollectionTracingUtils(types);
  }

  process(path: NodePath<t.JSXOpeningElement>): void {
    if (this.attributeUtils.hasAttribute(path, DATA_COLLECTION_ID)) return;

    const info =
      this.tryDirectMapInChildren(path) ??
      this.tryGetByIdInChildren(path) ??
      this.tryComponentRootWithCollectionProp(path);

    if (!info) return;

    const target = this.pathUtils.findDOMElementTarget(path) ?? path;

    this.attributeUtils.addStringAttribute(target, DATA_COLLECTION_ID, info.id);

    if (info.references.length > 0) {
      this.attributeUtils.addStringAttribute(
        target,
        DATA_COLLECTION_REFERENCE,
        info.references.join(",")
      );
    }
  }

  private tryDirectMapInChildren(
    path: NodePath<t.JSXOpeningElement>
  ): CollectionInfo | null {
    const jsxElement = path.parentPath;
    if (!jsxElement?.isJSXElement()) return null;

    const children = jsxElement.get("children");
    for (const child of children) {
      if (!child.isJSXExpressionContainer()) continue;

      const expression = child.get("expression");
      if (expression.isJSXEmptyExpression()) continue;

      const mapSource = this.extractMapSource(
        expression as NodePath<t.Expression>
      );
      if (mapSource) return mapSource;
    }

    return null;
  }

  private extractMapSource(
    expr: NodePath<t.Expression>
  ): CollectionInfo | null {
    if (expr.isCallExpression()) {
      return this.traceMapCall(expr);
    }

    if (expr.isLogicalExpression()) {
      if (expr.node.operator === "&&") {
        const right = expr.get("right") as NodePath<t.Expression>;
        return this.extractMapSource(right);
      }
    }

    if (expr.isConditionalExpression()) {
      const consequent = expr.get("consequent") as NodePath<t.Expression>;
      const alternate = expr.get("alternate") as NodePath<t.Expression>;
      return (
        this.extractMapSource(consequent) ?? this.extractMapSource(alternate)
      );
    }

    if (expr.isOptionalCallExpression()) {
      return this.traceOptionalMapCall(expr);
    }

    return null;
  }

  private traceMapCall(
    callPath: NodePath<t.CallExpression>
  ): CollectionInfo | null {
    const callee = callPath.get("callee");
    if (!callee.isMemberExpression()) return null;

    const property = callee.get("property") as NodePath;
    if (
      !property.isIdentifier() ||
      (property.node.name !== "map" && property.node.name !== "flatMap")
    ) {
      return null;
    }

    if (!this.callbackProducesJSX(callPath)) return null;

    const arrayObj = callee.get("object") as NodePath<t.Expression>;
    return this.tracingUtils.traceCollectionSource(arrayObj);
  }

  private traceOptionalMapCall(
    callPath: NodePath<t.OptionalCallExpression>
  ): CollectionInfo | null {
    const callee = callPath.get("callee");
    if (
      !callee.isMemberExpression() &&
      !callee.isOptionalMemberExpression()
    ) {
      return null;
    }

    const property = (callee as NodePath<t.MemberExpression>).get(
      "property"
    ) as NodePath;
    if (
      !property.isIdentifier() ||
      (property.node.name !== "map" && property.node.name !== "flatMap")
    ) {
      return null;
    }

    const arrayObj = (callee as NodePath<t.MemberExpression>).get(
      "object"
    ) as NodePath<t.Expression>;
    return this.tracingUtils.traceCollectionSource(arrayObj);
  }

  private callbackProducesJSX(
    callPath: NodePath<t.CallExpression>
  ): boolean {
    const args = callPath.get("arguments");
    const callback = args[0];
    if (!callback) return false;

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

  private tryGetByIdInChildren(
    path: NodePath<t.JSXOpeningElement>,
    depth: number = 0
  ): CollectionInfo | null {
    if (depth > MAX_JSX_DEPTH) return null;

    const jsxElement = path.parentPath;
    if (!jsxElement?.isJSXElement()) return null;

    const children = jsxElement.get("children");
    for (const child of children) {
      const info = this.checkChildForGetById(child, depth);
      if (info) return info;
    }

    for (const attr of path.node.attributes) {
      if (
        this.types.isJSXAttribute(attr) &&
        attr.value &&
        this.types.isJSXExpressionContainer(attr.value)
      ) {
        const expr = attr.value.expression;
        if (this.types.isMemberExpression(expr)) {
          const info = this.tracingUtils.traceGetByIdSource(path);
          if (info) return info;
        }
      }
    }

    return null;
  }

  private checkChildForGetById(
    child: NodePath,
    depth: number
  ): CollectionInfo | null {
    if (child.isJSXExpressionContainer()) {
      const expr = child.get("expression");
      if (
        expr.isMemberExpression() ||
        expr.isOptionalMemberExpression()
      ) {
        return this.tracingUtils.traceGetByIdSource(child);
      }
    }

    if (child.isJSXElement()) {
      const childOpening = child.get("openingElement");
      return this.tryGetByIdInChildren(childOpening, depth + 1);
    }

    return null;
  }

  private tryComponentRootWithCollectionProp(
    path: NodePath<t.JSXOpeningElement>
  ): CollectionInfo | null {
    if (!this.pathUtils.isRootReturnElement(path)) return null;

    const fn = this.pathUtils.findEnclosingFunction(path);
    if (!fn) return null;

    let info: CollectionInfo | null = null;

    fn.traverse({
      CallExpression: (callPath: NodePath<t.CallExpression>) => {
        if (info) return;

        const callee = callPath.get("callee");
        if (!callee.isMemberExpression()) return;

        const prop = callee.get("property") as NodePath;
        if (
          !prop.isIdentifier() ||
          (prop.node.name !== "map" && prop.node.name !== "flatMap")
        ) {
          return;
        }

        if (!this.callbackProducesJSX(callPath)) return;

        // Skip map calls that are directly embedded as JSX children — those
        // are already handled by tryDirectMapInChildren on their immediate
        // parent, so attributing them to the component root would be wrong.
        if (this.isCallInsideJSXChildren(callPath)) return;

        const arrayObj = callee.get("object") as NodePath<t.Expression>;
        info = this.tracingUtils.traceCollectionSource(arrayObj);
      },
    });

    return info;
  }

  private isCallInsideJSXChildren(path: NodePath): boolean {
    let current: NodePath | null = path.parentPath;
    while (current) {
      if (current.isFunction()) break;
      if (current.isJSXExpressionContainer()) {
        return current.parentPath?.isJSXElement() ?? false;
      }
      current = current.parentPath;
    }
    return false;
  }
}
