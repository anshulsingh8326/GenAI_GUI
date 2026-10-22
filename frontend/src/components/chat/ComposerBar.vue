<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowUp, ChevronDown, Images, Plus, SlidersHorizontal, Sparkles, Upload, X } from '@lucide/vue'
import { imageModels } from '@/lib/fixtures'
import { useCatalogStore } from '@/stores/catalog'
import { useChatStore } from '@/stores/chat'
import { useLibraryStore } from '@/stores/library'
import { useSettingsStore } from '@/stores/settings'
import AppPopover from '@/components/ui/AppPopover.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppSwitch from '@/components/ui/AppSwitch.vue'
import Badge from '@/components/ui/Badge.vue'
import AttachmentCard from './AttachmentCard.vue'
import AttachPickerModal from './AttachPickerModal.vue'
import AdvancedModal from './AdvancedModal.vue'

const props = defineProps<{
  tabId: string
}>()

const chat = useChatStore()
const library = useLibraryStore()
const catalog = useCatalogStore()
const settings = useSettingsStore()

const thread = computed(() => chat.thread(props.tabId))
const composer = computed(() => thread.value.composer)
const currentModel = computed(() => imageModels.find((m) => m.id === composer.value.modelId))
const currentBase = computed(() => currentModel.value?.base ?? null)

watch(
  () => settings.backendState,
  (state) => {
    if (state === 'live') void catalog.ensureLoaded()
  },
  { immediate: true },
)

const ratios = ['1:1', '3:2', '4:3', '16:9', '9:16', '21:9']
const resolutions = [512, 768, 1024, 1280, 1536, 2048]

const showAttach = ref(false)
const showModel = ref(false)
const showSize = ref(false)
const showBatch = ref(false)
const showLoras = ref(false)
const showAdvanced = ref(false)
const showPicker = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

function setModel(id: string) {
  composer.value.modelId = id
  const defaults = imageModels.find((m) => m.id === id)?.defaults
  if (defaults) {
    composer.value.advanced.steps = defaults.steps
    composer.value.advanced.cfg = defaults.cfg
    composer.value.advanced.sampler = defaults.sampler
    composer.value.advanced.scheduler = defaults.scheduler
    composer.value.advanced.denoise = defaults.denoise
  }
  showModel.value = false
}

function applySize(ratio: string, res: number) {
  const [a, b] = ratio.split(':').map(Number)
  const w = a >= b ? res : Math.round((res * a) / b)
  const h = a >= b ? Math.round((res * b) / a) : res
  composer.value.ratio = ratio
  composer.value.width = w
  composer.value.height = h
}

function onFiles(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files) return
  Array.from(files).forEach((f) => {
    const reader = new FileReader()
    reader.onload = () => {
      composer.value.attachments.push({
        id: 'att-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6),
        url: String(reader.result),
        name: f.name,
        source: 'upload',
        identity: true,
        describe: false,
        describeMode: 'character',
      })
    }
    reader.readAsDataURL(f)
  })
  input.value = ''
}

function addFromLibrary(assetId: string) {
  const asset = library.byId(assetId)
  if (!asset) return
  composer.value.attachments.push({
    id: 'att-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6),
    url: asset.url,
    name: asset.label,
    source: 'library',
    identity: true,
    describe: false,
    describeMode: 'character',
  })
  showPicker.value = false
}

function removeAttachment(id: string) {
  composer.value.attachments = composer.value.attachments.filter((a) => a.id !== id)
}

const loraName = (id: string) => catalog.byLora(id)?.label ?? id
const availableLoras = computed(() => catalog.loras.filter((l) => !composer.value.loras.some((x) => x.id === l.id)))
const activeTriggers = computed(() => catalog.triggersFor(composer.value.loras.filter((l) => l.on).map((l) => l.id)))

function baseMismatch(id: string): boolean {
  const base = catalog.byLora(id)?.base
  return Boolean(base && currentBase.value && base !== currentBase.value)
}

function addLora(id: string) {
  composer.value.loras.push({ id, strength: catalog.defaultStrength(id), on: true })
}

function removeLora(id: string) {
  composer.value.loras = composer.value.loras.filter((l) => l.id !== id)
}

function send() {
  chat.send(props.tabId)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}
</script>

<template>
  <div class="shrink-0 border-t border-border bg-bg/85 px-6 py-4 backdrop-blur">
    <div class="mx-auto w-full max-w-3xl">
      <div class="rounded-3xl border border-border bg-surface p-3 shadow-lg">
        <!-- attachments -->
        <div v-if="composer.attachments.length" class="mb-2.5 flex flex-wrap gap-2 px-1">
          <AttachmentCard
            v-for="a in composer.attachments"
            :key="a.id"
            :attachment="a"
            @remove="removeAttachment(a.id)"
          />
        </div>

        <!-- prompt -->
        <textarea
          v-model="composer.text"
          rows="2"
          placeholder="Describe your image... (Enter to generate, Shift+Enter for a new line)"
          class="w-full resize-none bg-transparent px-2 py-1.5 text-sm leading-relaxed text-text outline-none placeholder:text-muted/60"
          @keydown="onKeydown"
        />

        <!-- controls -->
        <div class="mt-1.5 flex flex-wrap items-center gap-1.5 px-1">
          <!-- add image -->
          <AppPopover v-model="showAttach" up width="12rem">
            <template #trigger>
              <button
                class="flex h-8 w-8 cursor-pointer items-center justify-center rounded-full border border-border bg-surface-2/70 text-muted transition-colors hover:text-text"
                title="Add reference image"
                @click="showAttach = !showAttach"
              >
                <Plus class="h-4 w-4" />
              </button>
            </template>
            <div class="space-y-0.5">
              <button
                class="flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-muted transition-colors hover:bg-surface-2 hover:text-text"
                @click="showAttach = false; fileInput?.click()"
              >
                <Upload class="h-3.5 w-3.5" /> From computer
              </button>
              <button
                class="flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-muted transition-colors hover:bg-surface-2 hover:text-text"
                @click="showAttach = false; showPicker = true"
              >
                <Images class="h-3.5 w-3.5" /> From gallery
              </button>
            </div>
          </AppPopover>
          <input ref="fileInput" type="file" accept="image/*" multiple class="hidden" @change="onFiles" />

          <!-- model (per tab) -->
          <AppPopover v-model="showModel" up width="21rem">
            <template #trigger>
              <button
                class="flex h-8 cursor-pointer items-center gap-1.5 rounded-full border border-border bg-surface-2/70 px-3 text-xs text-text transition-colors hover:border-accent/40"
                title="Image model for this tab"
                @click="showModel = !showModel"
              >
                <Sparkles class="h-3.5 w-3.5 text-accent" />
                <span class="max-w-44 truncate">{{ currentModel?.name ?? 'Select model' }}</span>
                <ChevronDown class="h-3 w-3 text-muted" />
              </button>
            </template>
            <p class="mb-2 px-1 text-[10px] uppercase tracking-wider text-muted">Image model - this tab</p>
            <div class="max-h-72 space-y-1 overflow-y-auto">
              <button
                v-for="m in imageModels"
                :key="m.id"
                class="w-full rounded-xl border p-2.5 text-left transition-colors"
                :class="[
                  m.id === composer.modelId ? 'border-accent/50 bg-accent-soft' : 'border-transparent',
                  m.installed ? 'cursor-pointer hover:bg-surface-2' : 'cursor-not-allowed opacity-50',
                ]"
                :disabled="!m.installed"
                @click="setModel(m.id)"
              >
                <p class="text-xs font-medium">{{ m.name }}</p>
                <p class="mt-0.5 text-[10px] text-muted">{{ m.family }} - {{ m.vram }}<span v-if="m.note"> - {{ m.note }}</span></p>
                <div class="mt-1.5 flex flex-wrap gap-1">
                  <span v-for="b in m.badges" :key="b" class="rounded bg-surface px-1 py-0.5 text-[9px] uppercase tracking-wide text-muted">{{ b }}</span>
                </div>
              </button>
            </div>
          </AppPopover>

          <!-- size -->
          <AppPopover v-model="showSize" up width="15rem">
            <template #trigger>
              <button
                class="flex h-8 cursor-pointer items-center gap-1.5 rounded-full border border-border bg-surface-2/70 px-3 text-xs text-text transition-colors hover:border-accent/40"
                @click="showSize = !showSize"
              >
                {{ composer.ratio }} - {{ composer.width }}x{{ composer.height }}
                <ChevronDown class="h-3 w-3 text-muted" />
              </button>
            </template>
            <p class="mb-2 px-1 text-[10px] uppercase tracking-wider text-muted">Aspect ratio</p>
            <div class="mb-3 grid grid-cols-3 gap-1.5">
              <button
                v-for="r in ratios"
                :key="r"
                class="h-8 cursor-pointer rounded-lg border text-xs transition-colors"
                :class="composer.ratio === r ? 'border-accent/50 bg-accent-soft text-accent' : 'border-border text-muted hover:text-text'"
                @click="applySize(r, Math.max(composer.width, composer.height))"
              >
                {{ r }}
              </button>
            </div>
            <p class="mb-2 px-1 text-[10px] uppercase tracking-wider text-muted">Resolution (long side)</p>
            <div class="grid grid-cols-3 gap-1.5">
              <button
                v-for="res in resolutions"
                :key="res"
                class="h-8 cursor-pointer rounded-lg border text-xs transition-colors"
                :class="Math.max(composer.width, composer.height) === res ? 'border-accent/50 bg-accent-soft text-accent' : 'border-border text-muted hover:text-text'"
                @click="applySize(composer.ratio, res)"
              >
                {{ res }}
              </button>
            </div>
          </AppPopover>

          <!-- batch -->
          <AppPopover v-model="showBatch" up width="11rem">
            <template #trigger>
              <button
                class="flex h-8 cursor-pointer items-center gap-1.5 rounded-full border border-border bg-surface-2/70 px-3 text-xs text-text transition-colors hover:border-accent/40"
                title="Batch size"
                @click="showBatch = !showBatch"
              >
                x{{ composer.batch }}
                <ChevronDown class="h-3 w-3 text-muted" />
              </button>
            </template>
            <p class="mb-2 px-1 text-[10px] uppercase tracking-wider text-muted">Images per run</p>
            <div class="grid grid-cols-4 gap-1.5">
              <button
                v-for="n in 8"
                :key="n"
                class="h-8 cursor-pointer rounded-lg border text-xs transition-colors"
                :class="composer.batch === n ? 'border-accent/50 bg-accent-soft text-accent' : 'border-border text-muted hover:text-text'"
                @click="composer.batch = n; showBatch = false"
              >
                {{ n }}
              </button>
            </div>
          </AppPopover>

          <!-- lora chain -->
          <AppPopover v-model="showLoras" up align="right" width="22rem">
            <template #trigger>
              <button
                class="flex h-8 cursor-pointer items-center gap-1.5 rounded-full border border-border bg-surface-2/70 px-3 text-xs text-text transition-colors hover:border-accent/40"
                title="LoRA chain"
                @click="showLoras = !showLoras"
              >
                LoRA - {{ composer.loras.filter((l) => l.on).length }}
                <ChevronDown class="h-3 w-3 text-muted" />
              </button>
            </template>
            <p class="mb-2 px-1 text-[10px] uppercase tracking-wider text-muted">Chain (order matters - top runs first)</p>
            <div class="space-y-2">
              <div
                v-for="l in composer.loras"
                :key="l.id"
                class="rounded-xl border border-border bg-surface-2/40 p-2"
              >
                <div class="flex items-center gap-2">
                  <AppSwitch v-model="l.on" />
                  <div class="min-w-0 flex-1">
                    <div class="flex flex-wrap items-center gap-1">
                      <p class="truncate text-[11px]">{{ loraName(l.id) }}</p>
                      <Badge v-if="catalog.byLora(l.id)?.base" tone="neutral">{{ catalog.byLora(l.id)?.base }}</Badge>
                      <Badge v-if="baseMismatch(l.id)" tone="warn">other base</Badge>
                      <Badge v-if="catalog.byLora(l.id) && !catalog.byLora(l.id)?.present" tone="warn">missing</Badge>
                    </div>
                    <p
                      v-if="catalog.byLora(l.id)?.triggers.length"
                      class="mt-0.5 truncate text-[9px] text-muted"
                      :title="catalog.byLora(l.id)?.triggers.join(', ')"
                    >
                      trigger: {{ catalog.byLora(l.id)?.triggers.join(', ') }}
                    </p>
                    <input
                      v-model.number="l.strength"
                      type="range"
                      :min="catalog.strengthRange(l.id).min"
                      :max="catalog.strengthRange(l.id).max"
                      :step="catalog.strengthRange(l.id).step"
                      class="mt-1 h-1 w-full cursor-pointer appearance-none rounded-full bg-border"
                      :style="{ accentColor: 'var(--c-accent)' }"
                    />
                  </div>
                  <span class="w-8 shrink-0 text-right text-[10px] tabular-nums text-muted">{{ l.strength.toFixed(2) }}</span>
                  <button class="shrink-0 cursor-pointer text-muted transition-colors hover:text-danger" @click="removeLora(l.id)">
                    <X class="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
              <p v-if="!composer.loras.length" class="px-1 text-[11px] text-muted">No LoRAs in the chain.</p>
            </div>
            <div v-if="availableLoras.length" class="mt-3 border-t border-border pt-2">
              <p class="mb-1 px-1 text-[10px] uppercase tracking-wider text-muted">Add LoRA</p>
              <div class="max-h-56 overflow-y-auto pr-1">
                <button
                  v-for="l in availableLoras"
                  :key="l.id"
                  class="flex w-full cursor-pointer items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-muted transition-colors hover:bg-surface-2 hover:text-text disabled:cursor-not-allowed disabled:opacity-40"
                  :disabled="!l.present"
                  @click="addLora(l.id)"
                >
                  <span class="min-w-0">
                    <span class="block truncate">{{ l.label }}</span>
                    <span class="block truncate text-[9px] text-muted">
                      {{ l.base ? catalog.baseLabel(l.base) : 'unassigned' }}
                      <template v-if="l.triggers.length"> - {{ l.triggers.join(', ') }}</template>
                    </span>
                  </span>
                  <span class="flex shrink-0 items-center gap-1">
                    <Badge v-if="!l.present" tone="warn">missing</Badge>
                    <Badge v-else-if="baseMismatch(l.id)" tone="warn">other base</Badge>
                    <Plus class="h-3 w-3" />
                  </span>
                </button>
              </div>
            </div>
            <div v-else-if="catalog.loras.length" class="mt-3 border-t border-border pt-2">
              <p class="px-1 text-[10px] text-muted">All catalog LoRAs are in the chain.</p>
            </div>
            <div v-else class="mt-3 border-t border-border pt-2">
              <p class="px-1 text-[10px] text-muted">
                <template v-if="catalog.loading">Loading the LoRA catalog...</template>
                <template v-else-if="catalog.error">LoRA catalog unavailable (backend offline?).</template>
                <template v-else>No LoRAs in the catalog yet.</template>
              </p>
              <RouterLink
                to="/settings?tab=catalog"
                class="mt-1 inline-block px-1 text-[10px] text-accent hover:underline"
                @click="showLoras = false"
              >
                Build it in Settings - Model catalog
              </RouterLink>
            </div>
            <p
              v-if="activeTriggers.length"
              class="mt-3 rounded-lg bg-surface-2/60 px-2 py-1.5 text-[10px] leading-relaxed text-muted"
            >
              Trigger words added automatically: <span class="text-text">{{ activeTriggers.join(', ') }}</span>
            </p>
          </AppPopover>

          <!-- right group: actions - ml-auto keeps Generate pinned right even when the row wraps -->
          <button
            class="ml-auto flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-full border border-border bg-surface-2/70 text-muted transition-colors hover:text-text"
            title="Advanced parameters - stages, seed, steps, CFG, sampler..."
            @click="showAdvanced = true"
          >
            <SlidersHorizontal class="h-3.5 w-3.5" />
          </button>

          <AppButton variant="primary" size="sm" class="shrink-0 rounded-full! px-4!" :disabled="!composer.text.trim()" @click="send">
            Generate
            <ArrowUp class="h-3.5 w-3.5" />
          </AppButton>
        </div>
      </div>

      <p class="mt-2 text-center text-[10px] text-muted">
        Freeze v8 pipeline - LoRA chain and identity run as visible stages; enhance, refine and all parameters live behind the sliders button.
      </p>
    </div>

    <AttachPickerModal v-model="showPicker" @pick="addFromLibrary" />
    <AdvancedModal v-model="showAdvanced" :tab-id="tabId" />
  </div>
</template>
