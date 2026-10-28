<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { FolderOpen, LoaderCircle, Play, RefreshCw, ServerCog, MessageSquareText, SlidersHorizontal } from '@lucide/vue'
import { useSettingsStore } from '@/stores/settings'
import { useEngineStore } from '@/stores/engine'
import { useContentStore } from '@/stores/content'
import { api, ApiError } from '@/lib/api'
import { useUiStore } from '@/stores/ui'
import Section from '@/components/ui/Section.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppSwitch from '@/components/ui/AppSwitch.vue'
import StatusDot from '@/components/ui/StatusDot.vue'
import ResetButton from '@/components/ui/ResetButton.vue'
import ProfilesModal from '../components/ProfilesModal.vue'

const settings = useSettingsStore()
const engine = useEngineStore()
const ui = useUiStore()

const managing = ref<'comfyui' | 'ollama' | null>(null)
const browsingLauncher = ref(false)

async function browseLauncher() {
  browsingLauncher.value = true
  try {
    const res = await api.pickPath({
      mode: 'file',
      title: 'Select the ComfyUI launcher (.bat)',
      start: settings.comfyuiLauncher,
      extensions: ['bat', 'cmd', 'exe'],
    })
    if (res.path) settings.comfyuiLauncher = res.path
  } catch (err) {
    ui.toast(
      err instanceof ApiError && err.isOffline
        ? 'Backend offline - the file dialog opens on the machine running the backend.'
        : `Could not open the dialog: ${err instanceof Error ? err.message : 'unknown error'}`,
      'warn',
    )
  } finally {
    browsingLauncher.value = false
  }
}

const content = useContentStore()
const browsingFolder = ref(false)

async function browseFolder() {
  browsingFolder.value = true
  try {
    const res = await api.pickPath({
      mode: 'folder',
      title: 'Select the ComfyUI source folder (the one with main.py)',
      start: settings.comfyuiFolder,
    })
    if (res.path) settings.comfyuiFolder = res.path
  } catch (err) {
    ui.toast(
      err instanceof ApiError && err.isOffline
        ? 'Backend offline - the folder dialog opens on the machine running the backend.'
        : `Could not open the dialog: ${err instanceof Error ? err.message : 'unknown error'}`,
      'warn',
    )
  } finally {
    browsingFolder.value = false
  }
}

const folderSet = computed(() => settings.comfyuiFolder.trim().length > 0)

// Only trust a report that was made for the value currently in the field - a
// stale scan (older folder) shows the "checking" state instead of wrong data.
const folderReport = computed(() => {
  const insp = content.inspect
  if (!insp || !folderSet.value) return null
  return insp.configured === settings.comfyuiFolder.trim() ? insp : null
})

const suggestion = computed(() => (folderSet.value ? '' : (content.inspect?.suggestions[0] ?? '')))
const suggestedCorrection = computed(() => (folderSet.value ? (folderReport.value?.suggestedFolder ?? '') : ''))

async function applyFolder(path: string) {
  if (!path) return
  settings.comfyuiFolder = path
  await settings.flushSettings()
  await content.refresh()
}

const folderSummary = computed(() => {
  const report = folderReport.value
  if (!report?.valid) return ''
  const flavor =
    report.flavor === 'portable'
      ? 'Portable install'
      : report.flavor === 'venv'
        ? 'Venv install'
        : 'ComfyUI install'
  const parts = [flavor]
  if (report.version) parts.push(`v${report.version}`)
  parts.push(`${report.customNodes.length} custom node${report.customNodes.length === 1 ? '' : 's'}`)
  if (report.pythonPath) parts.push('Python found')
  return parts.join(' \u00b7 ')
})

// The field saves ~400ms after the last keystroke - wait for that push, then
// re-scan so the status line reflects the folder that is actually stored.
let folderTimer: ReturnType<typeof setTimeout> | null = null
watch(
  [() => settings.comfyuiFolder, () => settings.comfyuiLauncher],
  () => {
    if (folderTimer) clearTimeout(folderTimer)
    folderTimer = setTimeout(() => void content.refresh(), 700)
  },
)

onMounted(() => void content.refresh())

function onLauncherDrop(e: DragEvent) {
  const file = e.dataTransfer?.files?.[0] as (File & { path?: string }) | undefined
  if (file?.path) {
    settings.comfyuiLauncher = file.path
    return
  }
  ui.toast(
    'Browsers hide file paths on drag & drop - use Browse... to pick the .bat (drag & drop works in the desktop wrapper later).',
    'warn',
  )
}

const managingOpen = computed({
  get: () => managing.value !== null,
  set: (v: boolean) => {
    if (!v) managing.value = null
  },
})

const comfyProfile = computed(() => settings.activeProfile('comfyui'))
const ollamaProfile = computed(() => settings.activeProfile('ollama'))

function profileOptions(kind: 'comfyui' | 'ollama') {
  return settings.profiles
    .filter((p) => p.kind === kind)
    .map((p) => ({ value: p.id, label: p.name || p.id }))
}
</script>

<template>
  <Section
    title="ComfyUI - the engine"
    desc="The app talks to ComfyUI over its HTTP + WebSocket API. The browser never connects directly."
  >
    <div class="flex flex-wrap items-center gap-2">
      <StatusDot :state="engine.comfy.checking ? 'busy' : engine.comfy.connected ? 'ok' : 'off'" />
      <span class="text-sm font-medium" :class="engine.comfy.connected ? 'text-success' : 'text-danger'">
        {{ engine.comfy.connected ? 'Connected' : 'Offline' }}
      </span>
      <span class="text-xs text-muted">- {{ engine.comfy.detail }}</span>
    </div>
    <div class="mt-3 flex flex-wrap items-end gap-2">
      <div class="min-w-64 flex-1">
        <p class="mb-1 text-[11px] uppercase tracking-wider text-muted">URL (active profile)</p>
        <AppInput
          :model-value="comfyProfile?.url ?? ''"
          @update:model-value="(v: string) => comfyProfile && settings.setProfileUrl(comfyProfile.id, v)"
        />
      </div>
      <div class="w-44">
        <p class="mb-1 text-[11px] uppercase tracking-wider text-muted">Profile</p>
        <AppSelect
          :model-value="settings.activeProfiles.comfyui"
          :options="profileOptions('comfyui')"
          @update:model-value="(v: string) => settings.setActiveProfile('comfyui', v)"
        />
      </div>
      <ResetButton
        :disabled="!comfyProfile || settings.isDefault(['profiles', comfyProfile.id, 'url'])"
        @reset="comfyProfile && settings.resetField(['profiles', comfyProfile.id, 'url'])"
      />
      <AppButton @click="engine.test('comfyui')">
        <LoaderCircle v-if="engine.comfy.checking" class="h-3.5 w-3.5 animate-spin" />
        <RefreshCw v-else class="h-3.5 w-3.5" />
        Test connection
      </AppButton>
      <AppButton variant="ghost" @click="managing = 'comfyui'">
        <SlidersHorizontal class="h-3.5 w-3.5" /> Profiles...
      </AppButton>
    </div>
    <p v-if="comfyProfile?.auth" class="mt-2 text-[11px] text-muted">Auth header configured for this profile.</p>
    <div class="mt-3 rounded-xl border border-dashed border-border p-3" @dragover.prevent @drop.prevent="onLauncherDrop">
      <p class="text-xs font-medium">ComfyUI launcher (optional)</p>
      <p class="mb-2 text-[11px] leading-relaxed text-muted">
        Your own .bat that starts ComfyUI (e.g. run_nvidia_gpu.bat). Launch opens it in its own terminal window -
        exactly like double-clicking it. The switch below can start it together with the app.
      </p>
      <div class="flex flex-wrap items-center gap-2">
        <div class="min-w-64 flex-1">
          <AppInput v-model="settings.comfyuiLauncher" placeholder="Drag a .bat here, or Browse / paste a path" />
        </div>
        <AppButton variant="ghost" :disabled="browsingLauncher" @click="browseLauncher">
          <LoaderCircle v-if="browsingLauncher" class="h-3.5 w-3.5 animate-spin" />
          <FolderOpen v-else class="h-3.5 w-3.5" />
          Browse...
        </AppButton>
        <ResetButton
          :disabled="settings.isDefault(['comfyuiLauncher'])"
          @reset="settings.resetField(['comfyuiLauncher'])"
        />
        <AppButton :disabled="!settings.comfyuiLauncher.trim() || engine.launching" @click="engine.launchComfy()">
          <LoaderCircle v-if="engine.launching" class="h-3.5 w-3.5 animate-spin" />
          <Play v-else class="h-3.5 w-3.5" />
          Launch ComfyUI
        </AppButton>
      </div>
      <div class="mt-3 flex flex-wrap items-center gap-2 border-t border-border/60 pt-3">
        <AppSwitch v-model="settings.comfyuiLauncherAutoStart" :disabled="!settings.comfyuiLauncher.trim()" />
        <span class="text-xs" :class="settings.comfyuiLauncher.trim() ? 'text-text' : 'text-muted'">
          Start it automatically when the app launches
        </span>
        <ResetButton
          :disabled="settings.isDefault(['comfyuiLauncherAutoStart'])"
          @reset="settings.resetField(['comfyuiLauncherAutoStart'])"
        />
        <span class="text-[11px] text-muted">skips when ComfyUI is already running</span>
      </div>
    </div>
    <div class="mt-3 rounded-xl border border-dashed border-border p-3">
      <p class="text-xs font-medium">ComfyUI folder (content management)</p>
      <p class="mb-2 text-[11px] leading-relaxed text-muted">
        The ComfyUI source folder - the one with main.py, custom_nodes and models. The app reads it to report which
        module content (custom nodes, model files) is installed; see Settings &gt; Engine content. Read-only.
      </p>
      <div class="flex flex-wrap items-center gap-2">
        <div class="min-w-64 flex-1">
          <AppInput
            v-model="settings.comfyuiFolder"
            placeholder="e.g. D:\ComfyUI_windows_portable\ComfyUI"
          />
        </div>
        <AppButton variant="ghost" :disabled="browsingFolder" @click="browseFolder">
          <LoaderCircle v-if="browsingFolder" class="h-3.5 w-3.5 animate-spin" />
          <FolderOpen v-else class="h-3.5 w-3.5" />
          Browse...
        </AppButton>
        <ResetButton
          :disabled="settings.isDefault(['comfyuiFolder'])"
          @reset="settings.resetField(['comfyuiFolder'])"
        />
      </div>
      <div v-if="folderSet" class="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
        <template v-if="folderReport?.valid">
          <StatusDot state="ok" />
          <span class="text-success">{{ folderSummary }}</span>
        </template>
        <template v-else-if="folderReport?.error">
          <StatusDot state="off" />
          <span class="text-warn">{{ folderReport.error }}</span>
          <template v-if="suggestedCorrection">
            <code class="rounded bg-surface-2 px-1.5 py-0.5 text-[10px]">{{ suggestedCorrection }}</code>
            <AppButton variant="ghost" @click="applyFolder(suggestedCorrection)">Use this folder</AppButton>
          </template>
        </template>
        <template v-else>
          <LoaderCircle class="h-3 w-3 animate-spin text-muted" />
          <span class="text-muted">Checking the folder...</span>
        </template>
      </div>
      <div v-else-if="suggestion" class="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
        <span class="text-muted">Detected from your launcher:</span>
        <code class="rounded bg-surface-2 px-1.5 py-0.5 text-[10px]">{{ suggestion }}</code>
        <AppButton variant="ghost" @click="applyFolder(suggestion)">Use this folder</AppButton>
      </div>
      <p v-if="content.lastError" class="mt-2 text-[11px] text-warn">{{ content.lastError }}</p>
    </div>
    <p class="mt-3 flex items-start gap-2 rounded-xl border border-border bg-surface-2/40 p-3 text-xs leading-relaxed text-muted">
      <ServerCog class="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
      The app probes version, GPU and VRAM on every refresh (top bar pills and the Resources popover are live).
      Custom node and model checks for installed generation modules live in Settings &gt; Engine content (read-only).
    </p>
  </Section>

  <Section
    title="Ollama - text provider"
    desc="Local LLM used for prompt enhance and image describe. Uncensored models are the recommended default."
  >
    <div class="flex flex-wrap items-center gap-2">
      <StatusDot :state="engine.ollama.checking ? 'busy' : engine.ollama.connected ? 'ok' : 'off'" />
      <span class="text-sm font-medium" :class="engine.ollama.connected ? 'text-success' : 'text-danger'">
        {{ engine.ollama.connected ? 'Connected' : 'Offline' }}
      </span>
      <span class="text-xs text-muted">- {{ engine.ollama.detail }}</span>
    </div>
    <div class="mt-3 flex flex-wrap items-end gap-2">
      <div class="min-w-64 flex-1">
        <p class="mb-1 text-[11px] uppercase tracking-wider text-muted">URL (active profile)</p>
        <AppInput
          :model-value="ollamaProfile?.url ?? ''"
          @update:model-value="(v: string) => ollamaProfile && settings.setProfileUrl(ollamaProfile.id, v)"
        />
      </div>
      <div class="w-44">
        <p class="mb-1 text-[11px] uppercase tracking-wider text-muted">Profile</p>
        <AppSelect
          :model-value="settings.activeProfiles.ollama"
          :options="profileOptions('ollama')"
          @update:model-value="(v: string) => settings.setActiveProfile('ollama', v)"
        />
      </div>
      <ResetButton
        :disabled="!ollamaProfile || settings.isDefault(['profiles', ollamaProfile.id, 'url'])"
        @reset="ollamaProfile && settings.resetField(['profiles', ollamaProfile.id, 'url'])"
      />
      <AppButton @click="engine.test('ollama')">
        <LoaderCircle v-if="engine.ollama.checking" class="h-3.5 w-3.5 animate-spin" />
        <RefreshCw v-else class="h-3.5 w-3.5" />
        Test connection
      </AppButton>
      <AppButton variant="ghost" @click="managing = 'ollama'">
        <SlidersHorizontal class="h-3.5 w-3.5" /> Profiles...
      </AppButton>
    </div>
    <p v-if="ollamaProfile?.auth" class="mt-2 text-[11px] text-muted">Auth header configured for this profile.</p>
    <p class="mt-3 flex items-start gap-2 rounded-xl border border-border bg-surface-2/40 p-3 text-xs leading-relaxed text-muted">
      <MessageSquareText class="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
      Fallback: ComfyUI TextGenerate (zero extra install). OpenAI-compatible providers (LM Studio, llama.cpp,
      cloud) come later as opt-ins - cloud calls are off by default and clearly marked.
    </p>
  </Section>

  <ProfilesModal v-if="managing" v-model="managingOpen" :kind="managing" />
</template>
