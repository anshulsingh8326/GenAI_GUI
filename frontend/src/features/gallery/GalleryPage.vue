<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  Images,
  Maximize2,
  RefreshCw,
  Search,
  Star,
  Trash2,
  Upload,
  X,
} from '@lucide/vue'
import { timeAgo } from '@/lib/format'
import { useLibraryStore } from '@/stores/library'
import { useUiStore } from '@/stores/ui'
import type { MediaViewerItem } from '@/components/media/types'
import MediaViewer from '@/components/media/MediaViewer.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import Chip from '@/components/ui/Chip.vue'
import type { Asset } from '@/types'

const library = useLibraryStore()
const ui = useUiStore()

const query = ref('')
const filter = ref<'all' | 'favorites'>('all')
const fileInput = ref<HTMLInputElement | null>(null)
const refreshing = ref(false)
const viewerOpen = ref(false)
const viewerIndex = ref(0)
const viewerItems = ref<MediaViewerItem[]>([])

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  return library.assets.filter((asset) => {
    if (filter.value === 'favorites' && !asset.favorite) return false
    if (!needle) return true
    const haystack = [
      asset.prompt,
      asset.label,
      asset.model,
      asset.originJob ?? '',
      String(asset.seed),
      ...(asset.tags ?? []),
    ]
      .join(' ')
      .toLowerCase()
    return haystack.includes(needle)
  })
})

const emptyMessage = computed(() => {
  if (query.value || filter.value !== 'all') return 'Nothing matches this search or filter.'
  return library.loaded
    ? 'The library is empty - import images or generate something.'
    : 'Library unavailable - is the backend running?'
})

function pickFiles(): void {
  fileInput.value?.click()
}

async function onFilesChosen(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  await library.importFiles(files)
}

async function refresh(): Promise<void> {
  if (refreshing.value) return
  refreshing.value = true
  const ok = await library.syncFromBackend()
  refreshing.value = false
  if (!ok) ui.toast('Could not refresh the library. Is the backend running?', 'error')
}

function clearFilters(): void {
  query.value = ''
  filter.value = 'all'
}

function viewerItem(asset: Asset): MediaViewerItem {
  const meta = [
    { label: 'Model', value: asset.model || 'Unknown' },
    { label: 'Seed', value: String(asset.seed) },
    ...(asset.width && asset.height
      ? [{ label: 'Size', value: `${asset.width} × ${asset.height}` }]
      : []),
    { label: 'Created', value: timeAgo(asset.createdAt) },
    ...(asset.originJob ? [{ label: 'Job', value: asset.originJob }] : []),
    ...(asset.tags?.length ? [{ label: 'Tags', value: asset.tags.join(', ') }] : []),
    ...(asset.nsfw ? [{ label: 'Rating', value: 'NSFW' }] : []),
  ]
  return {
    id: asset.id,
    url: asset.url,
    thumbUrl: asset.thumbUrl,
    label: asset.label || `Asset ${asset.id}`,
    prompt: asset.prompt,
    filename: `${asset.label || asset.id}.png`,
    meta,
  }
}

function openViewer(index: number): void {
  viewerItems.value = filtered.value.map(viewerItem)
  viewerIndex.value = index
  viewerOpen.value = true
}

function isViewerFavorite(item: MediaViewerItem): boolean {
  return library.byId(item.id)?.favorite ?? false
}

async function toggleViewerFavorite(item: MediaViewerItem): Promise<void> {
  if (!library.byId(item.id)) return
  await library.toggleFavorite(item.id)
}

async function deleteViewerAsset(item: MediaViewerItem): Promise<void> {
  if (!window.confirm('Move this image to the library trash? It can be restored from data/trash.')) {
    return
  }
  const removed = await library.trash(item.id)
  if (!removed) return
  viewerItems.value = viewerItems.value.filter((entry) => entry.id !== item.id)
  if (!viewerItems.value.length) {
    viewerOpen.value = false
    return
  }
  if (viewerIndex.value >= viewerItems.value.length) {
    viewerIndex.value = viewerItems.value.length - 1
  }
}

onMounted(() => {
  void refresh()
})
</script>

<template>
  <div class="mx-auto max-w-7xl px-4 py-5 sm:px-6">
    <header class="mb-5 flex flex-wrap items-center gap-3">
      <div class="min-w-0">
        <h1 class="text-lg font-semibold">Gallery</h1>
        <p class="text-xs text-muted">
          {{ library.assets.length }} assets in the local library
          <span v-if="filtered.length !== library.assets.length"> · {{ filtered.length }} shown</span>
        </p>
      </div>

      <div class="flex-1" />

      <div class="relative w-full sm:w-72">
        <Search class="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
        <AppInput
          v-model="query"
          placeholder="Search prompts, labels, models, jobs, seeds..."
          size="sm"
          class="pl-8 pr-8"
        />
        <button
          v-if="query"
          type="button"
          class="absolute right-2 top-1/2 flex h-5 w-5 -translate-y-1/2 cursor-pointer items-center justify-center rounded-md text-muted transition-colors hover:bg-surface-2 hover:text-text"
          title="Clear search"
          aria-label="Clear search"
          @click="query = ''"
        >
          <X class="h-3 w-3" />
        </button>
      </div>

      <div class="flex items-center gap-1.5">
        <Chip :active="filter === 'all'" @click="filter = 'all'">All</Chip>
        <Chip :active="filter === 'favorites'" @click="filter = 'favorites'">
          <Star class="h-3 w-3" /> Favorites
        </Chip>
      </div>

      <input
        ref="fileInput"
        type="file"
        accept="image/*"
        multiple
        class="hidden"
        @change="onFilesChosen"
      />
      <AppButton
        size="sm"
        variant="ghost"
        :disabled="refreshing"
        title="Refresh from backend"
        @click="refresh"
      >
        <RefreshCw class="h-3.5 w-3.5" :class="refreshing ? 'animate-spin' : ''" />
        {{ refreshing ? 'Refreshing...' : 'Refresh' }}
      </AppButton>
      <AppButton size="sm" variant="ghost" :disabled="library.importing" @click="pickFiles">
        <Upload class="h-3.5 w-3.5" />
        {{ library.importing ? 'Importing...' : 'Import' }}
      </AppButton>
    </header>

    <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
      <div
        v-for="(asset, index) in filtered"
        :key="asset.id"
        class="group relative overflow-hidden rounded-2xl border border-border transition-all hover:border-accent/40"
      >
        <button
          type="button"
          class="block w-full cursor-zoom-in"
          :title="asset.prompt || asset.label"
          @click="openViewer(index)"
        >
          <img
            :src="asset.thumbUrl ?? asset.url"
            :alt="asset.label || asset.prompt || 'Library image'"
            class="aspect-square w-full bg-surface-2 object-cover transition-transform duration-300 group-hover:scale-[1.02]"
            loading="lazy"
          />
          <div
            class="absolute inset-x-0 bottom-0 bg-linear-to-t from-black/70 via-black/25 to-transparent px-2.5 pb-2 pt-8 text-left"
          >
            <p class="truncate text-[11px] font-medium text-white">
              {{ asset.label || asset.prompt || asset.id }}
            </p>
            <p class="mt-0.5 truncate text-[10px] text-white/60">
              {{ asset.model || 'Unknown model' }} · {{ timeAgo(asset.createdAt) }}
            </p>
          </div>
        </button>

        <div class="absolute right-2 top-2 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
          <button
            type="button"
            class="flex h-7 w-7 cursor-pointer items-center justify-center rounded-lg border border-white/10 bg-black/45 text-white/85 backdrop-blur transition-colors hover:bg-black/70"
            :title="asset.favorite ? 'Remove from favorites' : 'Add to favorites'"
            :aria-label="asset.favorite ? 'Remove from favorites' : 'Add to favorites'"
            @click.stop="library.toggleFavorite(asset.id)"
          >
            <Star
              class="h-3.5 w-3.5"
              :class="asset.favorite ? 'fill-amber-300 text-amber-300' : ''"
            />
          </button>
          <button
            type="button"
            class="flex h-7 w-7 cursor-pointer items-center justify-center rounded-lg border border-white/10 bg-black/45 text-white/85 backdrop-blur transition-colors hover:bg-black/70"
            title="Open in viewer"
            aria-label="Open in viewer"
            @click.stop="openViewer(index)"
          >
            <Maximize2 class="h-3.5 w-3.5" />
          </button>
        </div>

        <span
          v-if="asset.favorite"
          class="pointer-events-none absolute left-2 top-2 rounded-lg bg-black/40 p-1.5"
        >
          <Star class="h-3.5 w-3.5 fill-amber-300 text-amber-300" />
        </span>
        <span
          v-if="asset.nsfw"
          class="pointer-events-none absolute right-2 top-2 rounded-md bg-danger/80 px-1.5 py-0.5 text-[9px] font-semibold text-white group-hover:opacity-0"
        >
          NSFW
        </span>
      </div>
    </div>

    <div v-if="!filtered.length" class="flex flex-col items-center py-16 text-center">
      <Images class="mb-2 h-6 w-6 text-muted" />
      <p class="text-sm text-muted">{{ emptyMessage }}</p>
      <AppButton
        v-if="query || filter !== 'all'"
        size="sm"
        variant="ghost"
        class="mt-3"
        @click="clearFilters"
      >
        Clear search and filters
      </AppButton>
    </div>

    <MediaViewer
      v-model:open="viewerOpen"
      v-model:index="viewerIndex"
      :items="viewerItems"
      title="Library"
    >
      <template #actions="{ item }">
        <template v-if="item">
          <button
            type="button"
            class="flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl text-white/70 transition-colors hover:bg-white/10 hover:text-white"
            :title="isViewerFavorite(item) ? 'Remove from favorites' : 'Add to favorites'"
            aria-label="Toggle favorite"
            @click="toggleViewerFavorite(item)"
          >
            <Star class="h-4 w-4" :class="isViewerFavorite(item) ? 'fill-current text-amber-300' : ''" />
          </button>
          <button
            type="button"
            class="flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl text-white/70 transition-colors hover:bg-white/10 hover:text-white"
            title="Move image to trash"
            aria-label="Move image to trash"
            @click="deleteViewerAsset(item)"
          >
            <Trash2 class="h-4 w-4" />
          </button>
        </template>
      </template>
    </MediaViewer>
  </div>
</template>
