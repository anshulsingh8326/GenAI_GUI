<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Download, LoaderCircle, Power, RefreshCw, Terminal } from '@lucide/vue'
import { useContentStore } from '@/stores/content'
import type { ComfyInstallTask, ComfyRequirementNode } from '@/types'
import AppButton from '@/components/ui/AppButton.vue'
import AppModal from '@/components/ui/AppModal.vue'
import Badge from '@/components/ui/Badge.vue'

const props = defineProps<{
  moduleId: string
  moduleName: string
  node: ComfyRequirementNode
}>()

const content = useContentStore()
const confirmOpen = ref(false)
const logOpen = ref(false)
const logEl = ref<HTMLElement | null>(null)

const task = computed<ComfyInstallTask | null>(() =>
  content.taskMatches(props.moduleId, props.node.name) ? content.installTask : null,
)
const busy = computed(() => task.value?.status === 'running')

/* Git installs must pin a full SHA; package installs (pip) are exempt. */
const unpinned = computed(
  () => Boolean(props.node.repo) && !props.node.package && !props.node.commit,
)

/* Loose prefix compare - manifests store full SHAs, installs report 12 chars. */
function commitMatches(wanted: string, installed: string | null): boolean {
  if (!wanted || !installed) return true
  return wanted.startsWith(installed) || installed.startsWith(wanted)
}

const action = computed<'install' | 'update' | 'retry' | null>(() => {
  if (task.value?.status === 'failed') return 'retry'
  if (props.node.installed === false && !props.node.installedPath) return 'install'
  if (
    props.node.installed &&
    props.node.commit &&
    props.node.installedCommit &&
    !commitMatches(props.node.commit, props.node.installedCommit)
  ) {
    return 'update'
  }
  return null
})

const verb = computed(() => {
  if (action.value === 'install') return 'Install'
  if (action.value === 'update') return 'Update'
  return 'Retry'
})

const confirmTitle = computed(() => `${verb.value} ${props.node.name}`)

const actionDetail = computed(() => {
  if (unpinned.value) {
    return 'This entry has no pinned commit. Add a full 40-character SHA to requirements.json before installing.'
  }
  if (props.node.package) {
    return `Install the Python package ${props.node.pip || props.node.package} into this ComfyUI's Python environment.`
  }
  if (action.value === 'update') {
    return 'Check out the pinned commit, then re-run the node’s Python requirements / install.py if present.'
  }
  return 'Clone the repository at the pinned commit, then run its Python requirements / install.py if present.'
})

const statusLabel = computed(() => {
  if (!task.value) return 'Install'
  if (task.value.status === 'running') return 'Installing'
  if (task.value.status === 'succeeded') return 'Installed'
  return 'Failed'
})

const statusTone = computed<'neutral' | 'accent' | 'ok' | 'warn'>(() => {
  if (!task.value) return 'neutral'
  if (task.value.status === 'running') return 'accent'
  if (task.value.status === 'succeeded') return 'ok'
  return 'warn'
})

function openAction(): void {
  if (action.value === 'retry') {
    void retry()
    return
  }
  confirmOpen.value = true
}

async function runInstall(): Promise<void> {
  confirmOpen.value = false
  const ok = await content.startInstall(props.moduleId, props.node.name)
  if (ok) logOpen.value = true
}

async function retry(): Promise<void> {
  const ok = await content.startInstall(props.moduleId, props.node.name)
  if (ok) logOpen.value = true
}

function openLog(): void {
  logOpen.value = true
}

watch(
  () => [task.value?.log.length, logOpen.value] as const,
  async () => {
    await nextTick()
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
  },
)
</script>

<template>
  <div class="ml-auto flex items-center gap-1">
    <AppButton
      v-if="task"
      variant="ghost"
      size="sm"
      title="Show the install log"
      @click="openLog"
    >
      <LoaderCircle v-if="busy" class="h-3.5 w-3.5 animate-spin" />
      <Terminal v-else class="h-3.5 w-3.5" />
    </AppButton>
    <AppButton
      v-if="action"
      variant="ghost"
      size="sm"
      :disabled="content.starting || content.installing"
      :title="actionDetail"
      @click="openAction"
    >
      <LoaderCircle v-if="busy" class="h-3.5 w-3.5 animate-spin" />
      <Download v-else-if="action === 'install'" class="h-3.5 w-3.5" />
      <RefreshCw v-else class="h-3.5 w-3.5" />
      {{ busy ? 'Working' : verb }}
    </AppButton>

    <!-- confirmation before writing anything -->
    <AppModal v-model="confirmOpen" :title="confirmTitle" :subtitle="moduleName">
      <div class="space-y-3 text-xs leading-relaxed">
        <p v-if="node.why" class="text-muted">{{ node.why }}</p>
        <div class="space-y-1.5 rounded-lg border border-border bg-surface-2/40 p-3">
          <p class="text-muted">{{ actionDetail }}</p>
          <p v-if="node.repo" class="break-all">
            <span class="text-muted">Repository </span>
            <code class="font-mono text-[11px]">{{ node.repo }}</code>
          </p>
          <p v-if="node.commit">
            <span class="text-muted">Pinned commit </span>
            <code class="font-mono text-[11px]">{{ node.commit.slice(0, 12) }}</code>
          </p>
          <p v-else-if="!node.package" class="text-warn">
            No pinned commit - installs are disabled. Add a full 40-character SHA to requirements.json.
          </p>
          <p v-if="node.package">
            <span class="text-muted">Package </span>
            <code class="font-mono text-[11px]">{{ node.pip || node.package }}</code>
          </p>
        </div>
        <p class="text-warn">
          This writes inside your ComfyUI folder and may run the node’s install script. Restart ComfyUI afterwards to
          load it. Nothing is overwritten or deleted.
        </p>
      </div>
      <template #footer>
        <AppButton variant="ghost" @click="confirmOpen = false">Cancel</AppButton>
        <AppButton
          variant="primary"
          :disabled="content.starting || content.installing || unpinned"
          @click="runInstall"
        >
          {{ content.starting ? 'Starting...' : verb }}
        </AppButton>
      </template>
    </AppModal>

    <!-- live log -->
    <AppModal v-model="logOpen" :title="`${node.name} - ${statusLabel}`" :subtitle="moduleName" width="760px">
      <div v-if="task" class="space-y-3">
        <div class="flex flex-wrap items-center gap-2 text-[11px]">
          <Badge :tone="statusTone">{{ statusLabel }}</Badge>
          <span class="text-muted">{{ task.stage }}</span>
          <span class="truncate font-mono text-[10px] text-muted" :title="task.target">{{ task.target }}</span>
        </div>
        <p v-if="task.warning" class="rounded-lg bg-warn/10 px-3 py-2 text-[11px] text-warn">{{ task.warning }}</p>
        <p v-if="task.error" class="rounded-lg bg-danger/10 px-3 py-2 text-[11px] text-danger">{{ task.error }}</p>
        <pre
          ref="logEl"
          class="max-h-[320px] overflow-y-auto whitespace-pre-wrap break-words rounded-lg border border-border bg-black/30 p-3 font-mono text-[10px] leading-relaxed text-muted"
        >{{ task.log.join('\n') || 'Starting...' }}</pre>
        <p v-if="task.status === 'succeeded'" class="text-[11px] text-muted">
          Restart ComfyUI to load the new node. The audit above refreshes automatically.
        </p>
      </div>
      <template #footer>
        <AppButton
          v-if="task?.status === 'succeeded'"
          variant="primary"
          :disabled="content.restarting"
          @click="content.restartComfyui()"
        >
          <LoaderCircle v-if="content.restarting" class="h-3.5 w-3.5 animate-spin" />
          <Power v-else class="h-3.5 w-3.5" />
          {{ content.restarting ? 'Restarting...' : 'Restart ComfyUI' }}
        </AppButton>
        <AppButton v-if="task?.status === 'failed'" variant="soft" :disabled="content.starting" @click="retry">
          <RefreshCw class="h-3.5 w-3.5" />
          Retry
        </AppButton>
        <AppButton variant="ghost" @click="logOpen = false">
          {{ task?.status === 'running' ? 'Run in background' : 'Close' }}
        </AppButton>
      </template>
    </AppModal>
  </div>
</template>
