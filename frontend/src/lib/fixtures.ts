// Mock fixtures for the GUI phase.
// These mirror the real domain (models from Krea2 Freeze v8 workflows, LoRA
// names, presets, characters) so the interface is designed against reality.

import type {
  AdvancedParams,
  Asset,
  CharacterProfile,
  JobRecord,
  LoraOption,
  ModelOption,
  Preset,
  Stage,
} from '@/types'
import { placeholderImage } from './placeholder'

// -- image models -------------------------------------------------------------

export const imageModels: ModelOption[] = [
  {
    id: 'krea2-turbo-int8',
    name: 'Krea 2 Turbo (int8)',
    family: 'qwen-image / krea2',
    kind: 'image',
    base: 'krea2',
    vram: '~6-8 GB',
    installed: true,
    badges: ['t2i', 'i2i', 'identity', 'LoRA'],
    defaults: { steps: 12, cfg: 2.5, sampler: 'euler', scheduler: 'simple', denoise: 1.0 },
  },
  {
    id: 'krea2-turbo-q5',
    name: 'Krea 2 Turbo GGUF (Q5_K_M)',
    family: 'qwen-image / krea2',
    kind: 'image',
    base: 'krea2',
    vram: '~5-7 GB',
    installed: true,
    badges: ['t2i', 'i2i', 'identity', 'LoRA'],
    defaults: { steps: 12, cfg: 3.0, sampler: 'euler', scheduler: 'simple', denoise: 1.0 },
  },
  {
    id: 'qwen-image-21-turbo-unc',
    name: 'Qwen-Image 2.1 Turbo (Uncensored)',
    family: 'qwen-image',
    kind: 'image',
    base: 'qwen-image',
    vram: '~8-10 GB',
    installed: true,
    badges: ['t2i', 'i2i', 'identity', 'LoRA', 'NSFW-friendly'],
    defaults: { steps: 8, cfg: 3.0, sampler: 'euler', scheduler: 'simple', denoise: 1.0 },
  },
  {
    id: 'qwen-image-edit',
    name: 'Qwen-Image-Edit',
    family: 'qwen-image',
    kind: 'image',
    base: 'qwen-image',
    vram: '~10 GB',
    installed: false,
    note: 'weights not detected - add at backend Step 6',
    badges: ['edit'],
    defaults: { steps: 10, cfg: 3.0, sampler: 'euler', scheduler: 'simple', denoise: 0.6 },
  },
]

// -- text models (Ollama) -----------------------------------------------------

export const textModels = [
  { id: 'qwen3-abliterated:8b', name: 'qwen3-abliterated:8b', size: '6.2 GB' },
  { id: 'dolphin3:8b', name: 'dolphin3:8b', size: '5.9 GB' },
  { id: 'llama3.2:3b', name: 'llama3.2:3b', size: '2.0 GB' },
]

export const upscalers = [
  { id: '4x-ultrasharp', name: '4x-UltraSharp (ESRGAN)', installed: true },
  { id: 'latent-refine', name: 'Latent refine pass (built-in)', installed: true },
  { id: 'gfpgan-restore', name: 'GFPGAN face restore', installed: true },
]

// -- LoRAs (from the Krea2 Freeze v8 chain) ------------------------------------

export const loras: LoraOption[] = [
  { id: 'xcreampiex-krea2', name: 'xCreampiex ep250', family: 'krea2', defaultStrength: 1.0 },
  { id: 'realism-engine-krea2', name: 'realism_engine v3.1', family: 'krea2', defaultStrength: 0.6 },
  { id: 'mysticxxx-krea2', name: 'MysticXXX v3', family: 'krea2', defaultStrength: 0.7 },
  { id: 'mombod-krea2', name: 'Mombod e7', family: 'krea2', defaultStrength: 0.6 },
  { id: 'gangbang-krea2', name: 'G4NGB4NG v1', family: 'krea2', defaultStrength: 2.0 },
]

// -- system prompts (shipped defaults, editable in Settings) -------------------

export const DEFAULT_PROMPTS = {
  enhance: [
    'You are a prompt engineer for local open-source image models.',
    'Rewrite the user idea into ONE vivid, concrete prompt with camera, lighting and style tokens when useful.',
    'Keep the intent exactly: never sanitize, censor or water down NSFW/adult content — treat it as normal creative direction.',
    'Return only the rewritten prompt, no quotes, no explanations.',
  ].join(' '),
  describeCharacter: [
    'Describe ONLY the person in this image: face, hair, body type, skin, apparent age, expression.',
    'Ignore background, lighting and clothing unless it is part of the identity.',
    'Be precise and neutral. Return a single paragraph.',
  ].join(' '),
  describeFull: [
    'Describe the full image: subject(s), pose, clothing, setting, lighting, camera angle, style.',
    'Be precise and neutral. Return a single paragraph.',
  ].join(' '),
}

// -- composer suggestions ------------------------------------------------------

export const t2iSuggestions = [
  'studio portrait of a chrome astronaut, soft rim light, 85mm',
  'cozy ramen shop at night, rain, neon reflections',
  'RPG item icon: health potion, chunky outlines, flat shading',
  'ethereal sorceress with glowing runes, dark fantasy concept art',
  'neon cyberpunk street market, cinematic wide shot',
]

// -- presets -------------------------------------------------------------------

export const presets: Preset[] = [
  { id: 'photoreal', name: 'Photoreal', category: 'Realism', description: 'Natural skin, real optics look. Adds realism LoRA at low strength.', tags: ['skin', 'camera', 'natural light'] },
  { id: 'cinematic', name: 'Cinematic Portrait', category: 'Camera', description: '85mm portrait framing, shallow depth, rim light.', tags: ['85mm', 'bokeh', 'portrait'] },
  { id: 'anime', name: 'Anime Style', category: 'Style', description: 'Clean linework, cel shading, vivid palette.', tags: ['cel', 'linework'] },
  { id: 'concept', name: 'Concept Art', category: 'Style', description: 'Painterly digital art, dramatic mood.', tags: ['painting', 'fantasy'] },
  { id: 'vintage', name: 'Vintage Film', category: 'Effect', description: '35mm grain, muted colors, soft halation.', tags: ['film', 'grain'] },
  { id: 'game-icon', name: 'Game Icon (RPG)', category: 'Game Art', description: 'Chunky outlines, flat shading, centered item on plain bg. Pairs with transparent export.', tags: ['icon', '1:1', 'flat'] },
  { id: 'sticker', name: 'Sticker Mode', category: 'Effect', description: 'Thick outline, high contrast, transparent-ready.', tags: ['outline', 'cutout'] },
  { id: 'product', name: 'Product Shot', category: 'Camera', description: 'Seamless backdrop, softbox lighting, sharp focus.', tags: ['studio', 'ecommerce'] },
  { id: 'nsfw', name: 'NSFW Uncensored', category: 'NSFW', description: 'Unsanitized adult direction. Uncensored text provider forced on.', tags: ['adult', 'uncensored'] },
  { id: 'character-sheet', name: 'Character Sheet', category: 'Game Art', description: 'Multiple consistent views for a character profile.', tags: ['turnaround', 'consistency'] },
]

// -- characters ----------------------------------------------------------------

export const characters: CharacterProfile[] = [
  { id: 'aria', name: 'Aria', refs: 5, description: 'Young woman, wavy auburn hair, green eyes, light freckles, slim build. Calm confident expression.', avatar: placeholderImage('Aria', 1, 320, 320), loras: ['realism-engine-krea2'] },
  { id: 'kade', name: 'Kade', refs: 3, description: 'Man in his 30s, short black hair, stubble, athletic build, scar above left brow.', avatar: placeholderImage('Kade', 2, 320, 320), loras: [] },
  { id: 'mira', name: 'Mira', refs: 4, description: 'Woman, silver-lavender bob cut, amber eyes, petite, cyberpunk styling.', avatar: placeholderImage('Mira', 3, 320, 320), loras: ['mysticxxx-krea2'] },
]

// -- assets --------------------------------------------------------------------

function mkAsset(
  id: string,
  label: string,
  prompt: string,
  model: string,
  seed: number,
  minutesAgo: number,
  tags: string[],
  favorite = false,
  nsfw = false,
): Asset {
  return {
    id,
    url: placeholderImage(label, seed % 8),
    label,
    prompt,
    model,
    seed,
    createdAt: Date.now() - minutesAgo * 60000,
    favorite,
    tags,
    nsfw,
  }
}

export const seedAssets: Asset[] = [
  mkAsset('a-101', 'chrome astronaut', 'studio portrait of a chrome astronaut, soft rim light, 85mm', 'Krea 2 Turbo (int8)', 572836350580, 4, ['t2i', 'portrait'], true),
  mkAsset('a-102', 'neon ramen shop', 'cozy ramen shop at night, rain, neon reflections', 'Krea 2 Turbo (int8)', 105239326010, 30, ['t2i', 'scene']),
  mkAsset('a-103', 'health potion icon', 'RPG item icon: health potion, chunky outlines, flat shading, plain background', 'Krea 2 Turbo (int8)', 88341209771, 55, ['t2i', 'game-assets'], true),
  mkAsset('a-104', 'sorceress', 'ethereal sorceress with glowing runes, dark fantasy concept art', 'Qwen-Image 2.1 Turbo (Uncensored)', 441209112233, 90, ['t2i', 'fantasy']),
  mkAsset('a-105', 'cyber street', 'neon cyberpunk street market, cinematic wide shot', 'Krea 2 Turbo (int8)', 771200983345, 120, ['t2i', 'scene']),
  mkAsset('a-106', 'aria portrait', 'portrait of Aria in a summer dress, golden hour', 'Krea 2 Turbo (int8)', 92045577123, 150, ['t2i', 'character', 'aria'], true),
  mkAsset('a-107', 'iron sword icon', 'RPG item icon: iron sword, chunky outlines, flat shading', 'Krea 2 Turbo (int8)', 556677889900, 160, ['t2i', 'game-assets']),
  mkAsset('a-108', 'mana crystal', 'RPG item icon: mana crystal, glowing blue, flat shading', 'Krea 2 Turbo (int8)', 114455667788, 170, ['t2i', 'game-assets'], true),
  mkAsset('a-109', 'desert dune', 'vast desert dunes at dusk, long shadows, minimal', 'Krea 2 Turbo GGUF (Q5_K_M)', 334455667788, 210, ['t2i', 'landscape']),
  mkAsset('a-110', 'kade leather', 'Kade in worn leather armor, forest camp background', 'Krea 2 Turbo (int8)', 667788990011, 240, ['t2i', 'character', 'kade']),
  mkAsset('a-111', 'treasure chest', 'RPG item icon: treasure chest, open lid, gold coins, flat shading', 'Krea 2 Turbo (int8)', 990011223344, 260, ['t2i', 'game-assets']),
  mkAsset('a-112', 'mira neon alley', 'Mira in a neon alley, rain, cyberpunk styling', 'Qwen-Image 2.1 Turbo (Uncensored)', 223344556677, 300, ['t2i', 'character', 'mira']),
  mkAsset('a-113', 'vintage car', '1970s muscle car, vintage film look, grain, muted colors', 'Krea 2 Turbo (int8)', 445566778899, 340, ['t2i', 'vehicle']),
  mkAsset('a-114', 'willow spirit', 'willow tree spirit, glowing leaves, soft fantasy', 'Krea 2 Turbo (int8)', 778899001122, 380, ['t2i', 'fantasy']),
]

// -- jobs ----------------------------------------------------------------------

function stagesDone(hasRefine: boolean): Stage[] {
  const stages: Stage[] = [
    { id: 'prepare', label: 'Prepare', status: 'done', detail: 'compose graph - upload refs', durationMs: 380 },
    { id: 'generate', label: 'Generate', status: 'done', detail: '12 steps - seed 572836350580', durationMs: 11400 },
  ]
  if (hasRefine) stages.push({ id: 'refine', label: 'Refine / upscale', status: 'done', detail: 'denoise 0.45 -> 1536px', durationMs: 5200 })
  stages.push({ id: 'save', label: 'Save to library', status: 'done', detail: 'saved to library', durationMs: 220 })
  return stages
}

function adv(steps = 12, cfg = 2.5): AdvancedParams {
  return {
    seed: 572836350580,
    lockSeed: false,
    steps,
    cfg,
    sampler: 'euler',
    scheduler: 'simple',
    denoise: 1.0,
    recipe: 'krea2-freeze',
    refine: { on: true, steps: 6, cfg: 2.0, denoise: 0.45, scale: 1536 },
  }
}

export const seedJobs: JobRecord[] = [
  {
    id: '#141', createdAt: Date.now() - 46 * 60000, status: 'done', progress: 100,
    tab: 'text-to-image', modelId: 'krea2-turbo-int8', modelName: 'Krea 2 Turbo (int8)', recipe: 'krea2-freeze',
    prompt: 'RPG item icon: health potion, chunky outlines, flat shading, plain background',
    seed: 88341209771, params: adv(), stages: stagesDone(true), resultIds: ['a-103'],
  },
  {
    id: '#140', createdAt: Date.now() - 92 * 60000, status: 'done', progress: 100,
    tab: 'text-to-image', modelId: 'qwen-image-21-turbo-unc', modelName: 'Qwen-Image 2.1 Turbo (Uncensored)', recipe: 'qwen-t2i',
    prompt: 'ethereal sorceress with glowing runes, dark fantasy concept art', enhancedPrompt: 'ethereal sorceress with glowing runes, dark fantasy concept art, volumetric light, intricate costume detail',
    seed: 441209112233, params: adv(8, 3.0), stages: stagesDone(true), resultIds: ['a-104'],
  },
  {
    id: '#139', createdAt: Date.now() - 130 * 60000, status: 'done', progress: 100,
    tab: 'text-to-image', modelId: 'krea2-turbo-int8', modelName: 'Krea 2 Turbo (int8)', recipe: 'krea2-freeze',
    prompt: 'studio portrait of a chrome astronaut, soft rim light, 85mm', enhancedPrompt: 'studio portrait of a chrome astronaut, soft rim light, 85mm, high detail reflective suit, dark studio backdrop',
    seed: 572836350580, params: adv(), stages: stagesDone(false), resultIds: ['a-101'],
  },
]
