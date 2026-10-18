<script setup lang="ts">
import { RefreshCw } from '@lucide/vue'
import { useSettingsStore } from '@/stores/settings'
import Section from '@/components/ui/Section.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppSelect from '@/components/ui/AppSelect.vue'
import AppTextarea from '@/components/ui/AppTextarea.vue'
import ResetButton from '@/components/ui/ResetButton.vue'

const settings = useSettingsStore()

const providerOptions = [
  { value: 'ollama', label: 'Ollama (local, recommended)' },
  { value: 'comfyui-textgen', label: 'ComfyUI TextGenerate (fallback)' },
  { value: 'openai', label: 'OpenAI-compatible (coming soon)', disabled: true },
]

const promptFields: { key: 'enhance' | 'describeCharacter' | 'describeFull'; label: string; desc: string }[] = [
  { key: 'enhance', label: 'Prompt enhancer (per-generation, optional)', desc: 'Rewrites your idea into a model-friendly prompt. The result is always shown as a diff before running.' },
  { key: 'describeCharacter', label: 'Describe - character only', desc: 'Used when an image feeds a character profile or identity description.' },
  { key: 'describeFull', label: 'Describe - full image', desc: 'Used when you want the whole scene described (style reference, captions).' },
]
</script>

<template>
  <Section title="Provider per task" desc="Enhance and Describe can use different providers and models - overridable per generation.">
    <div class="flex flex-wrap items-center gap-3">
      <p class="w-52 text-xs text-muted">Default provider (both tasks)</p>
      <div class="flex items-center gap-2">
        <div class="w-72"><AppSelect v-model="settings.defaults.textProvider" :options="providerOptions" /></div>
        <ResetButton
          :disabled="settings.isDefault(['defaults', 'textProvider'])"
          @reset="settings.resetField(['defaults', 'textProvider'])"
        />
      </div>
    </div>
    <p class="mt-3 text-[11px] leading-relaxed text-muted">
      Enhance must never water down NSFW or adult creative direction - the shipped defaults are written for
      uncensored models and are fully editable below.
    </p>
  </Section>

  <Section
    v-for="f in promptFields"
    :key="f.key"
    :title="f.label"
    :desc="f.desc"
  >
    <AppTextarea v-model="settings.prompts[f.key]" :rows="4" />
    <div class="mt-2 flex justify-end">
      <AppButton
        size="sm"
        variant="ghost"
        :disabled="settings.isDefault(['prompts', f.key])"
        @click="settings.resetPrompt(f.key)"
      >
        <RefreshCw class="h-3.5 w-3.5" /> Reset to default
      </AppButton>
    </div>
  </Section>
</template>
