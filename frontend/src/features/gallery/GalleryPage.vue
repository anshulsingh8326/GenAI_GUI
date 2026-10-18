<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Download, Search, Star, Trash2, Upload } from '@lucide/vue'
import { timeAgo } from '@/lib/format'
import { downloadAsset } from '@/lib/download'
import { useLibraryStore } from '@/stores/library'
import { useUiStore } from '@/stores/ui'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import Chip from '@/components/ui/Chip.vue'

const router = useRouter()
const library = useLibraryStore()
const ui = useUiStore()

const query = ref('')
const filter = ref<'all' | 'favorites'>('all')
const selectedId = ref<string | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

const filtered = computed(() =>
  library.assets.filter((a) => {
    if (filter.value === 'favorites' && !a.favorite) return false
    if (query.value && !a.prompt.toLowerCase().includes(query.value.toLowerCase())) return false
    return true
  }),
)

const selected = computed(() => (selectedId.value ? library.byId(selectedId.value) : undefined))

const emptyMessage = computed(() => {
  if (library.assets.length) return 'Nothing matches this filter.'
  return library.loaded
    ? 'The library is empty - import images or generate something.'
    : 'Library unavailable - is the backend running?'
})

function pickFiles() {
  fileInput.value?.click()
}

async function onFilesChosen(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  await library.importFiles(files)
}

function useAsReference() {
  ui.toast('Added to the Text - Image composer as a reference (mock)')
  router.push('/image/text-to-image')
}

async function removeAsset(id: string) {
  if (await library.trash(id)) selectedId.value = null
}
</script>

<template>
  <div class="mx-auto max-w-7xl px-6 py-6">
    <header class="mb-5 flex flex-wrap items-center gap-3">
      <div>
        <h1 class="text-lg font-semibold">Gallery</h1>
        <p class="text-xs text-muted">{{ library.assets.length }} assets in the local library</p>
      </div>
      <div class="flex-1" />
      <div class="relative w-64">
        <Search class="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
        <AppInput v-model="query" placeholder="Search prompts..." size="sm" class="pl-8" />
      </div>
      <Chip :active="filter === 'all'" @click="filter = 'all'">All</Chip>
      <Chip :active="filter === 'favorites'" @click="filter = 'favorites'">
        <Star class="h-3 w-3" /> Favorites
      </Chip>
      <input ref="fileInput" type="file" accept="image/*" multiple class="hidden" @change="onFilesChosen" />
      <AppButton size="sm" variant="ghost" :disabled="library.importing" @click="pickFiles">
        <Upload class="h-3.5 w-3.5" /> {{ library.importing ? 'Importing...' : 'Import' }}
      </AppButton>
    </header>

    <div class="flex flex-col gap-5 lg:flex-row">
      <!-- grid -->
      <div class="flex-1">
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
          <button
            v-for="a in filtered"
            :key="a.id"
            class="group relative cursor-pointer overflow-hidden rounded-2xl border transition-all"
            :class="selectedId === a.id ? 'border-accent ring-2 ring-accent/30' : 'border-border hover:border-accent/40'"
            @click="selectedId = a.id"
          >
            <img :src="a.thumbUrl ?? a.url" class="aspect-square w-full object-cover" alt="" />
            <div class="absolute inset-x-0 bottom-0 bg-linear-to-t from-black/55 to-transparent px-2.5 pb-2 pt-6 text-left">
              <p class="truncate text-[11px] font-medium text-white">{{ a.label }}</p>
            </div>
            <span
              class="absolute left-2 top-2 cursor-pointer rounded-lg bg-black/40 p-1.5 transition-opacity"
              :class="a.favorite ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'"
              @click.stop="library.toggleFavorite(a.id)"
            >
              <Star class="h-3.5 w-3.5" :class="a.favorite ? 'fill-amber-300 text-amber-300' : 'text-white'" />
            </span>
            <span v-if="a.nsfw" class="absolute right-2 top-2 rounded-md bg-danger/80 px-1.5 py-0.5 text-[9px] font-semibold text-white">NSFW</span>
          </button>
        </div>
        <p v-if="!filtered.length" class="py-16 text-center text-sm text-muted">{{ emptyMessage }}</p>
      </div>

      <!-- detail panel -->
      <aside v-if="selected" class="w-full shrink-0 lg:w-80">
        <div class="sticky top-4 space-y-3 rounded-2xl border border-border bg-surface p-4">
          <img :src="selected.url" class="w-full rounded-xl border border-border object-cover" alt="" />
          <p class="text-sm leading-relaxed">{{ selected.prompt }}</p>

          <div class="space-y-1.5 rounded-xl border border-border bg-surface-2/40 p-3 text-xs">
            <p class="flex justify-between gap-3"><span class="text-muted">Model</span><span class="text-right">{{ selected.model }}</span></p>
            <p class="flex justify-between gap-3"><span class="text-muted">Seed</span><span class="tabular-nums">{{ selected.seed }}</span></p>
            <p v-if="selected.width && selected.height" class="flex justify-between gap-3">
              <span class="text-muted">Size</span><span class="tabular-nums">{{ selected.width }} x {{ selected.height }}</span>
            </p>
            <p class="flex justify-between gap-3"><span class="text-muted">Created</span><span>{{ timeAgo(selected.createdAt) }}</span></p>
            <p v-if="selected.originJob" class="flex justify-between gap-3"><span class="text-muted">Job</span><span class="tabular-nums">{{ selected.originJob }}</span></p>
          </div>

          <div class="flex flex-wrap gap-1">
            <span v-for="t in selected.tags" :key="t" class="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted">{{ t }}</span>
          </div>

          <div class="flex flex-wrap gap-1.5">
            <Chip :active="selected.favorite" @click="library.toggleFavorite(selected.id)">
              <Star class="h-3 w-3" /> Favorite
            </Chip>
            <Chip @click="downloadAsset(selected)">
              <Download class="h-3 w-3" /> Download
            </Chip>
            <Chip @click="useAsReference">Use as reference</Chip>
            <Chip @click="removeAsset(selected.id)">
              <Trash2 class="h-3 w-3" /> Delete
            </Chip>
          </div>

          <AppButton block variant="ghost" @click="selectedId = null">Close</AppButton>
        </div>
      </aside>
    </div>
  </div>
</template>
