/**
 * T2I_main module store.
 *
 * The form is the single source of truth for the page. It is autosaved to
 * localStorage, reconciled against the live pack/catalog on load, and every
 * settings panel can reset its own slice. Jobs are persisted by the backend;
 * this store keeps the chat ordered oldest -> newest and reattaches polling
 * after a route switch or reload.
 */
import { computed, reactive, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { useJobsStore } from '@/stores/jobs'
import { useLibraryStore } from '@/stores/library'
import { useEngineStore } from '@/stores/engine'
import { useUiStore } from '@/stores/ui'
import { T2IApiError, t2iApi } from './api'
import type {
  T2ICatalog,
  T2IEnhanceResponse,
  T2IJobDeleteResult,
  T2IJobParams,
  T2IJobRecord,
  T2IJobRequest,
  T2ILora,
  T2IModel,
  T2IProvider,
  T2IRange,
  T2IUpscaler,
  T2IWarning,
} from './types'

const STORAGE_KEY = 'genai.t2i.form.v1'
const STORAGE_VERSION = 1
const JOB_PAGE_SIZE = 60

export interface T2ILoraForm {
  id: string
  strength?: number | null
  on: boolean
}

export interface T2IFormState {
  prompt: string
  negativePrompt: string
  modelId: string
  ratio: string
  size: number
  batch: number
  seed: number
  lockSeed: boolean
  loras: T2ILoraForm[]
  autoTriggers: boolean
  enhanceEnabled: boolean
  enhanceProvider: T2IProvider
  enhanceModel: string
  fallbackToOriginal: boolean
  approvedPrompt: string
  steps: number
  cfg: number
  sampler: string
  scheduler: string
  denoise: number
  refineSteps: number
  refineCfg: number
  refineDenoise: number
  upscalerId: string
  upscalerEnabled: boolean
  upscalerValue: number
}

export type T2IPanel = 'prompt' | 'output' | 'loras' | 'enhance' | 'sampling' | 'upscale' | 'all'

interface PersistedForm {
  form: Record<string, unknown>
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

function defaultForm(): T2IFormState {
  return {
    prompt: '',
    negativePrompt: '',
    modelId: '',
    ratio: '1:1',
    size: 1024,
    batch: 1,
    seed: randomSeed(),
    lockSeed: false,
    loras: [],
    autoTriggers: true,
    enhanceEnabled: false,
    enhanceProvider: 'ollama',
    enhanceModel: '',
    fallbackToOriginal: false,
    approvedPrompt: '',
    steps: 8,
    cfg: 1,
    sampler: 'euler',
    scheduler: 'simple',
    denoise: 1,
    refineSteps: 2,
    refineCfg: 1,
    refineDenoise: 0.35,
    upscalerId: 'latent-refine',
    upscalerEnabled: true,
    upscalerValue: 1536,
  }
}

function readPersisted(): PersistedForm | null {
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

function sanitizeLoras(value: unknown): T2ILoraForm[] | null {
  if (!Array.isArray(value)) return null
  return value
    .filter(isRecord)
    .filter((item) => typeof item.id === 'string' && item.id.trim())
    .map((item) => ({
      id: String(item.id),
      strength:
        typeof item.strength === 'number' && Number.isFinite(item.strength)
          ? item.strength
          : null,
      on: item.on !== false,
    }))
}

function mergePersisted(base: T2IFormState, saved: Record<string, unknown>): boolean {
  let changed = false
  for (const key of Object.keys(base) as Array<keyof T2IFormState>) {
    if (!(key in saved)) continue
    const value = saved[key]
    if (key === 'loras') {
      const loras = sanitizeLoras(value)
      if (loras) {
        base.loras = loras
        changed = true
      }
      continue
    }
    if (key === 'enhanceProvider') {
      if (value === 'ollama' || value === 'comfyui') {
        base.enhanceProvider = value
        changed = true
      }
      continue
    }
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

function clampRange(value: number, range: T2IRange): number {
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

function nearestSize(value: number, values: number[]): number {
  if (!values.length) return value
  return values.reduce(
    (best, candidate) => (Math.abs(candidate - value) < Math.abs(best - value) ? candidate : best),
    values[0],
  )
}

function loraCompatible(lora: T2ILora, model: T2IModel | null): boolean {
  if (!lora.t2i || lora.available === false || lora.present === false) return false
  if (!model) return true
  if (lora.compatibleModels?.length) return lora.compatibleModels.includes(model.id)
  if (model.compatibleLoras?.length) return model.compatibleLoras.includes(lora.id)
  return lora.base === model.base || lora.compatibleBases?.includes(model.base)
}

function upscalerRangeFor(upscaler: T2IUpscaler | null, model: T2IModel | null): T2IRange | null {
  if (!upscaler || upscaler.kind === 'none') return null
  if (upscaler.kind === 'latent') return model?.ranges.refine.scale ?? upscaler.valueRange
  return upscaler.valueRange
}

export const useT2IStore = defineStore('t2i', () => {
  const ui = useUiStore()
  const library = useLibraryStore()
  const genericJobs = useJobsStore()
  const engine = useEngineStore()

  const persisted = readPersisted()
  const initial = defaultForm()
  const restored = persisted ? mergePersisted(initial, persisted.form) : false
  const form = reactive<T2IFormState>(initial)

  const catalog = ref<T2ICatalog | null>(null)
  const loading = ref(true)
  const loadError = ref('')
  const actionError = ref('')
  const jobsError = ref('')
  const jobSyncError = ref('')
  const catalogWarnings = ref<T2IWarning[]>([])
  const warnings = ref<T2IWarning[]>([])
  const submitting = ref(false)
  const enhancing = ref(false)
  const enhancePreview = ref<T2IEnhanceResponse | null>(null)
  const jobs = ref<T2IJobRecord[]>([])
  const jobsLoading = ref(false)
  const lastSavedAt = ref<number | null>(restored ? (persisted?.savedAt ?? Date.now()) : null)
  const storageError = ref('')

  let catalogInitialized = false
  let catalogAbort: AbortController | null = null
  let enhanceAbort: AbortController | null = null
  let saveTimer: number | undefined
  let persistReady = true
  const pollTimers = new Map<string, number>()
  const pollFailures = new Map<string, number>()
  // Jobs counted in the shared engine store. Deduplicated so a reattach after
  // navigation or a repeated load cannot double-count the top-bar busy state.
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

  function persistNow(): void {
    if (saveTimer !== undefined) {
      window.clearTimeout(saveTimer)
      saveTimer = undefined
    }
    if (!persistReady) return
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          version: STORAGE_VERSION,
          savedAt: Date.now(),
          form,
        }),
      )
      lastSavedAt.value = Date.now()
      storageError.value = ''
    } catch (err) {
      persistReady = false
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

  watch(form, schedulePersist, { deep: true })
  // An approved rewrite or preview belongs to the prompt it was generated
  // from. Editing the prompt invalidates both rather than silently applying an
  // old rewrite to new text.
  watch(
    () => form.prompt,
    () => {
      if (enhancing.value) cancelEnhancement()
      if (!form.approvedPrompt && !enhancePreview.value) return
      form.approvedPrompt = ''
      enhancePreview.value = null
    },
  )
  if (typeof window !== 'undefined') window.addEventListener('beforeunload', persistNow)

  const selectedModel = computed<T2IModel | null>(() => {
    const next = catalog.value
    if (!next) return null
    return next.models.find((model) => model.id === form.modelId) ?? next.models[0] ?? null
  })

  const availableLoras = computed<T2ILora[]>(() => {
    const next = catalog.value
    if (!next) return []
    const model = selectedModel.value
    return next.loras.filter((lora) => loraCompatible(lora, model))
  })

  const upscaler = computed<T2IUpscaler | null>(() => {
    const next = catalog.value
    if (!next) return null
    return next.upscalers.find((item) => item.id === form.upscalerId) ?? null
  })

  const upscalerRange = computed<T2IRange | null>(() =>
    upscalerRangeFor(upscaler.value, selectedModel.value),
  )

  const upscalerOn = computed(
    () => form.upscalerEnabled && upscaler.value != null && upscaler.value.kind !== 'none',
  )

  const refineActive = computed(
    () => upscalerOn.value && upscaler.value?.kind === 'latent',
  )

  const upscalerLabel = computed(() => {
    if (!upscalerOn.value) return 'Upscale off'
    const item = upscaler.value
    if (!item) return 'Upscale'
    if (item.kind === 'latent') return `Refine ${form.upscalerValue}px`
    return `${item.shortLabel} ${form.upscalerValue}px`
  })

  const enhanceModels = computed(() => {
    const next = catalog.value
    if (!next) return []
    return next.textModels.filter((model) => model.provider === form.enhanceProvider)
  })

  const comfyReady = computed(() => catalog.value?.engine.comfyui.connected === true)

  const providerReady = computed(() => {
    if (form.enhanceProvider === 'ollama') return catalog.value?.engine.ollama.connected === true
    return comfyReady.value
  })

  const activeLoraCount = computed(() => form.loras.filter((lora) => lora.on).length)

  const busy = computed(
    () =>
      submitting.value ||
      jobs.value.some((job) => job.status === 'queued' || job.status === 'running'),
  )

  const canGenerate = computed(
    () =>
      catalog.value != null &&
      form.prompt.trim().length > 0 &&
      !busy.value &&
      !enhancing.value &&
      selectedModel.value != null &&
      selectedModel.value.ready !== false &&
      comfyReady.value &&
      // Enhancement needs a live text provider unless the user approved a
      // rewrite or explicitly allows fallback to the original prompt.
      (!form.enhanceEnabled ||
        form.approvedPrompt.trim().length > 0 ||
        form.fallbackToOriginal ||
        providerReady.value),
  )

  const canEnhance = computed(
    () =>
      catalog.value != null &&
      form.prompt.trim().length > 0 &&
      !enhancing.value &&
      providerReady.value,
  )

  const activeJob = computed(
    () => jobs.value.find((job) => job.status === 'queued' || job.status === 'running') ?? null,
  )

  function fallbackUpscaler(next: T2ICatalog, onlyPresent = false): T2IUpscaler | null {
    const candidates = next.upscalers.filter(
      (item) =>
        item.t2i &&
        item.kind !== 'none' &&
        (!onlyPresent || item.present !== false),
    )
    return candidates.find((item) => item.enabledByDefault) ?? candidates[0] ?? null
  }

  function defaultLoras(next: T2ICatalog, model: T2IModel | null): T2ILoraForm[] {
    const chain = next.defaults.loraChain ?? []
    const allowed = new Map(next.loras.filter((lora) => loraCompatible(lora, model)).map((lora) => [lora.id, lora]))
    return chain
      .filter((entry) => entry.on !== false)
      .filter((entry) => allowed.has(entry.id))
      .slice(0, next.limits.maxLoras)
      .map((entry) => ({
        id: entry.id,
        strength: entry.strength ?? allowed.get(entry.id)?.strength.default ?? null,
        on: true,
      }))
  }

  function applyModelDefaults(next: T2ICatalog, resetLoras = false): void {
    const model = next.models.find((item) => item.id === form.modelId) ?? next.models[0] ?? null
    if (!model) return
    form.modelId = model.id
    form.steps = model.defaults.steps
    form.cfg = model.defaults.cfg
    form.sampler = model.defaults.sampler
    form.scheduler = model.defaults.scheduler
    form.denoise = model.defaults.denoise
    form.refineSteps = model.ranges.refine.steps.default
    form.refineCfg = model.ranges.refine.cfg.default
    form.refineDenoise = model.ranges.refine.denoise.default
    form.size = nearestSize(clampRange(form.size, model.ranges.width), next.size.values)
    form.batch = clamp(
      Math.round(form.batch),
      model.ranges.batch.min,
      model.ranges.batch.max,
    )
    if (resetLoras) form.loras = defaultLoras(next, model)

    const allowed = new Set(next.loras.filter((lora) => loraCompatible(lora, model)).map((lora) => lora.id))
    form.loras = form.loras.filter((lora) => allowed.has(lora.id)).slice(0, next.limits.maxLoras)

    const range = upscalerRangeFor(upscaler.value, model)
    if (range) form.upscalerValue = clampRange(form.upscalerValue, range)
  }

  function applyEnhanceDefaults(next: T2ICatalog): void {
    const defaults = next.defaults.enhance
    form.enhanceEnabled = defaults.enabled
    form.enhanceProvider = defaults.provider
    form.enhanceModel = defaults.model || ''
    form.fallbackToOriginal = defaults.fallbackToOriginal
    form.approvedPrompt = ''
    enhancePreview.value = null
  }

  function applySamplingDefaults(next: T2ICatalog): void {
    const model = selectedModel.value ?? next.models[0] ?? null
    if (!model) return
    form.steps = model.defaults.steps
    form.cfg = model.defaults.cfg
    form.sampler = model.defaults.sampler
    form.scheduler = model.defaults.scheduler
    form.denoise = model.defaults.denoise
    form.refineSteps = model.ranges.refine.steps.default
    form.refineCfg = model.ranges.refine.cfg.default
    form.refineDenoise = model.ranges.refine.denoise.default
  }

  function applyUpscaleDefaults(next: T2ICatalog): void {
    const defaults = next.defaults.upscaler
    const item =
      next.upscalers.find(
        (entry) => entry.id === defaults.id && entry.t2i && entry.present !== false,
      ) ??
      fallbackUpscaler(next, true) ??
      fallbackUpscaler(next)
    if (!item) {
      form.upscalerId = 'none'
      form.upscalerEnabled = false
      return
    }
    form.upscalerId = item.id
    const range = upscalerRangeFor(item, selectedModel.value)
    form.upscalerValue = range
      ? clampRange(defaults.value ?? range.default, range)
      : (defaults.value ?? 1536)
    form.upscalerEnabled =
      defaults.enabled && item.kind !== 'none' && item.present !== false
  }

  function applyDefaults(next: T2ICatalog): void {
    const defaults = next.defaults
    const model =
      next.models.find((item) => item.id === defaults.modelId) ??
      next.models.find((item) => item.id === next.selectedModelId) ??
      next.models[0] ??
      null
    form.modelId = model?.id ?? defaults.modelId
    form.ratio = next.ratios.some((ratio) => ratio.id === defaults.ratio)
      ? defaults.ratio
      : (next.ratios[0]?.id ?? defaults.ratio)
    form.size = nearestSize(defaults.size, next.size.values)
    form.batch = defaults.batch
    form.lockSeed = defaults.lockSeed
    form.seed = randomSeed()
    form.negativePrompt = defaults.negativePrompt
    form.autoTriggers = defaults.autoTriggers
    form.loras = defaultLoras(next, model)
    form.approvedPrompt = ''
    enhancePreview.value = null
    applyEnhanceDefaults(next)
    applyUpscaleDefaults(next)
    if (model) {
      form.modelId = model.id
      form.steps = model.defaults.steps
      form.cfg = model.defaults.cfg
      form.sampler = model.defaults.sampler
      form.scheduler = model.defaults.scheduler
      form.denoise = model.defaults.denoise
      form.refineSteps = model.ranges.refine.steps.default
      form.refineCfg = model.ranges.refine.cfg.default
      form.refineDenoise = model.ranges.refine.denoise.default
      form.batch = clamp(
        Math.round(form.batch),
        model.ranges.batch.min,
        model.ranges.batch.max,
      )
      form.size = nearestSize(clampRange(form.size, model.ranges.width), next.size.values)
    }
  }

  function reconcile(next: T2ICatalog, notify = true): boolean {
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
    if (!model) return changed

    if (!next.ratios.some((ratio) => ratio.id === form.ratio)) {
      form.ratio = next.ratios.some((ratio) => ratio.id === next.defaults.ratio)
        ? next.defaults.ratio
        : (next.ratios[0]?.id ?? form.ratio)
      mark()
    }

    if (!next.size.values.includes(form.size)) {
      form.size = nearestSize(form.size, next.size.values)
      mark()
    }
    const clampedSize = nearestSize(clampRange(form.size, model.ranges.width), next.size.values)
    if (clampedSize !== form.size) {
      form.size = clampedSize
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

    const sampling: Array<[keyof T2IFormState, T2IRange]> = [
      ['steps', model.ranges.steps],
      ['cfg', model.ranges.cfg],
      ['denoise', model.ranges.denoise],
      ['refineSteps', model.ranges.refine.steps],
      ['refineCfg', model.ranges.refine.cfg],
      ['refineDenoise', model.ranges.refine.denoise],
    ]
    for (const [key, range] of sampling) {
      const current = form[key] as number
      const adjusted = clampRange(current, range)
      if (adjusted !== current) {
        ;(form as unknown as Record<string, unknown>)[key] = adjusted
        mark()
      }
    }

    if (!model.samplers.some((sampler) => sampler.id === form.sampler)) {
      form.sampler = model.defaults.sampler
      mark()
    }
    if (!model.schedulers.some((scheduler) => scheduler.id === form.scheduler)) {
      form.scheduler = model.defaults.scheduler
      mark()
    }

    const compatible = next.loras.filter((lora) => loraCompatible(lora, model))
    const compatibleIds = new Set(compatible.map((lora) => lora.id))
    const normalizedLoras = form.loras
      .filter((entry) => compatibleIds.has(entry.id))
      .slice(0, next.limits.maxLoras)
      .map((entry) => {
        const range = compatible.find((lora) => lora.id === entry.id)?.strength
        if (!range || entry.strength == null) return entry
        const strength = clampRange(entry.strength, range)
        return strength === entry.strength ? entry : { ...entry, strength }
      })
    if (
      normalizedLoras.length !== form.loras.length ||
      normalizedLoras.some((entry, index) => entry !== form.loras[index])
    ) {
      form.loras = normalizedLoras
      mark()
    }

    let item = next.upscalers.find((entry) => entry.id === form.upscalerId && entry.t2i) ?? null
    if (!item) {
      item = fallbackUpscaler(next, true) ?? fallbackUpscaler(next)
      form.upscalerId = item?.id ?? 'none'
      mark()
    }
    if (!item || item.kind === 'none') {
      form.upscalerId = 'none'
      if (form.upscalerEnabled) {
        form.upscalerEnabled = false
        mark()
      }
    } else {
      if (item.present === false && form.upscalerEnabled) {
        form.upscalerEnabled = false
        mark()
      }
      const range = upscalerRangeFor(item, model)
      if (range) {
        const value = clampRange(form.upscalerValue, range)
        if (value !== form.upscalerValue) {
          form.upscalerValue = value
          mark()
        }
      }
    }

    if (form.enhanceProvider !== 'ollama' && form.enhanceProvider !== 'comfyui') {
      form.enhanceProvider = next.defaults.enhance.provider
      mark()
    }
    if (form.enhanceModel) {
      const selected = next.textModels.find(
        (entry) => entry.provider === form.enhanceProvider && entry.id === form.enhanceModel,
      )
      if (!selected || selected.present === false) {
        form.enhanceModel = ''
        mark()
      }
    }

    if (changed && notify) {
      ui.toast('Restored T2I settings were adjusted to the current pack ranges.', 'info', 5000)
    }
    return changed
  }

  function applyCatalog(next: T2ICatalog): void {
    const firstLoad = !catalogInitialized
    catalog.value = next
    catalogWarnings.value = next.warnings ?? []
    if (firstLoad) {
      if (restored) reconcile(next)
      else applyDefaults(next)
      catalogInitialized = true
    } else {
      reconcile(next)
    }
    loading.value = false
  }

  async function loadCatalog(): Promise<void> {
    catalogAbort?.abort()
    catalogAbort = new AbortController()
    if (!catalog.value) loading.value = true
    loadError.value = ''
    try {
      const next = await t2iApi.getCatalog(null, catalogAbort.signal)
      applyCatalog(next)
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

  function onModelChange(): void {
    const next = catalog.value
    if (!next) return
    applyModelDefaults(next)
    ui.toast(`Applied ${selectedModel.value?.shortLabel ?? 'model'} defaults.`, 'info')
  }

  function onProviderChange(): void {
    const first = enhanceModels.value.find((model) => model.present !== false)
    form.enhanceModel = first?.id ?? ''
  }

  function onUpscalerChange(): void {
    const item = upscaler.value
    if (!item) return
    if (item.kind === 'none' || item.present === false) {
      form.upscalerEnabled = false
    }
    const range = upscalerRangeFor(item, selectedModel.value)
    if (range) form.upscalerValue = clampRange(form.upscalerValue, range)
  }

  function setUpscalerEnabled(enabled: boolean): void {
    if (!enabled) {
      form.upscalerEnabled = false
      return
    }
    const next = catalog.value
    if (!next) return
    let item = upscaler.value
    if (!item || item.kind === 'none' || item.present === false) {
      item = fallbackUpscaler(next, true)
      if (!item) {
        form.upscalerEnabled = false
        ui.toast('No installed upscaler is available.', 'warn')
        return
      }
      form.upscalerId = item.id
      const range = upscalerRangeFor(item, selectedModel.value)
      if (range) form.upscalerValue = clampRange(form.upscalerValue, range)
    }
    form.upscalerEnabled = true
  }

  function setEnhanceEnabled(enabled: boolean): void {
    form.enhanceEnabled = enabled
    if (!enabled) cancelEnhancement()
  }

  function loraStrength(id: string): number | null {
    const selected = form.loras.find((lora) => lora.id === id)
    if (selected?.strength != null) return selected.strength
    const item = availableLoras.value.find((lora) => lora.id === id)
    return item?.strength.default ?? null
  }

  function isLoraOn(id: string): boolean {
    return form.loras.some((lora) => lora.id === id && lora.on)
  }

  function setLoraOn(id: string, on: boolean): void {
    const existing = form.loras.find((lora) => lora.id === id)
    if (existing) {
      existing.on = on
      return
    }
    if (!on) return
    const item = availableLoras.value.find((lora) => lora.id === id)
    form.loras.push({ id, strength: item?.strength.default ?? null, on: true })
  }

  function setLoraStrength(id: string, value: number): void {
    const item = availableLoras.value.find((lora) => lora.id === id)
    if (!item) return
    const strength = clampRange(value, item.strength)
    const existing = form.loras.find((lora) => lora.id === id)
    if (existing) existing.strength = strength
    else form.loras.push({ id, strength, on: true })
  }

  function resetPanel(panel: T2IPanel): void {
    const next = catalog.value
    if (!next) return
    switch (panel) {
      case 'prompt':
        // The page composer owns the main prompt and has its own clear action.
        // This panel only owns the negative prompt and the approved preview.
        form.negativePrompt = next.defaults.negativePrompt
        form.approvedPrompt = ''
        enhancePreview.value = null
        ui.toast('Prompt extras reset.', 'success')
        break
      case 'output': {
        const defaults = next.defaults
        form.modelId = defaults.modelId
        form.ratio = defaults.ratio
        form.size = nearestSize(defaults.size, next.size.values)
        form.batch = defaults.batch
        form.seed = randomSeed()
        form.lockSeed = defaults.lockSeed
        // Re-clamp dependent constraints for the default model without resetting
        // the sampling or LoRA panels, which have their own reset actions.
        reconcile(next, false)
        ui.toast('Output panel reset to pack defaults.', 'success')
        break
      }
      case 'loras':
        form.loras = defaultLoras(next, selectedModel.value)
        form.autoTriggers = next.defaults.autoTriggers
        ui.toast('LoRA panel reset.', 'success')
        break
      case 'enhance':
        applyEnhanceDefaults(next)
        ui.toast('Prompt enhancement panel reset.', 'success')
        break
      case 'sampling':
        applySamplingDefaults(next)
        ui.toast('Sampling panel reset.', 'success')
        break
      case 'upscale':
        applyUpscaleDefaults(next)
        ui.toast('Upscale panel reset.', 'success')
        break
      case 'all':
        applyDefaults(next)
        form.prompt = ''
        form.approvedPrompt = ''
        enhancePreview.value = null
        ui.toast('All T2I settings reset.', 'success')
        break
    }
    persistNow()
  }

  function buildRequest(): T2IJobRequest {
    const item = upscaler.value
    const wantsUpscale = item != null && item.kind !== 'none' && form.upscalerEnabled
    return {
      prompt: form.prompt.trim(),
      negativePrompt: form.negativePrompt.trim(),
      modelId: form.modelId,
      ratio: form.ratio,
      size: form.size,
      batch: form.batch,
      seed: form.lockSeed ? form.seed : undefined,
      lockSeed: form.lockSeed,
      loras: form.loras.map((lora, index) => ({
        id: lora.id,
        strength: lora.strength ?? undefined,
        on: lora.on,
        order: index,
      })),
      autoTriggers: form.autoTriggers,
      enhance: {
        enabled: form.enhanceEnabled,
        provider: form.enhanceProvider,
        model: form.enhanceEnabled && form.enhanceModel ? form.enhanceModel : undefined,
        fallbackToOriginal: form.fallbackToOriginal,
      },
      enhancedPrompt: form.enhanceEnabled ? form.approvedPrompt.trim() || undefined : undefined,
      advanced: {
        steps: form.steps,
        cfg: form.cfg,
        sampler: form.sampler,
        scheduler: form.scheduler,
        denoise: form.denoise,
        refine: {
          steps: form.refineSteps,
          cfg: form.refineCfg,
          denoise: form.refineDenoise,
        },
        upscaler: {
          id: item?.id ?? form.upscalerId,
          enabled: wantsUpscale,
          value: item?.kind === 'none' ? null : form.upscalerValue,
        },
      },
      tab: 'text-to-image',
    }
  }

  function errorText(err: unknown): string {
    if (err instanceof T2IApiError) {
      if (err.errors.length) return `${err.message} (${err.errors[0].message})`
      return err.message
    }
    if (err instanceof Error) return err.message
    return 'Something went wrong.'
  }

  function replaceJob(next: T2IJobRecord): void {
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
    // Preserve pollFailures here; the backoff needs the streak. Only an
    // explicit stop (terminal/404/delete) clears it.
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
      const next = await t2iApi.getJob(jobId)
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
      if (err instanceof T2IApiError && err.status === 404) {
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
      // Keep retrying at a capped interval. The backend job may still be
      // running, so do not stop tracking it or pretend it finished.
      schedulePoll(jobId, Math.min(15_000, pollDelay() * 2 ** Math.min(failures, 4)))
    }
  }

  async function loadJobs(): Promise<void> {
    jobsLoading.value = true
    jobsError.value = ''
    try {
      const list = await t2iApi.listJobs(JOB_PAGE_SIZE)
      jobSyncError.value = ''
      const remote = [...list].reverse()
      // A generate() can finish while this list request is in flight. Keep any
      // local running/queued job that the earlier snapshot did not include.
      const remoteIds = new Set(remote.map((job) => job.id))
      const pendingLocal = jobs.value.filter(
        (job) =>
          !remoteIds.has(job.id) && (job.status === 'queued' || job.status === 'running'),
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
    if (!catalog.value || busy.value || enhancing.value) return
    submitting.value = true
    actionError.value = ''
    warnings.value = []
    try {
      const request = buildRequest()
      if (!request.prompt) throw new Error('Write a prompt first.')
      const validation = await t2iApi.validate(request)
      warnings.value = validation.warnings ?? []
      const job = await t2iApi.createJob(request)
      jobs.value.push(job)
      markJobActive(job.id)
      form.approvedPrompt = ''
      enhancePreview.value = null
      persistNow()
      schedulePoll(job.id, 500)
      void genericJobs.syncFromBackend()
    } catch (err) {
      if (err instanceof T2IApiError) {
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
      const next = await t2iApi.cancelJob(jobId)
      replaceJob(next)
      if (next.status !== 'queued' && next.status !== 'running') releaseJob(jobId)
      schedulePoll(jobId, 400)
    } catch (err) {
      actionError.value = errorText(err)
    }
  }

  async function deleteJob(jobId: string, deleteAssets: boolean): Promise<T2IJobDeleteResult> {
    const result = await t2iApi.deleteJob(jobId, deleteAssets)
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

  function applyJobSettings(job: T2IJobRecord): void {
    const next = catalog.value
    const params: Partial<T2IJobParams> = job.params ?? {}
    form.prompt = job.prompt || params.basePrompt || ''
    form.negativePrompt = params.negativePrompt ?? form.negativePrompt
    form.modelId = params.modelId || job.modelId || form.modelId
    form.ratio = params.ratio ?? form.ratio
    form.size = params.size ?? form.size
    form.batch = params.batch ?? form.batch
    form.seed = params.seed ?? job.seed ?? form.seed
    form.lockSeed = params.lockSeed ?? true
    form.loras = (params.loras ?? []).map((lora) => ({
      id: lora.id,
      strength: lora.strength,
      on: true,
    }))
    form.autoTriggers = params.autoTriggers ?? form.autoTriggers
    form.enhanceEnabled = params.enhance?.enabled ?? false
    form.enhanceProvider = params.enhance?.provider ?? form.enhanceProvider
    form.enhanceModel = params.enhance?.model ?? ''
    form.fallbackToOriginal =
      params.enhance?.fallbackToOriginal ?? form.fallbackToOriginal
    form.approvedPrompt = ''
    form.steps = params.steps ?? form.steps
    form.cfg = params.cfg ?? form.cfg
    form.sampler = params.sampler ?? form.sampler
    form.scheduler = params.scheduler ?? form.scheduler
    form.denoise = params.denoise ?? form.denoise
    form.refineSteps = params.refine?.steps ?? form.refineSteps
    form.refineCfg = params.refine?.cfg ?? form.refineCfg
    form.refineDenoise = params.refine?.denoise ?? form.refineDenoise
    form.upscalerId = params.upscaler?.id || params.upscalerId || form.upscalerId
    form.upscalerEnabled = Boolean(params.upscaler?.enabled)
    form.upscalerValue =
      params.upscaler?.value ?? params.refine?.scale ?? form.upscalerValue
    enhancePreview.value = null
    if (next) reconcile(next, false)
    persistNow()
    ui.toast(`Reused prompt and settings from ${job.id}.`, 'success')
  }

  function useJobSeed(job: T2IJobRecord): void {
    form.seed = Number(job.params?.seed ?? job.seed ?? form.seed)
    form.lockSeed = true
    persistNow()
    ui.toast(`Seed ${form.seed} locked.`, 'success')
  }

  async function enhanceNow(): Promise<void> {
    if (!catalog.value || enhancing.value) return
    const prompt = form.prompt.trim()
    if (!prompt) {
      actionError.value = 'Write a prompt before enhancing it.'
      return
    }
    enhanceAbort?.abort()
    enhanceAbort = new AbortController()
    enhancing.value = true
    actionError.value = ''
    enhancePreview.value = null
    try {
      const next = await t2iApi.enhance(
        {
          prompt,
          provider: form.enhanceProvider,
          model: form.enhanceModel || undefined,
          maxLength: catalog.value.limits.promptMaxChars,
        },
        enhanceAbort.signal,
      )
      // The prompt may have changed (or enhancement may have been switched
      // off) while the provider was working; never show a stale rewrite.
      if (form.prompt.trim() !== prompt || !form.enhanceEnabled) return
      enhancePreview.value = next
      ui.toast(`Prompt enhanced with ${next.model}.`, 'success')
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      if (err instanceof Error && err.name === 'AbortError') return
      actionError.value = errorText(err)
    } finally {
      enhancing.value = false
    }
  }

  function useEnhancement(): void {
    if (!enhancePreview.value) return
    form.approvedPrompt = enhancePreview.value.prompt
    persistNow()
    ui.toast('Enhanced prompt approved for the next generation.', 'success')
  }

  function discardEnhancement(): void {
    enhancePreview.value = null
    form.approvedPrompt = ''
    persistNow()
  }

  function cancelEnhancement(): void {
    enhanceAbort?.abort()
    enhancing.value = false
  }

  return {
    // state
    form,
    catalog,
    loading,
    loadError,
    actionError,
    jobsError,
    jobSyncError,
    catalogWarnings,
    warnings,
    submitting,
    enhancing,
    enhancePreview,
    jobs,
    jobsLoading,
    lastSavedAt,
    storageError,
    // derived
    selectedModel,
    availableLoras,
    upscaler,
    upscalerRange,
    upscalerOn,
    upscalerLabel,
    refineActive,
    enhanceModels,
    comfyReady,
    providerReady,
    activeLoraCount,
    busy,
    canGenerate,
    canEnhance,
    activeJob,
    // lifecycle
    loadCatalog,
    loadJobs,
    flushPersist,
    errorText,
    // actions
    onModelChange,
    onProviderChange,
    onUpscalerChange,
    setUpscalerEnabled,
    setEnhanceEnabled,
    isLoraOn,
    loraStrength,
    setLoraOn,
    setLoraStrength,
    resetPanel,
    generate,
    cancelJob,
    deleteJob,
    applyJobSettings,
    useJobSeed,
    enhanceNow,
    useEnhancement,
    discardEnhancement,
    cancelEnhancement,
  }
})
