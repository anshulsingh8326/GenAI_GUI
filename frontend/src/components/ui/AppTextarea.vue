<script setup lang="ts">
withDefaults(
  defineProps<{
    placeholder?: string
    rows?: number
    disabled?: boolean
  }>(),
  { rows: 4 },
)

const model = defineModel<string>({ default: '' })
</script>

<template>
  <textarea
    v-model="model"
    :rows="rows"
    :placeholder="placeholder"
    :disabled="disabled"
    class="w-full resize-y rounded-xl border border-border bg-surface px-3 py-2.5 text-sm leading-relaxed text-text outline-none transition-colors placeholder:text-muted/60 focus:border-accent/60 disabled:opacity-50"
  />
</template>
