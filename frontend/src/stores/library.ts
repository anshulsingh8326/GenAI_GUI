import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { Asset } from '@/types'
import { api } from '@/lib/api'
import { useUiStore } from './ui'

// Backend-first asset store. `GET /api/assets` is the source of truth: imported
// files, files dropped into the library folder, and outputs written by the
// (still mock) pipeline. Mutations go through the API; assets created while the
// backend is offline live in this list for the session only.

/** Session-only assets (offline mock results) are data URIs - no DB row behind them. */
function isSessionOnly(asset: Asset): boolean {
  return asset.url.startsWith('data:')
}

export const useLibraryStore = defineStore('library', () => {
  const ui = useUiStore()
  const assets = ref<Asset[]>([])
  const loaded = ref(false)
  const importing = ref(false)

  function byId(id: string): Asset | undefined {
    return assets.value.find((a) => a.id === id)
  }

  /** Replace the cache with the backend list; failures keep the current list. */
  async function syncFromBackend(): Promise<void> {
    try {
      assets.value = await api.getAssets({ limit: 500 })
      loaded.value = true
    } catch {
      /* backend offline - keep whatever is cached / session-only */
    }
  }

  /** Local insert (mock results). */
  function add(list: Asset[]) {
    assets.value.unshift(...list)
  }

  async function toggleFavorite(id: string) {
    const asset = byId(id)
    if (!asset) return
    const next = !asset.favorite
    asset.favorite = next
    if (isSessionOnly(asset)) return
    try {
      await api.updateAsset(id, { favorite: next })
    } catch (err) {
      asset.favorite = !next
      ui.toast(`Favorite not saved: ${(err as Error).message}`, 'warn')
    }
  }

  /** Move an asset to data/trash via the backend (recoverable - nothing is hard-deleted). */
  async function trash(id: string): Promise<boolean> {
    const asset = byId(id)
    if (asset && isSessionOnly(asset)) {
      assets.value = assets.value.filter((a) => a.id !== id)
      ui.toast(`Removed ${asset.label || id} (this session only)`)
      return true
    }
    try {
      const result = await api.trashAsset(id)
      assets.value = assets.value.filter((a) => a.id !== id)
      ui.toast(result.movedTo ? `Moved to trash: ${asset?.label || id}` : `Removed: ${asset?.label || id}`)
      return true
    } catch (err) {
      ui.toast(`Could not remove: ${(err as Error).message}`, 'error')
      return false
    }
  }

  /** Upload local files into the library (the backend writes them into the library folder). */
  async function importFiles(files: File[]): Promise<number> {
    if (!files.length) return 0
    importing.value = true
    const added: Asset[] = []
    const failed: string[] = []
    for (const file of files) {
      try {
        added.push(await api.importAsset(file))
      } catch (err) {
        failed.push(`${file.name}: ${(err as Error).message}`)
      }
    }
    assets.value.unshift(...added)
    importing.value = false
    if (added.length) {
      ui.toast(`Imported ${added.length} file${added.length > 1 ? 's' : ''} into the library`, 'success')
    }
    if (failed.length) ui.toast(`Import failed - ${failed.join('; ')}`, 'error', 6000)
    return added.length
  }

  return { assets, loaded, importing, byId, syncFromBackend, add, toggleFavorite, trash, importFiles }
})
