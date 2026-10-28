<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  CheckCircle2,
  FolderOpen,
  LoaderCircle,
  PackageSearch,
  RefreshCw,
  Settings,
  TriangleAlert,
} from '@lucide/vue'
import { api, ApiError } from '@/lib/api'
import { useContentStore } from '@/stores/content'
import { useSettingsStore } from '@/stores/settings'
import { useUiStore } from '@/stores/ui'
import type { ComfyRequirementNode } from '@/types'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'
import AppModal from '@/components/ui/AppModal.vue'
import Badge from '@/components/ui/Badge.vue'
import NodeInstallButton from '@/components/content/NodeInstallButton.vue'

interface NodeGroup {
  id: string
  name: string
  nodes: ComfyRequirementNode[]
}

const open = defineModel<boolean>({ required: true })
const router = useRouter()
const content = useContentStore()
const settings = useSettingsStore()
const ui = useUiStore()

const inspecting = computed(() => content.checking)
const inspect = computed(() => content.inspect)
const folderValid = computed(() => inspect.value?.valid === true)
const gitMissing = computed(() => inspect.value?.gitAvailable === false)
const pythonMissing = computed(() => folderValid.value && !inspect.value?.pythonPath)
const browsingFolder = ref(false)

/** Required (non-optional) nodes missing from core and every installed GenModule. */
const groups = computed<NodeGroup[]>(() => {
  const report = content.requirements
  if (!report || !report.inspect.valid) return []

  const result: NodeGroup[] = []
  const coreNodes = report.core.nodes.filter((node) => node.installed === false && !node.optional)
  if (coreNodes.length) {
    result.push({ id: 'core', name: 'Core requirements', nodes: coreNodes })
  }
  for (const mod of report.modules) {
    const nodes = mod.nodes.filter((node) => node.installed === false && !node.optional)
    if (nodes.length) result.push({ id: mod.id, name: mod.name, nodes })
  }
  return result
})

const missingCount = computed(() => groups.value.reduce((sum, group) => sum + group.nodes.length, 0))
const moduleErrors = computed(() => (content.requirements?.modules ?? []).filter((mod) => mod.error))
const allRequiredReady = computed(
  () => folderValid.value && missingCount.value === 0 && moduleErrors.value.length === 0,
)
const launcherSuggestion = computed(
  () => inspect.value?.suggestedFolder ?? inspect.value?.suggestions[0] ?? '',
)

async function applyFolder(path: string) {
  if (!path) return
  settings.comfyuiFolder = path
  await settings.flushSettings()
  await content.refresh()
}

async function browseFolder() {
  if (browsingFolder.value) return
  browsingFolder.value = true
  try {
    const result = await api.pickPath({
      mode: 'folder',
      title: 'Select the ComfyUI source folder (the one with main.py)',
      start: settings.comfyuiFolder,
    })
    if (result.path) await applyFolder(result.path)
  } catch (err) {
    ui.toast(
      err instanceof ApiError && err.isOffline
        ? 'Backend offline - the folder dialog opens on the machine running the backend.'
        : `Could not open the dialog: ${err instanceof Error ? err.message : 'unknown error'}`,
      'warn',
    )
  } finally {
    browsingFolder.value = false
  }
}

function openSettings(tab = 'content') {
  open.value = false
  void router.push({ path: '/settings', query: { tab } })
}
</script>

<template>
  <AppModal
    v-model="open"
    title="ComfyUI setup"
    subtitle="Check the engine folder and install the custom nodes the generation modules need."
    width="760px"
  >
    <div class="space-y-4 text-sm leading-relaxed">
      <div v-if="inspecting" class="flex items-center gap-2 rounded-xl border border-border bg-surface-2/40 p-3 text-xs text-muted">
        <LoaderCircle class="h-4 w-4 animate-spin" />
        Checking the ComfyUI folder...
      </div>

      <!-- folder first: without a valid source folder there is nothing to audit -->
      <div v-else-if="!folderValid" class="space-y-3">
        <div class="flex items-start gap-2 rounded-xl border border-warn/30 bg-warn/10 p-3 text-xs text-warn">
          <TriangleAlert class="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p class="font-medium">Choose your ComfyUI source folder</p>
            <p class="mt-0.5 leading-relaxed">
              {{ inspect?.error || 'No ComfyUI folder configured yet.' }} Pick the folder that contains
              <code class="rounded bg-black/20 px-1">main.py</code>,
              <code class="rounded bg-black/20 px-1">custom_nodes/</code> and
              <code class="rounded bg-black/20 px-1">models/</code>.
            </p>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <div class="min-w-64 flex-1">
            <AppInput
              v-model="settings.comfyuiFolder"
              placeholder="e.g. D:\ComfyUI_windows_portable\ComfyUI"
            />
          </div>
          <AppButton variant="ghost" :disabled="browsingFolder" @click="browseFolder">
            <LoaderCircle v-if="browsingFolder" class="h-3.5 w-3.5 animate-spin" />
            <FolderOpen v-else class="h-3.5 w-3.5" />
            Browse...
          </AppButton>
        </div>

        <div v-if="launcherSuggestion" class="flex flex-wrap items-center gap-2 text-xs">
          <span class="text-muted">Detected source folder:</span>
          <code class="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[10px]">{{ launcherSuggestion }}</code>
          <AppButton variant="ghost" @click="applyFolder(launcherSuggestion)">Use this folder</AppButton>
        </div>

        <p class="text-[11px] text-muted">
          The app does not bundle ComfyUI. Download the portable or desktop release from
          <a class="text-accent underline-offset-2 hover:underline" href="https://www.comfy.org/download" target="_blank" rel="noreferrer">comfy.org/download</a>,
          then point the field above at its <code class="rounded bg-surface-2 px-1">ComfyUI</code> folder.
        </p>
      </div>

      <!-- valid folder: required nodes only, no optional nodes or model downloads -->
      <template v-else>
        <div class="flex items-center gap-2 rounded-xl border border-border bg-surface-2/40 p-3 text-xs">
          <CheckCircle2 class="h-4 w-4 shrink-0 text-success" />
          <span class="min-w-0 flex-1 truncate" :title="inspect?.path">{{ inspect?.path }}</span>
          <span class="text-muted">
            {{ inspect?.flavor === 'portable' ? 'Portable' : inspect?.flavor === 'venv' ? 'Venv' : 'ComfyUI' }}
          </span>
        </div>

        <div v-if="gitMissing" class="flex items-start gap-2 rounded-xl border border-warn/30 bg-warn/10 p-3 text-xs text-warn">
          <TriangleAlert class="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            Git was not found. Install
            <a class="underline underline-offset-2" href="https://git-scm.com/download/win" target="_blank" rel="noreferrer">Git for Windows</a>
            and restart the app. Git-based node installs and updates are disabled until then.
          </p>
        </div>

        <div v-if="pythonMissing" class="flex items-start gap-2 rounded-xl border border-warn/30 bg-warn/10 p-3 text-xs text-warn">
          <TriangleAlert class="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            ComfyUI's Python was not found. Node files can still be installed, but their Python dependencies will be
            skipped. Check that this is a Portable/Venv install.
          </p>
        </div>

        <div v-if="allRequiredReady" class="flex items-center gap-3 rounded-xl border border-success/30 bg-success/10 p-4">
          <CheckCircle2 class="h-5 w-5 shrink-0 text-success" />
          <div>
            <p class="text-sm font-medium text-success">All required custom nodes are installed</p>
            <p class="text-xs text-muted">Optional nodes and model files are managed in Settings → Engine content.</p>
          </div>
        </div>

        <template v-else>
          <template v-if="missingCount">
            <div class="flex items-center gap-2">
              <PackageSearch class="h-4 w-4 text-accent" />
              <span class="text-sm font-medium">
                {{ missingCount }} required custom node{{ missingCount === 1 ? '' : 's' }} missing
              </span>
              <span class="text-xs text-muted">across {{ groups.length }} manifest{{ groups.length === 1 ? '' : 's' }}</span>
              <AppButton variant="ghost" class="ml-auto" :disabled="inspecting" @click="content.refresh()">
                <LoaderCircle v-if="inspecting" class="h-3.5 w-3.5 animate-spin" />
                <RefreshCw v-else class="h-3.5 w-3.5" />
                Check again
              </AppButton>
            </div>

            <div class="space-y-3">
              <div v-for="group in groups" :key="group.id" class="rounded-xl border border-border bg-surface-2/30 p-3">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="text-xs font-semibold">{{ group.name }}</span>
                  <span class="font-mono text-[10px] text-muted">{{ group.id }}</span>
                  <Badge tone="warn">{{ group.nodes.length }} missing</Badge>
                </div>
                <div
                  v-for="node in group.nodes"
                  :key="`${group.id}-${node.name}`"
                  class="mt-2 flex flex-wrap items-center gap-2 border-t border-border/50 pt-2 text-xs"
                >
                  <div class="min-w-0 flex-1">
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="font-medium">{{ node.name }}</span>
                      <Badge v-if="node.package" tone="neutral">package</Badge>
                    </div>
                    <p v-if="node.why" class="mt-0.5 text-[10px] leading-relaxed text-muted">{{ node.why }}</p>
                  </div>
                  <NodeInstallButton :module-id="group.id" :module-name="group.name" :node="node" />
                </div>
              </div>
            </div>
          </template>

          <div v-if="moduleErrors.length" class="rounded-xl border border-warn/30 bg-warn/10 p-3 text-[11px] text-warn">
            <p v-for="mod in moduleErrors" :key="mod.id">{{ mod.name }}: {{ mod.error }}</p>
          </div>

          <p v-if="missingCount" class="text-[11px] text-muted">
            Only required custom nodes are listed. Optional nodes and model files stay in Settings → Engine content;
            installing a node writes inside your ComfyUI folder and may run its install script. Restart ComfyUI after
            an install.
          </p>
        </template>
      </template>

      <p v-if="content.lastError" class="text-[11px] text-warn">{{ content.lastError }}</p>
    </div>

    <template #footer>
      <AppButton variant="ghost" @click="openSettings(folderValid ? 'content' : 'connections')">
        <Settings class="h-3.5 w-3.5" />
        Open settings
      </AppButton>
      <AppButton variant="primary" @click="open = false">
        {{ allRequiredReady ? 'Done' : 'Later' }}
      </AppButton>
    </template>
  </AppModal>
</template>
