import type { NodePath } from "@babel/traverse";
import type * as t from "@babel/types";
import type { CollectionInfo } from "../../capabilities/inline-edit/types.js";
import {
  BindingUtils,
  CallExpressionUtils,
} from "./shared-utils.js";

export class CollectionTracingUtils {
  private bindingUtils: BindingUtils;
  private callUtils: CallExpressionUtils;
  private visitedSetters = new Set<string>();
  private visitedGetByIdSetters = new Set<string>();

  constructor(private types: typeof t) {
    this.bindingUtils = new BindingUtils(types);
    this.callUtils = new CallExpressionUtils(types);
  }

  resetVisited(): void {
    this.visitedSetters.clear();
    this.visitedGetByIdSetters.clear();
  }

  traceCollectionSource(
    path: NodePath<t.Expression>
  ): CollectionInfo | null {
    this.resetVisited();
    return this.traceExpression(path);
  }

  private traceExpression(
    path: NodePath<t.Expression>
  ): CollectionInfo | null {
    if (path.isIdentifier()) {
      return this.traceIdentifierToCollection(path);
    }

    if (path.isMemberExpression()) {
      return this.traceMemberExpression(path);
    }

    if (path.isCallExpression()) {
      return this.traceCallExpression(path);
    }

    if (path.isAwaitExpression()) {
      const argument = path.get("argument");
      if (argument.isExpression()) {
        return this.traceExpression(argument);
      }
    }

    if (path.isArrayExpression()) {
      return this.traceArrayExpression(path);
    }

    return null;
  }

  private traceIdentifierToCollection(
    path: NodePath<t.Identifier>
  ): CollectionInfo | null {
    const name = path.node.name;
    const binding = path.scope.getBinding(name);
    if (!binding) return null;

    if (binding.path.isVariableDeclarator()) {
      return this.traceVariableDeclarator(binding.path, name);
    }

    if (this.bindingUtils.isFunctionParameter(name, path)) {
      return this.traceParameterToCollection(name, path);
    }

    return null;
  }

  private traceVariableDeclarator(
    declaratorPath: NodePath<t.VariableDeclarator>,
    variableName: string
  ): CollectionInfo | null {
    const init = declaratorPath.get("init");

    if (init.isCallExpression()) {
      const directResult = this.checkDirectServiceCall(init);
      if (directResult) return directResult;

      const useStateInfo = this.bindingUtils.isUseStateCall(init);
      if (useStateInfo?.setterName) {
        return this.traceUseStateSetter(useStateInfo.setterName, declaratorPath);
      }
    }

    if (init.isAwaitExpression()) {
      const awaitArg = init.get("argument");
      if (awaitArg.isCallExpression()) {
        const directResult = this.checkDirectServiceCall(awaitArg);
        if (directResult) return directResult;
      }
      return this.traceExpression(init);
    }

    if (init.isConditionalExpression()) {
      const consequent = init.get("consequent") as NodePath<t.Expression>;
      const alternate = init.get("alternate") as NodePath<t.Expression>;
      const result = this.traceExpression(consequent);
      if (result) return result;
      return this.traceExpression(alternate);
    }

    if (init.isMemberExpression()) {
      return this.traceExpression(init);
    }

    if (init.isIdentifier()) {
      return this.traceExpression(init);
    }

    if (init.isCallExpression()) {
      return this.traceExpression(init);
    }

    const id = declaratorPath.get("id");

    if (id.isArrayPattern()) {
      return this.traceArrayDestructuring(declaratorPath, id, variableName);
    }

    if (id.isObjectPattern()) {
      return this.traceObjectDestructuring(declaratorPath, id, variableName);
    }

    return null;
  }

  private traceUseStateSetter(
    setterName: string,
    declaratorPath: NodePath<t.VariableDeclarator>
  ): CollectionInfo | null {
    if (this.visitedSetters.has(setterName)) return null;
    this.visitedSetters.add(setterName);

    const functionScope = declaratorPath.getFunctionParent() ?? declaratorPath.scope.path;

    // Pattern 1: setData(result) — direct call
    const setterCall = this.bindingUtils.findSetterCallInScope(
      setterName,
      functionScope
    );
    if (setterCall) {
      const args = setterCall.get("arguments");
      const firstArg = args[0];
      if (!firstArg || !firstArg.isExpression()) return null;
      return this.traceExpression(firstArg);
    }

    // Pattern 2: somePromise.then(setData) — setter passed as .then callback
    const thenCall = this.findThenCallWithSetter(setterName, functionScope);
    if (thenCall) {
      const callee = thenCall.get("callee");
      if (callee.isMemberExpression()) {
        const promiseExpr = callee.get("object") as NodePath<t.Expression>;
        return this.traceExpression(promiseExpr);
      }
    }

    return null;
  }

  private findThenCallWithSetter(
    setterName: string,
    scope: NodePath
  ): NodePath<t.CallExpression> | null {
    let result: NodePath<t.CallExpression> | null = null;

    scope.traverse({
      CallExpression: (callPath: NodePath<t.CallExpression>) => {
        if (result) {
          callPath.stop();
          return;
        }
        const callee = callPath.node.callee;
        if (
          this.types.isMemberExpression(callee) &&
          this.types.isIdentifier(callee.property) &&
          callee.property.name === "then" &&
          callPath.node.arguments.length > 0 &&
          this.types.isIdentifier(callPath.node.arguments[0]) &&
          callPath.node.arguments[0].name === setterName
        ) {
          result = callPath;
        }
      },
    });

    return result;
  }

  private traceMemberExpression(
    path: NodePath<t.MemberExpression>
  ): CollectionInfo | null {
    const property = path.get("property");
    const object = path.get("object");

    if (
      property.isIdentifier() &&
      property.node.name === "items"
    ) {
      if (object.isExpression()) {
        return this.traceExpression(object);
      }
    }

    if (object.isIdentifier()) {
      const objResult = this.traceIdentifierToCollection(object);
      if (objResult && property.isIdentifier()) {
        if (objResult.references.includes(property.node.name)) {
          return { id: property.node.name, references: [] };
        }
      }
      return objResult;
    }

    if (object.isExpression()) {
      return this.traceExpression(object);
    }

    return null;
  }

  private traceCallExpression(
    path: NodePath<t.CallExpression>
  ): CollectionInfo | null {
    const directResult = this.checkDirectServiceCall(path);
    if (directResult) return directResult;

    const useQueryResult = this.traceUseQueryCall(path);
    if (useQueryResult) return useQueryResult;

    if (this.callUtils.isChainedArrayMethod(path.node)) {
      const callee = path.get("callee");
      if (callee.isMemberExpression()) {
        const obj = callee.get("object") as NodePath<t.Expression>;
        return this.traceExpression(obj);
      }
    }

    return null;
  }

  /**
   * Trace useQuery({ queryFn: () => base44.entities.X.list() }) patterns.
   * Extracts the collection from the queryFn return expression.
   */
  private traceUseQueryCall(
    path: NodePath<t.CallExpression>
  ): CollectionInfo | null {
    const callee = path.get("callee");
    if (!callee.isIdentifier() || callee.node.name !== "useQuery") return null;

    const args = path.get("arguments");
    const configArg = args[0];
    if (!configArg?.isObjectExpression()) return null;

    for (const prop of configArg.get("properties")) {
      if (!prop.isObjectProperty()) continue;
      const key = prop.get("key");
      if (!key.isIdentifier() || key.node.name !== "queryFn") continue;

      const value = prop.get("value");

      if (value.isArrowFunctionExpression() || value.isFunctionExpression()) {
        const fnBody = value.get("body") as NodePath<t.Node>;
        if (fnBody.isCallExpression()) {
          return this.checkDirectServiceCall(fnBody as NodePath<t.CallExpression>);
        }
        if (fnBody.isBlockStatement()) {
          let result: CollectionInfo | null = null;
          fnBody.traverse({
            ReturnStatement: (retPath: NodePath<t.ReturnStatement>) => {
              if (result) return;
              const arg = retPath.get("argument");
              if (arg.isCallExpression()) {
                result = this.checkDirectServiceCall(arg);
              }
            },
          });
          if (result) return result;
        }
      }
    }

    return null;
  }

  private checkDirectServiceCall(
    path: NodePath<t.CallExpression>
  ): CollectionInfo | null {
    const getAllInfo = this.callUtils.isGetAllCall(path.node);
    if (getAllInfo) {
      return {
        id: getAllInfo.collectionName,
        references: getAllInfo.references,
      };
    }

    const getByIdInfo = this.callUtils.isGetByIdCall(path.node);
    if (getByIdInfo) {
      return {
        id: getByIdInfo.collectionName,
        references: getByIdInfo.multiRefFields,
      };
    }

    const base44List = this.callUtils.isBase44EntityListCall(path.node);
    if (base44List) {
      return { id: base44List.collectionName, references: [] };
    }

    const base44Get = this.callUtils.isBase44EntityGetCall(path.node);
    if (base44Get) {
      return { id: base44Get.collectionName, references: [] };
    }

    return null;
  }

  private traceArrayDestructuring(
    declaratorPath: NodePath<t.VariableDeclarator>,
    pattern: NodePath<t.ArrayPattern>,
    variableName: string
  ): CollectionInfo | null {
    const elements = pattern.get("elements");
    const index = elements.findIndex(
      (el) => el.isIdentifier() && el.node.name === variableName
    );

    if (index === -1) return null;

    const init = declaratorPath.get("init");

    if (init.hasNode() && this.bindingUtils.isPromiseAllCall(init as NodePath<t.Node>)) {
      return this.tracePromiseAllElement(init as NodePath<t.Node>, index);
    }

    if (init.isCallExpression()) {
      const useStateInfo = this.bindingUtils.isUseStateCall(init);
      if (useStateInfo && index === 0 && useStateInfo.setterName) {
        return this.traceUseStateSetter(useStateInfo.setterName, declaratorPath);
      }
    }

    return null;
  }

  private traceObjectDestructuring(
    declaratorPath: NodePath<t.VariableDeclarator>,
    pattern: NodePath<t.ObjectPattern>,
    variableName: string
  ): CollectionInfo | null {
    const init = declaratorPath.get("init");
    if (!init.isExpression()) return null;

    const prop = pattern.node.properties.find(
      (p) =>
        this.types.isObjectProperty(p) &&
        (
          (this.types.isIdentifier(p.value) && p.value.name === variableName) ||
          (this.types.isAssignmentPattern(p.value) &&
            this.types.isIdentifier(p.value.left) &&
            p.value.left.name === variableName)
        )
    );

    if (!prop || !this.types.isObjectProperty(prop)) return null;

    const key = prop.key;
    const propertyName = this.types.isIdentifier(key)
      ? key.name
      : this.types.isStringLiteral(key)
        ? key.value
        : null;

    if (propertyName === "items") {
      return this.traceExpression(init);
    }

    return this.traceExpression(init);
  }

  private tracePromiseAllElement(
    init: NodePath<t.Node>,
    index: number
  ): CollectionInfo | null {
    let callExpr: NodePath<t.CallExpression>;

    if (init.isAwaitExpression()) {
      const arg = init.get("argument");
      if (!arg.isCallExpression()) return null;
      callExpr = arg;
    } else if (init.isCallExpression()) {
      callExpr = init;
    } else {
      return null;
    }

    const args = callExpr.get("arguments");
    const firstArg = args[0];
    if (!firstArg?.isArrayExpression()) return null;

    const elements = firstArg.get("elements");
    const targetElement = elements[index];
    if (!targetElement || !targetElement.isExpression()) return null;

    return this.traceExpression(targetElement);
  }

  private traceParameterToCollection(
    paramName: string,
    path: NodePath
  ): CollectionInfo | null {
    const fn = path.getFunctionParent();
    if (!fn) return null;

    const fnName = this.getFunctionName(fn);
    if (!fnName) return null;

    const programPath = fn.findParent((p) => p.isProgram());
    if (!programPath) return null;

    let result: CollectionInfo | null = null;

    programPath.traverse({
      JSXOpeningElement: (jsxPath: NodePath<t.JSXOpeningElement>) => {
        if (result) return;

        const elementName = this.getJSXElementName(jsxPath.node);
        if (elementName !== fnName) return;

        for (const attr of jsxPath.node.attributes) {
          if (!this.types.isJSXAttribute(attr)) continue;
          if (!this.types.isJSXIdentifier(attr.name)) continue;
          if (attr.name.name !== paramName) continue;

          if (
            attr.value &&
            this.types.isJSXExpressionContainer(attr.value) &&
            this.types.isExpression(attr.value.expression)
          ) {
            const exprPath = jsxPath
              .get("attributes")
              .find(
                (a) =>
                  a.isJSXAttribute() &&
                  this.types.isJSXIdentifier(a.node.name) &&
                  a.node.name.name === paramName
              );

            if (exprPath && exprPath.isJSXAttribute()) {
              const valPath = exprPath.get("value");
              if (
                valPath.isJSXExpressionContainer()
              ) {
                const expr = valPath.get("expression");
                if (expr.isExpression()) {
                  result = this.traceExpression(expr);
                }
              }
            }
          }
        }
      },
    });

    if (!result) {
      return { id: paramName, references: [] };
    }

    return result;
  }

  private traceArrayExpression(
    path: NodePath<t.ArrayExpression>
  ): CollectionInfo | null {
    const elements = path.get("elements");
    for (const el of elements) {
      if (el.isSpreadElement()) {
        const arg = el.get("argument");
        if (arg.isExpression()) {
          const result = this.traceExpression(arg);
          if (result) return result;
        }
      }
    }
    return null;
  }

  private getFunctionName(fn: NodePath<t.Function>): string | null {
    if (fn.isFunctionDeclaration() && fn.node.id) {
      return fn.node.id.name;
    }

    const parent = fn.parentPath;
    if (parent?.isVariableDeclarator()) {
      const id = parent.get("id");
      if (id.isIdentifier()) return id.node.name;
    }

    return null;
  }

  private getJSXElementName(node: t.JSXOpeningElement): string | null {
    if (this.types.isJSXIdentifier(node.name)) {
      return node.name.name;
    }
    return null;
  }

  traceGetByIdSource(
    path: NodePath
  ): CollectionInfo | null {
    this.visitedGetByIdSetters.clear();
    return this.findGetByIdInScope(path);
  }

  private findGetByIdInScope(
    path: NodePath
  ): CollectionInfo | null {
    const fn = path.getFunctionParent() ?? path.scope.path;
    let result: CollectionInfo | null = null;

    fn.traverse({
      CallExpression: (callPath: NodePath<t.CallExpression>) => {
        if (result) return;
        const info = this.callUtils.isGetByIdCall(callPath.node);
        if (info) {
          result = {
            id: info.collectionName,
            references: info.multiRefFields,
          };
          return;
        }
        const base44Get = this.callUtils.isBase44EntityGetCall(callPath.node);
        if (base44Get) {
          result = { id: base44Get.collectionName, references: [] };
        }
      },
    });

    return result;
  }
}
