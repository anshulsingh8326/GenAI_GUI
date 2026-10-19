// ComfyUI content management - Phase A (read-only).
//
// Inspects the configured ComfyUI folder and audits what each installed
// generation module needs (custom nodes + model files) against it. Nothing in
// this store writes: installs/downloads arrive in later phases behind explicit
// clicks (docs/COMFYUI_CONTENT.md).

import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/lib/api'
import type { ComfyInspect, ComfyRequirements } from '@/types'

export const useContentStore = defineStore('content', () => {
  const inspect = ref<ComfyInspect | null>(null)
  const requirements = ref<ComfyRequirements | null>(null)
  const checking = ref(false)
  const lastError = ref<string | null>(null)

  // guards against overlapping polls (Connections + Engine content sections can
  // both trigger a refresh while the first one is still scanning the folder)
  let inflight: Promise<void> | null = null

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

  return { inspect, requirements, checking, lastError, refresh }
})
