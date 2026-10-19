<script setup lang="ts">
import { computed, ref } from 'vue'
import { FolderOpen, LoaderCircle, Play, RefreshCw, ServerCog, MessageSquareText, SlidersHorizontal } from '@lucide/vue'
import { useSettingsStore } from '@/stores/settings'
import { useEngineStore } from '@/stores/engine'
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
    <p class="mt-3 flex items-start gap-2 rounded-xl border border-border bg-surface-2/40 p-3 text-xs leading-relaxed text-muted">
      <ServerCog class="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
      The app probes version, GPU and VRAM on every refresh (top bar pills and the Resources popover are live).
      Node-pack checks and feature gating arrive with the generation modules.
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
