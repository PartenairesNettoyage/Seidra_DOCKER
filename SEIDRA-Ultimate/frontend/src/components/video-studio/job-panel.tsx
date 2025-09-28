'use client'

import { formatDistanceToNow } from 'date-fns'

import { ProgressBar } from '@/components/ui/progress-bar'

import { useVideoStudioStore } from './store'

export function JobPanel() {
  const { videoJobs, jobError, isLoadingJobs } = useVideoStudioStore((state) => ({
    videoJobs: state.videoJobs,
    jobError: state.jobError,
    isLoadingJobs: state.isLoadingJobs,
  }))

  return (
    <div className="rounded-2xl border border-purple-500/40 bg-black/30 p-6 text-purple-100 shadow-lg">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-yellow-200">Jobs vidéo</h3>
          <p className="text-sm text-purple-300">
            Synchronisation automatique avec les jobs générés par le pipeline vidéo.
          </p>
        </div>
        <span className="rounded-full border border-purple-500/40 px-3 py-1 text-xs text-purple-200">
          {videoJobs.length} job{videoJobs.length === 1 ? '' : 's'} suivis
        </span>
      </div>

      {jobError && (
        <p className="mb-3 text-xs text-red-300" role="alert">
          {jobError}
        </p>
      )}
      {isLoadingJobs && (
        <p className="mb-3 text-xs text-purple-300" role="status" aria-live="polite">
          Chargement des jobs…
        </p>
      )}

      <div className="space-y-4" role="list" aria-live="polite">
        {videoJobs.length === 0 && !isLoadingJobs && (
          <p className="text-sm text-purple-200">
            Aucun job vidéo actif pour le moment. Les nouveaux jobs apparaîtront ici automatiquement.
          </p>
        )}
        {videoJobs.map((job) => (
          <div
            key={job.jobId}
            className="rounded-xl border border-purple-500/30 bg-black/40 p-4 shadow-inner"
            role="listitem"
            aria-label={`Job ${job.jobId} (${job.status})`}
          >
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-sm">
              <div className="flex items-center gap-2">
                <span className="rounded bg-purple-500/40 px-2 py-1 text-xs uppercase tracking-wider text-yellow-200">
                  {job.status}
                </span>
                <span className="font-semibold text-purple-100">{job.jobId}</span>
                <span className="text-[11px] uppercase tracking-wide text-purple-300">{job.jobType}</span>
              </div>
              <div className="text-xs text-purple-300">
                {job.updatedAt
                  ? formatDistanceToNow(new Date(job.updatedAt), { addSuffix: true })
                  : 'Mise à jour en attente'}
              </div>
            </div>
            <ProgressBar value={job.progress * 100} status={job.status === 'completed' ? 'success' : undefined} />
            <div className="mt-3 flex flex-col gap-1 text-xs text-purple-300">
              <span>Assets générés : {job.assetCount}</span>
              {job.createdAt && (
                <span>Créé {formatDistanceToNow(new Date(job.createdAt), { addSuffix: true })}</span>
              )}
              {job.statusMessage && <span className="text-purple-200">{job.statusMessage}</span>}
              {job.errorMessage && <span className="text-red-300">{job.errorMessage}</span>}
              {job.resultUrls && job.resultUrls.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {job.resultUrls.map((url) => (
                    <a
                      key={url}
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="rounded bg-yellow-300/10 px-2 py-1 text-[11px] font-semibold text-yellow-200 hover:bg-yellow-300/20"
                      aria-label={`Voir le média du job ${job.jobId}`}
                    >
                      Voir le média
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
