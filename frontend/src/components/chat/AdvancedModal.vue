<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Dices, RefreshCw } from '@lucide/vue'
import type { AdvancedParams } from '@/types'
import { imageModels } from '@/lib/fixtures'
import { useChatStore } from '@/stores/chat'
import AppModal from '@/components/ui/AppModal.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppSlider from '@/components/ui/AppSlider.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppSwitch from '@/components/ui/AppSwitch.vue'

const props = defineProps<{
  tabId: string
}>()

const open = defineModel<boolean>({ required: true })

const chat = useChatStore()
const composer = computed(() => chat.thread(props.tabId).composer)
const model = computed(() => imageModels.find((m) => m.id === composer.value.modelId))

const draft = ref<AdvancedParams>(JSON.parse(JSON.stringify(composer.value.advanced)))
const draftEnhance = ref(false)

watch(open, (isOpen) => {
  if (isOpen) {
    draft.value = JSON.parse(JSON.stringify(composer.value.advanced))
    draftEnhance.value = composer.value.enhance
  }
})

const samplers = ['euler', 'euler_ancestral', 'dpmpp_2m', 'dpmpp_sde', 'heun'].map((s) => ({ value: s, label: s }))
const schedulers = ['simple', 'normal', 'karras', 'sgm_uniform'].map((s) => ({ value: s, label: s }))
const recipes = [
  { value: 'krea2-freeze', label: 'Krea2 Freeze v8 (full pipeline)' },
  { value: 'krea2-t2i', label: 'Krea2 minimal T2I' },
  { value: 'qwen-t2i', label: 'Qwen Turbo T2I' },
]

function rollSeed() {
  draft.value.seed = Math.floor(Math.random() * 1e12)
}

function resetDefaults() {
  const d = model.value?.defaults
  if (!d) return
  draft.value.steps = d.steps
  draft.value.cfg = d.cfg
  draft.value.sampler = d.sampler
  draft.value.scheduler = d.scheduler
  draft.value.denoise = d.denoise
  draft.value.refine = { on: true, steps: 6, cfg: 2.0, denoise: 0.45, scale: 1536 }
}

function apply() {
  composer.value.advanced = JSON.parse(JSON.stringify(draft.value))
  composer.value.enhance = draftEnhance.value
  open.value = false
}
</script>

<template>
  <AppModal
    v-model="open"
    title="Advanced parameters"
    :subtitle="`Defaults come from the selected model manifest${model ? ' - ' + model.name : ''}`"
    width="620px"
  >
    <div class="space-y-5">
      <!-- recipe -->
      <div>
        <p class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">Recipe</p>
        <AppSelect v-model="draft.recipe" :options="recipes" />
      </div>

      <!-- stages -->
      <div class="rounded-2xl border border-border bg-surface-2/40 p-4">
        <p class="mb-3 text-[11px] font-semibold uppercase tracking-wider text-muted">Stages</p>
        <div class="space-y-3">
          <div class="flex items-center justify-between gap-4">
            <div>
              <p class="text-sm font-medium">Enhance prompt</p>
              <p class="text-[11px] text-muted">Rewrite the prompt with the text provider before running (visible as a stage).</p>
            </div>
            <AppSwitch v-model="draftEnhance" />
          </div>
          <div class="flex items-center justify-between gap-4">
            <div>
              <p class="text-sm font-medium">Refine / upscale pass</p>
              <p class="text-[11px] text-muted">Second sampling pass on an upscaled latent - stage 2 of Freeze v8.</p>
            </div>
            <AppSwitch v-model="draft.refine.on" />
          </div>
        </div>
      </div>

      <!-- seed -->
      <div>
        <p class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">Seed</p>
        <div class="flex items-center gap-2">
          <input
            v-model.number="draft.seed"
            type="number"
            class="h-10 flex-1 rounded-xl border border-border bg-surface px-3 text-sm tabular-nums outline-none focus:border-accent/60"
          />
          <AppButton size="md" @click="rollSeed">
            <Dices class="h-4 w-4" />
            Random
          </AppButton>
        </div>
        <div class="mt-2">
          <AppSwitch v-model="draft.lockSeed" label="Keep this seed for every run (reproducible results)" />
        </div>
      </div>

      <!-- sampling -->
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <p class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">Steps</p>
          <AppSlider v-model="draft.steps" :min="1" :max="40" :step="1" />
        </div>
        <div>
          <p class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">CFG scale</p>
          <AppSlider v-model="draft.cfg" :min="0" :max="10" :step="0.1" />
        </div>
        <div>
          <p class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">Sampler</p>
          <AppSelect v-model="draft.sampler" :options="samplers" />
        </div>
        <div>
          <p class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">Scheduler</p>
          <AppSelect v-model="draft.scheduler" :options="schedulers" />
        </div>
        <div>
          <p class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">Denoise</p>
          <AppSlider v-model="draft.denoise" :min="0" :max="1" :step="0.05" />
        </div>
      </div>

      <!-- refine pass parameters -->
      <div class="rounded-2xl border border-border bg-surface-2/40 p-4">
        <p class="mb-3 text-[11px] font-semibold uppercase tracking-wider text-muted">Refine pass parameters</p>
        <div v-if="draft.refine.on" class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <p class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">Steps</p>
            <AppSlider v-model="draft.refine.steps" :min="1" :max="20" :step="1" />
          </div>
          <div>
            <p class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">CFG</p>
            <AppSlider v-model="draft.refine.cfg" :min="0" :max="10" :step="0.1" />
          </div>
          <div>
            <p class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">Denoise</p>
            <AppSlider v-model="draft.refine.denoise" :min="0" :max="1" :step="0.05" />
          </div>
          <div>
            <p class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">Scale (long side px)</p>
            <AppSlider v-model="draft.refine.scale" :min="1024" :max="2048" :step="128" />
          </div>
        </div>
        <p v-else class="text-xs text-muted">Refine pass is off - turn it on under Stages above.</p>
      </div>

      <p class="text-[10px] leading-relaxed text-muted">
        These exact values are snapshotted into every job - re-run or clone a job and you get the same result
        (seed locking) or controlled variations.
      </p>
    </div>

    <template #footer>
      <AppButton variant="ghost" @click="resetDefaults">
        <RefreshCw class="h-3.5 w-3.5" /> Model defaults
      </AppButton>
      <AppButton variant="primary" @click="apply">Apply</AppButton>
    </template>
  </AppModal>
</template>
