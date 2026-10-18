<script setup lang="ts">
import type { ChatMessage } from '@/types'

defineProps<{
  message: ChatMessage
}>()
</script>

<template>
  <div class="flex justify-end">
    <div class="max-w-[85%] rounded-2xl rounded-br-md border border-border bg-surface px-4 py-3">
      <div v-if="message.attachments?.length" class="mb-2 flex flex-wrap gap-2">
        <div v-for="a in message.attachments" :key="a.id" class="relative h-16 w-16 overflow-hidden rounded-xl border border-border">
          <img :src="a.url" class="h-full w-full object-cover" alt="" />
          <div class="absolute inset-x-0 bottom-0 flex gap-1 bg-black/45 px-1 py-0.5 text-[8px] font-semibold uppercase text-white">
            <span v-if="a.identity">ID</span>
            <span v-if="a.describe">DESC{{ a.describeMode === 'character' ? '-C' : '' }}</span>
          </div>
        </div>
      </div>
      <p class="whitespace-pre-wrap text-sm leading-relaxed">{{ message.text }}</p>
    </div>
  </div>
</template>
