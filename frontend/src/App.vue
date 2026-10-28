<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AppShell from '@/components/layout/AppShell.vue'
import ToastHost from '@/components/ui/ToastHost.vue'
import ComfySetupModal from '@/components/content/ComfySetupModal.vue'
import { useUiStore } from '@/stores/ui'
import { useSettingsStore } from '@/stores/settings'
import { useEngineStore } from '@/stores/engine'
import { useJobsStore } from '@/stores/jobs'
import { useLibraryStore } from '@/stores/library'
import { useContentStore } from '@/stores/content'

const ui = useUiStore()
const settings = useSettingsStore()
const engine = useEngineStore()
const jobs = useJobsStore()
const library = useLibraryStore()
const content = useContentStore()

const SETUP_DISMISSED_KEY = 'genai.comfy-setup.dismissed.v1'
const setupOpen = ref(false)
const setupChecked = ref(false)

/** Changes whenever the startup setup state changes; used to avoid re-opening a dismissed popup. */
const setupSignature = computed(() => {
  const report = content.requirements
  if (!report) return ''
  if (!report.inspect.valid) {
    return `folder|${report.inspect.configured}|${report.inspect.path}|${report.inspect.suggestedFolder ?? ''}`
  }
  const missing: string[] = []
  for (const node of report.core.nodes) {
    if (node.installed === false && !node.optional) missing.push(`core:${node.name}`)
  }
  for (const mod of report.modules) {
    for (const node of mod.nodes) {
      if (node.installed === false && !node.optional) missing.push(`${mod.id}:${node.name}`)
    }
  }
  return missing.sort().join('|')
})

onMounted(async () => {
  ui.applyTheme()
  // Pull settings + shipped defaults from the backend (falls back to the
  // browser cache when it is not running), then start probing the engines and
  // load the job history + library.
  await settings.syncFromBackend()
  // First run can have local settings that were not pushed yet; flush them
  // before the content audit reads settings.json.
  await settings.flushSettings()
  await content.refresh()
  setupChecked.value = true

  const signature = setupSignature.value
  if (signature && sessionStorage.getItem(SETUP_DISMISSED_KEY) !== signature) {
    setupOpen.value = true
  }

  engine.startPolling()
  void jobs.syncFromBackend()
  void library.syncFromBackend()
})

watch(setupOpen, (open) => {
  if (open || !setupChecked.value) return
  const signature = setupSignature.value
  if (signature) sessionStorage.setItem(SETUP_DISMISSED_KEY, signature)
  else sessionStorage.removeItem(SETUP_DISMISSED_KEY)
})
</script>

<template>
  <AppShell />
  <ToastHost />
  <ComfySetupModal v-model="setupOpen" />
</template>
