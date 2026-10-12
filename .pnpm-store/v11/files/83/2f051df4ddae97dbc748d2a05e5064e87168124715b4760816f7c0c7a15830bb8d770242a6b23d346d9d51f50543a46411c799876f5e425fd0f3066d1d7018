import type { NodePath } from "@babel/traverse";
import type * as t from "@babel/types";
import {
  DATA_ARR_INDEX,
  DATA_ARR_VARIABLE_NAME,
  DATA_ARR_FIELD,
  MAX_JSX_DEPTH,
} from "../consts.js";
import { JSXAttributeUtils, StaticValueUtils } from "./utils/shared-utils.js";

const GENERATED_INDEX_PARAM = "__arrIdx__";

interface ArrayMapInfo {
  arrayExpression: NodePath<t.Expression>;
  callbackParam: string;
  indexParam: string | null;
  arrayVariableName: string | null;
  mapCallPath: NodePath<t.CallExpression>;
}

export class StaticArrayProcessor {
  private attributeUtils: JSXAttributeUtils;
  private staticValueUtils: StaticValueUtils;

  constructor(private types: typeof t) {
    this.attributeUtils = new JSXAttributeUtils(types);
    this.staticValueUtils = new StaticValueUtils(types);
  }

  process(path: NodePath<t.JSXOpeningElement>): void {
    const arrayInfo = this.findParentArrayMap(path);
    if (!arrayInfo) return;

    if (!this.isStaticArray(arrayInfo.arrayExpression)) return;

    const indexIdentifier = this.ensureIndexParam(arrayInfo);
    this.addDataAttributes(path, arrayInfo, indexIdentifier);
  }

  private addDataAttributes(
    path: NodePath<t.JSXOpeningElement>,
    arrayInfo: ArrayMapInfo,
    indexIdentifier: string
  ): void {
    this.attributeUtils.addExpressionAttribute(
      path,
      DATA_ARR_INDEX,
      this.types.identifier(indexIdentifier)
    );

    if (arrayInfo.arrayVariableName) {
      this.attributeUtils.addStringAttribute(
        path,
        DATA_ARR_VARIABLE_NAME,
        arrayInfo.arrayVariableName
      );
    }

    const fieldPath = this.findTextContentFieldPath(
      path,
      arrayInfo.callbackParam
    );
    if (fieldPath) {
      this.attributeUtils.addStringAttribute(path, DATA_ARR_FIELD, fieldPath);
    }
  }

  private findTextContentFieldPath(
    path: NodePath<t.JSXOpeningElement>,
    callbackParam: string
  ): string | null {
    const imageSrcFieldPath = this.findImageSrcFieldPath(path, callbackParam);
    if (imageSrcFieldPath) return imageSrcFieldPath;

    const parentElement = path.parentPath;
    if (!parentElement?.isJSXElement()) return null;

    for (const child of parentElement.get("children")) {
      const fieldPath = this.extractFieldPathFromChild(child, callbackParam);
      if (fieldPath) return fieldPath;
    }

    return null;
  }

  private findImageSrcFieldPath(
    path: NodePath<t.JSXOpeningElement>,
    callbackParam: string
  ): string | null {
    const elementName = this.types.isJSXIdentifier(path.node.name)
      ? path.node.name.name
      : null;
    if (elementName !== "img" && elementName !== "Image") return null;

    for (const attr of path.get("attributes")) {
      if (!attr.isJSXAttribute()) continue;

      const attrName = attr.get("name");
      if (!attrName.isJSXIdentifier() || attrName.node.name !== "src") {
        continue;
      }

      const value = attr.get("value");
      if (!value.isJSXExpressionContainer()) return null;

      const expression = value.get("expression");
      if (!expression.isMemberExpression()) return null;

      return this.extractFieldPath(expression, callbackParam);
    }

    return null;
  }

  private extractFieldPathFromChild(
    child: NodePath<t.JSXElement["children"][number]>,
    callbackParam: string
  ): string | null {
    if (!child.isJSXExpressionContainer()) return null;

    const expression = child.get("expression");
    if (!expression.isMemberExpression()) return null;

    return this.extractFieldPath(expression, callbackParam);
  }

  private extractFieldPath(
    expr: NodePath<t.MemberExpression>,
    callbackParam: string
  ): string | null {
    const keyedLookup = this.extractKeyedLookupFieldPath(expr, callbackParam);
    if (keyedLookup) return keyedLookup;

    const parts = this.collectMemberExpressionParts(expr);
    if (!parts) return null;

    const { rootName, propertyNames } = parts;
    return rootName === callbackParam ? propertyNames.join(".") : null;
  }

  private extractKeyedLookupFieldPath(
    expr: NodePath<t.MemberExpression>,
    callbackParam: string
  ): string | null {
    const object = expr.get("object");
    if (!expr.node.computed || !object.isIdentifier()) return null;

    const property = expr.get("property");
    if (!property.isMemberExpression()) return null;

    const keyFieldPath = this.extractFieldPath(property, callbackParam);
    return keyFieldPath ? `${object.node.name}[${keyFieldPath}]` : null;
  }

  private collectMemberExpressionParts(
    expr: NodePath<t.MemberExpression>
  ): { rootName: string; propertyNames: string[] } | null {
    const propertyNames: string[] = [];
    let current: NodePath<t.Expression> = expr;

    while (current.isMemberExpression()) {
      const property = current.get("property");
      if (!property.isIdentifier()) return null;

      propertyNames.unshift(property.node.name);
      current = current.get("object") as NodePath<t.Expression>;
    }

    if (!current.isIdentifier()) return null;

    return { rootName: current.node.name, propertyNames };
  }

  private ensureIndexParam(arrayInfo: ArrayMapInfo): string {
    if (arrayInfo.indexParam) {
      return arrayInfo.indexParam;
    }

    this.addIndexParamToCallback(arrayInfo.mapCallPath);
    return GENERATED_INDEX_PARAM;
  }

  private addIndexParamToCallback(
    mapCallPath: NodePath<t.CallExpression>
  ): void {
    const callback = this.getMapCallback(mapCallPath);
    if (!callback) return;

    const params = callback.get("params");
    if (params.length === 1) {
      callback.node.params.push(this.types.identifier(GENERATED_INDEX_PARAM));
    }
  }

  private getMapCallback(
    mapCallPath: NodePath<t.CallExpression>
  ): NodePath<t.Function> | null {
    const args = mapCallPath.get("arguments");
    const firstArg = args[0];
    if (firstArg && firstArg.isFunction()) {
      return firstArg as NodePath<t.Function>;
    }
    return null;
  }

  private findParentArrayMap(
    path: NodePath<t.JSXOpeningElement>,
    maxDepth: number = MAX_JSX_DEPTH
  ): ArrayMapInfo | null {
    let currentPath: NodePath = path;
    let depth = 0;

    while (currentPath.parentPath && depth < maxDepth) {
      const mapInfo = this.tryExtractMapInfo(currentPath.parentPath);
      if (mapInfo) return mapInfo;

      currentPath = currentPath.parentPath;
      depth++;
    }

    return null;
  }

  private tryExtractMapInfo(parent: NodePath): ArrayMapInfo | null {
    if (!parent.isCallExpression()) return null;
    if (!this.isMapCall(parent)) return null;

    return this.extractArrayMapInfo(parent);
  }

  private isMapCall(callExpr: NodePath<t.CallExpression>): boolean {
    const callee = callExpr.get("callee");
    if (!callee.isMemberExpression()) return false;

    const property = callee.get("property");
    return property.isIdentifier() && property.node.name === "map";
  }

  private extractArrayMapInfo(
    mapCall: NodePath<t.CallExpression>
  ): ArrayMapInfo | null {
    const callback = this.getMapCallback(mapCall);
    if (!callback) return null;

    const params = callback.get("params");
    const firstParam = params[0];
    if (!firstParam || !firstParam.isIdentifier()) return null;

    const callee = mapCall.get("callee") as NodePath<t.MemberExpression>;
    const arrayExpression = callee.get("object") as NodePath<t.Expression>;

    return {
      arrayExpression,
      callbackParam: firstParam.node.name,
      indexParam: this.extractIndexParam(params),
      arrayVariableName: this.extractArrayVariableName(arrayExpression),
      mapCallPath: mapCall,
    };
  }

  private extractIndexParam(params: NodePath<t.Node>[]): string | null {
    const secondParam = params[1];
    return secondParam && secondParam.isIdentifier()
      ? secondParam.node.name
      : null;
  }

  private extractArrayVariableName(
    arrayExpression: NodePath<t.Expression>
  ): string | null {
    return arrayExpression.isIdentifier() ? arrayExpression.node.name : null;
  }

  private isStaticArray(arrayExpression: NodePath<t.Expression>): boolean {
    const arrayExpr = this.resolveArrayExpression(arrayExpression);
    return arrayExpr ? this.isStaticArrayExpression(arrayExpr) : false;
  }

  private resolveArrayExpression(
    expression: NodePath<t.Expression>
  ): NodePath<t.ArrayExpression> | null {
    if (expression.isArrayExpression()) {
      return expression;
    }

    if (expression.isIdentifier()) {
      return this.resolveIdentifierToArray(expression);
    }

    return null;
  }

  private resolveIdentifierToArray(
    identifier: NodePath<t.Identifier>
  ): NodePath<t.ArrayExpression> | null {
    const binding = identifier.scope.getBinding(identifier.node.name);

    if (!binding?.path.isVariableDeclarator()) return null;

    const init = binding.path.get("init");
    return init.isArrayExpression() ? init : null;
  }

  private isStaticArrayExpression(
    arrayExpression: NodePath<t.ArrayExpression>
  ): boolean {
    return this.staticValueUtils.isStaticArrayExpression(arrayExpression);
  }
}
