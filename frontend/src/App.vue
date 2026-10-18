<script setup lang="ts">
import { onMounted } from 'vue'
import AppShell from '@/components/layout/AppShell.vue'
import ToastHost from '@/components/ui/ToastHost.vue'
import { useUiStore } from '@/stores/ui'
import { useSettingsStore } from '@/stores/settings'
import { useEngineStore } from '@/stores/engine'
import { useJobsStore } from '@/stores/jobs'
import { useLibraryStore } from '@/stores/library'

const ui = useUiStore()
const settings = useSettingsStore()
const engine = useEngineStore()
const jobs = useJobsStore()
const library = useLibraryStore()

onMounted(async () => {
  ui.applyTheme()
  // Pull settings + shipped defaults from the backend (falls back to the
  // browser cache when it is not running), then start probing the engines and
  // load the job history + library.
  await settings.syncFromBackend()
  engine.startPolling()
  void jobs.syncFromBackend()
  void library.syncFromBackend()
})
</script>

<template>
  <AppShell />
  <ToastHost />
</template>
