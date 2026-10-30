/**
 * T2I_main - frontend/API contract for the strict Text -> Image module.
 *
 * These types mirror the JSON boundary exactly (camelCase on the wire).
 * The backend remains the authority for ranges; these values are for rendering
 * controls and showing sensible warnings, not for replacing server checks.
 *
 * Copy this file to frontend/src/features/text-to-image/ when the visual GUI
 * is implemented, or import it from a shared generated-contract step later.
 */

export type T2IProvider = 'ollama' | 'comfyui'
export type T2IJobStatus = 'queued' | 'running' | 'done' | 'error'
export type T2IStageStatus = 'pending' | 'running' | 'done' | 'skipped' | 'error'
export type T2IUpscalerKind = 'none' | 'latent' | 'esrgan'

/** One numeric control contract from the tracked pack. */
export interface T2IRange {
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

export interface T2IValidationIssue {
  code: string
  message: string
  field?: string
  min?: number
  max?: number
  recommendedMin?: number
  recommendedMax?: number
  modelId?: string
  loraId?: string
}

/** Warnings have the same shape as validation issues. */
export type T2IWarning = T2IValidationIssue

export interface T2IModelDefaults {
  steps: number
  cfg: number
  sampler: string
  scheduler: string
  denoise: number
}

export interface T2IModelRanges {
  steps: T2IRange
  cfg: T2IRange
  denoise: T2IRange
  width: T2IRange
  height: T2IRange
  batch: T2IRange
  seed: T2IRange
  refine: {
    steps: T2IRange
    cfg: T2IRange
    denoise: T2IRange
    scale: T2IRange
  }
}

export interface T2IComponentState {
  role: string
  name: string
  declaredName: string
  target: string
  /** true/false when the user catalog knows; null when presence is unknown. */
  present: boolean | null
  catalogId: string
}

export interface T2IModel {
  id: string
  catalogId: string
  label: string
  shortLabel: string
  family: string
  base: string
  /** Pack that owns this model and its graph/defaults. */
  packId: string
  packLabel: string
  description: string
  loader: 'UNETLoader' | 'UnetLoaderGGUF'
  file: string
  declaredFile: string
  target: string
  aliases: string[]
  fallbackAliases: string[]
  baseGroup: string
  baseGroupLabel: string
  required: boolean
  nsfw: boolean
  downloadUrl: string
  pageUrl: string
  size: number | null
  sha256: string
  weightDtype?: string | null
  textEncoder: string
  declaredTextEncoder: string
  textEncoderAliases: string[]
  textEncoderTarget: string
  clipType: string
  vae: string
  declaredVae: string
  vaeAliases: string[]
  vaeTarget: string
  vram: string
  capabilities: string[]
  verified: boolean
  tested: boolean
  notes: string
  defaults: T2IModelDefaults
  ranges: T2IModelRanges
  /** Main diffusion file presence. */
  present: boolean | null
  /** False when any required component is known to be missing. */
  ready: boolean
  missing: string[]
  baseGroupSatisfied?: boolean | null
  components: T2IComponentState[]
  catalogIdFound: string
  compatibleLoras: string[]
  samplers: T2ISamplerOption[]
  schedulers: T2ISamplerOption[]
}

export interface T2ILora {
  id: string
  label: string
  file: string
  declaredFile: string
  aliases: string[]
  nsfw: boolean
  base: string
  compatibleBases: string[]
  family: string
  type: string
  /** false for LoRAs that are deliberately excluded from strict T2I. */
  t2i: boolean
  excludeReason: string
  verified: boolean
  tested: boolean
  defaultOrder: number
  triggers: string[]
  strength: T2IRange
  notes: string
  /** null means the user catalog has not been built yet. */
  present: boolean | null
  compatibleModels: string[]
  available: boolean
  catalogId: string
  catalogLabel: string
}

export interface T2IUpscaler {
  id: string
  label: string
  shortLabel: string
  kind: T2IUpscalerKind
  file: string | null
  declaredFile?: string | null
  aliases?: string[]
  target: string | null
  scaleFactor: number
  enabledByDefault: boolean
  defaultValue: number | null
  /** For ESRGAN this is the target long-side range; latent uses model.refine.scale. */
  valueRange: T2IRange | null
  t2i: boolean
  verified: boolean
  tested: boolean
  notes: string
  present: boolean | null
  missing: string[]
  components: T2IComponentState[]
}

export interface T2ITextModel {
  id: string
  label: string
  provider: T2IProvider
  file?: string
  target?: string
  clipType?: string
  node?: string
  maxLength?: number
  verified: boolean
  tested: boolean
  vram?: string
  notes: string
  /** Ollama models are discovered live and carry their actual tag here. */
  model?: string
  present: boolean | null
  catalogId?: string
  sizeGb?: number
  preferred?: boolean
}

export interface T2IRatio {
  id: string
  label: string
  w: number
  h: number
  /** w / h convenience value for previews. */
  value: number
}

export interface T2ISamplerOption {
  id: string
  label: string
}

export interface T2ISizeOptions {
  label: string
  longSideDefault: number
  step: number
  values: number[]
  description: string
}

export interface T2ILimits {
  promptMaxChars: number
  negativePromptMaxChars: number
  maxLoras: number
  jobTimeoutSeconds: number
  pollIntervalSeconds: number
  historyTimeoutSeconds: number
  enhanceTimeoutSeconds: number
  downloadTimeoutSeconds: number
  downloadRetries: number
}

export interface T2IEnhanceDefaults {
  enabled: boolean
  provider: T2IProvider
  model: string
  systemPrompt: string
  fallbackToOriginal: boolean
  modelExplicit?: boolean
}

export interface T2ICatalogDefaults {
  recipeId: string
  modelId: string
  ratio: string
  size: number
  batch: number
  lockSeed: boolean
  negativePrompt: string
  autoTriggers: boolean
  enhanceEnabled: boolean
  upscaler: {
    id: string
    enabled: boolean
    value: number | null
  }
  loraChain: Array<{
    id: string
    label: string
    strength: number
    on: boolean
    triggers: string[]
    present: boolean | null
  }>
  steps: number
  cfg: number
  sampler: string
  scheduler: string
  denoise: number
  refine: {
    steps: number
    cfg: number
    denoise: number
    scale: number
  }
  enhance: T2IEnhanceDefaults
}

export interface T2IEngineProbe {
  connected: boolean
  url?: string
  detail?: string
  installed?: Array<{ name: string; sizeGb?: number }>
  loaded?: unknown[]
}

export interface T2IEngine {
  comfyui: T2IEngineProbe
  ollama: T2IEngineProbe
  ready: boolean
}

export interface T2ICatalogMeta {
  available: boolean
  updatedAt: string | null
  createdAt: string | null
  source: Record<string, unknown>
  error: string | null
}

export interface T2ICatalog {
  ok: boolean
  pack: {
    id: string
    label: string
    description: string
    nsfw: boolean
    order: number
  }
  recipe: T2IRecipe
  workflow: T2IWorkflowInfo
  models: T2IModel[]
  selectedModelId: string | null
  loras: T2ILora[]
  upscalers: T2IUpscaler[]
  textModels: T2ITextModel[]
  ratios: T2IRatio[]
  size: T2ISizeOptions
  samplers: T2ISamplerOption[]
  schedulers: T2ISamplerOption[]
  limits: T2ILimits
  defaults: T2ICatalogDefaults
  engine: T2IEngine
  catalog: T2ICatalogMeta
  warnings: T2IWarning[]
}

export interface T2IRecipe {
  id: string
  label: string
  workflow: string
  engine: string
  description: string
}

export interface T2IWorkflowInfo {
  path: string
  nodeCount: number
  format: 'comfyui-api'
}

// -- request -----------------------------------------------------------------

export interface T2ILoraSelection {
  id: string
  strength?: number | null
  on?: boolean
  order?: number | null
}

export interface T2IRefineSelection {
  steps?: number | null
  cfg?: number | null
  denoise?: number | null
}

export interface T2IUpscalerSelection {
  id?: string | null
  enabled?: boolean | null
  value?: number | null
}

export interface T2IAdvancedOptions {
  steps?: number | null
  cfg?: number | null
  sampler?: string | null
  scheduler?: string | null
  denoise?: number | null
  refine?: T2IRefineSelection | null
  upscaler?: T2IUpscalerSelection | null
}

export interface T2IEnhanceSelection {
  /** Omit to use the pack default; explicit false disables. */
  enabled?: boolean | null
  provider?: T2IProvider | null
  model?: string | null
  systemPrompt?: string | null
  fallbackToOriginal?: boolean
  /** Unload an Ollama text model after the rewrite (default true). */
  unloadAfter?: boolean
}

export interface T2IJobRequest {
  prompt: string
  negativePrompt?: string
  modelId?: string
  recipeId?: string | null
  width?: number | null
  height?: number | null
  ratio?: string | null
  size?: number | null
  batch?: number | null
  seed?: number | null
  lockSeed?: boolean
  loras?: T2ILoraSelection[]
  autoTriggers?: boolean
  enhance?: T2IEnhanceSelection | null
  /** An enhancement the user previewed/approved; skips auto-enhancement. */
  enhancedPrompt?: string | null
  advanced?: T2IAdvancedOptions | null
  tab?: string
}

// -- validation --------------------------------------------------------------

export interface T2INormalized {
  modelId: string
  modelName: string
  width: number
  height: number
  ratio: string
  size: number
  batch: number
  seed: number
  lockSeed: boolean
  seedRandomized: boolean
  steps: number
  cfg: number
  sampler: string
  scheduler: string
  denoise: number
  refine: {
    on: boolean
    steps: number
    cfg: number
    denoise: number
    scale: number | null
  }
  upscaler: {
    id: string
    label: string
    kind: T2IUpscalerKind
    enabled: boolean
    value: number | null
  }
  loras: Array<{
    id: string
    label: string
    strength: number
    triggers: string[]
  }>
  prompt: string
  basePrompt: string
  promptUsed: string
  negativePrompt: string
  triggers: string[]
  autoTriggers: boolean
  enhance: T2IResolvedEnhance
  recipeId: string
}

export interface T2IValidationGraph {
  recipeId: string
  nodeCount: number
  width: number
  height: number
  finalWidth: number
  finalHeight: number
  refine: {
    enabled: boolean
    steps: number
    cfg: number
    denoise: number
    seed: number
    width: number | null
    height: number | null
  }
  upscaler: {
    id: string
    kind: T2IUpscalerKind
    enabled: boolean
    value: number | null
    outputWidth: number
    outputHeight: number
  }
  loras: Array<{ id: string; label: string; strength: number }>
}

export interface T2IValidationResult {
  valid: true
  normalized: T2INormalized
  warnings: T2IWarning[]
  graph: T2IValidationGraph
}

// -- enhancement -------------------------------------------------------------

export interface T2IEnhanceRequest {
  prompt: string
  provider?: T2IProvider | null
  model?: string | null
  systemPrompt?: string | null
  maxLength?: number | null
  temperature?: number | null
  /** Free the Ollama text model once the rewrite is returned. */
  unloadAfter?: boolean
}

export interface T2IEnhanceResponse {
  prompt: string
  originalPrompt: string
  provider: T2IProvider
  model: string
  durationMs: number
  /** True when the Ollama text model was released after the rewrite. */
  unloaded?: boolean
  /** Best-effort unload failure; the rewrite still succeeded. */
  unloadError?: string | null
}

export interface T2IResolvedEnhance extends T2IEnhanceSelection {
  enabled: boolean
  mode: 'off' | 'pending' | 'approved' | 'applied' | 'fallback'
  provider: T2IProvider
  model: string
  modelExplicit?: boolean
  systemPrompt: string
  fallbackToOriginal: boolean
  unloadAfter: boolean
  error?: string
  unloadError?: string
}

// -- jobs --------------------------------------------------------------------

export interface T2IStage {
  id: 'enhance' | 'compose' | 'submit' | 'generate' | 'collect' | string
  label: string
  status: T2IStageStatus
  detail?: string
  startedAt?: number
  finishedAt?: number
  durationMs?: number
}

export interface T2IJobLoraParam {
  id: string
  label: string
  file: string
  strength: number
  triggers: string[]
}

export interface T2IJobParams {
  // Generic AdvancedParams-compatible fields used by the shared job UI.
  recipe: string
  seed: number
  lockSeed: boolean
  steps: number
  cfg: number
  sampler: string
  scheduler: string
  denoise: number
  refine: {
    on: boolean
    steps: number
    cfg: number
    denoise: number
    scale: number | null
    seed: number | null
    width: number | null
    height: number | null
  }
  // Module metadata.
  recipeId: string
  modelId: string
  modelName: string
  modelShortLabel: string
  modelBase: string
  width: number
  height: number
  ratio: string
  size: number
  batch: number
  seedRandomized: boolean
  loras: T2IJobLoraParam[]
  triggers: string[]
  autoTriggers: boolean
  basePrompt: string
  promptUsed: string
  negativePrompt: string
  enhance: T2IResolvedEnhance
  upscaler: {
    id: string
    label: string
    kind: T2IUpscalerKind
    enabled: boolean
    value: number | null
    outputWidth: number | null
    outputHeight: number | null
  }
  upscalerId: string
  finalWidth: number | null
  finalHeight: number | null
  engine: 'comfyui'
  enginePromptId: string | null
  workflowNodeCount: number | null
  warnings: T2IWarning[]
}

export interface T2IJobRecord {
  id: string
  createdAt: number
  updatedAt?: number
  status: T2IJobStatus
  progress: number
  tab: string
  /** Added by the generic job service; T2I_main for this module. */
  module?: string
  modelId: string
  modelName: string
  recipe: string
  prompt: string
  enhancedPrompt?: string | null
  seed: number
  params: T2IJobParams
  stages: T2IStage[]
  resultIds: string[]
  error?: string
}

export interface T2IJobDeleteResult {
  id: string
  deleted: boolean
  /** Asset ids that were moved to data/trash. */
  assetsTrashed: string[]
  /** Result ids that were already missing (for example, deleted from the Library). */
  assetsMissing: string[]
}

export interface T2IClearHistoryResult {
  /** Number of jobs soft-deleted from this module's chat. */
  deleted: number
  jobIds: string[]
  assetsTrashed: string[]
  assetsMissing: string[]
}

export interface T2IPackInfo {
  ok: boolean
  version: number
  recipe: T2IRecipe
  models: Array<{
    id: string
    label: string
    base: string
    loader: string
    verified: boolean
    tested: boolean
  }>
  loras: Array<{
    id: string
    label: string
    t2i: boolean
    base: string
    excludeReason: string
  }>
  upscalers: Array<{ id: string; label: string; kind: T2IUpscalerKind }>
  textModels: Array<{ id: string; label: string; provider: T2IProvider }>
  workflow: T2IWorkflowInfo
}

export interface T2IApiErrorDetail {
  code?: string
  message?: string
  errors?: T2IValidationIssue[]
  warnings?: T2IWarning[]
}

/** Shared first-open setup contract; the same types drive other GenModules. */
export type {
  ModuleSetupGroup,
  ModuleSetupItem,
  ModuleSetupMissingGroup,
  ModuleSetupPack,
  ModuleSetupPayload,
} from '@/types'
