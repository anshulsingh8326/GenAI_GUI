import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import type { ConnRuntime, LoadedModel, StatusSnapshot } from '@/types'
import { api } from '@/lib/api'
import { useUiStore } from './ui'

// Engine + resources: the live view of ComfyUI / Ollama / VRAM / RAM.
//
// Fed by GET /api/status (polled every few seconds - one call covers both
// engines and the hardware bars). Unload actions go through the backend,
// which owns the safety rules (it never loads a model just to unload it).
export const useEngineStore = defineStore('engine', () => {
  const ui = useUiStore()

  const comfy = reactive<ConnRuntime>({ connected: false, checking: false, detail: 'Waiting for the first probe...' })
  const ollama = reactive<ConnRuntime>({ connected: false, checking: false, detail: 'Waiting for the first probe...' })

  const gpu = reactive({ usedGb: 0, totalGb: 0, known: false })
  const ram = reactive({ usedGb: 0, totalGb: 0, known: false })
  const queue = reactive({ running: 0, pending: 0 })

  const comfyLoaded = ref<LoadedModel[]>([])
  const ollamaLoaded = ref<LoadedModel[]>([])
  const launching = ref(false)

  // jobs started by the GUI itself (mock chat jobs for now) - added on top of
  // what ComfyUI reports so the busy lock works while a run is in flight
  const localJobs = ref(0)
  const activeJobs = computed(() => queue.running + localJobs.value)
  const busy = computed(() => activeJobs.value + queue.pending > 0)
  const queueLabel = computed(() => {
    const parts: string[] = []
    if (activeJobs.value) parts.push(`${activeJobs.value} running`)
    if (queue.pending) parts.push(`${queue.pending} queued`)
    return parts.join(' - ') || 'Queue idle'
  })

  let pollTimer: ReturnType<typeof setInterval> | null = null

  function applySnapshot(s: StatusSnapshot) {
    comfy.connected = s.comfyui.connected
    comfy.detail = s.comfyui.detail
    ollama.connected = s.ollama.connected
    ollama.detail = s.ollama.detail

    queue.running = s.comfyui.queue.running
    queue.pending = s.comfyui.queue.pending

    const r = s.resources
    gpu.known = r.vramUsedGb !== null && r.vramTotalGb !== null
    if (gpu.known) {
      gpu.usedGb = r.vramUsedGb as number
      gpu.totalGb = r.vramTotalGb as number
    }
    ram.known = r.ramUsedGb !== null && r.ramTotalGb !== null
    if (ram.known) {
      ram.usedGb = r.ramUsedGb as number
      ram.totalGb = r.ramTotalGb as number
    }

    comfyLoaded.value = s.comfyui.loaded ?? []
    ollamaLoaded.value = s.ollama.loaded ?? []
  }

  /** Pull one status snapshot (poll interval + after every engine action). */
  async function refresh() {
    try {
      applySnapshot(await api.getStatus())
    } catch {
      comfy.connected = false
      comfy.detail = 'Backend unreachable - is it running?'
      ollama.connected = false
      ollama.detail = 'Backend unreachable - is it running?'
      queue.running = 0
      queue.pending = 0
    }
  }

  /** Called once on app start (after settings are synced so profiles are loaded). */
  function startPolling(intervalMs = 8000) {
    if (pollTimer) return
    void refresh()
    pollTimer = setInterval(refresh, intervalMs)
  }

  /** Full connection test for one engine (Settings > Connections "Test connection"). */
  async function test(kind: 'comfyui' | 'ollama') {
    const target = kind === 'comfyui' ? comfy : ollama
    target.checking = true
    try {
      const res = await api.testConnection(kind)
      target.connected = res.connected
      target.detail = res.detail
    } catch (err) {
      target.connected = false
      target.detail = err instanceof Error ? err.message : 'Test failed'
    } finally {
      target.checking = false
    }
  }

  async function unloadComfy() {
    if (busy.value) {
      ui.toast('Jobs are running - unload when the queue is idle.', 'warn')
      return
    }
    try {
      const res = await api.freeComfyui()
      ui.toast(res.message, res.ok ? 'success' : 'error')
      if (res.ok) await refresh()
    } catch (err) {
      ui.toast(err instanceof Error ? err.message : 'Unload failed', 'error')
    }
  }

  async function unloadOllama(id: string) {
    if (busy.value) {
      ui.toast('Jobs are running - unload when the queue is idle.', 'warn')
      return
    }
    const model = ollamaLoaded.value.find((m) => m.id === id)
    try {
      const res = await api.unloadOllama(model?.name ?? id)
      ui.toast(res.message, res.ok ? 'success' : 'error')
      if (res.ok) await refresh()
    } catch (err) {
      ui.toast(err instanceof Error ? err.message : 'Unload failed', 'error')
    }
  }

  async function unloadAllOllama() {
    if (busy.value) {
      ui.toast('Jobs are running - unload when the queue is idle.', 'warn')
      return
    }
    try {
      const res = await api.unloadOllama()
      ui.toast(res.message, res.ok ? 'success' : 'error')
      if (res.ok) await refresh()
    } catch (err) {
      ui.toast(err instanceof Error ? err.message : 'Unload failed', 'error')
    }
  }

  /** Start the user's ComfyUI launcher (.bat saved in Settings) in its own window. */
  async function launchComfy() {
    launching.value = true
    try {
      const res = await api.launchComfyui()
      ui.toast(res.detail, res.started ? 'success' : 'warn')
      // give it a moment to boot, then refresh so the pills flip when it is up
      if (res.started) setTimeout(() => void refresh(), 3000)
    } catch (err) {
      ui.toast(err instanceof Error ? err.message : 'Launch failed', 'error')
    } finally {
      launching.value = false
    }
  }

  // job bookkeeping for GUI-side runs (mock chat jobs until real jobs land)
  function jobStarted() {
    localJobs.value += 1
  }

  function jobFinished() {
    localJobs.value = Math.max(0, localJobs.value - 1)
  }

  return {
    comfy,
    ollama,
    gpu,
    ram,
    queue,
    busy,
    activeJobs,
    queueLabel,
    comfyLoaded,
    ollamaLoaded,
    launching,
    refresh,
    startPolling,
    test,
    unloadComfy,
    unloadOllama,
    unloadAllOllama,
    launchComfy,
    jobStarted,
    jobFinished,
  }
})
