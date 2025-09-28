'use client'

import { useMemo } from 'react'
import { clsx } from 'clsx'

import { useVideoStudioStore } from './store'

const formatTimecode = (frame: number, frameRate: number) => {
  const totalSeconds = frame / frameRate
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = Math.floor(totalSeconds % 60)
  const frames = Math.floor(frame % frameRate)
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}:${String(frames).padStart(2, '0')}`
}

export function FramePreview() {
  const { timeline, frameRate, selectedFrame, setSelectedFrame, proxyPreview } = useVideoStudioStore((state) => ({
    timeline: state.timeline,
    frameRate: state.frameRate,
    selectedFrame: state.selectedFrame,
    setSelectedFrame: state.setSelectedFrame,
    proxyPreview: state.proxyPreview,
  }))

  const totalDuration = useMemo(() => {
    const max = timeline.reduce((duration, clip) => Math.max(duration, clip.start + clip.duration), 0)
    return Math.max(max, 10)
  }, [timeline])

  const maxFrame = Math.max(Math.floor(totalDuration * frameRate), frameRate * 10)
  const timecode = formatTimecode(selectedFrame, frameRate)
  const seconds = (selectedFrame / frameRate).toFixed(2)

  return (
    <div className="rounded-2xl border border-purple-500/40 bg-black/40 p-6 text-purple-100 shadow-xl">
      <div className="mb-6 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-xl font-semibold text-yellow-200">Prévisualisation frame-by-frame</h2>
          <p className="text-sm text-purple-200">
            Ajustez la tête de lecture pour explorer votre montage image par image.
          </p>
        </div>
        <div className="text-right text-xs text-purple-300">
          <div>
            Frame :{' '}
            <span className="font-semibold text-yellow-200" data-testid="frame-value">
              {selectedFrame}
            </span>
          </div>
          <div>
            Temps :{' '}
            <span className="font-semibold text-yellow-200" data-testid="time-seconds">
              {seconds}s
            </span>
          </div>
          <div>
            Timecode :{' '}
            <span className="font-semibold text-yellow-200" data-testid="timecode-value">
              {timecode}
            </span>
          </div>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_260px]">
        <div
          className="relative flex aspect-video items-center justify-center overflow-hidden rounded-xl border border-purple-500/40 bg-gradient-to-br from-purple-900/60 via-black/40 to-black/80"
          aria-live="polite"
        >
          {proxyPreview.status === 'ready' && proxyPreview.url ? (
            <video
              key={proxyPreview.url}
              src={proxyPreview.url}
              className="h-full w-full object-cover"
              controls
              muted
              loop
              playsInline
              aria-label="Prévisualisation proxy de la timeline"
              data-testid="proxy-preview-video"
            />
          ) : (
            <>
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(250,204,21,0.25),transparent_65%)]" aria-hidden="true" />
              <div className="relative flex h-24 w-24 items-center justify-center rounded-full border border-yellow-300/60 bg-black/50 text-sm font-semibold text-yellow-200">
                Frame {selectedFrame}
              </div>
            </>
          )}
          <div
            className={clsx(
              'absolute left-4 top-4 rounded-full px-3 py-1 text-xs font-semibold backdrop-blur',
              {
                'bg-yellow-300/20 text-yellow-200': proxyPreview.status === 'processing' || proxyPreview.status === 'loading',
                'bg-emerald-400/20 text-emerald-200': proxyPreview.status === 'ready',
                'bg-red-500/20 text-red-200': proxyPreview.status === 'error',
                'bg-purple-500/20 text-purple-100': proxyPreview.status === 'idle',
              },
            )}
          >
            {proxyPreview.status === 'ready'
              ? 'Proxy prêt'
              : proxyPreview.status === 'processing'
                ? 'Proxy en cours'
                : proxyPreview.status === 'loading'
                  ? 'Proxy en préparation'
                  : proxyPreview.status === 'error'
                    ? 'Proxy indisponible'
                    : 'Proxy non généré'}
          </div>
        </div>
        <div className="space-y-3">
          <label className="flex flex-col gap-2 text-sm text-purple-200">
            Position de lecture
            <input
              type="range"
              min={0}
              max={maxFrame}
              value={selectedFrame}
              onChange={(event) => setSelectedFrame(Number(event.target.value))}
              className="h-2 w-full cursor-pointer appearance-none rounded-full bg-purple-500/30 accent-yellow-300"
              data-testid="frame-slider"
            />
          </label>
          <div className="flex items-center justify-between text-xs text-purple-300">
            <span>00:00:00</span>
            <span>{formatTimecode(maxFrame, frameRate)}</span>
          </div>
          <p className="text-xs text-purple-200">
            La prévisualisation est générée à {frameRate} fps. Utilisez la timeline pour positionner précisément vos clips et
            déclencher un rendu proxy pour visualiser le montage en basse résolution.
          </p>
          {proxyPreview.status === 'processing' && (
            <p className="text-xs text-yellow-200" aria-live="polite">
              Génération du proxy en cours…
            </p>
          )}
          {proxyPreview.status === 'loading' && (
            <p className="text-xs text-purple-200" aria-live="polite">
              Préparation de la prévisualisation proxy…
            </p>
          )}
          {proxyPreview.errorMessage && (
            <p className="text-xs text-red-300" role="alert">
              {proxyPreview.errorMessage}
            </p>
          )}
          {proxyPreview.updatedAt && (
            <p className="text-[11px] text-purple-300">
              Dernière mise à jour proxy : {new Date(proxyPreview.updatedAt).toLocaleString('fr-FR', { hour12: false })}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
