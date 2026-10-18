<script setup lang="ts">
import { X } from '@lucide/vue'

const open = defineModel<boolean>({ required: true })

withDefaults(
  defineProps<{
    title?: string
    subtitle?: string
    width?: string
  }>(),
  { width: '560px' },
)
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="open = false" />
        <div
          class="relative max-h-[86vh] w-full overflow-y-auto rounded-2xl border border-border bg-surface p-5 shadow-2xl"
          :style="{ maxWidth: width }"
        >
          <header v-if="title" class="mb-4 flex items-start justify-between gap-4">
            <div>
              <h2 class="text-base font-semibold">{{ title }}</h2>
              <p v-if="subtitle" class="mt-0.5 text-xs text-muted">{{ subtitle }}</p>
            </div>
            <button class="cursor-pointer rounded-lg p-1 text-muted transition-colors hover:bg-surface-2 hover:text-text" @click="open = false">
              <X class="h-4 w-4" />
            </button>
          </header>
          <slot />
          <footer v-if="$slots.footer" class="mt-5 flex justify-end gap-2">
            <slot name="footer" />
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
