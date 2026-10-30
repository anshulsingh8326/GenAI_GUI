# Packs — How ComfyUI workflows, models & presets become GUI features

> Companion to `docs/PLAN.md`. Draft v0.1 · 2026-10-17
> Answers: "How does my ComfyUI workflow actually run inside this GUI?"
>
> **Implementation note:** this is the early architecture sketch. The shipped
> pack layout, `pack.json` metadata, alias matching and one-of groups are
> documented in `docs/GENMODULE_GUIDE.md` §4.1 and §4.4, with the live example in
> `backend/app/GenModules/T2I_main/backend/pack/`.

---

## 1. The idea in one paragraph

The GUI never shows a node graph and never talks to ComfyUI. Every capability the user sees
(e.g. "Text → Image", "Edit image", "Upscale", "Image → Video") is backed by a **pack**: plain JSON
files that describe (a) which **models** exist, (b) which **workflow graph** to run (exported from
ComfyUI in API format), (c) how GUI fields **bind** to that graph, (d) which optional parts
(**blocks**) can be switched on/off, and (e) which **presets** bundle styling choices.
You keep authoring and testing workflows in ComfyUI exactly like today — then wrap them.
Adding a capability or model = writing JSON, never changing app code.

```
packs/
├─ schema/     # JSON Schemas (editor validation + pack validator)
├─ models/     # one file per model        → "what can I run"
├─ workflows/  # templates + recipes       → "how do I run it"
└─ presets/    # starter/user presets      → "with which style/settings"
```

## 2. Model manifest — one JSON per model

`packs/models/krea2-turbo.json` (realistic example):

```json
{
  "id": "krea2-turbo",
  "display_name": "Krea 2 Turbo",
  "family": "qwen-image",
  "kind": "image",
  "files": {
    "unet":         { "match": ["*krea2*turbo*.gguf", "*krea2*turbo*.safetensors"], "vram_hint": "Q5 ≈ 5-7GB" },
    "text_encoder": { "match": ["qwen3vl_4b*.safetensors"], "clip_type": "krea2" },
    "vae":          { "match": ["qwen_image_vae*.safetensors"] }
  },
  "defaults":    { "steps": 12, "cfg": 3.0, "sampler": "euler", "scheduler": "simple", "resolution": 1024 },
  "capabilities":["t2i", "i2i", "identity-conditioning", "lora"],
  "lora_family": "krea2",
  "sources":     ["https://…"],
  "license":     "see sources"
}
```

- **`match` patterns** let *anyone's* filenames work (mine is `snofsSexNudes…int8.safetensors`, yours is `krea2_turbo-Q5_K_M.gguf` — both match the same manifest).
- **`capabilities`** gate the GUI: a model without `identity-conditioning` simply hides that toggle.
- **`vram_hint` + `defaults`** power warnings, quant advice, and sane initial settings.
- The app only stores manifests — **never weights**. Files live in the user's ComfyUI folders and are found via the capability probe.

## 3. Workflow template — the graph, exported from ComfyUI

### Authoring steps (your side)

1. Build/test the workflow in ComfyUI as usual (e.g. the Freeze-v8 graph).
2. **Workflow → Export (API)** → `krea2_freeze.api.json` (flat map: node id → class + inputs).
3. Hand the file over (or annotate it yourself). We wrap it into a pack:

```json
{
  "template": { "19": { "class_type": "KSampler",
                        "inputs": { "seed": 0, "steps": 12, "cfg": 3.0,
                                    "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
                                    "model": ["5",0], "positive": ["11",0], "negative": ["12",0],
                                    "latent_image": ["18",0] } },
                "…": {} },
  "bindings": {
    "prompt":   "11.inputs.text",
    "negative": "12.inputs.text",
    "seed":     "19.inputs.seed",
    "steps":    "19.inputs.steps",
    "cfg":      "19.inputs.cfg",
    "resolution": ["18.inputs.width", "18.inputs.height"]
  },
  "requirements": { "models": ["krea2-turbo"], "nodes": ["KSampler", "LoraLoaderModelOnly"] }
}
```

That's it — this alone produces a working "Text → Image" recipe. The GUI Advanced panel writes
`seed/steps/cfg` straight into the graph; Simple panel writes prompt/model choices.

### Blocks — how toggles work (replacing switches)

Optional parts are declared as **blocks** with link points, e.g. the upscale block:

```json
"blocks": {
  "upscale": {
    "add_nodes": ["26", "27", "29"],
    "input":  { "samples": "19.outputs.LATENT" },     // composer re-wires this
    "output": { "images":  "29.outputs.IMAGE" },       // → SaveImage instead of 28
    "requires": ["esrgan-model"]
  }
}
```

- Toggle **on** → composer adds the block's nodes, rewires links.
- Toggle **off** → nodes are absent from the submitted graph → **never executed, zero cost**.
- No IAMCCS / LazySwitch nodes needed. The five Freeze-v8 toggles (enhance, text-ref, describe-mode, identity, upscale) all become block flags.

### Recipes — one capability, many graphs

`packs/workflows/krea2-freeze.recipe.json`:

```json
{
  "id": "krea2-freeze",
  "capability": "t2i",
  "display_name": "Krea 2 — Freeze style",
  "template": "krea2_freeze.api.json",
  "models": ["krea2-turbo"],
  "blocks": ["enhance", "text_ref", "identity", "upscale"],
  "simple_fields":   ["prompt", "loras", "upscale", "enhance"],
  "advanced_fields": ["seed", "steps", "cfg", "sampler", "resolution", "denoise"]
}
```

The GUI is capability-first: user picks "Text → Image", app chooses recipe (default or user-preferred);
advanced users pick the recipe themselves. Multiple recipes per capability = healthy ecosystem.

## 4. Capability → recipe map (what we'll author, in order)

| Capability | Recipe (pack) | Model base | Notes |
|---|---|---|---|
| Text → image | `krea2_t2i`, `krea2_freeze` | Krea2 Turbo (have) | Step 3 of the ladder |
| Image → image | `krea2_img2img` | Krea2 Turbo | Load → VAEEncode → KSampler denoise<1 |
| Edit (image+text) | `qwen_edit` | Qwen-Image-Edit class (download) | True instruction edit; Krea2 edit chain was the wrong tool |
| Character gen | `krea2_freeze` + identity block | Krea2 + profile ref | Identity = block + character profile |
| Face swap | `reactor_swap` | inswapper+GFPGAN (have) | Standalone or post-stage |
| Upscale | `esrgan_upscale`, latent pass | 4x-UltraSharp (have) | Simple-mode toggle |
| Image → video | `wan_i2v` / `ltx_i2v` | Wan/LTX class (download) | Step 10 |
| Text → video | `wan_t2v` | Wan/LTX class | Step 10 |
| Video → video | `v2v_faceswap`, `subject_to_video` | frame-swap (have) + Wan-Animate class (download) | Step 11: memes/deepfake/body swap |
| Audio | providers (TTS/music/STT engines) + `mmaudio_foley` | Step 12 picks | Not all audio needs ComfyUI |

## 5. Validation & contributions

- `packs/schema/*.json` → JSON Schema for manifests/templates/recipes/presets (IDE autocomplete + validator).
- `packs validate` (script) checks: schema, file matches against a live ComfyUI probe, node availability, binding targets exist, block link points resolve.
- Errors are actionable: "binding `seed` → node 19 missing", "recipe qwen_edit needs model caps `edit` — not installed".
- Contribution flow: fork → add pack → validate (CI runs schema checks) → PR. `schema_version` on every pack; bad packs get disabled, never crash the app.

## 6. FAQ

- **Can I use my existing workflows?** Yes — Export (API); the pack wrapper is small. Your UI graphs stay yours; the app runs API-format copies.
- **Do I have to stop using ComfyUI directly?** No. It stays the authoring/debugging tool and the engine.
- **What if a node pack is missing on my machine?** Probe gates the recipe; you get the exact install hint.
- **Where do models live?** In *your* ComfyUI folders (`models/unet`, `models/loras`, …). The app only stores JSON manifests + the probe results.
- **Can a workflow serve multiple features?** Yes — same template can back several recipes (different defaults/exposed fields).
- **Who can add a capability?** Anyone — a recipe pack is a PR away; no app release needed.
