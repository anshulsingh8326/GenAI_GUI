# Manual model downloads (Krea 2 / T2I_main)

Status: **manual only**. The app never downloads, moves or deletes model files.
Download the files yourself, put them in the ComfyUI folders below, then use
**Settings -> Model catalog -> Refresh from ComfyUI** and **Settings -> Engine
content** to verify what the app can see.

Links were checked on **2026-10-29**. Sizes are approximate; the linked page or
repository is authoritative. Model licences apply to the downloaded weights.

## Two configurations

The tracked `krea2` T2I_main pack supports two base files: **SNOFS_Krea2**
(int8) and **Krea2 Turbo Q5_K_M** (GGUF). The official Comfy-Org FP8/INT8 files
use different filenames and defaults, so they are **not interchangeable**
without a pack update.

- **A. Current tracked pack.** Use one of the two tested bases in section A,
  plus the shared text encoder, VAE and optional files. This runs with the
  current pack without editing the module.
- **B. Official Krea 2 Turbo (Comfy-Org FP8/INT8).** These are clean base
  files, but using them in this app requires a pack/model update in the separate
  GenModule session. They are not a drop-in replacement for section A.

## A. Current tracked T2I_main pack

The pack supports two tested base models. Download **one**; the text encoder,
VAE and upscaler are shared. The SNOFS base and the Realism Engine LoRA are
community/NSFW-oriented; they are labelled below. The other LoRAs in
`requirements.json` are optional and are not linked here.

| Model | File in ComfyUI | Folder | Source | Size |
| --- | --- | --- | --- | --- |
| **SNOFS_Krea2** (int8) | `snofsSexNudesAndOther_krea2TurboV14_int8.safetensors` | `models/unet/` | [SNOFS Merged - Krea 2 Turbo v1.4](https://civitai.com/models/2416142?modelVersionId=3333138) - **NSFW model page; Civitai login/opt-in may be required** | 12.8 GB |
| **Krea2 Turbo Q5_K_M** (GGUF) | `krea2_turbo-Q5_K_M.gguf` | `models/unet/` | [Vantage GGUF repository](https://huggingface.co/vantagewithai/Krea-2-Turbo-GGUF) / [direct file](https://huggingface.co/vantagewithai/Krea-2-Turbo-GGUF/resolve/main/krea2_turbo-Q5_K_M.gguf) | 8.87 GB |
| Text encoder | `qwen3vl_4b_fp8_scaled.safetensors` | `models/text_encoders/` | [Comfy-Org direct](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_fp8_scaled.safetensors) | 5.24 GB |
| VAE | `qwen_image_vae.safetensors` | `models/vae/` | [Comfy-Org direct](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/vae/qwen_image_vae.safetensors) | 253.8 MB |
| Upscaler (optional) | `4x-UltraSharp.pth` | `models/upscale_models/` | [Kim2091/UltraSharp direct](https://huggingface.co/Kim2091/UltraSharp/resolve/main/4x-UltraSharp.pth) | 67 MB |
| Realism LoRA (optional) | `realism_engine_krea2_v3.1.safetensors` | `models/loras/` | [Realism Engine mirror](https://huggingface.co/RazzzHF/realism_engine_krea2/resolve/main/realism_engine_krea2_v3.1.safetensors) - **uncensored/NSFW-capable LoRA** | 1.56 GB |

Both base models have been tested by the project owner. Use the GGUF when you
want the smaller download; use SNOFS_Krea2 when you want the pack's reference
path. The GGUF path uses ComfyUI-GGUF, which the setup installs as a required
core node.

Current audit limitation: `requirements.json` still marks SNOFS_Krea2 as
required and Q5_K_M as optional, so a Q5-only install can show a missing
required base until the GenModule update makes them alternatives. Both load and
run.

### SNOFS_Krea2 file name and checksum

Do **not** rename downloaded files. The Civitai download is named
`snofsSexNudesAndOther_krea2TurboV14.safetensors`, while the current build still
checks for `..._int8.safetensors`. The bytes are identical. The T2I_main
GenModule update will match any name containing `snofs` as `SNOFS_Krea2`, so the
downloaded name will work unchanged.

Until that update lands, the GGUF base works with its current name, or use the
exact `_int8` file if it is already present. Do not rename just to satisfy the
old check; the alias fix is the intended solution.

SHA-256 of the Civitai file (must match):

```text
AFB9F7DB3122AD2BE63EF6A236B104566770DE1590F14693F452EF137BCF75A9
```

The full download URL is
<https://civitai.com/api/download/models/3333138?fileId=3219464>. If Civitai
redirects to a login page, use the model page above instead of the direct URL.

### Current realism LoRA

The only realism LoRA the tracked pack knows is
`realism_engine_krea2_v3.1.safetensors` (the last row above). It is a LoKr, and
v3.1 is uncensored/NSFW-capable. It is **not** an SFW-only realism LoRA. If you
only need a clean realism option, see section B; using it requires a pack edit.

If the other optional LoRAs are absent, the Text -> Image UI filters them out of
the default chain after the model catalog is refreshed. You can also turn any
remaining LoRA off in the LoRA panel.

## B. Official Krea 2 Turbo (clean base; requires a pack update)

These are the official/ComfyUI-repackaged Krea 2 files. They are the preferred
base for a new public pack, but the tracked `krea2` pack does not reference
these filenames yet.

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
  CFG 1.0). The current SNOFS pack uses different defaults, so do not simply
  rename the official file to the SNOFS filename.
- To use this base in the app, update the pack's model binding, workflow
  filename and sampler defaults in a separate GenModule session.

### SFW realism LoRA candidates

Neither LoRA is in the tracked pack today, so neither is selectable until the
pack/catalog is updated. They are listed because they are SFW-oriented and
publicly available.

| LoRA | File | Source | Size | Notes |
| --- | --- | --- | --- | --- |
| Krea 2 Realism LoRA (gokaygokay) | `krea2_realism_lora.safetensors` | [Hugging Face page](https://huggingface.co/gokaygokay/Krea-2-Realism-LoRA) / [direct file](https://huggingface.co/gokaygokay/Krea-2-Realism-LoRA/resolve/main/krea2_realism_lora.safetensors) | 469 MB | Natural/candid photography; diffusers-format LoRA. Verify it loads in ComfyUI before relying on it. |
| [KREA 2] Realism Slider | `RealismSlider-v1.safetensors` | [Civitai page](https://civitai.com/models/2781697) / [direct file](https://civitai.com/api/download/models/3132956?fileId=3013604) | 6.7 MB | SFW-flagged slider; no trigger word; roughly -1 to +1. Not tested by this project. |

## Folder layout

For the **current pack**, use the `unet` folder; the app's required target is
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
3. Open **Settings -> Engine content** and check that the required files are
   present. Missing optional LoRAs are expected if you did not download them.

The app only reads these files. It does not write, move or delete anything in
the ComfyUI folder.

## Licensing notes

- Krea 2 weights and derivatives are covered by the
  [Krea 2 Community License](https://huggingface.co/krea/Krea-2-Turbo/blob/main/LICENSE.pdf).
  This includes the SNOFS merge and the `Krea2 Turbo Q5_K_M` GGUF quantization.
- `4x-UltraSharp.pth` is **CC-BY-NC-SA 4.0**; check the licence before commercial
  use.
- Civitai models have their own page-level terms. The SNOFS base and the
  Realism Engine LoRA in section A are NSFW-oriented; only download them if that
  is appropriate for your use and jurisdiction.
