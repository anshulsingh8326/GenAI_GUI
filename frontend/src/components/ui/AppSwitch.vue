<script setup lang="ts">
withDefaults(
  defineProps<{
    label?: string
    disabled?: boolean
  }>(),
  {},
)

const model = defineModel<boolean>({ default: false })
</script>

<template>
  <label class="inline-flex cursor-pointer items-center gap-2 select-none" :class="disabled ? 'cursor-not-allowed opacity-50' : ''">
    <button
      type="button"
      role="switch"
      :aria-checked="model"
      :disabled="disabled"
      class="relative h-6 w-10 shrink-0 cursor-pointer rounded-full transition-colors"
      :class="model ? 'bg-accent' : 'bg-border'"
      @click="model = !model"
    >
      <span
        class="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-all"
        :class="model ? 'left-[18px]' : 'left-0.5'"
      />
    </button>
    <span v-if="label" class="text-sm">{{ label }}</span>
  </label>
</template>
