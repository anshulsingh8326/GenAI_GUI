<script setup lang="ts">
import { X } from '@lucide/vue'
import type { Attachment } from '@/types'

defineProps<{
  attachment: Attachment
}>()

defineEmits<{ (e: 'remove'): void }>()
</script>

<template>
  <div class="flex w-28 flex-col gap-1.5 rounded-xl border border-border bg-surface-2/60 p-1.5">
    <div class="relative h-16 w-full overflow-hidden rounded-lg">
      <img :src="attachment.url" class="h-full w-full object-cover" alt="" />
      <button
        class="absolute right-1 top-1 cursor-pointer rounded-md bg-black/50 p-0.5 text-white transition-colors hover:bg-black/75"
        title="Remove"
        @click="$emit('remove')"
      >
        <X class="h-3 w-3" />
      </button>
    </div>

    <div class="flex flex-wrap gap-1 px-0.5">
      <button
        class="cursor-pointer rounded-md px-1.5 py-0.5 text-[9px] font-semibold tracking-wide transition-colors"
        :class="attachment.identity ? 'bg-accent-soft text-accent' : 'bg-surface text-muted'"
        title="Use as identity reference (face / character)"
        @click="attachment.identity = !attachment.identity"
      >
        IDENTITY
      </button>
      <button
        class="cursor-pointer rounded-md px-1.5 py-0.5 text-[9px] font-semibold tracking-wide transition-colors"
        :class="attachment.describe ? 'bg-accent-soft text-accent' : 'bg-surface text-muted'"
        title="Describe this image and append the text to the prompt"
        @click="attachment.describe = !attachment.describe"
      >
        DESCRIBE
      </button>
    </div>

    <select
      v-if="attachment.describe"
      v-model="attachment.describeMode"
      class="w-full cursor-pointer rounded-md border border-border bg-surface px-1 py-0.5 text-[10px] text-muted"
    >
      <option value="character">Character only</option>
      <option value="full">Full image</option>
    </select>
  </div>
</template>
