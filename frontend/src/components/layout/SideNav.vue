<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
import { ChevronDown, Film, Image, Library, Mic, Settings, Sparkles } from '@lucide/vue'
import { navGroups } from '@/lib/nav'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const route = useRoute()

const groupIcons: Record<string, any> = {
  image: Image,
  video: Film,
  audio: Mic,
  library: Library,
  system: Settings,
}
</script>

<template>
  <aside class="flex w-60 shrink-0 flex-col border-r border-border bg-surface/60">
    <!-- brand -->
    <div class="flex items-center gap-2.5 px-4 pb-4 pt-5">
      <div class="flex h-8 w-8 items-center justify-center rounded-xl bg-accent text-accent-contrast">
        <Sparkles class="h-4 w-4" />
      </div>
      <div class="min-w-0">
        <p class="truncate text-sm font-semibold leading-tight">GenAI GUI</p>
        <p class="text-[10px] uppercase tracking-widest text-muted">local studio</p>
      </div>
    </div>

    <!-- groups -->
    <nav class="flex-1 space-y-1 overflow-y-auto px-3 pb-4">
      <div v-for="g in navGroups" :key="g.id">
        <button
          class="flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted transition-colors hover:text-text"
          @click="ui.toggleGroup(g.id)"
        >
          <component :is="groupIcons[g.id]" class="h-3.5 w-3.5" />
          <span class="flex-1 text-left">{{ g.label }}</span>
          <ChevronDown
            class="h-3.5 w-3.5 transition-transform"
            :class="ui.collapsedGroups[g.id] ? '-rotate-90' : ''"
          />
        </button>

        <div v-show="!ui.collapsedGroups[g.id]" class="mt-0.5 space-y-0.5 pb-1">
          <RouterLink
            v-for="item in g.items"
            :key="item.id"
            :to="item.to"
            class="group flex items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] transition-colors"
            :class="
              route.path === item.to
                ? 'bg-accent-soft font-medium text-accent'
                : 'text-muted hover:bg-surface-2 hover:text-text'
            "
          >
            <span
              class="h-1.5 w-1.5 rounded-full transition-colors"
              :class="route.path === item.to ? 'bg-accent' : 'bg-border group-hover:bg-muted'"
            />
            <span class="flex-1 truncate">{{ item.label }}</span>
            <span v-if="item.soon" class="rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted">soon</span>
          </RouterLink>
        </div>
      </div>
    </nav>

    <!-- footer note -->
    <div class="border-t border-border px-4 py-3">
      <p class="text-[10px] leading-relaxed text-muted">
        Settings, folders and connections persist to the backend.<br />
        Generation modules are still mock data.
      </p>
    </div>
  </aside>
</template>
