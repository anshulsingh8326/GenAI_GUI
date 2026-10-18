<script setup lang="ts">
import { useChatStore } from '@/stores/chat'

const props = defineProps<{
  tabId: string
  label: string
}>()

const chat = useChatStore()
</script>

<template>
  <div class="flex shrink-0 items-center gap-3 border-b border-border bg-surface/40 px-6 py-2">
    <p class="text-xs text-muted">
      Session - <span class="text-text">{{ props.label }}</span>
    </p>
    <div class="flex-1" />
    <button
      class="cursor-pointer text-xs text-muted transition-colors hover:text-text"
      title="Clear this thread and start fresh"
      @click="chat.resetThread(props.tabId)"
    >
      New session
    </button>
  </div>
</template>
