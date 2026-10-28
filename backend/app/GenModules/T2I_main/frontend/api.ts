/**
 * T2I_main API client.
 *
 * Same-origin only: `/api/t2i/...` is proxied by Vite in dev and served by
 * FastAPI in production. No base URL or CORS configuration is needed.
 *
 * This file is the canonical module contract under
 * backend/app/GenModules/T2I_main/frontend/ and is copied into
 * frontend/src/features/text-to-image/ by the integration step.
 */

import type {
  T2IEnhanceRequest,
  T2IEnhanceResponse,
  T2IClearHistoryResult,
  T2IJobRecord,
  T2IJobRequest,
  T2IJobDeleteResult,
  T2IPackInfo,
  T2IValidationIssue,
  T2IValidationResult,
  T2IWarning,
  T2ICatalog,
  T2IApiErrorDetail,
} from './types'

const BASE = '/api/t2i'

export class T2IApiError extends Error {
  readonly status: number
  readonly code: string
  readonly errors: T2IValidationIssue[]
  readonly warnings: T2IWarning[]

  constructor(
    status: number,
    message: string,
    code = 'request_failed',
    errors: T2IValidationIssue[] = [],
    warnings: T2IWarning[] = [],
  ) {
    super(message)
    this.name = 'T2IApiError'
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

function issuesFromFastApi(detail: unknown): T2IValidationIssue[] {
  if (!Array.isArray(detail)) return []
  return detail.map((item): T2IValidationIssue => {
    const record = isRecord(item) ? item : {}
    const loc = Array.isArray(record.loc) ? record.loc.map(String).filter((part) => part !== 'body') : []
    return {
      code: 'request_validation',
      message: String(record.msg ?? record.message ?? 'Invalid request value.'),
      field: loc.join('.') || undefined,
    }
  })
}

async function parseError(res: Response): Promise<T2IApiError> {
  const payload = await res.json().catch(() => null)
  const detail: unknown = isRecord(payload) ? payload.detail : null

  if (isRecord(detail)) {
    const named = detail as T2IApiErrorDetail
    const errors = Array.isArray(named.errors) ? named.errors : []
    const warnings = Array.isArray(named.warnings) ? named.warnings : []
    return new T2IApiError(
      res.status,
      String(named.message || `Request failed (HTTP ${res.status}).`),
      String(named.code || 'request_failed'),
      errors,
      warnings,
    )
  }

  const errors = issuesFromFastApi(detail)
  if (errors.length) {
    return new T2IApiError(
      res.status,
      errors[0].message,
      'request_validation',
      errors,
    )
  }

  if (typeof detail === 'string' && detail.trim()) {
    return new T2IApiError(res.status, detail.trim())
  }

  return new T2IApiError(res.status, `Request failed (HTTP ${res.status}).`)
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
    throw new T2IApiError(
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

export const t2iApi = {
  /** Full GUI contract for one selected model (defaults to the pack default). */
  getCatalog(modelId?: string | null, signal?: AbortSignal): Promise<T2ICatalog> {
    const query = modelId ? `?modelId=${encodeURIComponent(modelId)}` : ''
    return request<T2ICatalog>(`/catalog${query}`, { signal })
  },

  /** Secret-free pack summary for debug/ops screens. */
  getPack(signal?: AbortSignal): Promise<T2IPackInfo> {
    return request<T2IPackInfo>('/pack', { signal })
  },

  /** Validate without creating a job. */
  validate(body: T2IJobRequest, signal?: AbortSignal): Promise<T2IValidationResult> {
    return request<T2IValidationResult>('/validate', {
      method: 'POST',
      body: jsonBody(body),
      signal,
    })
  },

  /** Preview a prompt rewrite. This can take tens of seconds (cold model). */
  enhance(body: T2IEnhanceRequest, signal?: AbortSignal): Promise<T2IEnhanceResponse> {
    return request<T2IEnhanceResponse>('/enhance', {
      method: 'POST',
      body: jsonBody(body),
      signal,
    })
  },

  /** Create and start a job. The returned record is already persisted. */
  createJob(body: T2IJobRequest, signal?: AbortSignal): Promise<T2IJobRecord> {
    return request<T2IJobRecord>('/jobs', {
      method: 'POST',
      body: jsonBody(body),
      signal,
    })
  },

  listJobs(limit = 80, signal?: AbortSignal): Promise<T2IJobRecord[]> {
    const safeLimit = Math.max(1, Math.min(200, Math.trunc(limit)))
    return request<T2IJobRecord[]>(`/jobs?limit=${safeLimit}`, { signal })
  },

  /** Clear this module's whole chat; optionally trash every result image. */
  clearHistory(deleteAssets = false, signal?: AbortSignal): Promise<T2IClearHistoryResult> {
    return request<T2IClearHistoryResult>(
      `/jobs?deleteAssets=${deleteAssets ? 'true' : 'false'}`,
      { method: 'DELETE', signal },
    )
  },

  getJob(jobId: string, signal?: AbortSignal): Promise<T2IJobRecord> {
    // Job ids contain '#': the encoded form is part of the URL contract.
    return request<T2IJobRecord>(`/jobs/${encodeURIComponent(jobId)}`, { signal })
  },

  cancelJob(jobId: string, signal?: AbortSignal): Promise<T2IJobRecord> {
    return request<T2IJobRecord>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: 'POST',
      signal,
    })
  },

  /** Hide a terminal job; `deleteAssets` moves its result images to library trash. */
  deleteJob(jobId: string, deleteAssets = true, signal?: AbortSignal): Promise<T2IJobDeleteResult> {
    return request<T2IJobDeleteResult>(
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
