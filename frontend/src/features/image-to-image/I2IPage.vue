<script setup lang="ts">
import ComingSoon from '@/components/ui/ComingSoon.vue'
</script>

<template>
  <ComingSoon
    title="Image - Image"
    blurb="Same chat composer as Text - Image, plus a source image card and a denoise slider. Everything else stays identical."
    planned="Step 5 in the build plan"
    :features="[
      'Source = upload, gallery asset or file path from an agent',
      'Denoise strength as the main creative knob',
      'Reuses the whole composer: model, LoRAs, size, batch, advanced',
      'Send-to-Img2Img action from every result and gallery asset',
    ]"
  />
</template>
