<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import {
  CheckCircle2,
  Download,
  FolderOpen,
  Link2,
  LoaderCircle,
  RefreshCw,
  TriangleAlert,
} from '@lucide/vue'
import type {
  ModuleSetupGroup,
  ModuleSetupItem,
  ModuleSetupMissingGroup,
  ModuleSetupPayload,
} from '@/types'
import AppModal from '@/components/ui/AppModal.vue'
import AppButton from '@/components/ui/AppButton.vue'
import Badge from '@/components/ui/Badge.vue'

const open = defineModel<boolean>({ required: true })

const props = withDefaults(
  defineProps<{
    payload: ModuleSetupPayload | null
    loading?: boolean
    error?: string
    title?: string
  }>(),
  { loading: false, error: '', title: 'Module setup' },
)

const emit = defineEmits<{
  (e: 'refresh'): void
}>()

const moduleTitle = computed(
  () => props.title || props.payload?.module.label || 'Module setup',
)

const moduleSubtitle = computed(() => {
  const module = props.payload?.module
  if (!module) return 'Checking required files...'
  return module.description || 'Required model files and download links.'
})

function bytesLabel(value: number | null): string {
  if (!value || value <= 0) return ''
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let amount = value
  let index = 0
  while (amount >= 1024 && index < units.length - 1) {
    amount /= 1024
    index += 1
  }
  return `${amount.toFixed(index > 2 ? 1 : 0)} ${units[index]}`
}

function groupBadge(group: ModuleSetupGroup): {
  tone: 'ok' | 'warn' | 'neutral'
  label: string
} {
  if (group.satisfied === true) return { tone: 'ok', label: 'satisfied' }
  if (group.satisfied === false) {
    return { tone: 'warn', label: group.required ? 'required' : 'not installed' }
  }
  return { tone: 'neutral', label: 'not checked' }
}

function itemLabel(item: ModuleSetupItem): string {
  return item.label || item.name || item.id
}

function isMissingGroup(
  value: ModuleSetupItem | ModuleSetupMissingGroup,
): value is ModuleSetupMissingGroup {
  return value.kind === 'group'
}

const missingGroups = computed(() =>
  (props.payload?.missingRequired ?? []).filter(isMissingGroup),
)
const missingItems = computed(() =>
  (props.payload?.missingRequired ?? []).filter(
    (value): value is ModuleSetupItem => !isMissingGroup(value),
  ),
)
</script>

<template>
  <AppModal
    v-model="open"
    :title="`${moduleTitle} setup`"
    :subtitle="moduleSubtitle"
    width="760px"
  >
    <div class="space-y-4">
      <div v-if="loading" class="flex items-center gap-2 rounded-xl border border-border bg-surface-2 px-3 py-2 text-xs text-muted">
        <LoaderCircle class="h-4 w-4 animate-spin" />
        Checking the model catalog...
      </div>

      <div
        v-else-if="error"
        class="flex items-start gap-2 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-xs leading-relaxed text-danger"
      >
        <TriangleAlert class="mt-0.5 h-4 w-4 shrink-0" />
        <span>{{ error }}</span>
      </div>

      <template v-else-if="payload">
        <div
          v-if="payload.catalog.available === false"
          class="flex items-start gap-2 rounded-xl border border-warn/30 bg-warn/10 px-3 py-2 text-xs leading-relaxed text-warn"
        >
          <TriangleAlert class="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            The model catalog is empty, so file presence is unknown.
            Build it in <strong>Settings → Model catalog</strong>, then refresh this panel.
          </span>
        </div>

        <div
          v-else-if="payload.ready === false"
          class="rounded-xl border border-warn/30 bg-warn/10 px-3 py-3 text-xs text-warn"
        >
          <div class="flex items-center gap-2 font-semibold">
            <TriangleAlert class="h-4 w-4" />
            Missing required setup files
          </div>
          <p class="mt-1 text-[11px] leading-relaxed text-warn/90">
            Place these files in the folders below, then refresh the model catalog.
            Nothing is downloaded automatically.
          </p>
          <div class="mt-2 space-y-2">
            <div
              v-for="missing in missingGroups"
              :key="`group-${missing.id}`"
              class="rounded-lg border border-warn/25 bg-surface/70 p-2.5 text-text"
            >
              <div class="flex flex-wrap items-center gap-1.5">
                <span class="text-[11px] font-semibold">{{ missing.label }}</span>
                <Badge tone="warn">one of</Badge>
                <Badge v-if="missing.nsfw" tone="warn">NSFW</Badge>
              </div>
              <p class="mt-1 flex items-center gap-1 text-[10px] text-muted">
                <FolderOpen class="h-3 w-3" />
                {{ missing.folder }}
              </p>
              <div class="mt-1.5 flex flex-wrap gap-1.5">
                <a
                  v-for="item in missing.items"
                  :key="item.id"
                  :href="item.url || item.pageUrl || undefined"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-[10px] transition-colors hover:border-accent/40 hover:text-accent"
                  :class="item.url || item.pageUrl ? '' : 'pointer-events-none opacity-45'"
                >
                  <Download class="h-3 w-3" />
                  {{ item.label }}
                  <span v-if="item.size" class="text-muted">· {{ bytesLabel(item.size) }}</span>
                </a>
              </div>
            </div>
            <div
              v-for="missing in missingItems"
              :key="`model-${missing.id}`"
              class="rounded-lg border border-warn/25 bg-surface/70 p-2.5 text-text"
            >
              <div class="flex flex-wrap items-center gap-1.5">
                <span class="text-[11px] font-semibold">{{ missing.label }}</span>
                <Badge v-if="missing.nsfw" tone="warn">NSFW</Badge>
              </div>
              <p class="mt-1 break-all font-mono text-[10px] text-muted">{{ missing.name }}</p>
              <p class="mt-0.5 flex items-center gap-1 text-[10px] text-muted">
                <FolderOpen class="h-3 w-3" />
                {{ missing.destination || missing.folder }}
              </p>
              <div class="mt-1.5 flex flex-wrap gap-1.5">
                <a
                  v-if="missing.url"
                  :href="missing.url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-[10px] transition-colors hover:border-accent/40 hover:text-accent"
                >
                  <Download class="h-3 w-3" /> Download
                </a>
                <a
                  v-if="missing.pageUrl"
                  :href="missing.pageUrl"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-[10px] transition-colors hover:border-accent/40 hover:text-accent"
                >
                  <Link2 class="h-3 w-3" /> Source page
                </a>
                <span v-if="!missing.url && !missing.pageUrl" class="text-[10px] text-muted">
                  No download URL is documented for this file.
                </span>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="flex items-center gap-2 rounded-xl border border-success/30 bg-success/10 px-3 py-2 text-xs text-success">
          <CheckCircle2 class="h-4 w-4" />
          All required files are present.
        </div>

        <section
          v-for="pack in payload.packs"
          :key="pack.id"
          class="rounded-xl border border-border bg-surface-2/40 p-3"
        >
          <div class="flex flex-wrap items-center gap-2">
            <h3 class="text-sm font-semibold">{{ pack.label }}</h3>
            <Badge v-if="pack.nsfw" tone="warn">NSFW</Badge>
            <Badge v-if="pack.ready === true" tone="ok">Ready</Badge>
            <Badge v-else-if="pack.ready === false" tone="warn">Needs files</Badge>
          </div>
          <p v-if="pack.description" class="mt-1 text-[11px] leading-relaxed text-muted">
            {{ pack.description }}
          </p>

          <div
            v-for="group in pack.groups"
            :key="group.id"
            class="mt-2 rounded-lg border border-border bg-surface p-2.5"
          >
            <div class="flex flex-wrap items-center gap-1.5">
              <span class="text-[11px] font-semibold">{{ group.label }}</span>
              <Badge tone="neutral">{{ group.mode === 'oneOf' ? 'one of' : group.mode }}</Badge>
              <Badge :tone="groupBadge(group).tone">
                {{ groupBadge(group).label }}
              </Badge>
              <Badge v-if="group.nsfw" tone="warn">NSFW</Badge>
            </div>
            <p v-if="group.why" class="mt-1 text-[10px] leading-snug text-muted">{{ group.why }}</p>
            <p v-if="group.satisfied === true && group.matchedFile" class="mt-1 text-[10px] text-success">
              Detected: {{ group.matchedFile }}
            </p>
            <div class="mt-1.5 space-y-1.5">
              <div
                v-for="item in group.items"
                :key="item.id"
                class="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border border-border/70 bg-surface-2/40 px-2 py-1.5"
              >
                <CheckCircle2 v-if="item.present === true" class="h-3.5 w-3.5 shrink-0 text-success" />
                <TriangleAlert v-else-if="item.present === false" class="h-3.5 w-3.5 shrink-0 text-warn" />
                <span v-else class="h-3.5 w-3.5 shrink-0 rounded-full border border-border" />
                <span class="text-[11px] font-medium">{{ itemLabel(item) }}</span>
                <Badge v-if="item.nsfw" tone="warn">NSFW</Badge>
                <Badge v-if="!item.tested" tone="neutral">untested</Badge>
                <span class="text-[10px] text-muted">{{ item.name }}</span>
                <span v-if="item.size" class="text-[10px] text-muted">· {{ bytesLabel(item.size) }}</span>
                <span class="ml-auto flex items-center gap-1.5">
                  <a
                    v-if="item.url"
                    :href="item.url"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-1.5 py-0.5 text-[10px] transition-colors hover:border-accent/40 hover:text-accent"
                  >
                    <Download class="h-3 w-3" /> Download
                  </a>
                  <a
                    v-if="item.pageUrl"
                    :href="item.pageUrl"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-1.5 py-0.5 text-[10px] transition-colors hover:border-accent/40 hover:text-accent"
                  >
                    <Link2 class="h-3 w-3" /> Page
                  </a>
                </span>
              </div>
            </div>
          </div>

          <div
            v-for="item in pack.items.filter((entry) => entry.required)"
            :key="item.id"
            class="mt-2 rounded-lg border border-border bg-surface p-2.5"
          >
            <div class="flex flex-wrap items-center gap-1.5">
              <CheckCircle2 v-if="item.present === true" class="h-3.5 w-3.5 text-success" />
              <TriangleAlert v-else-if="item.present === false" class="h-3.5 w-3.5 text-warn" />
              <span class="text-[11px] font-semibold">{{ itemLabel(item) }}</span>
              <Badge v-if="item.nsfw" tone="warn">NSFW</Badge>
              <Badge v-if="item.required" tone="accent">required</Badge>
              <span class="text-[10px] text-muted">{{ item.name }}</span>
              <span v-if="item.size" class="text-[10px] text-muted">· {{ bytesLabel(item.size) }}</span>
            </div>
            <p class="mt-1 flex items-center gap-1 text-[10px] text-muted">
              <FolderOpen class="h-3 w-3" />
              {{ item.destination || item.folder }}
            </p>
            <div class="mt-1.5 flex flex-wrap gap-1.5">
              <a
                v-if="item.url"
                :href="item.url"
                target="_blank"
                rel="noopener noreferrer"
                class="inline-flex items-center gap-1 rounded-md border border-border bg-surface-2 px-2 py-1 text-[10px] transition-colors hover:border-accent/40 hover:text-accent"
              >
                <Download class="h-3 w-3" /> Download
              </a>
              <a
                v-if="item.pageUrl"
                :href="item.pageUrl"
                target="_blank"
                rel="noopener noreferrer"
                class="inline-flex items-center gap-1 rounded-md border border-border bg-surface-2 px-2 py-1 text-[10px] transition-colors hover:border-accent/40 hover:text-accent"
              >
                <Link2 class="h-3 w-3" /> Source page
              </a>
            </div>
          </div>

          <details
            v-if="pack.items.some((entry) => !entry.required)"
            class="mt-2 rounded-lg border border-border bg-surface p-2.5"
          >
            <summary class="cursor-pointer list-none text-[11px] font-semibold text-muted [&::-webkit-details-marker]:hidden">
              Optional files ({{ pack.items.filter((entry) => !entry.required).length }})
            </summary>
            <div class="mt-1.5 space-y-1.5">
              <div
                v-for="item in pack.items.filter((entry) => !entry.required)"
                :key="item.id"
                class="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border border-border/70 bg-surface-2/40 px-2 py-1.5"
              >
                <CheckCircle2 v-if="item.present === true" class="h-3.5 w-3.5 shrink-0 text-success" />
                <TriangleAlert v-else-if="item.present === false" class="h-3.5 w-3.5 shrink-0 text-muted" />
                <span class="text-[11px]">{{ itemLabel(item) }}</span>
                <Badge v-if="item.nsfw" tone="warn">NSFW</Badge>
                <span class="text-[10px] text-muted">{{ item.name }}</span>
                <span v-if="item.size" class="text-[10px] text-muted">· {{ bytesLabel(item.size) }}</span>
                <span class="ml-auto flex items-center gap-1.5">
                  <a
                    v-if="item.url"
                    :href="item.url"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-1.5 py-0.5 text-[10px] transition-colors hover:border-accent/40 hover:text-accent"
                  >
                    <Download class="h-3 w-3" /> Download
                  </a>
                  <a
                    v-if="item.pageUrl"
                    :href="item.pageUrl"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-1.5 py-0.5 text-[10px] transition-colors hover:border-accent/40 hover:text-accent"
                  >
                    <Link2 class="h-3 w-3" /> Page
                  </a>
                </span>
              </div>
            </div>
          </details>
        </section>

        <p class="text-[10px] leading-relaxed text-muted">
          {{ payload.policy.note }}
        </p>
      </template>
    </div>

    <template #footer>
      <RouterLink
        to="/settings?tab=catalog"
        class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-2.5 text-xs text-muted transition-colors hover:border-accent/40 hover:text-text"
      >
        Model catalog
      </RouterLink>
      <AppButton size="sm" variant="ghost" :disabled="loading" @click="emit('refresh')">
        <RefreshCw class="h-3.5 w-3.5" />
        Refresh check
      </AppButton>
      <AppButton size="sm" @click="open = false">Close</AppButton>
    </template>
  </AppModal>
</template>
