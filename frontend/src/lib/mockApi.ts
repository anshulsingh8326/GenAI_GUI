// Mock API layer — the GUI talks ONLY to this module for job simulation.
// Connections / resources / unloads are real now (lib/api.ts via the stores);
// what remains here is the simulated job runner until real jobs land.

import type { JobRecord, Stage } from '@/types'

export function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * Simulated job runner — walks the stage list, reports progress, resolves when
 * the job is "done". Mirrors: POST /prompt -> WS progress -> history -> library.
 */
export async function runJob(
  job: JobRecord,
  onUpdate: (patch: Partial<JobRecord>) => void,
): Promise<void> {
  const stages: Stage[] = job.stages.map((s) => ({ ...s }))
  const publish = (progress: number) => {
    onUpdate({ stages: stages.map((s) => ({ ...s })), progress })
  }

  for (let i = 0; i < stages.length; i++) {
    const st = stages[i]
    st.status = 'running'
    publish(Math.round((i / stages.length) * 100))
    const started = Date.now()

    if (st.id === 'prepare') {
      await delay(450)
      st.detail = 'compose graph - upload refs'
    } else if (st.id === 'enhance') {
      await delay(1300)
      st.detail = 'rewritten by LLM (mock)'
      onUpdate({ enhancedPrompt: job.prompt + ', ultra detailed, natural lighting' })
    } else if (st.id === 'describe') {
      await delay(1100)
      st.detail = 'identity description (mock)'
    } else if (st.id === 'generate') {
      const steps = Math.max(4, job.params.steps)
      for (let p = 25; p <= 100; p += 25) {
        await delay(340)
        const step = Math.max(1, Math.round((p / 100) * steps))
        st.detail = `sampling - step ${step}/${steps}`
        publish(Math.round(((i + p / 100) / stages.length) * 100))
      }
    } else if (st.id === 'refine') {
      await delay(1400)
      st.detail = `denoise ${job.params.refine.denoise} -> ${job.params.refine.scale}px`
    } else {
      await delay(400)
      st.detail = 'saved to library'
    }

    st.status = 'done'
    st.durationMs = Date.now() - started
    publish(Math.round(((i + 1) / stages.length) * 100))
  }

  onUpdate({ status: 'done', progress: 100, stages: stages.map((s) => ({ ...s })) })
}
