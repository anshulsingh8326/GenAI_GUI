// Asset download helper - backend asset URLs (`/api/assets/{id}/file`) carry no
// file extension, so the download name is derived from the URL when possible.

import type { Asset } from '@/types'

const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'svg'])

function extensionFor(url: string): string {
  const match = /\.([a-z0-9]+)(?:[?#]|$)/i.exec(url)
  const ext = match?.[1].toLowerCase()
  return ext && IMAGE_EXTENSIONS.has(ext) ? ext : 'png'
}

/** Trigger a browser download of an asset file. */
export function downloadAsset(asset: Asset): void {
  const el = document.createElement('a')
  el.href = asset.url
  el.download = `${asset.label.replace(/[^\w-]+/g, '_') || 'asset'}.${extensionFor(asset.url)}`
  el.click()
}
