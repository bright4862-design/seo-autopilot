import type { NodePath } from "@babel/traverse";
import type * as t from "@babel/types";
export declare class DataItemFieldProcessor {
    private types;
    private attributeUtils;
    private expressionUtils;
    private staticUtils;
    constructor(types: typeof t);
    process(path: NodePath<t.JSXOpeningElement>): void;
    private extractFieldFromChildren;
    private extractFieldFromChild;
    private extractFromExpressionContainer;
    private extractFromMemberExpression;
    private extractFromSimpleIdentifier;
    private extractFromChildElement;
    private extractFromImageElement;
    private extractFromConditionalImage;
    private tryAddItemId;
    /**
     * Build the ID expression for a given root object name.
     * If a specific idField was resolved from a key attribute, generates root?.id (or root?._id).
     * If unknown (cross-file component), generates root?.id || root?._id to cover both conventions.
     */
    private buildIdExpression;
    /**
     * Walk up the JSX tree to find a key attribute that accesses .id or ._id.
     * Returns null when no key is found (e.g. cross-file component receiving props).
     */
    private resolveIdFieldName;
    private extractIdFieldFromKey;
    /**
     * For simple identifiers from destructured component props like ({ name, price }),
     * find or inject the id field in the ObjectPattern so we can reference it directly.
     */
    private tryAddItemIdFromDestructuredParams;
    private tryAddItemIdFromParentComponent;
    private findKeyWithId;
}
//# sourceMappingURL=collection-item-field-processor.d.ts.map