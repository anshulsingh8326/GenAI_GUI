<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const open = defineModel<boolean>({ required: true })

withDefaults(
  defineProps<{
    align?: 'left' | 'right'
    up?: boolean
    width?: string
  }>(),
  { align: 'left', up: false, width: '18rem' },
)

const root = ref<HTMLElement | null>(null)

function onDocPointerDown(e: PointerEvent) {
  if (root.value && !root.value.contains(e.target as Node)) open.value = false
}

onMounted(() => document.addEventListener('pointerdown', onDocPointerDown))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onDocPointerDown))
</script>

<template>
  <div ref="root" class="relative inline-block">
    <slot name="trigger" />
    <Transition name="fade">
      <div
        v-if="open"
        class="absolute z-40 rounded-2xl border border-border bg-surface p-3 shadow-2xl"
        :class="[align === 'right' ? 'right-0' : 'left-0', up ? 'bottom-full mb-2' : 'top-full mt-2']"
        :style="{ width }"
      >
        <slot />
      </div>
    </Transition>
  </div>
</template>
