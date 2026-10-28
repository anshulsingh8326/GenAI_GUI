<script setup lang="ts">
/**
 * One T2I generation rendered as a chat turn: user prompt bubble plus the
 * assistant result card (images, progress, settings, actions and deletion).
 */
import { computed, ref } from 'vue'
import {
  ChevronDown,
  Copy,
  Dices,
  Download,
  Images,
  Maximize2,
  MoreHorizontal,
  Sparkles,
  Star,
  Trash2,
  TriangleAlert,
  WandSparkles,
} from '@lucide/vue'
import type { Asset, Stage } from '@/types'
import type { MediaViewerItem } from '@/components/media/types'
import { formatTime, timeAgo } from '@/lib/format'
import { downloadAsset } from '@/lib/download'
import { useLibraryStore } from '@/stores/library'
import { useUiStore } from '@/stores/ui'
import { assetFileUrl, assetThumbUrl } from './api'
import type { T2IJobParams, T2IJobRecord } from './types'
import AppButton from '@/components/ui/AppButton.vue'
import AppPopover from '@/components/ui/AppPopover.vue'
import StageTimeline from '@/components/chat/StageTimeline.vue'

const props = defineProps<{ job: T2IJobRecord }>()
const emit = defineEmits<{
  (
    e: 'open-viewer',
    payload: { items: MediaViewerItem[]; index: number; title: string; jobId: string },
  ): void
  (e: 'delete', job: T2IJobRecord, deleteAssets: boolean): void
  (e: 'reuse', job: T2IJobRecord): void
  (e: 'use-seed', job: T2IJobRecord): void
  (e: 'cancel', job: T2IJobRecord): void
}>()

const library = useLibraryStore()
const ui = useUiStore()
const menuOpen = ref(false)
const deleteMenuOpen = ref(false)

const params = computed<Partial<T2IJobParams>>(() => props.job.params ?? {})
const isRunning = computed(
  () => props.job.status === 'queued' || props.job.status === 'running',
)
const isDone = computed(() => props.job.status === 'done')
const isError = computed(() => props.job.status === 'error')
const isTerminal = computed(() => isDone.value || isError.value)

const modelName = computed(
  () => params.value.modelShortLabel || params.value.modelName || props.job.modelName || 'Model',
)
const ratio = computed(() => params.value.ratio || '')
const baseSize = computed(() => {
  const width = params.value.width
  const height = params.value.height
  return width && height ? `${width}×${height}` : ''
})
const finalSize = computed(() => {
  const width = params.value.finalWidth
  const height = params.value.finalHeight
  return width && height ? `${width}×${height}` : ''
})
const promptUsed = computed(() => params.value.promptUsed || '')
const negativePrompt = computed(() => params.value.negativePrompt || '')
const warnings = computed(() => params.value.warnings ?? [])
const baseSeed = computed(() => Number(params.value.seed ?? props.job.seed ?? 0))
const batchSize = computed(() => {
  const value = Number(params.value.batch ?? props.job.resultIds?.length ?? 1)
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : 1
})

const resultAssets = computed<Asset[]>(() =>
  (props.job.resultIds ?? [])
    .map((id, index) => {
      const found = library.byId(id)
      if (found) return found
      // If the library has already synced and the asset is absent, the image was
      // deleted. Do not keep rendering a broken /file URL.
      if (library.loaded) return null
      return {
        id,
        url: assetFileUrl(id),
        thumbUrl: assetThumbUrl(id),
        label: `${props.job.id} result ${index + 1}`,
        prompt: props.job.prompt,
        model: props.job.modelName,
        seed: (baseSeed.value + index) & 0xffffffff,
        createdAt: props.job.createdAt,
        favorite: false,
        tags: [],
      } as Asset
    })
    .filter((asset): asset is Asset => asset != null),
)

const loraSummary = computed(() =>
  (params.value.loras ?? [])
    .map((lora) => `${lora.label} ${Number(lora.strength).toFixed(2)}`)
    .join(', '),
)

const enhanceSummary = computed(() => {
  const enhance = params.value.enhance
  if (!enhance || enhance.mode === 'off') return 'Off'
  const provider = enhance.provider ? `${enhance.provider}` : ''
  const model = enhance.model ? ` · ${enhance.model}` : ''
  return `${enhance.mode} · ${provider}${model}`
})

const upscaleSummary = computed(() => {
  const item = params.value.upscaler
  if (!item || item.kind === 'none' || !item.enabled) return 'Off'
  const value = item.value != null ? ` · ${item.value}px` : ''
  const out =
    item.outputWidth && item.outputHeight ? ` → ${item.outputWidth}×${item.outputHeight}` : ''
  return `${item.label}${value}${out}`
})

function settingsRowsFor(imageSeed?: number): Array<{ label: string; value: string }> {
  const rows: Array<{ label: string; value: string }> = []
  const add = (label: string, value: unknown): void => {
    if (value === null || value === undefined || String(value).trim() === '') return
    rows.push({ label, value: String(value) })
  }
  add('Job', props.job.id)
  add('Model', modelName.value)
  add('Recipe', params.value.recipeId || props.job.recipe)
  add('Prompt used', promptUsed.value && promptUsed.value !== props.job.prompt ? promptUsed.value : '')
  add('Negative prompt', negativePrompt.value)
  add('Ratio', ratio.value)
  add('Base size', baseSize.value)
  add('Final size', finalSize.value)
  add('Batch', params.value.batch)
  if (imageSeed != null) {
    add('Seed', imageSeed)
    if (batchSize.value > 1) add('Base seed', baseSeed.value)
  } else {
    add(batchSize.value > 1 ? 'Base seed' : 'Seed', baseSeed.value)
  }
  add('Seed randomized', params.value.seedRandomized ? 'yes' : 'no')
  add('Lock seed', params.value.lockSeed ? 'yes' : 'no')
  add('Steps', params.value.steps)
  add('CFG', params.value.cfg)
  add('Sampler', params.value.sampler)
  add('Scheduler', params.value.scheduler)
  add('Denoise', params.value.denoise)
  add('Refine', params.value.refine?.on ? 'on' : 'off')
  if (params.value.refine?.on) {
    add('Refine steps', params.value.refine.steps)
    add('Refine CFG', params.value.refine.cfg)
    add('Refine denoise', params.value.refine.denoise)
    add('Refine size', params.value.refine.scale)
  }
  add('Upscale', upscaleSummary.value)
  add('Enhancement', enhanceSummary.value)
  add('LoRAs', loraSummary.value)
  add('Triggers', (params.value.triggers ?? []).join(', '))
  add('Auto triggers', params.value.autoTriggers ? 'yes' : 'no')
  add('Engine', params.value.engine)
  add('Workflow nodes', params.value.workflowNodeCount)
  return rows
}

const settingsRows = computed(() => settingsRowsFor())

const viewerItems = computed<MediaViewerItem[]>(() =>
  resultAssets.value.map((asset, index) => {
    const seed = Number.isFinite(asset.seed) ? asset.seed : (baseSeed.value + index) & 0xffffffff
    return {
      id: asset.id,
      url: asset.url,
      thumbUrl: asset.thumbUrl,
      label: asset.label || `${props.job.id} · result ${index + 1}`,
      prompt: props.job.prompt,
      filename: `${props.job.id.replace('#', 'job-')}-${index + 1}.png`,
      meta: settingsRowsFor(seed),
    }
  }),
)

const stageRows = computed<Stage[]>(() =>
  (props.job.stages ?? []).map((stage) => ({
    id: stage.id,
    label: stage.label,
    status: stage.status,
    detail: stage.detail,
    durationMs: stage.durationMs,
  })),
)

const statusLabel = computed(() => {
  if (props.job.status === 'queued') return 'Queued'
  if (props.job.status === 'running') return 'Generating'
  if (props.job.status === 'done') return 'Ready'
  return props.job.error === 'Cancelled by user' ? 'Cancelled' : 'Failed'
})

const statusDot = computed(() => {
  if (props.job.status === 'queued') return 'bg-warn'
  if (props.job.status === 'running') return 'bg-accent animate-pulse'
  if (props.job.status === 'done') return 'bg-success'
  return 'bg-danger'
})

const resultGridClass = computed(() =>
  resultAssets.value.length > 1 ? 'grid grid-cols-2 gap-2' : 'grid grid-cols-1',
)

function isFavorite(asset: Asset): boolean {
  return library.byId(asset.id)?.favorite ?? asset.favorite
}

function toggleFavorite(asset: Asset): void {
  if (!library.byId(asset.id)) {
    ui.toast('This image is not in the Library cache yet. Refresh the Gallery and try again.', 'warn')
    return
  }
  void library.toggleFavorite(asset.id)
}

function openViewer(index: number): void {
  emit('open-viewer', {
    items: viewerItems.value,
    index,
    title: `Job ${props.job.id}`,
    jobId: props.job.id,
  })
}

function downloadAll(): void {
  resultAssets.value.forEach((asset, index) => {
    window.setTimeout(() => downloadAsset(asset), index * 120)
  })
}

async function copyText(text: string, label: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    ui.toast(`${label} copied.`, 'success')
  } catch {
    ui.toast('Clipboard access was denied.', 'warn')
  }
}

function copyPrompt(): void {
  void copyText(props.job.prompt, 'Prompt')
  menuOpen.value = false
}

function copyJob(): void {
  void copyText(JSON.stringify(props.job, null, 2), 'Job JSON')
  menuOpen.value = false
}

function reuse(): void {
  emit('reuse', props.job)
  menuOpen.value = false
}

function useSeed(): void {
  emit('use-seed', props.job)
  menuOpen.value = false
}

function remove(deleteAssets: boolean): void {
  emit('delete', props.job, deleteAssets)
  deleteMenuOpen.value = false
}

async function removeAsset(asset: Asset): Promise<void> {
  const label = asset.label || asset.id
  if (
    !window.confirm(
      `Move “${label}” to the library trash? The chat message stays, but the image leaves the Library.`,
    )
  ) {
    return
  }
  await library.trash(asset.id)
}

function cancel(): void {
  emit('cancel', props.job)
}
</script>

<template>
  <div class="space-y-3">
    <!-- user prompt -->
    <div class="flex justify-end">
      <div class="max-w-[88%] rounded-2xl rounded-br-md border border-border bg-surface px-4 py-3">
        <p class="whitespace-pre-wrap text-sm leading-relaxed">{{ job.prompt }}</p>
        <div class="mt-2 flex flex-wrap items-center justify-end gap-1.5 text-[10px] text-muted">
          <span>{{ formatTime(job.createdAt) }}</span>
          <span class="rounded-full border border-border bg-surface-2 px-2 py-0.5">{{ modelName }}</span>
          <span v-if="ratio" class="rounded-full border border-border bg-surface-2 px-2 py-0.5">
            {{ ratio }}
          </span>
          <span v-if="params.batch && params.batch > 1" class="rounded-full border border-border bg-surface-2 px-2 py-0.5">
            × {{ params.batch }}
          </span>
        </div>
      </div>
    </div>

    <!-- assistant result -->
    <div class="flex gap-2.5">
      <div class="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent">
        <Sparkles class="h-3.5 w-3.5" />
      </div>

      <div class="min-w-0 flex-1 rounded-2xl rounded-tl-md border border-border bg-surface p-3.5">
        <div class="flex flex-wrap items-center gap-2">
          <span class="h-2 w-2 rounded-full" :class="statusDot" />
          <span class="text-xs font-semibold">{{ statusLabel }}</span>
          <span class="text-[10px] text-muted">{{ job.id }}</span>
          <span class="text-[10px] text-muted">· {{ timeAgo(job.createdAt) }}</span>
          <span v-if="isRunning" class="ml-auto text-[10px] tabular-nums text-muted">
            {{ Math.max(0, Math.min(100, job.progress)) }}%
          </span>
        </div>

        <!-- running -->
        <div v-if="isRunning" class="mt-3 space-y-3">
          <div class="h-1.5 overflow-hidden rounded-full bg-border">
            <div
              class="h-full rounded-full bg-accent transition-[width] duration-500"
              :style="{ width: `${Math.max(2, Math.min(100, job.progress))}%` }"
            />
          </div>
          <StageTimeline :stages="stageRows" />
          <div class="flex justify-end">
            <AppButton size="sm" variant="ghost" @click="cancel">Cancel job</AppButton>
          </div>
        </div>

        <!-- error -->
        <div v-else-if="isError" class="mt-3 space-y-3">
          <div class="flex gap-2 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2.5">
            <TriangleAlert class="mt-0.5 h-4 w-4 shrink-0 text-danger" />
            <div class="min-w-0">
              <p class="text-xs font-medium text-danger">{{ statusLabel }}</p>
              <p class="mt-0.5 whitespace-pre-wrap text-[11px] leading-relaxed text-muted">
                {{ job.error || 'The generation failed.' }}
              </p>
            </div>
          </div>
          <StageTimeline v-if="stageRows.length" :stages="stageRows" />
        </div>

        <!-- results -->
        <div v-else-if="isDone" class="mt-3">
          <div v-if="resultAssets.length" :class="resultGridClass">
            <div
              v-for="(asset, index) in resultAssets"
              :key="asset.id"
              class="group relative overflow-hidden rounded-xl border border-border bg-black/10"
            >
              <button
                type="button"
                class="block w-full cursor-zoom-in"
                :title="`Open ${asset.label || 'image'} in the media viewer`"
                @click="openViewer(index)"
              >
                <img
                  :src="asset.thumbUrl || asset.url"
                  :alt="asset.label || `Result ${index + 1}`"
                  class="w-full bg-surface-2 object-center"
                  :class="
                    resultAssets.length > 1
                      ? 'aspect-square object-cover'
                      : 'max-h-[520px] object-contain'
                  "
                  loading="lazy"
                />
              </button>

              <div class="absolute right-2 top-2 flex gap-1">
                <button
                  type="button"
                  class="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg border border-white/10 bg-black/45 text-white/85 backdrop-blur transition-colors hover:bg-black/70"
                  :title="isFavorite(asset) ? 'Remove from favorites' : 'Add to favorites'"
                  :aria-label="isFavorite(asset) ? 'Remove from favorites' : 'Add to favorites'"
                  @click.stop="toggleFavorite(asset)"
                >
                  <Star
                    class="h-3.5 w-3.5"
                    :class="isFavorite(asset) ? 'fill-current text-warn' : ''"
                  />
                </button>
                <button
                  type="button"
                  class="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg border border-white/10 bg-black/45 text-white/85 backdrop-blur transition-colors hover:bg-black/70"
                  title="Open fullscreen viewer"
                  aria-label="Open fullscreen viewer"
                  @click.stop="openViewer(index)"
                >
                  <Maximize2 class="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  class="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg border border-white/10 bg-black/45 text-white/85 backdrop-blur transition-colors hover:bg-danger/80"
                  title="Move this image to the library trash"
                  aria-label="Move this image to the library trash"
                  @click.stop="removeAsset(asset)"
                >
                  <Trash2 class="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </div>
          <div v-else class="rounded-xl border border-border bg-surface-2/50 px-3 py-4 text-xs text-muted">
            This job has no result images. They may have been removed from the Library.
          </div>
        </div>

        <!-- warnings -->
        <div
          v-if="warnings.length"
          class="mt-3 rounded-xl border border-warn/30 bg-warn/10 px-3 py-2 text-[11px] leading-snug text-warn"
        >
          <p class="font-semibold">Warnings</p>
          <ul class="mt-1 list-disc space-y-0.5 pl-4">
            <li v-for="warning in warnings" :key="`${warning.code}-${warning.message}`">
              {{ warning.message }}
            </li>
          </ul>
        </div>

        <!-- actions -->
        <div class="mt-3 flex flex-wrap items-center gap-1.5">
          <AppButton
            v-if="resultAssets.length"
            size="sm"
            variant="soft"
            @click="openViewer(0)"
          >
            <Images class="h-3.5 w-3.5" />
            View
          </AppButton>
          <AppButton v-if="isTerminal" size="sm" variant="ghost" @click="reuse">
            <WandSparkles class="h-3.5 w-3.5" />
            Reuse
          </AppButton>
          <AppButton v-if="isTerminal" size="sm" variant="ghost" @click="useSeed">
            <Dices class="h-3.5 w-3.5" />
            Use seed
          </AppButton>
          <AppButton
            v-if="resultAssets.length"
            size="sm"
            variant="ghost"
            @click="downloadAll"
          >
            <Download class="h-3.5 w-3.5" />
            Download
          </AppButton>

          <AppPopover v-if="isTerminal" v-model="deleteMenuOpen" align="right" up width="18rem">
            <template #trigger>
              <button
                type="button"
                class="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium text-danger transition-colors hover:bg-danger/10"
                title="Delete this generation"
                @click="deleteMenuOpen = !deleteMenuOpen"
              >
                <Trash2 class="h-3.5 w-3.5" />
                Delete
              </button>
            </template>

            <div class="space-y-1">
              <p class="px-2 text-[11px] font-semibold">Delete {{ job.id }}</p>
              <button
                type="button"
                class="flex w-full cursor-pointer items-start gap-2 rounded-lg px-2 py-2 text-left transition-colors hover:bg-surface-2"
                @click="remove(false)"
              >
                <Trash2 class="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted" />
                <span class="min-w-0">
                  <span class="block text-xs font-medium text-text">Remove message only</span>
                  <span class="block text-[10px] leading-snug text-muted">
                    The result images stay in the Library.
                  </span>
                </span>
              </button>
              <button
                type="button"
                class="flex w-full cursor-pointer items-start gap-2 rounded-lg px-2 py-2 text-left transition-colors hover:bg-danger/10"
                @click="remove(true)"
              >
                <Trash2 class="mt-0.5 h-3.5 w-3.5 shrink-0 text-danger" />
                <span class="min-w-0">
                  <span class="block text-xs font-medium text-danger">Delete message + images</span>
                  <span class="block text-[10px] leading-snug text-muted">
                    Move {{ resultAssets.length }} result image{{ resultAssets.length === 1 ? '' : 's' }} to the library trash.
                  </span>
                </span>
              </button>
            </div>
          </AppPopover>

          <AppPopover v-model="menuOpen" align="right" up width="16rem">
            <template #trigger>
              <button
                type="button"
                class="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-text"
                title="More actions"
                aria-label="More actions"
                @click="menuOpen = !menuOpen"
              >
                <MoreHorizontal class="h-4 w-4" />
              </button>
            </template>

            <div class="space-y-0.5">
              <button
                type="button"
                class="flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs text-muted transition-colors hover:bg-surface-2 hover:text-text"
                @click="copyPrompt"
              >
                <Copy class="h-3.5 w-3.5" /> Copy prompt
              </button>
              <button
                type="button"
                class="flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs text-muted transition-colors hover:bg-surface-2 hover:text-text"
                @click="copyJob"
              >
                <Copy class="h-3.5 w-3.5" /> Copy job JSON
              </button>
              <button
                v-if="resultAssets.length"
                type="button"
                class="flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs text-muted transition-colors hover:bg-surface-2 hover:text-text"
                @click="downloadAll(); menuOpen = false"
              >
                <Download class="h-3.5 w-3.5" /> Download all
              </button>
            </div>
          </AppPopover>
        </div>

        <!-- full settings disclosure -->
        <details class="group mt-3 rounded-xl border border-border bg-surface-2/35">
          <summary
            class="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-[11px] font-medium text-muted [&::-webkit-details-marker]:hidden"
          >
            <span>Generation settings</span>
            <span class="truncate text-[10px] text-muted/70">
              {{ modelName }} · {{ params.steps ?? '?' }} steps · seed {{ params.seed ?? job.seed }}
            </span>
            <ChevronDown class="ml-auto h-3.5 w-3.5 transition-transform group-open:rotate-180" />
          </summary>

          <div class="space-y-3 border-t border-border px-3 py-3">
            <dl class="grid grid-cols-1 gap-x-4 gap-y-1.5 text-[11px] sm:grid-cols-2">
              <template v-for="row in settingsRows" :key="row.label">
                <dt class="text-muted">{{ row.label }}</dt>
                <dd class="break-words sm:text-right">{{ row.value }}</dd>
              </template>
            </dl>

            <div v-if="promptUsed && promptUsed !== job.prompt" class="rounded-lg border border-border bg-surface px-2.5 py-2">
              <p class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Prompt used</p>
              <p class="whitespace-pre-wrap text-[11px] leading-relaxed">{{ promptUsed }}</p>
            </div>
            <div v-if="negativePrompt" class="rounded-lg border border-border bg-surface px-2.5 py-2">
              <p class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Negative prompt</p>
              <p class="whitespace-pre-wrap text-[11px] leading-relaxed">{{ negativePrompt }}</p>
            </div>

            <details v-if="stageRows.length" class="rounded-lg border border-border bg-surface px-2.5 py-2">
              <summary class="cursor-pointer list-none text-[10px] font-semibold uppercase tracking-wide text-muted [&::-webkit-details-marker]:hidden">
                Stages
              </summary>
              <div class="mt-2">
                <StageTimeline :stages="stageRows" />
              </div>
            </details>
          </div>
        </details>
      </div>
    </div>
  </div>
</template>
