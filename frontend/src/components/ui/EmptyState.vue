<script setup lang="ts">
import { Sparkles } from '@lucide/vue'

defineProps<{
  title: string
  desc?: string
}>()
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-border bg-surface/50 px-6 py-14 text-center">
    <div class="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent-soft text-accent">
      <slot name="icon">
        <Sparkles class="h-5 w-5" />
      </slot>
    </div>
    <h3 class="text-sm font-semibold">{{ title }}</h3>
    <p v-if="desc" class="max-w-md text-xs leading-relaxed text-muted">{{ desc }}</p>
    <slot />
  </div>
</template>
