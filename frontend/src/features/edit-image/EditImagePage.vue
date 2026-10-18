<script setup lang="ts">
import ComingSoon from '@/components/ui/ComingSoon.vue'
</script>

<template>
  <ComingSoon
    title="Edit Image"
    blurb="Source image + text instruction: add / remove / replace / restyle. Backed by a Qwen-Image-Edit class recipe."
    planned="Step 6 in the build plan"
    :features="[
      'Instruction box instead of a prompt - add a red hat, remove the lamp',
      'Edit-capable models only in the picker (capability gating)',
      'Chain freely: generate - edit - upscale as visible stages',
      'Same MCP tool surface for the agent',
    ]"
  />
</template>
