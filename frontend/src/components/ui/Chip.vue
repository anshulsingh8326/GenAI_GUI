<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    active?: boolean
    disabled?: boolean
  }>(),
  {},
)

const emit = defineEmits<{ (e: 'click'): void }>()

const cls = computed(() =>
  props.active
    ? 'border-accent/45 bg-accent-soft text-accent'
    : 'border-border bg-surface-2/70 text-muted hover:border-accent/30 hover:text-text',
)
</script>

<template>
  <button
    type="button"
    class="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40"
    :class="cls"
    :disabled="disabled"
    @click="emit('click')"
  >
    <slot />
  </button>
</template>
