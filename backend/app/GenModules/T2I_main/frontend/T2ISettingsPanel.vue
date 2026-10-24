<script setup lang="ts">
import { computed } from 'vue'
import {
  ChevronDown,
  Dices,
  RotateCcw,
  Sparkles,
  TriangleAlert,
  WandSparkles,
  X,
} from '@lucide/vue'
import { useT2IStore } from './store'
import AppButton from '@/components/ui/AppButton.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppSlider from '@/components/ui/AppSlider.vue'
import AppSwitch from '@/components/ui/AppSwitch.vue'

const emit = defineEmits<{ (e: 'close'): void }>()
const store = useT2IStore()

const catalog = computed(() => store.catalog)
const model = computed(() => store.selectedModel)
const upscaler = computed(() => store.upscaler)
const upscalerRange = computed(() => store.upscalerRange)
const missingUpscaler = computed(() => upscaler.value?.present === false)
const hasUsableUpscaler = computed(() =>
  (catalog.value?.upscalers ?? []).some(
    (item) => item.t2i && item.kind !== 'none' && item.present !== false,
  ),
)

const modelOptions = computed(() =>
  (catalog.value?.models ?? []).map((item) => ({
    value: item.id,
    label: item.present === false ? `${item.shortLabel} (missing)` : item.shortLabel,
    disabled: item.present === false,
  })),
)

const ratioOptions = computed(() =>
  (catalog.value?.ratios ?? []).map((item) => ({ value: item.id, label: item.label })),
)

const sizeOptions = computed(() =>
  (catalog.value?.size.values ?? []).map((value) => ({
    value: String(value),
    label: `${value}px`,
  })),
)

const samplerOptions = computed(() =>
  (model.value?.samplers ?? []).map((item) => ({ value: item.id, label: item.label })),
)

const schedulerOptions = computed(() =>
  (model.value?.schedulers ?? []).map((item) => ({ value: item.id, label: item.label })),
)

const upscalerOptions = computed(() =>
  (catalog.value?.upscalers ?? [])
    .filter((item) => item.t2i)
    .map((item) => ({
      value: item.id,
      label: item.present === false ? `${item.shortLabel} (missing)` : item.shortLabel,
      disabled: item.present === false,
    })),
)

const providerOptions = [
  { value: 'ollama', label: 'Ollama' },
  { value: 'comfyui', label: 'ComfyUI' },
]

const textModelOptions = computed(() => [
  { value: '', label: 'Auto (pack default)' },
  ...store.enhanceModels.map((item) => ({
    value: item.id,
    label:
      item.present === false
        ? `${item.label} (missing)`
        : item.provider === 'ollama' && item.model
          ? `${item.label} (${item.model})`
          : item.label,
    disabled: item.present === false,
  })),
])

const loraRows = computed(() =>
  store.availableLoras.map((lora) => ({
    lora,
    on: store.isLoraOn(lora.id),
    strength: store.loraStrength(lora.id) ?? lora.strength.default,
  })),
)

function setModel(value: string): void {
  store.form.modelId = value
  store.onModelChange()
}

function setSize(value: string): void {
  store.form.size = Number(value)
}

function setUpscaler(value: string): void {
  store.form.upscalerId = value
  store.onUpscalerChange()
}

function setProvider(value: string): void {
  store.form.enhanceProvider = value === 'comfyui' ? 'comfyui' : 'ollama'
  store.onProviderChange()
}

function setEnhanceModel(value: string): void {
  store.form.enhanceModel = value
}

function setLoraStrength(id: string, event: Event): void {
  const value = Number((event.target as HTMLInputElement).value)
  if (Number.isFinite(value)) store.setLoraStrength(id, value)
}

function toggleLora(id: string, value: boolean): void {
  store.setLoraOn(id, value)
}

function setUpscalerValue(event: Event): void {
  const value = Number((event.target as HTMLInputElement).value)
  if (Number.isFinite(value)) store.form.upscalerValue = value
}

function reset(panel: 'prompt' | 'output' | 'loras' | 'enhance' | 'sampling' | 'upscale'): void {
  store.resetPanel(panel)
}

function resetAll(): void {
  if (
    window.confirm(
      'Reset every T2I setting? This also clears the prompt, negative prompt and approved enhancement.',
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
        <p class="text-sm font-semibold">Generation settings</p>
        <p class="mt-0.5 text-[11px] leading-snug text-muted">
          Autosaved in this browser. Every panel has its own reset.
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

    <div v-else class="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
      <!-- Output ------------------------------------------------------------>
      <details
        id="t2i-panel-output"
        open
        class="group rounded-2xl border border-border bg-surface-2/30"
      >
        <summary
          class="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 [&::-webkit-details-marker]:hidden"
        >
          <span class="text-xs font-semibold">Output</span>
          <span class="truncate text-[10px] text-muted">
            {{ model?.shortLabel ?? 'No model' }} · {{ store.form.ratio }} · {{ store.form.size }}px
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

        <div class="space-y-3 border-t border-border px-3 py-3">
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
            <span v-if="model.present === false" class="text-danger"> · model file missing</span>
          </p>

          <div class="grid grid-cols-2 gap-2">
            <label class="block">
              <span class="mb-1 block text-[11px] text-muted">Ratio</span>
              <AppSelect v-model="store.form.ratio" :options="ratioOptions" size="sm" />
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] text-muted">Long side</span>
              <AppSelect
                :model-value="String(store.form.size)"
                :options="sizeOptions"
                size="sm"
                @update:model-value="setSize"
              />
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] text-muted">Images</span>
              <input
                v-model.number="store.form.batch"
                type="number"
                class="h-8 w-full rounded-lg border border-border bg-surface px-2 text-[13px] text-text outline-none focus:border-accent/60"
                :min="model?.ranges.batch.min ?? 1"
                :max="model?.ranges.batch.max ?? 4"
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
        </div>
      </details>

      <!-- Upscale ----------------------------------------------------------->
      <details
        id="t2i-panel-upscale"
        open
        class="group rounded-2xl border border-border bg-surface-2/30"
      >
        <summary
          class="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 [&::-webkit-details-marker]:hidden"
        >
          <span class="text-xs font-semibold">Upscale</span>
          <span class="truncate text-[10px] text-muted">{{ store.upscalerLabel }}</span>
          <button
            type="button"
            class="ml-auto flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface hover:text-text"
            title="Reset upscale panel"
            aria-label="Reset upscale panel"
            @click.prevent.stop="reset('upscale')"
          >
            <RotateCcw class="h-3.5 w-3.5" />
          </button>
          <ChevronDown class="h-3.5 w-3.5 shrink-0 text-muted transition-transform group-open:rotate-180" />
        </summary>

        <div class="space-y-3 border-t border-border px-3 py-3">
          <div class="flex items-center gap-2 rounded-xl border border-border bg-surface px-2.5 py-2">
            <span
              class="h-2 w-2 rounded-full"
              :class="store.upscalerOn ? 'bg-success' : 'bg-border'"
            />
            <AppSwitch
              :model-value="store.upscalerOn"
              :disabled="!hasUsableUpscaler"
              label="Enable upscale"
              @update:model-value="store.setUpscalerEnabled"
            />
            <span class="ml-auto text-[10px] font-semibold uppercase tracking-wide text-muted">
              {{ store.upscalerOn ? 'On' : 'Off' }}
            </span>
          </div>

          <label class="block">
            <span class="mb-1 block text-[11px] text-muted">Path</span>
            <AppSelect
              :model-value="store.form.upscalerId"
              :options="upscalerOptions"
              size="sm"
              @update:model-value="setUpscaler"
            />
          </label>

          <p v-if="missingUpscaler" class="flex gap-1.5 text-[10px] leading-snug text-warn">
            <TriangleAlert class="mt-0.5 h-3 w-3 shrink-0" />
            This path is not installed. Choose another path or leave upscale off.
          </p>

          <template v-if="upscaler && upscaler.kind !== 'none' && store.upscalerOn">
            <div v-if="store.refineActive" class="grid grid-cols-3 gap-2">
              <label class="block">
                <span class="mb-1 block text-[10px] text-muted">Refine steps</span>
                <input
                  v-model.number="store.form.refineSteps"
                  type="number"
                  class="h-8 w-full rounded-lg border border-border bg-surface px-2 text-xs text-text outline-none focus:border-accent/60"
                  :min="model?.ranges.refine.steps.min"
                  :max="model?.ranges.refine.steps.max"
                  :step="model?.ranges.refine.steps.step"
                />
              </label>
              <label class="block">
                <span class="mb-1 block text-[10px] text-muted">Refine CFG</span>
                <input
                  v-model.number="store.form.refineCfg"
                  type="number"
                  class="h-8 w-full rounded-lg border border-border bg-surface px-2 text-xs text-text outline-none focus:border-accent/60"
                  :min="model?.ranges.refine.cfg.min"
                  :max="model?.ranges.refine.cfg.max"
                  :step="model?.ranges.refine.cfg.step"
                />
              </label>
              <label class="block">
                <span class="mb-1 block text-[10px] text-muted">Denoise</span>
                <input
                  v-model.number="store.form.refineDenoise"
                  type="number"
                  class="h-8 w-full rounded-lg border border-border bg-surface px-2 text-xs text-text outline-none focus:border-accent/60"
                  :min="model?.ranges.refine.denoise.min"
                  :max="model?.ranges.refine.denoise.max"
                  :step="model?.ranges.refine.denoise.step"
                />
              </label>
            </div>

            <div v-if="upscalerRange">
              <div class="mb-1 flex items-center justify-between gap-2 text-[11px] text-muted">
                <span>{{ upscalerRange.label }}</span>
                <span class="text-[10px]">recommended {{ upscalerRange.recommendedMin }}–{{ upscalerRange.recommendedMax }}px</span>
              </div>
              <AppSlider
                v-model="store.form.upscalerValue"
                :min="upscalerRange.min"
                :max="upscalerRange.max"
                :step="upscalerRange.step"
              />
              <input
                :value="store.form.upscalerValue"
                type="number"
                class="mt-1 h-8 w-full rounded-lg border border-border bg-surface px-2 text-xs tabular-nums text-text outline-none focus:border-accent/60"
                :min="upscalerRange.min"
                :max="upscalerRange.max"
                :step="upscalerRange.step"
                @input="setUpscalerValue"
              />
            </div>
            <p class="text-[10px] leading-snug text-muted">
              {{ upscaler.notes }}
            </p>
          </template>

          <p v-else-if="upscaler && upscaler.kind === 'none'" class="text-[10px] text-muted">
            No upscale: the image is decoded at the selected long side.
          </p>
        </div>
      </details>

      <!-- LoRA chain -------------------------------------------------------->
      <details id="t2i-panel-loras" class="group rounded-2xl border border-border bg-surface-2/30">
        <summary
          class="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 [&::-webkit-details-marker]:hidden"
        >
          <span class="text-xs font-semibold">LoRA chain</span>
          <span class="truncate text-[10px] text-muted">{{ store.activeLoraCount }} active</span>
          <button
            type="button"
            class="ml-auto flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface hover:text-text"
            title="Reset LoRA panel"
            aria-label="Reset LoRA panel"
            @click.prevent.stop="reset('loras')"
          >
            <RotateCcw class="h-3.5 w-3.5" />
          </button>
          <ChevronDown class="h-3.5 w-3.5 shrink-0 text-muted transition-transform group-open:rotate-180" />
        </summary>

        <div class="space-y-2 border-t border-border px-3 py-3">
          <p v-if="!loraRows.length" class="text-[10px] text-muted">
            No compatible LoRAs for this model.
          </p>
          <div
            v-for="row in loraRows"
            :key="row.lora.id"
            class="rounded-xl border border-border bg-surface px-2.5 py-2"
          >
            <div class="flex items-center gap-2">
              <AppSwitch
                :model-value="row.on"
                @update:model-value="toggleLora(row.lora.id, $event)"
              />
              <div class="min-w-0 flex-1">
                <p class="truncate text-xs font-medium">{{ row.lora.label }}</p>
                <p class="truncate text-[10px] text-muted">
                  {{ row.lora.type || row.lora.base }}
                  <span v-if="row.lora.triggers.length"> · {{ row.lora.triggers.join(', ') }}</span>
                </p>
              </div>
              <span class="shrink-0 text-[10px] tabular-nums text-muted">
                {{ row.strength.toFixed(2) }}
              </span>
            </div>
            <div v-if="row.on" class="mt-2">
              <input
                :value="row.strength"
                type="range"
                class="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-border"
                :min="row.lora.strength.min"
                :max="row.lora.strength.max"
                :step="row.lora.strength.step"
                :style="{ accentColor: 'var(--c-accent)' }"
                @input="setLoraStrength(row.lora.id, $event)"
              />
            </div>
          </div>
          <p class="text-[10px] text-muted">
            {{ store.activeLoraCount }} / {{ catalog.limits.maxLoras }} active · trigger words
            are added automatically.
          </p>
          <AppSwitch v-model="store.form.autoTriggers" label="Auto-append trigger words" />
        </div>
      </details>

      <!-- Enhancement ------------------------------------------------------->
      <details id="t2i-panel-enhance" class="group rounded-2xl border border-border bg-surface-2/30">
        <summary
          class="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 [&::-webkit-details-marker]:hidden"
        >
          <span class="text-xs font-semibold">Prompt enhancement</span>
          <span class="truncate text-[10px] text-muted">
            {{ store.form.enhanceEnabled ? store.form.enhanceProvider : 'Off' }}
          </span>
          <button
            type="button"
            class="ml-auto flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface hover:text-text"
            title="Reset enhancement panel"
            aria-label="Reset enhancement panel"
            @click.prevent.stop="reset('enhance')"
          >
            <RotateCcw class="h-3.5 w-3.5" />
          </button>
          <ChevronDown class="h-3.5 w-3.5 shrink-0 text-muted transition-transform group-open:rotate-180" />
        </summary>

        <div class="space-y-3 border-t border-border px-3 py-3">
          <AppSwitch
            :model-value="store.form.enhanceEnabled"
            label="Improve prompt with a text model"
            @update:model-value="store.setEnhanceEnabled"
          />

          <template v-if="store.form.enhanceEnabled">
            <div class="grid grid-cols-2 gap-2">
              <label class="block">
                <span class="mb-1 block text-[11px] text-muted">Provider</span>
                <AppSelect
                  :model-value="store.form.enhanceProvider"
                  :options="providerOptions"
                  size="sm"
                  @update:model-value="setProvider"
                />
              </label>
              <label class="block">
                <span class="mb-1 block text-[11px] text-muted">Text model</span>
                <AppSelect
                  :model-value="store.form.enhanceModel"
                  :options="textModelOptions"
                  size="sm"
                  @update:model-value="setEnhanceModel"
                />
              </label>
            </div>

            <p class="flex items-center gap-1.5 text-[10px] text-muted">
              <span
                class="h-1.5 w-1.5 rounded-full"
                :class="store.providerReady ? 'bg-success' : 'bg-danger'"
              />
              {{ store.providerReady ? 'Provider ready' : 'Provider offline — preview is disabled' }}
            </p>

            <div class="flex flex-wrap items-center gap-2">
              <AppButton
                size="sm"
                :disabled="!store.canEnhance"
                @click="store.enhanceNow"
              >
                <WandSparkles class="h-3.5 w-3.5" />
                {{ store.enhancing ? 'Enhancing...' : 'Preview enhancement' }}
              </AppButton>
              <AppButton v-if="store.enhancing" size="sm" variant="ghost" @click="store.cancelEnhancement">
                Cancel
              </AppButton>
              <AppSwitch v-model="store.form.fallbackToOriginal" label="Fall back to original" />
            </div>

            <div
              v-if="store.enhancePreview"
              class="rounded-xl border border-accent/30 bg-accent-soft/40 p-2.5"
            >
              <div class="mb-1.5 flex items-center justify-between gap-2">
                <span class="text-[10px] font-semibold uppercase tracking-wide text-accent">
                  Preview · {{ store.enhancePreview.model }}
                </span>
                <span class="text-[10px] text-muted">
                  {{ (store.enhancePreview.durationMs / 1000).toFixed(1) }}s
                </span>
              </div>
              <p class="whitespace-pre-wrap text-[12px] leading-relaxed">{{ store.enhancePreview.prompt }}</p>
              <div class="mt-2 flex gap-2">
                <AppButton size="sm" @click="store.useEnhancement">Use this prompt</AppButton>
                <AppButton size="sm" variant="ghost" @click="store.discardEnhancement">Discard</AppButton>
              </div>
            </div>

            <label class="block">
              <span class="mb-1 flex items-center justify-between text-[11px] text-muted">
                <span>Approved prompt</span>
                <span>{{ store.form.approvedPrompt.length }} chars</span>
              </span>
              <textarea
                v-model="store.form.approvedPrompt"
                rows="3"
                :maxlength="catalog.limits.promptMaxChars"
                class="w-full resize-y rounded-xl border border-border bg-surface px-2.5 py-2 text-xs leading-relaxed text-text outline-none placeholder:text-muted/60 focus:border-accent/60"
                placeholder="Leave empty to let the backend enhance automatically, or preview and approve a rewrite."
              />
            </label>
            <p class="text-[10px] leading-snug text-muted">
              An approved prompt is used for the next generation and then cleared.
            </p>
          </template>
        </div>
      </details>

      <!-- Sampling ---------------------------------------------------------->
      <details id="t2i-panel-sampling" class="group rounded-2xl border border-border bg-surface-2/30">
        <summary
          class="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 [&::-webkit-details-marker]:hidden"
        >
          <span class="text-xs font-semibold">Sampling</span>
          <span class="truncate text-[10px] text-muted">
            {{ store.form.steps }} steps · CFG {{ store.form.cfg }}
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

        <div class="space-y-3 border-t border-border px-3 py-3">
          <div class="grid grid-cols-3 gap-2">
            <label class="block">
              <span class="mb-1 block text-[10px] text-muted">Steps</span>
              <input
                v-model.number="store.form.steps"
                type="number"
                class="h-8 w-full rounded-lg border border-border bg-surface px-2 text-xs text-text outline-none focus:border-accent/60"
                :min="model?.ranges.steps.min"
                :max="model?.ranges.steps.max"
                :step="model?.ranges.steps.step"
              />
            </label>
            <label class="block">
              <span class="mb-1 block text-[10px] text-muted">CFG</span>
              <input
                v-model.number="store.form.cfg"
                type="number"
                class="h-8 w-full rounded-lg border border-border bg-surface px-2 text-xs text-text outline-none focus:border-accent/60"
                :min="model?.ranges.cfg.min"
                :max="model?.ranges.cfg.max"
                :step="model?.ranges.cfg.step"
              />
            </label>
            <label class="block">
              <span class="mb-1 block text-[10px] text-muted">Denoise</span>
              <input
                v-model.number="store.form.denoise"
                type="number"
                class="h-8 w-full rounded-lg border border-border bg-surface px-2 text-xs text-text outline-none focus:border-accent/60"
                :min="model?.ranges.denoise.min"
                :max="model?.ranges.denoise.max"
                :step="model?.ranges.denoise.step"
              />
            </label>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <label class="block">
              <span class="mb-1 block text-[11px] text-muted">Sampler</span>
              <AppSelect v-model="store.form.sampler" :options="samplerOptions" size="sm" />
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] text-muted">Scheduler</span>
              <AppSelect v-model="store.form.scheduler" :options="schedulerOptions" size="sm" />
            </label>
          </div>
          <p class="text-[10px] leading-snug text-muted">
            Defaults: {{ model?.defaults.steps }} steps · CFG {{ model?.defaults.cfg }} ·
            {{ model?.defaults.sampler }}/{{ model?.defaults.scheduler }}.
          </p>
        </div>
      </details>

      <!-- Prompt extras ----------------------------------------------------->
      <details id="t2i-panel-prompt" class="group rounded-2xl border border-border bg-surface-2/30">
        <summary
          class="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 [&::-webkit-details-marker]:hidden"
        >
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

        <div class="space-y-3 border-t border-border px-3 py-3">
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
            Prompt is edited in the composer. This reset restores the pack's negative prompt and
            clears the approved enhancement.
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
