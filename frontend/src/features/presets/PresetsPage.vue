<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Palette, Sparkles } from '@lucide/vue'
import { presets } from '@/lib/fixtures'
import { useUiStore } from '@/stores/ui'
import AppButton from '@/components/ui/AppButton.vue'
import Chip from '@/components/ui/Chip.vue'

const router = useRouter()
const ui = useUiStore()

const categories = ['All', ...Array.from(new Set(presets.map((p) => p.category)))]
const activeCategory = ref('All')

const filtered = computed(() =>
  activeCategory.value === 'All' ? presets : presets.filter((p) => p.category === activeCategory.value),
)

function applyPreset(name: string) {
  ui.toast(`Preset "${name}" applied to Text - Image (mock)`, 'success')
  router.push('/image/text-to-image')
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-6 py-6">
    <header class="mb-5">
      <h1 class="flex items-center gap-2 text-lg font-semibold">
        <Palette class="h-5 w-5 text-accent" /> Presets
      </h1>
      <p class="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
        One-click bundles: prompt template + style tokens + LoRA chain + settings. Apply to your idea and tweak
        anything it set.
      </p>
    </header>

    <div class="mb-5 flex flex-wrap gap-2">
      <Chip v-for="c in categories" :key="c" :active="activeCategory === c" @click="activeCategory = c">{{ c }}</Chip>
    </div>

    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div v-for="p in filtered" :key="p.id" class="flex flex-col rounded-2xl border border-border bg-surface p-4">
        <div class="mb-2 flex items-center justify-between">
          <p class="text-sm font-semibold">{{ p.name }}</p>
          <span class="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted">{{ p.category }}</span>
        </div>
        <p class="text-xs leading-relaxed text-muted">{{ p.description }}</p>
        <div class="mt-3 flex flex-wrap gap-1">
          <span v-for="t in p.tags" :key="t" class="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted">{{ t }}</span>
        </div>
        <div class="mt-4">
          <AppButton size="sm" variant="primary" @click="applyPreset(p.name)">
            <Sparkles class="h-3.5 w-3.5" /> Apply to my idea
          </AppButton>
        </div>
      </div>
    </div>
  </div>
</template>
