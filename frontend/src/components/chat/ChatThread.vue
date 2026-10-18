<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Sparkles } from '@lucide/vue'
import { useChatStore } from '@/stores/chat'
import UserBubble from './UserBubble.vue'
import ResultCard from './ResultCard.vue'
import Chip from '@/components/ui/Chip.vue'

const props = defineProps<{
  tabId: string
  suggestions?: string[]
}>()

const chat = useChatStore()
const thread = computed(() => chat.thread(props.tabId))
const scroller = ref<HTMLElement | null>(null)

watch(
  () => thread.value.messages.length,
  async () => {
    await nextTick()
    scroller.value?.scrollTo({ top: scroller.value.scrollHeight, behavior: 'smooth' })
  },
)

function useSuggestion(s: string) {
  thread.value.composer.text = s
}
</script>

<template>
  <div ref="scroller" class="min-h-0 flex-1 overflow-y-auto">
    <div class="mx-auto w-full max-w-3xl space-y-5 px-6 py-6">
      <!-- empty state -->
      <div v-if="!thread.messages.length" class="py-14 text-center">
        <div class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-3xl bg-accent-soft text-accent">
          <Sparkles class="h-6 w-6" />
        </div>
        <h2 class="text-lg font-semibold">Describe it - the studio does the rest</h2>
        <p class="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted">
          Type an idea below, add reference images with +, and the pipeline handles enhance, identity, LoRAs
          and the refine pass - like your ComfyUI workflow, minus the graph.
        </p>
        <div v-if="suggestions?.length" class="mx-auto mt-6 flex max-w-xl flex-wrap justify-center gap-2">
          <Chip v-for="s in suggestions" :key="s" @click="useSuggestion(s)">{{ s }}</Chip>
        </div>
      </div>

      <!-- thread -->
      <template v-for="m in thread.messages" :key="m.id">
        <UserBubble v-if="m.role === 'user'" :message="m" />
        <ResultCard v-else-if="m.jobId" :job-id="m.jobId" />
      </template>
    </div>
  </div>
</template>
