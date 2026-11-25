<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ChevronDown,
  Dices,
  ImagePlus,
  RotateCcw,
  Sparkles,
  Trash2,
  TriangleAlert,
  X,
} from '@lucide/vue'
import { useI2IStore } from './store'
import AppButton from '@/components/ui/AppButton.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppSlider from '@/components/ui/AppSlider.vue'
import AppSwitch from '@/components/ui/AppSwitch.vue'

const emit = defineEmits<{ (e: 'close'): void }>()
const store = useI2IStore()
const fileInput = ref<HTMLInputElement | null>(null)
const replaceIndex = ref(-1)

const catalog = computed(() => store.catalog)
const model = computed(() => store.selectedModel)

const modelOptions = computed(() =>
  (catalog.value?.models ?? []).map((item) => {
    const tags: string[] = []
    if (item.nsfw) tags.push('NSFW')
    if (item.present === false) tags.push('missing')
    return {
      value: item.id,
      label: tags.length ? `${item.shortLabel} (${tags.join(', ')})` : item.shortLabel,
      disabled: item.present === false,
    }
  }),
)

const resolutionOptions = computed(() =>
  (catalog.value?.resolutions ?? []).map((item) => ({
    value: String(item.value),
    label: item.label,
  })),
)

const samplerOptions = computed(() =>
  (catalog.value?.samplers ?? []).map((item) => ({ value: item.id, label: item.label })),
)

const cacheDeviceOptions = computed(() =>
  (catalog.value?.cacheDevices ?? []).map((value) => ({ value, label: value })),
)

const cacheDtypeOptions = computed(() =>
  (catalog.value?.cacheDtypes ?? []).map((value) => ({ value, label: value })),
)

const acceptTypes = computed(() =>
  (catalog.value?.source.mimeTypes ?? ['image/png', 'image/jpeg', 'image/webp']).join(','),
)

const targetLabel = computed(() => {
  const dims = store.dimensions
  return dims ? `${dims.width} × ${dims.height} px` : 'choose a reference'
})

const denoiseRange = computed(() => model.value?.ranges.denoise ?? null)
const stepsRange = computed(() => model.value?.ranges.steps ?? null)
const cfgRange = computed(() => model.value?.ranges.cfg ?? null)
const batchRange = computed(() => model.value?.ranges.batch ?? null)
const sourceReady = computed(() => store.hasSource)
const fullPath = computed(() => store.form.denoise >= 0.999)

function setModel(value: string): void {
  store.form.modelId = value
  store.onModelChange()
}

function setResolution(value: string): void {
  store.setResolution(Number(value))
}

function openFilePicker(index = -1): void {
  replaceIndex.value = index
  fileInput.value?.click()
}

async function onFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  const index = replaceIndex.value
  input.value = ''
  replaceIndex.value = -1
  if (!files.length) return
  if (index >= 0) await store.replaceSourceFile(index, files[0])
  else await store.selectSourceFiles(files)
}

function reset(panel: 'source' | 'output' | 'sampling' | 'prompt' | 'advanced'): void {
  store.resetPanel(panel)
}

function resetAll(): void {
  if (
    window.confirm(
      'Reset every Image -> Image setting? This also clears the prompt, source image and negative prompt.',
    )
  ) {
    store.resetPanel('all')
  }
}
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-surface">
    <header class="flex shrink-0 items-start justify-between gap-3 border-b border-border px-4 py-3">
      <div class="min-w-0">
        <p class="text-sm font-semibold">Edit settings</p>
        <p class="mt-0.5 text-[11px] leading-snug text-muted">
          Autosaved in this browser. The source image is saved separately.
        </p>
      </div>
      <button
        type="button"
        class="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-text"
        title="Close settings"
        aria-label="Close settings"
        @click="emit('close')"
      >
        <X class="h-4 w-4" />
      </button>
    </header>

    <div v-if="!catalog" class="flex flex-1 items-center justify-center p-6 text-center text-xs text-muted">
      Loading the pack catalog...
    </div>

    <div v-else class="min-h-0 flex-1 space-y-3 overflow-y-auto bg-bg/25 p-3">
      <input
        ref="fileInput"
        type="file"
        class="hidden"
        :accept="acceptTypes"
        @change="onFile"
      />

      <!-- Source ----------------------------------------------------------->
      <details
        id="i2i-panel-source"
        open
        class="group overflow-hidden rounded-xl border border-l-2 border-border border-l-rose bg-surface shadow-sm open:ring-1 open:ring-accent/20"
      >
        <summary
          class="flex cursor-pointer list-none items-center gap-2 border-b border-border/80 bg-surface-2/75 px-3.5 py-2.5 transition-colors hover:bg-surface-2 [&::-webkit-details-marker]:hidden"
        >
          <span class="h-2 w-2 shrink-0 rounded-full bg-rose" />
          <span class="text-xs font-semibold">References</span>
          <span class="truncate text-[10px] text-muted">{{ store.latestSourceLabel }}</span>
          <button
            type="button"
            class="ml-auto flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface hover:text-text"
            title="Clear the reference images"
            aria-label="Clear the reference images"
            @click.prevent.stop="reset('source')"
          >
            <RotateCcw class="h-3.5 w-3.5" />
          </button>
          <ChevronDown class="h-3.5 w-3.5 shrink-0 text-muted transition-transform group-open:rotate-180" />
        </summary>

        <div class="space-y-3 bg-surface px-3.5 py-3">
          <div v-if="sourceReady" class="space-y-2">
            <div
              v-for="(item, index) in store.sources"
              :key="`${index}-${item.name}-${item.dataUrl.length}`"
              class="flex items-center gap-2 rounded-xl border border-border bg-surface-2/40 p-2"
            >
              <img
                :src="item.dataUrl"
                :alt="`Image ${index + 1}`"
                class="h-16 w-16 shrink-0 rounded-lg border border-border object-cover"
              />
              <div class="min-w-0 flex-1">
                <p class="text-[10px] font-semibold uppercase tracking-wide text-accent">
                  Image {{ index + 1 }}
                </p>
                <p class="truncate text-[11px] font-medium">{{ item.name }}</p>
                <p class="text-[10px] text-muted">
                  {{ item.width }} × {{ item.height }} px
                  <span v-if="index === 0"> · → {{ targetLabel }}</span>
                </p>
              </div>
              <div class="flex shrink-0 flex-col gap-1">
                <button
                  type="button"
                  class="inline-flex cursor-pointer items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium text-muted transition-colors hover:bg-surface hover:text-text"
                  :title="`Replace Image ${index + 1}`"
                  @click="openFilePicker(index)"
                >
                  <ImagePlus class="h-3 w-3" />
                  Replace
                </button>
                <button
                  type="button"
                  class="inline-flex cursor-pointer items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium text-muted transition-colors hover:bg-danger/10 hover:text-danger"
                  :title="`Remove Image ${index + 1}`"
                  @click="store.removeSource(index)"
                >
                  <Trash2 class="h-3 w-3" />
                  Remove
                </button>
              </div>
            </div>

            <p
              class="flex items-start gap-1.5 text-[10px] leading-snug"
              :class="store.sourceTooLargeForStorage ? 'text-warn' : 'text-muted'"
            >
              <TriangleAlert v-if="store.sourceTooLargeForStorage" class="mt-0.5 h-3 w-3 shrink-0" />
              <span v-if="store.sourceTooLargeForStorage">{{ store.sourceNotice }}</span>
              <span v-else-if="store.sourcePersisted">Saved in this browser for the next reload.</span>
              <span v-else>The references are in memory for this session.</span>
            </p>
          </div>
          <p v-else class="text-[11px] leading-snug text-muted">
            No reference images yet. Upload one to {{ store.maxSources }} in the composer, or
            choose files here.
          </p>

          <div class="flex flex-wrap gap-2">
            <AppButton
              size="sm"
              variant="soft"
              :disabled="store.sourceBusy || !store.canAddSource"
              @click="openFilePicker()"
            >
              <ImagePlus class="h-3.5 w-3.5" />
              {{ sourceReady ? 'Add image' : 'Choose images' }}
            </AppButton>
            <AppButton v-if="sourceReady" size="sm" variant="ghost" @click="store.clearSource">
              <Trash2 class="h-3.5 w-3.5" />
              Remove all
            </AppButton>
          </div>

          <p class="text-[10px] leading-snug text-muted">
            Refer to the references as <span class="font-medium text-text">&lt;image1&gt;</span>,
            <span class="font-medium text-text">&lt;image2&gt;</span> and
            <span class="font-medium text-text">&lt;image3&gt;</span> in the prompt; ComfyUI shows
            them as Image 1, Image 2 and Image 3 here. Output size follows Image 1. Up to
            {{ Math.round(catalog.source.maxBytes / 1048576) }} MB and {{ catalog.source.maxSide }} px
            per file; the backend decodes and normalizes each file and uploads it to ComfyUI's input
            folder only when a job starts.
          </p>
        </div>
      </details>

      <!-- Output ----------------------------------------------------------->
      <details
        id="i2i-panel-output"
        open
        class="group overflow-hidden rounded-xl border border-l-2 border-border border-l-sky/60 bg-surface shadow-sm open:ring-1 open:ring-accent/20"
      >
        <summary
          class="flex cursor-pointer list-none items-center gap-2 border-b border-border/80 bg-surface-2/75 px-3.5 py-2.5 transition-colors hover:bg-surface-2 [&::-webkit-details-marker]:hidden"
        >
          <span class="h-2 w-2 shrink-0 rounded-full bg-sky" />
          <span class="text-xs font-semibold">Output</span>
          <span class="truncate text-[10px] text-muted">
            {{ targetLabel }} · {{ store.form.batch }} image{{ store.form.batch === 1 ? '' : 's' }}
          </span>
          <button
            type="button"
            class="ml-auto flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface hover:text-text"
            title="Reset output panel"
            aria-label="Reset output panel"
            @click.prevent.stop="reset('output')"
          >
            <RotateCcw class="h-3.5 w-3.5" />
          </button>
          <ChevronDown class="h-3.5 w-3.5 shrink-0 text-muted transition-transform group-open:rotate-180" />
        </summary>

        <div class="space-y-3 bg-surface px-3.5 py-3">
          <label class="block">
            <span class="mb-1 block text-[11px] text-muted">Model</span>
            <AppSelect
              :model-value="store.form.modelId"
              :options="modelOptions"
              size="sm"
              @update:model-value="setModel"
            />
          </label>
          <p v-if="model" class="text-[10px] leading-snug text-muted">
            {{ model.description || model.family }} · {{ model.vram }}
            <span v-if="model.nsfw" class="font-medium text-warn">(NSFW)</span>
            <span v-if="model.present === false" class="text-danger"> · diffusion file missing</span>
          </p>

          <label class="block">
            <span class="mb-1 block text-[11px] text-muted">Resolution</span>
            <AppSelect
              :model-value="String(store.form.resolution)"
              :options="resolutionOptions"
              size="sm"
              @update:model-value="setResolution"
            />
          </label>
          <p class="text-[10px] leading-snug text-muted">
            <span class="font-medium text-text">0</span> keeps the source size rounded to 32 px.
            A positive value is a total pixel budget that preserves the aspect ratio. Output
            <span class="font-semibold tabular-nums text-text">{{ targetLabel }}</span>.
          </p>

          <div class="grid grid-cols-2 gap-2">
            <label class="block">
              <span class="mb-1 block text-[11px] text-muted">Images</span>
              <input
                v-model.number="store.form.batch"
                type="number"
                class="h-8 w-full rounded-lg border border-border bg-surface px-2 text-[13px] text-text outline-none focus:border-accent/60"
                :min="batchRange?.min ?? 1"
                :max="batchRange?.max ?? 4"
                :step="batchRange?.step ?? 1"
              />
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] text-muted">Seed</span>
              <div class="flex gap-1">
                <input
                  v-model.number="store.form.seed"
                  type="number"
                  class="h-8 min-w-0 flex-1 rounded-lg border border-border bg-surface px-2 text-[13px] tabular-nums text-text outline-none focus:border-accent/60"
                  min="0"
                />
                <button
                  type="button"
                  class="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-border bg-surface text-muted transition-colors hover:border-accent/40 hover:text-text"
                  title="New random seed"
                  aria-label="New random seed"
                  @click="store.form.seed = Math.floor(Math.random() * 4294967296)"
                >
                  <Dices class="h-3.5 w-3.5" />
                </button>
              </div>
            </label>
          </div>

          <AppSwitch v-model="store.form.lockSeed" label="Lock seed" />
          <p class="text-[10px] leading-snug text-muted">
            Batch {{ batchRange?.min ?? 1 }}–{{ batchRange?.max ?? 4 }}. Each batch item is an
            independent variation of the same source and prompt.
          </p>
        </div>
      </details>

      <!-- Sampling --------------------------------------------------------->
      <details
        id="i2i-panel-sampling"
        open
        class="group overflow-hidden rounded-xl border border-l-2 border-border border-l-peach bg-surface shadow-sm open:ring-1 open:ring-accent/20"
      >
        <summary
          class="flex cursor-pointer list-none items-center gap-2 border-b border-border/80 bg-surface-2/75 px-3.5 py-2.5 transition-colors hover:bg-surface-2 [&::-webkit-details-marker]:hidden"
        >
          <span class="h-2 w-2 shrink-0 rounded-full bg-peach" />
          <span class="text-xs font-semibold">Sampling</span>
          <span class="truncate text-[10px] text-muted">
            {{ store.form.steps }} steps · denoise {{ store.form.denoise.toFixed(2) }} · CFG {{ store.form.cfg }}
          </span>
          <button
            type="button"
            class="ml-auto flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface hover:text-text"
            title="Reset sampling panel"
            aria-label="Reset sampling panel"
            @click.prevent.stop="reset('sampling')"
          >
            <RotateCcw class="h-3.5 w-3.5" />
          </button>
          <ChevronDown class="h-3.5 w-3.5 shrink-0 text-muted transition-transform group-open:rotate-180" />
        </summary>

        <div class="space-y-3 bg-surface px-3.5 py-3">
          <div v-if="denoiseRange">
            <div class="mb-1 flex items-center justify-between gap-2 text-[11px] text-muted">
              <span>Denoise</span>
              <span class="tabular-nums text-text">{{ store.form.denoise.toFixed(2) }}</span>
            </div>
            <AppSlider
              v-model="store.form.denoise"
              :min="denoiseRange.min"
              :max="denoiseRange.max"
              :step="denoiseRange.step"
            />
            <p class="mt-1 text-[10px] leading-snug text-muted">
              {{ denoiseRange.description }}
            </p>
            <p
              class="mt-1 rounded-lg border px-2 py-1.5 text-[10px] leading-snug"
              :class="
                fullPath
                  ? 'border-success/30 bg-success/10 text-success'
                  : 'border-warn/30 bg-warn/10 text-warn'
              "
            >
              {{ fullPath ? 'Official turbo edit path (full denoise).' : 'Img2img path: the VAE-encoded source is kept below 1.0.' }}
            </p>
          </div>

          <div class="grid grid-cols-2 gap-2">
            <label class="block">
              <span class="mb-1 block text-[11px] text-muted">Steps</span>
              <input
                v-model.number="store.form.steps"
                type="number"
                class="h-8 w-full rounded-lg border border-border bg-surface px-2 text-xs tabular-nums text-text outline-none focus:border-accent/60"
                :min="stepsRange?.min ?? 4"
                :max="stepsRange?.max ?? 20"
                :step="stepsRange?.step ?? 1"
              />
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] text-muted">CFG</span>
              <input
                v-model.number="store.form.cfg"
                type="number"
                class="h-8 w-full rounded-lg border border-border bg-surface px-2 text-xs tabular-nums text-text outline-none focus:border-accent/60"
                :min="cfgRange?.min ?? 1"
                :max="cfgRange?.max ?? 8"
                :step="cfgRange?.step ?? 0.05"
              />
            </label>
          </div>

          <label class="block">
            <span class="mb-1 block text-[11px] text-muted">Sampler</span>
            <AppSelect v-model="store.form.sampler" :options="samplerOptions" size="sm" />
          </label>

          <p class="text-[10px] leading-snug text-muted">
            Turbo ships an 8-step sigma schedule; 8 steps run it exactly and other values
            interpolate it. Keep CFG at 1.0 for the official turbo path.
            <span v-if="cfgRange">Recommended CFG {{ cfgRange.recommendedMin }}–{{ cfgRange.recommendedMax }}.</span>
          </p>
          <p
            v-if="stepsRange && store.form.steps !== model?.defaults.steps"
            class="rounded-lg border border-warn/30 bg-warn/10 px-2 py-1.5 text-[10px] leading-snug text-warn"
          >
            Turbo is trained for {{ model?.defaults.steps ?? 8 }} steps; {{ store.form.steps }} steps
            interpolate its schedule and can reduce fidelity.
          </p>
        </div>
      </details>

      <!-- Prompt extras ---------------------------------------------------->
      <details
        id="i2i-panel-prompt"
        class="group overflow-hidden rounded-xl border border-l-2 border-border border-l-lavender bg-surface shadow-sm open:ring-1 open:ring-accent/20"
      >
        <summary
          class="flex cursor-pointer list-none items-center gap-2 border-b border-border/80 bg-surface-2/75 px-3.5 py-2.5 transition-colors hover:bg-surface-2 [&::-webkit-details-marker]:hidden"
        >
          <span class="h-2 w-2 shrink-0 rounded-full bg-lavender" />
          <span class="text-xs font-semibold">Prompt extras</span>
          <span class="truncate text-[10px] text-muted">negative prompt</span>
          <button
            type="button"
            class="ml-auto flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface hover:text-text"
            title="Reset prompt extras"
            aria-label="Reset prompt extras"
            @click.prevent.stop="reset('prompt')"
          >
            <RotateCcw class="h-3.5 w-3.5" />
          </button>
          <ChevronDown class="h-3.5 w-3.5 shrink-0 text-muted transition-transform group-open:rotate-180" />
        </summary>

        <div class="space-y-3 bg-surface px-3.5 py-3">
          <label class="block">
            <span class="mb-1 flex items-center justify-between text-[11px] text-muted">
              <span>Negative prompt</span>
              <span>{{ store.form.negativePrompt.length }} / {{ catalog.limits.negativePromptMaxChars }}</span>
            </span>
            <textarea
              v-model="store.form.negativePrompt"
              rows="3"
              :maxlength="catalog.limits.negativePromptMaxChars"
              class="w-full resize-y rounded-xl border border-border bg-surface px-2.5 py-2 text-xs leading-relaxed text-text outline-none placeholder:text-muted/60 focus:border-accent/60"
              placeholder="Text to avoid..."
            />
          </label>
          <p class="text-[10px] leading-snug text-muted">
            The main prompt is edited in the composer. This reset restores the pack's negative
            prompt.
          </p>
        </div>
      </details>

      <!-- Advanced --------------------------------------------------------->
      <details
        id="i2i-panel-advanced"
        class="group overflow-hidden rounded-xl border border-l-2 border-border border-l-warn/70 bg-surface shadow-sm open:ring-1 open:ring-accent/20"
      >
        <summary
          class="flex cursor-pointer list-none items-center gap-2 border-b border-border/80 bg-surface-2/75 px-3.5 py-2.5 transition-colors hover:bg-surface-2 [&::-webkit-details-marker]:hidden"
        >
          <span class="h-2 w-2 shrink-0 rounded-full bg-warn" />
          <span class="text-xs font-semibold">Advanced</span>
          <span class="truncate text-[10px] text-muted">workflow · references</span>
          <button
            type="button"
            class="ml-auto flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface hover:text-text"
            title="Reset advanced settings"
            aria-label="Reset advanced settings"
            @click.prevent.stop="reset('advanced')"
          >
            <RotateCcw class="h-3.5 w-3.5" />
          </button>
          <ChevronDown class="h-3.5 w-3.5 shrink-0 text-muted transition-transform group-open:rotate-180" />
        </summary>

        <div class="space-y-3 bg-surface px-3.5 py-3">
          <div class="rounded-xl border border-border bg-surface-2/50 p-2.5">
            <p class="text-[11px] font-medium">Workflow</p>
            <p class="mt-0.5 text-[10px] leading-snug text-muted">
              {{ catalog.workflow.path }} · {{ catalog.workflow.nodeCount }} nodes ·
              {{ catalog.recipe.engine }}
            </p>
            <p class="mt-1 text-[10px] leading-snug text-muted">
              Full denoise: TextEncodeQwenImage21 emits the 64-channel latent at Image 1's size,
              then SamplerCustom runs the checkpoint's {{ model?.defaults.steps ?? 8 }}-step turbo
              sigmas from ManualSigmas. Below 1.0: ImageScale + VAEEncode feed the same sampler with
              the tail of that schedule. There is no switch node; the graph is pruned per request.
            </p>
          </div>

          <div class="rounded-xl border border-border bg-surface-2/50 p-2.5">
            <p class="text-[11px] font-medium">KV cache</p>
            <div class="mt-2 grid grid-cols-2 gap-2">
              <label class="block">
                <span class="mb-1 block text-[11px] text-muted">Device</span>
                <AppSelect v-model="store.form.cacheDevice" :options="cacheDeviceOptions" size="sm" />
              </label>
              <label class="block">
                <span class="mb-1 block text-[11px] text-muted">Dtype</span>
                <AppSelect v-model="store.form.cacheDtype" :options="cacheDtypeOptions" size="sm" />
              </label>
            </div>
            <p class="mt-1.5 text-[10px] leading-snug text-muted">
              `default` is lossless. `int8` halves the cache at about bf16 accuracy; `int4`
              quarters it but adds per-step error. `auto` uses spare VRAM, then RAM.
            </p>
          </div>

          <div class="rounded-xl border border-border bg-surface-2/50 p-2.5">
            <p class="text-[11px] font-medium">References</p>
            <p class="mt-0.5 text-[10px] leading-snug text-muted">
              TextEncodeQwenImage21 binds up to {{ store.maxSources }} images as
              <span class="font-medium text-text">&lt;image1&gt;</span>,
              <span class="font-medium text-text">&lt;image2&gt;</span> and
              <span class="font-medium text-text">&lt;image3&gt;</span>. Output size follows Image 1.
              Unused slots are removed from the graph rather than left linked.
            </p>
            <p class="mt-1 text-[10px] leading-snug text-muted">
              Qwen Image 2.1 native sampling · {{ catalog.workflow.referenceSlots }} reference
              slots · {{ model?.defaults.steps ?? 8 }} steps · euler / manual turbo sigmas.
            </p>
          </div>

          <p class="flex items-start gap-1.5 text-[10px] leading-snug text-muted">
            <Sparkles class="mt-0.5 h-3 w-3 shrink-0 text-accent" />
            Each reference image is uploaded to ComfyUI's input folder once per job and referenced
            by its own core LoadImage node.
          </p>
        </div>
      </details>

      <div
        v-if="store.storageError"
        class="flex gap-1.5 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-[10px] leading-snug text-danger"
      >
        <TriangleAlert class="mt-0.5 h-3 w-3 shrink-0" />
        Settings could not be autosaved: {{ store.storageError }}
      </div>
    </div>

    <footer class="shrink-0 space-y-2 border-t border-border px-3 py-3">
      <div class="flex items-center gap-2 text-[10px] text-muted">
        <Sparkles class="h-3 w-3 text-accent" />
        Settings survive route switches and reloads.
      </div>
      <AppButton size="sm" variant="danger" block @click="resetAll">
        <RotateCcw class="h-3.5 w-3.5" />
        Reset all settings
      </AppButton>
    </footer>
  </div>
</template>
