<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Save, TriangleAlert } from '@lucide/vue'
import { useSettingsStore } from '@/stores/settings'
import AppTabs from '@/components/ui/AppTabs.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppModal from '@/components/ui/AppModal.vue'
import StatusDot from '@/components/ui/StatusDot.vue'
import AppearanceSection from './sections/AppearanceSection.vue'
import ConnectionsSection from './sections/ConnectionsSection.vue'
import DefaultsSection from './sections/DefaultsSection.vue'
import FoldersSection from './sections/FoldersSection.vue'
import TextPromptsSection from './sections/TextPromptsSection.vue'
import ResourcesSection from './sections/ResourcesSection.vue'
import AgentSection from './sections/AgentSection.vue'

const route = useRoute()
const router = useRouter()
const settings = useSettingsStore()

const tabs = [
  { id: 'appearance', label: 'Appearance' },
  { id: 'connections', label: 'Connections' },
  { id: 'defaults', label: 'Defaults & Models' },
  { id: 'folders', label: 'Folders' },
  { id: 'text', label: 'Text & Prompts' },
  { id: 'resources', label: 'Resources' },
  { id: 'agent', label: 'Agent Access' },
]

const tab = ref<string>((route.query.tab as string) ?? 'appearance')

watch(tab, (t) => router.replace({ query: { ...route.query, tab: t } }))

const syncState = computed<'ok' | 'busy' | 'warn'>(() => {
  if (settings.backendState === 'connecting') return 'busy'
  if (settings.backendState === 'offline') return 'warn'
  return settings.saving ? 'busy' : 'ok'
})

const syncText = computed(() => {
  if (settings.backendState === 'connecting') return 'Connecting to the backend...'
  if (settings.backendState === 'offline')
    return 'Backend offline - changes are kept in the browser and pushed to settings.json when it is back.'
  return settings.saving ? 'Saving to settings.json...' : 'Synced with the backend - every change is written to settings.json automatically.'
})

const confirmReset = ref(false)

async function doResetAll() {
  confirmReset.value = false
  await settings.resetAll()
}
</script>

<template>
  <div class="mx-auto max-w-4xl px-6 py-6">
    <header class="mb-5">
      <h1 class="text-lg font-semibold">Settings</h1>
      <p class="mt-1 flex flex-wrap items-center gap-2 text-sm leading-relaxed text-muted">
        <StatusDot :state="syncState" />
        <span>{{ syncText }}</span>
      </p>
      <p v-if="settings.backendState === 'live' && settings.systemInfo" class="mt-1 text-[11px] text-muted">
        <Save class="mr-1 inline h-3 w-3" />
        <code class="rounded bg-surface-2 px-1 py-0.5">{{ settings.systemInfo.settingsFile }}</code>
      </p>
      <p v-else-if="settings.lastError" class="mt-1 text-[11px] text-warn">{{ settings.lastError }}</p>
    </header>

    <AppTabs v-model="tab" :tabs="tabs" class="mb-5" />

    <div class="space-y-4">
      <AppearanceSection v-if="tab === 'appearance'" />
      <ConnectionsSection v-else-if="tab === 'connections'" />
      <DefaultsSection v-else-if="tab === 'defaults'" />
      <FoldersSection v-else-if="tab === 'folders'" />
      <TextPromptsSection v-else-if="tab === 'text'" />
      <ResourcesSection v-else-if="tab === 'resources'" />
      <AgentSection v-else-if="tab === 'agent'" />
    </div>

    <!-- reset all - always visible, deliberately at the very bottom -->
    <div class="mt-8 rounded-2xl border border-border bg-surface p-5">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="max-w-xl">
          <p class="text-sm font-semibold">Reset settings</p>
          <p class="mt-0.5 text-xs leading-relaxed text-muted">
            Restores connections and profiles, model and text defaults, folders, prompts and the agent token to
            the shipped defaults. Files, library assets and jobs are never touched.
          </p>
        </div>
        <AppButton variant="danger" @click="confirmReset = true">Reset all to defaults</AppButton>
      </div>
    </div>

    <AppModal
      v-model="confirmReset"
      title="Reset all settings to defaults?"
      subtitle="This cannot be undone."
      width="480px"
    >
      <div class="space-y-3 text-sm leading-relaxed text-muted">
        <p>Every setting on this page goes back to its shipped default:</p>
        <ul class="list-disc space-y-1 pl-5 text-xs">
          <li>Connections and connection profiles (URLs, auth headers)</li>
          <li>Model and text defaults</li>
          <li>Folder paths</li>
          <li>Text prompts and the agent token</li>
        </ul>
        <p class="flex items-start gap-2 rounded-xl border border-warn/30 bg-warn/10 p-3 text-xs text-warn">
          <TriangleAlert class="mt-0.5 h-3.5 w-3.5 shrink-0" />
          Nothing on disk is deleted - the folders and their files stay exactly as they are. Only
          settings.json is overwritten with the defaults.
        </p>
      </div>
      <template #footer>
        <AppButton variant="ghost" @click="confirmReset = false">Cancel</AppButton>
        <AppButton variant="danger" @click="doResetAll">Yes, reset everything</AppButton>
      </template>
    </AppModal>
  </div>
</template>
