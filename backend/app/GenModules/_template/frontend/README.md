# Template frontend contract

These six files are the canonical frontend for the `_template` GenModule. They
are copied byte-for-byte into `frontend/src/features/<nav-id>/`; this README is
not copied.

| File | Responsibility |
| --- | --- |
| `types.ts` | Camel-case wire types: catalog, form request, job record, stages, delete/clear results |
| `api.ts` | Same-origin `/api/template` client, error normalization, job-id encoding, asset URLs |
| `store.ts` | Form persistence (`genai.template.form.v1`), catalog reconciliation, job history, polling/backoff, delete/clear, shared-store sync |
| `TemplatePage.vue` | Header, chat scroller, composer, settings drawer, viewer owner, transient UI |
| `TemplateSettingsPanel.vue` | Output and renderer cards bound directly to the store, panel resets, autosave/error footer |
| `TemplateGenerationCard.vue` | User bubble, job status, stages, result grid, favorite/trash, reuse/seed/delete actions |

## Copy

```powershell
$repo = (Resolve-Path '.').Path
$src = Join-Path $repo 'backend/app/GenModules/My_module/frontend'
$dst = Join-Path $repo 'frontend/src/features/my-module'
New-Item -ItemType Directory -Force -Path $dst | Out-Null

Get-ChildItem $src -File |
  Where-Object { $_.Name -ne 'README.md' } |
  ForEach-Object { Copy-Item $_.FullName (Join-Path $dst $_.Name) -Force }
```

Hash-check both copies; the guide's §3.5 has the command. The runtime folder is
what Vite builds.

## Adapt

- Change `BASE = '/api/template'` in `api.ts`.
- Change `STORAGE_KEY = 'genai.template.form.v1'`, the Pinia id, and the
  request `tab` in `store.ts`.
- Rename the three components (recommended), update the imports in the page,
  and update `manifest.frontend` to the canonical page filename.
- Replace the form fields/request shape with your module's controls. Keep:
  - defaults, fixed values and min/max/step read from `/catalog`, not hardcoded
    in the components;
  - defensive persistence + catalog reconciliation;
  - newest-first API list reversed once for chat;
  - polling with backoff and 404 handling;
  - `library.syncFromBackend()` + `jobs.syncFromBackend()` after terminal jobs;
  - module-scoped per-job delete and clear;
  - viewer ownership in the page (open/index/items).
- Rebuild the settings cards for your real panels. Keep one reset per panel and
  a confirmed global reset.
- Replace the renderer-specific text in `TemplateSettingsPanel.vue`.

## Shared imports

Both copies import only shared app code:

```ts
import type { Asset, Stage } from '@/types'
import { formatTime, timeAgo } from '@/lib/format'
import { downloadAsset } from '@/lib/download'
import { useLibraryStore } from '@/stores/library'
import { useJobsStore } from '@/stores/jobs'
import { useUiStore } from '@/stores/ui'
import MediaViewer from '@/components/media/MediaViewer.vue'
import StageTimeline from '@/components/chat/StageTimeline.vue'
```

Do not import from another GenModule or from `backend/` at runtime.

## What this starter deliberately does not do

- It does not call ComfyUI or Ollama. The backend renders a local SVG card.
- It has no per-model ranges. Add `backend/pack/models.json` when controls
  depend on the selected model; the guide's §4.4 shows the shape.
- It does not resume engine prompts. The backend marks a stale `running` job as
  failed; an engine-backed module must add a `main.py` resume hook.
- It does not store audio/video. The library is image-only today.

The full host contract, registration steps, and zero-context dry run are in
[`docs/GENMODULE_GUIDE.md`](../../../../../docs/GENMODULE_GUIDE.md).
