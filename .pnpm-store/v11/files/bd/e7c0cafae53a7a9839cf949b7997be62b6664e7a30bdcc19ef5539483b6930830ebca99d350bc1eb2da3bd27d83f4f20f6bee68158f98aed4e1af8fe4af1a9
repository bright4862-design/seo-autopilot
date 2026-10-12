import type { NodePath } from "@babel/traverse";
import type * as t from "@babel/types";
import type { CollectionInfo } from "../../capabilities/inline-edit/types.js";
export declare class CollectionTracingUtils {
    private types;
    private bindingUtils;
    private callUtils;
    private visitedSetters;
    private visitedGetByIdSetters;
    constructor(types: typeof t);
    resetVisited(): void;
    traceCollectionSource(path: NodePath<t.Expression>): CollectionInfo | null;
    private traceExpression;
    private traceIdentifierToCollection;
    private traceVariableDeclarator;
    private traceUseStateSetter;
    private findThenCallWithSetter;
    private traceMemberExpression;
    private traceCallExpression;
    /**
     * Trace useQuery({ queryFn: () => base44.entities.X.list() }) patterns.
     * Extracts the collection from the queryFn return expression.
     */
    private traceUseQueryCall;
    private checkDirectServiceCall;
    private traceArrayDestructuring;
    private traceObjectDestructuring;
    private tracePromiseAllElement;
    private traceParameterToCollection;
    private traceArrayExpression;
    private getFunctionName;
    private getJSXElementName;
    traceGetByIdSource(path: NodePath): CollectionInfo | null;
    private findGetByIdInScope;
}
//# sourceMappingURL=collection-tracing-utils.d.ts.map