<script setup lang="ts">
import { RotateCcw } from '@lucide/vue'

// Small ghost icon button that restores one field to its shipped default.
// Disabled (and dimmed) while the field already holds the default value, so
// it doubles as a "modified?" indicator across the Settings page.
withDefaults(defineProps<{ disabled?: boolean; label?: string }>(), { label: 'Reset to default' })
const emit = defineEmits<{ (e: 'reset'): void }>()
</script>

<template>
  <button
    type="button"
    class="inline-flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-xl border border-border bg-surface text-muted transition-colors hover:border-accent/40 hover:text-text disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:border-border disabled:hover:text-muted"
    :title="label"
    :disabled="disabled"
    @click="emit('reset')"
  >
    <RotateCcw class="h-4 w-4" />
  </button>
</template>
