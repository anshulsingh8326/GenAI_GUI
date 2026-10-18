<script setup lang="ts">
import ComingSoon from '@/components/ui/ComingSoon.vue'
</script>

<template>
  <ComingSoon
    title="Text - Video"
    blurb="Full text-to-video generation with the same chat composer and stage timeline."
    planned="Step 10 in the build plan"
    :features="[
      'Prompt - clip with motion presets and duration control',
      'Batch variations: one concept, N takes, pick the best',
      'Same preset system as images where applicable',
    ]"
  />
</template>
