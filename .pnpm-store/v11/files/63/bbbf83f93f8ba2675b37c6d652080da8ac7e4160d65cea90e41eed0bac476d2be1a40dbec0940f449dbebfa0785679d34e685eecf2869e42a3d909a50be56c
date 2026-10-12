import type { NodePath } from "@babel/traverse";
import type * as t from "@babel/types";
export declare class DataItemIdProcessor {
    private types;
    private attributeUtils;
    private expressionUtils;
    private pathUtils;
    constructor(types: typeof t);
    process(path: NodePath<t.JSXOpeningElement>): void;
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
    processRootElement(path: NodePath<t.JSXOpeningElement>): void;
    private hasSpreadAttribute;
    /**
     * Returns true when `fn` is a direct callback argument to a `.map()` or
     * `.flatMap()` call — i.e. the function is an iteration callback, not a
     * component definition. This prevents injecting prop-forwarding into
     * patterns like `[...Array(3)].map((_, i) => <div />)` where the first
     * param may be `undefined`.
     */
    private isMapCallbackFunction;
    private functionContainsMapCall;
    /**
     * Returns an expression for reading `data-collection-item-id` from the component's
     * props, modifying the function's params destructuring if necessary.
     */
    private buildCollectionItemIdExpression;
    private findKeyAttribute;
    private extractKeyExpression;
}
//# sourceMappingURL=collection-item-id-processor.d.ts.map