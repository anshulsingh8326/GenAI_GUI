<script setup lang="ts">
import { ref } from 'vue'
import { FolderCheck, FolderOpen, LoaderCircle } from '@lucide/vue'
import { api, ApiError } from '@/lib/api'
import { useSettingsStore } from '@/stores/settings'
import { useUiStore } from '@/stores/ui'
import Section from '@/components/ui/Section.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import ResetButton from '@/components/ui/ResetButton.vue'

const settings = useSettingsStore()
const ui = useUiStore()

type FolderKey = 'library' | 'exports' | 'imports' | 'agentInbox'

const rows: { key: FolderKey; label: string; desc: string }[] = [
  { key: 'library', label: 'Library (assets)', desc: 'Every input and output asset lives here with full metadata.' },
  { key: 'exports', label: 'Exports', desc: 'Default target for download / export actions.' },
  { key: 'imports', label: 'Imports (watch folder)', desc: 'Drop files here and they appear in the gallery.' },
  { key: 'agentInbox', label: 'Agent inbox', desc: 'The only folder an AI agent is allowed to read/write through the app.' },
]

const checking = ref<FolderKey | null>(null)
const browsing = ref<FolderKey | null>(null)

async function check(key: FolderKey) {
  checking.value = key
  try {
    const res = await api.validateFolder(settings.folders[key], true)
    if (res.ok) {
      ui.toast(`${res.message} ${res.resolved}`, 'success')
    } else {
      ui.toast(res.message || 'Folder is not usable.', 'warn')
    }
  } catch (err) {
    ui.toast(
      err instanceof ApiError && err.isOffline
        ? 'Backend offline - start it to validate folders against the file system.'
        : `Folder check failed: ${err instanceof Error ? err.message : 'unknown error'}`,
      'warn',
    )
  } finally {
    checking.value = null
  }
}

async function browse(key: FolderKey) {
  browsing.value = key
  try {
    const res = await api.pickPath({
      mode: 'folder',
      title: `Select the ${key} folder`,
      start: settings.folders[key],
    })
    if (res.path) settings.folders[key] = res.path
  } catch (err) {
    ui.toast(
      err instanceof ApiError && err.isOffline
        ? 'Backend offline - the folder dialog opens on the machine running the backend.'
        : `Could not open the dialog: ${err instanceof Error ? err.message : 'unknown error'}`,
      'warn',
    )
  } finally {
    browsing.value = null
  }
}
</script>

<template>
  <Section
    title="Folders"
    desc="Where the library, exports and agent access point. Check validates the path against the real file system and creates it if missing."
  >
    <div class="space-y-4">
      <div v-for="r in rows" :key="r.key">
        <p class="text-xs font-medium">{{ r.label }}</p>
        <p class="mb-1 text-[11px] text-muted">{{ r.desc }}</p>
        <div class="flex flex-wrap items-center gap-2">
          <div class="min-w-64 flex-1"><AppInput v-model="settings.folders[r.key]" /></div>
          <AppButton variant="ghost" :disabled="checking === r.key" title="Validate against the file system (creates the folder if missing)" @click="check(r.key)">
            <LoaderCircle v-if="checking === r.key" class="h-3.5 w-3.5 animate-spin" />
            <FolderCheck v-else class="h-3.5 w-3.5" />
            Check
          </AppButton>
          <ResetButton :disabled="settings.isDefault(['folders', r.key])" @reset="settings.resetField(['folders', r.key])" />
          <AppButton variant="ghost" :disabled="browsing === r.key" @click="browse(r.key)">
            <LoaderCircle v-if="browsing === r.key" class="h-3.5 w-3.5 animate-spin" />
            <FolderOpen v-else class="h-3.5 w-3.5" /> Browse...
          </AppButton>
        </div>
      </div>

      <div>
        <p class="text-xs font-medium">ComfyUI models root (detected)</p>
        <p class="mb-1 text-[11px] text-muted">Read-only - detected from the ComfyUI probe; the app never stores weights.</p>
        <AppInput model-value="D:\ComfyUI\models  (auto-detected in backend session)" disabled />
      </div>
    </div>
  </Section>
</template>
