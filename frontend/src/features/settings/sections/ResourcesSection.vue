<script setup lang="ts">
import { Cpu, MessageSquareText, ServerCog } from '@lucide/vue'
import { useEngineStore } from '@/stores/engine'
import { useSettingsStore } from '@/stores/settings'
import Section from '@/components/ui/Section.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppSwitch from '@/components/ui/AppSwitch.vue'
import StatusDot from '@/components/ui/StatusDot.vue'
import ResetButton from '@/components/ui/ResetButton.vue'

const engine = useEngineStore()
const settings = useSettingsStore()

function barWidth(known: boolean, usedGb: number, totalGb: number): string {
  if (!known || totalGb <= 0) return '0%'
  return `${Math.min(100, (usedGb / totalGb) * 100)}%`
}
</script>

<template>
  <Section title="Memory & loaded models" desc="What currently occupies VRAM and system RAM, and safe ways to free it - for a 12GB card sharing ComfyUI, the LLM and future video models.">
    <!-- status -->
    <div class="mb-4 space-y-3">
      <span class="flex items-center gap-2 text-xs text-muted">
        <StatusDot :state="engine.busy ? 'busy' : 'ok'" />
        {{ engine.busy ? 'Jobs queued or running - unloading is locked' : 'Queue idle - safe to unload' }}
      </span>
      <div>
        <div class="mb-1 flex items-center gap-2 text-xs text-muted">
          <Cpu class="h-3.5 w-3.5" />
          <span>GPU VRAM</span>
          <span class="ml-auto tabular-nums">
            {{ engine.gpu.known ? `${engine.gpu.usedGb.toFixed(1)} / ${engine.gpu.totalGb} GB` : 'unknown (ComfyUI offline)' }}
          </span>
        </div>
        <div class="h-2 overflow-hidden rounded-full bg-surface-2">
          <div class="h-full rounded-full bg-accent transition-all duration-500" :style="{ width: barWidth(engine.gpu.known, engine.gpu.usedGb, engine.gpu.totalGb) }" />
        </div>
      </div>
      <div>
        <div class="mb-1 flex items-center gap-2 text-xs text-muted">
          <span>System RAM</span>
          <span class="ml-auto tabular-nums">
            {{ engine.ram.known ? `${engine.ram.usedGb.toFixed(1)} / ${engine.ram.totalGb} GB` : 'unknown' }}
          </span>
        </div>
        <div class="h-2 overflow-hidden rounded-full bg-surface-2">
          <div class="h-full rounded-full bg-sky transition-all duration-500" :style="{ width: barWidth(engine.ram.known, engine.ram.usedGb, engine.ram.totalGb) }" />
        </div>
      </div>
    </div>

    <!-- comfyui -->
    <div class="mb-3 rounded-2xl border border-border bg-surface-2/40 p-4">
      <p class="mb-2 flex items-center gap-2 text-sm font-semibold">
        <ServerCog class="h-4 w-4 text-accent" /> ComfyUI (engine)
        <StatusDot class="ml-auto" :state="engine.comfy.connected ? 'ok' : 'off'" />
      </p>
      <p v-if="!engine.comfy.connected" class="text-xs text-muted">ComfyUI is offline - start it to free its cache.</p>
      <p v-else-if="!engine.comfyLoaded.length" class="text-xs text-muted">
        No models tracked as loaded (ComfyUI has no loaded-models list; app jobs will appear here).
      </p>
      <ul v-else class="space-y-1">
        <li v-for="m in engine.comfyLoaded" :key="m.id" class="flex items-center justify-between gap-3 text-xs text-muted">
          <span class="truncate">{{ m.name }}</span>
          <span class="shrink-0 tabular-nums">{{ m.sizeGb.toFixed(1) }} GB</span>
        </li>
      </ul>
      <div class="mt-3 flex items-center gap-2">
        <AppButton size="sm" :disabled="engine.busy || !engine.comfy.connected" @click="engine.unloadComfy()">
          Unload all &amp; free VRAM
        </AppButton>
        <span class="text-[11px] text-muted">ComfyUI has no per-model unload - one call frees its whole cache.</span>
      </div>
    </div>

    <!-- ollama -->
    <div class="mb-4 rounded-2xl border border-border bg-surface-2/40 p-4">
      <p class="mb-2 flex items-center gap-2 text-sm font-semibold">
        <MessageSquareText class="h-4 w-4 text-accent" /> Ollama (text)
        <StatusDot class="ml-auto" :state="engine.ollama.connected ? 'ok' : 'off'" />
      </p>
      <p v-if="!engine.ollama.connected" class="text-xs text-muted">Ollama is offline.</p>
      <p v-else-if="!engine.ollamaLoaded.length" class="text-xs text-muted">No models in memory.</p>
      <ul v-else class="space-y-2">
        <li v-for="m in engine.ollamaLoaded" :key="m.id" class="flex items-center justify-between gap-3">
          <div class="min-w-0 text-xs text-muted">
            <p class="truncate">{{ m.name }}</p>
            <p class="tabular-nums">{{ m.sizeGb.toFixed(1) }} GB<span v-if="m.expiresInMin !== undefined && m.expiresInMin !== null"> - auto-unloads in {{ m.expiresInMin }}m</span></p>
          </div>
          <AppButton size="sm" variant="ghost" :disabled="engine.busy" @click="engine.unloadOllama(m.id)">Unload</AppButton>
        </li>
      </ul>
      <AppButton v-if="engine.ollamaLoaded.length > 1" size="sm" class="mt-3" :disabled="engine.busy" @click="engine.unloadAllOllama()">
        Unload all
      </AppButton>
    </div>

    <!-- policy -->
    <div class="rounded-2xl border border-border bg-surface-2/40 p-4">
      <div class="flex items-start justify-between gap-4">
        <div>
          <p class="text-sm font-semibold">Auto-free VRAM before a model switch</p>
          <p class="mt-0.5 text-[11px] leading-relaxed text-muted">
            Before a job that needs a different main model, the app asks ComfyUI to free its cache first.
            Slightly slower first image, but prevents two big models fighting over 12GB.
          </p>
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <AppSwitch v-model="settings.autoFreeVram" />
          <ResetButton
            :disabled="settings.isDefault(['autoFreeVram'])"
            @reset="settings.resetField(['autoFreeVram'])"
          />
        </div>
      </div>
    </div>

    <p class="mt-4 text-[10px] leading-relaxed text-muted">
      Live calls (backend sessions): ComfyUI <code class="rounded bg-surface-2 px-1">POST /free {"unload_models":true}</code>,
      Ollama <code class="rounded bg-surface-2 px-1">POST /api/generate {"keep_alive":0}</code>. Ollama unloads only touch
      models already in memory. Both also become MCP tools so an agent can free memory before heavy runs.
    </p>
  </Section>
</template>
