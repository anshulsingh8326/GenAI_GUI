# GUI Guidelines — GenAI GUI (frontend)

Version 0.1 (mock phase). This is the authoritative reference for building **any new module GUI**
(Image→Image, Face Swap, Video, Audio, ...) in `frontend/src`. Follow it in every session so all
modules feel like one product. If something here blocks a design, change this doc in the same PR.

---

## 0. TL;DR — new module checklist

1. Create the module folder `frontend/src/features/<module-id>/` with `<Module>Page.vue`
   (module-only pieces go in `<module-id>/components/`).
2. Register the route in `frontend/src/router/index.ts` and the sidebar entry in `frontend/src/lib/nav.ts`.
3. Use **design tokens only** (no raw colors), reuse `components/ui/*`, and use only the fixed
   z-index scale (§3).
4. Chat-style modules: reuse `ChatThread` + `ComposerBar` with a **new `tabId`** — threads, composer
   state and model memory come for free.
5. Mock-only actions: show a toast (`"... arrives with the backend session"`). Engine-dependent
   actions (unload, etc.) are disabled while `engine.busy`.
6. Report every run through the shared runner (`chat.send` -> `engine.jobStarted()` /
   `jobFinished()`): the top-bar queue pill flips to **Working** by itself (§7). Never build
   per-module busy pills or progress chips - the shell owns run status.
7. Check light **and** dark theme, plus a narrow window width.
8. `npm run build` (includes `vue-tsc`) must pass and the console must be clean before finishing.

---

## 1. Folder architecture

```
frontend/src/
├─ components/              shared library - reuse before you rebuild
│  ├─ ui/                   primitives (buttons, inputs, modal, popover, chips, ...)
│  ├─ layout/               AppShell, SideNav, TopBar, ResourcesPopover
│  └─ chat/                 ChatThread, ComposerBar, ResultCard, StageTimeline,
│                           AttachmentCard, AttachPickerModal, AdvancedModal, UserBubble
├─ features/                ONE FOLDER PER MODULE - self-contained
│  └─ <module-id>/
│     ├─ <Module>Page.vue   the route target
│     └─ components/        pieces used ONLY by this module (e.g. T2I SessionBar)
├─ stores/                  Pinia: ui, settings, engine, jobs, library, chat
├─ lib/                     api.ts (typed REST client), download.ts, nav.ts,
│                           fixtures.ts, mockApi.ts, placeholder.ts, format.ts
└─ router/                  routes
```

Rules:

- A module may import from `components/*`, `stores/*`, `lib/*` — **never from another module's folder**.
- If a second module needs the same piece, promote it to the right `components/<category>/` folder
  (that is exactly how the chat workspace components became shared).
- Per-tab state is keyed by `tabId` in the chat store: one thread + one composer per generation tab.

Current module folders: `text-to-image` (functional mock), `gallery`, `presets`, `jobs`,
`characters`, `game-assets`, `settings` (working mock pages), and the structured "soon" pages
`image-to-image`, `edit-image`, `face-swap`, `influencer`, `video/*`, `audio/*`.

## 2. Theming & tokens

- Two themes: `pastel-dark` (default) and `pastel-light`; four accents (lavender, mint, peach, sky).
  Switch via `useUiStore().setTheme()` / `setAccent()`. Persisted in `localStorage` (`genai.ui.v1`).
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
  Single documented exception: the favorite star (`fill-amber-300 text-amber-300`).
- Shape conventions: cards `rounded-2xl border border-border bg-surface p-4` (page sections `p-5`),
  controls `rounded-xl`, chips/pills `rounded-full`, the composer `rounded-3xl`.
- The global `:focus-visible` ring in `main.css` handles keyboard focus — don't re-implement it.
- Mock images: always generate via `lib/placeholder.ts` (deterministic SVG) — never add binary assets.

## 3. Z-index scale (do not invent new levels)

| Layer | Value | Owner |
| --- | --- | --- |
| Top bar | `z-30` | `components/layout/TopBar.vue` |
| Dropdowns / popovers / tooltips | `z-40` | `components/ui/AppPopover.vue` |
| Modals | `z-50` | `components/ui/AppModal.vue` (teleports to body) |
| Toasts | `z-60` | `components/ui/ToastHost.vue` |

Lessons already paid for:

- The top bar must **not** use `overflow-hidden` — it clips popovers (this bit us once).
  Use `min-w-0` + `truncate` on the title and `shrink-0` on pills instead.
- Popovers are **not** portaled; keep them inside a `relative` wrapper (`AppPopover` handles this).

## 4. Component catalog (reuse — don't rebuild)

**`components/ui/`**
`AppButton` (variants: primary / soft / ghost / danger · sizes sm/md/lg) ·
`AppInput` · `AppTextarea` · `AppSelect` · `AppSwitch` · `AppSlider` · `Chip` · `Badge` ·
`StatusDot` (ok / off / warn / busy) · `AppModal` (v-model, `title`, `subtitle`, `#footer`) ·
`AppPopover` (v-model, `align`, `up`, `width`, `#trigger`) · `AppTabs` · `Section` ·
`EmptyState` · `ComingSoon` · `ToastHost` (mounted once in `App.vue`).

**`components/layout/`**
`AppShell` · `SideNav` · `TopBar` · `ResourcesPopover`.

**`components/chat/`**
`ChatThread` (`tabId`, `suggestions`) · `ComposerBar` (`tabId`) · `ResultCard` (`jobId`) ·
`StageTimeline` · `AttachmentCard` · `AttachPickerModal` · `AdvancedModal` (`tabId`) ·
`UserBubble`.

Global habits:

- Interactive elements get `cursor-pointer`; disabled state `disabled:opacity-45`.
- Feedback goes through `useUiStore().toast(msg, 'success' | 'info' | 'warn' | 'error')` — never `alert()`.
- Mock-action copy: `"... arrives with the backend session"` / `"... activates with the backend session"`.

## 5. Page patterns

**A — Chat workspace** (every generation tab: T2I now, I2I next):

- Root `<div class="flex h-full flex-col">` inside the shell's scrollable main.
- Optional module session bar (see `features/text-to-image/components/SessionBar.vue`).
- `<ChatThread :tab-id="..." :suggestions="[...]" />` + `<ComposerBar :tab-id="..." />`.
- New tab = new `tabId`: thread, composer, model choice and job history are isolated automatically.
- **Composer layout rule (hard):** the action group `[Advanced] [Generate]` carries `ml-auto` so
  the Generate button stays right-aligned at every width, even when the control row wraps.
  Stage toggles (Enhance / Refine) and rarely-used parameters live **inside the Advanced modal** —
  never as extra chips in the control row.

**B — Standard page** (library / tools / settings):

- Root `mx-auto max-w-6xl px-6 py-6`.
- Header: `text-lg font-semibold` title + `text-sm text-muted` description.
- Cards grid for content; optional detail panel `lg:w-80` with `sticky top-4`.
- Filters as a `Chip` row; empty states via `EmptyState` or `py-16 text-center text-sm text-muted`.

**C — "Soon" tab** (planned, not wired):

- `<ComingSoon title blurb :planned="..." :features="..." />` — always list which backend step the
  module lands in and 3–4 concrete features, so the page documents intent.

## 6. Data & stores (backend-first)

- All I/O goes through `src/lib/api.ts` (typed REST client) — stores are backend-first with
  offline fallbacks: settings → localStorage, jobs → `#offline-n` session records, library →
  session `data:`-URI assets. `mockApi.ts` is down to the T2I mock runner and disappears with
  the real pipeline.
- Components never fake delays themselves.
- `chat` store: thread + composer per `tabId`; `send(tabId)` snapshots the composer into a job.
- `jobs` store: every run is a `JobRecord` with stages; result cards and the Jobs page read from it.
- `library` store: all assets (seeded fixtures + generated). Gallery reads it.
- `settings` store: connections / defaults / folders / prompts — localStorage key `genai.settings.v1`
  in the exact shape of the future `settings.json`. `settings.json` is authoritative: pushes are
  **partial diffs of only the touched keys** (a stale tab can never wipe other fields) and unpushed
  local edits always win over a late sync. The store re-syncs on reconnect (engine poll), tab focus
  and cross-tab storage events - never send full snapshots.
- `engine` store: GPU VRAM + system RAM + loaded models + unload actions + run accounting
  (`jobStarted()` / `jobFinished()`), which drives `engine.busy` and the top-bar queue pill.
  Every GUI run must report there (the mock runner does it today; keep the calls when the
  real pipeline replaces it).
- `fixtures.ts` mirrors the real domain (Krea2 Freeze v8 values, LoRAs, presets). If the real
  workflow values change, update fixtures and note it in the session summary.
- Persistence: settings + ui persist; chat threads are in-memory by design (mock phase).

## 7. Top bar conventions

- Connection pills (green dot + "Connected") always navigate to `/settings?tab=connections`.
- The **queue pill** is the single source of run status: `Queue idle` only when `engine.busy` is
  false; while anything runs it reads `Working - n running - n queued` (accent color + spinner).
  It is fed by the ComfyUI queue (status poll) plus `engine.jobStarted()/jobFinished()` from GUI
  runs - modules must never add their own busy indicators.
- **Do not** add status pills for anything the Resources popover already shows (GPU VRAM, RAM).
  Top bar keeps: connections, queue, Resources, theme toggle, settings.
- Pills: `h-8 shrink-0 rounded-full border border-border bg-surface px-3 text-xs`; hide on narrow
  widths with `hidden lg:flex` instead of letting the bar wrap.
- The Resources popover is the single home of memory info: **GPU VRAM + System RAM bars**
  (VRAM via `nvidia-smi` in GiB - the same numbers Windows Task Manager shows - falling back to
  ComfyUI's device stats, so VRAM stays visible even with ComfyUI closed), loaded
  model lists (ComfyUI + Ollama) and unload actions (disabled while `engine.busy`).

## 8. Acceptance checklist for a new module session

1. Module folder + route + sidebar entry (`soon` badge until wired).
2. Reused tokens/components; no new z-index values; no raw colors.
3. Chat modules: new `tabId`; Generate button right-aligned at all widths; stage toggles in Advanced.
4. Mock actions produce toasts; engine-dependent controls lock while busy.
5. Light + dark + one accent spot-checked; narrow-width check (sidebar, top bar, composer).
6. `npm run build` green; browser console free of errors/warnings.
