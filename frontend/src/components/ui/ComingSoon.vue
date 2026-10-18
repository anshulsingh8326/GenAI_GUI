<script setup lang="ts">
import { Construction } from '@lucide/vue'
import Badge from './Badge.vue'

defineProps<{
  title: string
  blurb?: string
  planned?: string
  features?: string[]
}>()
</script>

<template>
  <div class="mx-auto max-w-2xl px-6 py-14">
    <div class="rounded-3xl border border-border bg-surface p-8 text-center">
      <div class="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">
        <Construction class="h-6 w-6" />
      </div>
      <h1 class="text-lg font-semibold">{{ title }}</h1>
      <p v-if="blurb" class="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted">{{ blurb }}</p>
      <div v-if="planned" class="mt-3">
        <Badge tone="accent">{{ planned }}</Badge>
      </div>
      <ul v-if="features?.length" class="mx-auto mt-6 max-w-sm space-y-2 text-left text-sm text-muted">
        <li v-for="f in features" :key="f" class="flex items-start gap-2">
          <span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent/60" />
          <span>{{ f }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>
