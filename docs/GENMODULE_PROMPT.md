# GenModule build prompt

Paste the block below into an AI coding agent working in this repository.
Replace `(Your GenModule Idea)` with the actual module idea. Keep the rest of the
contract unchanged unless the idea genuinely needs a different shape.

```markdown
# Build a GenModule

## Idea

(Your GenModule Idea)

## Read first

1. Read `docs/GENMODULE_GUIDE.md` end to end. Use §3 for the copy/rename and host
   registration steps, §4.1 for `requirements.json`, §4.4 for pack/alias rules,
   §4.2 for the API surface, §5.1 for canonical/runtime frontend files, and
   Appendix A for every host registration.
2. Read `docs/COMFYUI_CONTENT.md` §2 for the requirements/audit contract and
   `docs/MODEL_CATALOG.md` for the user-owned file catalog.
3. Read `backend/app/GenModules/T2I_main/` as the reference for a real
   ComfyUI-backed module. Do not modify `T2I_main` while building the new module.

## Build rules

- One GenModule owns one page, one API prefix, one jobs/history stream, and one
  library integration. Do not clone a page or API for every model family.
- Start from `backend/app/GenModules/_template/`; rename the folder and every
  `Template`/`template` identifier. Register the backend router, Vue route, and
  sidebar item exactly as §3 says.
- Keep one tracked pack per model family/recipe under `backend/pack/packs/<id>/`.
  Each pack owns `pack.json`, `options.json`, `models.json`, `loras.json` /
  `upscalers.json` when needed, and its own ComfyUI API workflow. Never build one
  switch-node mega-graph and never borrow another family's graph.
- `pack.json` owns `label`, `description`, `nsfw`, and `order`. The registry owns
  `id`, `path`, and `defaultPack`.
- Keep user-facing defaults, ranges, workflow bindings, and filenames in pack
  JSON. The frontend only renders what `/catalog` returns.
- The installed model catalog is read-only input. Never rename, move, delete, or
  download a user file. Bind the real catalog filename into the graph.

## Requirements and aliases

- Ship `requirements.json` only if the module needs ComfyUI nodes or model files.
  Use `schemaVersion: 2`, `module`, `groups`, `nodes`, and `models` as documented
  in `docs/GENMODULE_GUIDE.md` §4.1.
- Every model file gets a stable `id`, owning `pack`, `role`, `label`, canonical
  `name`, `target`, `aliases`, `required`, `tested`, `nsfw`, `size`, `url`,
  `pageUrl` when available, and `why`.
- Aliases are case-, separator-, path-, and extension-insensitive. Add meaningful
  aliases for the real download names. Do not require users to rename files.
- If several files are alternatives for one required role, create a required
  `groups[]` entry with `mode: "oneOf"` and mark each member
  `required: false`. Count the group once in audits and the setup popup.
- Put model-specific aliases in `aliases` and generic family aliases in
  `fallbackAliases`. A fallback may not claim a file already claimed by a
  sibling model's specific alias.
- Resolve text encoders, VAEs, LoRAs, and upscalers through aliases too.
- If the default model is absent but another member of its base group is
  installed, select the installed member. A partial install must not fail just
  because the configured default is missing.
- Add `(NSFW)`/`nsfw` metadata where appropriate. Never hide required setup
  information behind an NSFW label.

## First-open setup popup

- Add `GET /setup` and build it with
  `app.common.module_setup.build_setup_payload` from the normalized
  `requirements.json`, pack metadata, and user catalog.
- Reuse `frontend/src/components/content/ModuleSetupModal.vue`. Fetch once on
  page mount, auto-open only when `ready === false`, and add a **Setup** header
  button to reopen it.
- Show missing required files and groups, destination folders, sizes, direct
  download/source links, pack descriptions, tested status, and NSFW tags.
- Return `ready: null` when the user catalog is unavailable. Never report every
  file as "missing" before the catalog has been built.
- The popup is read-only. It must not download, install, move, or delete files.
  "Refresh check" only re-reads the catalog-backed setup payload.

## Verification

Run and fix:

```bash
# backend
cd backend
uv run python -m pytest -q
uv run python -m compileall -q app

# frontend
cd ../frontend
npm run typecheck
npm run build
```

Add focused tests for:

- pack loading, unique model ids, and the default pack;
- alias matching for shifted/renamed filenames;
- exact-file graph bindings for the model, text encoder, VAE, LoRAs, and upscaler;
- a one-of base group with only the non-default alternative installed;
- the setup payload and `/setup` endpoint, including `ready: null`;
- the shared setup modal typecheck/build;
- the real service path used by `/validate` and `/jobs`, not a copy.

## Finish

- Update the README module list and relevant docs.
- Keep all changes uncommitted unless explicitly asked to commit.
- Report the commands you ran, what passed, and any remaining external blocker
  (for example an unverified ComfyUI API graph).
```

## Notes for maintainers

- The prompt deliberately points at `T2I_main` as a reference, not a file to
  copy blindly. A new family needs its own workflow and model bindings.
- Flux/Qwen packs stay deferred until their ComfyUI API graphs, loader nodes,
  text encoders, and VAE names are verified against a live install.
- The setup endpoint contract is generic. Any module can implement it without
  depending on the T2I service.
