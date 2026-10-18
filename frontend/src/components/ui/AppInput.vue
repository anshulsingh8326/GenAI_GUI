<script setup lang="ts">
withDefaults(
  defineProps<{
    placeholder?: string
    type?: string
    disabled?: boolean
    size?: 'sm' | 'md'
  }>(),
  { type: 'text', size: 'md' },
)

const model = defineModel<string>({ default: '' })
</script>

<template>
  <input
    v-model="model"
    :type="type"
    :placeholder="placeholder"
    :disabled="disabled"
    class="w-full rounded-xl border border-border bg-surface text-text outline-none transition-colors placeholder:text-muted/60 focus:border-accent/60 disabled:opacity-50"
    :class="size === 'sm' ? 'h-8 px-2.5 text-[13px]' : 'h-10 px-3 text-sm'"
  />
</template>
