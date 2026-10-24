# GUI Guidelines — GenAI GUI (frontend)

Version 0.2 (T2I_main is the first real backend module; other generation tabs still use mock
state). This is the authoritative reference for building **any new module GUI**
(Image→Image, Face Swap, Video, Audio, ...) in `frontend/src`. Follow it in every session so all
modules feel like one product. If something here blocks a design, change this doc in the same PR.

---

## 0. TL;DR — new module checklist

1. Create the canonical module frontend under
   `backend/app/GenModules/<module-id>/frontend/` (page, `types.ts`, `api.ts`, store,
   settings panel, result card, README). Copy it to `frontend/src/features/<module-id>/`.
2. Register the route in `frontend/src/router/index.ts` and the sidebar entry in
   `frontend/src/lib/nav.ts`.
3. Use **design tokens only** (no raw colors), reuse `components/ui/*`, and use only the fixed
   z-index scale (§3).
4. New generation modules own a **module Pinia store** for the durable form, catalog
   reconciliation, job polling and actions (§6). Do not keep a durable form in page-local state.
5. Persist the module form under a versioned key (`genai.<module>.form.v1`), flush on unload,
   and reconcile it against the live pack. Give every settings panel a reset action plus one
   global reset.
6. Chat-style modules use the compact chat workspace pattern: prompt bubbles + result cards in a
   scroller, settings in a drawer, composer pinned at the bottom. T2I_main is the reference.
7. Show engine-dependent state honestly. Report every GUI run through
   `engine.jobStarted()` / `engine.jobFinished()` (deduplicated) so the top-bar queue pill flips
   to **Working** by itself (§7). Never build per-module busy pills.
8. Generated media must be saved through the library and discoverable in Gallery. Reuse the
   shared `MediaViewer` for fullscreen/viewer needs; the Gallery must sync on mount.
9. Engine content: if the module needs ComfyUI custom nodes / model files, ship a
   `requirements.json` — Settings → Engine content audits it read-only against the user's
   ComfyUI install (`docs/COMFYUI_CONTENT.md` §2). Don't duplicate that audit in the module page.
10. Check light **and** dark theme, plus a narrow window width.
11. `npm run typecheck` and `npm run build` (the latter includes `vue-tsc`) must pass and the
    console must be clean before finishing.

---

## 1. Folder architecture

```
backend/app/GenModules/<module-id>/
├─ manifest.json              identity, nav id, API prefix, frontend entry
├─ requirements.json          optional ComfyUI nodes / model files
├─ backend/                   schema, service, API, pack, workflows
└─ frontend/                  canonical frontend contract (copied into runtime)
   ├─ README.md
   ├─ types.ts
   ├─ api.ts
   ├─ store.ts
   ├─ <Module>Page.vue
   ├─ <Module>SettingsPanel.vue
   └─ <Module>GenerationCard.vue

frontend/src/
├─ components/                shared library - reuse before you rebuild
│  ├─ ui/                     primitives (buttons, inputs, modal, popover, chips, ...)
│  ├─ layout/                 AppShell, SideNav, TopBar, ResourcesPopover
│  ├─ media/                  MediaViewer + shared item contract
│  └─ chat/                   StageTimeline, mock ChatThread/ComposerBar/ResultCard
├─ features/                  ONE FOLDER PER MODULE - self-contained
│  └─ <module-id>/            runtime copy of the canonical module frontend
├─ stores/                    Pinia: ui, settings, engine, jobs, library, chat, content
├─ lib/                       api.ts, download.ts, nav.ts, format.ts, ...
└─ router/                    routes
```

Rules:

- A module may import from `components/*`, `stores/*`, `lib/*` — **never from another module's
  folder**.
- If a second module needs the same piece, promote it to the right `components/<category>/`
  folder. That is how `MediaViewer` became shared; do not copy it into another feature folder.
- Canonical module files live next to the module backend. Runtime copies are required by the
  Vite build, but the canonical copy is the contract. Update both in the same change.
- Mock generation tabs still key per-tab state by `tabId` in the chat store. New real modules use
  their own module store and must not depend on the mock chat runner.

Current status: `text-to-image` is backed by the real T2I_main API and is the reference
implementation. `gallery`, `jobs` and `settings` are backend-backed common pages; `presets`,
`characters` and `game-assets` still use mock state; the structured "soon" pages are
`image-to-image`, `edit-image`, `face-swap`, `influencer`, `video/*`, `audio/*`.

## 2. Theming & tokens

- Two themes: `pastel-dark` (default) and `pastel-light`; four accents (lavender, mint, peach,
  sky). Switch via `useUiStore().setTheme()` / `setAccent()`. Persisted in `localStorage`
  (`genai.ui.v1`).
- All colors are Tailwind utilities generated from the `@theme` block in `src/styles/main.css`.
  **Use only these semantic classes:**

| Purpose | Classes |
| --- | --- |
| App background | `bg-bg` |
| Cards / panels | `bg-surface`, `bg-surface-2` |
| Borders | `border-border` |
| Text | `text-text`, `text-muted` |
| Accent (active / primary) | `bg-accent`, `bg-accent-soft`, `text-accent`, `text-accent-contrast` |
| States | `bg-success`/`text-success`, `text-warn`, `text-danger` |
| Decorative pastels (placeholders, RAM bar, art) | `sky`, `mint`, `lavender`, `peach`, `rose` |

- **Never** use raw hex, `bg-white`, `text-black` or default Tailwind palette colors in UI chrome.
  Documented exceptions:
  - the favorite star (`fill-amber-300 text-amber-300`);
  - media overlays that sit directly on top of arbitrary images (Gallery card labels/actions,
    result-card actions, `MediaViewer` chrome). These use black/white translucency so they remain
    readable over any image in both app themes. Keep them scoped to media surfaces, never in
    ordinary page chrome;
  - modal/drawer backdrops (`AppModal`, the mobile settings drawer) may use a black scrim; the
    panel/content itself must use semantic tokens.
- Shape conventions: cards `rounded-2xl border border-border bg-surface p-4` (page sections
  `p-5`), controls `rounded-xl`, chips/pills `rounded-full`, the composer `rounded-3xl`.
- The global `:focus-visible` ring in `main.css` handles keyboard focus — don't re-implement it.
- Gallery placeholders/generated missing media use deterministic SVGs from `lib/placeholder.ts`;
  never add binary assets.

## 3. Z-index scale (do not invent new levels)

| Layer | Value | Owner |
| --- | --- | --- |
| Top bar | `z-30` | `components/layout/TopBar.vue` |
| Mobile settings drawer overlay | `z-30` | module page |
| Dropdowns / popovers / tooltips / mobile settings drawer | `z-40` | `components/ui/AppPopover.vue`, module page |
| Modals / `MediaViewer` lightbox | `z-50` | `components/ui/AppModal.vue`, `components/media/MediaViewer.vue` (both teleport to body) |
| Toasts | `z-60` | `components/ui/ToastHost.vue` |

Lessons already paid for:

- The top bar must **not** use `overflow-hidden` — it clips popovers (this bit us once).
  Use `min-w-0` + `truncate` on the title and `shrink-0` on pills instead.
- Popovers are **not** portaled; keep them inside a `relative` wrapper (`AppPopover` handles this).
- The media viewer and modal must be teleported to `body`; nesting them inside the shell's
  scroll container causes clipping and stacking-context bugs.

## 4. Component catalog (reuse — don't rebuild)

**`components/ui/`**
`AppButton` (variants: primary / soft / ghost / danger · sizes sm/md/lg) ·
`AppInput` · `AppTextarea` · `AppSelect` · `AppSwitch` · `AppSlider` · `Chip` · `Badge` ·
`StatusDot` (ok / off / warn / busy) · `AppModal` (v-model, `title`, `subtitle`, `#footer`) ·
`AppPopover` (v-model, `align`, `up`, `width`, `#trigger`) · `AppTabs` · `Section` ·
`EmptyState` · `ComingSoon` · `ToastHost` (mounted once in `App.vue`).

**`components/layout/`**
`AppShell` · `SideNav` · `TopBar` · `ResourcesPopover`.

**`components/media/`**
`MediaViewer` (v-model `open`/`index`, `items`, `title`, `downloadable`, `showThumbs`, `info`,
slots `actions` and `info`) + `types.ts` (`MediaViewerItem`, `MediaViewerMeta`). Supports
images, video and audio, fullscreen, keyboard navigation, zoom and a metadata panel.

**`components/chat/`**
`StageTimeline` (backend job stages) · `ChatThread` · `ComposerBar` · `ResultCard` ·
`AttachmentCard` · `AttachPickerModal` · `AdvancedModal` · `UserBubble`. The legacy chat/runner
pieces remain for mock tabs; real modules should not route jobs through them.

Global habits:

- Interactive elements get `cursor-pointer`; disabled state `disabled:opacity-45`.
- Feedback goes through `useUiStore().toast(msg, 'success' | 'info' | 'warn' | 'error')` — never
  `alert()`.
- Mock-action copy: `"... arrives with the backend session"` / `"... activates with the backend
  session"`. Do not use mock copy in T2I_main.

## 5. Page patterns

**A — Compact chat workspace** (T2I_main; the pattern for every generation tab):

- Root `<div class="flex h-full min-h-0 flex-col">`; the page header is compact, the chat area
  takes the remaining height and the composer is pinned at the bottom.
- Chat scroller: oldest → newest messages. Each job is a right-aligned user prompt bubble followed
  by a left-aligned generation card.
- Generation card: status dot, job id, time, progress, shared `StageTimeline`, cancel/error,
  result grid, warnings, collapsible applied settings, actions (View, Reuse, Use seed, Download,
  more menu), and soft-delete actions.
- Settings live in a right drawer on desktop (`~380–400px`, static) and a fixed overlay on
  mobile. Each panel is a `<details>` section with a reset icon; the page footer has a confirmed
  global reset.
- Composer: prompt textarea, autosave label + character count, quick chips for model / output /
  LoRA / upscale / enhancement, and a stable action group. `Ctrl+Enter`/`Meta+Enter` generates;
  plain Enter stays a newline.
- **Composer layout rule (hard):** the action group (`[Settings] [Generate]`) carries `ml-auto`
  so Generate stays right-aligned at every width, even when the control row wraps.
- **Visibility rule:** controls that materially change the output (upscale on/off, enhancement
  on/off) stay visible in the composer. Rarely used values live in the settings drawer — never
  hide the upscale switch behind a collapsed advanced section.

**B — Standard page** (library / tools / settings):

- Root `mx-auto max-w-7xl px-4 py-5 sm:px-6`.
- Header: `text-lg font-semibold` title + `text-xs/sm text-muted` description, then actions.
- Gallery: sync the library on mount, provide a Refresh action, search prompts/labels/models/
  tags/job ids/seeds, and open the shared `MediaViewer` on card click. Viewer actions:
  favorite, built-in download, move to trash. Do not add “use as reference” to a strict T2I
  module — that would reintroduce a reference-image input path.
- Empty states use `EmptyState` or `py-16 text-center text-sm text-muted`; offer “clear search”
  when filters are active.

**C — "Soon" tab** (planned, not wired):

- `<ComingSoon title blurb :planned="..." :features="..." />` — always list which backend step the
  module lands in and 3–4 concrete features, so the page documents intent.

## 6. Data & stores (backend-first)

- All I/O goes through `src/lib/api.ts` (shared client) or the module's canonical `api.ts`. Stores
  are backend-first with offline fallbacks. `mockApi.ts` must not be used by T2I_main.
- Components never fake delays themselves.

**Real module store pattern** (see `features/text-to-image/store.ts`):

- Owns the durable form, catalog, jobs, warnings, busy flags and actions.
- Persists the form under `genai.<module>.form.v1` as
  `{ version, savedAt, form }`; debounced writes + sync flush on `beforeunload` and page
  `onBeforeUnmount`.
- Restores only known keys/types, then reconciles against the live catalog: fallback unknown
  IDs, drop incompatible LoRAs, clamp stale ranges, normalize strength/batch/seed, and show one
  “adjusted” notice if anything changed.
- Resets: `resetPanel('prompt' | 'output' | 'loras' | 'enhance' | 'sampling' | 'upscale' | 'all')`
  in the store; panels call the store rather than duplicating field logic.
- Jobs: load history on mount (API returns newest-first; T2I reverses once for chat order),
  reattach polling to queued/running jobs, replace records as they change, sync library + generic
  jobs on terminal, and drop 404s.
- Engine accounting: mark a job active when created or reattached; keep a **deduplicated**
  tracked-id set; release on terminal status, cancel-to-terminal, 404 and delete. This feeds the
  top-bar queue pill.
- Deletion: call the module DELETE endpoint, which soft-deletes the job. T2I also offers
  “delete images & message” (assets move to `data/trash`) vs “remove message only”. Running jobs
  are refused with `job_running`.

Other stores:

- `jobs` store: generic recent-job cache for the Jobs page; module stores sync it after terminal
  jobs.
- `library` store: backend-first assets + thumbnails. Gallery reads it; modules sync it after
  terminal jobs and after asset deletions. `library.loaded` distinguishes “not loaded yet” from
  “asset was deleted”.
- `settings` store: connections / defaults / folders / prompts — localStorage key
  `genai.settings.v1` in the shape of the future `settings.json`. `settings.json` is
  authoritative: pushes are **partial diffs of only touched keys** (a stale tab can never wipe
  other fields) and unpushed local edits always win over a late sync. Re-sync on reconnect
  (engine poll), tab focus and cross-tab storage events — never send full snapshots.
- `engine` store: GPU VRAM + system RAM + loaded models + unload actions + run accounting
  (`jobStarted()` / `jobFinished()`), driving `engine.busy` and the top-bar queue pill.
- `content` store: read-only ComfyUI content audit (`GET /api/comfyui/inspect`,
  `/requirements`). Settings → Connections owns the `comfyuiFolder` field; Settings → Engine
  content renders the report. Never add install/download calls here until those phases land —
  and they must stay explicit-click actions (`docs/COMFYUI_CONTENT.md`).
- Persistence: settings, ui and real module forms persist; mock chat threads are in-memory by
  design. Do not persist API keys, absolute server paths or viewer state.
- `fixtures.ts` mirrors the real domain for mock pages. If real pack values change, update T2I
  pack/catalog first and document it; keep mock fixtures separate.

## 7. Top bar conventions

- Connection pills (green dot + "Connected") always navigate to `/settings?tab=connections`.
- The **queue pill** is the single source of run status: `Queue idle` only when `engine.busy` is
  false; while anything runs it reads `Working - n running - n queued` (accent color + spinner).
  It is fed by the ComfyUI queue (status poll) plus `engine.jobStarted()/jobFinished()` from GUI
  runs — modules must never add their own busy indicators.
- **Do not** add status pills for anything the Resources popover already shows (GPU VRAM, RAM).
  Top bar keeps: connections, queue, Resources, theme toggle, settings.
- Pills: `h-8 shrink-0 rounded-full border border-border bg-surface px-3 text-xs`; hide on narrow
  widths with `hidden lg:flex` instead of letting the bar wrap.
- The Resources popover is the single home of memory info: **GPU VRAM + System RAM bars**
  (VRAM via `nvidia-smi` in GiB — the same numbers Windows Task Manager shows — falling back to
  ComfyUI's device stats, so VRAM stays visible even with ComfyUI closed), loaded model lists
  (ComfyUI + Ollama) and unload actions (disabled while `engine.busy`).

## 8. Media viewing

- `MediaViewer` is shared. Build `MediaViewerItem[]` from library assets/job results, pass
  `v-model:open` and `v-model:index`, and use the `actions`/`info` slots for module-specific
  buttons/metadata.
- Parent owns the item list and must remove deleted items, close on empty, and avoid broken
  `/file` URLs. If `library.loaded` is true and an asset id is missing, treat it as deleted.
- The viewer owns zoom, fullscreen, keyboard nav, thumbnails and the built-in download. Do not
  rebuild those in a module.
- Fullscreen/keyboard contract: `Escape` exits fullscreen then closes; arrows navigate; `+/-`
  zoom; `0` resets zoom; `F` toggles fullscreen.
- The information panel is optional (`info` prop). Include prompt, negative prompt, job id, seed,
  model, ratio/size, upscale and enhancement values for generated media.

## 9. Acceptance checklist for a new module session

1. Canonical backend module folder + `manifest.json` + pack; thin API router mounted.
2. Canonical frontend copied to `frontend/src/features/<module-id>/`; route + sidebar entry.
3. Module store owns form state; versioned localStorage persistence and unload flush.
4. Catalog reconciliation after load; per-panel resets + confirmed global reset.
5. Job history loads on mount; running jobs reattach; engine busy accounting is deduplicated.
6. Result assets saved through the library; Gallery syncs on mount and after terminal jobs.
7. Media viewer reused; deleted/missing assets do not render broken images.
8. Reused tokens/components; no new z-index values; no raw colors (except documented viewer/star
   exceptions).
9. Composer Generate button right-aligned at all widths; upscale on/off visible.
10. Mock actions produce toasts (mock pages only); engine-dependent controls lock while busy.
11. Light + dark + one accent spot-checked; narrow-width check (settings drawer, sidebar, top bar,
    composer).
12. `npm run typecheck` + `npm run build` green; backend tests green; browser console free of
    errors/warnings.
