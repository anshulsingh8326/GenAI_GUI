<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RefreshCw } from '@lucide/vue'
import { formatTime } from '@/lib/format'
import { useJobsStore } from '@/stores/jobs'
import { useUiStore } from '@/stores/ui'
import AppButton from '@/components/ui/AppButton.vue'
import StatusDot from '@/components/ui/StatusDot.vue'
import StageTimeline from '@/components/chat/StageTimeline.vue'

const jobs = useJobsStore()
const ui = useUiStore()

const selectedId = ref<string>('')
const selected = computed(() => jobs.byId(selectedId.value))
const refreshing = ref(false)

async function refresh(): Promise<void> {
  if (refreshing.value) return
  refreshing.value = true
  await jobs.syncFromBackend()
  refreshing.value = false
}

// Auto-select the newest job once history loads from the backend.
watch(
  () => jobs.jobs[0]?.id,
  (first) => {
    if (!selected.value && first) selectedId.value = first
  },
  { immediate: true },
)

onMounted(() => {
  void refresh()
})

function snapshot(): string {
  if (!selected.value) return ''
  return JSON.stringify(
    {
      job: selected.value.id,
      recipe: selected.value.recipe,
      model: selected.value.modelId,
      prompt: selected.value.prompt,
      enhanced: selected.value.enhancedPrompt ?? null,
      seed: selected.value.seed,
      params: selected.value.params,
    },
    null,
    2,
  )
}

function copySnapshot() {
  navigator.clipboard?.writeText(snapshot())
  ui.toast('Job snapshot copied', 'success')
}
</script>

<template>
  <div class="mx-auto max-w-7xl px-6 py-6">
    <header class="mb-5 flex flex-wrap items-start gap-3">
      <div>
        <h1 class="text-lg font-semibold">Jobs</h1>
        <p class="mt-1 text-sm text-muted">
          Every generation is an ordered pipeline run. Inspect stages, snapshot params, re-run from any point.
        </p>
      </div>
      <div class="ml-auto">
        <AppButton size="sm" variant="ghost" :disabled="refreshing" @click="refresh">
          <RefreshCw class="h-3.5 w-3.5" :class="refreshing ? 'animate-spin' : ''" />
          {{ refreshing ? 'Refreshing...' : 'Refresh' }}
        </AppButton>
      </div>
    </header>

    <div class="flex flex-col gap-5 lg:flex-row">
      <!-- list -->
      <div class="w-full shrink-0 space-y-2 lg:w-96">
        <button
          v-for="j in jobs.jobs"
          :key="j.id"
          class="w-full cursor-pointer rounded-2xl border p-3 text-left transition-colors"
          :class="selectedId === j.id ? 'border-accent/50 bg-accent-soft' : 'border-border bg-surface hover:border-accent/30'"
          @click="selectedId = j.id"
        >
          <div class="flex items-center gap-2 text-xs">
            <StatusDot :state="j.status === 'done' ? 'ok' : j.status === 'error' ? 'off' : 'busy'" />
            <span class="font-semibold">{{ j.id }}</span>
            <span class="text-muted">{{ j.modelName }}</span>
            <span class="ml-auto text-muted">{{ formatTime(j.createdAt) }}</span>
          </div>
          <p class="mt-1.5 line-clamp-1 text-xs text-muted">{{ j.prompt }}</p>
        </button>
      </div>

      <!-- detail -->
      <div v-if="selected" class="min-w-0 flex-1">
        <div class="space-y-4 rounded-2xl border border-border bg-surface p-5">
          <header class="flex flex-wrap items-center gap-2">
            <h2 class="text-sm font-semibold">Job {{ selected.id }}</h2>
            <span class="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted">{{ selected.recipe }}</span>
            <span class="text-xs text-muted">{{ selected.modelName }}</span>
            <div class="flex-1" />
            <AppButton size="sm" variant="ghost" @click="copySnapshot">Copy snapshot</AppButton>
            <AppButton size="sm" @click="ui.toast('Re-run from stage arrives with the pipeline engine (mock)')">
              <RefreshCw class="h-3.5 w-3.5" /> Re-run from stage
            </AppButton>
          </header>

          <div>
            <p class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">Stages</p>
            <div class="rounded-xl border border-border bg-surface-2/30 p-3">
              <StageTimeline :stages="selected.stages" />
            </div>
          </div>

          <div>
            <p class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">Params snapshot</p>
            <pre class="max-h-96 overflow-auto rounded-xl border border-border bg-surface-2/30 p-3 text-[11px] leading-relaxed text-muted">{{ snapshot() }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
