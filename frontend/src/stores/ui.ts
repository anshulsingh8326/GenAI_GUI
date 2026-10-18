import { reactive, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import type { AccentId, ThemeId } from '@/types'

export interface Toast {
  id: number
  message: string
  kind: 'info' | 'success' | 'warn' | 'error'
}

const LS_KEY = 'genai.ui.v1'

function load(): Record<string, unknown> {
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) || '{}')
  } catch {
    return {}
  }
}

export const useUiStore = defineStore('ui', () => {
  const saved = load()

  const theme = ref<ThemeId>((saved.theme as ThemeId) ?? 'pastel-dark')
  const accent = ref<AccentId>((saved.accent as AccentId) ?? 'lavender')
  const collapsedGroups = reactive<Record<string, boolean>>(
    (saved.collapsedGroups as Record<string, boolean>) ?? {},
  )
  const toasts = ref<Toast[]>([])
  let toastSeq = 0

  function applyTheme() {
    document.documentElement.dataset.theme = theme.value
    document.documentElement.dataset.accent = accent.value
  }

  function setTheme(t: ThemeId) {
    theme.value = t
    applyTheme()
  }

  function setAccent(a: AccentId) {
    accent.value = a
    applyTheme()
  }

  function toggleGroup(id: string) {
    collapsedGroups[id] = !collapsedGroups[id]
  }

  function toast(message: string, kind: Toast['kind'] = 'info', ms = 3400) {
    toastSeq += 1
    const id = toastSeq
    toasts.value.push({ id, message, kind })
    setTimeout(() => dismiss(id), ms)
  }

  function dismiss(id: number) {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }

  watch(
    [theme, accent, collapsedGroups],
    () => {
      localStorage.setItem(
        LS_KEY,
        JSON.stringify({ theme: theme.value, accent: accent.value, collapsedGroups }),
      )
    },
    { deep: true },
  )

  return { theme, accent, collapsedGroups, toasts, applyTheme, setTheme, setAccent, toggleGroup, toast, dismiss }
})
