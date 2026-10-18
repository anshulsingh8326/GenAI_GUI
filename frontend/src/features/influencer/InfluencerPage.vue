<script setup lang="ts">
import ComingSoon from '@/components/ui/ComingSoon.vue'
</script>

<template>
  <ComingSoon
    title="Influencer"
    blurb="Batch content generation for a character persona - varied scenes, outfits and presets, always the same identity."
    planned="Step 7 in the build plan (after Characters)"
    :features="[
      'Pick a character profile - identity conditioning stays on',
      'Concepts x variations matrix (scene list x takes)',
      'Preset pool per persona (styles, camera, NSFW families)',
      'Review board with keep / discard triage',
    ]"
  />
</template>
