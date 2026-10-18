<script setup lang="ts">
import { Check } from '@lucide/vue'
import type { AccentId, ThemeId } from '@/types'
import { useUiStore } from '@/stores/ui'
import Section from '@/components/ui/Section.vue'

const ui = useUiStore()

const themes: { id: ThemeId; name: string; desc: string; preview: { bg: string; surface: string; border: string; text: string; muted: string; accent: string } }[] = [
  {
    id: 'pastel-dark',
    name: 'Pastel Dark',
    desc: 'Deep plum base, soft pastel accents. The default studio look.',
    preview: { bg: '#141221', surface: '#1c1a2b', border: '#33304a', text: '#eceaf6', muted: '#a39ec2', accent: '#b8a7ee' },
  },
  {
    id: 'pastel-light',
    name: 'Pastel Light',
    desc: 'Soft lilac white, crisp cards. Same layout, daylight feel.',
    preview: { bg: '#f6f4fb', surface: '#ffffff', border: '#e2ddf0', text: '#2b2838', muted: '#6f6a85', accent: '#7f66e0' },
  },
]

const accents: { id: AccentId; color: string; name: string }[] = [
  { id: 'lavender', color: '#b8a7ee', name: 'Lavender' },
  { id: 'mint', color: '#8fe6c0', name: 'Mint' },
  { id: 'peach', color: '#ffc29e', name: 'Peach' },
  { id: 'sky', color: '#9ecbff', name: 'Sky' },
]
</script>

<template>
  <Section title="Theme" desc="Two pastel themes, both flat and minimal. Switch instantly - the quick toggle lives in the top bar.">
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <button
        v-for="t in themes"
        :key="t.id"
        class="cursor-pointer rounded-2xl border p-3 text-left transition-colors"
        :class="ui.theme === t.id ? 'border-accent/60 ring-2 ring-accent/25' : 'border-border hover:border-accent/30'"
        @click="ui.setTheme(t.id)"
      >
        <!-- mini preview -->
        <div class="overflow-hidden rounded-xl border" :style="{ background: t.preview.bg, borderColor: t.preview.border }">
          <div class="flex gap-1.5 p-2">
            <div class="h-14 w-1/3 rounded-lg border" :style="{ background: t.preview.surface, borderColor: t.preview.border }" />
            <div class="flex-1 space-y-1.5">
              <div class="h-3 w-2/3 rounded" :style="{ background: t.preview.muted, opacity: 0.35 }" />
              <div class="h-3 w-1/2 rounded" :style="{ background: t.preview.muted, opacity: 0.25 }" />
              <div class="h-3 w-1/3 rounded" :style="{ background: t.preview.accent }" />
            </div>
          </div>
        </div>
        <div class="mt-3 flex items-center gap-2">
          <p class="text-sm font-semibold">{{ t.name }}</p>
          <span v-if="ui.theme === t.id" class="flex items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-medium text-accent">
            <Check class="h-3 w-3" /> Active
          </span>
        </div>
        <p class="mt-1 text-xs leading-relaxed text-muted">{{ t.desc }}</p>
      </button>
    </div>
  </Section>

  <Section title="Accent" desc="The pastel accent used for actions, highlights and the active nav state.">
    <div class="flex flex-wrap gap-3">
      <button
        v-for="a in accents"
        :key="a.id"
        class="flex cursor-pointer items-center gap-2 rounded-full border px-3 py-2 transition-colors"
        :class="ui.accent === a.id ? 'border-accent/60 bg-accent-soft' : 'border-border hover:border-accent/30'"
        @click="ui.setAccent(a.id)"
      >
        <span class="h-4 w-4 rounded-full" :style="{ background: a.color }" />
        <span class="text-xs">{{ a.name }}</span>
      </button>
    </div>
  </Section>
</template>
