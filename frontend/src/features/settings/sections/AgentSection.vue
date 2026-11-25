<script setup lang="ts">
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

// Keep in sync with backend/app/mcp/server.py (tools are added per build step).
const tools = ['app_info', 'list_models', 'job_status', 'list_jobs', 'library_list', 'import_asset']

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

    <p class="mb-2 text-[11px] uppercase tracking-wider text-muted">Tools (v0)</p>
    <div class="space-y-1.5">
      <div v-for="t in tools" :key="t" class="flex items-center justify-between rounded-xl border border-border bg-surface-2/40 px-3 py-2">
        <span class="text-xs text-muted">{{ t }}</span>
        <Badge tone="ok">live</Badge>
      </div>
    </div>

    <div class="mt-4 flex items-start gap-2 rounded-xl border border-border bg-surface-2/40 p-3">
      <Bot class="mt-0.5 h-4 w-4 shrink-0 text-accent" />
      <p class="text-xs leading-relaxed text-muted">
        Security: stdio is local-only. The API token gates the future HTTP transport, not stdio
        today, and file-path allowlists are not enforced yet - enable agent access only on a
        machine you trust.
        <span class="mx-1"><Badge tone="accent">example</Badge></span>
        <span class="text-text">"take D:\photos\me.png and add a red hat"</span> - once edit tools
        ship, the agent will call the app, the app will do the work and return the output path.
      </p>
    </div>
    <p class="mt-3 flex items-center gap-1.5 text-[10px] text-muted">
      <BadgeCheck class="h-3 w-3 text-success" />
      Settings are stored in settings.json via the backend. The stdio MCP server is available now -
      see README -> Agents (MCP) for the client config.
    </p>
  </Section>
</template>
