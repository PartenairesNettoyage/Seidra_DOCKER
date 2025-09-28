'use client'

import { useEffect } from 'react'

import { AssetPanel } from './asset-panel'
import { FramePreview } from './frame-preview'
import { JobPanel } from './job-panel'
import { Timeline } from './timeline'
import { useVideoStudioStore } from './store'

import { useWebSocketStatus } from '@/lib/websocket-context'

export function VideoStudio() {
  const { refreshJobs, applyRealtimeUpdate, jobError, isLoadingJobs, refreshProxyPreview, proxyPreview, timelineId } =
    useVideoStudioStore((state) => ({
      refreshJobs: state.refreshJobs,
      applyRealtimeUpdate: state.applyRealtimeUpdate,
      jobError: state.jobError,
      isLoadingJobs: state.isLoadingJobs,
      refreshProxyPreview: state.refreshProxyPreview,
      proxyPreview: state.proxyPreview,
      timelineId: state.timelineId,
    }))
  const { jobUpdates } = useWebSocketStatus()

  useEffect(() => {
    void refreshJobs()
    const interval = window.setInterval(() => {
      void refreshJobs()
    }, 15000)
    return () => window.clearInterval(interval)
  }, [refreshJobs])

  useEffect(() => {
    if (!timelineId) return
    void refreshProxyPreview()
  }, [timelineId, refreshProxyPreview])

  useEffect(() => {
    if (!['processing', 'loading'].includes(proxyPreview.status)) {
      return
    }
    const interval = window.setInterval(() => {
      void refreshProxyPreview()
    }, 5000)
    return () => window.clearInterval(interval)
  }, [proxyPreview.status, refreshProxyPreview])

  useEffect(() => {
    const updates = Object.values(jobUpdates)
    updates
      .filter(
        (update) =>
          update.jobType === undefined || update.jobType === 'video' || update.jobType === 'video_timeline',
      )
      .forEach((update) => applyRealtimeUpdate(update))
  }, [jobUpdates, applyRealtimeUpdate])

  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <h1 className="text-3xl font-bold text-yellow-200">Studio vidéo</h1>
        <p className="max-w-3xl text-sm text-purple-200">
          Composez vos montages en alignant clips vidéo, pistes audio et assets graphiques. L’expérience combine un store
          Zustand pour la gestion des états et une synchronisation en temps réel avec les jobs vidéo issus du backend.
        </p>
        {jobError && (
          <p className="text-xs text-red-300">
            Impossible de charger les jobs vidéo : {jobError}. L’interface reste disponible hors-ligne.
          </p>
        )}
        {isLoadingJobs && <p className="text-xs text-purple-300">Chargement des jobs…</p>}
      </header>

      <FramePreview />

      <div className="grid gap-8 lg:grid-cols-[320px,minmax(0,1fr)]">
        <AssetPanel />
        <div className="space-y-6">
          <Timeline />
          <JobPanel />
        </div>
      </div>
    </div>
  )
}
