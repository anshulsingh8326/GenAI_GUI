<script setup lang="ts">
import { Check, Trash2 } from '@lucide/vue'
import type { ConnectionProfile } from '@/types'
import { useSettingsStore } from '@/stores/settings'
import AppButton from '@/components/ui/AppButton.vue'
import AppInput from '@/components/ui/AppInput.vue'

// One connection profile row inside ProfilesModal. Editing goes through the
// store setters (never direct prop mutation).
const props = defineProps<{
  profile: ConnectionProfile
  kind: 'comfyui' | 'ollama'
  active: boolean
  canRemove: boolean
}>()

const settings = useSettingsStore()
</script>

<template>
  <div
    class="rounded-2xl border p-3 transition-colors"
    :class="active ? 'border-accent/50 bg-accent-soft/30' : 'border-border'"
  >
    <div class="flex items-center gap-2">
      <div class="min-w-0 flex-1">
        <AppInput
          :model-value="profile.name"
          placeholder="Profile name"
          @update:model-value="settings.setProfileName(profile.id, $event)"
        />
      </div>
      <span v-if="active" class="flex shrink-0 items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-medium text-accent">
        <Check class="h-3 w-3" /> Active
      </span>
      <AppButton v-else size="sm" variant="ghost" @click="settings.setActiveProfile(props.kind, profile.id)">Use</AppButton>
      <AppButton
        size="sm"
        variant="ghost"
        class="text-danger"
        :disabled="!canRemove"
        :title="canRemove ? 'Remove this profile (settings only - no files are touched)' : 'At least one profile must remain'"
        @click="settings.removeProfile(profile.id)"
      >
        <Trash2 class="h-3.5 w-3.5" />
      </AppButton>
    </div>
    <div class="mt-2 space-y-2">
      <AppInput
        :model-value="profile.url"
        placeholder="http://127.0.0.1:8188"
        @update:model-value="settings.setProfileUrl(profile.id, $event)"
      />
      <AppInput
        :model-value="profile.auth"
        placeholder="Auth header (optional) - e.g. Authorization: Bearer ..."
        @update:model-value="settings.setProfileAuth(profile.id, $event)"
      />
    </div>
  </div>
</template>
