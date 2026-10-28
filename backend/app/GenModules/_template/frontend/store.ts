/**
 * Template GenModule store.
 *
 * The page owns transient UI (drawer, viewer, popovers). Durable state lives
 * here: form, persistence, catalog reconciliation, jobs, polling, delete/clear.
 *
 * Adapt the form fields to your module. Keep the lifecycle methods and the
 * shared library/jobs synchronization - they are the portable part.
 */

import { computed, reactive, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { useJobsStore } from '@/stores/jobs'
import { useLibraryStore } from '@/stores/library'
import { useUiStore } from '@/stores/ui'
import { TemplateApiError, templateApi } from './api'
import type {
  TemplateAccent,
  TemplateCatalog,
  TemplateClearResult,
  TemplateDeleteResult,
  TemplateJobRecord,
  TemplateJobRequest,
  TemplateValidationIssue,
} from './types'

const STORAGE_KEY = 'genai.template.form.v1'
const STORAGE_VERSION = 1
const JOB_PAGE_SIZE = 60

export interface TemplateFormState {
  prompt: string
  accent: TemplateAccent
  width: number
  height: number
  batch: number
  seed: number
  lockSeed: boolean
}

export type TemplatePanel = 'output' | 'all'

interface PersistedForm {
  version: number
  savedAt: number
  form: Partial<TemplateFormState>
}

function randomSeed(): number {
  return Math.floor(Math.random() * 0x1_0000_0000)
}

export function defaultForm(): TemplateFormState {
  return {
    prompt: '',
    accent: 'lavender',
    width: 1024,
    height: 1024,
    batch: 1,
    seed: randomSeed(),
    lockSeed: false,
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function readPersisted(): PersistedForm | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (!isRecord(parsed) || !isRecord(parsed.form)) return null
    const version = Number(parsed.version)
    if (!Number.isFinite(version) || version !== STORAGE_VERSION) return null
    return {
      version,
      savedAt: Number(parsed.savedAt) || 0,
      form: parsed.form as Partial<TemplateFormState>,
    }
  } catch {
    return null
  }
}

function mergePersisted(target: TemplateFormState, saved: Partial<TemplateFormState>): boolean {
  let changed = false
  if (typeof saved.prompt === 'string') {
    target.prompt = saved.prompt
    changed = true
  }
  if (typeof saved.accent === 'string') {
    target.accent = saved.accent as TemplateAccent
    changed = true
  }
  for (const key of ['width', 'height', 'batch', 'seed'] as const) {
    const value = saved[key]
    if (typeof value === 'number' && Number.isFinite(value)) {
      target[key] = value
      changed = true
    }
  }
  if (typeof saved.lockSeed === 'boolean') {
    target.lockSeed = saved.lockSeed
    changed = true
  }
  return changed
}

function errorText(err: unknown): string {
  if (err instanceof TemplateApiError) {
    if (err.isOffline) return err.message
    return err.message || `Request failed (HTTP ${err.status}).`
  }
  if (err instanceof Error && err.message) return err.message
  return 'Something went wrong.'
}

function clampSize(value: number, min: number, max: number, step: number): number {
  const safeStep = Number.isFinite(step) && step > 0 ? step : 1
  const rounded = Math.round(value / safeStep) * safeStep
  return Math.max(min, Math.min(max, rounded))
}

export const useTemplateStore = defineStore('template', () => {
  const ui = useUiStore()
  const library = useLibraryStore()
  const genericJobs = useJobsStore()

  const persisted = readPersisted()
  const initial = defaultForm()
  const restored = persisted ? mergePersisted(initial, persisted.form) : false
  const form = reactive<TemplateFormState>(initial)

  const catalog = ref<TemplateCatalog | null>(null)
  const loading = ref(true)
  const loadError = ref('')
  const actionError = ref('')
  const jobsError = ref('')
  const jobSyncError = ref('')
  const warnings = ref<TemplateValidationIssue[]>([])
  const submitting = ref(false)
  const jobsLoading = ref(false)
  const jobs = ref<TemplateJobRecord[]>([])
  const lastSavedAt = ref<number | null>(restored ? (persisted?.savedAt ?? Date.now()) : null)
  const storageError = ref('')

  let catalogInitialized = false
  let catalogAbort: AbortController | null = null
  let saveTimer: number | undefined
  const pollTimers = new Map<string, number>()
  const pollFailures = new Map<string, number>()
  const terminalSynced = new Set<string>()

  const accentOptions = computed(() => catalog.value?.accents ?? [])
  const promptLimit = computed(() => catalog.value?.limits.promptMaxChars ?? 2000)
  const pollInterval = computed(
    () => Math.max(350, (catalog.value?.limits.pollIntervalSeconds ?? 1) * 1000),
  )
  const sizeOptions = computed(() => {
    const limits = catalog.value?.limits
    const min = limits?.minSize ?? 256
    const max = limits?.maxSize ?? 2048
    const presets = limits?.sizeValues?.length
      ? limits.sizeValues
      : [256, 512, 768, 1024, 1280, 1536, 2048]
    const values = new Set(presets)
    // Keep a restored/custom value selectable even if it is not a preset.
    if (Number.isFinite(form.width)) values.add(form.width)
    if (Number.isFinite(form.height)) values.add(form.height)
    return [...values]
      .filter((value) => Number.isFinite(value) && value >= min && value <= max)
      .sort((a, b) => a - b)
      .map((value) => ({ value: String(value), label: `${value} px` }))
  })
  const busy = computed(() =>
    jobs.value.some((job) => job.status === 'queued' || job.status === 'running'),
  )
  const canGenerate = computed(
    () =>
      catalog.value != null &&
      form.prompt.trim().length > 0 &&
      !busy.value &&
      !submitting.value,
  )
  const selectedAccent = computed(
    () => accentOptions.value.find((item) => item.id === form.accent)?.label ?? form.accent,
  )

  // -- persistence ----------------------------------------------------------

  function persistNow(): void {
    if (typeof window === 'undefined') return
    if (saveTimer !== undefined) {
      window.clearTimeout(saveTimer)
      saveTimer = undefined
    }
    try {
      const encoded = JSON.stringify(form)
      const previous = window.localStorage.getItem(STORAGE_KEY)
      if (previous) {
        try {
          const parsed = JSON.parse(previous) as PersistedForm
          if (parsed.version === STORAGE_VERSION && JSON.stringify(parsed.form) === encoded) {
            return
          }
        } catch {
          // Corrupt payload: overwrite it below.
        }
      }
      const payload: PersistedForm = {
        version: STORAGE_VERSION,
        savedAt: Date.now(),
        form: JSON.parse(encoded) as TemplateFormState,
      }
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
      lastSavedAt.value = payload.savedAt
      storageError.value = ''
    } catch (err) {
      storageError.value = `Autosave failed: ${errorText(err)}`
    }
  }

  function schedulePersist(): void {
    if (typeof window === 'undefined') return
    if (saveTimer !== undefined) window.clearTimeout(saveTimer)
    saveTimer = window.setTimeout(persistNow, 180)
  }

  function handleStorage(event: StorageEvent): void {
    if (event.key !== STORAGE_KEY || !event.newValue) return
    try {
      const parsed = JSON.parse(event.newValue) as PersistedForm
      if (parsed.version !== STORAGE_VERSION || !isRecord(parsed.form)) return
      if (!mergePersisted(form, parsed.form)) return
      reconcile()
      lastSavedAt.value = Number(parsed.savedAt) || Date.now()
    } catch {
      // Ignore malformed cross-tab payloads.
    }
  }

  watch(form, schedulePersist, { deep: true })
  if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', persistNow)
    window.addEventListener('storage', handleStorage)
  }

  // -- catalog --------------------------------------------------------------

  function applyDefaults(next: TemplateCatalog): void {
    form.accent = next.defaults.accent
    form.width = next.defaults.width
    form.height = next.defaults.height
    form.batch = next.defaults.batch
    form.lockSeed = next.defaults.lockSeed
    if (!form.prompt) form.prompt = next.defaults.prompt
  }

  function reconcile(): boolean {
    const next = catalog.value
    if (!next) return false
    let changed = false
    if (!next.accents.some((item) => item.id === form.accent)) {
      form.accent = next.defaults.accent
      changed = true
    }
    const width = clampSize(
      form.width,
      next.limits.minSize,
      next.limits.maxSize,
      next.limits.sizeStep,
    )
    if (width !== form.width) {
      form.width = width
      changed = true
    }
    const height = clampSize(
      form.height,
      next.limits.minSize,
      next.limits.maxSize,
      next.limits.sizeStep,
    )
    if (height !== form.height) {
      form.height = height
      changed = true
    }
    const batch = Math.max(
      next.limits.minBatch,
      Math.min(next.limits.maxBatch, Math.round(form.batch)),
    )
    if (batch !== form.batch) {
      form.batch = batch
      changed = true
    }
    if (!Number.isFinite(form.seed)) {
      form.seed = randomSeed()
      changed = true
    }
    return changed
  }

  async function loadCatalog(): Promise<void> {
    catalogAbort?.abort()
    catalogAbort = new AbortController()
    loading.value = true
    loadError.value = ''
    try {
      const next = await templateApi.getCatalog(catalogAbort.signal)
      catalog.value = next
      if (!catalogInitialized) {
        catalogInitialized = true
        if (restored) {
          if (reconcile()) {
            ui.toast('Some restored Template settings were adjusted to the current limits.', 'warn', 5000)
          }
        } else {
          applyDefaults(next)
        }
      } else {
        reconcile()
      }
      loading.value = false
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      if (err instanceof Error && err.name === 'AbortError') return
      loading.value = false
      loadError.value = errorText(err)
    }
  }

  // -- jobs -----------------------------------------------------------------

  function replaceJob(job: TemplateJobRecord): void {
    const index = jobs.value.findIndex((item) => item.id === job.id)
    if (index >= 0) jobs.value[index] = job
    else jobs.value.push(job)
  }

  function stopPolling(jobId: string): void {
    const timer = pollTimers.get(jobId)
    if (timer !== undefined) {
      window.clearTimeout(timer)
      pollTimers.delete(jobId)
    }
  }

  function isTerminal(job: TemplateJobRecord): boolean {
    return job.status === 'done' || job.status === 'error'
  }

  function syncAfterTerminal(job: TemplateJobRecord): void {
    if (!isTerminal(job) || terminalSynced.has(job.id)) return
    terminalSynced.add(job.id)
    void Promise.allSettled([library.syncFromBackend(), genericJobs.syncFromBackend()])
  }

  function schedulePoll(jobId: string, delay = pollInterval.value): void {
    stopPolling(jobId)
    pollTimers.set(
      jobId,
      window.setTimeout(() => {
        pollTimers.delete(jobId)
        void pollJob(jobId)
      }, delay),
    )
  }

  async function pollJob(jobId: string): Promise<void> {
    try {
      const job = await templateApi.getJob(jobId)
      const index = jobs.value.findIndex((item) => item.id === job.id)
      if (index < 0) {
        stopPolling(jobId)
        return
      }
      jobs.value[index] = job
      jobSyncError.value = ''
      pollFailures.delete(jobId)
      if (isTerminal(job)) {
        stopPolling(jobId)
        syncAfterTerminal(job)
      } else {
        schedulePoll(jobId)
      }
    } catch (err) {
      if (err instanceof TemplateApiError && err.status === 404) {
        jobs.value = jobs.value.filter((item) => item.id !== jobId)
        stopPolling(jobId)
        terminalSynced.delete(jobId)
        void Promise.allSettled([library.syncFromBackend(), genericJobs.syncFromBackend()])
        return
      }
      const failures = (pollFailures.get(jobId) ?? 0) + 1
      pollFailures.set(jobId, failures)
      if (failures >= 3) {
        jobSyncError.value = `Could not refresh job ${jobId}; retrying. ${errorText(err)}`
      }
      schedulePoll(jobId, Math.min(8000, pollInterval.value * 2 ** failures))
    }
  }

  function reattach(job: TemplateJobRecord): void {
    if (!isTerminal(job)) schedulePoll(job.id, 500)
    else syncAfterTerminal(job)
  }

  async function loadJobs(): Promise<void> {
    jobsLoading.value = true
    jobsError.value = ''
    try {
      const remote = await templateApi.listJobs(JOB_PAGE_SIZE)
      jobs.value = [...remote].reverse()
      for (const job of jobs.value) reattach(job)
      void genericJobs.syncFromBackend()
    } catch (err) {
      jobsError.value = errorText(err)
    } finally {
      jobsLoading.value = false
    }
  }

  function buildRequest(): TemplateJobRequest {
    return {
      prompt: form.prompt.trim(),
      accent: form.accent,
      width: form.width,
      height: form.height,
      batch: form.batch,
      seed: form.lockSeed ? form.seed : null,
      lockSeed: form.lockSeed,
      tab: 'template',
    }
  }

  async function generate(): Promise<void> {
    if (!canGenerate.value) return
    submitting.value = true
    actionError.value = ''
    warnings.value = []
    try {
      // Validate and create from one snapshot. Reuse the normalized seed so the
      // card and the form report the seed the backend actually rendered.
      const request = buildRequest()
      const preflight = await templateApi.validate(request)
      warnings.value = preflight.warnings ?? []
      form.seed = preflight.normalized.seed
      const job = await templateApi.createJob({
        ...request,
        ...preflight.normalized,
        lockSeed: request.lockSeed,
      })
      jobs.value.push(job)
      terminalSynced.delete(job.id)
      schedulePoll(job.id, 350)
      void genericJobs.syncFromBackend()
    } catch (err) {
      actionError.value = errorText(err)
      if (err instanceof TemplateApiError) warnings.value = err.warnings
    } finally {
      submitting.value = false
    }
  }

  async function cancelJob(jobId: string): Promise<void> {
    actionError.value = ''
    try {
      const job = await templateApi.cancelJob(jobId)
      replaceJob(job)
      if (!isTerminal(job)) schedulePoll(jobId, 250)
      else syncAfterTerminal(job)
    } catch (err) {
      actionError.value = errorText(err)
    }
  }

  async function deleteJob(jobId: string, deleteAssets = true): Promise<TemplateDeleteResult | null> {
    actionError.value = ''
    try {
      const result = await templateApi.deleteJob(jobId, deleteAssets)
      jobs.value = jobs.value.filter((job) => job.id !== jobId)
      stopPolling(jobId)
      pollFailures.delete(jobId)
      terminalSynced.delete(jobId)
      void Promise.allSettled([library.syncFromBackend(), genericJobs.syncFromBackend()])
      return result
    } catch (err) {
      actionError.value = errorText(err)
      return null
    }
  }

  async function clearHistory(deleteAssets = false): Promise<TemplateClearResult | null> {
    actionError.value = ''
    try {
      const result = await templateApi.clearHistory(deleteAssets)
      const removed = new Set(result.jobIds)
      jobs.value = jobs.value.filter((job) => !removed.has(job.id))
      for (const jobId of result.jobIds) {
        stopPolling(jobId)
        pollFailures.delete(jobId)
        terminalSynced.delete(jobId)
      }
      // Sync even on keep-media clears so missing result assets disappear.
      void Promise.allSettled([library.syncFromBackend(), genericJobs.syncFromBackend()])
      return result
    } catch (err) {
      actionError.value = errorText(err)
      return null
    }
  }

  // -- form actions ---------------------------------------------------------

  function applyJobSettings(job: TemplateJobRecord): void {
    const params = job.params
    if (params?.accent) form.accent = params.accent
    if (Number.isFinite(params?.width)) form.width = params.width
    if (Number.isFinite(params?.height)) form.height = params.height
    if (Number.isFinite(params?.batch)) form.batch = params.batch
    if (Number.isFinite(params?.seed)) form.seed = params.seed
    form.lockSeed = true
    form.prompt = job.prompt
    persistNow()
    ui.toast('Settings and prompt restored from this job.', 'success')
  }

  function useJobSeed(job: TemplateJobRecord): void {
    form.seed = Number(job.params?.seed ?? job.seed ?? form.seed)
    form.lockSeed = true
    persistNow()
    ui.toast(`Seed ${form.seed} locked.`, 'success')
  }

  function resetPanel(panel: TemplatePanel): void {
    const next = catalog.value
    if (!next) return
    if (panel === 'output') {
      form.accent = next.defaults.accent
      form.width = next.defaults.width
      form.height = next.defaults.height
      form.batch = next.defaults.batch
      form.seed = randomSeed()
      form.lockSeed = next.defaults.lockSeed
      ui.toast('Output settings reset.', 'success')
    } else {
      applyDefaults(next)
      form.prompt = ''
      form.seed = randomSeed()
      ui.toast('Every Template setting reset.', 'success')
    }
    persistNow()
  }

  function flushPersist(): void {
    persistNow()
  }

  function clearActionError(): void {
    actionError.value = ''
  }

  return {
    form,
    catalog,
    loading,
    loadError,
    actionError,
    jobsError,
    jobSyncError,
    warnings,
    submitting,
    jobsLoading,
    jobs,
    lastSavedAt,
    storageError,
    accentOptions,
    promptLimit,
    pollInterval,
    sizeOptions,
    busy,
    canGenerate,
    selectedAccent,
    loadCatalog,
    loadJobs,
    generate,
    cancelJob,
    deleteJob,
    clearHistory,
    applyJobSettings,
    useJobSeed,
    resetPanel,
    persistNow,
    flushPersist,
    clearActionError,
  }
})
