<script setup lang="ts">
import { ref } from 'vue'
import { Download, Gamepad2, Star } from '@lucide/vue'
import { placeholderImage } from '@/lib/placeholder'
import { useUiStore } from '@/stores/ui'
import AppButton from '@/components/ui/AppButton.vue'
import Chip from '@/components/ui/Chip.vue'

const ui = useUiStore()

const lanes = ['RPG Item Icon', 'Character Portrait', 'Tileable Texture', 'UI Kit', 'Background']
const activeLane = ref('RPG Item Icon')

const items = ref(
  [
    'health potion',
    'iron sword',
    'mana crystal',
    'treasure chest',
    'wooden shield',
    'scroll of fire',
    'gold coins',
    'magic ring',
  ].map((label, i) => ({
    id: 'ga-' + i,
    label,
    url: placeholderImage(label, i, 512, 512),
    starred: i === 0 || i === 3,
  })),
)

const pipeline = [
  'Preset: RPG Item Icon (tokens + LoRA + size + transparent output)',
  'Batch generate per prompt (4 variations, pick by starring)',
  'Use the starred item as a describe-source for style consistency',
  'Background removal runs as a stage -> alpha PNG',
  'Export set with a naming pattern (icon_{slug}_{###}.png)',
]

function mockOnly(label: string) {
  ui.toast(`${label} - arrives in an upcoming GUI session (preview only)`)
}

function selectLane(lane: string) {
  activeLane.value = lane
  if (lane !== 'RPG Item Icon') mockOnly('Lane "' + lane + '"')
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-6 py-6">
    <header class="mb-5">
      <h1 class="flex items-center gap-2 text-lg font-semibold">
        <Gamepad2 class="h-5 w-5 text-accent" /> Game Assets
      </h1>
      <p class="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
        A guided, preset-driven workspace for game art: consistent style across a set, transparent backgrounds,
        batches you triage with stars, and engine-ready export. Built on the same generation engine - no special mode.
      </p>
    </header>

    <!-- preset lanes -->
    <div class="mb-5 flex flex-wrap items-center gap-2">
      <Chip v-for="lane in lanes" :key="lane" :active="activeLane === lane" @click="selectLane(lane)">
        {{ lane }}
      </Chip>
    </div>

    <div class="flex flex-col gap-5 lg:flex-row">
      <!-- board -->
      <div class="flex-1">
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div
            v-for="item in items"
            :key="item.id"
            class="group relative cursor-pointer overflow-hidden rounded-2xl border border-border bg-surface transition-colors hover:border-accent/40"
          >
            <div class="checkerboard">
              <img :src="item.url" class="aspect-square w-full object-cover" alt="" />
            </div>
            <button
              class="absolute left-2 top-2 cursor-pointer rounded-lg bg-black/40 p-1.5 transition-opacity"
              :class="item.starred ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'"
              @click="item.starred = !item.starred"
            >
              <Star class="h-3.5 w-3.5" :class="item.starred ? 'fill-amber-300 text-amber-300' : 'text-white'" />
            </button>
            <p class="truncate px-2.5 py-2 text-[11px] text-muted">{{ item.label }}</p>
          </div>
        </div>
        <p class="mt-3 text-center text-[10px] text-muted">
          Checkerboard = transparent PNG output (background-removal stage). Preview uses mock assets.
        </p>
      </div>

      <!-- pipeline + export -->
      <aside class="w-full shrink-0 space-y-4 lg:w-80">
        <div class="rounded-2xl border border-border bg-surface p-4">
          <h3 class="mb-3 text-sm font-semibold">The pipeline</h3>
          <ol class="space-y-2.5">
            <li v-for="(p, i) in pipeline" :key="p" class="flex gap-2.5 text-xs leading-relaxed text-muted">
              <span class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[10px] font-semibold text-accent">
                {{ i + 1 }}
              </span>
              <span>{{ p }}</span>
            </li>
          </ol>
        </div>

        <AppButton block @click="mockOnly('Export set')">
          <Download class="h-4 w-4" /> Export set...
        </AppButton>

        <p class="rounded-xl border border-border bg-surface-2/50 p-3 text-[11px] leading-relaxed text-muted">
          This tab is a live preview of the planned layout. Buttons activate in upcoming GUI sessions; the star
          triage, transparent output and export flow are already reflected in the interaction design.
        </p>
      </aside>
    </div>
  </div>
</template>
