<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Database, Link2, LoaderCircle, Pencil, RefreshCw, Tags, TriangleAlert } from '@lucide/vue'
import { useCatalogStore } from '@/stores/catalog'
import type {
  CatalogClipRange,
  CatalogLoraEntry,
  CatalogLoraPatch,
  CatalogModelEntry,
  CatalogModelPatch,
  CatalogRange,
} from '@/types'
import Section from '@/components/ui/Section.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppModal from '@/components/ui/AppModal.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppSwitch from '@/components/ui/AppSwitch.vue'
import AppTextarea from '@/components/ui/AppTextarea.vue'
import Badge from '@/components/ui/Badge.vue'
import EmptyState from '@/components/ui/EmptyState.vue'

const catalog = useCatalogStore()

onMounted(() => {
  void catalog.ensureLoaded()
})

const sourceFolder = computed(() => catalog.data?.source?.comfyuiFolder ?? '')
const updatedLabel = computed(() => formatDate(catalog.data?.updatedAt ?? null))
const baseFilter = ref('all')

const baseFilterOptions = computed(() => {
  const options = [
    { value: 'all', label: 'All bases' },
    { value: '__none', label: 'Unassigned' },
  ]
  for (const base of catalog.bases) {
    options.push({ value: base.id, label: `${base.label} (${base.loras})` })
  }
  return options
})

const filteredLoras = computed(() => {
  if (baseFilter.value === 'all') return catalog.loras
  if (baseFilter.value === '__none') return catalog.loras.filter((lora) => !lora.base)
  return catalog.loras.filter((lora) => lora.base === baseFilter.value)
})

function formatDate(value: string | null): string {
  if (!value) return 'never'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function formatBytes(bytes: number): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value.toFixed(index <= 1 ? 0 : 1)} ${units[index]}`
}

function rangeText(range: CatalogRange): string {
  const step = range.step < 0.01 ? range.step.toFixed(3) : String(range.step)
  return `${fmt(range.min)} - ${fmt(range.max)} (step ${step})`
}

function fmt(value: number): string {
  if (Number.isInteger(value)) return String(value)
  return value.toFixed(2).replace(/0+$/, '').replace(/\.$/, '')
}

function baseOptions(current: string) {
  const options = [{ value: '', label: 'Unassigned' }]
  for (const base of catalog.bases) {
    options.push({ value: base.id, label: base.label })
  }
  if (current && !options.some((option) => option.value === current)) {
    options.push({ value: current, label: current })
  }
  return options
}

// -- LoRA editor -------------------------------------------------------------

interface LoraForm {
  label: string
  base: string
  models: string[]
  modelsAuto: boolean
  triggersText: string
  strength: CatalogRange
  clip: CatalogClipRange
  otherText: string
  notes: string
}

const loraModal = ref(false)
const editingLora = ref<CatalogLoraEntry | null>(null)
const formError = ref('')

const form = reactive<LoraForm>({
  label: '',
  base: '',
  models: [],
  modelsAuto: true,
  triggersText: '',
  strength: { default: 0.8, min: 0, max: 1.5, step: 0.05 },
  clip: { default: 0.8, min: 0, max: 1.5, step: 0.05, enabled: false },
  otherText: '{}',
  notes: '',
})

const loraBaseOptions = computed(() => baseOptions(form.base))
const autoModels = computed(() => catalog.autoModelsFor(form.base || null))
const rangeFields = ['default', 'min', 'max', 'step'] as const

function openLora(lora: CatalogLoraEntry): void {
  editingLora.value = lora
  Object.assign(form, {
    label: lora.label,
    base: lora.base ?? '',
    models: [...lora.models],
    modelsAuto: lora.modelsAuto,
    triggersText: lora.triggers.join(', '),
    strength: { ...lora.strength },
    clip: { ...lora.clipStrength },
    otherText: JSON.stringify(lora.otherRanges ?? {}, null, 2),
    notes: lora.notes,
  })
  formError.value = ''
  loraModal.value = true
}

function toggleModel(id: string, event: Event): void {
  const checked = (event.target as HTMLInputElement).checked
  if (checked) {
    if (!form.models.includes(id)) form.models.push(id)
  } else {
    form.models = form.models.filter((modelId) => modelId !== id)
  }
}

function rangeError(name: string, range: CatalogRange): string | null {
  const values = [range.default, range.min, range.max, range.step]
  if (!values.every((value) => Number.isFinite(value))) {
    return `${name}: enter a number for default, min, max and step.`
  }
  if (range.max <= range.min) return `${name}: max must be greater than min.`
  if (range.default < range.min || range.default > range.max) {
    return `${name}: default must be between min and max.`
  }
  if (range.step <= 0) return `${name}: step must be greater than zero.`
  return null
}

function parseOtherRanges(text: string): Record<string, CatalogRange> {
  const trimmed = text.trim()
  if (!trimmed || trimmed === '{}') return {}
  let raw: unknown
  try {
    raw = JSON.parse(trimmed)
  } catch {
    throw new Error('Other ranges must be valid JSON.')
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new Error('Other ranges must be a JSON object of named ranges.')
  }
  const result: Record<string, CatalogRange> = {}
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (!/^[A-Za-z0-9_.-]+$/.test(key)) {
      throw new Error(`Invalid range name "${key}". Use letters, numbers, dots, dashes or underscores.`)
    }
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw new Error(`Range "${key}" must be an object.`)
    }
    const source = value as Record<string, unknown>
    const range: CatalogRange = {
      default: Number(source.default),
      min: Number(source.min),
      max: Number(source.max),
      step: Number(source.step),
    }
    const error = rangeError(`Range "${key}"`, range)
    if (error) throw new Error(error)
    result[key] = range
  }
  return result
}

async function saveLora(): Promise<void> {
  const lora = editingLora.value
  if (!lora) return
  formError.value = ''

  const strengthError = rangeError('Strength', form.strength)
  if (strengthError) {
    formError.value = strengthError
    return
  }
  const clipError = rangeError('CLIP strength', form.clip)
  if (clipError) {
    formError.value = clipError
    return
  }

  let otherRanges: Record<string, CatalogRange>
  try {
    otherRanges = parseOtherRanges(form.otherText)
  } catch (err) {
    formError.value = err instanceof Error ? err.message : String(err)
    return
  }

  const patch: CatalogLoraPatch = {
    label: form.label.trim(),
    base: form.base.trim() || null,
    modelsAuto: form.modelsAuto,
    triggers: form.triggersText
      .split(/[,\n]/)
      .map((value) => value.trim())
      .filter(Boolean),
    strength: { ...form.strength },
    clipStrength: { ...form.clip },
    otherRanges,
    notes: form.notes.trim(),
  }
  if (!form.modelsAuto) patch.models = [...form.models]

  const saved = await catalog.saveLora(lora.id, patch)
  if (saved) loraModal.value = false
}

// -- model editor ------------------------------------------------------------

interface ModelForm {
  label: string
  base: string
  notes: string
}

const modelModal = ref(false)
const editingModel = ref<CatalogModelEntry | null>(null)
const modelError = ref('')
const modelForm = reactive<ModelForm>({ label: '', base: '', notes: '' })
const modelBaseOptions = computed(() => baseOptions(modelForm.base))

function openModel(model: CatalogModelEntry): void {
  editingModel.value = model
  modelForm.label = model.label
  modelForm.base = model.base ?? ''
  modelForm.notes = model.notes
  modelError.value = ''
  modelModal.value = true
}

async function saveModel(): Promise<void> {
  const model = editingModel.value
  if (!model) return
  modelError.value = ''
  if (!modelForm.label.trim()) {
    modelError.value = 'Give the model a label.'
    return
  }
  const patch: CatalogModelPatch = {
    label: modelForm.label.trim(),
    base: modelForm.base.trim() || null,
    notes: modelForm.notes.trim(),
  }
  const saved = await catalog.saveModel(model.id, patch)
  if (saved) modelModal.value = false
}
</script>

<template>
  <Section
    title="Model & LoRA catalog"
    desc="Stable metadata for the models in your ComfyUI folder. Built from file headers, then editable: model links, strength ranges and trigger words are what modules and the composer use."
  >
    <div class="flex flex-wrap items-center gap-2">
      <Badge :tone="catalog.hasCatalog ? 'ok' : 'neutral'">
        {{ catalog.hasCatalog ? 'Catalog built' : 'Not built yet' }}
      </Badge>
      <span v-if="catalog.hasCatalog" class="text-[11px] text-muted">Updated {{ updatedLabel }}</span>
      <span
        v-if="sourceFolder"
        class="max-w-[280px] truncate font-mono text-[10px] text-muted"
        :title="sourceFolder"
      >
        {{ sourceFolder }}
      </span>
      <AppButton
        v-if="catalog.hasCatalog"
        class="ml-auto"
        size="sm"
        variant="soft"
        :disabled="catalog.refreshing || catalog.loading"
        @click="catalog.refresh()"
      >
        <LoaderCircle v-if="catalog.refreshing" class="h-3.5 w-3.5 animate-spin" />
        <RefreshCw v-else class="h-3.5 w-3.5" />
        {{
          catalog.refreshing
            ? 'Scanning headers...'
            : catalog.hasCatalog
              ? 'Refresh from ComfyUI'
              : 'Build from ComfyUI'
        }}
      </AppButton>
    </div>

    <p class="mt-2 text-[11px] leading-relaxed text-muted">
      Building reads only the safetensors/GGUF headers - no model is loaded or changed. Refreshing keeps your labels,
      model links, triggers and ranges. Files that disappeared stay in the catalog marked as missing.
    </p>

    <p v-if="catalog.error" class="mt-2 flex items-start gap-2 rounded-xl border border-warn/30 bg-warn/10 p-3 text-[11px] text-warn">
      <TriangleAlert class="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>{{ catalog.error }}</span>
    </p>

    <div v-if="catalog.loading && !catalog.data" class="mt-4 flex items-center gap-2 text-xs text-muted">
      <LoaderCircle class="h-4 w-4 animate-spin" /> Reading the saved catalog...
    </div>

    <EmptyState
      v-else-if="!catalog.hasCatalog"
      class="mt-4"
      title="No catalog yet"
      desc="Build it once from your configured ComfyUI folder. The catalog records each model's family, which LoRAs belong to it, their safe strength ranges and trigger words."
    >
      <template #icon>
        <Database class="h-5 w-5" />
      </template>
      <AppButton variant="soft" :disabled="catalog.refreshing" @click="catalog.refresh()">
        <LoaderCircle v-if="catalog.refreshing" class="h-4 w-4 animate-spin" />
        <RefreshCw v-else class="h-4 w-4" />
        {{ catalog.refreshing ? 'Scanning headers...' : 'Build catalog from ComfyUI' }}
      </AppButton>
    </EmptyState>

    <template v-else>
      <div class="mt-4 grid gap-2 sm:grid-cols-4">
        <div class="rounded-xl border border-border bg-surface-2/40 p-3">
          <p class="text-[10px] uppercase tracking-wider text-muted">Base models</p>
          <p class="mt-1 text-lg font-semibold">{{ catalog.stats.baseModels }}</p>
        </div>
        <div class="rounded-xl border border-border bg-surface-2/40 p-3">
          <p class="text-[10px] uppercase tracking-wider text-muted">LoRAs</p>
          <p class="mt-1 text-lg font-semibold">{{ catalog.stats.loras }}</p>
        </div>
        <div class="rounded-xl border border-border bg-surface-2/40 p-3">
          <p class="text-[10px] uppercase tracking-wider text-muted">With triggers</p>
          <p class="mt-1 text-lg font-semibold">{{ catalog.stats.withTriggers }}</p>
        </div>
        <div class="rounded-xl border border-border bg-surface-2/40 p-3">
          <p class="text-[10px] uppercase tracking-wider text-muted">Missing files</p>
          <p class="mt-1 text-lg font-semibold" :class="catalog.stats.missing ? 'text-warn' : ''">
            {{ catalog.stats.missing }}
          </p>
        </div>
      </div>

      <!-- base models -->
      <div class="mt-5">
        <div class="mb-2 flex items-center gap-2">
          <h4 class="text-xs font-semibold">Base models</h4>
          <Badge>{{ catalog.baseModels.length }}</Badge>
        </div>
        <div v-if="catalog.baseModels.length" class="space-y-2">
          <div
            v-for="model in catalog.baseModels"
            :key="model.id"
            class="rounded-xl border border-border bg-surface-2/30 p-3"
          >
            <div class="flex items-start gap-2">
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-1.5">
                  <p class="truncate text-xs font-medium">{{ model.label }}</p>
                  <Badge>{{ model.kind }}</Badge>
                  <Badge v-if="model.base" tone="accent">{{ catalog.baseLabel(model.base) }}</Badge>
                  <Badge v-if="!model.present" tone="warn">missing</Badge>
                </div>
                <p class="mt-0.5 truncate text-[10px] text-muted">
                  {{ model.name }} - {{ formatBytes(model.size) }}
                  <span v-if="model.architecture"> - {{ model.architecture }}</span>
                </p>
              </div>
              <AppButton size="sm" variant="ghost" @click="openModel(model)">
                <Pencil class="h-3 w-3" /> Edit
              </AppButton>
            </div>
            <div class="mt-2 flex flex-wrap items-center gap-1">
              <span class="text-[10px] text-muted">LoRAs:</span>
              <span
                v-for="loraId in model.loras"
                :key="loraId"
                class="rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] text-text"
              >
                {{ catalog.byLora(loraId)?.label ?? loraId }}
              </span>
              <span v-if="!model.loras.length" class="text-[10px] text-muted">none linked</span>
              <span v-if="!model.present" class="text-[10px] text-warn">file not found in the last scan</span>
            </div>
          </div>
        </div>
        <p v-else class="rounded-xl border border-dashed border-border p-3 text-xs text-muted">
          No base models were found in the configured ComfyUI folder. Add a checkpoint or diffusion model, then
          refresh.
        </p>

        <details v-if="catalog.companions.length" class="mt-2 rounded-xl border border-border bg-surface-2/20 p-3">
          <summary class="cursor-pointer text-[11px] text-muted">
            Companion files ({{ catalog.companions.length }}) - VAE, text encoders, upscalers, ...
          </summary>
          <ul class="mt-2 space-y-1">
            <li
              v-for="model in catalog.companions"
              :key="model.id"
              class="flex items-center justify-between gap-2 text-[11px]"
            >
              <span class="truncate">
                {{ model.label }} <span class="text-muted">- {{ model.kind }}</span>
              </span>
              <span class="shrink-0 text-[10px] text-muted">{{ formatBytes(model.size) }}</span>
            </li>
          </ul>
        </details>
      </div>

      <!-- LoRAs -->
      <div class="mt-5">
        <div class="mb-2 flex flex-wrap items-center gap-2">
          <h4 class="text-xs font-semibold">LoRAs</h4>
          <Badge>{{ catalog.stats.loras }}</Badge>
          <div class="ml-auto w-44">
            <AppSelect v-model="baseFilter" :options="baseFilterOptions" size="sm" />
          </div>
        </div>

        <div v-if="filteredLoras.length" class="space-y-2">
          <div
            v-for="lora in filteredLoras"
            :key="lora.id"
            class="rounded-xl border border-border bg-surface-2/30 p-3"
          >
            <div class="flex items-start gap-2">
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-1.5">
                  <p class="truncate text-xs font-medium">{{ lora.label }}</p>
                  <Badge v-if="lora.base" tone="accent">{{ catalog.baseLabel(lora.base) }}</Badge>
                  <Badge v-else tone="warn">unassigned</Badge>
                  <Badge v-if="lora.modelsAuto" tone="neutral">auto-linked</Badge>
                  <Badge v-if="!lora.present" tone="warn">missing</Badge>
                </div>
                <p class="mt-0.5 truncate text-[10px] text-muted">
                  {{ lora.name }} - {{ formatBytes(lora.size) }}
                </p>
              </div>
              <AppButton size="sm" variant="ghost" @click="openLora(lora)">
                <Pencil class="h-3 w-3" /> Edit
              </AppButton>
            </div>

            <div class="mt-2 flex flex-wrap items-center gap-1">
              <Tags class="h-3 w-3 text-muted" />
              <span v-for="trigger in lora.triggers" :key="trigger" class="rounded-md bg-accent-soft px-1.5 py-0.5 text-[10px] text-accent">
                {{ trigger }}
              </span>
              <span v-if="!lora.triggers.length" class="text-[10px] text-muted">no trigger words</span>
            </div>

            <div class="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted">
              <span>Weight {{ fmt(lora.strength.default) }} - {{ rangeText(lora.strength) }}</span>
              <span v-if="lora.clipStrength.enabled">CLIP {{ fmt(lora.clipStrength.default) }} - {{ rangeText(lora.clipStrength) }}</span>
              <span v-if="Object.keys(lora.otherRanges).length">
                {{ Object.keys(lora.otherRanges).length }} extra range(s)
              </span>
            </div>

            <div class="mt-2 flex flex-wrap items-center gap-1">
              <Link2 class="h-3 w-3 text-muted" />
              <template v-if="lora.models.length">
                <span
                  v-for="modelId in lora.models"
                  :key="modelId"
                  class="rounded-md bg-accent-soft px-1.5 py-0.5 text-[10px] text-accent"
                >
                  {{ catalog.modelLabel(modelId) }}
                </span>
              </template>
              <span v-else class="text-[10px] text-warn">not linked to a base model</span>
            </div>

            <p v-if="lora.notes" class="mt-1.5 line-clamp-2 text-[10px] text-muted">{{ lora.notes }}</p>
          </div>
        </div>

        <p
          v-else-if="catalog.loras.length"
          class="rounded-xl border border-dashed border-border p-3 text-xs text-muted"
        >
          No LoRAs for this base.
        </p>
        <p v-else class="rounded-xl border border-dashed border-border p-3 text-xs text-muted">
          No LoRAs were found in the configured ComfyUI `loras` folders. Add one, then refresh.
        </p>
      </div>
    </template>
  </Section>

  <!-- LoRA editor -->
  <AppModal
    v-model="loraModal"
    title="Edit LoRA catalog entry"
    :subtitle="editingLora?.name"
    width="720px"
  >
    <div class="space-y-4">
      <div class="grid gap-3 sm:grid-cols-2">
        <label class="block text-xs">
          <span class="text-muted">Label</span>
          <AppInput v-model="form.label" class="mt-1" placeholder="Readable name" />
        </label>
        <label class="block text-xs">
          <span class="text-muted">Base</span>
          <AppSelect v-model="form.base" :options="loraBaseOptions" class="mt-1" />
        </label>
      </div>

      <div class="rounded-xl border border-border p-3">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p class="text-xs font-medium">Linked base models</p>
            <p class="mt-0.5 text-[10px] text-muted">Which models this LoRA belongs to.</p>
          </div>
          <AppSwitch v-model="form.modelsAuto" label="Auto-link by base" />
        </div>
        <div v-if="form.modelsAuto" class="mt-2">
          <p v-if="autoModels.length" class="flex flex-wrap items-center gap-1 text-[10px] text-muted">
            Auto:
            <Badge v-for="model in autoModels" :key="model.id" tone="accent">{{ model.label }}</Badge>
          </p>
          <p v-else class="text-[10px] text-warn">
            No base models match this base. Pick a base or turn auto-link off and select models manually.
          </p>
        </div>
        <div v-else class="mt-2 max-h-40 space-y-1 overflow-y-auto pr-1">
          <label
            v-for="model in catalog.baseModels"
            :key="model.id"
            class="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1 text-[11px] transition-colors hover:bg-surface-2"
          >
            <input
              type="checkbox"
              class="h-3.5 w-3.5 accent-[var(--c-accent)]"
              :checked="form.models.includes(model.id)"
              @change="toggleModel(model.id, $event)"
            />
            <span class="min-w-0 flex-1 truncate">{{ model.label }}</span>
            <Badge v-if="model.base" tone="neutral">{{ catalog.baseLabel(model.base) }}</Badge>
          </label>
          <p v-if="!catalog.baseModels.length" class="text-[10px] text-muted">
            No base models in the catalog. Build it from a ComfyUI folder with checkpoints first.
          </p>
        </div>
      </div>

      <label class="block text-xs">
        <span class="text-muted">Trigger words</span>
        <AppInput v-model="form.triggersText" class="mt-1" placeholder="word one, word two" />
        <span class="mt-1 block text-[10px] leading-relaxed text-muted">
          Comma-separated. These are appended to the prompt automatically when the LoRA is on. A word already in the
          prompt is never added twice.
        </span>
      </label>

      <div class="grid gap-3 sm:grid-cols-2">
        <div class="rounded-xl border border-border p-3">
          <p class="text-xs font-medium">Strength range</p>
          <p class="mt-0.5 text-[10px] text-muted">The composer's weight slider uses these bounds.</p>
          <div class="mt-2 grid grid-cols-2 gap-2">
            <label v-for="field in rangeFields" :key="field" class="text-[10px] text-muted">
              {{ field }}
              <input
                v-model.number="form.strength[field]"
                type="number"
                step="0.01"
                class="mt-0.5 h-8 w-full rounded-lg border border-border bg-surface px-2 text-xs text-text outline-none focus:border-accent/60"
              />
            </label>
          </div>
        </div>

        <div class="rounded-xl border border-border p-3">
          <div class="flex items-center justify-between gap-2">
            <div>
              <p class="text-xs font-medium">CLIP strength</p>
              <p class="mt-0.5 text-[10px] text-muted">For dual-strength LoRAs.</p>
            </div>
            <AppSwitch v-model="form.clip.enabled" />
          </div>
          <div class="mt-2 grid grid-cols-2 gap-2" :class="form.clip.enabled ? '' : 'opacity-50'">
            <label v-for="field in rangeFields" :key="field" class="text-[10px] text-muted">
              {{ field }}
              <input
                v-model.number="form.clip[field]"
                type="number"
                step="0.01"
                :disabled="!form.clip.enabled"
                class="mt-0.5 h-8 w-full rounded-lg border border-border bg-surface px-2 text-xs text-text outline-none focus:border-accent/60 disabled:cursor-not-allowed"
              />
            </label>
          </div>
        </div>
      </div>

      <details class="rounded-xl border border-border p-3">
        <summary class="cursor-pointer text-xs font-medium">Other ranges (advanced JSON)</summary>
        <p class="mt-1 text-[10px] leading-relaxed text-muted">
          Optional recommended ranges for partner knobs, consumed by module recipes. Example:
          <code class="rounded bg-surface-2 px-1">{"steps":{"default":8,"min":4,"max":16,"step":1}}</code>
        </p>
        <AppTextarea v-model="form.otherText" :rows="5" class="mt-2 font-mono text-[11px]" spellcheck="false" />
      </details>

      <label class="block text-xs">
        <span class="text-muted">Notes</span>
        <AppTextarea v-model="form.notes" :rows="2" class="mt-1" placeholder="Recommended usage, caveats, ..." />
      </label>

      <p v-if="formError" class="flex items-start gap-2 rounded-xl border border-warn/30 bg-warn/10 p-3 text-[11px] text-warn">
        <TriangleAlert class="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>{{ formError }}</span>
      </p>
    </div>
    <template #footer>
      <AppButton variant="ghost" @click="loraModal = false">Cancel</AppButton>
      <AppButton :disabled="catalog.saving === editingLora?.id" @click="saveLora">
        {{ catalog.saving === editingLora?.id ? 'Saving...' : 'Save LoRA' }}
      </AppButton>
    </template>
  </AppModal>

  <!-- model editor -->
  <AppModal v-model="modelModal" title="Edit model" :subtitle="editingModel?.name" width="520px">
    <div class="space-y-3">
      <label class="block text-xs">
        <span class="text-muted">Label</span>
        <AppInput v-model="modelForm.label" class="mt-1" placeholder="Readable name" />
      </label>
      <label class="block text-xs">
        <span class="text-muted">Base</span>
        <AppSelect v-model="modelForm.base" :options="modelBaseOptions" class="mt-1" />
        <span class="mt-1 block text-[10px] leading-relaxed text-muted">
          The family key used to match LoRAs. Change it only if the header-derived family is wrong.
        </span>
      </label>
      <label class="block text-xs">
        <span class="text-muted">Notes</span>
        <AppTextarea v-model="modelForm.notes" :rows="2" class="mt-1" />
      </label>
      <p v-if="modelError" class="rounded-xl border border-warn/30 bg-warn/10 p-3 text-[11px] text-warn">
        {{ modelError }}
      </p>
    </div>
    <template #footer>
      <AppButton variant="ghost" @click="modelModal = false">Cancel</AppButton>
      <AppButton :disabled="catalog.saving === editingModel?.id" @click="saveModel">
        {{ catalog.saving === editingModel?.id ? 'Saving...' : 'Save model' }}
      </AppButton>
    </template>
  </AppModal>
</template>
