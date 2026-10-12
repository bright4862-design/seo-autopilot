# visual-edit-plugin.ts - Deep Dive

## What Is This?

A **Vite plugin** that instruments every JSX element in React components with metadata attributes at build time. This enables a **live visual editing** experience for React apps running inside sandboxed iframes.

It adds two HTML `data-*` attributes to every JSX element:
- `data-source-location` - maps the element back to its source file, line, and column
- `data-dynamic-content` - flags whether the element contains runtime-generated content

```jsx
// BEFORE (source code):
<Button className="px-4">Click me</Button>

// AFTER (served to browser):
<Button
  data-source-location="src/components/Button.jsx:42:8"
  data-dynamic-content="false"
  className="px-4"
>Click me</Button>
```

---

## When Does It Run?

### Activation Conditions (ALL must be true)

| Condition | Where | Why |
|-----------|-------|-----|
| `MODAL_SANDBOX_ID` env var is set | `index.ts:8` | Only runs inside Modal sandbox containers |
| Dev **server** in `"development"` mode | `apply: (config, env) => env.command === "serve" && config.mode === "development"` | The injected `data-*` markers are only consumed by the visual-edit agent in the live preview, which the dev server serves. Builds never use them — including `vite build --mode development` (the platform's validation build), where instrumenting user code once produced compile errors on code that wasn't on disk |
| File is `.js`, `.jsx`, `.ts`, or `.tsx` | `id.match(/\.(jsx?\|tsx?)$/)` | Only JSX-capable files |
| File is NOT in `node_modules` | `id.includes("node_modules")` | Skip third-party code |
| File is NOT `visual-edit-agent` | `id.includes("visual-edit-agent")` | Don't instrument the agent itself |

### Execution Timeline

```
1. npm run dev            (dev SERVER only — `vite build` never registers this plugin,
                           regardless of mode)
2. Vite starts, loads plugin config
3. index.ts checks: isRunningInSandbox = !!process.env.MODAL_SANDBOX_ID
4. If true → registers visualEditPlugin() in the plugin pipeline
5. Vite dev server starts
   ├── transformIndexHtml runs ONCE → injects Tailwind CDN into <head>
   └── transform runs PER FILE when browser requests it
       ├── Babel parses code → AST
       ├── Traverse finds all JSXElement nodes
       ├── Adds data-source-location + data-dynamic-content attributes
       ├── Babel generates modified code
       └── Serves transformed code to browser
6. Browser renders components with data-* attributes in the DOM
7. sandbox-mount-observer.js detects instrumented elements → notifies parent
8. visual-edit-agent loads → enables hover/click/edit interactions
```

### Plugin Ordering

- `enforce: "pre"` + `order: "pre"` ensures this runs **before** all other Vite transforms
- This is critical because the plugin needs to process raw JSX before any other plugin modifies it

---

## How It Works - The Transform Logic

### Step 1: Filename Extraction (lines 123-173)

Builds the canonical real source path (the path the backend and sandbox use) from the full file path:

```
/Users/dev/project/src/pages/About/index.tsx  →  "src/pages/About/index.tsx"
/Users/dev/project/src/components/ui/Button.tsx  →  "src/components/ui/Button.tsx"
/Users/dev/project/src/Layout.tsx  →  "src/Layout.tsx"
```

**Rules:**
- Anchors on the last `src/` segment and keeps everything from there, preserving nested structure
- The file extension is retained (`.jsx`/`.tsx`/`.js`/`.ts`)
- Files not under `src/` → just the filename (extension kept)

### Step 2: AST Parsing (lines 177-196)

Uses `@babel/parser` with 15 syntax plugins to handle any modern TypeScript/React code:

| Plugin | Handles |
|--------|---------|
| `jsx` | JSX syntax (`<Component />`) |
| `typescript` | TypeScript type annotations |
| `decorators-legacy` | `@decorator` syntax |
| `classProperties` | Class field declarations |
| `objectRestSpread` | `...spread` syntax |
| `optionalChaining` | `?.` operator |
| `nullishCoalescingOperator` | `??` operator |
| `dynamicImport` | `import()` expressions |
| `asyncGenerators` | `async function*` |
| `bigInt` | `123n` literals |
| `optionalCatchBinding` | `catch {}` without param |
| `throwExpressions` | `throw` as expression |
| `functionBind` | `::` bind operator |
| `exportDefaultFrom` | `export v from "mod"` |
| `exportNamespaceFrom` | `export * as ns from "mod"` |

**Why Babel over regex?** AST parsing is accurate and won't break on edge cases like JSX-in-strings or commented-out JSX.

### Step 3: AST Traversal (lines 199-246)

Visits every `JSXElement` node. For each one:

1. **Skip JSX Fragments** (`<>...</>`) - they have no opening tag to attach attributes to
2. **Skip already-instrumented elements** - checks if `data-source-location` already exists (idempotent)
3. **Extract location** from AST node: `openingElement.loc.start` gives `{ line, column }`
4. **Detect dynamic content** via `checkIfElementHasDynamicContent()` (see below)
5. **Insert BOTH attributes** at position 0 of the attributes array (appear first in output)

**`data-dynamic-content` is added to EVERY JSX element unconditionally** — it is always present alongside `data-source-location`. The only thing that changes is the value: `"true"` if the element's own attributes OR children contain any dynamic patterns (expressions, props, function calls, spread attributes, etc.), or `"false"` if everything is purely static. This means every element in the DOM carries both attributes, so the visual editor can always check any element's dynamic status without extra logic.

### Step 4: Dynamic Content Detection (lines 8-98)

`checkIfElementHasDynamicContent(jsxElement)` determines whether to set `data-dynamic-content` to `"true"` or `"false"`.

#### Two-phase detection: attributes first, then children

The function checks in two phases:

1. **Own attributes** (lines 91-106): Iterates `jsxElement.openingElement.attributes`. Spread attributes (`{...props}`) are always dynamic. For regular attributes, the attribute value is checked via `traverseNode` — so `src={photo.url}` is detected as dynamic (JSXExpressionContainer with a non-literal expression), while `src="static.png"` is not (StringLiteral).

2. **Children** (lines 108-112): Iterates `jsxElement.children` and recursively traverses all descendants.

Both phases use early exit — if the attribute check already found dynamic content, the children check is skipped entirely.

```jsx
// "true" — src={url} is a dynamic OWN attribute
<img src={url} />

// "true" — {name} is a dynamic CHILD
<div>{name}</div>

// "true" — spread attribute is always dynamic
<Component {...props} />

// "false" — static attribute + static child
<div className="box">Hello</div>
```

#### What counts as dynamic (the `checkNodeForDynamicContent` function)

Each attribute value and child node (and recursively all descendants) is checked against these patterns in order:

| # | Check | Matches | Example |
|---|-------|---------|---------|
| 1 | `isJSXExpressionContainer` + expression is NOT a literal | Any `{expression}` where the expression isn't a string/number/boolean literal | `{variable}`, `{obj.prop}`, `{fn()}` |
| 2 | `isTemplateLiteral` with `expressions.length > 0` | Template literals with interpolation | `` `Hello ${name}` `` |
| 3 | `isMemberExpression` | Property access | `props.title`, `state.value` |
| 4 | `isCallExpression` | Function/method calls | `getData()`, `arr.map()` |
| 5 | `isConditionalExpression` | Ternary operators | `x ? "a" : "b"` |
| 6 | `isIdentifier` + name contains keyword | Identifiers whose name includes (case-sensitive substring match): `props`, `state`, `data`, `item`, `value`, `text`, `content` | `dataItems` matches, but `userData` does NOT (capital D) |

Check #1 is the main workhorse — it catches most dynamic patterns because in JSX, dynamic values are always wrapped in `{...}`.

Checks #3-#6 catch patterns found during **deep recursion** into nested AST structures.

#### The recursive traversal

`traverseNode` (line 69) recursively visits ALL properties of each AST node (`Object.keys(node).forEach`). This means once a node is passed to `traverseNode`, it checks every nested structure — child elements, their attributes, their children, etc.

Both the element's own attributes AND its children tree are checked consistently:

```jsx
// "true" — div's OWN dynamic attribute is checked
<div className={styles.foo}>Hello</div>

// "true" — recursion also reaches nested span's attributes
<div><span className={styles.foo}>text</span></div>
```

#### Concrete examples

```jsx
// "true" — {name} is a non-literal expression in children
<h1>{name}</h1>

// "false" — {"Hello"} is a literal expression (string literal)
<h1>{"Hello"}</h1>

// "false" — {} is an empty expression (JSXEmptyExpression)
<div>{}</div>

// "false" — {42} is a literal expression (numeric literal)
<span>{42}</span>

// "true" — {user.name} is a MemberExpression (non-literal)
<p>{user.name}</p>

// "true" — {getLabel()} is a CallExpression (non-literal)
<button>{getLabel()}</button>

// "true" — ternary is a ConditionalExpression (non-literal)
<span>{active ? "On" : "Off"}</span>

// "true" — `Hello ${name}` is a TemplateLiteral with expressions
<div>{`Hello ${name}`}</div>

// "true" — src={imageUrl} is a dynamic own attribute
<img src={imageUrl} />

// "true" — spread attribute is always dynamic
<Component {...props} />

// "true" — recursion also reaches nested img's src attribute
<div><img src={imageUrl} /></div>

// "false" — no children, no dynamic attributes
<br />

// "true" — deeply nested dynamic content found
<div><ul><li>{item.name}</li></ul></div>
```

#### Early exit optimization

The function stops as soon as any dynamic pattern is found (line 71: `hasDynamicContent = true; return;` and line 93: `if (hasDynamicContent) return;`).

### Step 5: Code Generation (lines 249-258)

```typescript
generate.default(ast, {
  compact: false,    // Don't minify
  concise: false,    // Keep readable formatting
  retainLines: true, // Preserve original line numbers
})
```

`retainLines: true` is critical - it ensures the generated code has the same line numbers as the original, so the `data-source-location` values remain accurate and debugger breakpoints still work.

### Error Handling (lines 259-265)

If parsing or transformation fails, the plugin **returns the original code unchanged**. Errors are logged but never break the build.

---

## Why Do We Need This?

### Problem 1: Source Code Mapping in Iframes

In a sandboxed iframe, clicking a rendered element doesn't tell you which React component file created it. The `data-source-location` attribute creates a direct link from the rendered DOM back to the source code.

### Problem 2: Dynamic vs. Static Content Awareness

A visual editor needs to know:
- **Static elements** (`data-dynamic-content="false"`) → safe to edit directly, changes will persist
- **Dynamic elements** (`data-dynamic-content="true"`) → content comes from variables/props/state, editing the DOM will be overwritten on next render

This prevents users from wasting time editing elements that will reset.

### Problem 3: Cross-Window Communication

The parent window (editor UI) and the sandbox iframe can't share a DOM. The `data-*` attributes serve as a **stable identifier system** that both sides understand:

```
Parent Window (Editor UI)                    iframe Sandbox (React App)
─────────────────────────                    ──────────────────────────
"Select element src/components/Button.jsx:42:8"  →   querySelector('[data-source-location="src/components/Button.jsx:42:8"]')
                                         ←   "Element found: classes='px-4', isDynamic=false"
"Update classes to 'px-6 py-3'"          →   element.setAttribute("class", "px-6 py-3")
```

### Problem 4: Multi-Instance Elements

React can render the same component multiple times (e.g., list items). The `findElementsById()` utility finds ALL elements with the same `data-source-location`, enabling bulk updates across all instances.

### Problem 5: Tailwind CSS Support

The `transformIndexHtml` hook injects the Tailwind CSS CDN, enabling visual editing tools to apply Tailwind utility classes to elements in real time.

---

## Full System Architecture

```
                    ┌──────────────────────────────┐
                    │     Parent Window (Editor)    │
                    │                               │
                    │  - Shows element inspector    │
                    │  - Provides class editor      │
                    │  - Shows source location      │
                    │  - Content editing UI         │
                    │  - Attribute editing UI       │
                    └──────────┬───────────────────┘
                               │ postMessage (both ways)
                               │
          ┌────────────────────┴───────────────────────┐
          │            iframe Sandbox                    │
          │                                             │
          │  ┌───────────────────────────────────────┐  │
          │  │   visual-edit-agent.ts (runtime)      │  │
          │  │   - Hover/click event handlers        │  │
          │  │   - Overlay positioning               │  │
          │  │   - DOM query & updates               │  │
          │  │   - postMessage bridge                │  │
          │  └───────────────────────────────────────┘  │
          │                    ▲                         │
          │                    │ reads data-* attributes │
          │  ┌───────────────────────────────────────┐  │
          │  │   React App (DOM)                     │  │
          │  │                                       │  │
          │  │   <div data-source-location=          │  │
          │  │        "src/pages/Home.jsx:10:4"      │  │
          │  │        data-dynamic-content="true">   │  │
          │  │     {greeting}                        │  │
          │  │   </div>                              │  │
          │  └───────────────────────────────────────┘  │
          │                    ▲                         │
          │                    │ build-time transform    │
          │  ┌───────────────────────────────────────┐  │
          │  │   visual-edit-plugin.ts (Vite plugin) │  │
          │  │   - Parses JSX with Babel             │  │
          │  │   - Injects data-* attributes         │  │
          │  │   - Detects dynamic content           │  │
          │  │   - Injects Tailwind CDN              │  │
          │  └───────────────────────────────────────┘  │
          └─────────────────────────────────────────────┘
```

### Messages: Parent → iframe

| Message Type | Purpose |
|-------------|---------|
| `toggle-visual-edit-mode` | Enable/disable visual editing cursor |
| `update-classes` | Change CSS classes on selected element |
| `update-content` | Change text content of selected element |
| `update-attribute` | Change an attribute (e.g., `src`) on selected element |
| `unselect-element` | Remove selection overlay |
| `refresh-page` | Reload the iframe |
| `request-element-position` | Ask for current element coordinates |

### Messages: iframe → Parent

| Message Type | Purpose |
|-------------|---------|
| `element-selected` | User clicked an element - sends full element info |
| `element-position-update` | Element moved (scroll/resize) - updated coordinates |
| `visual-edit-agent-ready` | Agent loaded and listening |
| `sandbox:onMounted` | Instrumented elements appeared in DOM |
| `sandbox:onUnmounted` | No instrumented elements found |

---

## Related Files

| File | Role |
|------|------|
| `src/index.ts` | Registers the plugin (conditionally, in sandbox mode) |
| `src/html-injections-plugin.ts` | Injects agent scripts and observer scripts into HTML |
| `src/injections/visual-edit-agent.ts` | Runtime agent in the iframe (hover, click, overlay, postMessage) |
| `src/injections/sandbox-mount-observer.ts` | Detects when instrumented elements mount in DOM |
| `src/injections/utils.ts` | `findElementsById()`, `updateElementClasses()` utilities |
| `tests/visual-edit-agent.test.ts` | Unit tests for element finding and class updates |

### Seeded Image components

A `data-base44-image` wrapper is one logical image edit target. Its classes and
source location refer to the app's `<Image>` call site; report its tag as `IMG`
for the image toolbar and layer labels. Read `src` from `data-base44-image-src`,
which preserves the original prop rather than the inner image's transformed CDN
URL. The template keeps all instrumentation on the wrapper and suppresses source
locations on the placeholder and main image.

For `src` edits, dispatch `base44:image-replace` with `detail: { src }` on the
wrapper, retaining the selected-array-index filter. The template updates React
state so the replacement survives responsive resizes. Native images continue to
use direct attribute updates. Publish this support before seeding a template
that uses the wrapper contract.
