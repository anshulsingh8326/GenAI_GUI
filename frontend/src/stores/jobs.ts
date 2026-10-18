import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { JobRecord, NewJobDraft } from '@/types'
import { api } from '@/lib/api'

// Backend-first job store. Records live in SQLite through /api/jobs and ids are
// issued there too (#142, #143, ...). Execution is still the mock runner in the
// chat store - every progress/stage patch it publishes is persisted through
// update() here, so job history survives reloads. Jobs started while the
// backend is offline (id "#offline-n") stay in this session only.

export const useJobsStore = defineStore('jobs', () => {
  const jobs = ref<JobRecord[]>([])
  let offlineSeq = 0

  function byId(id: string): JobRecord | undefined {
    return jobs.value.find((j) => j.id === id)
  }

  /** Replace the cache with the backend history; failures keep session jobs. */
  async function syncFromBackend(): Promise<void> {
    try {
      jobs.value = await api.getJobs(80)
    } catch {
      /* backend offline - keep whatever we have */
    }
  }

  /** Create a job record (backend assigns id/createdAt). Falls back to a session-only record. */
  async function create(draft: NewJobDraft): Promise<JobRecord> {
    try {
      const job = await api.createJob(draft)
      jobs.value.unshift(job)
      return job
    } catch {
      offlineSeq += 1
      const job: JobRecord = {
        ...draft,
        id: `#offline-${offlineSeq}`,
        createdAt: Date.now(),
        status: 'running',
        progress: 0,
        resultIds: [],
      }
      jobs.value.unshift(job)
      return job
    }
  }

  /** Patch a job locally and persist it (fire-and-forget; offline ids skip the server). */
  function update(id: string, patch: Partial<JobRecord>) {
    const job = byId(id)
    if (job) Object.assign(job, patch)
    if (!id.startsWith('#offline')) {
      void api.updateJob(id, patch).catch(() => {
        /* offline: local state already reflects the patch */
      })
    }
  }

  /** Replace a job with the authoritative server copy (e.g. after mock-complete). */
  function replace(job: JobRecord) {
    const index = jobs.value.findIndex((j) => j.id === job.id)
    if (index >= 0) jobs.value[index] = job
    else jobs.value.unshift(job)
  }

  return { jobs, byId, syncFromBackend, create, update, replace }
})
