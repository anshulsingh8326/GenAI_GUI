<script setup lang="ts">
export interface TabDef {
  id: string
  label: string
  soon?: boolean
}

defineProps<{
  tabs: TabDef[]
}>()

const model = defineModel<string>({ required: true })
</script>

<template>
  <div class="inline-flex flex-wrap gap-1 rounded-2xl border border-border bg-surface p-1.5">
    <button
      v-for="t in tabs"
      :key="t.id"
      type="button"
      class="h-8 cursor-pointer rounded-xl px-3 text-[13px] transition-colors"
      :class="model === t.id ? 'bg-accent-soft font-medium text-accent' : 'text-muted hover:bg-surface-2 hover:text-text'"
      @click="model = t.id"
    >
      {{ t.label }}
      <span v-if="t.soon" class="ml-1 text-[10px] opacity-60">soon</span>
    </button>
  </div>
</template>
