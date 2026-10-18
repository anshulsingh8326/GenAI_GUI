<script setup lang="ts">
withDefaults(
  defineProps<{
    min?: number
    max?: number
    step?: number
    label?: string
    disabled?: boolean
  }>(),
  { min: 0, max: 100, step: 1 },
)

const model = defineModel<number>({ default: 0 })
</script>

<template>
  <div class="flex items-center gap-3">
    <div class="flex-1">
      <div v-if="label" class="mb-1 flex justify-between text-[11px] text-muted">
        <span>{{ label }}</span>
      </div>
      <input
        v-model.number="model"
        type="range"
        :min="min"
        :max="max"
        :step="step"
        :disabled="disabled"
        class="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-border disabled:opacity-50"
        :style="{ accentColor: 'var(--c-accent)' }"
      />
    </div>
    <span class="w-10 text-right text-xs tabular-nums text-muted">{{ model }}</span>
  </div>
</template>
