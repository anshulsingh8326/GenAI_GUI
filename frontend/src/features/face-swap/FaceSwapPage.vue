<script setup lang="ts">
import ComingSoon from '@/components/ui/ComingSoon.vue'
</script>

<template>
  <ComingSoon
    title="Face Swap"
    blurb="ReActor + face restore as a standalone tool or the final stage of any chain."
    planned="Step 8 in the build plan"
    :features="[
      'Source face + target image - one click, one stage',
      'Optional GFPGAN restore and upscale after the swap',
      'Multi-source support (several faces in a scene)',
      'Available as a post-pass from every generation',
    ]"
  />
</template>
