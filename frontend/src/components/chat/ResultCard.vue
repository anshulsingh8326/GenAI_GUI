<script setup lang="ts">
import { computed, ref } from 'vue'
import { Copy, Download, Lock, RefreshCw, Star } from '@lucide/vue'
import type { Asset } from '@/types'
import { downloadAsset } from '@/lib/download'
import { useChatStore } from '@/stores/chat'
import { useJobsStore } from '@/stores/jobs'
import { useLibraryStore } from '@/stores/library'
import { useUiStore } from '@/stores/ui'
import StageTimeline from './StageTimeline.vue'
import Chip from '@/components/ui/Chip.vue'

const props = defineProps<{
  jobId: string
}>()

const jobs = useJobsStore()
const library = useLibraryStore()
const chat = useChatStore()
const ui = useUiStore()

const job = computed(() => jobs.byId(props.jobId))
const assets = computed<Asset[]>(() => {
  if (!job.value) return []
  return job.value.resultIds
    .map((id) => library.byId(id))
    .filter((a): a is Asset => Boolean(a))
})
const selectedId = ref<string | null>(null)
const selected = computed(() => assets.value.find((a) => a.id === selectedId.value) ?? assets.value[0])

function useSeed(asset: Asset) {
  if (!job.value) return
  const composer = chat.thread(job.value.tab).composer
  composer.advanced.seed = asset.seed
  composer.advanced.lockSeed = true
  ui.toast(`Seed ${asset.seed} locked for the next run`)
}

function copyParams() {
  if (!job.value) return
  const snapshot = {
    prompt: job.value.prompt,
    enhanced: job.value.enhancedPrompt ?? null,
    seed: job.value.seed,
    params: job.value.params,
  }
  navigator.clipboard?.writeText(JSON.stringify(snapshot, null, 2))
  ui.toast('Params copied to clipboard', 'success')
}

function mockOnly(label: string) {
  ui.toast(`${label} arrives with the engine session (mock for now)`)
}
</script>

<template>
  <div v-if="job" class="rounded-2xl border border-border bg-surface p-4">
    <!-- header -->
    <header class="mb-3 flex flex-wrap items-center gap-2 text-xs text-muted">
      <span class="font-semibold text-text">Job {{ job.id }}</span>
      <span>-</span>
      <span>{{ job.modelName }}</span>
      <span v-if="job.status === 'done'" class="ml-auto tabular-nums">
        {{ assets.length }} image{{ assets.length > 1 ? 's' : '' }} - seed {{ job.seed }}
      </span>
      <span v-else class="ml-auto flex items-center gap-1.5 tabular-nums">
        <span class="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
        running - {{ job.progress }}%
      </span>
    </header>

    <!-- prompt + enhanced flag -->
    <p class="mb-3 line-clamp-2 text-xs text-muted">
      {{ job.prompt }}
      <span v-if="job.enhancedPrompt" class="ml-1 rounded-md bg-accent-soft px-1.5 py-0.5 text-[10px] text-accent" title="Prompt was rewritten by the text provider">
        enhanced
      </span>
    </p>

    <!-- running state: stage timeline -->
    <div v-if="job.status !== 'done'">
      <div class="mb-3 h-1.5 overflow-hidden rounded-full bg-surface-2">
        <div class="h-full rounded-full bg-accent transition-all duration-300" :style="{ width: job.progress + '%' }" />
      </div>
      <StageTimeline :stages="job.stages" />
    </div>

    <!-- done state: images + actions -->
    <template v-else>
      <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <button
          v-for="a in assets"
          :key="a.id"
          class="group relative cursor-pointer overflow-hidden rounded-xl border transition-all"
          :class="selected?.id === a.id ? 'border-accent ring-2 ring-accent/30' : 'border-border hover:border-accent/40'"
          @click="selectedId = a.id"
        >
          <img :src="a.thumbUrl ?? a.url" class="aspect-square w-full object-cover" alt="" />
          <span v-if="a.favorite" class="absolute left-1.5 top-1.5 rounded-md bg-black/45 p-1">
            <Star class="h-3 w-3 fill-amber-300 text-amber-300" />
          </span>
        </button>
      </div>

      <div class="mt-3 flex flex-wrap items-center gap-1.5">
        <Chip :active="Boolean(selected?.favorite)" @click="selected && library.toggleFavorite(selected.id)">
          <Star class="h-3 w-3" /> Favorite
        </Chip>
        <Chip @click="selected && downloadAsset(selected)">
          <Download class="h-3 w-3" /> Download
        </Chip>
        <Chip @click="selected && useSeed(selected)">
          <Lock class="h-3 w-3" /> Use seed
        </Chip>
        <Chip @click="mockOnly('Remove background')">Remove BG</Chip>
        <Chip @click="mockOnly('Send to Edit')">Send to Edit</Chip>
        <Chip @click="chat.rerun(job.id)">
          <RefreshCw class="h-3 w-3" /> Re-run
        </Chip>
        <Chip @click="copyParams">
          <Copy class="h-3 w-3" /> Params
        </Chip>
      </div>

      <p class="mt-3 text-[11px] leading-relaxed text-muted">
        steps {{ job.params.steps }} - cfg {{ job.params.cfg }} - {{ job.params.sampler }}/{{ job.params.scheduler }}
        <span v-if="job.params.refine.on">- refine {{ job.params.refine.steps }} steps @ {{ job.params.refine.scale }}px</span>
      </p>
    </template>
  </div>
</template>
