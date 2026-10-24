<script setup lang="ts">
/**
 * Reusable media viewer for GenModules.
 *
 * Supports images, video and audio, fullscreen, keyboard navigation, zoom,
 * thumbnails, optional info/metadata and per-item action slots. It knows
 * nothing about a specific module: pass `MediaViewerItem[]`, bind `open` and
 * `index`, and add module actions through the `actions` / `info` slots.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  ChevronLeft,
  ChevronRight,
  Download,
  Info,
  Maximize2,
  Minimize2,
  Volume2,
  X,
  ZoomIn,
  ZoomOut,
} from '@lucide/vue'
import type { MediaViewerItem } from './types'

const open = defineModel<boolean>('open', { default: false })
const index = defineModel<number>('index', { default: 0 })

const props = withDefaults(
  defineProps<{
    items: MediaViewerItem[]
    title?: string
    downloadable?: boolean
    showThumbs?: boolean
    info?: boolean
  }>(),
  {
    title: 'Media viewer',
    downloadable: true,
    showThumbs: true,
    info: true,
  },
)

const emit = defineEmits<{ (e: 'close'): void }>()

const root = ref<HTMLElement | null>(null)
const zoom = ref(1)
const infoOpen = ref(false)
const isFullscreen = ref(false)
let previousOverflow = ''

const current = computed(() => props.items[index.value] ?? null)
const hasNavigation = computed(() => props.items.length > 1)
const isImage = computed(
  () => current.value != null && current.value.kind !== 'video' && current.value.kind !== 'audio',
)
const zoomStyle = computed(() => {
  if (zoom.value === 1) return undefined
  return {
    width: `${Math.round(zoom.value * 100)}%`,
    maxWidth: 'none',
    maxHeight: 'none',
  }
})
const countLabel = computed(() => {
  if (!current.value) return 'No media'
  return `${index.value + 1} / ${props.items.length}`
})

function close(): void {
  open.value = false
  emit('close')
}

function select(nextIndex: number): void {
  if (!props.items.length) return
  index.value = Math.max(0, Math.min(props.items.length - 1, nextIndex))
  zoom.value = 1
}

function step(delta: number): void {
  if (!props.items.length) return
  const next = (index.value + delta + props.items.length) % props.items.length
  select(next)
}

function zoomIn(): void {
  zoom.value = Math.min(4, Math.round((zoom.value + 0.25) * 100) / 100)
}

function zoomOut(): void {
  zoom.value = Math.max(0.5, Math.round((zoom.value - 0.25) * 100) / 100)
}

function resetZoom(): void {
  zoom.value = 1
}

function toggleZoom(): void {
  zoom.value = zoom.value === 1 ? 2 : 1
}

function extension(): string {
  const item = current.value
  if (!item) return 'png'
  if (item.kind === 'video') return 'mp4'
  if (item.kind === 'audio') return 'mp3'
  const match = item.url.split('?')[0].match(/\.([a-z0-9]+)$/i)
  return match?.[1]?.toLowerCase() || 'png'
}

function safeName(): string {
  const item = current.value
  const base = item?.filename || item?.label || item?.id || 'media'
  const clean = base
    .replace(/\.[a-z0-9]+$/i, '')
    .replace(/[^\w.-]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return clean || 'media'
}

function download(): void {
  const item = current.value
  if (!item) return
  const anchor = document.createElement('a')
  anchor.href = item.url
  anchor.download = `${safeName()}.${extension()}`
  anchor.rel = 'noopener'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}

async function toggleFullscreen(): Promise<void> {
  try {
    if (!document.fullscreenElement) {
      await root.value?.requestFullscreen()
    } else {
      await document.exitFullscreen()
    }
  } catch {
    /* The browser can reject fullscreen when the request is not user-driven. */
  }
}

function syncFullscreen(): void {
  isFullscreen.value = document.fullscreenElement === root.value
}

function onKeydown(event: KeyboardEvent): void {
  if (!open.value) return
  const target = event.target as HTMLElement | null
  const editing =
    target?.tagName === 'INPUT' ||
    target?.tagName === 'TEXTAREA' ||
    target?.tagName === 'SELECT' ||
    target?.isContentEditable

  if (event.key === 'Escape') {
    event.preventDefault()
    if (document.fullscreenElement) {
      void document.exitFullscreen()
    } else {
      close()
    }
    return
  }
  if (editing) return

  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    step(-1)
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    step(1)
  } else if (event.key === '+' || event.key === '=') {
    event.preventDefault()
    zoomIn()
  } else if (event.key === '-') {
    event.preventDefault()
    zoomOut()
  } else if (event.key === '0') {
    event.preventDefault()
    resetZoom()
  } else if (event.key.toLowerCase() === 'f') {
    event.preventDefault()
    void toggleFullscreen()
  }
}

watch(
  () => props.items.length,
  (length) => {
    if (!length) {
      if (open.value) close()
      index.value = 0
      return
    }
    if (index.value >= length) index.value = length - 1
  },
)

watch(open, async (isOpen) => {
  if (isOpen) {
    previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    zoom.value = 1
    await nextTick()
    root.value?.focus()
  } else {
    document.body.style.overflow = previousOverflow
  }
})

watch(index, resetZoom)

onMounted(() => {
  infoOpen.value = window.matchMedia('(min-width: 1024px)').matches
  window.addEventListener('keydown', onKeydown)
  document.addEventListener('fullscreenchange', syncFullscreen)
})

onBeforeUnmount(() => {
  document.body.style.overflow = previousOverflow
  window.removeEventListener('keydown', onKeydown)
  document.removeEventListener('fullscreenchange', syncFullscreen)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="open && current"
        ref="root"
        class="fixed inset-0 z-50 flex flex-col bg-black/95 text-white outline-none"
        role="dialog"
        aria-modal="true"
        aria-label="Media viewer"
        tabindex="-1"
      >
        <header class="flex shrink-0 items-center gap-3 border-b border-white/10 px-3 py-2.5 sm:px-4">
          <div class="min-w-0 flex-1">
            <p class="truncate text-sm font-semibold">{{ current.label || title }}</p>
            <p class="truncate text-[11px] text-white/55">
              {{ countLabel }} <span v-if="current.kind && current.kind !== 'image'">· {{ current.kind }}</span>
            </p>
          </div>

          <div class="flex items-center gap-1">
            <slot name="actions" :item="current" />

            <button
              v-if="info"
              type="button"
              class="flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl text-white/70 transition-colors hover:bg-white/10 hover:text-white"
              :class="infoOpen ? 'bg-white/10 text-white' : ''"
              title="Toggle info"
              aria-label="Toggle info"
              @click="infoOpen = !infoOpen"
            >
              <Info class="h-4 w-4" />
            </button>
            <button
              type="button"
              class="flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl text-white/70 transition-colors hover:bg-white/10 hover:text-white"
              title="Zoom out"
              aria-label="Zoom out"
              @click="zoomOut"
            >
              <ZoomOut class="h-4 w-4" />
            </button>
            <button
              type="button"
              class="flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl text-white/70 transition-colors hover:bg-white/10 hover:text-white"
              title="Zoom in"
              aria-label="Zoom in"
              @click="zoomIn"
            >
              <ZoomIn class="h-4 w-4" />
            </button>
            <button
              type="button"
              class="hidden h-9 min-w-9 cursor-pointer items-center justify-center rounded-xl px-2 text-[11px] tabular-nums text-white/60 transition-colors hover:bg-white/10 hover:text-white sm:flex"
              title="Reset zoom"
              aria-label="Reset zoom"
              @click="resetZoom"
            >
              {{ Math.round(zoom * 100) }}%
            </button>
            <button
              v-if="downloadable"
              type="button"
              class="flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl text-white/70 transition-colors hover:bg-white/10 hover:text-white"
              title="Download"
              aria-label="Download"
              @click="download"
            >
              <Download class="h-4 w-4" />
            </button>
            <button
              type="button"
              class="flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl text-white/70 transition-colors hover:bg-white/10 hover:text-white"
              title="Fullscreen"
              aria-label="Fullscreen"
              @click="toggleFullscreen"
            >
              <Minimize2 v-if="isFullscreen" class="h-4 w-4" />
              <Maximize2 v-else class="h-4 w-4" />
            </button>
            <button
              type="button"
              class="flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl text-white/70 transition-colors hover:bg-white/10 hover:text-white"
              title="Close"
              aria-label="Close"
              @click="close"
            >
              <X class="h-5 w-5" />
            </button>
          </div>
        </header>

        <div class="relative flex min-h-0 flex-1">
          <div class="relative flex min-w-0 flex-1 items-center justify-center overflow-hidden" @click.self="close">
            <button
              v-if="hasNavigation"
              type="button"
              class="absolute left-2 top-1/2 z-10 flex h-10 w-10 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full border border-white/10 bg-black/45 text-white/85 backdrop-blur transition-colors hover:bg-black/70 sm:left-4"
              title="Previous"
              aria-label="Previous media"
              @click.stop="step(-1)"
            >
              <ChevronLeft class="h-6 w-6" />
            </button>

            <div class="flex h-full w-full items-center justify-center overflow-auto p-3 sm:p-6">
              <img
                v-if="isImage"
                :src="current.url"
                :alt="current.label || 'Media preview'"
                class="m-auto block rounded-md object-contain shadow-2xl"
                :class="zoom === 1 ? 'max-h-full max-w-full' : ''"
                :style="zoomStyle"
                @click.stop
                @dblclick="toggleZoom"
              />
              <video
                v-else-if="current.kind === 'video'"
                :src="current.url"
                controls
                autoplay
                class="m-auto max-h-full max-w-full rounded-md shadow-2xl"
                @click.stop
              />
              <div
                v-else
                class="m-auto w-full max-w-lg rounded-3xl border border-white/10 bg-white/5 p-6"
                @click.stop
              >
                <div class="mb-5 flex items-center gap-3">
                  <span class="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/10">
                    <Volume2 class="h-5 w-5" />
                  </span>
                  <div class="min-w-0">
                    <p class="truncate text-sm font-semibold">{{ current.label || 'Audio' }}</p>
                    <p class="text-[11px] text-white/55">Audio preview</p>
                  </div>
                </div>
                <audio :src="current.url" controls class="w-full" />
              </div>
            </div>

            <button
              v-if="hasNavigation"
              type="button"
              class="absolute right-2 top-1/2 z-10 flex h-10 w-10 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full border border-white/10 bg-black/45 text-white/85 backdrop-blur transition-colors hover:bg-black/70 sm:right-4"
              title="Next"
              aria-label="Next media"
              @click.stop="step(1)"
            >
              <ChevronRight class="h-6 w-6" />
            </button>
          </div>

          <aside
            v-if="info && infoOpen"
            class="absolute inset-x-0 bottom-0 z-20 max-h-[52%] overflow-y-auto border-t border-white/10 bg-black/85 p-4 backdrop-blur lg:static lg:max-h-none lg:w-80 lg:shrink-0 lg:border-l lg:border-t-0"
          >
            <div class="mb-3 flex items-center justify-between gap-2 lg:hidden">
              <p class="text-xs font-semibold uppercase tracking-wider text-white/60">Info</p>
              <button
                type="button"
                class="flex h-7 w-7 cursor-pointer items-center justify-center rounded-lg text-white/60 hover:bg-white/10 hover:text-white"
                aria-label="Close info"
                @click="infoOpen = false"
              >
                <X class="h-4 w-4" />
              </button>
            </div>
            <p v-if="current.prompt" class="whitespace-pre-wrap text-[13px] leading-relaxed text-white/85">
              {{ current.prompt }}
            </p>
            <dl v-if="current.meta?.length" class="mt-4 grid grid-cols-2 gap-x-3 gap-y-2 text-[11px]">
              <template v-for="row in current.meta" :key="row.label">
                <dt class="text-white/45">{{ row.label }}</dt>
                <dd class="break-words text-right text-white/80">{{ row.value }}</dd>
              </template>
            </dl>
            <slot name="info" :item="current" />
          </aside>
        </div>

        <footer
          v-if="showThumbs && items.length > 1"
          class="shrink-0 overflow-x-auto border-t border-white/10 px-3 py-2.5"
        >
          <div class="flex items-center justify-center gap-2">
            <button
              v-for="(item, thumbIndex) in items"
              :key="item.id"
              type="button"
              class="h-14 w-14 shrink-0 cursor-pointer overflow-hidden rounded-lg border-2 transition-all"
              :class="
                thumbIndex === index
                  ? 'border-white opacity-100'
                  : 'border-transparent opacity-45 hover:opacity-80'
              "
              :title="item.label || `Media ${thumbIndex + 1}`"
              @click="select(thumbIndex)"
            >
              <img
                v-if="item.kind !== 'video' && item.kind !== 'audio'"
                :src="item.thumbUrl || item.url"
                alt=""
                class="h-full w-full object-cover"
              />
              <span v-else class="flex h-full w-full items-center justify-center bg-white/10 text-[10px] uppercase">
                {{ item.kind }}
              </span>
            </button>
          </div>
        </footer>
      </div>
    </Transition>
  </Teleport>
</template>
