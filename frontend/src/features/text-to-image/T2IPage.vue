<script setup lang="ts">
import { t2iSuggestions } from '@/lib/fixtures'
import ChatThread from '@/components/chat/ChatThread.vue'
import ComposerBar from '@/components/chat/ComposerBar.vue'
import SessionBar from './components/SessionBar.vue'
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- session bar (module-specific component lives in this module's folder) -->
    <SessionBar tab-id="text-to-image" label="Krea2 Freeze pipeline" />

    <!-- chat thread -->
    <ChatThread tab-id="text-to-image" :suggestions="t2iSuggestions" />

    <!-- composer -->
    <ComposerBar tab-id="text-to-image" />
  </div>
</template>
