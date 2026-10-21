<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { Boxes, HardDrive, LoaderCircle, PackageSearch, RefreshCw, TriangleAlert } from '@lucide/vue'
import { useSettingsStore } from '@/stores/settings'
import { useContentStore } from '@/stores/content'
import type { ComfyModuleRequirements, ComfyModelFile, ComfyRequirementNode } from '@/types'
import Section from '@/components/ui/Section.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import Badge from '@/components/ui/Badge.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import StatusDot from '@/components/ui/StatusDot.vue'

const settings = useSettingsStore()
const content = useContentStore()

const inspect = computed(() => content.inspect)
const report = computed(() => content.requirements)
const modules = computed(() => report.value?.modules ?? [])
const core = computed(() => report.value?.core ?? null)

const totalModelFiles = computed(() => (inspect.value?.models ?? []).reduce((sum, m) => sum + m.files, 0))

const flavorLabel = computed(() => {
  const flavor = inspect.value?.flavor
  if (flavor === 'portable') return 'Portable install'
  if (flavor === 'venv') return 'Venv install'
  return 'ComfyUI install'
})

/** Decimal units - model file sizes follow the `ollama list` convention. */
function formatBytes(bytes: number): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = 0
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000
    unit += 1
  }
  return `${value >= 10 || unit === 0 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`
}

function moduleBadge(mod: ComfyModuleRequirements): { tone: 'neutral' | 'accent' | 'ok' | 'warn'; label: string } {
  if (!mod.checked) return { tone: 'neutral', label: 'Not checked' }
  const missing = mod.missingNodes + mod.missingModels
  if (missing === 0) return { tone: 'ok', label: 'Ready' }
  return { tone: 'warn', label: `${missing} missing` }
}

function nodeState(node: { installed: boolean | null; installedPath: string | null }) {
  if (node.installed === null) return { tone: 'neutral' as const, label: 'Not checked' }
  if (node.installed) return { tone: 'ok' as const, label: 'Installed' }
  if (node.installedPath) return { tone: 'warn' as const, label: 'Disabled' }
  return { tone: 'warn' as const, label: 'Missing' }
}

function modelState(model: { installed: boolean | null; sizeMatches: boolean | null }) {
  if (model.installed === null) return { tone: 'neutral' as const, label: 'Not checked' }
  if (!model.installed) return { tone: 'warn' as const, label: 'Missing' }
  if (model.sizeMatches === false) return { tone: 'warn' as const, label: 'Size mismatch' }
  return { tone: 'ok' as const, label: 'Installed' }
}

/** Core items flagged optional are recommendations - don't show them as errors. */
function coreNodeState(node: ComfyRequirementNode) {
  if (node.installed === null) return { tone: 'neutral' as const, label: 'Not checked' }
  if (node.installed) return { tone: 'ok' as const, label: 'Installed' }
  if (node.installedPath) return { tone: 'warn' as const, label: 'Disabled' }
  return node.optional
    ? { tone: 'neutral' as const, label: 'Not installed' }
    : { tone: 'warn' as const, label: 'Missing' }
}

const coreBadge = computed(() => {
  const block = core.value
  if (!block?.checked) return { tone: 'neutral' as const, label: 'Not checked' }
  const missing = block.missingNodes + block.missingModels
  if (missing === 0) return { tone: 'ok' as const, label: 'Ready' }
  return { tone: 'warn' as const, label: `${missing} missing` }
})

// -- model inventory grouped by kind -------------------------------------------

type ModelRow = ComfyModelFile & { category: string }

const MODEL_KIND_ORDER = [
  'image',
  'video',
  'audio',
  'lora',
  'vae',
  'text_encoder',
  'clip_vision',
  'controlnet',
  'upscaler',
  'embedding',
  'model_patch',
  'unknown',
]

const MODEL_KIND_LABELS: Record<string, string> = {
  image: 'Image models',
  video: 'Video models',
  audio: 'Audio models',
  lora: 'LoRAs',
  vae: 'VAEs',
  text_encoder: 'Text encoders',
  clip_vision: 'CLIP vision',
  controlnet: 'ControlNet',
  upscaler: 'Upscalers',
  embedding: 'Embeddings',
  model_patch: 'Model patches',
  unknown: 'Unclassified',
}

const modelRows = computed<ModelRow[]>(() =>
  (inspect.value?.models ?? []).flatMap((stat) =>
    stat.items.map((item) => ({ ...item, category: stat.category })),
  ),
)

const modelGroups = computed(() => {
  const groups = new Map<string, ModelRow[]>()
  for (const row of modelRows.value) {
    const list = groups.get(row.kind) ?? []
    list.push(row)
    groups.set(row.kind, list)
  }
  const known = MODEL_KIND_ORDER.filter((kind) => groups.has(kind))
  const extra = [...groups.keys()].filter((kind) => !MODEL_KIND_ORDER.includes(kind)).sort()
  return [...known, ...extra].map((kind) => ({
    kind,
    label: MODEL_KIND_LABELS[kind] ?? kind,
    items: (groups.get(kind) ?? []).slice().sort((a, b) => b.sizeBytes - a.sizeBytes),
  }))
})

/* Loose prefix compare - manifests store full SHAs, installs report 12 chars. */
function commitMatches(wanted: string, installed: string | null): boolean {
  if (!wanted || !installed) return true
  return wanted.startsWith(installed) || installed.startsWith(wanted)
}

// wait out the ~400ms settings push, then re-scan with the stored value
let folderTimer: ReturnType<typeof setTimeout> | null = null
watch(
  () => settings.comfyuiFolder,
  () => {
    if (folderTimer) clearTimeout(folderTimer)
    folderTimer = setTimeout(() => void content.refresh(), 700)
  },
)

onMounted(() => void content.refresh())
</script>

<template>
  <Section
    title="Engine content"
    desc="What the installed generation modules need from ComfyUI - custom nodes and model files - and what is already there. Read-only: this page only reports, nothing is installed or downloaded."
  >
    <!-- folder status -->
    <div class="rounded-xl border border-dashed border-border p-3">
      <div class="flex flex-wrap items-center gap-2">
        <template v-if="inspect?.valid">
          <StatusDot state="ok" />
          <span class="text-sm font-medium text-success">{{ flavorLabel }}</span>
          <span v-if="inspect.version" class="text-xs text-muted">ComfyUI v{{ inspect.version }}</span>
          <span class="text-xs text-muted">
            &middot; {{ inspect.customNodes.length }} custom node{{ inspect.customNodes.length === 1 ? '' : 's' }}
            &middot; {{ totalModelFiles }} model file{{ totalModelFiles === 1 ? '' : 's' }}
            <template v-if="inspect.pythonPath"> &middot; Python found</template>
          </span>
        </template>
        <template v-else>
          <StatusDot :state="content.checking ? 'busy' : 'off'" />
          <span class="text-sm font-medium" :class="content.checking ? 'text-muted' : 'text-warn'">
            {{ content.checking ? 'Checking...' : inspect?.error ?? 'No ComfyUI folder configured yet.' }}
          </span>
        </template>
        <div class="ml-auto">
          <AppButton variant="ghost" :disabled="content.checking" @click="content.refresh()">
            <LoaderCircle v-if="content.checking" class="h-3.5 w-3.5 animate-spin" />
            <RefreshCw v-else class="h-3.5 w-3.5" />
            Refresh
          </AppButton>
        </div>
      </div>
      <div v-if="inspect?.path" class="mt-2 truncate font-mono text-[10px] text-muted" :title="inspect.path">
        {{ inspect.path }}
      </div>
      <div v-if="!inspect?.valid" class="mt-3 flex flex-wrap items-center gap-2">
        <div class="min-w-64 flex-1">
          <AppInput
            v-model="settings.comfyuiFolder"
            placeholder="e.g. D:\ComfyUI_windows_portable\ComfyUI"
          />
        </div>
        <AppButton
          v-if="!settings.comfyuiFolder.trim() && inspect?.suggestions.length"
          variant="ghost"
          @click="settings.comfyuiFolder = inspect.suggestions[0]"
        >
          Use detected folder
        </AppButton>
      </div>
      <div v-if="!settings.comfyuiFolder.trim() && inspect?.suggestions.length" class="mt-2 text-[10px] text-muted">
        Detected from your launcher: <code class="rounded bg-surface-2 px-1 py-0.5">{{ inspect.suggestions[0] }}</code>
      </div>
      <p v-if="content.lastError" class="mt-2 text-[11px] text-warn">{{ content.lastError }}</p>
    </div>

    <!-- core baseline -->
    <div class="mt-4 rounded-xl border border-border bg-surface-2/30 p-4">
      <div class="flex flex-wrap items-center gap-2">
        <PackageSearch class="h-4 w-4 text-accent" />
        <span class="text-sm font-medium">Core requirements</span>
        <Badge :tone="coreBadge.tone">{{ coreBadge.label }}</Badge>
        <span class="text-[11px] text-muted">baseline for every module</span>
      </div>
      <p v-if="!core?.checked" class="mt-2 text-xs text-muted">
        Pick the ComfyUI folder above to check the shared baseline.
      </p>
      <div v-else class="mt-3 space-y-2">
        <div
          v-for="node in core?.nodes ?? []"
          :key="`core-node-${node.name}`"
          class="border-b border-border/50 pb-2 last:border-b-0 last:pb-0"
        >
          <div class="flex flex-wrap items-center gap-2 text-xs">
            <span class="font-medium">{{ node.name }}</span>
            <span v-if="node.optional" class="text-[10px] text-muted">recommended</span>
            <Badge :tone="coreNodeState(node).tone">{{ coreNodeState(node).label }}</Badge>
            <span
              v-if="node.installed && !commitMatches(node.commit, node.installedCommit)"
              class="text-[10px] text-muted"
            >
              installed {{ node.installedCommit }} &middot; wants {{ node.commit.slice(0, 7) }}
            </span>
          </div>
          <p v-if="node.why" class="mt-0.5 text-[10px] leading-relaxed text-muted">{{ node.why }}</p>
        </div>
        <div
          v-for="model in core?.models ?? []"
          :key="`core-model-${model.target}-${model.name}`"
          class="border-b border-border/50 pb-2 last:border-b-0 last:pb-0"
        >
          <div class="flex flex-wrap items-center gap-2 text-xs">
            <span class="font-medium">{{ model.name }}</span>
            <span class="font-mono text-[10px] text-muted">models/{{ model.target }}</span>
            <span v-if="model.optional" class="text-[10px] text-muted">recommended</span>
            <Badge :tone="modelState(model).tone">{{ modelState(model).label }}</Badge>
          </div>
          <p v-if="model.why" class="mt-0.5 text-[10px] text-muted">{{ model.why }}</p>
        </div>
      </div>
    </div>

    <!-- per-module audit -->
    <div class="mt-4">
      <EmptyState
        v-if="!modules.length"
        title="No module requirements yet"
        desc="When an installed generation module ships a requirements.json (custom nodes + model files), it shows up here and is checked against the ComfyUI folder above."
      >
        <template #icon>
          <PackageSearch class="h-5 w-5" />
        </template>
      </EmptyState>

      <div v-else class="space-y-3">
        <div v-for="mod in modules" :key="mod.id" class="rounded-xl border border-border bg-surface-2/30 p-4">
          <div class="flex flex-wrap items-center gap-2">
            <Boxes class="h-4 w-4 text-accent" />
            <span class="text-sm font-medium">{{ mod.name }}</span>
            <Badge :tone="moduleBadge(mod).tone">{{ moduleBadge(mod).label }}</Badge>
            <span class="font-mono text-[10px] text-muted">{{ mod.id }}</span>
          </div>

          <p v-if="mod.error" class="mt-2 text-xs text-warn">{{ mod.error }}</p>
          <p v-else-if="!mod.checked" class="mt-2 text-xs text-muted">
            Pick the ComfyUI folder above to check this module's requirements.
          </p>

          <div v-if="mod.nodes.length" class="mt-3">
            <p class="mb-1 text-[10px] uppercase tracking-wider text-muted">Custom nodes</p>
            <div
              v-for="node in mod.nodes"
              :key="`${mod.id}-node-${node.name}`"
              class="flex flex-wrap items-center gap-2 border-b border-border/50 py-1.5 text-xs last:border-b-0"
            >
              <span class="font-medium">{{ node.name }}</span>
              <span v-if="node.optional" class="text-[10px] text-muted">optional</span>
              <Badge :tone="nodeState(node).tone">{{ nodeState(node).label }}</Badge>
              <span
                v-if="node.installed && !commitMatches(node.commit, node.installedCommit)"
                class="text-[10px] text-muted"
              >
                installed {{ node.installedCommit }} &middot; wants {{ node.commit.slice(0, 7) }}
              </span>
            </div>
          </div>

          <div v-if="mod.models.length" class="mt-3">
            <p class="mb-1 text-[10px] uppercase tracking-wider text-muted">Model files</p>
            <div
              v-for="model in mod.models"
              :key="`${mod.id}-model-${model.target}-${model.name}`"
              class="flex flex-wrap items-center gap-2 border-b border-border/50 py-1.5 text-xs last:border-b-0"
            >
              <span class="font-medium">{{ model.name }}</span>
              <span class="font-mono text-[10px] text-muted">models/{{ model.target }}</span>
              <span v-if="model.sizeBytes" class="text-[10px] text-muted">{{ formatBytes(model.sizeBytes) }}</span>
              <span v-if="model.optional" class="text-[10px] text-muted">optional</span>
              <Badge :tone="modelState(model).tone">{{ modelState(model).label }}</Badge>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- model inventory -->
    <div class="mt-4">
      <div class="mb-2 flex flex-wrap items-center gap-2">
        <HardDrive class="h-4 w-4 text-accent" />
        <span class="text-sm font-semibold">Models in this install</span>
        <span class="text-[11px] text-muted">
          {{ modelRows.length }} file{{ modelRows.length === 1 ? '' : 's' }} &middot; kind read from the file header
        </span>
      </div>
      <EmptyState
        v-if="!modelRows.length"
        title="No model files found"
        desc="Point the ComfyUI folder above at an install with a models/ directory to see the files grouped by what they generate."
      >
        <template #icon>
          <HardDrive class="h-5 w-5" />
        </template>
      </EmptyState>
      <div v-else class="grid gap-3 lg:grid-cols-2">
        <div v-for="group in modelGroups" :key="group.kind" class="rounded-xl border border-border bg-surface-2/30 p-3">
          <div class="mb-1 flex items-center gap-2">
            <span class="text-xs font-semibold">{{ group.label }}</span>
            <span class="text-[10px] text-muted">{{ group.items.length }}</span>
          </div>
          <div
            v-for="item in group.items"
            :key="`${item.category}-${item.name}`"
            class="border-b border-border/50 py-1.5 text-[11px] last:border-b-0 last:pb-0"
          >
            <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span class="font-medium">{{ item.name }}</span>
              <span class="text-[10px] text-muted">{{ formatBytes(item.sizeBytes) }}</span>
              <span
                v-if="item.arch"
                class="rounded bg-surface-2 px-1 py-0.5 font-mono text-[9px] text-muted"
              >{{ item.arch }}</span>
              <span class="text-[9px] text-muted">models/{{ item.category }}</span>
            </div>
            <div
              v-if="item.base || item.triggers.length"
              class="mt-0.5 flex flex-wrap items-center gap-2 text-[10px] text-muted"
            >
              <span v-if="item.base">for {{ item.base }}</span>
              <span v-if="item.triggers.length" class="truncate" :title="item.triggers.join(', ')">
                triggers: {{ item.triggers.join(', ') }}
              </span>
            </div>
            <p v-if="item.suggestedCategory" class="mt-0.5 flex items-center gap-1 text-[10px] text-warn">
              <TriangleAlert class="h-3 w-3 shrink-0" />
              stored in models/{{ item.category }} - belongs in models/{{ item.suggestedCategory }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <p class="mt-4 text-[11px] leading-relaxed text-muted">
      Matching is by custom-node folder / git origin and by model filename under the target folder (plus size when the
      manifest has one). Model kinds, LoRA bases and trigger words come from safetensors / GGUF headers only - no model
      is loaded. Hashes are verified at download time in a later phase. Plan:
      <code class="rounded bg-surface-2 px-1 py-0.5">docs/COMFYUI_CONTENT.md</code>.
    </p>
  </Section>
</template>
