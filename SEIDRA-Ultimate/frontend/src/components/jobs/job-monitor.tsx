'use client'

import Image from 'next/image'
import { FormEvent, useEffect, useMemo, useState } from 'react'
import { toast } from 'react-hot-toast'

import { ProgressBar } from '@/components/ui/progress-bar'
import { useJobHistory, usePersonas } from '@/lib/hooks'
import { extractJobMessages, mergeJobUpdates } from '@/lib/realtime-utils'
import { useWebSocketStatus } from '@/lib/websocket-context'

export function JobMonitor() {
  const { personas } = usePersonas()
  const {
    jobs,
    total,
    stats,
    filters,
    isLoading,
    error,
    applyFilters,
    loadMore,
    refresh,
    cancelJob,
    retryJob,
    setJobs,
  } = useJobHistory(24)

  const { jobUpdates } = useWebSocketStatus()
  const jobMessages = useMemo(() => extractJobMessages(jobUpdates), [jobUpdates])

  useEffect(() => {
    const updates = Object.values(jobUpdates)
    if (updates.length === 0) return
    setJobs((previous) => mergeJobUpdates(previous, updates))
  }, [jobUpdates, setJobs])

  const [statusFilter, setStatusFilter] = useState((filters.status as string | undefined) ?? '')
  const [personaFilter, setPersonaFilter] = useState(
    filters.persona_id ? String(filters.persona_id) : '',
  )
  const [search, setSearch] = useState((filters.search as string | undefined) ?? '')

  const handleFilterSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    applyFilters({
      status: statusFilter || undefined,
      persona_id: personaFilter ? Number(personaFilter) : undefined,
      search: search || undefined,
      offset: 0,
    })
  }

  const resetFilters = () => {
    setStatusFilter('')
    setPersonaFilter('')
    setSearch('')
    applyFilters({ status: undefined, persona_id: undefined, search: undefined, offset: 0 })
  }

  useEffect(() => {
    const updates = Object.values(jobUpdates)
    if (updates.length === 0) return
    setJobs((previous) => mergeJobUpdates(previous, updates))
  }, [jobUpdates])

  return (
    <section className="space-y-6">
      <div className="rounded-2xl border border-purple-500/30 bg-black/40 p-6 text-purple-100 shadow-xl">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-yellow-200">Job history</h2>
            <p className="text-xs text-purple-300">{total} jobs tracked across all personas.</p>
            {error && <p className="text-xs text-red-400">{error}</p>}
          </div>
          <button
            type="button"
            className="rounded border border-purple-500/40 px-3 py-1 text-xs text-purple-200 hover:border-yellow-300 hover:text-yellow-200"
            onClick={() => refresh()}
          >
            Refresh
          </button>
        </div>

        <form className="grid gap-4 lg:grid-cols-[repeat(4,minmax(0,1fr))]" onSubmit={handleFilterSubmit}>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search prompts"
            className="rounded-lg border border-purple-500/40 bg-black/60 p-2 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
          />
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="rounded-lg border border-purple-500/40 bg-black/60 p-2 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
          >
            <option value="">Any status</option>
            <option value="queued">Queued</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <select
            value={personaFilter}
            onChange={(event) => setPersonaFilter(event.target.value)}
            className="rounded-lg border border-purple-500/40 bg-black/60 p-2 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
          >
            <option value="">All personas</option>
            {personas.map((persona) => (
              <option key={persona.id} value={persona.id}>
                {persona.name}
              </option>
            ))}
          </select>
          <div className="flex items-center gap-2">
            <button
              type="submit"
              className="flex-1 rounded-lg bg-gradient-to-r from-purple-600 to-yellow-400 px-3 py-2 text-xs font-semibold text-black shadow-lg hover:opacity-90"
            >
              Apply
            </button>
            <button
              type="button"
              onClick={resetFilters}
              className="rounded-lg border border-purple-500/40 px-3 py-2 text-xs text-purple-200 hover:border-yellow-300 hover:text-yellow-200"
            >
              Reset
            </button>
          </div>
        </form>
      </div>

      {stats && (
        <div className="rounded-2xl border border-purple-500/30 bg-black/30 p-4 text-sm text-purple-200">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-yellow-200">Summary</h3>
          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <p className="text-xs text-purple-300">Completed jobs</p>
              <p className="text-lg font-semibold text-yellow-200">{stats.by_status?.completed ?? 0}</p>
            </div>
            <div>
              <p className="text-xs text-purple-300">Failures</p>
              <p className="text-lg font-semibold text-yellow-200">{stats.by_status?.failed ?? 0}</p>
            </div>
            <div>
              <p className="text-xs text-purple-300">Average duration</p>
              <p className="text-lg font-semibold text-yellow-200">
                {stats.average_duration ? `${stats.average_duration.toFixed(1)}s` : 'n/a'}
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="rounded-2xl border border-purple-500/30 bg-black/30 p-6 text-purple-100 shadow-xl">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {jobs.length === 0 && !isLoading && (
            <p className="text-sm text-purple-300">No jobs match the current filters.</p>
          )}
          {jobs.map((job) => {
            const images = job.result_images ?? []
            return (
              <article key={job.job_id} className="flex flex-col gap-3 rounded-xl border border-purple-500/30 bg-black/40 p-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-semibold uppercase tracking-wide text-yellow-200">
                    {job.status.replace(/[_-]+/g, ' ')}
                  </span>
                  <span className="text-xs text-purple-300">{new Date(job.created_at).toLocaleString()}</span>
                </div>
                <p className="text-xs text-purple-300 line-clamp-2">{job.prompt}</p>
                <ProgressBar value={job.progress ?? 0} status={job.status} />
                {jobMessages[job.job_id] && (
                  <p className="text-xs text-purple-300">{jobMessages[job.job_id]}</p>
                )}
                <div className="flex flex-wrap gap-2 text-[10px] text-purple-300">
                  <span className="rounded border border-purple-500/40 px-2 py-0.5">{job.model_name}</span>
                  {job.persona_id && (
                    <span className="rounded border border-purple-500/40 px-2 py-0.5">
                      Persona #{job.persona_id}
                    </span>
                  )}
                </div>
                {images.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {images.map((image) => (
                      <Image
                        key={image}
                        src={`/media/${image.split('/').pop() ?? image}`}
                        alt="Result"
                        width={80}
                        height={80}
                        className="h-20 w-20 rounded border border-purple-500/40 object-cover"
                        unoptimized
                      />
                    ))}
                  </div>
                )}
                <div className="mt-auto flex flex-wrap items-center gap-2 text-xs text-purple-200">
                  <button
                    type="button"
                    className="rounded border border-purple-500/40 px-3 py-1 hover:border-yellow-300 hover:text-yellow-200"
                    onClick={() =>
                      toast.promise(cancelJob(job.job_id), {
                        loading: 'Cancelling…',
                        success: 'Job cancelled',
                        error: 'Failed to cancel job',
                      })
                    }
                    disabled={['completed', 'failed', 'cancelled'].includes(job.status)}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="rounded border border-purple-500/40 px-3 py-1 hover:border-yellow-300 hover:text-yellow-200"
                    onClick={() =>
                      toast.promise(retryJob(job.job_id), {
                        loading: 'Retrying…',
                        success: 'Job retried',
                        error: 'Failed to retry job',
                      })
                    }
                  >
                    Retry
                  </button>
                </div>
              </article>
            )
          })}
        </div>

        {jobs.length < total && (
          <div className="mt-6 flex justify-center">
            <button
              type="button"
              onClick={() => loadMore()}
              className="rounded-lg border border-purple-500/40 px-4 py-2 text-sm text-purple-200 hover:border-yellow-300 hover:text-yellow-200"
            >
              Load more
            </button>
          </div>
        )}
      </div>
    </section>
  )
}
