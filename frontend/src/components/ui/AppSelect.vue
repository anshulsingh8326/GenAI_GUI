<script setup lang="ts">
export interface SelectOption {
  value: string
  label: string
  disabled?: boolean
}

withDefaults(
  defineProps<{
    options: SelectOption[]
    disabled?: boolean
    size?: 'sm' | 'md'
  }>(),
  { size: 'md' },
)

const model = defineModel<string>({ default: '' })
</script>

<template>
  <select
    v-model="model"
    :disabled="disabled"
    class="w-full cursor-pointer rounded-xl border border-border bg-surface text-text outline-none transition-colors focus:border-accent/60 disabled:cursor-not-allowed disabled:opacity-50"
    :class="size === 'sm' ? 'h-8 px-2 text-[13px]' : 'h-10 px-2.5 text-sm'"
  >
    <option v-for="o in options" :key="o.value" :value="o.value" :disabled="o.disabled">
      {{ o.label }}
    </option>
  </select>
</template>
