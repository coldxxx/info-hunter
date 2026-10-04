---
name: vercel-react-best-practices
description: React and React-framework engineering guidance for components, hooks, state, effects, data fetching, rendering, hydration, security boundaries, and browser bundles. Use when writing, reviewing, or refactoring React runtime code; do not use for non-React projects, backend services, infrastructure, or generic JavaScript/TypeScript work.
license: MIT
metadata:
  author: vercel
  version: '1.0.0'
---

# Vercel React Best Practices

Use this skill when writing, reviewing, or refactoring React runtime code,
including:

- components, pages, hooks, context, providers, state, and effects
- client-side data fetching, caching, subscriptions, events, and storage
- rendering, hydration, Suspense, resource loading, and browser behavior
- bundle and import choices that affect a React application
- React framework server/client boundaries, actions, and serialization

Apply the relevant guidance for correctness, security, maintainability, and
performance. This is not a blanket optimization pass.

Do not use it for non-React services, Node CLIs or scripts, infrastructure,
release tooling, documentation, or generic JavaScript/TypeScript utilities.
Do not assume Next.js, RSC, Server Actions, or another framework feature unless
the project actually uses it.

## Workflow

1. Identify the React runtime and framework used by the target project.
2. Select the relevant rule family and read only those files under `rules/`.
3. Apply rules supported by the code and task; do not force unrelated advice.
4. Preserve repository architecture and dependency policies.

## Quick Reference

### Eliminating Waterfalls

- `async-cheap-condition-before-await` - Check cheap sync conditions before awaiting
- `async-defer-await` - Move await into branches where actually used
- `async-parallel` - Use `Promise.all()` for independent operations
- `async-dependencies` - Start partially dependent work as early as possible
- `async-api-routes` - Start promises early and await late in API routes
- `async-suspense-boundaries` - Use Suspense to stream content

### Bundle Size

- `bundle-barrel-imports` - Avoid costly barrel imports
- `bundle-analyzable-paths` - Keep import and file-system paths statically analyzable
- `bundle-dynamic-imports` - Lazy-load heavy components
- `bundle-defer-third-party` - Defer non-critical third-party code
- `bundle-conditional` - Load modules only when a feature is active
- `bundle-preload` - Preload based on user intent

### Server-Side React

- `server-auth-actions` - Authenticate server mutations like API routes
- `server-cache-react` - Deduplicate request-scoped work
- `server-cache-lru` - Cache safe cross-request data
- `server-dedup-props` - Avoid duplicate RSC serialization
- `server-hoist-static-io` - Hoist static I/O
- `server-no-shared-module-state` - Keep request data out of shared module state
- `server-serialization` - Minimize server/client boundary data
- `server-parallel-fetching` - Parallelize component data fetching
- `server-parallel-nested-fetching` - Chain dependent fetches per item
- `server-after-nonblocking` - Defer non-blocking post-response work

### Client Data and Browser APIs

- `client-swr-dedup` - Deduplicate client requests
- `client-event-listeners` - Share global listeners
- `client-passive-event-listeners` - Keep scrolling responsive
- `client-localstorage-schema` - Version and minimize stored data

### Re-render Behavior

- `rerender-defer-reads` - Read dynamic state only where needed
- `rerender-memo` - Isolate expensive rendering work
- `rerender-memo-with-default-value` - Hoist non-primitive defaults
- `rerender-dependencies` - Narrow effect dependencies
- `rerender-derived-state` - Subscribe to derived state
- `rerender-derived-state-no-effect` - Derive state during render
- `rerender-functional-setstate` - Use functional state updates
- `rerender-lazy-state-init` - Lazily initialize expensive state
- `rerender-simple-expression-in-memo` - Avoid memoizing simple primitives
- `rerender-split-combined-hooks` - Split independent hook computations
- `rerender-move-effect-to-event` - Put interaction logic in handlers
- `rerender-transitions` - Mark non-urgent updates as transitions
- `rerender-use-deferred-value` - Defer expensive derived rendering
- `rerender-use-ref-transient-values` - Keep transient values in refs
- `rerender-no-inline-components` - Avoid nested component definitions

### Rendering

- `rendering-animate-svg-wrapper` - Animate an SVG wrapper
- `rendering-content-visibility` - Defer off-screen rendering
- `rendering-hoist-jsx` - Hoist static JSX
- `rendering-svg-precision` - Reduce excessive SVG precision
- `rendering-hydration-no-flicker` - Avoid client-only hydration flicker
- `rendering-hydration-suppress-warning` - Suppress only expected mismatches
- `rendering-activity` - Preserve frequently hidden UI state
- `rendering-conditional-render` - Avoid rendering falsy numeric values
- `rendering-usetransition-loading` - Use transition pending state
- `rendering-resource-hints` - Hint critical browser resources
- `rendering-script-defer-async` - Avoid render-blocking scripts

### JavaScript Used by React

- `js-batch-dom-css` - Batch DOM reads and writes
- `js-index-maps` - Index repeated lookups
- `js-cache-property-access` - Cache hot-loop property access
- `js-cache-function-results` - Cache repeated pure work
- `js-cache-storage` - Avoid repeated synchronous storage reads
- `js-combine-iterations` - Combine repeated array passes
- `js-length-check-first` - Check lengths before expensive comparisons
- `js-early-exit` - Return when the result is known
- `js-hoist-regexp` - Reuse regular expressions
- `js-min-max-loop` - Find extrema without sorting
- `js-set-map-lookups` - Use constant-time lookups
- `js-tosorted-immutable` - Preserve array immutability
- `js-flatmap-filter` - Map and filter in one pass
- `js-request-idle-callback` - Defer non-critical browser work

### Advanced Patterns

- `advanced-effect-event-deps` - Keep Effect Events out of dependencies
- `advanced-event-handler-refs` - Stabilize event subscriptions
- `advanced-init-once` - Initialize application-wide behavior once
- `advanced-use-latest` - Access current callbacks without resubscribing

Do not load `REFERENCE.md` unless the user explicitly requests an exhaustive
review or the targeted rule files are insufficient.
