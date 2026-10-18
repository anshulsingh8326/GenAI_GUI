import { reactive, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import type { ConnectionProfile, SettingsValues, SystemInfo } from '@/types'
import { DEFAULT_PROMPTS } from '@/lib/fixtures'
import { api } from '@/lib/api'
import { useUiStore } from './ui'

// Settings are backend-owned now: every change is pushed to settings.json via
// PUT /api/settings (debounced). localStorage stays as an offline cache so the
// GUI still works when the backend is not running.
//
// `baseline` holds the shipped defaults (from GET /api/settings/defaults) and
// powers every per-field reset button + the "reset all" action.

const LS_KEY = 'genai.settings.v1'

type Kind = 'comfyui' | 'ollama'

/** Field address for reset helpers, e.g. ['folders', 'library'] or ['profiles', id, 'url']. */
export type FieldPath = (string | number)[]

function fallbackValues(): SettingsValues {
  return {
    connections: {
      comfyui: { url: 'http://127.0.0.1:8188' },
      ollama: { url: 'http://127.0.0.1:11434' },
    },
    profiles: [
      { id: 'comfyui-local', name: 'Local ComfyUI', kind: 'comfyui', url: 'http://127.0.0.1:8188', auth: '' },
      { id: 'ollama-local', name: 'Local Ollama', kind: 'ollama', url: 'http://127.0.0.1:11434', auth: '' },
    ],
    activeProfiles: { comfyui: 'comfyui-local', ollama: 'ollama-local' },
    defaults: {
      imageModel: 'krea2-turbo-int8',
      upscaler: '4x-ultrasharp',
      textProvider: 'ollama',
      enhanceModel: 'qwen3-abliterated:8b',
      describeModel: 'qwen3-abliterated:8b',
    },
    folders: {
      library: 'D:\\GenAI\\library',
      exports: 'D:\\GenAI\\exports',
      imports: 'D:\\GenAI\\imports',
      agentInbox: 'D:\\GenAI\\agent-inbox',
    },
    prompts: { ...DEFAULT_PROMPTS },
    autoFreeVram: true,
    agentEnabled: false,
    agentToken: 'genai_live_5f3c9a1e7b2d4f80',
    comfyuiLauncher: '',
  }
}

/** Read the localStorage cache and migrate it to the current shape (pre-profiles saves). */
function loadCache(): SettingsValues {
  const fb = fallbackValues()
  let raw: any = {}
  try {
    raw = JSON.parse(localStorage.getItem(LS_KEY) || '{}')
  } catch {
    raw = {}
  }
  if (raw?.connections?.comfyui?.url) fb.connections.comfyui.url = raw.connections.comfyui.url
  if (raw?.connections?.ollama?.url) fb.connections.ollama.url = raw.connections.ollama.url
  if (Array.isArray(raw?.profiles) && raw.profiles.length) {
    fb.profiles = raw.profiles
  } else {
    // pre-profiles shape: turn the single URL per kind into the default profile
    fb.profiles = fb.profiles.map((p) => ({ ...p, url: fb.connections[p.kind].url }))
  }
  if (raw?.activeProfiles) fb.activeProfiles = raw.activeProfiles
  if (raw?.defaults) Object.assign(fb.defaults, raw.defaults)
  if (raw?.folders) Object.assign(fb.folders, raw.folders)
  if (raw?.prompts) fb.prompts = { ...fb.prompts, ...raw.prompts }
  if (typeof raw?.autoFreeVram === 'boolean') fb.autoFreeVram = raw.autoFreeVram
  if (typeof raw?.agentEnabled === 'boolean') fb.agentEnabled = raw.agentEnabled
  if (raw?.agentToken) fb.agentToken = raw.agentToken
  if (typeof raw?.comfyuiLauncher === 'string') fb.comfyuiLauncher = raw.comfyuiLauncher
  return fb
}

function deepGet(obj: unknown, path: FieldPath): unknown {
  return path.reduce<any>((acc, key) => (acc == null ? undefined : acc[key]), obj)
}

function cloned<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}

export const useSettingsStore = defineStore('settings', () => {
  const ui = useUiStore()
  const saved = loadCache()

  // -- persisted state (kept under the same names the components already use) --
  // connections keeps only the URL (mirror of the active profile); live
  // connected/checking/detail state lives in the engine store.
  const connections = reactive<Record<Kind, { url: string }>>({
    comfyui: { url: saved.connections.comfyui.url },
    ollama: { url: saved.connections.ollama.url },
  })
  const profiles = ref<ConnectionProfile[]>(cloned(saved.profiles))
  const activeProfiles = reactive<Record<Kind, string>>({ ...saved.activeProfiles })
  const defaults = reactive({ ...saved.defaults })
  const folders = reactive({ ...saved.folders })
  const prompts = reactive<Record<string, string>>({ ...saved.prompts })
  const autoFreeVram = ref(saved.autoFreeVram)
  const agentEnabled = ref(saved.agentEnabled)
  const agentToken = ref(saved.agentToken)
  const comfyuiLauncher = ref(saved.comfyuiLauncher)

  // -- sync + reset state ------------------------------------------------------
  const baseline = ref<SettingsValues>(fallbackValues())
  const backendState = ref<'connecting' | 'live' | 'offline'>('connecting')
  const saving = ref(false)
  const systemInfo = ref<SystemInfo | null>(null)
  const lastError = ref<string | null>(null)

  // -- profiles ----------------------------------------------------------------
  function activeProfile(kind: Kind): ConnectionProfile | undefined {
    return (
      profiles.value.find((p) => p.id === activeProfiles[kind] && p.kind === kind) ??
      profiles.value.find((p) => p.kind === kind)
    )
  }

  function syncConnectionUrls() {
    for (const kind of ['comfyui', 'ollama'] as Kind[]) {
      const p = activeProfile(kind)
      if (p) connections[kind].url = p.url
    }
  }

  function setActiveProfile(kind: Kind, id: string) {
    const p = profiles.value.find((x) => x.id === id && x.kind === kind)
    if (!p) return
    activeProfiles[kind] = id
    connections[kind].url = p.url
  }

  function setProfileUrl(id: string, url: string) {
    const p = profiles.value.find((x) => x.id === id)
    if (!p) return
    p.url = url
    if (activeProfiles[p.kind] === id) connections[p.kind].url = url
  }

  function setProfileName(id: string, name: string) {
    const p = profiles.value.find((x) => x.id === id)
    if (p) p.name = name
  }

  function setProfileAuth(id: string, auth: string) {
    const p = profiles.value.find((x) => x.id === id)
    if (p) p.auth = auth
  }

  function addProfile(kind: Kind): string {
    const id = `${kind}-${Date.now().toString(36)}`
    profiles.value.push({
      id,
      name: kind === 'comfyui' ? 'New ComfyUI profile' : 'New Ollama profile',
      kind,
      url: connections[kind].url,
      auth: '',
    })
    return id
  }

  function removeProfile(id: string) {
    const p = profiles.value.find((x) => x.id === id)
    if (!p) return
    if (profiles.value.filter((x) => x.kind === p.kind).length <= 1) {
      ui.toast('Keep at least one profile - edit or reset it instead.', 'warn')
      return
    }
    profiles.value = profiles.value.filter((x) => x.id !== id)
    if (activeProfiles[p.kind] === id) {
      const next = profiles.value.find((x) => x.kind === p.kind)
      if (next) setActiveProfile(p.kind, next.id)
    }
  }

  // -- per-field reset ----------------------------------------------------------
  function fieldValue(path: FieldPath): unknown {
    const [root, ...rest] = path
    switch (root) {
      case 'connections':
        return (connections as any)[rest[0]]?.[rest[1]]
      case 'defaults':
        return (defaults as any)[rest[0]]
      case 'folders':
        return (folders as any)[rest[0]]
      case 'prompts':
        return (prompts as any)[rest[0]]
      case 'profiles':
        return (profiles.value.find((p) => p.id === rest[0]) as any)?.[rest[1]]
      case 'autoFreeVram':
        return autoFreeVram.value
      case 'agentEnabled':
        return agentEnabled.value
      case 'agentToken':
        return agentToken.value
      case 'comfyuiLauncher':
        return comfyuiLauncher.value
      default:
        return undefined
    }
  }

  function applyField(path: FieldPath, value: unknown) {
    const [root, ...rest] = path
    switch (root) {
      case 'connections': {
        const conn = (connections as any)[rest[0]]
        if (conn) conn[rest[1] as string] = value
        break
      }
      case 'defaults':
        ;(defaults as any)[rest[0]] = value
        break
      case 'folders':
        ;(folders as any)[rest[0]] = value
        break
      case 'prompts':
        ;(prompts as any)[rest[0]] = value
        break
      case 'profiles': {
        const profile = profiles.value.find((p) => p.id === rest[0]) as any
        if (profile) profile[rest[1] as string] = value
        break
      }
      case 'autoFreeVram':
        autoFreeVram.value = value as boolean
        break
      case 'agentEnabled':
        agentEnabled.value = value as boolean
        break
      case 'agentToken':
        agentToken.value = value as string
        break
      case 'comfyuiLauncher':
        comfyuiLauncher.value = value as string
        break
    }
  }

  /** True when the field already matches its shipped default (or has no default to reset to). */
  function isDefault(path: FieldPath): boolean {
    const base = deepGet(baseline.value, path)
    if (base === undefined) return true
    return JSON.stringify(fieldValue(path)) === JSON.stringify(base)
  }

  function resetField(path: FieldPath) {
    const base = deepGet(baseline.value, path)
    if (base === undefined) return
    applyField(path, cloned(base))
  }

  function resetPrompt(key: string) {
    resetField(['prompts', key])
  }

  // -- backend sync ---------------------------------------------------------------
  function snapshot(): SettingsValues {
    return {
      connections: {
        comfyui: { url: connections.comfyui.url },
        ollama: { url: connections.ollama.url },
      },
      profiles: profiles.value.map((p) => ({ ...p })),
      activeProfiles: { comfyui: activeProfiles.comfyui, ollama: activeProfiles.ollama },
      defaults: { ...defaults },
      folders: { ...folders },
      prompts: { ...prompts },
      autoFreeVram: autoFreeVram.value,
      agentEnabled: agentEnabled.value,
      agentToken: agentToken.value,
      comfyuiLauncher: comfyuiLauncher.value,
    }
  }

  function applyValues(v: SettingsValues) {
    if (Array.isArray(v.profiles) && v.profiles.length) {
      profiles.value = v.profiles.map((p) => ({
        id: p.id,
        name: p.name ?? '',
        kind: p.kind === 'ollama' ? 'ollama' : 'comfyui',
        url: p.url ?? '',
        auth: p.auth ?? '',
      }))
    }
    if (v.activeProfiles?.comfyui) activeProfiles.comfyui = v.activeProfiles.comfyui
    if (v.activeProfiles?.ollama) activeProfiles.ollama = v.activeProfiles.ollama
    syncConnectionUrls()
    if (v.connections?.comfyui?.url && !activeProfile('comfyui')) connections.comfyui.url = v.connections.comfyui.url
    if (v.connections?.ollama?.url && !activeProfile('ollama')) connections.ollama.url = v.connections.ollama.url
    if (v.defaults) Object.assign(defaults, v.defaults)
    if (v.folders) Object.assign(folders, v.folders)
    if (v.prompts) {
      for (const key of Object.keys(prompts)) delete prompts[key]
      Object.assign(prompts, v.prompts)
    }
    if (typeof v.autoFreeVram === 'boolean') autoFreeVram.value = v.autoFreeVram
    if (typeof v.agentEnabled === 'boolean') agentEnabled.value = v.agentEnabled
    if (typeof v.agentToken === 'string' && v.agentToken) agentToken.value = v.agentToken
    if (typeof v.comfyuiLauncher === 'string') comfyuiLauncher.value = v.comfyuiLauncher
  }

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  async function pushSettings() {
    if (backendState.value !== 'live') return
    saving.value = true
    try {
      await api.putSettings(snapshot())
      lastError.value = null
    } catch (err) {
      backendState.value = 'offline'
      lastError.value = err instanceof Error ? err.message : 'Failed to save settings'
      ui.toast('Backend unreachable - settings are kept in the browser until it is back.', 'warn')
    } finally {
      saving.value = false
    }
  }

  function scheduleSave(delayMs = 400) {
    if (backendState.value !== 'live') return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(pushSettings, delayMs)
  }

  /** Called once on app start (App.vue): pull settings + defaults from the backend. */
  async function syncFromBackend() {
    try {
      const [envelope, defaultsFromApi, info] = await Promise.all([
        api.getSettings(),
        api.getSettingsDefaults(),
        api.getSystemInfo(),
      ])
      baseline.value = cloned(defaultsFromApi)
      systemInfo.value = info
      backendState.value = 'live'
      lastError.value = null
      if (envelope.initialized) {
        // settings.json is authoritative
        applyValues(envelope.values)
      } else {
        // first run: push what the browser currently has into settings.json
        scheduleSave(0)
      }
    } catch (err) {
      backendState.value = 'offline'
      lastError.value = err instanceof Error ? err.message : 'Backend unreachable'
    }
  }

  /** Reset every setting to the shipped defaults (warn first - see SettingsPage). */
  async function resetAll() {
    if (backendState.value === 'live') {
      try {
        const values = await api.resetSettings()
        applyValues(values)
        baseline.value = cloned(values)
        ui.toast('All settings reset to defaults', 'success')
        return
      } catch {
        backendState.value = 'offline'
      }
    }
    applyValues(cloned(baseline.value))
    ui.toast('Backend offline - reset applied in the browser; settings.json was not changed.', 'warn')
  }

  // cache locally always; push to the backend when it is live
  watch(
    [profiles, activeProfiles, defaults, folders, prompts, autoFreeVram, agentEnabled, agentToken, comfyuiLauncher],
    () => {
      localStorage.setItem(LS_KEY, JSON.stringify(snapshot()))
      scheduleSave()
    },
    { deep: true },
  )

  // the connection URL must always mirror the active profile, no matter which
  // code path edited it (modal inputs, settings section, reset buttons)
  watch(profiles, syncConnectionUrls, { deep: true })

  syncConnectionUrls()

  return {
    // state
    connections,
    profiles,
    activeProfiles,
    defaults,
    folders,
    prompts,
    autoFreeVram,
    agentEnabled,
    agentToken,
    comfyuiLauncher,
    baseline,
    backendState,
    saving,
    systemInfo,
    lastError,
    // actions
    syncFromBackend,
    activeProfile,
    setActiveProfile,
    setProfileUrl,
    setProfileName,
    setProfileAuth,
    addProfile,
    removeProfile,
    isDefault,
    resetField,
    resetPrompt,
    resetAll,
  }
})
