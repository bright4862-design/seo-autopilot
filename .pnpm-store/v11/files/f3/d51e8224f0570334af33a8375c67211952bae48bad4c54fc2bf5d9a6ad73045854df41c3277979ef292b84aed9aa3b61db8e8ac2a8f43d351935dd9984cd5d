# Layer Dropdown Feature

## Overview

The layer dropdown lets users navigate the instrumented DOM hierarchy around a selected element. Clicking the chevron (`▾`) on an element's label reveals a dropdown showing **ancestors**, **siblings**, **the selected element**, and its **children** — all with depth-based indentation.

```
grandparent          (depth 0)
  parent             (depth 1)
    sibling-1        (depth 2)
    ★ selected       (depth 2)   ← highlighted in blue
      child-a        (depth 3)
      child-b        (depth 3)
    sibling-2        (depth 2)
```

Children are only expanded for the selected element, not for siblings.

---

## Architecture

```
┌─────────────┐     ┌────────────────┐     ┌────────────────┐
│  types.ts   │◄────│  controller.ts │────►│  dropdown-ui.ts│
│  consts.ts  │◄────│  (orchestrator)│     │  (rendering)   │
└─────────────┘     └───────┬────────┘     └────────────────┘
                            │
                      ┌─────▼──────┐
                      │  utils.ts  │
                      │ (DOM walk) │
                      └────────────┘
```

| File | Role |
|------|------|
| **types.ts** | `LayerInfo`, callback types, `LayerControllerDeps`, `LayerController` |
| **consts.ts** | Style maps, depth limits, chevron character, attribute name |
| **utils.ts** | DOM traversal — parent walking, sibling/descendant collection, depth assignment |
| **dropdown-ui.ts** | Creates the dropdown DOM, positions it, handles hover/click/keyboard |
| **controller.ts** | Stateful factory that wires everything together: build chain, show dropdown, handle selection |

---

## Data Model

### `LayerInfo`

```typescript
interface LayerInfo {
  element: Element;            // DOM reference
  tagName: string;             // lowercase tag name ("div", "button")
  selectorId: string | null;   // data-source-location or data-visual-selector-id
  depth?: number;              // visual indentation level (set during chain building)
}
```

An element is **instrumented** if it has `dataset.sourceLocation` or `dataset.visualSelectorId`. Only instrumented elements appear in the dropdown.

### Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `MAX_PARENT_DEPTH` | `2` | Max ancestor levels shown above selected |
| `MAX_CHILD_DEPTH` | `2` | Max descendant levels shown below selected |
| `DEPTH_INDENT_PX` | `10` | Extra left-padding per depth level |
| `LABEL_CHEVRON` | `" ▾"` | Appended to label text when dropdown is available |

---

## How the Chain Is Built (`utils.ts`)

`buildLayerChain(selectedElement)` is the entry point. It delegates to focused helper functions:

```typescript
export function buildLayerChain(selectedElement: Element): LayerInfo[] {
  const parents = collectInstrumentedParents(selectedElement);
  const chain: LayerInfo[] = [];
  const selfDepth = appendParentsWithDepth(chain, parents);

  const instrParent = getImmediateInstrParent(parents);
  if (instrParent) {
    const siblings = collectSiblings(instrParent, selectedElement);
    appendSiblingsWithSelected(chain, siblings, selectedElement, selfDepth);
  } else {
    appendSelfAndDescendants(chain, selectedElement, selfDepth);
  }

  return chain;
}
```

### Helper Functions

| Function | Purpose |
|----------|---------|
| `toLayerInfo(element, depth?)` | Convert a DOM element to a `LayerInfo` object |
| `collectInstrumentedParents(el)` | Walk up the DOM, collect up to `MAX_PARENT_DEPTH` instrumented ancestors, return outermost-first |
| `appendParentsWithDepth(chain, parents)` | Push parents into chain with `depth = index` (0, 1, ...), return count as `selfDepth` |
| `getImmediateInstrParent(parents)` | Return the innermost parent's DOM element, or `null` if `parents` is empty |
| `collectSiblings(parent, selectedEl)` | Call `getInstrumentedDescendants(parent, 1)` to get all first-level instrumented children in DOM order; safety-guard ensures `selectedEl` is always included |
| `appendSiblingsWithSelected(chain, siblings, selectedEl, depth)` | Iterate siblings at `selfDepth`; for the selected element, expand children via `appendSelfAndDescendants`; for others, just add at `selfDepth` |
| `appendSelfAndDescendants(chain, el, depth)` | Push element + its descendants (up to `MAX_CHILD_DEPTH` levels) with assigned depths |
| `getInstrumentedDescendants(parent, maxDepth)` | Recursive DOM walk — instrumented children increment depth, non-instrumented wrappers are transparent. Results in DOM order |
| `assignDescendantDepths(root, descendants, startDepth)` | Second-pass walk assigning `depth = startDepth + instrDepth - 1` using a `Set`/`Map` for O(1) lookups |

### Chain-Building Steps

**Step 1 — `collectInstrumentedParents`**: Walk up from `selectedElement.parentElement`, skipping `document.body` and `document.documentElement`. Collect up to `MAX_PARENT_DEPTH` instrumented ancestors, then reverse so outermost comes first.

**Step 2 — `appendParentsWithDepth`**: Each parent gets `depth = index` (0, 1, ...). The count becomes `selfDepth`.

**Step 3 — `getImmediateInstrParent`**: Extract the innermost instrumented parent's element. If `parents` is empty, returns `null` (root-level element).

**Step 4 — `collectSiblings`** (when parent exists): Call `getInstrumentedDescendants(instrParent, 1)` to get all first-level instrumented children of the parent in DOM order — this naturally includes the selected element among its siblings. A safety guard ensures the selected element is always present.

**Step 5 — `appendSiblingsWithSelected`**: Iterate siblings in DOM order, all at `selfDepth`. For the selected element only, delegate to `appendSelfAndDescendants` which also collects and appends children. For other siblings, just push at `selfDepth` with no child expansion.

**Fallback** (no parent): If no instrumented parent exists (root-level element), skip sibling collection and call `appendSelfAndDescendants` directly — just self + children.

---

## Controller Lifecycle (`controller.ts`)

`createLayerController(deps)` returns `{ attachToOverlay, cleanup }`.

### Dependency Injection

| Dep | Called When |
|-----|------------|
| `createPreviewOverlay(el)` | User hovers a dropdown item |
| `getSelectedElementId()` | Checking if hovered item is already selected |
| `selectElement(el)` | User clicks a dropdown item — performs selection, returns overlay |
| `onDeselect()` | Dropdown opens — temporarily clears selection for hover previews |

### `attachToOverlay(overlay, element)`

1. Extract the label `<div>` from the overlay.
2. Call `buildLayerChain(element)`.
3. **Guard**: if `layers.length <= 1`, return early — no chevron, no click handler. This is how the chevron is hidden when there's nothing to navigate to.
4. Append chevron via `enhanceLabelWithChevron(label)`.
5. Bind click handler to label (toggle behavior).

### Click Handler Flow

```
Label clicked
  ├─ Dropdown already open → close + reselect source element
  └─ Dropdown closed →
       1. Save source element (for Escape restore)
       2. deps.onDeselect() (clear selection visual)
       3. Register Escape key listener (capture phase)
       4. showDropdown(label, layers, callbacks...)
```

### State Transitions

```
CLOSED ──[click chevron]──► OPEN
OPEN   ──[click chevron]──► CLOSED (reselect original)
OPEN   ──[Escape]──────────► CLOSED (reselect original)
OPEN   ──[click item]─────► CLOSED → NEW ELEMENT SELECTED → reattach
OPEN   ──[click outside]──► CLOSED
```

Selection is recursive — `selectElementFromLayer` calls `deps.selectElement()`, gets a new overlay, and calls `attachToOverlay()` again on it.

---

## Dropdown UI (`dropdown-ui.ts`)

### Global State (singleton)

Only one dropdown can be active at a time:

```typescript
let activeDropdown: HTMLDivElement | null = null;
let outsideMousedownHandler: ((e: MouseEvent) => void) | null = null;
let activeOnHoverEnd: OnLayerHoverEnd | null = null;
let activeKeydownHandler: ((e: KeyboardEvent) => void) | null = null;
```

### `showDropdown(label, layers, currentSelectorId, onSelect, onHover, onHoverEnd)`

1. Close any existing dropdown.
2. Create dropdown element with all layer items.
3. Position it below the label (`offsetTop + offsetHeight + 2px` gap).
4. Append to the overlay's parent element.
5. Set up keyboard navigation and outside-click handler.

### Dropdown Item Rendering

Each `LayerInfo` becomes a `<div>` row:

- **Display name**: `layer.tagName` (e.g., "div", "section")
- **Indentation**: `paddingLeft = 12 + depth * 10` px
- **Active (selected) item**: blue text (`#526cff`), light blue bg (`#DBEAFE`), semi-bold
- **Hover state**: light gray bg (`#f1f5f9`)
- **Events**: `mouseenter` → preview, `mouseleave` → clear preview, `click` → select

### Keyboard Navigation

- **Arrow Down/Up**: Circular focus movement through items
- **Enter**: Select focused item
- All listeners use capture phase to intercept before bubbling

### Outside Click

Registered via `setTimeout(..., 0)` to prevent the opening click from immediately closing. Uses `mousedown` in capture phase for responsive dismissal.

---

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| No instrumented parent (root element) | Falls back to self + children only (no siblings) |
| Only child (no other siblings) | Siblings list contains just self — same result as before |
| Parent is `document.body`/`html` | Excluded by parent-walk guard, so `parents` is empty |
| `layers.length <= 1` | No chevron appended, no click handler attached |
| Element not in siblings list | Safety guard appends it |
| Non-instrumented wrapper elements | Walked through transparently during descendant collection |

---

## Data Flow Summary

```
User selects element
    ↓
attachToOverlay(overlay, element)
    ↓
buildLayerChain(element)
  ├── collectInstrumentedParents() → parents[] (outermost first)
  ├── appendParentsWithDepth() → chain gets parents at depth 0,1,...
  ├── getImmediateInstrParent() → instrParent or null
  ├── collectSiblings(instrParent) → siblings[] (DOM order)
  └── appendSiblingsWithSelected()
       ├── sibling → chain at selfDepth (no expansion)
       ├── ★ selected → appendSelfAndDescendants()
       │    ├── self at selfDepth
       │    ├── getInstrumentedDescendants(self, 2) → children[]
       │    └── assignDescendantDepths() → children get depth values
       └── sibling → chain at selfDepth (no expansion)
    ↓
LayerInfo[] with depth values
    ↓
layers.length > 1 ? enhanceLabelWithChevron() : return
    ↓
User clicks chevron → showDropdown()
    ↓
createDropdownElement(layers, currentId, callbacks)
  └── createDropdownItem() for each layer (indented by depth)
    ↓
User hovers item → showLayerPreview() → preview overlay
User clicks item → selectElementFromLayer() → new selection → reattach
User presses Escape → closeDropdown() → reselect original
```
