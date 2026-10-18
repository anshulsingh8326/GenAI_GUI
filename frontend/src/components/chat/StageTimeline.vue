<script setup lang="ts">
import { Check, Circle, LoaderCircle, XCircle } from '@lucide/vue'
import type { Stage } from '@/types'

defineProps<{
  stages: Stage[]
}>()
</script>

<template>
  <ol class="space-y-1.5">
    <li v-for="s in stages" :key="s.id" class="flex items-center gap-2.5 text-xs">
      <Check v-if="s.status === 'done'" class="h-3.5 w-3.5 shrink-0 text-success" />
      <LoaderCircle v-else-if="s.status === 'running'" class="h-3.5 w-3.5 shrink-0 animate-spin text-accent" />
      <XCircle v-else-if="s.status === 'error'" class="h-3.5 w-3.5 shrink-0 text-danger" />
      <Circle v-else class="h-3.5 w-3.5 shrink-0 text-border" />

      <span :class="s.status === 'pending' ? 'text-muted/60' : 'text-text'">{{ s.label }}</span>
      <span v-if="s.detail" class="truncate text-muted">- {{ s.detail }}</span>
      <span v-if="s.durationMs" class="ml-auto shrink-0 tabular-nums text-muted">
        {{ (s.durationMs / 1000).toFixed(1) }}s
      </span>
    </li>
  </ol>
</template>
