/**
 * i2i_main module store.
 *
 * The form and the reference images are the single source of truth for the
 * page. The form is autosaved to localStorage; the reference images are saved
 * separately and only while their combined data URLs fit the pack's
 * `persistMaxChars` budget, so very large uploads stay in memory for this
 * session instead of breaking storage. Jobs are persisted by the backend; this
 * store keeps the chat ordered oldest -> newest and reattaches polling after a
 * route switch or reload.
 */
import { computed, reactive, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { useJobsStore } from '@/stores/jobs'
import { useLibraryStore } from '@/stores/library'
import { useEngineStore } from '@/stores/engine'
import { useUiStore } from '@/stores/ui'
import { I2IApiError, i2iApi } from './api'
import type {
  I2ICatalog,
  I2IClearHistoryResult,
  I2IJobDeleteResult,
  I2IJobParams,
  I2IJobRecord,
  I2IJobRequest,
  I2IModel,
  I2IRange,
  I2ISourceState,
  I2IWarning,
} from './types'

const STORAGE_KEY = 'genai.image-to-image.form.v1'
const SOURCES_KEY = 'genai.image-to-image.sources.v2'
const LEGACY_SOURCE_KEY = 'genai.image-to-image.source.v1'
const STORAGE_VERSION = 2
const JOB_PAGE_SIZE = 60
const DEFAULT_PERSIST_MAX_CHARS = 2_500_000
const DEFAULT_MAX_SOURCES = 3

export interface I2IFormState {
  prompt: string
  negativePrompt: string
  modelId: string
  resolution: number
  batch: number
  seed: number
  lockSeed: boolean
  steps: number
  cfg: number
  denoise: number
  sampler: string
  cacheDevice: string
  cacheDtype: string
}

export type I2IPanel = 'source' | 'output' | 'sampling' | 'advanced' | 'prompt' | 'all'

interface PersistedForm {
  form: Record<string, unknown>
  savedAt: number | null
}

interface PersistedSources {
  sources: I2ISourceState[]
  savedAt: number | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function randomSeed(): number {
  if (typeof crypto !== 'undefined' && 'getRandomValues' in crypto) {
    const buffer = new Uint32Array(1)
    crypto.getRandomValues(buffer)
    return buffer[0] % 4_294_967_296
  }
  return Math.floor(Math.random() * 4_294_967_296)
}

function defaultForm(): I2IFormState {
  return {
    prompt: '',
    negativePrompt: '',
    modelId: '',
    resolution: 0,
    batch: 1,
    seed: randomSeed(),
    lockSeed: false,
    steps: 8,
    cfg: 1,
    denoise: 1,
    sampler: 'euler',
    cacheDevice: 'auto',
    cacheDtype: 'default',
  }
}

function emptySource(): I2ISourceState {
  return {
    name: '',
    dataUrl: '',
    width: 0,
    height: 0,
    sizeBytes: 0,
    restored: false,
  }
}

function readPersistedForm(): PersistedForm | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const decoded: unknown = JSON.parse(raw)
    if (!isRecord(decoded)) return null
    const candidate = isRecord(decoded.form) ? decoded.form : decoded
    return {
      form: candidate,
      savedAt: typeof decoded.savedAt === 'number' ? decoded.savedAt : null,
    }
  } catch {
    return null
  }
}

function parseSourceState(item: unknown, restored: boolean): I2ISourceState | null {
  if (!isRecord(item)) return null
  if (typeof item.dataUrl !== 'string' || !item.dataUrl.startsWith('data:image/')) return null
  return {
    name: typeof item.name === 'string' ? item.name : 'reference',
    dataUrl: item.dataUrl,
    width: typeof item.width === 'number' ? item.width : 0,
    height: typeof item.height === 'number' ? item.height : 0,
    sizeBytes: typeof item.sizeBytes === 'number' ? item.sizeBytes : 0,
    restored,
  }
}

function readPersistedSources(): PersistedSources | null {
  try {
    const raw = localStorage.getItem(SOURCES_KEY)
    if (raw) {
      const decoded: unknown = JSON.parse(raw)
      if (isRecord(decoded) && Array.isArray(decoded.sources)) {
        const sources = decoded.sources
          .map((item) => parseSourceState(item, true))
          .filter((item): item is I2ISourceState => item != null)
        if (sources.length) {
          return {
            sources,
            savedAt: typeof decoded.savedAt === 'number' ? decoded.savedAt : null,
          }
        }
      }
    }
    // Migrate the single-image payload written by the previous version.
    const legacy = localStorage.getItem(LEGACY_SOURCE_KEY)
    if (!legacy) return null
    const decoded: unknown = JSON.parse(legacy)
    if (!isRecord(decoded)) return null
    const source = parseSourceState(decoded.source, true)
    if (!source) return null
    return {
      sources: [source],
      savedAt: typeof decoded.savedAt === 'number' ? decoded.savedAt : null,
    }
  } catch {
    return null
  }
}

function mergePersisted(base: I2IFormState, saved: Record<string, unknown>): boolean {
  let changed = false
  for (const key of Object.keys(base) as Array<keyof I2IFormState>) {
    if (!(key in saved)) continue
    const value = saved[key]
    const expected = typeof base[key]
    if (expected === 'number') {
      if (typeof value === 'number' && Number.isFinite(value)) {
        ;(base as unknown as Record<string, unknown>)[key] = value
        changed = true
      }
      continue
    }
    if (expected === 'boolean') {
      if (typeof value === 'boolean') {
        ;(base as unknown as Record<string, unknown>)[key] = value
        changed = true
      }
      continue
    }
    if (expected === 'string' && typeof value === 'string') {
      ;(base as unknown as Record<string, unknown>)[key] = value
      changed = true
    }
  }
  return changed
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function clampRange(value: number, range: I2IRange): number {
  let next = Number.isFinite(value) ? value : range.default
  const step = Number(range.step)
  if (step > 0) {
    next = range.min + Math.round((next - range.min) / step) * step
  }
  next = clamp(next, range.min, range.max)
  const precision = Number.isFinite(range.precision)
    ? Math.max(0, Math.min(6, Math.trunc(range.precision)))
    : 3
  return Number(next.toFixed(precision))
}

// Python's round() is half-to-even; the backend's _round32 relies on it. Mirror
// that here so the size shown in the GUI is the size the graph will use.
function roundLikePython(value: number): number {
  const floor = Math.floor(value)
  const fraction = value - floor
  if (fraction === 0.5) return floor % 2 === 0 ? floor : floor + 1
  return Math.round(value)
}

function round32(value: number): number {
  return Math.max(32, roundLikePython(value / 32) * 32)
}

/** Same formula as workflows.target_dimensions. */
export function targetDimensions(
  sourceWidth: number,
  sourceHeight: number,
  resolution: number,
): { width: number; height: number } {
  const width = Math.max(1, Math.trunc(sourceWidth || 1))
  const height = Math.max(1, Math.trunc(sourceHeight || 1))
  if (resolution > 0) {
    const ratio = width / height
    return {
      width: round32(Math.sqrt(resolution * resolution * ratio)),
      height: round32(Math.sqrt((resolution * resolution) / ratio)),
    }
  }
  return { width: round32(width), height: round32(height) }
}

function recommendedDelta(value: number, range: I2IRange): number {
  const min = Number.isFinite(range.recommendedMin) ? range.recommendedMin : range.min
  const max = Number.isFinite(range.recommendedMax) ? range.recommendedMax : range.max
  return Math.max(0, min - value, value - max)
}

export const useI2IStore = defineStore('image-to-image', () => {
  const ui = useUiStore()
  const library = useLibraryStore()
  const genericJobs = useJobsStore()
  const engine = useEngineStore()

  const persistedForm = readPersistedForm()
  const persistedSources = readPersistedSources()
  const initial = defaultForm()
  const restoredForm = persistedForm ? mergePersisted(initial, persistedForm.form) : false
  const form = reactive<I2IFormState>(initial)
  const sources = ref<I2ISourceState[]>(persistedSources?.sources ?? [])
  const source = computed<I2ISourceState>(() => sources.value[0] ?? emptySource())

  const catalog = ref<I2ICatalog | null>(null)
  const loading = ref(true)
  const loadError = ref('')
  const actionError = ref('')
  const jobsError = ref('')
  const jobSyncError = ref('')
  const catalogWarnings = ref<I2IWarning[]>([])
  const warnings = ref<I2IWarning[]>([])
  const submitting = ref(false)
  const sourceBusy = ref(false)
  const sourceNotice = ref('')
  const jobs = ref<I2IJobRecord[]>([])
  const jobsLoading = ref(false)
  const lastSavedAt = ref<number | null>(restoredForm ? (persistedForm?.savedAt ?? Date.now()) : null)
  const sourceSavedAt = ref<number | null>(
    persistedSources ? (persistedSources.savedAt ?? Date.now()) : null,
  )
  const storageError = ref('')

  let catalogInitialized = false
  let catalogAbort: AbortController | null = null
  let saveTimer: number | undefined
  const pollTimers = new Map<string, number>()
  const pollFailures = new Map<string, number>()
  const engineTracked = new Set<string>()

  function markJobActive(jobId: string): void {
    if (engineTracked.has(jobId)) return
    engineTracked.add(jobId)
    engine.jobStarted()
  }

  function releaseJob(jobId: string): void {
    if (!engineTracked.delete(jobId)) return
    engine.jobFinished()
  }

  function persistMaxChars(): number {
    return Number(catalog.value?.source.persistMaxChars ?? DEFAULT_PERSIST_MAX_CHARS)
  }

  function persistNow(): void {
    if (saveTimer !== undefined) {
      window.clearTimeout(saveTimer)
      saveTimer = undefined
    }
    try {
      const savedForm = JSON.stringify(form)
      const previous = localStorage.getItem(STORAGE_KEY)
      if (previous) {
        try {
          const decoded: unknown = JSON.parse(previous)
          if (isRecord(decoded)) {
            const candidate = isRecord(decoded.form) ? decoded.form : decoded
            if (JSON.stringify(candidate) === savedForm) {
              lastSavedAt.value =
                typeof decoded.savedAt === 'number' ? decoded.savedAt : lastSavedAt.value
              storageError.value = ''
              return
            }
          }
        } catch {
          // Fall through and overwrite a corrupt payload.
        }
      }
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          version: STORAGE_VERSION,
          savedAt: Date.now(),
          form: JSON.parse(savedForm),
        }),
      )
      lastSavedAt.value = Date.now()
      storageError.value = ''
    } catch (err) {
      storageError.value = (err as Error).message
    }
  }

  function schedulePersist(): void {
    if (saveTimer !== undefined) window.clearTimeout(saveTimer)
    saveTimer = window.setTimeout(persistNow, 180)
  }

  function flushPersist(): void {
    persistNow()
  }

  /**
   * Save the reference images together. If their combined data URLs exceed the
   * pack budget they stay in memory only, and any older saved set is removed so
   * a reload cannot silently resurrect unrelated images.
   */
  function persistSource(): void {
    try {
      localStorage.removeItem(LEGACY_SOURCE_KEY)
      if (!sources.value.length) {
        localStorage.removeItem(SOURCES_KEY)
        sourceSavedAt.value = null
        sourceNotice.value = ''
        return
      }
      const combined = sources.value.reduce((sum, item) => sum + item.dataUrl.length, 0)
      if (combined > persistMaxChars()) {
        localStorage.removeItem(SOURCES_KEY)
        sourceSavedAt.value = null
        sourceNotice.value =
          'These images are too large to save in the browser. They stay available until you reload the page.'
        return
      }
      const saved = JSON.stringify({
        version: STORAGE_VERSION,
        savedAt: Date.now(),
        sources: sources.value.map((item) => ({
          name: item.name,
          dataUrl: item.dataUrl,
          width: item.width,
          height: item.height,
          sizeBytes: item.sizeBytes,
        })),
      })
      if (localStorage.getItem(SOURCES_KEY) === saved) return
      localStorage.setItem(SOURCES_KEY, saved)
      sourceSavedAt.value = Date.now()
      sourceNotice.value = ''
    } catch (err) {
      sourceSavedAt.value = null
      sourceNotice.value = `The reference images could not be saved: ${(err as Error).message}`
    }
  }

  watch(form, schedulePersist, { deep: true })
  watch(sources, persistSource, { deep: true })
  if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', () => {
      persistNow()
      persistSource()
    })
  }

  // Multi-tab safety: adopt a form saved by another tab instead of overwriting
  // it on the next edit. The equality guard in persistNow prevents an echo.
  function handleStorage(event: StorageEvent): void {
    if (
      (event.key === SOURCES_KEY || event.key === LEGACY_SOURCE_KEY) &&
      event.newValue
    ) {
      const saved = readPersistedSources()
      if (!saved) return
      sources.value = saved.sources
      sourceSavedAt.value = saved.savedAt ?? Date.now()
      return
    }
    if (event.key !== STORAGE_KEY || !event.newValue) return
    const saved = readPersistedForm()
    if (!saved) return
    const next = defaultForm()
    mergePersisted(next, saved.form)
    if (saveTimer !== undefined) {
      window.clearTimeout(saveTimer)
      saveTimer = undefined
    }
    Object.assign(form, next)
    lastSavedAt.value = saved.savedAt ?? Date.now()
    if (catalog.value) reconcile(catalog.value, false)
  }
  if (typeof window !== 'undefined') window.addEventListener('storage', handleStorage)

  const selectedModel = computed<I2IModel | null>(() => {
    const next = catalog.value
    if (!next) return null
    return next.models.find((model) => model.id === form.modelId) ?? next.model ?? next.models[0] ?? null
  })

  const maxSources = computed(() =>
    Number(catalog.value?.source.maxImages ?? DEFAULT_MAX_SOURCES),
  )
  const sourceCount = computed(() => sources.value.length)
  const canAddSource = computed(() => sources.value.length < maxSources.value)

  const dimensions = computed(() => {
    const primary = source.value
    if (!primary.width || !primary.height) return null
    return targetDimensions(primary.width, primary.height, form.resolution)
  })

  // Engine readiness is live state, not a catalog snapshot. The shared engine
  // store polls /api/status, so ComfyUI can come online while this page is open.
  const comfyReady = computed(() => engine.comfy.connected === true)

  const hasSource = computed(() => sources.value.length > 0)

  const sourceBytes = computed(() =>
    sources.value.reduce((sum, item) => sum + item.dataUrl.length, 0),
  )

  const sourceTooLargeForStorage = computed(
    () => hasSource.value && sourceBytes.value > persistMaxChars(),
  )

  const sourcePersisted = computed(() => hasSource.value && sourceSavedAt.value != null)

  const busy = computed(
    () =>
      submitting.value ||
      jobs.value.some((job) => job.status === 'queued' || job.status === 'running'),
  )

  const canGenerate = computed(
    () =>
      catalog.value != null &&
      catalog.value.ready !== false &&
      form.prompt.trim().length > 0 &&
      hasSource.value &&
      !busy.value &&
      selectedModel.value != null &&
      selectedModel.value.ready !== false &&
      comfyReady.value,
  )

  const activeJob = computed(
    () => jobs.value.find((job) => job.status === 'queued' || job.status === 'running') ?? null,
  )

  const latestSourceLabel = computed(() => {
    const count = sources.value.length
    if (!count) return 'No reference images'
    if (count === 1) {
      const primary = sources.value[0]
      const size =
        primary.width && primary.height ? ` · ${primary.width}×${primary.height}` : ''
      return `Image 1 · ${primary.name || 'reference'}${size}`
    }
    return `${count} reference images (Image 1..${count})`
  })

  const denoiseSummary = computed(() =>
    form.denoise >= 0.999 ? 'full (official turbo)' : `img2img ${form.denoise.toFixed(2)}`,
  )

  function applyDefaults(next: I2ICatalog): void {
    const defaults = next.defaults
    const model =
      next.models.find((item) => item.id === defaults.modelId) ??
      next.models.find((item) => item.id === next.selectedModelId) ??
      next.models[0] ??
      null
    form.modelId = model?.id ?? defaults.modelId
    form.negativePrompt = defaults.negativePrompt
    form.resolution = next.resolutions.some((item) => item.value === defaults.resolution)
      ? defaults.resolution
      : (next.resolutions[0]?.value ?? 0)
    form.batch = defaults.batch
    form.seed = randomSeed()
    form.lockSeed = defaults.lockSeed
    form.steps = defaults.steps
    form.cfg = defaults.cfg
    form.denoise = defaults.denoise
    form.sampler = defaults.sampler
    form.cacheDevice = next.cacheDevices.includes(defaults.cacheDevice)
      ? defaults.cacheDevice
      : (next.cacheDevices[0] ?? 'auto')
    form.cacheDtype = next.cacheDtypes.includes(defaults.cacheDtype)
      ? defaults.cacheDtype
      : (next.cacheDtypes[0] ?? 'default')
  }

  function applySamplingDefaults(next: I2ICatalog): void {
    const defaults = next.defaults
    form.steps = defaults.steps
    form.cfg = defaults.cfg
    form.denoise = defaults.denoise
    form.sampler = defaults.sampler
  }

  function applyOutputDefaults(next: I2ICatalog): void {
    const defaults = next.defaults
    form.modelId = defaults.modelId
    form.resolution = next.resolutions.some((item) => item.value === defaults.resolution)
      ? defaults.resolution
      : (next.resolutions[0]?.value ?? 0)
    form.batch = defaults.batch
    form.seed = randomSeed()
    form.lockSeed = defaults.lockSeed
    reconcile(next, false)
  }

  function reconcile(next: I2ICatalog, notify = true): boolean {
    let changed = false
    const mark = (): void => {
      changed = true
    }

    let model = next.models.find((item) => item.id === form.modelId) ?? null
    if (!model) {
      const fallback = next.models.find((item) => item.id === next.defaults.modelId) ?? next.models[0]
      if (fallback) {
        form.modelId = fallback.id
        model = fallback
        mark()
      }
    }
    if (model?.present === false) {
      const fallback =
        next.models.find((item) => item.id === next.defaults.modelId && item.present !== false) ??
        next.models.find((item) => item.present === true)
      if (fallback) {
        form.modelId = fallback.id
        model = fallback
        mark()
      }
    }
    if (!model) return changed

    if (!next.resolutions.some((item) => item.value === form.resolution)) {
      form.resolution = next.resolutions.some((item) => item.value === next.defaults.resolution)
        ? next.defaults.resolution
        : (next.resolutions[0]?.value ?? 0)
      mark()
    }

    const batch = clamp(Math.round(form.batch), model.ranges.batch.min, model.ranges.batch.max)
    if (batch !== form.batch) {
      form.batch = batch
      mark()
    }

    if (!Number.isFinite(form.seed) || form.seed < 0 || form.seed > 4_294_967_295) {
      form.seed = randomSeed()
      mark()
    } else if (Math.round(form.seed) !== form.seed) {
      form.seed = Math.round(form.seed)
      mark()
    }

    const sampling: Array<[keyof I2IFormState, I2IRange]> = [
      ['steps', model.ranges.steps],
      ['cfg', model.ranges.cfg],
      ['denoise', model.ranges.denoise],
    ]
    for (const [key, range] of sampling) {
      const current = form[key] as number
      const adjusted = clampRange(current, range)
      if (adjusted !== current) {
        ;(form as unknown as Record<string, unknown>)[key] = adjusted
        mark()
      }
    }

    if (!next.samplers.some((sampler) => sampler.id === form.sampler)) {
      form.sampler = next.defaults.sampler
      mark()
    }
    if (!next.cacheDevices.includes(form.cacheDevice)) {
      form.cacheDevice = next.cacheDevices[0] ?? 'auto'
      mark()
    }
    if (!next.cacheDtypes.includes(form.cacheDtype)) {
      form.cacheDtype = next.cacheDtypes[0] ?? 'default'
      mark()
    }

    if (changed && notify) {
      ui.toast('Restored Image -> Image settings were adjusted to the current pack ranges.', 'info', 5000)
    }
    return changed
  }

  function applyCatalog(next: I2ICatalog): void {
    const firstLoad = !catalogInitialized
    catalog.value = next
    catalogWarnings.value = next.warnings ?? []
    if (firstLoad) {
      if (restoredForm) reconcile(next)
      else applyDefaults(next)
      catalogInitialized = true
    } else {
      reconcile(next)
    }
    loading.value = false
    // The saved images may have been written under a smaller budget. Re-check
    // once the real pack limit is known.
    if (sources.value.length) persistSource()
  }

  async function loadCatalog(modelId: string | null = null): Promise<void> {
    catalogAbort?.abort()
    catalogAbort = new AbortController()
    if (!catalog.value) loading.value = true
    loadError.value = ''
    try {
      let next = await i2iApi.getCatalog(modelId, catalogAbort.signal)
      if (!modelId && next.models.length > 1) {
        const current = next.models.find((item) => item.id === form.modelId)
        if (current?.packId && current.packId !== next.pack?.id) {
          next = await i2iApi.getCatalog(current.id, catalogAbort.signal)
        }
      }
      applyCatalog(next)
      if (modelId) {
        form.modelId = modelId
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      if (err instanceof Error && err.name === 'AbortError') return
      const message = errorText(err)
      if (catalog.value) actionError.value = message
      else loadError.value = message
    } finally {
      loading.value = false
    }
  }

  // The catalog carries file presence, warnings and limits. Refresh it once when
  // the shared status poll sees ComfyUI flip.
  let engineCatalogTimer: number | undefined
  watch(
    () => engine.comfy.connected,
    (comfy) => {
      const snapshot = catalog.value?.engine
      if (!snapshot) return
      if (snapshot.comfyui.connected === comfy) return
      if (engineCatalogTimer !== undefined) window.clearTimeout(engineCatalogTimer)
      engineCatalogTimer = window.setTimeout(() => {
        engineCatalogTimer = undefined
        if (catalog.value) void loadCatalog()
      }, 450)
    },
  )

  function setResolution(value: number): void {
    form.resolution = value
  }

  function onModelChange(): void {
    const next = catalog.value
    if (!next) return
    const model = next.models.find((item) => item.id === form.modelId)
    if (!model) return
    form.modelId = model.id
    reconcile(next, false)
    persistNow()
    ui.toast(`Using ${model.shortLabel}.`, 'info')
  }

  function setSources(next: I2ISourceState[]): void {
    sources.value = next.slice(0, maxSources.value)
    sourceNotice.value =
      sourceBytes.value > persistMaxChars()
        ? 'These images are too large to save in the browser. They stay available until you reload the page.'
        : ''
    persistSource()
  }

  function addSource(next: I2ISourceState): boolean {
    if (sources.value.length >= maxSources.value) {
      actionError.value = `This model accepts up to ${maxSources.value} reference images. Remove one first.`
      return false
    }
    sources.value = [...sources.value, next]
    persistSource()
    return true
  }

  function replaceSource(index: number, next: I2ISourceState): void {
    if (index < 0 || index >= sources.value.length) return
    const list = [...sources.value]
    list.splice(index, 1, next)
    sources.value = list
    persistSource()
  }

  function removeSource(index: number): void {
    sources.value = sources.value.filter((_, itemIndex) => itemIndex !== index)
    persistSource()
  }

  function clearSource(): void {
    sources.value = []
    sourceNotice.value = ''
    persistSource()
  }

  function readAsDataUrl(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result || ''))
      reader.onerror = () => reject(reader.error ?? new Error('The image could not be read.'))
      reader.readAsDataURL(file)
    })
  }

  function imageSize(dataUrl: string): Promise<{ width: number; height: number }> {
    return new Promise((resolve, reject) => {
      const image = new Image()
      image.onload = () => resolve({ width: image.naturalWidth, height: image.naturalHeight })
      image.onerror = () => reject(new Error('The file is not a readable image.'))
      image.src = dataUrl
    })
  }

  /**
   * Read one user-selected image. This mirrors the server limits for fast
   * feedback; the backend still decodes and validates every upload.
   */
  async function readSourceFile(file: File): Promise<I2ISourceState> {
    const limits = catalog.value?.source
    if (!file.type.startsWith('image/')) {
      throw new Error('Choose an image file (PNG, JPEG, WebP or BMP).')
    }
    if (limits && !limits.mimeTypes.includes(file.type) && file.type !== 'image/jpg') {
      throw new Error(`${file.type} is not supported. Use ${limits.mimeTypes.join(', ')}.`)
    }
    if (limits && file.size > limits.maxBytes) {
      throw new Error(
        `The image is ${(file.size / 1048576).toFixed(1)} MB; the limit is ${(
          limits.maxBytes / 1048576
        ).toFixed(0)} MB.`,
      )
    }
    const dataUrl = await readAsDataUrl(file)
    const size = await imageSize(dataUrl)
    if (limits) {
      if (size.width < 16 || size.height < 16) {
        throw new Error('Use an image at least 16×16 px.')
      }
      if (Math.max(size.width, size.height) > limits.maxSide) {
        throw new Error(
          `The image is ${size.width}×${size.height}; the longest side may not exceed ${limits.maxSide} px.`,
        )
      }
      if (size.width * size.height > limits.maxPixels) {
        throw new Error(
          `The image has ${size.width * size.height} pixels; the limit is ${limits.maxPixels}.`,
        )
      }
    }
    return {
      name: file.name || 'reference',
      dataUrl,
      width: size.width,
      height: size.height,
      sizeBytes: file.size,
      restored: false,
    }
  }

  /** Append one or more reference images, up to the model's limit. */
  async function selectSourceFiles(files: FileList | File[]): Promise<void> {
    const list = Array.from(files)
    if (!list.length) return
    sourceBusy.value = true
    actionError.value = ''
    try {
      const room = Math.max(0, maxSources.value - sources.value.length)
      if (!room) {
        throw new Error(
          `This model accepts up to ${maxSources.value} reference images. Remove one first.`,
        )
      }
      const accepted = list.slice(0, room)
      for (const file of accepted) {
        sources.value = [...sources.value, await readSourceFile(file)]
      }
      persistSource()
      if (list.length > accepted.length) {
        actionError.value = `Added ${accepted.length} image(s). This model accepts up to ${maxSources.value} reference images.`
      }
      ui.toast(
        accepted.length === 1
          ? 'Reference image ready.'
          : `${accepted.length} reference images ready.`,
        'success',
      )
    } catch (err) {
      actionError.value = errorText(err)
    } finally {
      sourceBusy.value = false
    }
  }

  async function selectSourceFile(file: File): Promise<void> {
    await selectSourceFiles([file])
  }

  /** Replace the reference at `index` without changing the other slots. */
  async function replaceSourceFile(index: number, file: File): Promise<void> {
    sourceBusy.value = true
    actionError.value = ''
    try {
      replaceSource(index, await readSourceFile(file))
      ui.toast(`Image ${index + 1} replaced.`, 'success')
    } catch (err) {
      actionError.value = errorText(err)
    } finally {
      sourceBusy.value = false
    }
  }

  function resetPanel(panel: I2IPanel): void {
    const next = catalog.value
    if (!next) return
    switch (panel) {
      case 'source':
        clearSource()
        ui.toast('Reference images cleared.', 'success')
        break
      case 'output':
        applyOutputDefaults(next)
        ui.toast('Output panel reset to pack defaults.', 'success')
        break
      case 'sampling':
        applySamplingDefaults(next)
        ui.toast('Sampling panel reset.', 'success')
        break
      case 'advanced':
        form.cacheDevice = next.cacheDevices[0] ?? 'auto'
        form.cacheDtype = next.cacheDtypes[0] ?? 'default'
        ui.toast('Advanced settings reset.', 'success')
        break
      case 'prompt':
        form.negativePrompt = next.defaults.negativePrompt
        ui.toast('Prompt extras reset.', 'success')
        break
      case 'all':
        applyDefaults(next)
        form.prompt = ''
        clearSource()
        ui.toast('All Image -> Image settings reset.', 'success')
        break
    }
    persistNow()
  }

  function buildRequest(): I2IJobRequest {
    return {
      modelId: form.modelId,
      recipeId: catalog.value?.defaults.recipeId,
      prompt: form.prompt.trim(),
      negativePrompt: form.negativePrompt.trim(),
      sourceImages: sources.value.map((item) => ({
        image: item.dataUrl,
        name: item.name,
      })),
      resolution: form.resolution,
      batch: form.batch,
      seed: form.seed,
      lockSeed: form.lockSeed,
      steps: form.steps,
      cfg: form.cfg,
      denoise: form.denoise,
      sampler: form.sampler,
      cacheDevice: form.cacheDevice,
      cacheDtype: form.cacheDtype,
      tab: 'image-to-image',
    }
  }

  function errorText(err: unknown): string {
    if (err instanceof I2IApiError) {
      if (err.errors.length) return `${err.message} (${err.errors[0].message})`
      return err.message
    }
    if (err instanceof Error) return err.message
    return 'Something went wrong.'
  }

  function replaceJob(next: I2IJobRecord): void {
    const index = jobs.value.findIndex((job) => job.id === next.id)
    if (index >= 0) jobs.value.splice(index, 1, next)
    else jobs.value.push(next)
  }

  function pollDelay(): number {
    const seconds = Number(catalog.value?.limits.pollIntervalSeconds ?? 1)
    return Math.max(750, Math.round(seconds * 1000))
  }

  function clearPollTimer(jobId: string): void {
    const timer = pollTimers.get(jobId)
    if (timer !== undefined) window.clearTimeout(timer)
    pollTimers.delete(jobId)
  }

  function stopPolling(jobId: string): void {
    clearPollTimer(jobId)
    pollFailures.delete(jobId)
  }

  function schedulePoll(jobId: string, delay = pollDelay()): void {
    clearPollTimer(jobId)
    pollTimers.set(
      jobId,
      window.setTimeout(() => {
        pollTimers.delete(jobId)
        void fetchJob(jobId)
      }, delay),
    )
  }

  async function fetchJob(jobId: string): Promise<void> {
    try {
      const next = await i2iApi.getJob(jobId)
      replaceJob(next)
      pollFailures.delete(jobId)
      jobSyncError.value = ''
      if (next.status === 'queued' || next.status === 'running') {
        markJobActive(jobId)
        schedulePoll(jobId)
        return
      }
      stopPolling(jobId)
      releaseJob(jobId)
      warnings.value = next.params?.warnings ?? warnings.value
      void library.syncFromBackend()
      void genericJobs.syncFromBackend()
    } catch (err) {
      if (err instanceof I2IApiError && err.status === 404) {
        jobs.value = jobs.value.filter((job) => job.id !== jobId)
        stopPolling(jobId)
        releaseJob(jobId)
        jobSyncError.value = ''
        return
      }
      const failures = (pollFailures.get(jobId) ?? 0) + 1
      pollFailures.set(jobId, failures)
      if (failures >= 2) {
        jobSyncError.value = `Live updates for ${jobId} are retrying: ${errorText(err)}`
      }
      schedulePoll(jobId, Math.min(15_000, pollDelay() * 2 ** Math.min(failures, 4)))
    }
  }

  async function loadJobs(): Promise<void> {
    jobsLoading.value = true
    jobsError.value = ''
    try {
      const list = await i2iApi.listJobs(JOB_PAGE_SIZE)
      jobSyncError.value = ''
      const remote = [...list].reverse()
      // A generate() can finish while this list request is in flight. Keep any
      // local running/queued job that the earlier snapshot did not include.
      const remoteIds = new Set(remote.map((job) => job.id))
      const pendingLocal = jobs.value.filter(
        (job) => !remoteIds.has(job.id) && (job.status === 'queued' || job.status === 'running'),
      )
      jobs.value = [...remote, ...pendingLocal].sort((a, b) => a.createdAt - b.createdAt)
      for (const job of jobs.value) {
        if (job.status === 'queued' || job.status === 'running') {
          markJobActive(job.id)
          schedulePoll(job.id)
        } else {
          releaseJob(job.id)
        }
      }
    } catch (err) {
      jobsError.value = errorText(err)
    } finally {
      jobsLoading.value = false
    }
  }

  async function generate(): Promise<void> {
    if (!catalog.value || busy.value) return
    submitting.value = true
    actionError.value = ''
    warnings.value = []
    try {
      const request = buildRequest()
      if (!request.prompt) throw new Error('Describe the change you want first.')
      if (!request.sourceImages?.length) throw new Error('Choose at least one reference image first.')
      const validation = await i2iApi.validate(request)
      warnings.value = validation.warnings ?? []
      const job = await i2iApi.createJob(request)
      jobs.value.push(job)
      markJobActive(job.id)
      persistNow()
      schedulePoll(job.id, 500)
      void genericJobs.syncFromBackend()
    } catch (err) {
      if (err instanceof I2IApiError) {
        actionError.value = errorText(err)
        if (err.warnings.length) warnings.value = err.warnings
      } else {
        actionError.value = errorText(err)
      }
    } finally {
      submitting.value = false
    }
  }

  async function cancelJob(jobId: string): Promise<void> {
    try {
      const next = await i2iApi.cancelJob(jobId)
      replaceJob(next)
      if (next.status !== 'queued' && next.status !== 'running') releaseJob(jobId)
      schedulePoll(jobId, 400)
    } catch (err) {
      actionError.value = errorText(err)
    }
  }

  async function deleteJob(jobId: string, deleteAssets: boolean): Promise<I2IJobDeleteResult> {
    const result = await i2iApi.deleteJob(jobId, deleteAssets)
    jobs.value = jobs.value.filter((job) => job.id !== jobId)
    stopPolling(jobId)
    releaseJob(jobId)
    jobSyncError.value = ''
    if (deleteAssets) await library.syncFromBackend()
    void genericJobs.syncFromBackend()
    ui.toast(
      deleteAssets
        ? `Deleted ${jobId}; its images were moved to trash.`
        : `Removed ${jobId} from history; its images stay in the Library.`,
      'success',
    )
    return result
  }

  async function clearHistory(deleteAssets: boolean): Promise<I2IClearHistoryResult> {
    const result = await i2iApi.clearHistory(deleteAssets)
    const cleared = new Set(result.jobIds)
    jobs.value = jobs.value.filter((job) => !cleared.has(job.id))
    for (const jobId of cleared) {
      stopPolling(jobId)
      releaseJob(jobId)
    }
    jobSyncError.value = ''
    await library.syncFromBackend()
    void genericJobs.syncFromBackend()
    ui.toast(
      deleteAssets
        ? `Cleared ${result.deleted} chat item${result.deleted === 1 ? '' : 's'}; ${result.assetsTrashed.length} image${result.assetsTrashed.length === 1 ? '' : 's'} moved to trash.`
        : `Cleared ${result.deleted} chat item${result.deleted === 1 ? '' : 's'}; images stay in the Library.`,
      'success',
    )
    return result
  }

  /**
   * Reuse a job's prompt and settings. The result record only stores a small
   * source thumbnail, never the full source bytes, so the source itself stays
   * whatever the user has selected now.
   */
  function applyJobSettings(job: I2IJobRecord): void {
    const params: Partial<I2IJobParams> = job.params ?? {}
    form.prompt = job.prompt || params.promptUsed || ''
    form.negativePrompt = params.negativePrompt ?? form.negativePrompt
    form.modelId = params.modelId || job.modelId || form.modelId
    form.resolution = params.resolution ?? form.resolution
    form.batch = params.batch ?? form.batch
    form.seed = Number(params.seed ?? job.seed ?? form.seed)
    form.lockSeed = params.lockSeed ?? true
    form.steps = params.steps ?? form.steps
    form.cfg = params.cfg ?? form.cfg
    form.denoise = params.denoise ?? form.denoise
    form.sampler = params.sampler ?? form.sampler
    form.cacheDevice = params.cacheDevice ?? form.cacheDevice
    form.cacheDtype = params.cacheDtype ?? form.cacheDtype
    if (catalog.value) reconcile(catalog.value, false)
    persistNow()
    ui.toast(
      hasSource.value
        ? `Reused prompt and settings from ${job.id}.`
        : `Reused prompt and settings from ${job.id}. Choose a source image to generate.`,
      'success',
      5000,
    )
  }

  function useJobSeed(job: I2IJobRecord): void {
    form.seed = Number(job.params?.seed ?? job.seed ?? form.seed)
    form.lockSeed = true
    persistNow()
    ui.toast(`Seed ${form.seed} locked.`, 'success')
  }

  return {
    // state
    form,
    source,
    sources,
    catalog,
    loading,
    loadError,
    actionError,
    jobsError,
    jobSyncError,
    catalogWarnings,
    warnings,
    submitting,
    sourceBusy,
    sourceNotice,
    jobs,
    jobsLoading,
    lastSavedAt,
    sourceSavedAt,
    storageError,
    // derived
    selectedModel,
    dimensions,
    comfyReady,
    hasSource,
    sourceCount,
    maxSources,
    canAddSource,
    sourceBytes,
    sourceTooLargeForStorage,
    sourcePersisted,
    busy,
    canGenerate,
    activeJob,
    latestSourceLabel,
    denoiseSummary,
    // lifecycle
    loadCatalog,
    loadJobs,
    flushPersist,
    errorText,
    // actions
    setResolution,
    onModelChange,
    selectSourceFile,
    selectSourceFiles,
    replaceSourceFile,
    setSources,
    addSource,
    replaceSource,
    removeSource,
    clearSource,
    resetPanel,
    generate,
    cancelJob,
    deleteJob,
    clearHistory,
    applyJobSettings,
    useJobSeed,
  }
})
