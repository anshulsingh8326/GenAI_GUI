<script setup lang="ts">
import { CheckCircle2, Info, TriangleAlert, XCircle } from '@lucide/vue'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

const icons = { info: Info, success: CheckCircle2, warn: TriangleAlert, error: XCircle }
const colors = { info: 'text-accent', success: 'text-success', warn: 'text-warn', error: 'text-danger' }
</script>

<template>
  <div class="pointer-events-none fixed bottom-5 right-5 z-[60] flex w-80 flex-col gap-2">
    <TransitionGroup name="toast">
      <div
        v-for="t in ui.toasts"
        :key="t.id"
        class="pointer-events-auto flex items-start gap-2.5 rounded-2xl border border-border bg-surface px-4 py-3 shadow-2xl"
      >
        <component :is="icons[t.kind]" class="mt-0.5 h-4 w-4 shrink-0" :class="colors[t.kind]" />
        <p class="text-[13px] leading-snug">{{ t.message }}</p>
      </div>
    </TransitionGroup>
  </div>
</template>
