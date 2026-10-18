<script setup lang="ts">
import { computed } from 'vue'
import { Plus } from '@lucide/vue'
import { useSettingsStore } from '@/stores/settings'
import AppModal from '@/components/ui/AppModal.vue'
import AppButton from '@/components/ui/AppButton.vue'
import ProfileRow from './ProfileRow.vue'

const props = defineProps<{ kind: 'comfyui' | 'ollama' }>()
const open = defineModel<boolean>({ required: true })
const settings = useSettingsStore()

const engineName = computed(() => (props.kind === 'comfyui' ? 'ComfyUI' : 'Ollama'))
const list = computed(() => settings.profiles.filter((p) => p.kind === props.kind))
</script>

<template>
  <AppModal
    v-model="open"
    :title="`${engineName} profiles`"
    subtitle="Switch between local, LAN or remote endpoints. The active profile is used for every call."
  >
    <div class="space-y-3">
      <ProfileRow
        v-for="p in list"
        :key="p.id"
        :profile="p"
        :kind="kind"
        :active="settings.activeProfiles[kind] === p.id"
        :can-remove="list.length > 1"
      />
    </div>

    <template #footer>
      <AppButton variant="ghost" @click="settings.addProfile(kind)">
        <Plus class="h-3.5 w-3.5" /> Add profile
      </AppButton>
      <AppButton variant="primary" @click="open = false">Done</AppButton>
    </template>
  </AppModal>
</template>
