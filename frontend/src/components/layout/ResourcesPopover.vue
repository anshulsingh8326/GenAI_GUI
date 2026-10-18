<script setup lang="ts">
import { ref } from 'vue'
import { HardDrive, MessageSquareText, ServerCog } from '@lucide/vue'
import AppPopover from '@/components/ui/AppPopover.vue'
import AppButton from '@/components/ui/AppButton.vue'
import StatusDot from '@/components/ui/StatusDot.vue'
import { useEngineStore } from '@/stores/engine'

const open = ref(false)
const engine = useEngineStore()

function barWidth(known: boolean, usedGb: number, totalGb: number): string {
  if (!known || totalGb <= 0) return '0%'
  return `${Math.min(100, (usedGb / totalGb) * 100)}%`
}
</script>

<template>
  <AppPopover v-model="open" align="right" width="21rem">
    <template #trigger>
      <button
        class="flex h-8 shrink-0 cursor-pointer items-center gap-2 rounded-full border border-border bg-surface px-3 text-xs text-muted transition-colors hover:border-accent/40"
        @click="open = !open"
      >
        <HardDrive class="h-3.5 w-3.5" />
        <span>Resources</span>
      </button>
    </template>

    <div class="space-y-3">
      <p class="flex items-center gap-2 text-[11px] text-muted">
        <StatusDot :state="engine.busy ? 'busy' : 'ok'" />
        {{ engine.busy ? 'Jobs queued or running - unloading locked' : 'Queue idle - safe to unload' }}
      </p>

      <div class="space-y-2">
        <div>
          <div class="mb-1 flex justify-between text-[11px] text-muted">
            <span>GPU VRAM</span>
            <span class="tabular-nums">
              {{ engine.gpu.known ? `${engine.gpu.usedGb.toFixed(1)} / ${engine.gpu.totalGb} GB` : 'unknown (ComfyUI offline)' }}
            </span>
          </div>
          <div class="h-2 overflow-hidden rounded-full bg-surface-2">
            <div
              class="h-full rounded-full bg-accent transition-all duration-500"
              :style="{ width: barWidth(engine.gpu.known, engine.gpu.usedGb, engine.gpu.totalGb) }"
            />
          </div>
        </div>
        <div>
          <div class="mb-1 flex justify-between text-[11px] text-muted">
            <span>System RAM</span>
            <span class="tabular-nums">
              {{ engine.ram.known ? `${engine.ram.usedGb.toFixed(1)} / ${engine.ram.totalGb} GB` : 'unknown' }}
            </span>
          </div>
          <div class="h-2 overflow-hidden rounded-full bg-surface-2">
            <div
              class="h-full rounded-full bg-sky transition-all duration-500"
              :style="{ width: barWidth(engine.ram.known, engine.ram.usedGb, engine.ram.totalGb) }"
            />
          </div>
        </div>
      </div>

      <div class="rounded-xl border border-border bg-surface-2/50 p-3">
        <div class="mb-2 flex items-center gap-2 text-xs font-semibold">
          <ServerCog class="h-3.5 w-3.5 text-accent" />
          <span>Engine - ComfyUI</span>
          <StatusDot class="ml-auto" :state="engine.comfy.connected ? 'ok' : 'off'" />
        </div>
        <p v-if="!engine.comfy.connected" class="text-[11px] text-muted">ComfyUI is offline.</p>
        <p v-else-if="!engine.comfyLoaded.length" class="text-[11px] text-muted">No models loaded.</p>
        <ul v-else class="space-y-1">
          <li v-for="m in engine.comfyLoaded" :key="m.id" class="flex items-center justify-between gap-2 text-[11px] text-muted">
            <span class="truncate">{{ m.name }}</span>
            <span class="shrink-0 tabular-nums">{{ m.sizeGb.toFixed(1) }} GB</span>
          </li>
        </ul>
        <AppButton size="sm" class="mt-2.5" :disabled="engine.busy || !engine.comfy.connected" @click="engine.unloadComfy()">
          Unload all &amp; free VRAM
        </AppButton>
      </div>

      <div class="rounded-xl border border-border bg-surface-2/50 p-3">
        <div class="mb-2 flex items-center gap-2 text-xs font-semibold">
          <MessageSquareText class="h-3.5 w-3.5 text-accent" />
          <span>Text - Ollama</span>
          <StatusDot class="ml-auto" :state="engine.ollama.connected ? 'ok' : 'off'" />
        </div>
        <p v-if="!engine.ollama.connected" class="text-[11px] text-muted">Ollama is offline.</p>
        <p v-else-if="!engine.ollamaLoaded.length" class="text-[11px] text-muted">No models in memory.</p>
        <ul v-else class="space-y-1.5">
          <li v-for="m in engine.ollamaLoaded" :key="m.id" class="flex items-center justify-between gap-2">
            <div class="min-w-0 text-[11px] text-muted">
              <p class="truncate">{{ m.name }}</p>
              <p class="tabular-nums">
                {{ m.sizeGb.toFixed(1) }} GB
                <span v-if="m.expiresInMin !== undefined && m.expiresInMin !== null">- unloads in {{ m.expiresInMin }}m</span>
              </p>
            </div>
            <AppButton size="sm" variant="ghost" :disabled="engine.busy" @click="engine.unloadOllama(m.id)">Unload</AppButton>
          </li>
        </ul>
        <AppButton
          v-if="engine.ollamaLoaded.length > 1"
          size="sm"
          class="mt-2.5"
          :disabled="engine.busy"
          @click="engine.unloadAllOllama()"
        >
          Unload all
        </AppButton>
      </div>

      <p class="text-[10px] leading-relaxed text-muted">
        ComfyUI frees its whole cache with one call (it has no per-model unload API or loaded-models list).
        Ollama unloads one model at a time - only models already in memory are touched.
      </p>
    </div>
  </AppPopover>
</template>
