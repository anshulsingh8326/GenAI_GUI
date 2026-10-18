<script setup lang="ts">
import ComingSoon from '@/components/ui/ComingSoon.vue'
</script>

<template>
  <ComingSoon
    title="Image - Video"
    blurb="Animate a library image into a short clip with motion presets. 12GB-class open models, chosen by manifest VRAM hints."
    planned="Step 10 in the build plan"
    :features="[
      'Source = gallery image or upload; motion presets (dolly, zoom, orbit)',
      'Wan / LTX / Hunyuan class GGUF quants for 12GB cards',
      'Video gallery with playback and thumbnails',
      'Audio-in-video where the model supports it',
    ]"
  />
</template>
