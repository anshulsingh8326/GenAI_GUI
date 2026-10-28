<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ChevronDown,
  Dices,
  Download,
  Images,
  Maximize2,
  MoreHorizontal,
  Sparkles,
  Star,
  Trash2,
  TriangleAlert,
} from '@lucide/vue'
import type { Asset, Stage } from '@/types'
import type { MediaViewerItem } from '@/components/media/types'
import { formatTime, timeAgo } from '@/lib/format'
import { downloadAsset } from '@/lib/download'
import { useLibraryStore } from '@/stores/library'
import StageTimeline from '@/components/chat/StageTimeline.vue'
import AppPopover from '@/components/ui/AppPopover.vue'
import { assetFileUrl, assetThumbUrl } from './api'
import type { TemplateJobRecord } from './types'

const props = defineProps<{ job: TemplateJobRecord }>()
const emit = defineEmits<{
  (e: 'open-viewer', payload: { items: MediaViewerItem[]; index: number; title: string; jobId: string }): void
  (e: 'trash-asset', assetId: string): void
  (e: 'delete', deleteAssets: boolean): void
  (e: 'reuse', job: TemplateJobRecord): void
  (e: 'use-seed', job: TemplateJobRecord): void
  (e: 'cancel', jobId: string): void
}>()

const library = useLibraryStore()
const deleteMenuOpen = ref(false)

const active = computed(() => props.job.status === 'queued' || props.job.status === 'running')
const progress = computed(() => Math.max(0, Math.min(100, props.job.progress || 0)))
const statusLabel = computed(() => {
  switch (props.job.status) {
    case 'queued':
      return 'Queued'
    case 'running':
      return 'Rendering'
    case 'done':
      return 'Done'
    case 'error':
      return 'Failed'
    default:
      return 'Unknown'
  }
})
const statusDot = computed(() => {
  switch (props.job.status) {
    case 'done':
      return 'bg-success'
    case 'error':
      return 'bg-danger'
    case 'running':
      return 'bg-accent'
    default:
      return 'bg-border'
  }
})
const stageRows = computed<Stage[]>(() =>
  (props.job.stages ?? []).map((stage) => ({
    id: stage.id,
    label: stage.label,
    status: stage.status,
    detail: stage.detail,
    durationMs: stage.durationMs ?? undefined,
  })),
)
const params = computed(() => props.job.params ?? ({} as TemplateJobRecord['params']))
const accentLabel = computed(() => {
  const raw = String(params.value.accent || 'lavender')
  return raw.charAt(0).toUpperCase() + raw.slice(1)
})

function fallbackAsset(assetId: string): Asset {
  return {
    id: assetId,
    url: assetFileUrl(assetId),
    thumbUrl: assetThumbUrl(assetId),
    label: `${props.job.id} result`,
    prompt: props.job.prompt,
    model: props.job.modelName,
    seed: props.job.seed,
    createdAt: props.job.createdAt,
    favorite: false,
    tags: [],
  }
}

const resultAssets = computed<Asset[]>(() => {
  const found = props.job.resultIds
    .map((assetId) => library.byId(assetId))
    .filter((asset): asset is Asset => Boolean(asset))
  if (library.loaded) return found
  const byId = new Map(found.map((asset) => [asset.id, asset]))
  return props.job.resultIds.map((assetId) => byId.get(assetId) ?? fallbackAsset(assetId))
})

const viewerItems = computed<MediaViewerItem[]>(() =>
  resultAssets.value.map((asset, index) => ({
    id: asset.id,
    url: asset.url,
    thumbUrl: asset.thumbUrl,
    kind: 'image',
    label: `${props.job.id} - result ${index + 1}`,
    prompt: props.job.prompt,
    filename: `${props.job.id.replace(/^#/, 'job-')}-${index + 1}.svg`,
    meta: [
      { label: 'Model', value: props.job.modelName },
      { label: 'Seed', value: String(asset.seed || props.job.seed) },
      { label: 'Size', value: `${params.value.width} x ${params.value.height}` },
    ],
  })),
)

function openViewer(index: number): void {
  if (!viewerItems.value.length) return
  emit('open-viewer', {
    items: viewerItems.value,
    index,
    title: `${props.job.id} - ${props.job.modelName}`,
    jobId: props.job.id,
  })
}

function chooseDelete(deleteAssets: boolean): void {
  deleteMenuOpen.value = false
  emit('delete', deleteAssets)
}

function downloadFirst(): void {
  const asset = resultAssets.value[0]
  if (asset) downloadAsset(asset)
}

function toggleFavorite(asset: Asset): void {
  void library.toggleFavorite(asset.id)
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
          <span class="rounded-full border border-border bg-surface-2 px-2 py-0.5">{{ job.modelName }}</span>
          <span class="rounded-full border border-border bg-surface-2 px-2 py-0.5">
            {{ params.width }} x {{ params.height }}
          </span>
          <span v-if="params.batch > 1" class="rounded-full border border-border bg-surface-2 px-2 py-0.5">
            x {{ params.batch }}
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
        <div class="flex flex-wrap items-center gap-2 text-[11px]">
          <span class="h-1.5 w-1.5 rounded-full" :class="statusDot" />
          <span class="font-semibold">{{ statusLabel }}</span>
          <span class="text-muted">{{ job.id }}</span>
          <span class="text-muted">{{ timeAgo(job.createdAt) }}</span>
          <span class="ml-auto tabular-nums text-muted">{{ progress }}%</span>
        </div>

        <div v-if="job.status === 'running'" class="mt-2.5">
          <div class="h-1.5 overflow-hidden rounded-full bg-border">
            <div class="h-full rounded-full bg-accent transition-all" :style="{ width: `${progress}%` }" />
          </div>
        </div>

        <p v-if="job.error" class="mt-3 flex items-start gap-2 rounded-xl border border-danger/25 bg-danger/10 p-2.5 text-xs text-danger">
          <TriangleAlert class="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{{ job.error }}</span>
        </p>

        <div v-if="stageRows.length && (active || job.status === 'error')" class="mt-3 rounded-xl border border-border bg-surface-2/40 p-2.5">
          <StageTimeline :stages="stageRows" />
        </div>

        <div v-if="resultAssets.length" class="mt-3 grid gap-2 sm:grid-cols-2">
          <div
            v-for="(asset, index) in resultAssets"
            :key="asset.id"
            class="group relative overflow-hidden rounded-xl border border-border bg-surface-2"
          >
            <button type="button" class="block w-full cursor-zoom-in" @click="openViewer(index)">
              <img
                :src="asset.thumbUrl || asset.url"
                :alt="`${job.id} result ${index + 1}`"
                class="aspect-square w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
                loading="lazy"
              />
              <span class="absolute inset-0 flex items-center justify-center bg-black/35 opacity-0 transition-opacity group-hover:opacity-100">
                <Maximize2 class="h-5 w-5 text-white" />
              </span>
            </button>
            <div class="absolute right-1.5 top-1.5 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
              <button
                type="button"
                class="flex h-7 w-7 cursor-pointer items-center justify-center rounded-lg bg-black/55 text-white backdrop-blur hover:bg-black/75"
                :title="asset.favorite ? 'Remove favorite' : 'Favorite'"
                @click.stop="toggleFavorite(asset)"
              >
                <Star class="h-3.5 w-3.5" :class="asset.favorite ? 'fill-current text-warn' : ''" />
              </button>
              <button
                type="button"
                class="flex h-7 w-7 cursor-pointer items-center justify-center rounded-lg bg-black/55 text-white backdrop-blur hover:bg-danger/90"
                title="Move this image to the library trash"
                @click.stop="emit('trash-asset', asset.id)"
              >
                <Trash2 class="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>

        <div v-else-if="job.status === 'done'" class="mt-3 rounded-xl border border-dashed border-border p-4 text-center text-xs text-muted">
          <Images class="mx-auto mb-1.5 h-4 w-4" />
          Results are no longer in the Library.
        </div>

        <div class="mt-3 flex flex-wrap items-center gap-1.5 border-t border-border/70 pt-2.5 text-[11px]">
          <button
            v-if="resultAssets.length"
            type="button"
            class="inline-flex h-7 cursor-pointer items-center gap-1 rounded-lg px-2 text-muted transition-colors hover:bg-surface-2 hover:text-text"
            @click="openViewer(0)"
          >
            <Maximize2 class="h-3.5 w-3.5" /> View
          </button>
          <button
            type="button"
            class="inline-flex h-7 cursor-pointer items-center gap-1 rounded-lg px-2 text-muted transition-colors hover:bg-surface-2 hover:text-text"
            @click="emit('reuse', job)"
          >
            Reuse
          </button>
          <button
            type="button"
            class="inline-flex h-7 cursor-pointer items-center gap-1 rounded-lg px-2 text-muted transition-colors hover:bg-surface-2 hover:text-text"
            @click="emit('use-seed', job)"
          >
            <Dices class="h-3.5 w-3.5" /> Use seed
          </button>
          <button
            v-if="resultAssets.length"
            type="button"
            class="inline-flex h-7 cursor-pointer items-center gap-1 rounded-lg px-2 text-muted transition-colors hover:bg-surface-2 hover:text-text"
            @click="downloadFirst"
          >
            <Download class="h-3.5 w-3.5" /> Download
          </button>

          <button
            v-if="active"
            type="button"
            class="ml-auto inline-flex h-7 cursor-pointer items-center gap-1 rounded-lg px-2 text-danger transition-colors hover:bg-danger/10"
            @click="emit('cancel', job.id)"
          >
            Cancel
          </button>

          <AppPopover
            v-else
            v-model="deleteMenuOpen"
            align="right"
            width="16rem"
          >
            <template #trigger>
              <button
                type="button"
                class="ml-auto inline-flex h-7 cursor-pointer items-center gap-1 rounded-lg px-2 text-muted transition-colors hover:bg-surface-2 hover:text-text"
                title="Delete this message"
                @click="deleteMenuOpen = !deleteMenuOpen"
              >
                <MoreHorizontal class="h-3.5 w-3.5" /> Delete
              </button>
            </template>
            <div class="space-y-1">
              <button
                type="button"
                class="w-full cursor-pointer rounded-lg px-2.5 py-2 text-left text-xs text-text transition-colors hover:bg-surface-2"
                @click="chooseDelete(false)"
              >
                Remove message only
                <span class="mt-0.5 block text-[10px] text-muted">Results stay in the Library.</span>
              </button>
              <button
                type="button"
                class="w-full cursor-pointer rounded-lg px-2.5 py-2 text-left text-xs text-danger transition-colors hover:bg-danger/10"
                @click="chooseDelete(true)"
              >
                Delete message + images
                <span class="mt-0.5 block text-[10px] text-muted">Results move to the library trash.</span>
              </button>
            </div>
          </AppPopover>

          <details class="group ml-0 w-full sm:ml-auto sm:w-auto">
            <summary class="inline-flex h-7 cursor-pointer list-none items-center gap-1 rounded-lg px-2 text-muted transition-colors hover:bg-surface-2 hover:text-text [&::-webkit-details-marker]:hidden">
              <ChevronDown class="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
              Settings
            </summary>
            <div class="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-xl border border-border bg-surface-2/40 p-2.5 text-[11px] sm:col-span-2">
              <span class="text-muted">Accent</span><span>{{ accentLabel }}</span>
              <span class="text-muted">Size</span><span>{{ params.width }} x {{ params.height }}</span>
              <span class="text-muted">Batch</span><span>{{ params.batch }}</span>
              <span class="text-muted">Seed</span><span class="tabular-nums">{{ params.seed }}</span>
              <span class="text-muted">Locked seed</span><span>{{ params.lockSeed ? 'Yes' : 'No' }}</span>
              <span class="text-muted">Recipe</span><span class="truncate">{{ job.recipe }}</span>
            </div>
          </details>
        </div>
      </div>
    </div>
  </div>
</template>
