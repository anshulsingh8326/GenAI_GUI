// Sidebar navigation config — grouped capability-first.
// Add new tabs here; each tab route lives in its own features/ folder.

export interface NavItem {
  id: string
  label: string
  to: string
  soon?: boolean
}

export interface NavGroup {
  id: 'image' | 'video' | 'audio' | 'library' | 'system'
  label: string
  items: NavItem[]
}

export const navGroups: NavGroup[] = [
  {
    id: 'image',
    label: 'Image',
    items: [
      { id: 'text-to-image', label: 'Text → Image', to: '/image/text-to-image' },
      { id: 'image-to-image', label: 'Image → Image', to: '/image/image-to-image', soon: true },
      { id: 'edit-image', label: 'Edit Image', to: '/image/edit-image', soon: true },
      { id: 'face-swap', label: 'Face Swap', to: '/image/face-swap', soon: true },
      { id: 'characters', label: 'Characters', to: '/image/characters' },
      { id: 'influencer', label: 'Influencer', to: '/image/influencer', soon: true },
      { id: 'game-assets', label: 'Game Assets', to: '/image/game-assets' },
    ],
  },
  {
    id: 'video',
    label: 'Video',
    items: [
      { id: 'image-to-video', label: 'Image → Video', to: '/video/image-to-video', soon: true },
      { id: 'text-to-video', label: 'Text → Video', to: '/video/text-to-video', soon: true },
      { id: 'video-to-video', label: 'Video → Video', to: '/video/video-to-video', soon: true },
    ],
  },
  {
    id: 'audio',
    label: 'Audio',
    items: [
      { id: 'text-to-speech', label: 'Text to Speech', to: '/audio/text-to-speech', soon: true },
      { id: 'music', label: 'Music', to: '/audio/music', soon: true },
      { id: 'sfx-foley', label: 'SFX & Foley', to: '/audio/sfx-foley', soon: true },
    ],
  },
  {
    id: 'library',
    label: 'Library',
    items: [
      { id: 'gallery', label: 'Gallery', to: '/gallery' },
      { id: 'presets', label: 'Presets', to: '/presets' },
    ],
  },
  {
    id: 'system',
    label: 'System',
    items: [
      { id: 'jobs', label: 'Jobs', to: '/jobs' },
      { id: 'settings', label: 'Settings', to: '/settings' },
    ],
  },
]
