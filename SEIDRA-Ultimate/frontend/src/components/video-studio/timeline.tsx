'use client'

import { useMemo } from 'react'
import { clsx } from 'clsx'

import { pxPerSecond, useVideoStudioStore } from './store'

const TRACK_HEIGHT = 80

type TrackProps = {
  layer: 'video' | 'audio'
  title: string
}

function Track({ layer, title }: TrackProps) {
  const { timeline, assets, createClipFromAsset, moveClip, removeClip, trimClip, highlightedAssetId } =
    useVideoStudioStore((state) => ({
      timeline: state.timeline,
      assets: state.assets,
      createClipFromAsset: state.createClipFromAsset,
      moveClip: state.moveClip,
      removeClip: state.removeClip,
      trimClip: state.trimClip,
      highlightedAssetId: state.highlightedAssetId,
    }))

  const clips = useMemo(() => timeline.filter((clip) => clip.layer === layer), [timeline, layer])

  const handleDrop: React.DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault()
    const assetId = event.dataTransfer.getData('application/x-seidra-asset')
    const clipId = event.dataTransfer.getData('application/x-seidra-clip')
    const rect = event.currentTarget.getBoundingClientRect()
    const seconds = (event.clientX - rect.left) / pxPerSecond

    if (clipId) {
      moveClip(clipId, Math.max(0, seconds))
      return
    }

    if (assetId) {
      createClipFromAsset(assetId, layer, Math.max(0, seconds))
    }
  }

  const handleDragOver: React.DragEventHandler<HTMLDivElement> = (event) => {
    if (
      event.dataTransfer.types.includes('application/x-seidra-asset') ||
      event.dataTransfer.types.includes('application/x-seidra-clip')
    ) {
      event.preventDefault()
      event.dataTransfer.dropEffect = 'move'
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs uppercase tracking-wider text-purple-200">
        <span>{title}</span>
        <span className="text-[10px] text-purple-300">
          {clips.length} clip{clips.length === 1 ? '' : 's'}
        </span>
      </div>
      <div
        className="relative overflow-hidden rounded-lg border border-purple-500/40 bg-black/50"
        style={{ height: TRACK_HEIGHT }}
        data-testid={`timeline-${layer}-track`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        role="list"
        aria-label={`Piste ${title.toLowerCase()}`}
        tabIndex={0}
        aria-dropeffect="move"
      >
        <div
          className="absolute left-0 top-0 h-full w-full bg-gradient-to-r from-purple-500/10 via-transparent to-purple-500/10"
          aria-hidden="true"
        />
        <div className="relative h-full">
          {clips.map((clip) => {
            const asset = assets.find((entry) => entry.id === clip.assetId)
            const width = Math.max(clip.duration * pxPerSecond, 24)
            const left = clip.start * pxPerSecond
            const isHighlighted = asset?.id && asset.id === highlightedAssetId
            return (
              <div
                key={clip.id}
                className={clsx(
                  'absolute top-2 flex h-[56px] cursor-grab select-none flex-col justify-between rounded-md border bg-purple-500/80 p-2 text-[11px] text-black shadow-lg transition hover:bg-yellow-300',
                  {
                    'border-yellow-400 ring-2 ring-yellow-300/60': isHighlighted,
                  },
                )}
                style={{ width, left }}
                draggable
                onDragStart={(event) => {
                  event.dataTransfer.setData('application/x-seidra-clip', clip.id)
                  event.dataTransfer.effectAllowed = 'move'
                }}
                data-testid={`timeline-clip-${clip.id}`}
                role="listitem"
                tabIndex={0}
                aria-roledescription="clip chronologique"
                aria-label={`${asset?.name ?? 'Clip'} – ${clip.duration.toFixed(1)} secondes`}
                onKeyDown={(event) => {
                  if (event.key === 'Delete' || event.key === 'Backspace') {
                    event.preventDefault()
                    removeClip(clip.id)
                  }
                  if (event.key === 'ArrowLeft') {
                    event.preventDefault()
                    moveClip(clip.id, Math.max(0, clip.start - 0.5))
                  }
                  if (event.key === 'ArrowRight') {
                    event.preventDefault()
                    moveClip(clip.id, clip.start + 0.5)
                  }
                }}
              >
                <div className="flex items-center justify-between font-semibold">
                  <span className="truncate" title={asset?.name ?? 'Clip'}>
                    {asset?.name ?? 'Clip'}
                  </span>
                  <span>{clip.duration.toFixed(1)}s</span>
                </div>
                {layer === 'audio' && asset?.waveform && asset.waveform.length > 0 && (
                  <svg
                    className="h-12 w-full text-purple-900"
                    viewBox={`0 0 ${asset.waveform.length} 100`}
                    preserveAspectRatio="none"
                    role="img"
                    aria-label={`Waveform audio de ${asset.name}`}
                  >
                    <polygon
                      fill="currentColor"
                      fillOpacity={0.2}
                      points={`${asset.waveform
                        .map((value, index) => `${index},${50 - value * 48}`)
                        .join(' ')} ${asset.waveform
                        .map((value, index) => `${index},${50 + value * 48}`)
                        .reverse()
                        .join(' ')}`}
                    />
                    <polyline
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={1.2}
                      strokeLinecap="round"
                      points={asset.waveform
                        .map((value, index) => `${index},${50 - value * 48}`)
                        .join(' ')}
                    />
                    <polyline
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={1.2}
                      strokeLinecap="round"
                      points={asset.waveform
                        .map((value, index) => `${index},${50 + value * 48}`)
                        .join(' ')}
                    />
                  </svg>
                )}
                {layer === 'audio' && asset?.waveformStatus === 'loading' && (
                  <p className="text-[10px] text-purple-900" aria-live="polite">
                    Calcul de la waveform…
                  </p>
                )}
                {layer === 'audio' && asset?.waveformStatus === 'error' && asset.waveformError && (
                  <p className="text-[10px] text-red-900" role="alert">
                    {asset.waveformError}
                  </p>
                )}
                <div className="flex items-center justify-between text-[10px] uppercase tracking-wide">
                  <button
                    type="button"
                    className="rounded bg-black/40 px-2 py-0.5 text-[10px] font-medium text-yellow-200 hover:bg-black/60"
                    onClick={() => trimClip(clip.id, clip.duration - 1)}
                    >
                    Trim -1s
                  </button>
                  <button
                    type="button"
                    className="rounded bg-black/40 px-2 py-0.5 text-[10px] font-medium text-yellow-200 hover:bg-black/60"
                    onClick={() => trimClip(clip.id, clip.duration + 1)}
                  >
                    Trim +1s
                  </button>
                  <button
                    type="button"
                    className="rounded bg-red-500/80 px-2 py-0.5 text-[10px] font-semibold text-black hover:bg-red-400"
                    onClick={() => removeClip(clip.id)}
                  >
                    Remove
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export function Timeline() {
  const {
    saveTimeline,
    queueTimelineRender,
    isSavingTimeline,
    saveError,
    lastSavedAt,
    isQueueingRender,
    queueError,
    timelineName,
    timelineId,
    requestProxyPreview,
    proxyPreview,
  } = useVideoStudioStore((state) => ({
    saveTimeline: state.saveTimeline,
    queueTimelineRender: state.queueTimelineRender,
    isSavingTimeline: state.isSavingTimeline,
    saveError: state.saveError,
    lastSavedAt: state.lastSavedAt,
    isQueueingRender: state.isQueueingRender,
    queueError: state.queueError,
    timelineName: state.timelineName,
    timelineId: state.timelineId,
    requestProxyPreview: state.requestProxyPreview,
    proxyPreview: state.proxyPreview,
  }))

  const handleSave = () => {
    void saveTimeline()
  }

  const handleRender = () => {
    void queueTimelineRender()
  }

  const handleProxy = () => {
    void requestProxyPreview()
  }

  const savedLabel = lastSavedAt
    ? new Date(lastSavedAt).toLocaleString('fr-FR', { hour12: false })
    : null

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 rounded-2xl border border-purple-500/40 bg-black/40 p-4 shadow-inner md:flex-row md:items-end md:justify-between">
        <div>
          <h3 className="text-lg font-semibold text-yellow-200">Timeline – {timelineName}</h3>
          <p className="text-sm text-purple-200">
            Glissez-déposez des assets sur les pistes vidéo et audio. Faites glisser les clips pour les repositionner.
          </p>
          <div className="mt-2 space-y-1 text-xs text-purple-300">
            {timelineId && <div>ID backend : {timelineId}</div>}
            {savedLabel && <div>Dernière sauvegarde : {savedLabel}</div>}
          </div>
          {saveError && <p className="mt-2 text-xs text-red-300">{saveError}</p>}
          {queueError && <p className="mt-1 text-xs text-red-300">{queueError}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleProxy}
            className="rounded-lg bg-purple-500/30 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-yellow-200 transition hover:bg-purple-400/60 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={proxyPreview.status === 'loading' || proxyPreview.status === 'processing'}
          >
            {proxyPreview.status === 'processing'
              ? 'Proxy en cours…'
              : proxyPreview.status === 'loading'
                ? 'Préparation du proxy…'
                : 'Générer un proxy'}
          </button>
          {proxyPreview.url && (
            <a
              href={proxyPreview.url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-lg border border-yellow-300/60 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-yellow-200 transition hover:bg-yellow-300/10"
            >
              Ouvrir le proxy
            </a>
          )}
          <button
            type="button"
            onClick={handleSave}
            className="rounded-lg bg-purple-500/40 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-yellow-200 transition hover:bg-purple-400/60 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isSavingTimeline}
          >
            {isSavingTimeline ? 'Sauvegarde…' : 'Sauvegarder la timeline'}
          </button>
          <button
            type="button"
            onClick={handleRender}
            className="rounded-lg bg-yellow-300 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-black transition hover:bg-yellow-200 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isQueueingRender || isSavingTimeline}
          >
            {isQueueingRender ? 'Rendu en cours…' : 'Lancer un rendu'}
          </button>
        </div>
      </div>
      <div className="rounded-lg border border-purple-500/40 bg-black/30 p-3 text-xs text-purple-200" role="status" aria-live="polite">
        {proxyPreview.status === 'ready' && proxyPreview.url && (
          <span>
            Proxy généré. Dernière mise à jour le {proxyPreview.updatedAt
              ? new Date(proxyPreview.updatedAt).toLocaleString('fr-FR', { hour12: false })
              : '—'}.
          </span>
        )}
        {proxyPreview.status === 'processing' && <span>Génération du proxy en cours…</span>}
        {proxyPreview.status === 'loading' && <span>Préparation du proxy…</span>}
        {proxyPreview.status === 'error' && proxyPreview.errorMessage && (
          <span className="text-red-300">Erreur proxy : {proxyPreview.errorMessage}</span>
        )}
        {proxyPreview.status === 'idle' && <span>Générez un proxy pour prévisualiser la timeline en basse résolution.</span>}
      </div>
      <Track layer="video" title="Piste vidéo" />
      <Track layer="audio" title="Piste audio" />
    </div>
  )
}
