<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    variant?: 'primary' | 'soft' | 'ghost' | 'danger'
    size?: 'sm' | 'md' | 'lg'
    disabled?: boolean
    block?: boolean
  }>(),
  { variant: 'soft', size: 'md' },
)

const sizeClass = computed(
  () =>
    ({
      sm: 'h-8 px-3 text-[13px] rounded-lg',
      md: 'h-10 px-4 text-sm rounded-xl',
      lg: 'h-11 px-5 text-sm rounded-xl',
    })[props.size],
)

const variantClass = computed(
  () =>
    ({
      primary: 'bg-accent text-accent-contrast hover:brightness-105 active:brightness-95',
      soft: 'bg-surface-2 text-text border border-border hover:border-accent/40',
      ghost: 'bg-transparent text-muted hover:text-text hover:bg-surface-2',
      danger: 'bg-danger/15 text-danger hover:bg-danger/25',
    })[props.variant],
)
</script>

<template>
  <button
    class="inline-flex cursor-pointer select-none items-center justify-center gap-2 font-medium transition-all disabled:cursor-not-allowed disabled:opacity-45"
    :class="[sizeClass, variantClass, block ? 'w-full' : '']"
    :disabled="disabled"
  >
    <slot />
  </button>
</template>
