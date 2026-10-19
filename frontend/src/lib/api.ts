// Real backend API client - everything the backend owns: settings, folders,
// connectors/resources, library assets and job records.
//
// URLs are relative (`/api/...`): vite proxies them to http://127.0.0.1:8766 in
// dev (see vite.config.ts) and in prod the FastAPI app serves the built SPA, so
// the frontend is always same-origin - no CORS, no base URL configuration.

import type {
  Asset,
  ComfyInspect,
  ComfyRequirements,
  ConnTestResult,
  EngineActionResult,
  EngineLaunchResult,
  FolderValidation,
  JobRecord,
  MockCompleteResult,
  NewJobDraft,
  PathPickResult,
  SettingsEnvelope,
  SettingsValues,
  StatusSnapshot,
  SystemInfo,
} from '@/types'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }

  /** true when the request never reached the backend (it is not running). */
  get isOffline(): boolean {
    return this.status === 0
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  // FormData uploads must keep the browser-set multipart boundary.
  const isForm = typeof FormData !== 'undefined' && init.body instanceof FormData
  let res: Response
  try {
    res = await fetch(path, {
      ...init,
      headers: isForm ? init.headers : { 'Content-Type': 'application/json', ...init.headers },
    })
  } catch {
    throw new ApiError(0, 'Backend unreachable - is the backend running on port 8766?')
  }

  if (!res.ok) {
    let message = `HTTP ${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') message = body.detail
      else if (body?.detail) message = JSON.stringify(body.detail)
    } catch {
      /* keep the default message */
    }
    throw new ApiError(res.status, message)
  }

  return (await res.json()) as T
}

export const api = {
  // system
  getHealth: () => request<{ ok: boolean; app: string; version: string }>('/api/health'),
  getSystemInfo: () => request<SystemInfo>('/api/system/info'),

  // settings
  getSettings: () => request<SettingsEnvelope>('/api/settings'),
  getSettingsDefaults: () => request<SettingsValues>('/api/settings/defaults'),
  putSettings: (values: Partial<SettingsValues>) =>
    request<SettingsValues>('/api/settings', { method: 'PUT', body: JSON.stringify(values) }),
  resetSettings: () => request<SettingsValues>('/api/settings/reset', { method: 'POST' }),

  // folders
  validateFolder: (path: string, create = false) =>
    request<FolderValidation>('/api/folders/validate', {
      method: 'POST',
      body: JSON.stringify({ path, create }),
    }),
  // OS-native dialog on the backend machine (browsers can't hand out real paths)
  pickPath: (opts: { mode: 'file' | 'folder'; title?: string; start?: string; extensions?: string[] }) =>
    request<PathPickResult>('/api/folders/pick', {
      method: 'POST',
      body: JSON.stringify({
        mode: opts.mode,
        title: opts.title ?? 'Select',
        start: opts.start ?? '',
        extensions: opts.extensions ?? [],
      }),
    }),

  // connectors + resources
  getStatus: () => request<StatusSnapshot>('/api/status'),
  testConnection: (kind: 'comfyui' | 'ollama') =>
    request<ConnTestResult>(`/api/connectors/${kind}/test`, { method: 'POST' }),
  freeComfyui: () => request<EngineActionResult>('/api/engine/comfyui/free', { method: 'POST' }),
  launchComfyui: () => request<EngineLaunchResult>('/api/engine/comfyui/launch', { method: 'POST' }),
  unloadOllama: (model?: string) =>
    request<EngineActionResult>('/api/engine/ollama/unload', {
      method: 'POST',
      body: JSON.stringify({ model: model ?? null }),
    }),

  // comfyui content (read-only in Phase A - see docs/COMFYUI_CONTENT.md)
  inspectComfy: (path?: string) =>
    request<ComfyInspect>(`/api/comfyui/inspect${path ? `?path=${encodeURIComponent(path)}` : ''}`),
  getComfyRequirements: () => request<ComfyRequirements>('/api/comfyui/requirements'),

  // library (assets)
  getAssets: (opts: { favorites?: boolean; q?: string; limit?: number } = {}) => {
    const params = new URLSearchParams()
    if (opts.favorites) params.set('favorites', 'true')
    if (opts.q) params.set('q', opts.q)
    if (opts.limit) params.set('limit', String(opts.limit))
    const qs = params.toString()
    return request<Asset[]>(`/api/assets${qs ? `?${qs}` : ''}`)
  },
  importAsset: (file: File, label?: string, tags?: string[]) => {
    const form = new FormData()
    form.append('file', file)
    if (label) form.append('label', label)
    if (tags?.length) form.append('tags', tags.join(','))
    return request<Asset>('/api/assets/import', { method: 'POST', body: form })
  },
  updateAsset: (
    id: string,
    patch: { favorite?: boolean; label?: string; tags?: string[]; nsfw?: boolean },
  ) =>
    request<Asset>(`/api/assets/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),
  trashAsset: (id: string) =>
    request<{ id: string; movedTo: string | null }>(`/api/assets/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }),

  // jobs
  getJobs: (limit = 80) => request<JobRecord[]>(`/api/jobs?limit=${limit}`),
  createJob: (draft: NewJobDraft) =>
    request<JobRecord>('/api/jobs', { method: 'POST', body: JSON.stringify(draft) }),
  updateJob: (id: string, patch: Partial<JobRecord>) =>
    request<JobRecord>(`/api/jobs/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),
  completeMockJob: (id: string, opts: { count: number; width: number; height: number }) =>
    request<MockCompleteResult>(`/api/jobs/${encodeURIComponent(id)}/mock-complete`, {
      method: 'POST',
      body: JSON.stringify(opts),
    }),
}
