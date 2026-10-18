import { createRouter, createWebHistory } from 'vue-router'

// Feature pages — one folder per tab (see PLAN: GUI-first, mock data).
import T2IPage from '@/features/text-to-image/T2IPage.vue'
import I2IPage from '@/features/image-to-image/I2IPage.vue'
import EditImagePage from '@/features/edit-image/EditImagePage.vue'
import FaceSwapPage from '@/features/face-swap/FaceSwapPage.vue'
import CharactersPage from '@/features/characters/CharactersPage.vue'
import InfluencerPage from '@/features/influencer/InfluencerPage.vue'
import GameAssetsPage from '@/features/game-assets/GameAssetsPage.vue'
import ImageToVideoPage from '@/features/video/ImageToVideoPage.vue'
import TextToVideoPage from '@/features/video/TextToVideoPage.vue'
import VideoToVideoPage from '@/features/video/VideoToVideoPage.vue'
import TextToSpeechPage from '@/features/audio/TextToSpeechPage.vue'
import MusicPage from '@/features/audio/MusicPage.vue'
import SfxFoleyPage from '@/features/audio/SfxFoleyPage.vue'
import GalleryPage from '@/features/gallery/GalleryPage.vue'
import PresetsPage from '@/features/presets/PresetsPage.vue'
import JobsPage from '@/features/jobs/JobsPage.vue'
import SettingsPage from '@/features/settings/SettingsPage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/image/text-to-image' },

    { path: '/image/text-to-image', component: T2IPage, meta: { title: 'Text → Image' } },
    { path: '/image/image-to-image', component: I2IPage, meta: { title: 'Image → Image' } },
    { path: '/image/edit-image', component: EditImagePage, meta: { title: 'Edit Image' } },
    { path: '/image/face-swap', component: FaceSwapPage, meta: { title: 'Face Swap' } },
    { path: '/image/characters', component: CharactersPage, meta: { title: 'Characters' } },
    { path: '/image/influencer', component: InfluencerPage, meta: { title: 'Influencer' } },
    { path: '/image/game-assets', component: GameAssetsPage, meta: { title: 'Game Assets' } },

    { path: '/video/image-to-video', component: ImageToVideoPage, meta: { title: 'Image → Video' } },
    { path: '/video/text-to-video', component: TextToVideoPage, meta: { title: 'Text → Video' } },
    { path: '/video/video-to-video', component: VideoToVideoPage, meta: { title: 'Video → Video' } },

    { path: '/audio/text-to-speech', component: TextToSpeechPage, meta: { title: 'Text to Speech' } },
    { path: '/audio/music', component: MusicPage, meta: { title: 'Music' } },
    { path: '/audio/sfx-foley', component: SfxFoleyPage, meta: { title: 'SFX & Foley' } },

    { path: '/gallery', component: GalleryPage, meta: { title: 'Gallery' } },
    { path: '/presets', component: PresetsPage, meta: { title: 'Presets' } },
    { path: '/jobs', component: JobsPage, meta: { title: 'Jobs' } },
    { path: '/settings', component: SettingsPage, meta: { title: 'Settings' } },

    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
