# GenAI GUI — Requirements

> Working title: **GenAI GUI** (final name TBD) · Draft v0.2 · 2026-10-17
> A local-first, open-source, Higgsfield-style generative AI studio on top of ComfyUI.
> Changelog v0.2: image-capability ladder, video + V2V/deepfake, audio suite, agent access (MCP/API), GUI tiers, JSON model manifests, open-source-models-first principle.

---

## 1. Vision & goal

Build a **complete local open-source alternative to Higgsfield**: a web app that gives
non-technical users a clean creative studio (pick a model, type an idea, get images/videos/audio,
keep characters consistent) while power users keep full control (LoRA chains, sampling settings,
staged pipelines).

- **Open-source models first.** Every capability is optimized for local open-weights models.
  Cloud/paid APIs are optional adapters that come **later** — never a requirement to use the app.
- **Local-first.** ComfyUI is the inference engine; the app is the product layer (UX, pipelines,
  assets, characters, presets). Cloud only where the user explicitly opts in.
- **Agent-accessible.** Everything the GUI can do is also exposed via API + MCP, so an AI agent
  (opencode, Claude, anything) can drive the tool directly: "take this image, add a red hat, return result."
- **Easy for anyone to adopt** — connect to an existing ComfyUI (portable or normal) in minutes.
- **Easy to add models later** — new models are **JSON manifest files** (one per model); new
  workflows are pack files. No app code needed.
- **Censorship-free** — uncensored/local LLMs and NSFW-capable image models are first-class.
- **Debuggable** — every run is visible ordered stages; any bad result is traceable to a stage.
- **GUI-first delivery** — build the interface in small steps with mock data, wire features one at a time.

## 2. Success criteria (v1)

1. Reproduce my current Krea2 "Freeze v8" outputs (same quality, same knobs) entirely from the app UI.
2. A stranger with their own ComfyUI + model files goes from zero to first image in < 10 minutes via in-app guidance.
3. Every generation saved with full metadata (recipe, prompt, seed, models, LoRAs, stages), re-runnable/pinnable.
4. Character workflows (describe → generate → swap → upscale) run as named stages with visible intermediates.
5. Adding a model = writing one JSON manifest (+ template if it's a new family).
6. **My AI agent can run an end-to-end edit via MCP**: "take D:\photos\me.png and add a red hat" → agent calls the app → app does the work → agent gets the output path/preview.
7. GUI works in simple mode for good results without touching a single advanced knob.

## 3. Target personas

- **Primary — the local creator (me):** 12GB-class GPU, NSFW-heavy use, LoRA tinkerer, wants speed + exact control + minimal graph rewiring.
- **Secondary — the newcomer:** wants "Higgsfield at home"; needs presets, sane defaults, connection wizard.
- **Third — the AI agent:** a local agent (or remote) that consumes the app through MCP/API to execute
  image/video/audio tasks on behalf of the user. Treated as a first-class client of the API.
- **Contributor — pack authors:** publish model manifests, workflow templates, presets, providers.

---

## 4. Functional requirements

Priority tags: **[v1] · [v2] · [v3] · [v4]** (see roadmap in PLAN.md). Feature ladder = one feature per step.

### 4.1 Connect & setup

- **FR-S1 [v1]** Connect to any ComfyUI via URL (default `http://127.0.0.1:8188`; auto-probe first; manual for remote/LAN).
- **FR-S2 [v1]** Capability probe on connect: version, GPU/VRAM, node packs, available model files. Drives all feature gating.
- **FR-S3 [v1]** Missing dependency = disabled feature + plain-language fix (file name, folder, link).
- **FR-S4 [v1]** Multiple connection profiles; optional auth header for remote.
- **FR-S5 [v1]** Zero config files for normal use; everything via UI.
- **FR-S6 [v2]** Launch portable ComfyUI from the app (path configured once) + health check.
- **FR-S7 [v3]** Cloud provider adapters, opt-in per generation.

### 4.2 Image generation — capability ladder

Ordered the way we'll build them; each is a separate feature later on. "Others" = the long tail.

- **FR-G1 [v1] Text → image (basic).** Model picker (file auto-matching), prompt/negative, batch, seed/steps/cfg/sampler/resolution with per-model defaults.
- **FR-G2 [v1] LoRA chain** (add/remove/reorder/strength/on-off, compatibility filtering, trigger words). **Lives in simple mode**, not hidden.
- **FR-G3 [v1] Upscale** as a one-click option (latent pass / ESRGAN class). **Simple mode.**
- **FR-G4 [v1] Enhance** prompt option (LLM) + describe option — see 4.3.
- **FR-G5 [v2] Image → image** (img2img: image + prompt + denoise strength; source = upload or library asset or file path from agent).
- **FR-G6 [v2] Edit image** (image + text instruction: add/remove/replace/style). Krea2's built-in edit chain is a known half-measure — use a proper Qwen-Image-Edit-class model (my `Qwen-Image-2.1-Turbo-Uncensored` covers gen; add the Edit variant weights when this feature starts).
- **FR-G7 [v2] Character / influencer generation** — T2I or I2I constrained to a saved character profile (see 4.4). Includes batch content generation for a persona.
- **FR-G8 [v2] Face swap (image)** — ReActor + face restore, standalone or as final stage of a chain.
- **FR-G9 [v3] Body swap & more** — masked-edit / pose-control based body transfer, plus future "others": inpaint, outpaint, background replace, restyle, relight, try-on. Each = a recipe, not new machinery.

### 4.3 Text tools (LLM-assisted)

- **FR-T1 [v1]** Prompt enhancer (optional per generation), model-appropriate output.
- **FR-T2 [v1]** Text-provider abstraction: **Ollama** (recommended local), **ComfyUI TextGenerate** (zero-install fallback), **OpenAI-compatible** (LM Studio/llama.cpp/cloud, later). Per-task override.
- **FR-T3 [v1]** Uncensored-first defaults: recommended models must not sanitize NSFW intent. Enhanced prompt shown as diff vs original, editable before running.
- **FR-T4 [v1]** Image → description: character-only and full-image modes; feeds prompts and profiles.
- **FR-T5 [v1]** Editable, savable system prompts for each text task with shipped defaults.
- **FR-T6 [v2]** Describe → save to character profile in one step.

### 4.4 Character consistency ("Soul ID", local)

- **FR-K1 [v1]** Character profiles: name, multi-reference images, gray-composite normalized reference, description, notes, preferred LoRAs.
- **FR-K2 [v1]** Profile wizard as visible stages: background removal → gray composite → describe (character-only) → review/edit → save.
- **FR-K3 [v1]** Profile usable everywhere: identity conditioning on/off, description injection on/off, independently.
- **FR-K4 [v1]** Face-swap stage as post pass (see FR-G8), multi-source support.
- **FR-K5 [v2]** Influencer mode: generate batches of content for a character persona (varied scenes/outfits/presets).
- **FR-K6 [v3]** Optional character LoRA training hook (external trainer) → managed like any LoRA.
- **FR-K7 [v3]** Per-model identity recipes stored per profile (what actually works, per family).

### 4.5 Pipelines, stages & debuggability

- **FR-J1 [v1]** Every generation = ordered stages; each stage artifact saved and inspectable.
- **FR-J2 [v1]** Re-run from any stage; clone job and change one thing.
- **FR-J3 [v1]** Exact reproducibility: recipe + params + file hashes stored per job.
- **FR-J4 [v1]** Side-by-side compare with metadata diffs.
- **FR-J5 [v2]** Pipeline editor: insert/remove/reorder optional stages without touching ComfyUI.
- **FR-J6 [v2]** Human-readable errors: "stage X failed because Y".

### 4.6 Library & assets

- **FR-L1 [v1]** Local library for all inputs/outputs (images, videos, audio). Never cloud by default.
- **FR-L2 [v1]** Full metadata per asset (prompt, enhanced prompt, seed, models, LoRAs, recipe, character, stages).
- **FR-L3 [v1]** Gallery: thumbnails, filters (type, model, character, date, favorites, NSFW flag), search, detail view.
- **FR-L4 [v1]** Actions: reuse seed/params, re-run, download, delete, favorite, **send to another feature** (image → edit / video / face swap).
- **FR-L5 [v2]** Tags, collections, disk usage, import/export bundles.

### 4.7 Presets & recipes

- **FR-P1 [v1]** Preset = bundle: prompt template + style tokens + LoRA chain + settings (+ optional reference requirement). Categories: Camera / Effect / Style / Realism / NSFW.
- **FR-P2 [v1]** One-click "apply preset to my idea" in simple mode.
- **FR-P3 [v2]** Import/export preset as single JSON; starter pack shipped.
- **FR-P4 [v3]** Community pack registry (browse/install presets + manifests).

### 4.8 Models & extensibility

- **FR-X1 [v1]** **One JSON manifest per model** (`packs/models/<model>.json`): files + filename match patterns, family, required TE/VAE, defaults, compatible LoRAs, VRAM hints, capabilities, sources, license.
- **FR-X2 [v1]** Add a model = drop JSON (+ template if new family). UI picks it up. No code changes.
- **FR-X3 [v1]** Model manager: list detected models, which recipes use them, missing-file report with fix instructions.
- **FR-X4 [v2]** One-click download with size/hash verification (HF/CivitAI URLs in manifest).
- **FR-X5 [v1]** Graceful degradation: a model missing a capability just hides that toggle.
- **FR-X6 [v3]** Import my own ComfyUI workflow (API export) as a personal template.

### 4.9 Video

- **FR-V1 [v2]** **Image → video** first (library image → clip), then **text → video**. Best open models for 12GB class (Wan / LTX / HunyuanVideo families, GGUF quantized), chosen by manifest VRAM hints.
- **FR-V2 [v2]** **Audio in video** where the model supports it (my H3-class generates audio natively; modern picks vary — decide at build time); otherwise pair with audio models (4.10).
- **FR-V3 [v2]** Camera-motion & motion presets (dolly, zoom, orbit, action) as recipe bundles.
- **FR-V4 [v2]** Batch variations: one concept, N takes, pick best ("Genjutsu"-style).
- **FR-V5 [v3]** **Video → video**: face swap in video (frame-based swap + restore + temporal smoothing) and character/subject insertion into a source clip (meme-template workflows: "9mm go bang"-style videos, dance clips) via subject-to-video model classes. Body swap in video lives here.
- **FR-V6 [v3]** Video upscale / interpolation stages.

### 4.10 Audio

- **FR-Au1 [v3]** **Text → speech** + **voice cloning** (TTS family: Kokoro/F5/Chatterbox/XTTS class — pick at build time).
- **FR-Au2 [v3]** **Text → music** (ACE-Step / Stable Audio Open class).
- **FR-Au3 [v3]** **Foley / SFX / video-to-audio** (MMAudio class) — adds sound to generated clips.
- **FR-Au4 [v3]** **Speech → text** (Whisper class) — captions, descriptions, agent input.
- **FR-Au5 [v3]** **Lipsync** — audio-driven talking video (LatentSync/MuseTalk class).
- **FR-Au6 [v3]** Voice separation/cleanup utilities (Demucs class) if needed for lipsync/dubbing workflows.

### 4.11 Agent access (MCP/API)

- **FR-A1 [v1]** The app's own REST API is the single interface **used by both the GUI and agents** (no separate logic paths).
- **FR-A2 [v1]** MCP server (shipped inside the backend, one toggle in Settings): exposes capabilities as tools. Starting toolset:
  - `app_info` / `list_capabilities` — what's installed, which models/recipes exist, parameter schemas.
  - `generate_image` — text → image (+ recipe/model/LoRA/upscale/enhance options).
  - `edit_image` — image + instruction → edited image.
  - `describe_image`, `enhance_prompt` — text helpers.
  - `image_to_video`, `text_to_video`, `video_to_video` — video (added with video features).
  - `face_swap`, `upscale_image` — utility ops.
  - `list_characters` / use character in generation; `search_library`, `get_asset` — asset access.
  - `job_status`, `job_result`, `cancel_job` — async job control for long runs.
  - New features add their tool as part of their build step (every step ends MCP-complete).
- **FR-A3 [v1]** Inputs accept: library asset ids, local file paths (agent runs locally; app copies into library), or uploaded bytes (remote agents).
- **FR-A4 [v1]** Results return: asset id, absolute file path, preview URL, metadata; plus MCP resources for gallery browsing/visual preview.
- **FR-A5 [v1]** Async pattern for slow ops (video/audio): submit → poll `job_status` (or MCP progress notifications) → `job_result`.
- **FR-A6 [v1]** Security: localhost-only by default, optional token, file-path allowlist (configurable "agent inbox" folder) so an agent can't read arbitrary disk paths through the app.
- **FR-A7 [v2]** API/MCP docs page exported from the live app (always accurate) + example agent prompts.

### 4.12 GUI

- **FR-U1 [v1]** **Two-tier controls per feature:** **Simple** (prompt, model, LoRAs, upscale, enhance, identity, batch — enough for great results with zero tuning) and **Advanced** (seed, steps, CFG, sampler, scheduler, resolution, denoise, template/recipe overrides).
- **FR-U2 [v1]** Flat, minimal design; **dark base + pastel accents**; generous spacing; no clutter. Keyboard-friendly.
- **FR-U3 [v1]** Everything built as documented Vue SFC components (design tokens + component inventory; detailed button/section inventory = next session deliverable, before backend work).
- **FR-U4 [v1]** Screens: Onboarding/Connect · Generate (image) · Gallery · Characters · Presets · Jobs (stage inspector) · Settings (connections, text providers, agent/MCP, storage). Later: Edit · Video · Audio · Models · Canvas.
- **FR-U5 [v1]** UI built first against a **mock API layer**, wired to the real backend feature-by-feature (GUI-first strategy).
- **FR-U6 [v2]** Progress everywhere: per-stage status, live previews where ComfyUI provides them, cancellation.

### 4.13 Content & NSFW policy

- **FR-N1 [v1]** NSFW fully supported locally/offline; no censorship in app or recommended models.
- **FR-N2 [v1]** Optional age confirmation first run; gallery content toggles.
- **FR-N3 [v1]** Cloud calls off by default, per-profile opt-in, visibly indicated.
- **FR-N4 [v1]** No telemetry/accounts ever, unless future opt-in.
- **FR-N5 [v1]** Deepfake/V2V features are local tools with user responsibility framing; no auto-distribution features; model licenses documented per manifest.

---

## 5. Non-functional requirements

- **NFR-1 Hardware floor:** 12GB VRAM / 32GB RAM target; app process light (<300MB idle, no GPU).
- **NFR-2 Performance:** app overhead negligible; UI responsive during generation.
- **NFR-3 Privacy:** 100% local default; nothing leaves the machine unless user configures a provider.
- **NFR-4 Compatibility:** upstream ComfyUI; version probe + warnings; no exotic custom node dependence (no IAMCCS; ReActor only for swap; core nodes preferred).
- **NFR-5 Robustness:** queue survives restarts; failed jobs leave actionable state; ComfyUI disconnect handled.
- **NFR-6 Modularity:** each capability = a self-contained step (pack + GUI panel + API/MCP tool). Features can land one at a time without destabilizing others.
- **NFR-7 Extensibility:** packs are JSON with versioned JSON Schemas; bad packs can't crash core.
- **NFR-8 UX:** simple mode default; advanced on demand; fast navigation; dark/pastel flat theme.
- **NFR-9 API stability:** GUI and agent share one API surface; contract changes are versioned and tested (GUI regression suite).

## 6. Data model (top level)

Asset (image/video/audio) · Job (pipeline run) · Stage (artifact + params snapshot) · Recipe (template + bindings + flags) ·
ModelManifest (JSON) · LoRA · Character · Preset · Connection profile · TextProvider config · AgentConfig (token, allowlist).
Local SQLite + asset folder; exportable.

## 7. Scope

- **v1 (Steps 1–4):** GUI foundation (mock) · backend core + connect/probe + MCP skeleton · T2I with LoRA chain + upscale + advanced tier · text providers + enhance + describe · gallery · jobs.
- **v2 (Steps 5–8):** I2I · Edit (Qwen-Image-Edit class) · Characters (+identity, wizard) · face swap · presets v0 · stage inspector.
- **v3 (Steps 9–12):** body-swap & image utility recipes · video (i2v/t2v, motion presets, model manager) · V2V/deepfake/meme · audio suite (TTS/clone/music/foley/STT/lipsync).
- **v4 (Step 13+):** cloud adapters · community registry · canvas/multi-scene · character LoRA training hook · multi-user if ever.
- Agent/MCP grows with every step (not a separate phase).

**Non-goals:** multi-user accounts/teams, billing, hosting GPUs, mobile apps, replacing the ComfyUI graph editor for arbitrary graphs, bundling model weights.

## 8. Open decisions

1. **Project name + code license** (suggest Apache-2.0; AGPL if blocking closed SaaS forks matters).
2. **Default settings/tuning** — deferred until each feature step (decide defaults during implementation).
3. **GUI component/button inventory** — next session deliverable (before backend starts).
4. Single-user local-first for v1 (recommended) — confirm.
5. Default text provider = Ollama with uncensored small model (recommended, decide at Step 4).
6. Age confirmation on first run: on by default (recommended) — confirm.
