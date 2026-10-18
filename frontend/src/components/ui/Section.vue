<script setup lang="ts">
defineProps<{
  title: string
  desc?: string
}>()
</script>

<template>
  <section class="rounded-2xl border border-border bg-surface p-5">
    <header class="mb-4">
      <h3 class="text-sm font-semibold">{{ title }}</h3>
      <p v-if="desc" class="mt-0.5 text-xs leading-relaxed text-muted">{{ desc }}</p>
    </header>
    <slot />
  </section>
</template>
