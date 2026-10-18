<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Boxes, Moon, Settings, Sun } from '@lucide/vue'
import StatusDot from '@/components/ui/StatusDot.vue'
import ResourcesPopover from './ResourcesPopover.vue'
import { useUiStore } from '@/stores/ui'
import { useEngineStore } from '@/stores/engine'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const engine = useEngineStore()

const pageTitle = computed(() => (route.meta.title as string) ?? 'GenAI GUI')

function toggleTheme() {
  ui.setTheme(ui.theme === 'pastel-dark' ? 'pastel-light' : 'pastel-dark')
}
</script>

<template>
  <header class="relative z-30 flex h-14 shrink-0 items-center gap-2 whitespace-nowrap border-b border-border bg-surface/70 px-4 backdrop-blur">
    <h1 class="max-w-64 truncate text-sm font-semibold">{{ pageTitle }}</h1>
    <span class="hidden rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted lg:inline">mock data</span>

    <div class="flex-1" />

    <!-- connections -->
    <button
      class="flex h-8 shrink-0 cursor-pointer items-center gap-2 rounded-full border border-border bg-surface px-3 text-xs text-muted transition-colors hover:border-accent/40"
      title="Open connection settings"
      @click="router.push('/settings?tab=connections')"
    >
      <StatusDot :state="engine.comfy.connected ? 'ok' : 'off'" />
      <span class="hidden sm:inline">ComfyUI</span>
      <span class="hidden lg:inline" :class="engine.comfy.connected ? 'text-success' : 'text-danger'">
        {{ engine.comfy.connected ? 'Connected' : 'Offline' }}
      </span>
    </button>

    <button
      class="flex h-8 shrink-0 cursor-pointer items-center gap-2 rounded-full border border-border bg-surface px-3 text-xs text-muted transition-colors hover:border-accent/40"
      title="Open connection settings"
      @click="router.push('/settings?tab=connections')"
    >
      <StatusDot :state="engine.ollama.connected ? 'ok' : 'off'" />
      <span class="hidden sm:inline">Ollama</span>
      <span class="hidden lg:inline" :class="engine.ollama.connected ? 'text-success' : 'text-danger'">
        {{ engine.ollama.connected ? 'Connected' : 'Offline' }}
      </span>
    </button>

    <!-- queue -->
    <div class="hidden h-8 shrink-0 items-center gap-2 rounded-full border border-border bg-surface px-3 text-xs text-muted lg:flex">
      <Boxes class="h-3.5 w-3.5" />
      <span>{{ engine.queueLabel }}</span>
    </div>

    <ResourcesPopover />

    <button
      class="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-full border border-border bg-surface text-muted transition-colors hover:text-text"
      :title="ui.theme === 'pastel-dark' ? 'Switch to pastel light' : 'Switch to pastel dark'"
      @click="toggleTheme"
    >
      <Sun v-if="ui.theme === 'pastel-dark'" class="h-4 w-4" />
      <Moon v-else class="h-4 w-4" />
    </button>

    <button
      class="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-full border border-border bg-surface text-muted transition-colors hover:text-text"
      title="Settings"
      @click="router.push('/settings')"
    >
      <Settings class="h-4 w-4" />
    </button>
  </header>
</template>
