# Lessons & Gotchas

**Status:** Append-only log of mistakes Claude Code has made on this project, and the fix — so
they don't repeat. Referenced by `CLAUDE.md`. Keep entries short and specific.

## How to use this file

When Claude Code gets something wrong and you correct it, end the correction with:
"Add this to docs/LESSONS.md so you don't make that mistake again." Claude writes the entry.

## Format

```
### [Area] Short description of the mistake
**Wrong:** what Claude did
**Right:** what it should do instead
```

## Entries

### [Frontend/tooling] Vite 8 breaks the Vitest toolchain
**Wrong:** Kept `create-vite`'s defaults (Vite 8 + `@vitejs/plugin-react` 6). Vitest 3.2 pulled
its own Vite 7, producing two Vite copies — `vitest/config` typed `test` against Vite 7 while the
app's `defineConfig` was Vite 8, so plugin types clashed and the config wouldn't type-check.
**Right:** Pin `vite` to `^7` and `@vitejs/plugin-react` to `^5` until Vitest supports Vite 8.
Keep a single Vite version across the app and the test runner (`npm ls vite` should show one).

### [Frontend/shadcn] The default shadcn style is Base UI, not Radix
**Wrong:** Composed buttons with Radix's `asChild` prop (`<Button asChild><Link/></Button>`).
**Right:** The current shadcn style ("base-nova") renders on `@base-ui/react`. Compose with the
`render` prop instead — `<Button render={<Link to="…" />}>label</Button>` — and add
`nativeButton={false}` when the rendered element is not a real `<button>` (e.g. a link).
