import { parse } from "@babel/parser";
import { default as traverse } from "@babel/traverse";
import { default as generate } from "@babel/generator";
import * as t from "@babel/types";
import { JSXProcessor } from "./jsx-processor.js";
import { JSXUtils } from "./jsx-utils.js";
import { TAILWIND_CDN_SRC } from "./consts.js";
export function visualEditPlugin() {
    return {
        name: "visual-edit-transform",
        // Dev SERVER only: the injected data-* markers are consumed by the
        // visual-edit agent in the live preview, which vite serves — never by
        // build output. Gating on mode alone also caught `vite build --mode
        // development` (the platform's validation build), where instrumenting
        // user code is pure risk: an injection bug there fails the build on
        // code that doesn't exist on disk.
        apply: (config, env) => env.command === "serve" && config.mode === "development",
        enforce: "pre",
        order: "pre",
        transformIndexHtml(html) {
            const tailwindScript = `    <!-- Tailwind CSS CDN for visual editing -->\n    <script src="${TAILWIND_CDN_SRC}"></script>\n  `;
            return html.replace("</head>", tailwindScript + "</head>");
        },
        transform(code, id) {
            if (id.includes("node_modules") || id.includes("visual-edit-agent")) {
                return null;
            }
            if (!id.match(/\.(jsx?|tsx?)$/)) {
                return null;
            }
            const filename = extractFilename(id);
            try {
                const ast = parse(code, {
                    sourceType: "module",
                    plugins: [
                        "jsx",
                        "typescript",
                        "decorators-legacy",
                        "classProperties",
                        "objectRestSpread",
                        "functionBind",
                        "exportDefaultFrom",
                        "exportNamespaceFrom",
                        "dynamicImport",
                        "nullishCoalescingOperator",
                        "optionalChaining",
                        "asyncGenerators",
                        "bigInt",
                        "optionalCatchBinding",
                        "throwExpressions",
                    ],
                });
                JSXUtils.init(t);
                const processor = new JSXProcessor(t, filename);
                traverse.default(ast, {
                    JSXElement(path) {
                        const jsxElement = path.node;
                        if (t.isJSXFragment(jsxElement))
                            return;
                        processor.processJSXElement(path.get("openingElement"));
                    },
                });
                const result = generate.default(ast, {
                    compact: false,
                    concise: false,
                    retainLines: true,
                });
                return {
                    code: result.code,
                    map: null,
                };
            }
            catch (error) {
                console.error("Failed to add source location to JSX:", error);
                return {
                    code: code,
                    map: null,
                };
            }
        },
    };
}
// Emit the canonical real path (src/pages/Home.jsx) the backend and sandbox use, NOT a
// legacy alias (pages/Home). The path is anchored on the last "src" segment with the
// extension retained, so consumers get the file's true sandbox path directly.
function extractFilename(id) {
    // Drop any Vite query suffix (e.g. "?v=...") and normalize separators.
    const cleanId = id.split("?")[0].replace(/\\/g, "/");
    const parts = cleanId.split("/");
    // Anchor on the LAST "src" segment so a "src" elsewhere in the absolute path
    // (e.g. a user's home dir) can't mis-anchor. base44 apps keep all source under src/.
    const srcIndex = parts.lastIndexOf("src");
    if (srcIndex >= 0) {
        return parts.slice(srcIndex).join("/"); // src/pages/Home.jsx, src/Layout.jsx, src/components/ui/Card.tsx
    }
    // Fallback: file not under src/ — use the bare filename (extension kept).
    return parts[parts.length - 1] ?? "";
}
//# sourceMappingURL=visual-edit-plugin.js.map