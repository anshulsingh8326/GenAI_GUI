/**
 * Template GenModule - wire types.
 *
 * The JSON boundary is camelCase and mirrors the backend schema exactly.
 * Replace these with your module's real catalog and job params; keep the
 * `TemplateJobRecord` shape so the shared card/polling code keeps working.
 */

export type TemplateAccent = 'lavender' | 'mint' | 'peach' | 'sky'
export type TemplateJobStatus = 'queued' | 'running' | 'done' | 'error'
export type TemplateStageStatus = 'pending' | 'running' | 'done' | 'skipped' | 'error'

export interface TemplateAccentOption {
  id: TemplateAccent
  label: string
}

export interface TemplateDefaults {
  prompt: string
  accent: TemplateAccent
  width: number
  height: number
  batch: number
  lockSeed: boolean
}

export interface TemplateLimits {
  promptMaxChars: number
  minBatch: number
  maxBatch: number
  batchStep: number
  minSize: number
  maxSize: number
  sizeStep: number
  sizeValues: number[]
  pollIntervalSeconds: number
}

export interface TemplateCatalog {
  ok: boolean
  moduleId: string
  defaults: TemplateDefaults
  limits: TemplateLimits
  accents: TemplateAccentOption[]
}

export interface TemplateValidationIssue {
  code: string
  message: string
  field?: string
  [key: string]: unknown
}

export interface TemplateJobRequest {
  prompt: string
  accent?: TemplateAccent | null
  width?: number | null
  height?: number | null
  batch?: number | null
  seed?: number | null
  lockSeed?: boolean
  tab?: string
}

export interface TemplateStage {
  id: string
  label: string
  status: TemplateStageStatus
  detail?: string
  startedAt?: number
  finishedAt?: number
  durationMs?: number
}

export interface TemplateJobParams {
  accent: TemplateAccent
  width: number
  height: number
  batch: number
  seed: number
  lockSeed: boolean
  modelId?: string
  modelName?: string
  recipeId?: string
}

export interface TemplateJobRecord {
  id: string
  createdAt: number
  updatedAt?: number
  status: TemplateJobStatus
  progress: number
  tab: string
  module: string
  modelId: string
  modelName: string
  recipe: string
  prompt: string
  seed: number
  params: TemplateJobParams
  stages: TemplateStage[]
  resultIds: string[]
  error?: string | null
}

export interface TemplateValidationResult {
  valid: true
  normalized: {
    prompt: string
    accent: TemplateAccent
    width: number
    height: number
    batch: number
    seed: number
    lockSeed: boolean
  }
  warnings: TemplateValidationIssue[]
}

export interface TemplateDeleteResult {
  id: string
  deleted: boolean
  assetsTrashed: string[]
  assetsMissing: string[]
}

export interface TemplateClearResult {
  deleted: number
  jobIds: string[]
  assetsTrashed: string[]
  assetsMissing: string[]
}

export interface TemplateApiErrorDetail {
  code?: string
  message?: string
  errors?: TemplateValidationIssue[]
  warnings?: TemplateValidationIssue[]
}
