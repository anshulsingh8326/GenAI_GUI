<script setup lang="ts">
withDefaults(
  defineProps<{
    state: 'ok' | 'off' | 'warn' | 'busy'
  }>(),
  { state: 'ok' },
)
</script>

<template>
  <span class="relative flex h-2.5 w-2.5 shrink-0">
    <span
      v-if="state === 'busy'"
      class="absolute inline-flex h-full w-full animate-ping rounded-full opacity-40"
      :class="{ ok: 'bg-success', off: 'bg-danger', warn: 'bg-warn', busy: 'bg-accent' }[state]"
    />
    <span
      class="relative inline-flex h-2.5 w-2.5 rounded-full"
      :class="{ ok: 'bg-success', off: 'bg-danger', warn: 'bg-warn', busy: 'bg-accent' }[state]"
    />
  </span>
</template>
