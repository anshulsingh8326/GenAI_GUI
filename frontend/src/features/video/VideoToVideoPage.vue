<script setup lang="ts">
import ComingSoon from '@/components/ui/ComingSoon.vue'
</script>

<template>
  <ComingSoon
    title="Video - Video"
    blurb="Face swap in video, character insertion into source clips - the meme / deepfake toolset, kept local and user-responsibility framed."
    planned="Step 11 in the build plan"
    :features="[
      'Frame-based swap + restore + temporal smoothing',
      'Subject-to-video class for character insertion into clips',
      'Source clip + character profile - template videos',
    ]"
  />
</template>
