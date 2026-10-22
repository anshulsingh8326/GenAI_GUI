// ComfyUI content management.
//
// Inspection/audits are read-only. Installs and updates run only from explicit
// user clicks (docs/COMFYUI_CONTENT.md + docs/COMFYUI_INSTALLER.md): the backend
// streams a task, the store polls it, then re-runs the audit.

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/lib/api'
import type { ComfyInspect, ComfyInstallTask, ComfyRequirements } from '@/types'
import { useUiStore } from './ui'

export const useContentStore = defineStore('content', () => {
  const ui = useUiStore()

  const inspect = ref<ComfyInspect | null>(null)
  const requirements = ref<ComfyRequirements | null>(null)
  const checking = ref(false)
  const lastError = ref<string | null>(null)

  // install task state (one at a time, enforced by the backend)
  const installTask = ref<ComfyInstallTask | null>(null)
  const starting = ref(false)
  const restarting = ref(false)
  const installing = computed(() => installTask.value?.status === 'running')

  // guards against overlapping polls (Connections + Engine content sections can
  // both trigger a refresh while the first one is still scanning the folder)
  let inflight: Promise<void> | null = null
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let pollGeneration = 0

  async function refresh(): Promise<void> {
    if (inflight) return inflight
    checking.value = true
    inflight = (async () => {
      try {
        requirements.value = await api.getComfyRequirements()
        inspect.value = requirements.value.inspect
        lastError.value = null
      } catch (err) {
        lastError.value = err instanceof Error ? err.message : 'Could not inspect the ComfyUI folder.'
      } finally {
        inflight = null
        checking.value = false
      }
    })()
    return inflight
  }

  function stopPolling(): void {
    pollGeneration += 1
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  function taskMatches(moduleId: string, nodeName: string): boolean {
    return installTask.value?.moduleId === moduleId && installTask.value.nodeName === nodeName
  }

  function pollInstall(generation: number): void {
    pollTimer = setTimeout(async () => {
      const current = installTask.value
      if (!current || generation !== pollGeneration) return
      try {
        const next = await api.getComfyInstallTask(current.id)
        if (generation !== pollGeneration) return
        installTask.value = next
        if (next.status === 'running') {
          pollInstall(generation)
          return
        }
        if (next.status === 'succeeded') {
          ui.toast(`${next.nodeName} installed - restart ComfyUI to load it`, 'success')
          await refresh()
        } else {
          ui.toast(`Install failed: ${next.nodeName}`, 'error')
        }
      } catch (err) {
        if (generation !== pollGeneration) return
        ui.toast(err instanceof Error ? err.message : 'Could not read the install task.', 'error')
      }
    }, 700)
  }

  /** Start an install/update and poll its log. false = request could not start. */
  async function startInstall(moduleId: string, nodeName: string): Promise<boolean> {
    if (installing.value) return false
    starting.value = true
    try {
      stopPolling()
      const task = await api.installComfyNode(moduleId, nodeName)
      installTask.value = task
      pollInstall(pollGeneration)
      return true
    } catch (err) {
      ui.toast(err instanceof Error ? err.message : 'Could not start the install.', 'error')
      return false
    } finally {
      starting.value = false
    }
  }

  async function restartComfyui(): Promise<void> {
    if (restarting.value) return
    restarting.value = true
    try {
      const result = await api.restartComfyui()
      ui.toast(result.message, result.restarted ? 'success' : 'warn')
    } catch (err) {
      ui.toast(err instanceof Error ? err.message : 'Could not restart ComfyUI.', 'error')
    } finally {
      restarting.value = false
    }
  }

  /** Drop the task once it is finished (keeps a running install visible). */
  function clearInstallTask(): void {
    if (!installing.value) {
      stopPolling()
      installTask.value = null
    }
  }

  return {
    inspect,
    requirements,
    checking,
    lastError,
    refresh,
    installTask,
    installing,
    starting,
    restarting,
    startInstall,
    restartComfyui,
    clearInstallTask,
    taskMatches,
  }
})
