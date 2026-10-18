<script setup lang="ts">
import { useLibraryStore } from '@/stores/library'
import AppModal from '@/components/ui/AppModal.vue'

const open = defineModel<boolean>({ required: true })

const emit = defineEmits<{ (e: 'pick', id: string): void }>()

const library = useLibraryStore()
</script>

<template>
  <AppModal v-model="open" title="Pick from gallery" subtitle="Choose a reference image from your library" width="640px">
    <div class="grid max-h-96 grid-cols-3 gap-2 overflow-y-auto sm:grid-cols-4">
      <button
        v-for="a in library.assets"
        :key="a.id"
        class="group cursor-pointer overflow-hidden rounded-xl border border-border transition-colors hover:border-accent/50"
        @click="emit('pick', a.id)"
      >
        <img :src="a.url" class="aspect-square w-full object-cover transition-transform group-hover:scale-105" alt="" />
        <p class="truncate px-1.5 py-1 text-left text-[10px] text-muted">{{ a.label }}</p>
      </button>
    </div>
  </AppModal>
</template>
