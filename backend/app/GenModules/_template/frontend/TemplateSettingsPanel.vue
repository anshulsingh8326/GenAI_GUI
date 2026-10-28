<script setup lang="ts">
import { computed } from 'vue'
import { X } from '@lucide/vue'
import { timeAgo } from '@/lib/format'
import ResetButton from '@/components/ui/ResetButton.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppSlider from '@/components/ui/AppSlider.vue'
import AppSwitch from '@/components/ui/AppSwitch.vue'
import { useTemplateStore } from './store'
import type { TemplateAccent } from './types'

const emit = defineEmits<{ (e: 'close'): void }>()
const store = useTemplateStore()

const accentValue = computed({
  get: () => store.form.accent,
  set: (value: string) => {
    store.form.accent = value as TemplateAccent
  },
})
const widthValue = computed({
  get: () => String(store.form.width),
  set: (value: string) => {
    const next = Number(value)
    if (Number.isFinite(next)) store.form.width = next
  },
})
const heightValue = computed({
  get: () => String(store.form.height),
  set: (value: string) => {
    const next = Number(value)
    if (Number.isFinite(next)) store.form.height = next
  },
})
const seedValue = computed({
  get: () => String(store.form.seed),
  set: (value: string) => {
    const next = Number(value)
    if (Number.isFinite(next)) store.form.seed = next & 0xffff_ffff
  },
})
const accentOptions = computed(() =>
  store.accentOptions.map((item) => ({ value: item.id, label: item.label })),
)
const lastSaved = computed(() =>
  store.lastSavedAt ? `Saved ${timeAgo(store.lastSavedAt)}` : 'Not saved yet',
)

function randomizeSeed(): void {
  store.form.seed = Math.floor(Math.random() * 0x1_0000_0000)
  store.persistNow()
}

function reset(panel: 'output' | 'all'): void {
  if (panel === 'output') {
    store.resetPanel('output')
    return
  }
  if (
    window.confirm(
      'Reset every Template setting? This also clears the composer prompt and locks nothing.',
    )
  ) {
    store.resetPanel('all')
  }
}
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-surface">
    <header class="flex shrink-0 items-start justify-between gap-3 border-b border-border px-4 py-3">
      <div class="min-w-0">
        <p class="text-sm font-semibold">Template settings</p>
        <p class="mt-0.5 text-[11px] leading-snug text-muted">
          Autosaved in this browser. Every panel has its own reset.
        </p>
      </div>
      <button
        type="button"
        class="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-text"
        title="Close settings"
        aria-label="Close settings"
        @click="emit('close')"
      >
        <X class="h-4 w-4" />
      </button>
    </header>

    <div v-if="!store.catalog" class="flex flex-1 items-center justify-center p-6 text-center text-xs text-muted">
      Loading the Template controls...
    </div>

    <div v-else class="min-h-0 flex-1 space-y-3 overflow-y-auto bg-bg/25 p-3">
      <!-- Output -->
      <details open class="group overflow-hidden rounded-xl border border-l-2 border-border border-l-sky/60 bg-surface shadow-sm open:ring-1 open:ring-accent/20">
        <summary class="flex cursor-pointer list-none items-center gap-2 border-b border-border/80 bg-surface-2/75 px-3.5 py-2.5 transition-colors hover:bg-surface-2 [&::-webkit-details-marker]:hidden">
          <span class="h-2 w-2 rounded-full bg-sky" />
          <span class="text-xs font-semibold">Output</span>
          <span class="truncate text-[10px] text-muted">{{ store.form.width }} x {{ store.form.height }} · {{ store.selectedAccent }}</span>
          <ResetButton
            class="ml-auto h-8 w-8"
            label="Reset output settings"
            @click.prevent.stop="reset('output')"
          />
        </summary>
        <div class="space-y-3 bg-surface px-3.5 py-3">
          <label class="block">
            <span class="mb-1 block text-[11px] font-medium text-muted">Accent</span>
            <AppSelect v-model="accentValue" :options="accentOptions" />
          </label>

          <div class="grid grid-cols-2 gap-2">
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-muted">Width</span>
              <AppSelect v-model="widthValue" :options="store.sizeOptions" />
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-muted">Height</span>
              <AppSelect v-model="heightValue" :options="store.sizeOptions" />
            </label>
          </div>

          <AppSlider
            v-model="store.form.batch"
            :min="store.catalog?.limits.minBatch ?? 1"
            :max="store.catalog?.limits.maxBatch ?? 4"
            :step="store.catalog?.limits.batchStep ?? 1"
            label="Batch"
          />

          <div class="flex items-end gap-2">
            <label class="min-w-0 flex-1">
              <span class="mb-1 block text-[11px] font-medium text-muted">Seed</span>
              <AppInput v-model="seedValue" type="number" />
            </label>
            <AppButton variant="soft" size="sm" class="h-10" @click="randomizeSeed">Randomize</AppButton>
          </div>

          <AppSwitch
            v-model="store.form.lockSeed"
            label="Lock the seed between runs"
            @update:model-value="store.persistNow()"
          />
        </div>
      </details>

      <!-- Renderer -->
      <details open class="group overflow-hidden rounded-xl border border-l-2 border-border border-l-mint/60 bg-surface shadow-sm open:ring-1 open:ring-accent/20">
        <summary class="flex cursor-pointer list-none items-center gap-2 border-b border-border/80 bg-surface-2/75 px-3.5 py-2.5 transition-colors hover:bg-surface-2 [&::-webkit-details-marker]:hidden">
          <span class="h-2 w-2 rounded-full bg-mint" />
          <span class="text-xs font-semibold">Renderer</span>
          <span class="truncate text-[10px] text-muted">local placeholder</span>
        </summary>
        <div class="space-y-2.5 bg-surface px-3.5 py-3 text-[11px] leading-relaxed text-muted">
          <p>
            This starter renders a deterministic SVG locally so the job, library, history and
            deletion contract works without a model or GPU.
          </p>
          <p>
            To make it a real module, replace <code class="rounded bg-surface-2 px-1 py-0.5 text-text">_render_svg</code>
            in <code class="rounded bg-surface-2 px-1 py-0.5 text-text">backend/service.py</code> with your
            engine pipeline. Keep the job creation, stage tracker and library collection code.
          </p>
          <p>
            Prompt limit: <span class="text-text">{{ store.promptLimit }}</span> characters.
            Recipe: <span class="text-text">template-card-v1</span>.
          </p>
        </div>
      </details>

      <p v-if="store.storageError" class="rounded-xl border border-warn/30 bg-warn/10 p-2.5 text-[11px] text-warn">
        {{ store.storageError }}
      </p>
    </div>

    <footer class="shrink-0 space-y-2 border-t border-border bg-surface p-3">
      <p class="text-[10px] text-muted">{{ lastSaved }}</p>
      <AppButton variant="danger" size="sm" block @click="reset('all')">Reset all settings</AppButton>
    </footer>
  </div>
</template>
