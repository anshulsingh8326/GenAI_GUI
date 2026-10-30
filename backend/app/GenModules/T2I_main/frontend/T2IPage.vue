<script setup lang="ts">
/**
 * T2I_main - compact chat workspace.
 *
 * One conversation per module: prompts and results are chat messages, settings
 * live in a persistent drawer, and generated images open in the shared media
 * viewer. Form state, including prompts and LoRA choices, is owned by the
 * module store and survives route switches/reloads.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { storeToRefs } from 'pinia'
import {
  ArrowDown,
  ChevronDown,
  Download,
  Images,
  RotateCcw,
  Settings2,
  Sparkles,
  Star,
  Trash2,
  TriangleAlert,
  X,
} from '@lucide/vue'
import { useT2IStore } from './store'
import { t2iApi } from './api'
import { useLibraryStore } from '@/stores/library'
import { useUiStore } from '@/stores/ui'
import type { MediaViewerItem } from '@/components/media/types'
import MediaViewer from '@/components/media/MediaViewer.vue'
import ModuleSetupModal from '@/components/content/ModuleSetupModal.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppPopover from '@/components/ui/AppPopover.vue'
import T2IGenerationCard from './T2IGenerationCard.vue'
import T2ISettingsPanel from './T2ISettingsPanel.vue'
import type { ModuleSetupPayload, T2IJobRecord } from './types'

const store = useT2IStore()
const library = useLibraryStore()
const ui = useUiStore()

const {
  catalog,
  loading,
  loadError,
  actionError,
  jobsError,
  jobSyncError,
  catalogWarnings,
  warnings,
  submitting,
  jobs,
  jobsLoading,
} = storeToRefs(store)

const scroller = ref<HTMLElement | null>(null)
const promptInput = ref<HTMLTextAreaElement | null>(null)
const nearBottom = ref(true)
const settingsOpen = ref(
  typeof window !== 'undefined' && window.matchMedia('(min-width: 1024px)').matches,
)

const setupOpen = ref(false)
const setupPayload = ref<ModuleSetupPayload | null>(null)
const setupLoading = ref(false)
const setupError = ref('')

const viewerOpen = ref(false)
const viewerIndex = ref(0)
const viewerItems = ref<MediaViewerItem[]>([])
const viewerTitle = ref('Media viewer')
const viewerJobId = ref('')
const clearMenuOpen = ref(false)
const clearing = ref(false)

const promptLimit = computed(() => catalog.value?.limits.promptMaxChars ?? 2000)
const visibleWarnings = computed(() => {
  const seen = new Set<string>()
  const modelId = store.selectedModel?.id
  return [
    ...catalogWarnings.value.filter((warning) => !warning.modelId || warning.modelId === modelId),
    ...warnings.value,
  ]
    .filter((warning) => {
      const key = `${warning.code}:${warning.message}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .slice(0, 5)
})
const savedLabel = computed(() => (store.lastSavedAt ? 'Autosaved' : 'Not saved yet'))
const setupNeedsFiles = computed(() => setupPayload.value?.ready === false)
const isEmpty = computed(() => !jobs.value.length && !jobsLoading.value)
const promptSuggestions = [
  'A cozy reading nook by a rainy window, soft afternoon light',
  'A cinematic portrait of an astronaut in a greenhouse',
  'A tiny robot tending a rooftop garden at sunset',
]

function scrollToLatest(): void {
  const element = scroller.value
  if (!element) return
  element.scrollTo({ top: element.scrollHeight, behavior: 'smooth' })
  nearBottom.value = true
}

function onScroll(): void {
  const element = scroller.value
  if (!element) return
  nearBottom.value = element.scrollHeight - element.scrollTop - element.clientHeight < 140
}

async function runGenerate(): Promise<void> {
  const before = store.jobs.length
  await store.generate()
  if (store.jobs.length > before) {
    nearBottom.value = true
    await nextTick()
    scrollToLatest()
  }
}

async function openSettings(section?: string): Promise<void> {
  settingsOpen.value = true
  await nextTick()
  if (!section) return
  document
    .getElementById(`t2i-panel-${section}`)
    ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function loadSetup(openWhenMissing = false): Promise<void> {
  setupLoading.value = true
  setupError.value = ''
  try {
    setupPayload.value = await t2iApi.getSetup()
    if (openWhenMissing && setupPayload.value.ready === false) setupOpen.value = true
  } catch (err) {
    setupError.value = store.errorText(err)
  } finally {
    setupLoading.value = false
  }
}

function openSetup(): void {
  setupOpen.value = true
  void loadSetup(false)
}

function handleUpscaleToggle(): void {
  store.setUpscalerEnabled(!store.upscalerOn)
}

function handleEnhanceToggle(): void {
  store.setEnhanceEnabled(!store.form.enhanceEnabled)
}

function useSuggestion(text: string): void {
  store.form.prompt = text
  void nextTick(() => promptInput.value?.focus())
}

function clearPrompt(): void {
  store.form.prompt = ''
  store.form.approvedPrompt = ''
  store.flushPersist()
  void nextTick(() => promptInput.value?.focus())
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
  viewerJobId.value = ''
}

function cancelJob(job: T2IJobRecord): void {
  void store.cancelJob(job.id)
}

function reuseJob(job: T2IJobRecord): void {
  store.applyJobSettings(job)
  void nextTick(() => promptInput.value?.focus())
}

function useJobSeed(job: T2IJobRecord): void {
  store.useJobSeed(job)
}

async function deleteJob(job: T2IJobRecord, deleteAssets: boolean): Promise<void> {
  const count = job.resultIds?.length ?? 0
  const message = deleteAssets
    ? `Delete ${job.id} and move ${count} image${count === 1 ? '' : 's'} to the library trash?`
    : `Remove ${job.id} from history? Its ${count} image${count === 1 ? '' : 's'} will stay in the Library.`
  if (!window.confirm(message)) return
  try {
    if (viewerJobId.value === job.id) viewerOpen.value = false
    await store.deleteJob(job.id, deleteAssets)
  } catch (err) {
    ui.toast(store.errorText(err), 'error')
  }
}

async function clearHistory(deleteAssets: boolean): Promise<void> {
  clearMenuOpen.value = false
  if (!jobs.value.length) return
  const message = deleteAssets
    ? 'Clear all T2I_main chat messages and move all of their result images to the library trash? This only affects T2I_main.'
    : 'Clear all T2I_main chat messages? Their result images stay in the Library.'
  if (!window.confirm(message)) return
  clearing.value = true
  try {
    viewerOpen.value = false
    viewerJobId.value = ''
    await store.clearHistory(deleteAssets)
  } catch (err) {
    ui.toast(store.errorText(err), 'error')
  } finally {
    clearing.value = false
  }
}

function isViewerFavorite(item: MediaViewerItem): boolean {
  return library.byId(item.id)?.favorite ?? false
}

async function toggleViewerFavorite(item: MediaViewerItem): Promise<void> {
  if (!library.byId(item.id)) await library.syncFromBackend()
  if (!library.byId(item.id)) {
    ui.toast('This image is not in the Library cache yet.', 'warn')
    return
  }
  await library.toggleFavorite(item.id)
}

watch(
  () => jobs.value.length,
  async () => {
    if (!nearBottom.value) return
    await nextTick()
    scrollToLatest()
  },
)

watch(settingsOpen, async () => {
  if (!nearBottom.value) return
  await nextTick()
  scrollToLatest()
})

onMounted(async () => {
  await Promise.allSettled([store.loadCatalog(), store.loadJobs(), library.syncFromBackend()])
  void loadSetup(true)
  await nextTick()
  scrollToLatest()
})

onBeforeUnmount(() => {
  store.flushPersist()
})
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-bg text-text">
    <header class="flex shrink-0 flex-wrap items-center gap-3 border-b border-border px-4 py-3">
      <div class="min-w-0">
        <p class="text-[10px] font-semibold uppercase tracking-[0.2em] text-accent">T2I_main</p>
        <h1 class="text-lg font-semibold leading-tight">Text → Image</h1>
      </div>

      <div class="ml-auto flex flex-wrap items-center justify-end gap-1.5 text-[11px]">
        <span class="inline-flex h-7 items-center gap-1.5 rounded-full border border-border bg-surface px-2.5">
          <span
            class="h-1.5 w-1.5 rounded-full"
            :class="!catalog ? 'bg-muted' : store.comfyReady ? 'bg-success' : 'bg-danger'"
          />
          {{ !catalog ? 'Checking ComfyUI' : store.comfyReady ? 'ComfyUI ready' : 'ComfyUI offline' }}
        </span>
        <span
          v-if="store.selectedModel"
          class="hidden h-7 items-center gap-1 rounded-full border border-border bg-surface px-2.5 text-muted sm:inline-flex"
        >
          {{ store.selectedModel.shortLabel }}
          <span v-if="store.selectedModel.nsfw" class="font-medium text-warn">(NSFW)</span>
        </span>
        <RouterLink
          to="/gallery"
          class="inline-flex h-7 items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 text-muted transition-colors hover:border-accent/40 hover:text-text"
        >
          <Images class="h-3.5 w-3.5" />
          Gallery
        </RouterLink>

        <AppPopover v-model="clearMenuOpen" align="right" width="18rem">
          <template #trigger>
            <button
              type="button"
              class="inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 text-muted transition-colors hover:border-danger/40 hover:text-danger disabled:cursor-not-allowed disabled:opacity-45"
              :disabled="!jobs.length || clearing"
              :title="jobs.length ? 'Clear this module chat' : 'No chat history to clear'"
              @click="clearMenuOpen = !clearMenuOpen"
            >
              <Trash2 class="h-3.5 w-3.5" />
              {{ clearing ? 'Clearing…' : 'Clear' }}
            </button>
          </template>

          <div class="space-y-1">
            <p class="px-2 text-[11px] font-semibold">Clear T2I_main chat</p>
            <p class="px-2 pb-1 text-[10px] leading-snug text-muted">
              Only this module. Other GenModules and Library favorites are untouched.
            </p>
            <p
              v-if="store.busy"
              class="mx-2 mb-1 rounded-lg border border-warn/30 bg-warn/10 px-2 py-1.5 text-[10px] leading-snug text-warn"
            >
              Cancel the active generation first.
            </p>
            <button
              type="button"
              class="flex w-full cursor-pointer items-start gap-2 rounded-lg px-2 py-2 text-left transition-colors hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-45"
              :disabled="store.busy"
              @click="clearHistory(false)"
            >
              <Trash2 class="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted" />
              <span class="min-w-0">
                <span class="block text-xs font-medium text-text">Clear chat</span>
                <span class="block text-[10px] leading-snug text-muted">
                  Remove all chat messages. Keep every image in the Library.
                </span>
              </span>
            </button>
            <button
              type="button"
              class="flex w-full cursor-pointer items-start gap-2 rounded-lg px-2 py-2 text-left transition-colors hover:bg-danger/10 disabled:cursor-not-allowed disabled:opacity-45"
              :disabled="store.busy"
              @click="clearHistory(true)"
            >
              <Trash2 class="mt-0.5 h-3.5 w-3.5 shrink-0 text-danger" />
              <span class="min-w-0">
                <span class="block text-xs font-medium text-danger">Clear chat + media</span>
                <span class="block text-[10px] leading-snug text-muted">
                  Move all of this module's result images to the library trash (recoverable).
                </span>
              </span>
            </button>
          </div>
        </AppPopover>

        <button
          type="button"
          class="inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-full border bg-surface px-2.5 transition-colors hover:border-accent/40 hover:text-text"
          :class="
            setupNeedsFiles
              ? 'border-warn/45 text-warn'
              : 'border-border text-muted'
          "
          :title="setupNeedsFiles ? 'Missing required model files' : 'Required files and download links'"
          @click="openSetup"
        >
          <Download class="h-3.5 w-3.5" />
          Setup
          <span v-if="setupNeedsFiles" class="h-1.5 w-1.5 rounded-full bg-warn" />
        </button>

        <button
          type="button"
          class="inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 text-muted transition-colors hover:border-accent/40 hover:text-text"
          :class="settingsOpen ? 'border-accent/40 text-accent' : ''"
          @click="settingsOpen = !settingsOpen"
        >
          <Settings2 class="h-3.5 w-3.5" />
          Settings
        </button>
      </div>
    </header>

    <div class="flex min-h-0 flex-1">
      <section class="relative flex min-w-0 flex-1 flex-col">
        <div v-if="loading" class="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-4 p-5">
          <div class="h-24 animate-pulse rounded-2xl bg-surface" />
          <div class="h-56 animate-pulse rounded-2xl bg-surface" />
        </div>

        <div v-else-if="loadError && !catalog" class="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
          <TriangleAlert class="h-6 w-6 text-danger" />
          <p class="text-sm font-medium">Could not load the T2I catalog</p>
          <p class="max-w-md text-xs leading-relaxed text-muted">{{ loadError }}</p>
          <AppButton size="sm" @click="store.loadCatalog">
            <RotateCcw class="h-3.5 w-3.5" />
            Retry
          </AppButton>
        </div>

        <template v-else-if="catalog">
          <div ref="scroller" class="min-h-0 flex-1 overflow-y-auto" @scroll="onScroll">
            <div class="mx-auto w-full max-w-4xl px-3 py-5 sm:px-5">
              <div v-if="jobsLoading && !jobs.length" class="space-y-4">
                <div class="h-20 animate-pulse rounded-2xl bg-surface" />
                <div class="h-44 animate-pulse rounded-2xl bg-surface" />
              </div>

              <div v-else-if="isEmpty" class="flex min-h-[52vh] flex-col items-center justify-center px-4 text-center">
                <span class="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">
                  <Sparkles class="h-6 w-6" />
                </span>
                <h2 class="text-base font-semibold">Start with a prompt</h2>
                <p class="mt-1 max-w-md text-xs leading-relaxed text-muted">
                  Strict Text → Image. Generated images land in the Library, and this
                  conversation keeps every prompt, image and setting.
                </p>
                <div class="mt-4 flex max-w-lg flex-wrap justify-center gap-1.5">
                  <button
                    v-for="suggestion in promptSuggestions"
                    :key="suggestion"
                    type="button"
                    class="cursor-pointer rounded-full border border-border bg-surface px-3 py-1.5 text-[11px] text-muted transition-colors hover:border-accent/40 hover:text-text"
                    @click="useSuggestion(suggestion)"
                  >
                    {{ suggestion }}
                  </button>
                </div>
              </div>

              <div v-else class="space-y-8">
                <T2IGenerationCard
                  v-for="job in jobs"
                  :key="job.id"
                  :job="job"
                  @open-viewer="openViewer"
                  @delete="deleteJob"
                  @reuse="reuseJob"
                  @use-seed="useJobSeed"
                  @cancel="cancelJob"
                />
              </div>
            </div>
          </div>

          <button
            v-if="!nearBottom && jobs.length"
            type="button"
            class="absolute bottom-4 right-4 z-10 flex h-9 w-9 cursor-pointer items-center justify-center rounded-full border border-border bg-surface text-muted shadow-lg transition-colors hover:border-accent/40 hover:text-text"
            title="Jump to latest"
            aria-label="Jump to latest"
            @click="scrollToLatest"
          >
            <ArrowDown class="h-4 w-4" />
          </button>

          <footer class="shrink-0 border-t border-border bg-bg/90 px-3 py-3 backdrop-blur sm:px-5">
            <div class="mx-auto w-full max-w-4xl">
              <div
                v-if="actionError"
                class="mb-2 flex items-start gap-1.5 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-[11px] leading-snug text-danger"
              >
                <TriangleAlert class="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{{ actionError }}</span>
              </div>
              <div
                v-if="jobsError"
                class="mb-2 flex items-start gap-1.5 rounded-xl border border-warn/30 bg-warn/10 px-3 py-2 text-[11px] leading-snug text-warn"
              >
                <TriangleAlert class="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>History could not be refreshed: {{ jobsError }}</span>
              </div>
              <div
                v-if="jobSyncError"
                class="mb-2 flex items-start gap-1.5 rounded-xl border border-warn/30 bg-warn/10 px-3 py-2 text-[11px] leading-snug text-warn"
              >
                <TriangleAlert class="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{{ jobSyncError }}</span>
              </div>
              <div
                v-if="visibleWarnings.length"
                class="mb-2 rounded-xl border border-warn/30 bg-warn/10 px-3 py-2 text-[11px] leading-snug text-warn"
              >
                <ul class="list-disc space-y-0.5 pl-4">
                  <li v-for="warning in visibleWarnings" :key="`${warning.code}-${warning.message}`">
                    {{ warning.message }}
                  </li>
                </ul>
              </div>

              <div class="rounded-3xl border border-border bg-surface p-2.5 shadow-lg transition-colors focus-within:border-accent/50">
                <div class="relative">
                  <textarea
                    ref="promptInput"
                    v-model="store.form.prompt"
                    rows="2"
                    :maxlength="promptLimit"
                    placeholder="Describe the image you want..."
                    class="w-full resize-none rounded-2xl border-0 bg-transparent px-2 py-1.5 pr-8 text-sm leading-relaxed text-text outline-none placeholder:text-muted/60"
                    @keydown.ctrl.enter.prevent="runGenerate"
                    @keydown.meta.enter.prevent="runGenerate"
                  />
                  <button
                    v-if="store.form.prompt"
                    type="button"
                    class="absolute right-1 top-1 flex h-6 w-6 cursor-pointer items-center justify-center rounded-md text-muted transition-colors hover:bg-surface-2 hover:text-text"
                    title="Clear prompt"
                    aria-label="Clear prompt"
                    @click="clearPrompt"
                  >
                    <X class="h-3.5 w-3.5" />
                  </button>
                </div>

                <div class="mt-1 flex flex-wrap items-center gap-1.5">
                  <button
                    type="button"
                    class="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-full border border-border bg-surface-2/70 px-2.5 text-[11px] font-medium text-muted transition-colors hover:border-accent/30 hover:text-text"
                    @click="openSettings('output')"
                  >
                    <Sparkles class="h-3.5 w-3.5 text-accent" />
                    {{ store.selectedModel?.shortLabel ?? 'Model' }}
                    <ChevronDown class="h-3 w-3" />
                  </button>
                  <button
                    type="button"
                    class="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-full border border-border bg-surface-2/70 px-2.5 text-[11px] font-medium text-muted transition-colors hover:border-accent/30 hover:text-text"
                    @click="openSettings('output')"
                  >
                    {{ store.form.ratio }} · {{ store.form.size }}px
                  </button>
                  <button
                    type="button"
                    class="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-full border border-border bg-surface-2/70 px-2.5 text-[11px] font-medium text-muted transition-colors hover:border-accent/30 hover:text-text"
                    @click="openSettings('loras')"
                  >
                    LoRA {{ store.activeLoraCount }}
                  </button>
                  <button
                    type="button"
                    class="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-full border px-2.5 text-[11px] font-medium transition-colors"
                    :class="
                      store.upscalerOn
                        ? 'border-accent/45 bg-accent-soft text-accent'
                        : 'border-border bg-surface-2/70 text-muted hover:text-text'
                    "
                    :title="store.upscalerOn ? 'Turn upscale off' : 'Turn upscale on'"
                    @click="handleUpscaleToggle"
                  >
                    <span class="h-1.5 w-1.5 rounded-full" :class="store.upscalerOn ? 'bg-accent' : 'bg-border'" />
                    Upscale {{ store.upscalerOn ? 'on' : 'off' }}
                  </button>
                  <button
                    type="button"
                    class="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-full border px-2.5 text-[11px] font-medium transition-colors"
                    :class="
                      store.form.enhanceEnabled
                        ? 'border-accent/45 bg-accent-soft text-accent'
                        : 'border-border bg-surface-2/70 text-muted hover:text-text'
                    "
                    :title="store.form.enhanceEnabled ? 'Turn prompt enhancement off' : 'Turn prompt enhancement on'"
                    @click="handleEnhanceToggle"
                  >
                    <span
                      class="h-1.5 w-1.5 rounded-full"
                      :class="store.form.enhanceEnabled ? 'bg-accent' : 'bg-border'"
                    />
                    Enhance {{ store.form.enhanceEnabled ? 'on' : 'off' }}
                  </button>

                  <div class="ml-auto flex items-center gap-1">
                    <button
                      type="button"
                      class="flex h-8 w-8 cursor-pointer items-center justify-center rounded-full text-muted transition-colors hover:bg-surface-2 hover:text-text"
                      title="All settings"
                      aria-label="All settings"
                      @click="openSettings()"
                    >
                      <Settings2 class="h-4 w-4" />
                    </button>
                    <AppButton
                      variant="primary"
                      size="sm"
                      class="rounded-full! px-4!"
                      :disabled="!store.canGenerate"
                      @click="runGenerate"
                    >
                      <span v-if="submitting">Starting…</span>
                      <span v-else-if="store.busy">Generating…</span>
                      <span v-else>Generate</span>
                      <span class="text-[13px]">↵</span>
                    </AppButton>
                  </div>
                </div>
              </div>

              <div class="mt-1.5 flex flex-wrap items-center justify-between gap-1 px-1 text-[10px] text-muted">
                <span>Ctrl+Enter to generate · {{ savedLabel }} in this browser</span>
                <span class="tabular-nums">
                  {{ store.form.prompt.length }} / {{ promptLimit }}
                </span>
              </div>
            </div>
          </footer>
        </template>
      </section>

      <div
        v-if="settingsOpen"
        class="fixed inset-0 z-30 bg-black/40 lg:hidden"
        @click="settingsOpen = false"
      />
      <aside
        v-if="settingsOpen"
        class="fixed inset-y-0 right-0 z-40 flex w-[min(92vw,390px)] flex-col border-l border-border bg-surface shadow-2xl lg:static lg:z-auto lg:w-[390px] lg:shadow-none"
      >
        <T2ISettingsPanel @close="settingsOpen = false" />
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
        <template v-if="item">
          <button
            type="button"
            class="flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl text-white/70 transition-colors hover:bg-white/10 hover:text-white"
            :title="isViewerFavorite(item) ? 'Remove from favorites' : 'Add to favorites'"
            aria-label="Toggle favorite"
            @click="toggleViewerFavorite(item)"
          >
            <Star class="h-4 w-4" :class="isViewerFavorite(item) ? 'fill-current text-warn' : ''" />
          </button>
        </template>
      </template>
    </MediaViewer>

    <ModuleSetupModal
      v-model="setupOpen"
      :payload="setupPayload"
      :loading="setupLoading"
      :error="setupError"
      @refresh="loadSetup(false)"
    />
  </div>
</template>
