<script setup lang="ts">
import { ref } from 'vue'
import { Bot, Copy, BadgeCheck, RefreshCw } from '@lucide/vue'
import { useSettingsStore } from '@/stores/settings'
import { useUiStore } from '@/stores/ui'
import Section from '@/components/ui/Section.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppSwitch from '@/components/ui/AppSwitch.vue'
import Badge from '@/components/ui/Badge.vue'
import ResetButton from '@/components/ui/ResetButton.vue'

const settings = useSettingsStore()
const ui = useUiStore()

const tools = ref([
  { name: 'app_info / list_capabilities', on: true },
  { name: 'generate_image', on: true },
  { name: 'edit_image', on: true },
  { name: 'describe_image / enhance_prompt', on: true },
  { name: 'upscale_image / face_swap', on: true },
  { name: 'search_library / get_asset', on: true },
  { name: 'job_status / job_result / cancel_job', on: true },
  { name: 'unload_models (free VRAM)', on: true },
])

function copyToken() {
  navigator.clipboard?.writeText(settings.agentToken)
  ui.toast('Token copied', 'success')
}

function regenerate() {
  settings.agentToken = 'genai_live_' + Math.random().toString(16).slice(2, 18)
  ui.toast('New token generated', 'success')
}
</script>

<template>
  <Section
    title="Agent access (MCP / API)"
    desc="Everything the GUI can do is also a REST endpoint and an MCP tool - the same features, one interface for both clients."
  >
    <div class="mb-4 flex items-center justify-between gap-4">
      <div>
        <p class="text-sm font-medium">Enable MCP server</p>
        <p class="text-[11px] text-muted">Ships inside the backend; stdio for local agents, HTTP for remote.</p>
      </div>
      <div class="flex items-center gap-2">
        <AppSwitch v-model="settings.agentEnabled" />
        <ResetButton
          :disabled="settings.isDefault(['agentEnabled'])"
          @reset="settings.resetField(['agentEnabled'])"
        />
      </div>
    </div>

    <div class="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
      <div>
        <p class="mb-1 text-[11px] uppercase tracking-wider text-muted">API token</p>
        <div class="flex items-center gap-2">
          <AppInput v-model="settings.agentToken" disabled />
          <AppButton size="md" title="Copy token" @click="copyToken"><Copy class="h-3.5 w-3.5" /></AppButton>
          <AppButton size="md" title="Generate a new token" @click="regenerate"><RefreshCw class="h-3.5 w-3.5" /></AppButton>
          <ResetButton
            :disabled="settings.isDefault(['agentToken'])"
            @reset="settings.resetField(['agentToken'])"
          />
        </div>
      </div>
      <div>
        <p class="mb-1 text-[11px] uppercase tracking-wider text-muted">Allowed folder (agent inbox)</p>
        <div class="flex items-center gap-2">
          <AppInput v-model="settings.folders.agentInbox" />
          <ResetButton
            :disabled="settings.isDefault(['folders', 'agentInbox'])"
            @reset="settings.resetField(['folders', 'agentInbox'])"
          />
        </div>
      </div>
    </div>

    <p class="mb-2 text-[11px] uppercase tracking-wider text-muted">Exposed tools</p>
    <div class="space-y-1.5">
      <div v-for="t in tools" :key="t.name" class="flex items-center justify-between rounded-xl border border-border bg-surface-2/40 px-3 py-2">
        <span class="text-xs text-muted">{{ t.name }}</span>
        <AppSwitch v-model="t.on" />
      </div>
    </div>

    <div class="mt-4 flex items-start gap-2 rounded-xl border border-border bg-surface-2/40 p-3">
      <Bot class="mt-0.5 h-4 w-4 shrink-0 text-accent" />
      <p class="text-xs leading-relaxed text-muted">
        Security: localhost-only by default, optional token, file-path allowlist so an agent can never read
        arbitrary disk paths through the app.
        <span class="mx-1"><Badge tone="accent">example</Badge></span>
        <span class="text-text">"take D:\photos\me.png and add a red hat"</span> - the agent calls the app,
        the app does the work and returns the output path.
      </p>
    </div>
    <p class="mt-3 flex items-center gap-1.5 text-[10px] text-muted">
      <BadgeCheck class="h-3 w-3 text-success" />
      Settings are stored in settings.json via the backend; the MCP server itself lands in a later group.
    </p>
  </Section>
</template>
