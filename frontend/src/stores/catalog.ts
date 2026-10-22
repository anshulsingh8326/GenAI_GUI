// Model + LoRA catalog store.
//
// The catalog is built explicitly from ComfyUI headers in Settings -> Model
// catalog. The composer reads the same store, so edits (strength range,
// triggers) apply immediately. Trigger words are never written into the
// textarea: `promptWithTriggers()` adds them to the job prompt at send time,
// in LoRA-chain order and without duplicates.

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/lib/api'
import type {
  CatalogLoraEntry,
  CatalogLoraPatch,
  CatalogModelEntry,
  CatalogModelPatch,
  CatalogRange,
  ModelCatalog,
} from '@/types'
import { useUiStore } from './ui'

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

export const useCatalogStore = defineStore('catalog', () => {
  const ui = useUiStore()

  const data = ref<ModelCatalog | null>(null)
  const loading = ref(false)
  const refreshing = ref(false)
  const saving = ref<string | null>(null)
  const error = ref<string | null>(null)

  let loaded = false
  let inflight: Promise<void> | null = null

  const models = computed<CatalogModelEntry[]>(() => data.value?.models ?? [])
  const loras = computed<CatalogLoraEntry[]>(() => data.value?.loras ?? [])
  const baseModels = computed(() => models.value.filter((m) => m.role === 'base'))
  const companions = computed(() => models.value.filter((m) => m.role !== 'base'))
  const bases = computed(() => data.value?.bases ?? [])
  const hasCatalog = computed(() => Boolean(data.value?.updatedAt))
  const stats = computed(
    () => data.value?.stats ?? { models: 0, baseModels: 0, loras: 0, missing: 0, withTriggers: 0 },
  )

  const loraById = computed(() => new Map(loras.value.map((l) => [l.id, l])))
  const modelById = computed(() => new Map(models.value.map((m) => [m.id, m])))

  function byLora(id: string): CatalogLoraEntry | undefined {
    return loraById.value.get(id)
  }

  function byModel(id: string): CatalogModelEntry | undefined {
    return modelById.value.get(id)
  }

  function baseLabel(id: string | null): string {
    if (!id) return 'Unassigned'
    return bases.value.find((b) => b.id === id)?.label ?? id
  }

  function modelLabel(id: string): string {
    return byModel(id)?.label ?? id
  }

  function autoModelsFor(base: string | null): CatalogModelEntry[] {
    if (!base) return []
    return baseModels.value.filter((model) => model.base === base)
  }

  async function load(): Promise<void> {
    if (inflight) return inflight
    loading.value = true
    inflight = (async () => {
      try {
        data.value = await api.getModelCatalog()
        error.value = null
        loaded = true
      } catch (err) {
        error.value = errorText(err)
      } finally {
        loading.value = false
        inflight = null
      }
    })()
    return inflight
  }

  /** Load once; retries after an earlier failure (e.g. backend was starting). */
  async function ensureLoaded(): Promise<void> {
    if (!loaded) await load()
  }

  async function refresh(): Promise<void> {
    if (refreshing.value) return
    refreshing.value = true
    try {
      data.value = await api.refreshModelCatalog()
      error.value = null
      loaded = true
      ui.toast(
        `Catalog refreshed - ${data.value.stats.baseModels} base models, ${data.value.stats.loras} LoRAs`,
        'success',
      )
    } catch (err) {
      error.value = errorText(err)
      ui.toast(`Catalog refresh failed: ${errorText(err)}`, 'error')
    } finally {
      refreshing.value = false
    }
  }

  async function saveLora(id: string, patch: CatalogLoraPatch): Promise<boolean> {
    if (saving.value) return false
    saving.value = id
    try {
      data.value = await api.updateCatalogLora(id, patch)
      loaded = true
      ui.toast('LoRA catalog entry saved', 'success')
      return true
    } catch (err) {
      ui.toast(`Could not save LoRA: ${errorText(err)}`, 'error')
      return false
    } finally {
      saving.value = null
    }
  }

  async function saveModel(id: string, patch: CatalogModelPatch): Promise<boolean> {
    if (saving.value) return false
    saving.value = id
    try {
      data.value = await api.updateCatalogModel(id, patch)
      loaded = true
      ui.toast('Model catalog entry saved', 'success')
      return true
    } catch (err) {
      ui.toast(`Could not save model: ${errorText(err)}`, 'error')
      return false
    } finally {
      saving.value = null
    }
  }

  /** Active LoRA trigger words, chain order, case-insensitive dedupe. */
  function triggersFor(ids: string[]): string[] {
    const out: string[] = []
    const seen = new Set<string>()
    for (const id of ids) {
      for (const trigger of byLora(id)?.triggers ?? []) {
        const text = trigger.trim()
        const key = text.toLowerCase()
        if (text && !seen.has(key)) {
          seen.add(key)
          out.push(text)
        }
      }
    }
    return out
  }

  function containsWord(text: string, word: string): boolean {
    if (!word) return true
    const escaped = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    try {
      return new RegExp(`(?<!\\w)${escaped}(?!\\w)`, 'i').test(text)
    } catch {
      return text.toLowerCase().includes(word.toLowerCase())
    }
  }

  /** Prompt sent to the engine: trigger words appended, existing triggers not repeated. */
  function promptWithTriggers(prompt: string, ids: string[]): string {
    const text = prompt.trim()
    const missing = triggersFor(ids).filter((trigger) => !containsWord(text, trigger))
    if (!missing.length) return text
    return text ? `${text}, ${missing.join(', ')}` : missing.join(', ')
  }

  /** Default weight for a new chain entry, clamped into its catalog range. */
  function defaultStrength(id: string): number {
    const range = byLora(id)?.strength
    if (!range) return 1
    return Math.min(range.max, Math.max(range.min, range.default))
  }

  function strengthRange(id: string): CatalogRange {
    return byLora(id)?.strength ?? { default: 1, min: 0, max: 2, step: 0.05 }
  }

  return {
    data,
    models,
    loras,
    baseModels,
    companions,
    bases,
    stats,
    hasCatalog,
    loading,
    refreshing,
    saving,
    error,
    load,
    ensureLoaded,
    refresh,
    saveLora,
    saveModel,
    byLora,
    byModel,
    baseLabel,
    modelLabel,
    autoModelsFor,
    triggersFor,
    promptWithTriggers,
    defaultStrength,
    strengthRange,
  }
})
