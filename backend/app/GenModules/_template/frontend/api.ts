/**
 * Template GenModule API client.
 *
 * Same-origin only: `/api/template/...` is proxied by Vite in development and
 * served by FastAPI in production. No base URL or CORS configuration.
 */

import type {
  TemplateApiErrorDetail,
  TemplateCatalog,
  TemplateClearResult,
  TemplateDeleteResult,
  TemplateJobRecord,
  TemplateJobRequest,
  TemplateValidationIssue,
  TemplateValidationResult,
} from './types'

const BASE = '/api/template'

export class TemplateApiError extends Error {
  readonly status: number
  readonly code: string
  readonly errors: TemplateValidationIssue[]
  readonly warnings: TemplateValidationIssue[]

  constructor(
    status: number,
    message: string,
    code = 'request_failed',
    errors: TemplateValidationIssue[] = [],
    warnings: TemplateValidationIssue[] = [],
  ) {
    super(message)
    this.name = 'TemplateApiError'
    this.status = status
    this.code = code
    this.errors = errors
    this.warnings = warnings
  }

  get isOffline(): boolean {
    return this.status === 0
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function issuesFromFastApi(detail: unknown): TemplateValidationIssue[] {
  if (!Array.isArray(detail)) return []
  return detail.map((item): TemplateValidationIssue => {
    const record = isRecord(item) ? item : {}
    const loc = Array.isArray(record.loc)
      ? record.loc.map(String).filter((part) => part !== 'body')
      : []
    return {
      code: 'request_validation',
      message: String(record.msg ?? record.message ?? 'Invalid request value.'),
      field: loc.join('.') || undefined,
    }
  })
}

async function parseError(res: Response): Promise<TemplateApiError> {
  const payload = await res.json().catch(() => null)
  const detail: unknown = isRecord(payload) ? payload.detail : null

  if (isRecord(detail)) {
    const named = detail as TemplateApiErrorDetail
    return new TemplateApiError(
      res.status,
      String(named.message || `Request failed (HTTP ${res.status}).`),
      String(named.code || 'request_failed'),
      Array.isArray(named.errors) ? named.errors : [],
      Array.isArray(named.warnings) ? named.warnings : [],
    )
  }

  const errors = issuesFromFastApi(detail)
  if (errors.length) {
    return new TemplateApiError(res.status, errors[0].message, 'request_validation', errors)
  }

  if (typeof detail === 'string' && detail.trim()) {
    return new TemplateApiError(res.status, detail.trim())
  }

  return new TemplateApiError(res.status, `Request failed (HTTP ${res.status}).`)
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
    throw new TemplateApiError(
      0,
      'The backend is not reachable. Start the GenAI backend and try again.',
      'backend_offline',
    )
  }

  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

function jsonBody(value: unknown): string {
  return JSON.stringify(value)
}

export const templateApi = {
  getCatalog(signal?: AbortSignal): Promise<TemplateCatalog> {
    return request<TemplateCatalog>('/catalog', { signal })
  },

  validate(body: TemplateJobRequest, signal?: AbortSignal): Promise<TemplateValidationResult> {
    return request<TemplateValidationResult>('/validate', {
      method: 'POST',
      body: jsonBody(body),
      signal,
    })
  },

  createJob(body: TemplateJobRequest, signal?: AbortSignal): Promise<TemplateJobRecord> {
    return request<TemplateJobRecord>('/jobs', {
      method: 'POST',
      body: jsonBody(body),
      signal,
    })
  },

  listJobs(limit = 80, signal?: AbortSignal): Promise<TemplateJobRecord[]> {
    const safeLimit = Math.max(1, Math.min(200, Math.trunc(limit)))
    return request<TemplateJobRecord[]>(`/jobs?limit=${safeLimit}`, { signal })
  },

  clearHistory(deleteAssets = false, signal?: AbortSignal): Promise<TemplateClearResult> {
    return request<TemplateClearResult>(
      `/jobs?deleteAssets=${deleteAssets ? 'true' : 'false'}`,
      { method: 'DELETE', signal },
    )
  },

  getJob(jobId: string, signal?: AbortSignal): Promise<TemplateJobRecord> {
    // Job ids contain '#': the encoded form is part of the URL contract.
    return request<TemplateJobRecord>(`/jobs/${encodeURIComponent(jobId)}`, { signal })
  },

  cancelJob(jobId: string, signal?: AbortSignal): Promise<TemplateJobRecord> {
    return request<TemplateJobRecord>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: 'POST',
      signal,
    })
  },

  deleteJob(
    jobId: string,
    deleteAssets = true,
    signal?: AbortSignal,
  ): Promise<TemplateDeleteResult> {
    return request<TemplateDeleteResult>(
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
