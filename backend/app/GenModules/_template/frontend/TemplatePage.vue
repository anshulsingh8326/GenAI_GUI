<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { storeToRefs } from 'pinia'
import {
  ArrowDown,
  ChevronDown,
  Images,
  LoaderCircle,
  Settings2,
  Sparkles,
  Star,
  Trash2,
  TriangleAlert,
  X,
} from '@lucide/vue'
import { useTemplateStore } from './store'
import { useLibraryStore } from '@/stores/library'
import MediaViewer from '@/components/media/MediaViewer.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppPopover from '@/components/ui/AppPopover.vue'
import Chip from '@/components/ui/Chip.vue'
import TemplateGenerationCard from './TemplateGenerationCard.vue'
import TemplateSettingsPanel from './TemplateSettingsPanel.vue'
import type { TemplateJobRecord } from './types'
import type { MediaViewerItem } from '@/components/media/types'

const store = useTemplateStore()
const library = useLibraryStore()
const {
  catalog,
  loading,
  loadError,
  actionError,
  jobsError,
  jobSyncError,
  warnings,
  submitting,
  jobsLoading,
  jobs,
  canGenerate,
  busy,
  lastSavedAt,
  storageError,
  promptLimit,
  selectedAccent,
} = storeToRefs(store)

const scroller = ref<HTMLElement | null>(null)
const promptInput = ref<HTMLTextAreaElement | null>(null)
const nearBottom = ref(true)
const settingsOpen = ref(
  typeof window !== 'undefined' && window.matchMedia('(min-width: 1024px)').matches,
)

const viewerOpen = ref(false)
const viewerIndex = ref(0)
const viewerItems = ref<MediaViewerItem[]>([])
const viewerTitle = ref('Media viewer')
const viewerJobId = ref('')
const clearMenuOpen = ref(false)
const clearing = ref(false)

const suggestions = [
  'A calm lavender gradient with a soft grain',
  'Mint geometric card with a single circle',
  'Peach sunrise poster, minimal typography',
]
const charCount = computed(() => store.form.prompt.length)
const promptTooLong = computed(() => charCount.value > promptLimit.value)
const canSend = computed(() => canGenerate.value && !promptTooLong.value)
const visibleWarnings = computed(() => {
  const seen = new Set<string>()
  return warnings.value.filter((warning) => {
    const key = `${warning.code}:${warning.message}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
})
const autosaveLabel = computed(() =>
  lastSavedAt.value ? 'Saved in this browser' : 'Autosave ready',
)

function scrollToBottom(behavior: ScrollBehavior = 'smooth'): void {
  const element = scroller.value
  if (!element) return
  element.scrollTo({ top: element.scrollHeight, behavior })
  nearBottom.value = true
}

function onScroll(): void {
  const element = scroller.value
  if (!element) return
  nearBottom.value =
    element.scrollHeight - element.scrollTop - element.clientHeight < 90
}

function jumpToBottom(): void {
  scrollToBottom()
}

function pickSuggestion(text: string): void {
  store.form.prompt = text
  promptInput.value?.focus()
}

function handlePromptKeydown(event: KeyboardEvent): void {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault()
    void generate()
  }
}

async function generate(): Promise<void> {
  if (!canSend.value) return
  await store.generate()
  await nextTick()
  scrollToBottom()
  promptInput.value?.focus()
}

async function clearHistory(deleteAssets: boolean): Promise<void> {
  clearMenuOpen.value = false
  if (clearing.value) return
  const message = deleteAssets
    ? 'Clear all Template chat messages and move their result images to the library trash? This only affects Template.'
    : 'Clear all Template chat messages? Their result images stay in the Library.'
  if (!window.confirm(message)) return
  clearing.value = true
  const result = await store.clearHistory(deleteAssets)
  clearing.value = false
  if (result && result.jobIds.includes(viewerJobId.value)) closeViewer()
}

async function deleteJob(job: TemplateJobRecord, deleteAssets: boolean): Promise<void> {
  const message = deleteAssets
    ? 'Delete this message and move its images to the library trash? This only affects Template.'
    : 'Remove this message? Its images stay in the Library.'
  if (!window.confirm(message)) return
  const result = await store.deleteJob(job.id, deleteAssets)
  if (result && viewerJobId.value === job.id) closeViewer()
}

function reuseJob(job: TemplateJobRecord): void {
  store.applyJobSettings(job)
  settingsOpen.value = true
  void nextTick(() => promptInput.value?.focus())
}

function useJobSeed(job: TemplateJobRecord): void {
  store.useJobSeed(job)
}

function cancelJob(jobId: string): void {
  void store.cancelJob(jobId)
}

function openViewer(payload: {
  items: MediaViewerItem[]
  index: number
  title: string
  jobId: string
}): void {
  viewerItems.value = payload.items
  viewerIndex.value = payload.index
  viewerTitle.value = payload.title
  viewerJobId.value = payload.jobId
  viewerOpen.value = true
}

function closeViewer(): void {
  viewerOpen.value = false
  viewerJobId.value = ''
}

function removeViewerAsset(assetId: string): void {
  if (!viewerOpen.value) return
  const index = viewerItems.value.findIndex((item) => item.id === assetId)
  if (index < 0) return
  viewerItems.value = viewerItems.value.filter((item) => item.id !== assetId)
  if (!viewerItems.value.length) {
    closeViewer()
    return
  }
  if (viewerIndex.value >= viewerItems.value.length) {
    viewerIndex.value = viewerItems.value.length - 1
  }
}

async function trashAsset(assetId: string): Promise<void> {
  if (!window.confirm('Move this image to the library trash? The chat message stays.')) return
  const ok = await library.trash(assetId)
  if (ok) removeViewerAsset(assetId)
}

function isFavorite(assetId: string): boolean {
  return library.byId(assetId)?.favorite === true
}

function toggleFavorite(item: MediaViewerItem | null): void {
  if (item) void library.toggleFavorite(item.id)
}

watch(
  () => jobs.value.length,
  async () => {
    if (!nearBottom.value) return
    await nextTick()
    scrollToBottom()
  },
)

watch(
  () => store.form.prompt,
  () => store.clearActionError(),
)

onMounted(() => {
  void store.loadCatalog()
  void store.loadJobs()
  void library.syncFromBackend()
  void nextTick(() => scrollToBottom('auto'))
})

onBeforeUnmount(() => {
  store.flushPersist()
})
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-bg text-text">
    <header class="flex shrink-0 flex-wrap items-center gap-3 border-b border-border px-4 py-3">
      <div class="min-w-0">
        <p class="text-[10px] font-semibold uppercase tracking-[0.2em] text-accent">Template</p>
        <h1 class="text-lg font-semibold leading-tight">Starter workspace</h1>
      </div>

      <div class="ml-auto flex flex-wrap items-center justify-end gap-1.5 text-[11px]">
        <span class="inline-flex h-7 items-center gap-1.5 rounded-full border border-border bg-surface px-2.5">
          <span
            class="h-1.5 w-1.5 rounded-full"
            :class="loading ? 'bg-muted' : catalog ? 'bg-success' : 'bg-danger'"
          />
          {{ loading ? 'Checking controls' : catalog ? 'Renderer ready' : 'Backend offline' }}
        </span>
        <span class="hidden h-7 items-center rounded-full border border-border bg-surface px-2.5 text-muted sm:inline-flex">
          {{ selectedAccent }}
        </span>
        <RouterLink
          to="/gallery"
          class="inline-flex h-7 items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 text-muted transition-colors hover:border-accent/40 hover:text-text"
        >
          <Images class="h-3.5 w-3.5" /> Gallery
        </RouterLink>

        <AppPopover v-model="clearMenuOpen" align="right" width="17rem">
          <template #trigger>
            <button
              type="button"
              class="inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 text-muted transition-colors hover:border-accent/40 hover:text-text disabled:cursor-not-allowed disabled:opacity-40"
              :disabled="!jobs.length || clearing || busy"
              @click="clearMenuOpen = !clearMenuOpen"
            >
              <Trash2 class="h-3.5 w-3.5" />
              {{ clearing ? 'Clearing...' : 'Clear' }}
            </button>
          </template>
          <div class="space-y-1">
            <button
              type="button"
              class="w-full cursor-pointer rounded-lg px-2.5 py-2 text-left text-xs text-text transition-colors hover:bg-surface-2"
              @click="clearHistory(false)"
            >
              Clear chat
              <span class="mt-0.5 block text-[10px] text-muted">Keep every result image in the Library.</span>
            </button>
            <button
              type="button"
              class="w-full cursor-pointer rounded-lg px-2.5 py-2 text-left text-xs text-danger transition-colors hover:bg-danger/10"
              @click="clearHistory(true)"
            >
              Clear chat + media
              <span class="mt-0.5 block text-[10px] text-muted">Move this module's result images to the library trash.</span>
            </button>
          </div>
        </AppPopover>

        <button
          type="button"
          class="inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-full border px-2.5 transition-colors"
          :class="settingsOpen ? 'border-accent/45 bg-accent-soft text-accent' : 'border-border bg-surface text-muted hover:border-accent/40 hover:text-text'"
          @click="settingsOpen = !settingsOpen"
        >
          <Settings2 class="h-3.5 w-3.5" /> Settings
        </button>
      </div>
    </header>

    <div class="flex min-h-0 flex-1">
      <section class="relative flex min-w-0 flex-1 flex-col">
        <div ref="scroller" class="min-h-0 flex-1 overflow-y-auto px-3 py-4 sm:px-4" @scroll="onScroll">
          <div class="mx-auto w-full max-w-3xl space-y-5">
            <div v-if="loading" class="flex items-center justify-center gap-2 rounded-2xl border border-border bg-surface p-8 text-xs text-muted">
              <LoaderCircle class="h-4 w-4 animate-spin" /> Loading the Template controls...
            </div>

            <div v-else-if="loadError" class="rounded-2xl border border-danger/30 bg-danger/10 p-4 text-xs text-danger">
              <p class="font-medium">{{ loadError }}</p>
              <AppButton variant="soft" size="sm" class="mt-2" @click="store.loadCatalog()">Retry</AppButton>
            </div>

            <div
              v-else-if="catalog && !jobs.length && !jobsLoading"
              class="rounded-2xl border border-border bg-surface p-6 text-center"
            >
              <div class="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-accent-soft text-accent">
                <Sparkles class="h-5 w-5" />
              </div>
              <h2 class="mt-3 text-base font-semibold">A complete starter, not a model</h2>
              <p class="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted">
                Generate a deterministic SVG card to verify jobs, stages, the library, history,
                deletion and autosave. Replace <code class="rounded bg-surface-2 px-1 py-0.5 text-text">_render_svg</code>
                in the backend service with your engine pipeline to make it real.
              </p>
              <div class="mt-4 flex flex-wrap justify-center gap-1.5">
                <Chip v-for="suggestion in suggestions" :key="suggestion" @click="pickSuggestion(suggestion)">
                  {{ suggestion }}
                </Chip>
              </div>
            </div>

            <div v-else-if="!catalog" class="rounded-2xl border border-border bg-surface p-6 text-center text-xs text-muted">
              The Template backend is not reachable. Start the backend and retry.
            </div>

            <div v-if="jobsError" class="rounded-xl border border-warn/30 bg-warn/10 p-2.5 text-xs text-warn">
              {{ jobsError }}
            </div>
            <p v-if="jobSyncError" class="rounded-xl border border-warn/30 bg-warn/10 p-2.5 text-xs text-warn">
              {{ jobSyncError }}
            </p>

            <div v-if="jobsLoading && !jobs.length" class="flex items-center justify-center gap-2 p-6 text-xs text-muted">
              <LoaderCircle class="h-4 w-4 animate-spin" /> Loading history...
            </div>

            <TemplateGenerationCard
              v-for="job in jobs"
              :key="job.id"
              :job="job"
              @open-viewer="openViewer"
              @trash-asset="trashAsset"
              @delete="(deleteAssets) => deleteJob(job, deleteAssets)"
              @reuse="reuseJob"
              @use-seed="useJobSeed"
              @cancel="cancelJob"
            />

            <div v-if="actionError" class="flex items-start gap-2 rounded-xl border border-danger/30 bg-danger/10 p-3 text-xs text-danger">
              <TriangleAlert class="mt-0.5 h-4 w-4 shrink-0" />
              <p class="flex-1">{{ actionError }}</p>
              <button type="button" class="cursor-pointer opacity-70 hover:opacity-100" @click="store.clearActionError()">
                <X class="h-3.5 w-3.5" />
              </button>
            </div>

            <div v-if="visibleWarnings.length" class="rounded-xl border border-warn/30 bg-warn/10 p-3 text-[11px] text-warn">
              <p v-for="warning in visibleWarnings" :key="`${warning.code}:${warning.message}`">
                {{ warning.message }}
              </p>
            </div>
          </div>
        </div>

        <button
          v-if="!nearBottom && jobs.length"
          type="button"
          class="absolute bottom-28 left-1/2 z-10 flex h-8 w-8 -translate-x-1/2 cursor-pointer items-center justify-center rounded-full border border-border bg-surface text-muted shadow-lg transition-colors hover:text-text"
          title="Jump to latest"
          @click="jumpToBottom"
        >
          <ArrowDown class="h-4 w-4" />
        </button>

        <div class="shrink-0 border-t border-border bg-surface/80 px-3 py-3 backdrop-blur sm:px-4">
          <div class="mx-auto w-full max-w-3xl">
            <div class="rounded-2xl border border-border bg-surface p-2.5 shadow-sm focus-within:border-accent/50">
              <textarea
                ref="promptInput"
                v-model="store.form.prompt"
                rows="3"
                :maxlength="promptLimit"
                class="w-full resize-none bg-transparent px-1.5 py-1 text-sm leading-relaxed text-text outline-none placeholder:text-muted/60"
                placeholder="Describe the card you want the starter to render..."
                @keydown="handlePromptKeydown"
              />
              <div class="mt-1.5 flex flex-wrap items-center gap-2 border-t border-border/70 pt-2 text-[10px] text-muted">
                <span>{{ charCount }} / {{ promptLimit }}</span>
                <span class="hidden sm:inline">{{ autosaveLabel }}</span>
                <span v-if="promptTooLong" class="text-danger">Shorten the prompt to generate.</span>
                <span class="ml-auto hidden sm:inline">Ctrl+Enter to generate</span>
                <AppButton
                  variant="primary"
                  size="sm"
                  :disabled="!canSend"
                  @click="generate"
                >
                  <LoaderCircle v-if="submitting || busy" class="h-3.5 w-3.5 animate-spin" />
                  {{ busy ? 'Working...' : submitting ? 'Starting...' : 'Generate' }}
                </AppButton>
              </div>
            </div>
            <div class="mt-1.5 flex flex-wrap items-center gap-1.5">
              <Chip :active="settingsOpen" @click="settingsOpen = !settingsOpen">
                <Settings2 class="h-3 w-3" /> Output settings
              </Chip>
              <Chip @click="jumpToBottom">Jump to latest</Chip>
              <span v-if="storageError" class="text-[10px] text-warn">{{ storageError }}</span>
            </div>
          </div>
        </div>
      </section>

      <aside
        v-if="settingsOpen"
        class="hidden w-[380px] shrink-0 border-l border-border lg:block"
      >
        <TemplateSettingsPanel @close="settingsOpen = false" />
      </aside>
    </div>

    <div v-if="settingsOpen" class="fixed inset-0 z-30 lg:hidden">
      <div class="absolute inset-0 bg-black/45" @click="settingsOpen = false" />
      <aside class="absolute right-0 top-0 h-full w-[min(92vw,400px)] border-l border-border bg-surface shadow-2xl">
        <TemplateSettingsPanel @close="settingsOpen = false" />
      </aside>
    </div>

    <MediaViewer
      v-model:open="viewerOpen"
      v-model:index="viewerIndex"
      :items="viewerItems"
      :title="viewerTitle"
      @close="closeViewer"
    >
      <template #actions="{ item }">
        <button
          v-if="item"
          type="button"
          class="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 text-xs text-muted transition-colors hover:text-text"
          @click="toggleFavorite(item)"
        >
          <Star class="h-3.5 w-3.5" :class="isFavorite(item.id) ? 'fill-current text-warn' : ''" />
          {{ isFavorite(item.id) ? 'Favorited' : 'Favorite' }}
        </button>
      </template>
    </MediaViewer>
  </div>
</template>
