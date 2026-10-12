import { CollectionIdProcessor } from "./processors/collection-id-processor.js";
import { DataItemIdProcessor } from "./processors/collection-item-id-processor.js";
import { DataItemFieldProcessor } from "./processors/collection-item-field-processor.js";
import { StaticArrayProcessor } from "./processors/static-array-processor.js";
import { DOCUMENT_ELEMENTS } from "./consts.js";
export class JSXProcessor {
    types;
    filename;
    collectionIdProcessor;
    dataItemIdProcessor;
    dataItemFieldProcessor;
    staticArrayProcessor;
    constructor(types, filename) {
        this.types = types;
        this.filename = filename;
        this.collectionIdProcessor = new CollectionIdProcessor(types);
        this.dataItemIdProcessor = new DataItemIdProcessor(types);
        this.dataItemFieldProcessor = new DataItemFieldProcessor(types);
        this.staticArrayProcessor = new StaticArrayProcessor(types);
    }
    processJSXElement(path) {
        if (this.hasAttribute(path, "data-source-location"))
            return;
        const { name } = path.node;
        if (this.types.isJSXIdentifier(name) && DOCUMENT_ELEMENTS.includes(name.name))
            return;
        this.addSourceLocationAttribute(path);
        this.addDynamicContentAttribute(path);
        this.collectionIdProcessor.process(path);
        this.dataItemIdProcessor.process(path);
        this.dataItemIdProcessor.processRootElement(path);
        this.dataItemFieldProcessor.process(path);
        this.staticArrayProcessor.process(path);
    }
    addSourceLocationAttribute(path) {
        const { line, column } = path.node.loc?.start || { line: 1, column: 0 };
        const value = `${this.filename}:${line}:${column}`;
        path.node.attributes.unshift(this.types.jsxAttribute(this.types.jsxIdentifier("data-source-location"), this.types.stringLiteral(value)));
    }
    addDynamicContentAttribute(path) {
        const parentElement = path.parentPath;
        if (!parentElement?.isJSXElement())
            return;
        const isDynamic = this.checkIfElementHasDynamicContent(parentElement.node);
        const sourceLocIdx = path.node.attributes.findIndex((attr) => this.types.isJSXAttribute(attr) &&
            this.types.isJSXIdentifier(attr.name) &&
            attr.name.name === "data-source-location");
        path.node.attributes.splice(sourceLocIdx + 1, 0, this.types.jsxAttribute(this.types.jsxIdentifier("data-dynamic-content"), this.types.stringLiteral(isDynamic ? "true" : "false")));
    }
    hasAttribute(path, name) {
        return path.node.attributes.some((attr) => this.types.isJSXAttribute(attr) &&
            this.types.isJSXIdentifier(attr.name) &&
            attr.name.name === name);
    }
    checkIfElementHasDynamicContent(jsxElement) {
        let hasDynamicContent = false;
        const checkNode = (node) => {
            if (this.types.isJSXExpressionContainer(node)) {
                const expression = node.expression;
                if (this.types.isJSXEmptyExpression(expression))
                    return false;
                if (!this.types.isLiteral(expression))
                    return true;
            }
            if (this.types.isTemplateLiteral(node) &&
                node.expressions.length > 0) {
                return true;
            }
            if (this.types.isMemberExpression(node))
                return true;
            if (this.types.isCallExpression(node))
                return true;
            if (this.types.isConditionalExpression(node))
                return true;
            if (this.types.isIdentifier(node)) {
                const dynamicNames = [
                    "props",
                    "state",
                    "data",
                    "item",
                    "value",
                    "text",
                    "content",
                ];
                if (dynamicNames.some((name) => node.name.includes(name))) {
                    return true;
                }
            }
            return false;
        };
        const traverseNode = (node) => {
            if (hasDynamicContent)
                return;
            if (checkNode(node)) {
                hasDynamicContent = true;
                return;
            }
            for (const key of Object.keys(node)) {
                if (hasDynamicContent)
                    return;
                const value = node[key];
                if (Array.isArray(value)) {
                    for (const child of value) {
                        if (child && typeof child === "object" && "type" in child) {
                            traverseNode(child);
                        }
                    }
                }
                else if (value && typeof value === "object" && "type" in value) {
                    traverseNode(value);
                }
            }
        };
        const attributes = jsxElement.openingElement?.attributes || [];
        for (const attr of attributes) {
            if (hasDynamicContent)
                break;
            if (this.types.isJSXSpreadAttribute(attr)) {
                hasDynamicContent = true;
                break;
            }
            if (this.types.isJSXAttribute(attr) && attr.value) {
                traverseNode(attr.value);
            }
        }
        for (const child of jsxElement.children) {
            if (hasDynamicContent)
                break;
            traverseNode(child);
        }
        return hasDynamicContent;
    }
}
//# sourceMappingURL=jsx-processor.js.map