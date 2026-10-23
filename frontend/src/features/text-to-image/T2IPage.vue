<script setup lang="ts">
/**
 * T2I_main - route-ready page shell.
 *
 * This is deliberately a functional contract shell, not the final visual
 * layout. It loads the real catalog, validates, creates a job, polls it,
 * cancels it and shows results. The next session can replace the markup with
 * the app's AppButton/AppSelect/AppModal primitives while keeping this state
 * flow and the `api.ts` / `types.ts` boundary.
 */

import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { assetFileUrl, assetThumbUrl, T2IApiError, t2iApi } from './api'
import type {
  T2ICatalog,
  T2IEnhanceResponse,
  T2IJobRecord,
  T2IJobRequest,
  T2ILoraSelection,
  T2IProvider,
  T2ITextModel,
  T2IWarning,
} from './types'

const catalog = ref<T2ICatalog | null>(null)
const loading = ref(true)
const loadError = ref('')
const actionError = ref('')
const warnings = ref<T2IWarning[]>([])
const enhancing = ref(false)
const submitting = ref(false)
const job = ref<T2IJobRecord | null>(null)
const enhancePreview = ref<T2IEnhanceResponse | null>(null)
const approvedPrompt = ref('')
const pollTimer = ref<number | null>(null)
let pollFailures = 0
let loadController: AbortController | null = null
let enhanceController: AbortController | null = null

const form = reactive({
  prompt: '',
  negativePrompt: '',
  modelId: '',
  ratio: '1:1',
  size: 1024,
  batch: 1,
  seed: randomSeed(),
  lockSeed: false,
  loras: [] as T2ILoraSelection[],
  autoTriggers: true,
  enhanceEnabled: false,
  enhanceProvider: 'ollama' as T2IProvider,
  enhanceModel: '',
  fallbackToOriginal: false,
  steps: 12,
  cfg: 2.5,
  sampler: 'euler',
  scheduler: 'simple',
  denoise: 1,
  refineSteps: 6,
  refineCfg: 2,
  refineDenoise: 0.45,
  upscalerId: 'latent-refine',
  upscalerEnabled: true,
  upscalerValue: 1536,
})

const selectedModel = computed(() => {
  const all = catalog.value?.models ?? []
  return all.find((model) => model.id === form.modelId) ?? all[0] ?? null
})

const comfyReady = computed(() => catalog.value?.engine.ready === true)
const ratioOptions = computed(() => catalog.value?.ratios ?? [])
const sizeOptions = computed(() => catalog.value?.size.values ?? [])
const samplers = computed(() => catalog.value?.samplers ?? [])
const schedulers = computed(() => catalog.value?.schedulers ?? [])

const availableLoras = computed(() => {
  const all = catalog.value?.loras ?? []
  const model = selectedModel.value
  if (!model) return []
  return all.filter(
    (lora) =>
      lora.t2i &&
      (lora.compatibleModels.includes(model.id) || lora.base === model.base),
  )
})

const enhanceModels = computed(() =>
  (catalog.value?.textModels ?? []).filter((model) => model.provider === form.enhanceProvider),
)

const providerReady = computed(() => {
  if (!catalog.value) return false
  return form.enhanceProvider === 'ollama'
    ? catalog.value.engine.ollama.connected
    : catalog.value.engine.comfyui.connected
})

const upscaler = computed(
  () => catalog.value?.upscalers.find((item) => item.id === form.upscalerId) ?? null,
)

const upscalerRange = computed(() => {
  const item = upscaler.value
  if (!item) return null
  if (item.kind === 'latent') return selectedModel.value?.ranges.refine.scale ?? item.valueRange
  return item.valueRange
})

const refineActive = computed(() => upscaler.value?.kind === 'latent' && form.upscalerEnabled)
const busy = computed(
  () =>
    submitting.value ||
    job.value?.status === 'running' ||
    job.value?.status === 'queued',
)
const progress = computed(() => job.value?.progress ?? 0)
const resultIds = computed(() => job.value?.resultIds ?? [])
const canGenerate = computed(
  () =>
    Boolean(catalog.value) &&
    form.prompt.trim().length > 0 &&
    Boolean(selectedModel.value) &&
    comfyReady.value &&
    !busy.value,
)

function randomSeed(): number {
  const buffer = new Uint32Array(1)
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    crypto.getRandomValues(buffer)
    return buffer[0]
  }
  return Math.floor(Math.random() * 0x100000000)
}

function isAbort(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === 'AbortError') ||
    (err instanceof Error && err.name === 'AbortError')
  )
}

function errorText(err: unknown): string {
  if (err instanceof T2IApiError) {
    if (err.errors.length) {
      return err.errors
        .map((issue) => (issue.field ? `${issue.field}: ${issue.message}` : issue.message))
        .join(' · ')
    }
    return err.message
  }
  return err instanceof Error ? err.message : String(err)
}

function textModelValue(model: T2ITextModel): string {
  return model.provider === 'ollama' ? model.model || model.id : model.id
}

function applyCatalog(next: T2ICatalog): void {
  catalog.value = next
  warnings.value = next.warnings ?? []
  const defaults = next.defaults

  form.modelId = next.selectedModelId ?? defaults.modelId
  form.ratio = defaults.ratio
  form.size = defaults.size
  form.batch = defaults.batch
  form.lockSeed = defaults.lockSeed
  form.negativePrompt = defaults.negativePrompt
  form.autoTriggers = defaults.autoTriggers
  const unavailable = new Set(
    next.loras.filter((lora) => lora.present === false || !lora.available).map((lora) => lora.id),
  )
  form.loras = (defaults.loraChain ?? [])
    .filter((lora) => !unavailable.has(lora.id))
    .map((lora) => ({
      id: lora.id,
      strength: lora.strength,
      on: lora.on,
    }))
  form.enhanceEnabled = defaults.enhance?.enabled ?? defaults.enhanceEnabled
  form.enhanceProvider = defaults.enhance?.provider ?? 'ollama'
  form.enhanceModel = defaults.enhance?.model ?? ''
  form.fallbackToOriginal = defaults.enhance?.fallbackToOriginal ?? false
  form.upscalerId = defaults.upscaler.id
  form.upscalerEnabled = defaults.upscaler.enabled
  form.upscalerValue = Number(defaults.upscaler.value ?? defaults.refine?.scale ?? 1536)

  applyModelDefaults(next)
}

function applyModelDefaults(next: T2ICatalog): void {
  const model = next.models.find((item) => item.id === form.modelId) ?? next.models[0]
  if (!model) return
  form.modelId = model.id
  form.steps = Number(model.defaults.steps)
  form.cfg = Number(model.defaults.cfg)
  form.sampler = model.defaults.sampler
  form.scheduler = model.defaults.scheduler
  form.denoise = Number(model.defaults.denoise)
  form.refineSteps = Number(model.ranges.refine.steps.default)
  form.refineCfg = Number(model.ranges.refine.cfg.default)
  form.refineDenoise = Number(model.ranges.refine.denoise.default)

  const longMin = Math.min(model.ranges.width.min, model.ranges.height.min)
  const longMax = Math.max(model.ranges.width.max, model.ranges.height.max)
  if (form.size < longMin || form.size > longMax) {
    form.size = Number(model.ranges.width.default)
  }

  const compatible = new Set(
    next.loras
      .filter(
        (lora) =>
          lora.t2i &&
          lora.present !== false &&
          lora.available &&
          (lora.compatibleModels.includes(model.id) || lora.base === model.base),
      )
      .map((lora) => lora.id),
  )
  form.loras = form.loras.filter((lora) => compatible.has(lora.id))

  const current = next.upscalers.find((item) => item.id === form.upscalerId)
  if (current?.kind === 'latent') {
    form.upscalerValue = Number(model.ranges.refine.scale.default)
  }
}

async function loadCatalog(): Promise<void> {
  loading.value = true
  loadError.value = ''
  loadController?.abort()
  loadController = new AbortController()
  try {
    applyCatalog(await t2iApi.getCatalog(null, loadController.signal))
  } catch (err) {
    if (!isAbort(err)) loadError.value = errorText(err)
  } finally {
    loading.value = false
  }
}

async function reattachJob(): Promise<void> {
  try {
    const recent = await t2iApi.listJobs(20)
    const active = recent.find(
      (item) =>
        item.module === 'T2I_main' &&
        (item.status === 'running' || item.status === 'queued'),
    )
    if (!active) return
    job.value = active
    submitting.value = true
    schedulePoll(0)
  } catch {
    // Reattach is best-effort; the user can still start a new job.
  }
}

function resetFreeze(): void {
  if (!catalog.value) return
  applyCatalog(catalog.value)
  enhancePreview.value = null
  approvedPrompt.value = ''
  actionError.value = ''
}

function onModelChange(): void {
  if (catalog.value) applyModelDefaults(catalog.value)
}

function onProviderChange(): void {
  const first = enhanceModels.value[0]
  form.enhanceModel = first ? textModelValue(first) : ''
}

function onUpscalerChange(): void {
  const item = upscaler.value
  if (!item) return
  if (item.kind === 'none') {
    form.upscalerEnabled = false
    return
  }
  form.upscalerEnabled = true
  const range =
    item.kind === 'latent' ? selectedModel.value?.ranges.refine.scale : item.valueRange
  if (range) form.upscalerValue = Number(range.default)
}

function loraOn(id: string): boolean {
  return form.loras.some((lora) => lora.id === id && lora.on !== false)
}

function loraStrength(id: string): number {
  const selected = form.loras.find((lora) => lora.id === id)
  const meta = availableLoras.value.find((lora) => lora.id === id)
  return Number(selected?.strength ?? meta?.strength.default ?? 1)
}

function toggleLora(id: string, checked: boolean): void {
  if (!checked) {
    form.loras = form.loras.filter((lora) => lora.id !== id)
    return
  }
  if (form.loras.some((lora) => lora.id === id)) return
  const meta = availableLoras.value.find((lora) => lora.id === id)
  form.loras = [
    ...form.loras,
    { id, strength: Number(meta?.strength.default ?? 1), on: true },
  ]
}

function onLoraToggle(id: string, event: Event): void {
  toggleLora(id, (event.target as HTMLInputElement).checked)
}

function setLoraStrength(id: string, value: number): void {
  const selected = form.loras.find((lora) => lora.id === id)
  if (selected) selected.strength = value
}

function onLoraStrength(id: string, event: Event): void {
  setLoraStrength(id, Number((event.target as HTMLInputElement).value))
}

function buildRequest(): T2IJobRequest {
  const item = upscaler.value
  const upscalerEnabled = item?.kind === 'none' ? false : form.upscalerEnabled
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
      on: lora.on !== false,
      order: index,
    })),
    autoTriggers: form.autoTriggers,
    enhance: {
      enabled: form.enhanceEnabled,
      provider: form.enhanceProvider,
      model: form.enhanceEnabled && form.enhanceModel ? form.enhanceModel : undefined,
      fallbackToOriginal: form.fallbackToOriginal,
    },
    enhancedPrompt: form.enhanceEnabled ? approvedPrompt.value.trim() || undefined : undefined,
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
        id: form.upscalerId,
        enabled: upscalerEnabled,
        value: item?.kind === 'none' ? undefined : form.upscalerValue,
      },
    },
    tab: 'text-to-image',
  }
}

async function enhanceNow(): Promise<void> {
  const prompt = form.prompt.trim()
  if (!prompt) {
    actionError.value = 'Write a prompt before enhancing it.'
    return
  }
  enhanceController?.abort()
  enhanceController = new AbortController()
  enhancing.value = true
  actionError.value = ''
  try {
    enhancePreview.value = await t2iApi.enhance(
      {
        prompt,
        provider: form.enhanceProvider,
        model: form.enhanceModel || undefined,
      },
      enhanceController.signal,
    )
    // A new preview invalidates the previous approval; the user must approve
    // the text they are about to send.
    approvedPrompt.value = ''
  } catch (err) {
    if (!isAbort(err)) actionError.value = errorText(err)
  } finally {
    enhancing.value = false
  }
}

function useEnhancement(): void {
  if (enhancePreview.value) approvedPrompt.value = enhancePreview.value.prompt
}

function discardEnhancement(): void {
  enhancePreview.value = null
  approvedPrompt.value = ''
}

function cancelEnhancement(): void {
  enhanceController?.abort()
  enhancing.value = false
}

function clearPollTimer(): void {
  if (pollTimer.value !== null) {
    window.clearTimeout(pollTimer.value)
    pollTimer.value = null
  }
}

function schedulePoll(delay = 900): void {
  clearPollTimer()
  pollTimer.value = window.setTimeout(fetchJob, delay)
}

async function fetchJob(): Promise<void> {
  const current = job.value
  if (!current) return
  try {
    const next = await t2iApi.getJob(current.id)
    job.value = next
    pollFailures = 0
    if (next.params?.warnings?.length) warnings.value = next.params.warnings
    if (next.status === 'running' || next.status === 'queued') {
      schedulePoll()
    } else {
      submitting.value = false
    }
  } catch (err) {
    pollFailures += 1
    if (pollFailures >= 5) {
      actionError.value = errorText(err)
      submitting.value = false
      return
    }
    schedulePoll(1500)
  }
}

async function generate(): Promise<void> {
  if (!canGenerate.value) return
  actionError.value = ''
  warnings.value = []
  enhancePreview.value = null
  clearPollTimer()
  pollFailures = 0
  const payload = buildRequest()
  submitting.value = true
  try {
    // Validate first so a bad value is reported against its field before a job
    // record exists. The actual job request is sent unchanged; the backend
    // normalizes the seed/size again.
    const validation = await t2iApi.validate(payload)
    warnings.value = validation.warnings
    job.value = await t2iApi.createJob(payload)
    approvedPrompt.value = ''
    schedulePoll(0)
  } catch (err) {
    if (err instanceof T2IApiError) warnings.value = err.warnings
    actionError.value = errorText(err)
    submitting.value = false
  }
}

async function cancelJob(): Promise<void> {
  if (!job.value) return
  try {
    job.value = await t2iApi.cancelJob(job.value.id)
    if (job.value.status === 'running' || job.value.status === 'queued') {
      schedulePoll(500)
    } else {
      submitting.value = false
    }
  } catch (err) {
    actionError.value = errorText(err)
  }
}

function stageDot(status: string): string {
  const classes: Record<string, string> = {
    pending: 'bg-border',
    running: 'bg-warn',
    done: 'bg-success',
    skipped: 'bg-muted',
    error: 'bg-danger',
  }
  return classes[status] ?? 'bg-border'
}

function statusLabel(status: T2IJobRecord['status']): string {
  if (status === 'done') return 'Done'
  if (status === 'error') return 'Failed'
  if (status === 'running') return 'Generating'
  return 'Queued'
}

async function loadPage(): Promise<void> {
  await loadCatalog()
  if (!loadError.value && catalog.value) await reattachJob()
}

onMounted(loadPage)

onBeforeUnmount(() => {
  clearPollTimer()
  loadController?.abort()
  enhanceController?.abort()
})
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-bg text-text">
    <header class="flex flex-wrap items-center justify-between gap-4 border-b border-border px-6 py-4">
      <div>
        <p class="text-[11px] font-semibold uppercase tracking-[0.2em] text-accent">T2I_main</p>
        <h1 class="text-xl font-semibold">Text &rarr; Image</h1>
        <p class="mt-0.5 text-xs text-muted">Strict Krea 2 Turbo pipeline &middot; Freeze v8</p>
      </div>
      <div class="flex items-center gap-3 text-xs">
        <span class="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5">
          <span
            class="h-2 w-2 rounded-full"
            :class="comfyReady ? 'bg-success' : 'bg-danger'"
          />
          {{ comfyReady ? 'ComfyUI ready' : 'ComfyUI offline' }}
        </span>
        <span
          v-if="catalog"
          class="rounded-full border border-border bg-surface px-3 py-1.5 text-muted"
        >
          {{ selectedModel?.shortLabel ?? 'No model' }}
        </span>
      </div>
    </header>

    <div v-if="loading" class="flex flex-1 items-center justify-center text-sm text-muted">
      Loading T2I catalog...
    </div>

    <div v-else-if="loadError" class="m-6 rounded-xl border border-danger/40 bg-surface p-5">
      <p class="font-semibold text-danger">Could not load the T2I catalog</p>
      <p class="mt-1 text-sm text-muted">{{ loadError }}</p>
      <button
        class="mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-contrast"
        @click="loadCatalog"
      >
        Retry
      </button>
    </div>

    <div
      v-else-if="catalog"
      class="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[minmax(0,1fr)_380px]"
    >
      <main class="min-h-0 overflow-y-auto px-6 py-5">
        <div
          v-if="!comfyReady"
          class="mb-5 rounded-xl border border-warn/40 bg-warn/10 px-4 py-3 text-sm"
        >
          ComfyUI is offline{{ catalog.engine.comfyui.url ? ` at ${catalog.engine.comfyui.url}` : '' }}.
          Start it to enable Generate.
        </div>

        <section class="rounded-2xl border border-border bg-surface p-5">
          <div class="flex items-center justify-between gap-3">
            <h2 class="text-sm font-semibold">Prompt</h2>
            <span class="text-xs text-muted">
              {{ form.prompt.length }} / {{ catalog.limits.promptMaxChars }}
            </span>
          </div>
          <textarea
            v-model="form.prompt"
            rows="5"
            class="mt-3 w-full resize-y rounded-xl border border-border bg-bg px-3 py-2.5 text-sm outline-none focus:border-accent"
            placeholder="Describe the image. Strict T2I only: no reference images, edits or identity inputs."
            @keydown.ctrl.enter.prevent="generate"
          />
          <label class="mt-3 block text-xs font-medium text-muted">
            Negative prompt
            <textarea
              v-model="form.negativePrompt"
              rows="2"
              class="mt-1 w-full resize-y rounded-xl border border-border bg-bg px-3 py-2 text-sm text-text outline-none focus:border-accent"
              placeholder="Optional things to avoid"
            />
          </label>

          <div class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <label class="block text-xs font-medium text-muted">
              Model
              <select
                v-model="form.modelId"
                class="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text"
                @change="onModelChange"
              >
                <option
                  v-for="model in catalog.models"
                  :key="model.id"
                  :value="model.id"
                  :disabled="model.ready === false"
                >
                  {{ model.label }}{{ model.present === false ? ' (missing)' : '' }}
                </option>
              </select>
            </label>
            <label class="block text-xs font-medium text-muted">
              Ratio
              <select
                v-model="form.ratio"
                class="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text"
              >
                <option v-for="ratio in ratioOptions" :key="ratio.id" :value="ratio.id">
                  {{ ratio.label }}
                </option>
              </select>
            </label>
            <label class="block text-xs font-medium text-muted">
              Long side
              <select
                v-model.number="form.size"
                class="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text"
              >
                <option v-for="value in sizeOptions" :key="value" :value="value">
                  {{ value }} px
                </option>
              </select>
            </label>
            <label class="block text-xs font-medium text-muted">
              Batch
              <input
                v-model.number="form.batch"
                type="number"
                class="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text"
                :min="selectedModel?.ranges.batch.min ?? 1"
                :max="selectedModel?.ranges.batch.max ?? 4"
                :step="selectedModel?.ranges.batch.step ?? 1"
              />
            </label>
          </div>

          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <label class="block text-xs font-medium text-muted">
              Seed
              <div class="mt-1 flex gap-2">
                <input
                  v-model.number="form.seed"
                  type="number"
                  class="min-w-0 flex-1 rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text disabled:opacity-50"
                  :disabled="!form.lockSeed"
                  min="0"
                  max="4294967295"
                  step="1"
                />
                <button
                  class="rounded-lg border border-border px-3 py-2 text-xs text-muted hover:text-text"
                  title="Generate a new displayed seed"
                  @click="form.seed = randomSeed()"
                >
                  Dice
                </button>
              </div>
            </label>
            <label class="flex items-end gap-2 text-xs font-medium text-muted">
              <input v-model="form.lockSeed" type="checkbox" class="mb-2.5 h-4 w-4 accent-accent" />
              <span class="mb-2">Lock seed for this request</span>
            </label>
          </div>
        </section>

        <section class="mt-4 rounded-2xl border border-border bg-surface p-5">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 class="text-sm font-semibold">LoRA chain</h2>
              <p class="mt-0.5 text-xs text-muted">
                {{ form.loras.length }} selected &middot; order is kept as listed
              </p>
            </div>
            <label class="flex items-center gap-2 text-xs text-muted">
              <input v-model="form.autoTriggers" type="checkbox" class="h-4 w-4 accent-accent" />
              Auto-inject trigger words
            </label>
          </div>

          <div class="mt-3 space-y-2">
            <div
              v-for="lora in availableLoras"
              :key="lora.id"
              class="rounded-xl border border-border px-3 py-2.5"
              :class="lora.present === false ? 'opacity-60' : ''"
            >
              <div class="flex flex-wrap items-center gap-2">
                <input
                  type="checkbox"
                  class="h-4 w-4 accent-accent"
                  :checked="loraOn(lora.id)"
                  :disabled="lora.present === false || !lora.available"
                  @change="onLoraToggle(lora.id, $event)"
                />
                <span class="text-sm font-medium">{{ lora.label }}</span>
                <span
                  v-if="lora.present === false"
                  class="rounded-full bg-danger/15 px-2 py-0.5 text-[10px] text-danger"
                >
                  missing
                </span>
                <span
                  v-else-if="lora.present === null"
                  class="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] text-muted"
                >
                  presence unknown
                </span>
                <span
                  v-if="!lora.tested"
                  class="rounded-full bg-warn/15 px-2 py-0.5 text-[10px] text-warn"
                >
                  untested
                </span>
                <span class="ml-auto text-[11px] text-muted">
                  {{ lora.strength.recommendedMin }}-{{ lora.strength.recommendedMax }}
                  recommended
                </span>
              </div>
              <div v-if="loraOn(lora.id)" class="mt-2 flex flex-wrap items-center gap-3">
                <input
                  type="range"
                  class="min-w-40 flex-1 accent-accent"
                  :min="lora.strength.min"
                  :max="lora.strength.max"
                  :step="lora.strength.step"
                  :value="loraStrength(lora.id)"
                  @input="onLoraStrength(lora.id, $event)"
                />
                <input
                  type="number"
                  class="w-20 rounded-lg border border-border bg-bg px-2 py-1 text-xs text-text"
                  :min="lora.strength.min"
                  :max="lora.strength.max"
                  :step="lora.strength.step"
                  :value="loraStrength(lora.id)"
                  @input="onLoraStrength(lora.id, $event)"
                />
              </div>
              <div v-if="lora.triggers.length" class="mt-1.5 flex flex-wrap gap-1">
                <span
                  v-for="trigger in lora.triggers"
                  :key="trigger"
                  class="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted"
                >
                  {{ trigger }}
                </span>
              </div>
            </div>
          </div>
        </section>

        <section class="mt-4 rounded-2xl border border-border bg-surface p-5">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 class="text-sm font-semibold">Prompt enhancement</h2>
              <p class="mt-0.5 text-xs text-muted">
                Preview and approve, or let the job run it automatically.
              </p>
            </div>
            <label class="flex items-center gap-2 text-xs text-muted">
              <input v-model="form.enhanceEnabled" type="checkbox" class="h-4 w-4 accent-accent" />
              Improve prompt
            </label>
          </div>

          <div v-if="form.enhanceEnabled" class="mt-3 grid gap-3 sm:grid-cols-2">
            <label class="block text-xs font-medium text-muted">
              Provider
              <select
                v-model="form.enhanceProvider"
                class="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text"
                @change="onProviderChange"
              >
                <option value="ollama">Ollama (preferred)</option>
                <option value="comfyui">ComfyUI TextGenerate</option>
              </select>
              <span v-if="!providerReady" class="mt-1 block text-[11px] text-warn">
                {{ form.enhanceProvider === 'ollama' ? 'Ollama is offline.' : 'ComfyUI is offline.' }}
              </span>
            </label>
            <label class="block text-xs font-medium text-muted">
              Model
              <select
                v-model="form.enhanceModel"
                class="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text"
              >
                <option value="">Auto (best installed)</option>
                <option
                  v-for="model in enhanceModels"
                  :key="model.id"
                  :value="textModelValue(model)"
                  :disabled="model.present === false"
                >
                  {{ model.label }}{{ model.present === false ? ' (missing)' : '' }}
                </option>
              </select>
            </label>
          </div>

          <div v-if="form.enhanceEnabled" class="mt-3 flex flex-wrap items-center gap-2">
            <button
              class="rounded-lg border border-accent/50 bg-accent-soft px-3 py-2 text-xs font-semibold text-accent disabled:opacity-50"
              :disabled="enhancing || !form.prompt.trim() || !providerReady"
              @click="enhanceNow"
            >
              {{ enhancing ? 'Enhancing...' : 'Preview enhancement' }}
            </button>
            <button
              v-if="enhancing"
              class="rounded-lg border border-border px-3 py-2 text-xs text-muted"
              @click="cancelEnhancement"
            >
              Cancel
            </button>
            <label class="ml-auto flex items-center gap-2 text-xs text-muted">
              <input
                v-model="form.fallbackToOriginal"
                type="checkbox"
                class="h-4 w-4 accent-accent"
              />
              Fall back to original on failure
            </label>
          </div>

          <div
            v-if="form.enhanceEnabled && enhancePreview"
            class="mt-3 rounded-xl border border-accent/40 bg-accent-soft/40 p-3"
          >
            <p class="text-[11px] font-semibold uppercase tracking-wide text-accent">
              {{ enhancePreview.provider }} / {{ enhancePreview.model }}
            </p>
            <p class="mt-2 whitespace-pre-wrap text-sm">{{ enhancePreview.prompt }}</p>
            <div class="mt-3 flex flex-wrap gap-2">
              <button
                class="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-accent-contrast"
                @click="useEnhancement"
              >
                Use this prompt
              </button>
              <button
                class="rounded-lg border border-border px-3 py-1.5 text-xs text-muted"
                @click="enhanceNow"
              >
                Regenerate
              </button>
              <button
                class="rounded-lg border border-border px-3 py-1.5 text-xs text-muted"
                @click="discardEnhancement"
              >
                Discard
              </button>
            </div>
          </div>

          <div v-if="form.enhanceEnabled && approvedPrompt" class="mt-3">
            <div class="flex items-center justify-between gap-2">
              <p class="text-[11px] font-semibold uppercase tracking-wide text-muted">
                Approved enhanced prompt
              </p>
              <button class="text-[11px] text-danger" @click="approvedPrompt = ''">Clear</button>
            </div>
            <textarea
              v-model="approvedPrompt"
              rows="3"
              class="mt-1 w-full resize-y rounded-xl border border-border bg-bg px-3 py-2 text-sm"
            />
          </div>
        </section>

        <section class="mt-4 rounded-2xl border border-border bg-surface p-5">
          <details>
            <summary class="cursor-pointer text-sm font-semibold">Advanced sampling &amp; upscale</summary>
            <div class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              <label class="block text-xs font-medium text-muted">
                Steps
                <input
                  v-model.number="form.steps"
                  type="number"
                  class="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text"
                  :min="selectedModel?.ranges.steps.min"
                  :max="selectedModel?.ranges.steps.max"
                  :step="selectedModel?.ranges.steps.step"
                />
              </label>
              <label class="block text-xs font-medium text-muted">
                CFG
                <input
                  v-model.number="form.cfg"
                  type="number"
                  class="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text"
                  :min="selectedModel?.ranges.cfg.min"
                  :max="selectedModel?.ranges.cfg.max"
                  :step="selectedModel?.ranges.cfg.step"
                />
              </label>
              <label class="block text-xs font-medium text-muted">
                Base denoise
                <input
                  v-model.number="form.denoise"
                  type="number"
                  class="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text"
                  :min="selectedModel?.ranges.denoise.min"
                  :max="selectedModel?.ranges.denoise.max"
                  :step="selectedModel?.ranges.denoise.step"
                />
              </label>
              <label class="block text-xs font-medium text-muted">
                Sampler
                <select
                  v-model="form.sampler"
                  class="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text"
                >
                  <option v-for="sampler in samplers" :key="sampler.id" :value="sampler.id">
                    {{ sampler.label }}
                  </option>
                </select>
              </label>
              <label class="block text-xs font-medium text-muted">
                Scheduler
                <select
                  v-model="form.scheduler"
                  class="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text"
                >
                  <option v-for="scheduler in schedulers" :key="scheduler.id" :value="scheduler.id">
                    {{ scheduler.label }}
                  </option>
                </select>
              </label>
              <label class="block text-xs font-medium text-muted">
                Upscale path
                <select
                  v-model="form.upscalerId"
                  class="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text"
                  @change="onUpscalerChange"
                >
                  <option
                    v-for="item in catalog.upscalers"
                    :key="item.id"
                    :value="item.id"
                    :disabled="item.present === false"
                  >
                    {{ item.label }}{{ item.present === false ? ' (missing)' : '' }}
                  </option>
                </select>
              </label>
            </div>

            <div v-if="upscalerRange && upscaler?.kind !== 'none'" class="mt-4">
              <div class="flex items-center justify-between text-xs text-muted">
                <span>{{ upscalerRange.label }} (long side)</span>
                <span class="font-semibold text-text">{{ form.upscalerValue }} px</span>
              </div>
              <input
                v-model.number="form.upscalerValue"
                type="range"
                class="mt-1 w-full accent-accent"
                :min="upscalerRange.min"
                :max="upscalerRange.max"
                :step="upscalerRange.step"
              />
            </div>

            <div v-if="refineActive" class="mt-4 grid gap-3 sm:grid-cols-3">
              <label class="block text-xs font-medium text-muted">
                Refine steps
                <input
                  v-model.number="form.refineSteps"
                  type="number"
                  class="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text"
                  :min="selectedModel?.ranges.refine.steps.min"
                  :max="selectedModel?.ranges.refine.steps.max"
                  :step="selectedModel?.ranges.refine.steps.step"
                />
              </label>
              <label class="block text-xs font-medium text-muted">
                Refine CFG
                <input
                  v-model.number="form.refineCfg"
                  type="number"
                  class="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text"
                  :min="selectedModel?.ranges.refine.cfg.min"
                  :max="selectedModel?.ranges.refine.cfg.max"
                  :step="selectedModel?.ranges.refine.cfg.step"
                />
              </label>
              <label class="block text-xs font-medium text-muted">
                Refine denoise
                <input
                  v-model.number="form.refineDenoise"
                  type="number"
                  class="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text"
                  :min="selectedModel?.ranges.refine.denoise.min"
                  :max="selectedModel?.ranges.refine.denoise.max"
                  :step="selectedModel?.ranges.refine.denoise.step"
                />
              </label>
            </div>
            <div class="mt-4 flex justify-end">
              <button
                class="rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:text-text"
                @click="resetFreeze"
              >
                Reset to Freeze v8
              </button>
            </div>
          </details>
        </section>
      </main>

      <aside class="min-h-0 overflow-y-auto border-t border-border bg-surface-2/40 px-5 py-5 lg:border-l lg:border-t-0">
        <div class="sticky top-0 space-y-4">
          <div v-if="actionError" class="rounded-xl border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
            {{ actionError }}
          </div>

          <div v-if="warnings.length" class="rounded-xl border border-warn/40 bg-warn/10 p-3">
            <p class="text-xs font-semibold uppercase tracking-wide text-warn">Warnings</p>
            <ul class="mt-2 space-y-1">
              <li v-for="(warning, index) in warnings" :key="`${warning.code}-${index}`" class="text-xs text-muted">
                {{ warning.message }}
              </li>
            </ul>
          </div>

          <button
            class="w-full rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-accent-contrast disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="!canGenerate"
            @click="generate"
          >
            {{ submitting && !job ? 'Starting...' : busy ? 'Generating...' : 'Generate image' }}
          </button>
          <button
            v-if="job && (job.status === 'running' || job.status === 'queued')"
            class="w-full rounded-xl border border-border px-4 py-2.5 text-sm text-muted hover:text-text"
            @click="cancelJob"
          >
            Cancel job
          </button>
          <p v-if="!comfyReady" class="text-center text-xs text-muted">
            Generate is disabled until ComfyUI is reachable.
          </p>

          <div v-if="job" class="rounded-2xl border border-border bg-surface p-4">
            <div class="flex items-center justify-between gap-2">
              <div>
                <p class="text-sm font-semibold">{{ statusLabel(job.status) }}</p>
                <p class="text-[11px] text-muted">{{ job.id }}</p>
              </div>
              <span class="text-xs text-muted">{{ progress }}%</span>
            </div>
            <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-2">
              <div
                class="h-full rounded-full bg-accent transition-all"
                :style="{ width: `${progress}%` }"
              />
            </div>

            <div class="mt-3 space-y-2">
              <div v-for="stage in job.stages" :key="stage.id" class="flex gap-2">
                <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full" :class="stageDot(stage.status)" />
                <div class="min-w-0">
                  <p class="text-xs font-medium">
                    {{ stage.label }}
                    <span class="font-normal text-muted">· {{ stage.status }}</span>
                  </p>
                  <p v-if="stage.detail" class="truncate text-[11px] text-muted" :title="stage.detail">
                    {{ stage.detail }}
                  </p>
                </div>
              </div>
            </div>

            <div v-if="job.error" class="mt-3 rounded-lg border border-danger/30 bg-danger/10 p-2.5 text-xs text-danger">
              {{ job.error }}
            </div>

            <div class="mt-3 grid grid-cols-2 gap-2 text-[11px] text-muted">
              <span>Seed</span>
              <span class="text-right text-text">{{ job.params?.seed ?? job.seed }}</span>
              <span>Output</span>
              <span class="text-right text-text">
                {{ job.params?.finalWidth ?? job.params?.width }} ×
                {{ job.params?.finalHeight ?? job.params?.height }}
              </span>
              <span>LoRAs</span>
              <span class="text-right text-text">{{ job.params?.loras?.length ?? 0 }}</span>
            </div>

            <div v-if="resultIds.length" class="mt-4 grid grid-cols-2 gap-2">
              <a
                v-for="assetId in resultIds"
                :key="assetId"
                :href="assetFileUrl(assetId)"
                target="_blank"
                rel="noreferrer"
                class="overflow-hidden rounded-lg border border-border"
              >
                <img
                  :src="assetThumbUrl(assetId)"
                  :alt="`Result ${assetId}`"
                  class="aspect-square w-full object-cover"
                  loading="lazy"
                />
              </a>
            </div>
          </div>

          <p class="text-center text-[10px] leading-relaxed text-muted">
            Strict Text &rarr; Image. No identity, reference-image, edit or face-swap inputs.
          </p>
        </div>
      </aside>
    </div>
  </div>
</template>
