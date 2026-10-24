/** Shared types for the reusable media viewer. */

export interface MediaViewerMeta {
  label: string
  value: string
}

export interface MediaViewerItem {
  /** Asset id (or any stable id when the item is not a library asset). */
  id: string
  url: string
  thumbUrl?: string | null
  kind?: 'image' | 'video' | 'audio'
  label?: string
  prompt?: string
  /** Extra rows rendered in the info panel and available to slot content. */
  meta?: MediaViewerMeta[]
  /** Suggested download filename. The viewer falls back to the item label/id. */
  filename?: string
}
