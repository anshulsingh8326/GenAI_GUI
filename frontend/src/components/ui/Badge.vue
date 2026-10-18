<script setup lang="ts">
withDefaults(
  defineProps<{
    tone?: 'neutral' | 'accent' | 'ok' | 'warn'
  }>(),
  { tone: 'neutral' },
)
</script>

<template>
  <span
    class="inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide"
    :class="{
      neutral: 'bg-surface-2 text-muted',
      accent: 'bg-accent-soft text-accent',
      ok: 'bg-success/15 text-success',
      warn: 'bg-warn/15 text-warn',
    }[tone]"
  >
    <slot />
  </span>
</template>
