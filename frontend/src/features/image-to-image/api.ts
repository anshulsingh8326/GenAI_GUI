/**
 * i2i_main API client.
 *
 * Same-origin only: `/api/image-to-image/...` is proxied by Vite in dev and
 * served by FastAPI in production. No base URL or CORS configuration is needed.
 *
 * This file is the canonical module contract under
 * backend/app/GenModules/i2i_main/frontend/ and is copied into
 * frontend/src/features/image-to-image/ by the integration step.
 */

import type {
  I2IClearHistoryResult,
  I2IJobDeleteResult,
  I2IJobRecord,
  I2IJobRequest,
  I2IPackInfo,
  I2IValidationIssue,
  I2IValidationResult,
  I2IWarning,
  I2ICatalog,
  I2IApiErrorDetail,
  ModuleSetupPayload,
} from './types'

const BASE = '/api/image-to-image'

export class I2IApiError extends Error {
  readonly status: number
  readonly code: string
  readonly errors: I2IValidationIssue[]
  readonly warnings: I2IWarning[]

  constructor(
    status: number,
    message: string,
    code = 'request_failed',
    errors: I2IValidationIssue[] = [],
    warnings: I2IWarning[] = [],
  ) {
    super(message)
    this.name = 'I2IApiError'
    this.status = status
    this.code = code
    this.errors = errors
    this.warnings = warnings
  }

  /** true when the request never reached the backend (it is not running). */
  get isOffline(): boolean {
    return this.status === 0
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function issuesFromFastApi(detail: unknown): I2IValidationIssue[] {
  if (!Array.isArray(detail)) return []
  return detail.map((item): I2IValidationIssue => {
    const record = isRecord(item) ? item : {}
    const loc = Array.isArray(record.loc) ? record.loc.map(String).filter((part) => part !== 'body') : []
    return {
      code: 'request_validation',
      message: String(record.msg ?? record.message ?? 'Invalid request value.'),
      field: loc.join('.') || undefined,
    }
  })
}

async function parseError(res: Response): Promise<I2IApiError> {
  const payload = await res.json().catch(() => null)
  const detail: unknown = isRecord(payload) ? payload.detail : null

  if (isRecord(detail)) {
    const named = detail as I2IApiErrorDetail
    const errors = Array.isArray(named.errors) ? named.errors : []
    const warnings = Array.isArray(named.warnings) ? named.warnings : []
    return new I2IApiError(
      res.status,
      String(named.message || `Request failed (HTTP ${res.status}).`),
      String(named.code || 'request_failed'),
      errors,
      warnings,
    )
  }

  const errors = issuesFromFastApi(detail)
  if (errors.length) {
    return new I2IApiError(res.status, errors[0].message, 'request_validation', errors)
  }

  if (typeof detail === 'string' && detail.trim()) {
    return new I2IApiError(res.status, detail.trim())
  }

  return new I2IApiError(res.status, `Request failed (HTTP ${res.status}).`)
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    if (err instanceof Error && err.name === 'AbortError') throw err
    throw new I2IApiError(
      0,
      'The backend is not reachable. Start the GenAI backend and try again.',
      'backend_offline',
    )
  }

  if (!res.ok) {
    throw await parseError(res)
  }

  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

function jsonBody(value: unknown): string {
  return JSON.stringify(value)
}

export const i2iApi = {
  /** Full GUI contract for one selected model (defaults to the pack default). */
  getCatalog(modelId?: string | null, signal?: AbortSignal): Promise<I2ICatalog> {
    const query = modelId ? `?modelId=${encodeURIComponent(modelId)}` : ''
    return request<I2ICatalog>(`/catalog${query}`, { signal })
  },

  /** Secret-free pack summary for debug/ops screens. */
  getPack(signal?: AbortSignal): Promise<I2IPackInfo> {
    return request<I2IPackInfo>('/pack', { signal })
  },

  /** Missing required files + download links for the shared setup modal. */
  getSetup(signal?: AbortSignal): Promise<ModuleSetupPayload> {
    return request<ModuleSetupPayload>('/setup', { signal })
  },

  /** Validate without creating a job. */
  validate(body: I2IJobRequest, signal?: AbortSignal): Promise<I2IValidationResult> {
    return request<I2IValidationResult>('/validate', {
      method: 'POST',
      body: jsonBody(body),
      signal,
    })
  },

  /** Create and start a job. The returned record is already persisted. */
  createJob(body: I2IJobRequest, signal?: AbortSignal): Promise<I2IJobRecord> {
    return request<I2IJobRecord>('/jobs', {
      method: 'POST',
      body: jsonBody(body),
      signal,
    })
  },

  listJobs(limit = 80, signal?: AbortSignal): Promise<I2IJobRecord[]> {
    const safeLimit = Math.max(1, Math.min(200, Math.trunc(limit)))
    return request<I2IJobRecord[]>(`/jobs?limit=${safeLimit}`, { signal })
  },

  /** Clear this module's whole chat; optionally trash every result image. */
  clearHistory(deleteAssets = false, signal?: AbortSignal): Promise<I2IClearHistoryResult> {
    return request<I2IClearHistoryResult>(
      `/jobs?deleteAssets=${deleteAssets ? 'true' : 'false'}`,
      { method: 'DELETE', signal },
    )
  },

  getJob(jobId: string, signal?: AbortSignal): Promise<I2IJobRecord> {
    return request<I2IJobRecord>(`/jobs/${encodeURIComponent(jobId)}`, { signal })
  },

  cancelJob(jobId: string, signal?: AbortSignal): Promise<I2IJobRecord> {
    return request<I2IJobRecord>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: 'POST',
      signal,
    })
  },

  /** Hide a terminal job; `deleteAssets` moves its result images to library trash. */
  deleteJob(jobId: string, deleteAssets = true, signal?: AbortSignal): Promise<I2IJobDeleteResult> {
    return request<I2IJobDeleteResult>(
      `/jobs/${encodeURIComponent(jobId)}?deleteAssets=${deleteAssets ? 'true' : 'false'}`,
      { method: 'DELETE', signal },
    )
  },
}

/** Asset URLs used by the results grid. Ids are backend-owned. */
export function assetFileUrl(assetId: string): string {
  return `/api/assets/${encodeURIComponent(assetId)}/file`
}

export function assetThumbUrl(assetId: string): string {
  return `/api/assets/${encodeURIComponent(assetId)}/thumb`
}
