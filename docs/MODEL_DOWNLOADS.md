# Manual model downloads (Krea 2 / T2I_main)

Status: **manual only**. The app never downloads, moves or deletes model files.
Download the files yourself, put them in the ComfyUI folders below, then use
**Settings -> Model catalog -> Refresh from ComfyUI** and **Settings -> Engine
content** to verify what the app can see.

Links were checked on **2026-10-29**. Sizes are approximate; the linked page or
repository is authoritative. Model licences apply to the downloaded weights.

## Base-model choices

T2I_main ships two packs that share one ComfyUI graph but keep separate defaults:

| Pack | Base | Default sampling |
| --- | --- | --- |
| **Krea 2 Turbo** | Krea2 Turbo Q5_K_M (GGUF) | 9 steps, CFG 2.0 |
| **Krea 2 SNOFS** | SNOFS_Krea2 (int8) | 12 steps, CFG 2.5 |

Install the base for each pack you want to use. You do **not** need both bases;
the model dropdown lists both packs and disables a model whose files are absent.
`requirements.json` treats each pack's base as an optional one-of group, so one
installed base does not block module readiness.

The official Comfy-Org FP8/INT8 files are also detected through the generic
`krea2` fallback alias, so a renamed or official Krea 2 base does not fail the
file check. The normal pack then loads it with `UNETLoader` and keeps its
9 steps / CFG 2.0 defaults. A generic file that contains `snofs` is reserved for
the SNOFS pack.

For either pack, the single file to edit for generation defaults is
`backend/app/GenModules/T2I_main/backend/pack/packs/<pack>/defaults.json`.
`models.json` only holds bindings and safe ranges; the API workflow only holds
node wiring. The composer overwrites workflow literals from `defaults.json` and
the request, so editing `krea2_t2i.api.json` is not how you change defaults.

- **A. Recommended.** Use one of the two tested bases in section A, plus the
  shared text encoder, VAE and optional files. This runs with the matching pack
  without editing the module.
- **B. Official Krea 2 Turbo (Comfy-Org FP8/INT8).** These are clean base files.
  They are accepted as a generic `krea2` fallback by the normal pack, which keeps
  its 9 steps / CFG 2.0 defaults.

## A. Recommended T2I_main files

Download **one base per pack you want**; the text encoder, VAE and upscaler are
shared. The SNOFS base is community/NSFW-oriented; it is labelled below. The
Realism Engine LoRA is a general realism/style LoRA, not an NSFW-specific LoRA.
Other LoRAs are optional and are not required for setup.

| Model | File in ComfyUI | Folder | Source | Size |
| --- | --- | --- | --- | --- |
| **SNOFS_Krea2** (int8, SNOFS pack) | `snofsSexNudesAndOther_krea2TurboV14_int8.safetensors` | `models/unet/` | [SNOFS Merged - Krea 2 Turbo v1.4](https://civitai.com/models/2416142?modelVersionId=3333138) - **NSFW model page; Civitai login/opt-in may be required** | 12.8 GB |
| **Krea2 Turbo Q5_K_M** (GGUF, normal pack) | `krea2_turbo-Q5_K_M.gguf` | `models/unet/` | [Vantage GGUF repository](https://huggingface.co/vantagewithai/Krea-2-Turbo-GGUF) / [direct file](https://huggingface.co/vantagewithai/Krea-2-Turbo-GGUF/resolve/main/krea2_turbo-Q5_K_M.gguf) | 8.87 GB |
| Text encoder | `qwen3vl_4b_fp8_scaled.safetensors` | `models/text_encoders/` | [Comfy-Org direct](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_fp8_scaled.safetensors) | 5.24 GB |
| VAE | `qwen_image_vae.safetensors` | `models/vae/` | [Comfy-Org direct](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/vae/qwen_image_vae.safetensors) | 253.8 MB |
| Upscaler (optional) | `4x-UltraSharp.pth` | `models/upscale_models/` | [Kim2091/UltraSharp direct](https://huggingface.co/Kim2091/UltraSharp/resolve/main/4x-UltraSharp.pth) | 67 MB |
| Realism LoRA (optional) | `realism_engine_krea2_v3.1.safetensors` | `models/loras/` | [Realism Engine mirror](https://huggingface.co/RazzzHF/realism_engine_krea2/resolve/main/realism_engine_krea2_v3.1.safetensors) - general realism/style LoRA | 1.56 GB |

Both base models have been tested by the project owner. Use the GGUF when you
want the smaller download; use SNOFS_Krea2 when you want the SNOFS pack's
12-step reference path. The GGUF path uses ComfyUI-GGUF, which the setup installs
as a required core node.

A single installed base is enough for the module. The model dropdown and the
selected pack decide which defaults apply; the other pack's model simply shows
as not installed.

### SNOFS_Krea2 file name and checksum

Do **not** rename downloaded files. The Civitai download may be named
`snofsSexNudesAndOther_krea2TurboV14.safetensors` (without `_int8`), while the
pack's canonical binding includes the suffix. The bytes are identical, and the
module matches any filename containing the alias `snofs` (or
`snofs_krea2`/`snofsSexNudesAndOther`) as **SNOFS_Krea2**. It binds the real
catalog filename into the graph.

SHA-256 of the Civitai file (must match):

```text
AFB9F7DB3122AD2BE63EF6A236B104566770DE1590F14693F452EF137BCF75A9
```

The full download URL is
<https://civitai.com/api/download/models/3333138?fileId=3219464>. If Civitai
redirects to a login page, use the model page above instead of the direct URL.

### Current realism LoRA

The only realism LoRA the tracked pack knows is
`realism_engine_krea2_v3.1.safetensors` (the last row above). It is a LoKr and a
general realism/style LoRA, not an NSFW-specific LoRA. It is not tagged NSFW in
the pack. If you want a different realism option, use the SFW candidates below;
using one requires a pack edit.

The default chain enables only the Realism Engine LoRA. Every other LoRA starts
off in both packs. Missing optional LoRAs are filtered out after the model
catalog is refreshed.

## B. Official Krea 2 Turbo (clean base; generic fallback)

These are the official/ComfyUI-repackaged Krea 2 files. The normal `krea2` pack
detects them through its generic `krea2` fallback alias and binds the actual
filename. It switches to `UNETLoader` for `.safetensors` and keeps its
9 steps / CFG 2.0 defaults. A dedicated official recipe is still the better
long-term path if you want the official 8-step / CFG 0.0 behavior.

| Role | File | Folder | Source | Size |
| --- | --- | --- | --- | --- |
| Base diffusion model (FP8, recommended) | `krea2_turbo_fp8_scaled.safetensors` | `models/unet/` or `models/diffusion_models/` | [Comfy-Org direct](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/diffusion_models/krea2_turbo_fp8_scaled.safetensors) | 13.14 GB |
| Base diffusion model (INT8 ConvRot) | `krea2_turbo_int8_convrot.safetensors` | `models/unet/` or `models/diffusion_models/` | [Comfy-Org direct](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/diffusion_models/krea2_turbo_int8_convrot.safetensors) | 13.49 GB |
| Text encoder | `qwen3vl_4b_fp8_scaled.safetensors` | `models/text_encoders/` | [Comfy-Org direct](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_fp8_scaled.safetensors) | 5.24 GB |
| VAE | `qwen_image_vae.safetensors` | `models/vae/` | [Comfy-Org direct](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/vae/qwen_image_vae.safetensors) | 253.8 MB |
| Upscaler (optional) | `4x-UltraSharp.pth` | `models/upscale_models/` | [Kim2091/UltraSharp direct](https://huggingface.co/Kim2091/UltraSharp/resolve/main/4x-UltraSharp.pth) | 67 MB |

- Official gated weights and licence:
  <https://huggingface.co/krea/Krea-2-Turbo> (accept the licence on Hugging Face
  before downloading).
- ComfyUI-ready repack and model card:
  <https://huggingface.co/Comfy-Org/Krea-2>.
- Official Turbo defaults: **8 steps, CFG 0.0** (some ComfyUI templates use
  CFG 1.0). The normal pack uses the tested 9 steps / CFG 2.0 values from
  `defaults.json`. Do not rename the file to a SNOFS name.
- For an official-default recipe, add a separate pack entry with its own
  `defaults.json` and sampler defaults in a GenModule development session.

### SFW realism LoRA candidates

Neither LoRA is in the tracked pack today, so neither is selectable until the
pack/catalog is updated. They are listed because they are SFW-oriented and
publicly available.

| LoRA | File | Source | Size | Notes |
| --- | --- | --- | --- | --- |
| Krea 2 Realism LoRA (gokaygokay) | `krea2_realism_lora.safetensors` | [Hugging Face page](https://huggingface.co/gokaygokay/Krea-2-Realism-LoRA) / [direct file](https://huggingface.co/gokaygokay/Krea-2-Realism-LoRA/resolve/main/krea2_realism_lora.safetensors) | 469 MB | Natural/candid photography; diffusers-format LoRA. Verify it loads in ComfyUI before relying on it. |
| [KREA 2] Realism Slider | `RealismSlider-v1.safetensors` | [Civitai page](https://civitai.com/models/2781697) / [direct file](https://civitai.com/api/download/models/3132956?fileId=3013604) | 6.7 MB | SFW-flagged slider; no trigger word; roughly -1 to +1. Not tested by this project. |

## Folder layout

For the **current packs**, use the `unet` folder; the app's required target is
`unet`. ComfyUI's newer examples may show `diffusion_models`, which is the same
model class.

```text
ComfyUI/
  models/
    unet/                 SNOFS_Krea2 (the int8 .safetensors)
                          OR krea2_turbo-Q5_K_M.gguf
    text_encoders/        qwen3vl_4b_fp8_scaled.safetensors
    vae/                  qwen_image_vae.safetensors
    upscale_models/       4x-UltraSharp.pth
    loras/                realism_engine_krea2_v3.1.safetensors
```

After moving files:

1. Restart ComfyUI if it was already running, so its model lists refresh.
2. In this app, open **Settings -> Model catalog** and click **Refresh from
   ComfyUI** (or **Build from ComfyUI** if the catalog is empty).
3. Open **Text -> Image**. The setup popup checks required files, shows the
   destination folder and opens source links. It never downloads or installs.
   Use its **Refresh check** button after refreshing the model catalog.
4. Open **Settings -> Engine content** for the full read-only audit. Missing
   optional LoRAs are expected if you did not download them.

The app only reads these files. It does not write, move or delete anything in
the ComfyUI folder.

The model catalog is a saved snapshot in `data/model_catalog.json`. If you
remove or rename the ComfyUI folder, old entries can still report `present: true`
until the catalog is refreshed. The setup popup reads that snapshot; it does not
scan the folder or call ComfyUI on every open. Restore the folder and click
**Refresh from ComfyUI**, or rebuild the catalog, after moving files.

## Licensing notes

- Krea 2 weights and derivatives are covered by the
  [Krea 2 Community License](https://huggingface.co/krea/Krea-2-Turbo/blob/main/LICENSE.pdf).
  This includes the SNOFS merge and the `Krea2 Turbo Q5_K_M` GGUF quantization.
- `4x-UltraSharp.pth` is **CC-BY-NC-SA 4.0**; check the licence before commercial
  use.
- Civitai models have their own page-level terms. The SNOFS base is
  NSFW-oriented; only download it if that is appropriate for your use and
  jurisdiction. The Realism Engine LoRA is a general realism/style LoRA.
