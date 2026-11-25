/**
 * i2i_main - frontend/API contract for the strict Image -> Image module.
 *
 * These types mirror the JSON boundary exactly (camelCase on the wire).
 * The backend remains the authority for ranges, source limits and file
 * presence; these values are for rendering controls and showing sensible
 * warnings, not for replacing server checks.
 *
 * This folder is canonical. The runtime copies under
 * frontend/src/features/image-to-image/ must stay byte-identical.
 */

export type I2IJobStatus = 'queued' | 'running' | 'done' | 'error'
export type I2IStageStatus = 'pending' | 'running' | 'done' | 'skipped' | 'error'
export type I2IWorkflowPath = 'full' | 'img2img'

/** One numeric control contract from the tracked pack. */
export interface I2IRange {
  label: string
  /** Safe range - what the GUI slider exposes. */
  min: number
  max: number
  default: number
  step: number
  /** Narrower "best results" band; values outside it are warning-only. */
  recommendedMin: number
  recommendedMax: number
  /** Engine/model absolute limits. Never expose a control outside these. */
  hardMin: number
  hardMax: number
  unit: string
  description: string
  precision: number
}

export interface I2IValidationIssue {
  code: string
  message: string
  field?: string
  min?: number
  max?: number
  recommendedMin?: number
  recommendedMax?: number
  modelId?: string
  severity?: 'error' | 'warning' | string
  node?: string
  found?: { name: string; target: string; catalogId: string }
}

/** Warnings have the same shape as validation issues. */
export type I2IWarning = I2IValidationIssue

export interface I2IModelDefaults {
  steps: number
  cfg: number
  sampler: string
  scheduler: string
  denoise: number
}

export interface I2IModelRanges {
  steps: I2IRange
  cfg: I2IRange
  denoise: I2IRange
  batch: I2IRange
  seed: I2IRange
}

export interface I2IComponentState {
  role: string
  /** Resolved real filename (or the declared filename when nothing matched). */
  name: string
  declaredName: string
  target: string
  /** true/false when the user catalog knows; null when presence is unknown. */
  present: boolean | null
  catalogId: string
  /** Only present on the text encoder component. */
  loader?: 'CLIPLoader' | 'CLIPLoaderGGUF' | string
}

export interface I2ITextEncoderLocation {
  name: string
  target: string
  catalogId: string
}

export interface I2IModel {
  id: string
  catalogId: string
  label: string
  shortLabel: string
  family: string
  base: string
  description: string
  /** Pack that owns this model and its graph/defaults. */
  packId: string
  packLabel: string
  loader: 'UNETLoader' | 'UnetLoaderGGUF' | string
  /** Resolved diffusion filename bound into the graph. */
  file: string
  declaredFile: string
  target: string
  aliases: string[]
  fallbackAliases: string[]
  excludeAliases: string[]
  baseGroup: string
  baseGroupLabel: string
  required: boolean
  nsfw: boolean
  pageUrl: string
  /** Resolved text-encoder filename. */
  textEncoder: string
  declaredTextEncoder: string
  textEncoderAliases: string[]
  textEncoderExcludeAliases: string[]
  textEncoderTarget: string
  textEncoderLoader: 'CLIPLoader' | 'CLIPLoaderGGUF' | string
  /** Set when a compatible encoder exists in the wrong ComfyUI folder. */
  textEncoderLocation: I2ITextEncoderLocation | null
  clipType: string
  /** Resolved 2.1 VAE filename. */
  vae: string
  declaredVae: string
  vaeAliases: string[]
  vaeExcludeAliases: string[]
  vaeTarget: string
  workflow: string
  composer: string
  vram: string
  capabilities: string[]
  verified: boolean
  tested: boolean
  notes: string
  defaults: I2IModelDefaults
  ranges: I2IModelRanges
  /** Main diffusion file presence. */
  present: boolean | null
  /** False when any required component is known to be missing. */
  ready: boolean
  missing: string[]
  components: I2IComponentState[]
  catalogIdFound: string
  /** The older Qwen Image VAE exists but is not the 2.1 VAE. */
  oldVaePresent: boolean
  oldVaeName: string
}

export interface I2ISamplerOption {
  id: string
  label: string
}

export interface I2IResolutionOption {
  value: number
  label: string
}

export interface I2ILimits {
  promptMaxChars: number
  negativePromptMaxChars: number
  maxBatch: number
  jobTimeoutSeconds: number
  pollIntervalSeconds: number
  historyTimeoutSeconds: number
  downloadTimeoutSeconds: number
  downloadRetries: number
}

export interface I2ISourceLimits {
  maxBytes: number
  maxSide: number
  maxPixels: number
  mimeTypes: string[]
  maxDataUrlChars: number
  thumbSize: number
  /** Above this data-URL length the source stays in memory only. */
  persistMaxChars: number
  /** How many reference images the encoder accepts (currently 1..3). */
  maxImages: number
}

export interface I2IEngineProbe {
  connected: boolean
  url?: string
  detail?: string
  installed?: Array<{ name: string; sizeGb?: number }>
  loaded?: unknown[]
  queue?: { running: number; pending: number }
}

export interface I2IEngine {
  comfyui: I2IEngineProbe
  ready: boolean
}

export interface I2ICatalogDefaults {
  modelId: string
  prompt: string
  negativePrompt: string
  resolution: number
  batch: number
  seed: number
  lockSeed: boolean
  steps: number
  cfg: number
  sampler: string
  scheduler: string
  denoise: number
  cacheDevice: string
  cacheDtype: string
  recipeId: string
}

export interface I2IRecipe {
  id: string
  label: string
  workflow: string
  /** Only the i2i composer ships with this module. */
  composer?: string
  engine: string
  description: string
}

export interface I2IWorkflowInfo {
  path: string
  nodeCount: number
  format: 'comfyui-api'
  /** Reference images the encoder binds (1..3). */
  referenceSlots: number
}

export interface I2IPreflight {
  errors: I2IWarning[]
  warnings: I2IWarning[]
}

export interface I2ICatalog {
  ok: boolean
  moduleId: string
  pack: {
    id: string
    label: string
    description: string
    nsfw: boolean
    order: number
  }
  recipe: I2IRecipe
  workflow: I2IWorkflowInfo
  model: I2IModel | null
  models: I2IModel[]
  selectedModelId: string | null
  defaults: I2ICatalogDefaults
  ranges: I2IModelRanges | Record<string, never>
  samplers: I2ISamplerOption[]
  resolutions: I2IResolutionOption[]
  cacheDevices: string[]
  cacheDtypes: string[]
  limits: I2ILimits
  source: I2ISourceLimits
  engine: I2IEngine
  /** True only when the model files exist and no preflight error is active. */
  ready: boolean
  preflight: I2IPreflight
  /** errors + warnings, kept for one flat warning list. */
  warnings: I2IWarning[]
  nodeInfo?: Record<string, boolean | null>
}

// -- source image -------------------------------------------------------------

/** In-memory source state. The data URL is persisted separately, size-gated. */
export interface I2ISourceState {
  name: string
  dataUrl: string
  width: number
  height: number
  sizeBytes: number
  /** True when this source came from the saved browser payload. */
  restored: boolean
}

// -- request -----------------------------------------------------------------

export interface I2IJobRequest {
  modelId?: string
  recipeId?: string | null
  prompt: string
  negativePrompt?: string
  /** 1..3 reference images, labelled Image 1..n in the GUI. */
  sourceImages?: I2ISourceImage[]
  /** Single-image fallback kept for older clients. */
  sourceImage?: string
  sourceName?: string
  resolution?: number | null
  batch?: number | null
  seed?: number | null
  lockSeed?: boolean
  steps?: number | null
  cfg?: number | null
  denoise?: number | null
  sampler?: string | null
  cacheDevice?: string | null
  cacheDtype?: string | null
  tab?: string
}

/** One reference image sent to the backend (data URL + display name). */
export interface I2ISourceImage {
  image: string
  name?: string
}

// -- validation --------------------------------------------------------------

export interface I2INormalizedSource {
  /** Image 1..n label used in chat and settings. */
  label?: string
  name: string
  width: number
  height: number
  /** Small JPEG preview stored with the job for chat cards. */
  thumbnail: string
}

export interface I2INormalized {
  modelId: string
  modelName: string
  prompt: string
  negativePrompt: string
  resolution: number
  /** Target size the composer will ask the reference node to use. */
  width: number
  height: number
  batch: number
  seed: number
  lockSeed: boolean
  seedRandomized: boolean
  steps: number
  cfg: number
  denoise: number
  sampler: string
  scheduler: string
  cacheDevice: string
  cacheDtype: string
  source: I2INormalizedSource
  sources: I2INormalizedSource[]
  recipeId: string
  tab: string
}

export interface I2IValidationGraph {
  recipeId: string
  nodeCount: number
  width: number
  height: number
  batch: number
  /** full = official turbo schedule; img2img = VAEEncode + SamplerCustom. */
  path: I2IWorkflowPath
  scheduler: string
}

export interface I2IValidationResult {
  valid: true
  normalized: I2INormalized
  warnings: I2IWarning[]
  graph: I2IValidationGraph
}

// -- jobs --------------------------------------------------------------------

export interface I2IStage {
  id: 'source' | 'upload' | 'compose' | 'submit' | 'generate' | 'collect' | string
  label: string
  status: I2IStageStatus
  detail?: string
  startedAt?: number
  finishedAt?: number
  durationMs?: number
}

export interface I2IJobSource {
  /** Image 1..n label when stored with the job. */
  label?: string
  /** Uploaded name inside ComfyUI's input folder, when known. */
  name: string
  originalName: string
  width: number
  height: number
  /** Small JPEG preview. Present on new jobs; may be empty on old ones. */
  thumbnail: string
}

export interface I2IJobParams {
  // Generic AdvancedParams-compatible fields used by the shared job UI.
  recipe: string
  seed: number
  lockSeed: boolean
  steps: number
  /** Steps actually applied after the denoise trim. */
  effectiveSteps?: number
  cfg: number
  sampler: string
  scheduler: string
  denoise: number
  // Module metadata.
  recipeId: string
  modelId: string
  modelName: string
  /** Kept for shared job UI; this module has no ratio control. */
  width: number
  height: number
  resolution: number
  batch: number
  seedRandomized: boolean
  cacheDevice: string
  cacheDtype: string
  promptUsed: string
  negativePrompt: string
  source: I2IJobSource
  sources: I2IJobSource[]
  referenceCount: number
  engine: 'comfyui'
  enginePromptId: string | null
  workflow: string
  nodeCount: number | null
  /** Back-compat aliases for the shared settings list. */
  workflowNodeCount?: number | null
  path: I2IWorkflowPath | string
  warnings: I2IWarning[]
}

export interface I2IJobRecord {
  id: string
  createdAt: number
  updatedAt?: number
  status: I2IJobStatus
  progress: number
  tab: string
  /** Added by the generic job service; i2i_main for this module. */
  module?: string
  modelId: string
  modelName: string
  recipe: string
  prompt: string
  seed: number
  params: I2IJobParams
  stages: I2IStage[]
  resultIds: string[]
  error?: string
}

export interface I2IJobDeleteResult {
  id: string
  deleted: boolean
  /** Asset ids that were moved to data/trash. */
  assetsTrashed: string[]
  /** Result ids that were already missing (for example, deleted from the Library). */
  assetsMissing: string[]
}

export interface I2IClearHistoryResult {
  /** Number of jobs soft-deleted from this module's chat. */
  deleted: number
  jobIds: string[]
  assetsTrashed: string[]
  assetsMissing: string[]
}

export interface I2IPackInfo {
  ok: boolean
  version: number
  pack: { id: string; label: string }
  recipe: I2IRecipe
  models: Array<{
    id: string
    label: string
    base: string
    packId: string
    composer: string
    workflow: string
    loader: string
    verified: boolean
    tested: boolean
  }>
  samplers: I2ISamplerOption[]
  resolutions: I2IResolutionOption[]
  workflow: I2IWorkflowInfo
}

export interface I2IApiErrorDetail {
  code?: string
  message?: string
  errors?: I2IValidationIssue[]
  warnings?: I2IWarning[]
}

/** Shared first-open setup contract; the same types drive other GenModules. */
export type {
  ModuleSetupGroup,
  ModuleSetupItem,
  ModuleSetupMissingGroup,
  ModuleSetupPack,
  ModuleSetupPayload,
} from '@/types'
