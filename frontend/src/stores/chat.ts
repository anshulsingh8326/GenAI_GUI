import { reactive } from 'vue'
import { defineStore } from 'pinia'
import type { AdvancedParams, Asset, ChatMessage, ComposerState, JobRecord, Stage } from '@/types'
import { api } from '@/lib/api'
import { imageModels } from '@/lib/fixtures'
import { placeholderImage } from '@/lib/placeholder'
import { runJob } from '@/lib/mockApi'
import { useCatalogStore } from './catalog'
import { useEngineStore } from './engine'
import { useJobsStore } from './jobs'
import { useLibraryStore } from './library'
import { useSettingsStore } from './settings'
import { useUiStore } from './ui'

// One chat thread + composer per tab. Each tab keeps its own selected model,
// size/ratio, batch, LoRAs and advanced params — exactly like Higgsfield-style
// per-mode controls, but fully local.

interface Thread {
  messages: ChatMessage[]
  composer: ComposerState
}

let seq = 0
function uid(prefix: string): string {
  seq += 1
  return `${prefix}-${Date.now()}-${seq}`
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function defaultAdvanced(modelId: string): AdvancedParams {
  const model = imageModels.find((m) => m.id === modelId) ?? imageModels[0]
  const d = model.defaults ?? { steps: 12, cfg: 2.5, sampler: 'euler', scheduler: 'simple', denoise: 1.0 }
  return {
    seed: Math.floor(Math.random() * 1e12),
    lockSeed: false,
    steps: d.steps,
    cfg: d.cfg,
    sampler: d.sampler,
    scheduler: d.scheduler,
    denoise: d.denoise,
    recipe: 'krea2-freeze',
    refine: { on: true, steps: 6, cfg: 2.0, denoise: 0.45, scale: 1536 },
  }
}

function createThread(defaultModelId: string): Thread {
  return {
    messages: [],
    composer: {
      text: '',
      attachments: [],
      modelId: defaultModelId,
      ratio: '1:1',
      width: 1024,
      height: 1024,
      batch: 2,
      enhance: false,
      loras: [],
      advanced: defaultAdvanced(defaultModelId),
    },
  }
}

export const useChatStore = defineStore('chat', () => {
  const settings = useSettingsStore()
  const jobs = useJobsStore()
  const library = useLibraryStore()
  const engine = useEngineStore()
  const catalog = useCatalogStore()
  const ui = useUiStore()

  const threads = reactive<Record<string, Thread>>({})

  function thread(tab: string): Thread {
    if (!threads[tab]) {
      threads[tab] = createThread(settings.defaults.imageModel)
    }
    return threads[tab]
  }

  function resetThread(tab: string) {
    threads[tab] = createThread(settings.defaults.imageModel)
    ui.toast('New session started', 'info')
  }

  function buildStages(composer: ComposerState): Stage[] {
    const stages: Stage[] = [{ id: 'prepare', label: 'Prepare', status: 'pending' }]
    if (composer.enhance) stages.push({ id: 'enhance', label: 'Enhance prompt', status: 'pending' })
    if (composer.attachments.some((a) => a.describe)) {
      stages.push({ id: 'describe', label: 'Describe image', status: 'pending' })
    }
    stages.push({ id: 'generate', label: 'Generate', status: 'pending' })
    if (composer.advanced.refine.on) stages.push({ id: 'refine', label: 'Refine / upscale', status: 'pending' })
    stages.push({ id: 'save', label: 'Save to library', status: 'pending' })
    return stages
  }

  function makeAssets(job: JobRecord, batch: number): Asset[] {
    const model = imageModels.find((m) => m.id === job.modelId)
    return Array.from({ length: Math.max(1, batch) }, (_, i) => ({
      id: uid('a'),
      url: placeholderImage(job.prompt, i),
      label: job.prompt.split(',')[0]?.trim().slice(0, 40) || 'image',
      prompt: job.prompt,
      model: model?.name ?? job.modelName,
      seed: job.seed + i,
      createdAt: Date.now() + i,
      favorite: false,
      tags: ['t2i', job.tab],
    }))
  }

  /**
   * Job finished: the backend writes the results into the library (placeholder
   * PNGs while the engine is still mock - see backend jobs service); if it is
   * unreachable, results become session-only placeholder assets instead.
   */
  async function finalizeJob(job: JobRecord, snapshot: ComposerState) {
    const batch = Math.max(1, snapshot.batch)
    if (!job.id.startsWith('#offline')) {
      try {
        const result = await api.completeMockJob(job.id, {
          count: batch,
          width: snapshot.width,
          height: snapshot.height,
        })
        jobs.replace(result.job)
        library.add(result.assets)
        ui.toast(`Job ${job.id} done - ${result.assets.length} image${result.assets.length > 1 ? 's' : ''}`, 'success')
        return
      } catch {
        /* fall through to the session-only path */
      }
    }
    const created = makeAssets(job, batch)
    library.add(created)
    jobs.update(job.id, { status: 'done', progress: 100, resultIds: created.map((a) => a.id) })
    ui.toast(`Job ${job.id} done - ${created.length} image${created.length > 1 ? 's' : ''} (kept in this session only)`, 'warn')
  }

  /** Creates the job record (backend when online) and runs the mock pipeline in the background. */
  async function startJob(tab: string, prompt: string, snapshot: ComposerState): Promise<JobRecord> {
    const model = imageModels.find((m) => m.id === snapshot.modelId) ?? imageModels[0]
    const job = await jobs.create({
      tab,
      modelId: model.id,
      modelName: model.name,
      recipe: snapshot.advanced.recipe,
      prompt,
      seed: snapshot.advanced.lockSeed ? snapshot.advanced.seed : Math.floor(Math.random() * 1e12),
      params: clone(snapshot.advanced),
      stages: buildStages(snapshot),
    })
    engine.jobStarted()

    void (async () => {
      try {
        await runJob(job, (patch) => jobs.update(job.id, patch))
        await finalizeJob(job, snapshot)
      } catch {
        jobs.update(job.id, { status: 'error' })
        ui.toast(`Job ${job.id} failed (mock)`, 'error')
      } finally {
        engine.jobFinished()
      }
    })()

    return job
  }

  async function send(tab: string, text?: string) {
    const t = thread(tab)
    const prompt = (text ?? t.composer.text).trim()
    if (!prompt) return

    await catalog.ensureLoaded()
    const snapshot = clone(t.composer)
    const activeLoras = snapshot.loras.filter((lora) => lora.on).map((lora) => lora.id)
    const jobPrompt = catalog.promptWithTriggers(prompt, activeLoras)
    t.messages.push({
      id: uid('m'),
      role: 'user',
      text: prompt,
      attachments: snapshot.attachments,
      createdAt: Date.now(),
    })

    // clear composer input before the job starts
    t.composer.text = ''
    t.composer.attachments = []

    const job = await startJob(tab, jobPrompt, snapshot)
    t.messages.push({ id: uid('m'), role: 'assistant', jobId: job.id, createdAt: Date.now() })
  }

  /** Re-run a finished job with the same params (new seeds unless locked). */
  function rerun(jobId: string) {
    const job = jobs.byId(jobId)
    if (!job) return
    const t = thread(job.tab)
    const snapshot: ComposerState = {
      ...clone(t.composer),
      text: job.prompt,
      attachments: [],
      modelId: job.modelId,
      advanced: {
        ...clone(job.params),
        seed: job.params.lockSeed ? job.params.seed : Math.floor(Math.random() * 1e12),
      },
    }
    void startJob(job.tab, job.prompt, snapshot).then((newJob) => {
      t.messages.push({ id: uid('m'), role: 'assistant', jobId: newJob.id, createdAt: Date.now() })
    })
  }

  return { threads, thread, resetThread, send, rerun }
})
