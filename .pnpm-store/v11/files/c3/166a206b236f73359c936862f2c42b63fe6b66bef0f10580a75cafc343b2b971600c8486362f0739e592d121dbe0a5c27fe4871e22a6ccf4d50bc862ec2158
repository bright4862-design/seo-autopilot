import type { NodePath } from "@babel/traverse";
import type * as t from "@babel/types";
export declare class JSXAttributeUtils {
    private types;
    constructor(types: typeof t);
    hasAttribute(path: NodePath<t.JSXOpeningElement>, attributeName: string): boolean;
    getAttributeValue(path: NodePath<t.JSXOpeningElement>, attributeName: string): t.JSXAttribute["value"] | null;
    getAttributeStringValue(path: NodePath<t.JSXOpeningElement>, attributeName: string): string | null;
    addStringAttribute(path: NodePath<t.JSXOpeningElement>, attributeName: string, value: string): void;
    addExpressionAttribute(path: NodePath<t.JSXOpeningElement>, attributeName: string, expression: t.Expression): void;
    findAncestorWithAttribute(path: NodePath, attributeName: string): NodePath<t.JSXOpeningElement> | null;
}
export declare class PathNavigationUtils {
    private types;
    constructor(types: typeof t);
    findParentJSXElement(path: NodePath): NodePath<t.JSXElement> | null;
    findEnclosingFunction(path: NodePath): NodePath<t.Function> | null;
    findReturnStatement(path: NodePath): NodePath<t.ReturnStatement> | null;
    isRootReturnElement(path: NodePath<t.JSXOpeningElement>): boolean;
    findDOMElementTarget(path: NodePath<t.JSXOpeningElement>): NodePath<t.JSXOpeningElement> | null;
    private isDOMOrAllowedElement;
}
export declare class ExpressionAnalysisUtils {
    private types;
    constructor(types: typeof t);
    isIdAccess(node: t.Expression): boolean;
    isItemsAccess(node: t.Expression): boolean;
    isLengthAccess(node: t.Expression): boolean;
    extractRootIdentifier(node: t.Expression): t.Identifier | null;
    unwrapLogicalExpression(node: t.Expression): t.Expression;
    collectMemberExpressionPath(node: t.Expression): string[];
    createOptionalChainExpression(node: t.MemberExpression): t.OptionalMemberExpression;
    getFieldPathFromExpression(node: t.Expression, rootName: string): string | null;
}
export declare class BindingUtils {
    private types;
    constructor(types: typeof t);
    isFunctionParameter(identifierName: string, path: NodePath): boolean;
    isUseStateCall(init: NodePath<t.Node>): {
        stateIndex: number;
        setterName: string | null;
    } | null;
    isPromiseAllCall(init: NodePath<t.Node>): boolean;
    private isPromiseAllCallee;
    extractDestructuredProperties(pattern: t.ObjectPattern): string[];
    findSetterCallInScope(setterName: string, scope: NodePath): NodePath<t.CallExpression> | null;
}
export declare class CallExpressionUtils {
    private types;
    constructor(types: typeof t);
    isGetAllCall(node: t.CallExpression): {
        collectionName: string;
        references: string[];
    } | null;
    isGetByIdCall(node: t.CallExpression): {
        collectionName: string;
        multiRefFields: string[];
    } | null;
    private extractReferencesFromArg;
    private extractMultiRefFromOptions;
    isArrayMethod(node: t.CallExpression, methodName: string): boolean;
    isChainedArrayMethod(node: t.CallExpression): boolean;
    /**
     * Detect base44.entities.EntityName.list() or .getAll() patterns.
     * Returns the entity name as the collection name.
     */
    isBase44EntityListCall(node: t.CallExpression): {
        collectionName: string;
    } | null;
    /**
     * Detect base44.entities.EntityName.getById() or .get() patterns.
     */
    isBase44EntityGetCall(node: t.CallExpression): {
        collectionName: string;
    } | null;
    getCallbackArgument(callExpr: t.CallExpression): t.ArrowFunctionExpression | t.FunctionExpression | null;
}
export declare class StaticValueUtils {
    private types;
    constructor(types: typeof t);
    isPrimitiveLiteral(path: NodePath<t.Node>): boolean;
    isStaticValue(path: NodePath<t.Node>, visited?: Set<string>): boolean;
    isStaticIdentifier(path: NodePath<t.Identifier>, visited?: Set<string>): boolean;
    isStaticObject(path: NodePath<t.ObjectExpression>, visited?: Set<string>): boolean;
    isStaticArrayExpression(arrayExpression: NodePath<t.ArrayExpression>, visited?: Set<string>): boolean;
    isDerivedFromStaticData(identifierName: string, path: NodePath): boolean;
}
export declare class TypeCheckUtils {
    private types;
    constructor(types: typeof t);
    isArrayIsArrayCheck(node: t.Expression): boolean;
    isTypeofObjectCheck(node: t.Expression): boolean;
    isReferenceTypeCheck(node: t.Expression): boolean;
    isLengthCheck(node: t.Expression): boolean;
}
//# sourceMappingURL=shared-utils.d.ts.map