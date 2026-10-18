<script setup lang="ts">
import { Sparkles } from '@lucide/vue'
import { imageModels, textModels, upscalers } from '@/lib/fixtures'
import { useSettingsStore } from '@/stores/settings'
import Section from '@/components/ui/Section.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import ResetButton from '@/components/ui/ResetButton.vue'

const settings = useSettingsStore()

const imageModelOptions = imageModels
  .filter((m) => m.installed)
  .map((m) => ({ value: m.id, label: m.name }))

const upscalerOptions = upscalers.map((u) => ({ value: u.id, label: u.name }))
const textModelOptions = textModels.map((t) => ({ value: t.id, label: `${t.name} (${t.size})` }))

const providerOptions = [
  { value: 'ollama', label: 'Ollama (local, recommended)' },
  { value: 'comfyui-textgen', label: 'ComfyUI TextGenerate (fallback)' },
  { value: 'openai', label: 'OpenAI-compatible (coming soon)', disabled: true },
]

const futureOptions = [{ value: 'none', label: 'Coming soon', disabled: true }]

type DefaultsKey = 'imageModel' | 'upscaler' | 'textProvider' | 'enhanceModel' | 'describeModel'

function reset(key: DefaultsKey) {
  settings.resetField(['defaults', key])
}
</script>

<template>
  <Section title="Image defaults" desc="What a new generation tab starts with before you change anything.">
    <div class="space-y-3">
      <div class="flex flex-wrap items-center gap-3">
        <p class="w-52 text-xs text-muted">Default text - image model</p>
        <div class="flex items-center gap-2">
          <div class="w-72"><AppSelect v-model="settings.defaults.imageModel" :options="imageModelOptions" /></div>
          <ResetButton :disabled="settings.isDefault(['defaults', 'imageModel'])" @reset="reset('imageModel')" />
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <p class="w-52 text-xs text-muted">Default upscaler</p>
        <div class="flex items-center gap-2">
          <div class="w-72"><AppSelect v-model="settings.defaults.upscaler" :options="upscalerOptions" /></div>
          <ResetButton :disabled="settings.isDefault(['defaults', 'upscaler'])" @reset="reset('upscaler')" />
        </div>
      </div>
    </div>
  </Section>

  <Section title="Text defaults" desc="Used by the Enhance and Describe stages - stored per task, overridable per generation.">
    <div class="space-y-3">
      <div class="flex flex-wrap items-center gap-3">
        <p class="w-52 text-xs text-muted">Text provider</p>
        <div class="flex items-center gap-2">
          <div class="w-72"><AppSelect v-model="settings.defaults.textProvider" :options="providerOptions" /></div>
          <ResetButton :disabled="settings.isDefault(['defaults', 'textProvider'])" @reset="reset('textProvider')" />
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <p class="w-52 text-xs text-muted">Enhance model</p>
        <div class="flex items-center gap-2">
          <div class="w-72"><AppSelect v-model="settings.defaults.enhanceModel" :options="textModelOptions" /></div>
          <ResetButton :disabled="settings.isDefault(['defaults', 'enhanceModel'])" @reset="reset('enhanceModel')" />
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <p class="w-52 text-xs text-muted">Describe model</p>
        <div class="flex items-center gap-2">
          <div class="w-72"><AppSelect v-model="settings.defaults.describeModel" :options="textModelOptions" /></div>
          <ResetButton :disabled="settings.isDefault(['defaults', 'describeModel'])" @reset="reset('describeModel')" />
        </div>
      </div>
    </div>
    <p class="mt-4 flex items-start gap-2 rounded-xl border border-border bg-surface-2/40 p-3 text-xs leading-relaxed text-muted">
      <Sparkles class="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
      Uncensored-first: recommended models must not sanitize NSFW intent. Viability of a model per task is probed
      on connect.
    </p>
  </Section>

  <Section title="Future defaults" desc="These selectors exist so the shape is visible - they activate as each engine lands.">
    <div class="space-y-3">
      <div class="flex flex-wrap items-center gap-3">
        <p class="w-52 text-xs text-muted">Default video model</p>
        <div class="w-72"><AppSelect model-value="" :options="futureOptions" disabled /></div>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <p class="w-52 text-xs text-muted">Default TTS voice</p>
        <div class="w-72"><AppSelect model-value="" :options="futureOptions" disabled /></div>
      </div>
    </div>
  </Section>
</template>
