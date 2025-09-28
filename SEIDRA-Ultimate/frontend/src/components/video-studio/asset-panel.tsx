'use client'

import { useCallback, type KeyboardEvent, type MouseEvent } from 'react'
import { useDropzone } from 'react-dropzone'
import { clsx } from 'clsx'

import { useVideoStudioStore } from './store'

const formatBytes = (size: number) => {
  if (size === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1)
  const value = size / 1024 ** exponent
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[exponent]}`
}

export function AssetPanel() {
  const {
    assets,
    queueUpload,
    removeAsset,
    highlightedAssetId,
    setHighlightedAsset,
    isUploading,
    uploadProgress,
    lastError,
  } =
    useVideoStudioStore((state) => ({
      assets: state.assets,
      queueUpload: state.queueUpload,
      removeAsset: state.removeAsset,
      highlightedAssetId: state.highlightedAssetId,
      setHighlightedAsset: state.setHighlightedAsset,
      isUploading: state.isUploading,
      uploadProgress: state.uploadProgress,
      lastError: state.lastError,
    }))

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      void queueUpload(acceptedFiles)
    },
    [queueUpload],
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, multiple: true })
  const dropzoneInputProps = getInputProps()

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold text-yellow-200">Assets</h3>
        <p className="text-sm text-purple-200">
          Ajoutez des vidéos, pistes audio ou images par glisser-déposer ou via l’explorateur de fichiers.
        </p>
        {lastError && <p className="mt-2 text-xs text-red-300">{lastError}</p>}
      </div>

      <div
        {...getRootProps({
          className: clsx(
            'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed p-6 text-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-yellow-300',
            isDragActive
              ? 'border-yellow-300 bg-yellow-300/10 text-yellow-200'
              : 'border-purple-500/40 bg-black/40 text-purple-200 hover:border-yellow-300 hover:text-yellow-200',
          ),
          role: 'button',
          tabIndex: 0,
          onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              dropzoneInputProps.onClick?.(event as unknown as MouseEvent<HTMLInputElement>)
            }
          },
          'aria-label': 'Ajouter des assets média',
        })}
        data-testid="asset-dropzone"
      >
        <input {...dropzoneInputProps} data-testid="asset-file-input" />
        <span className="font-semibold">Déposez vos fichiers ici</span>
        <span className="text-xs text-purple-300">MP4, MP3, WAV, PNG…</span>
        {isUploading && (
          <span className="text-xs text-yellow-200">
            Upload en cours… {Math.round(uploadProgress * 100)}%
          </span>
        )}
      </div>

      <ul className="space-y-3">
        {assets.length === 0 && (
          <li className="rounded-xl border border-purple-500/40 bg-black/40 p-4 text-sm text-purple-200">
            Aucun asset importé pour le moment.
          </li>
        )}
        {assets.map((asset) => (
          <li
            key={asset.id}
            className={clsx(
              'group flex items-center justify-between rounded-xl border border-purple-500/40 bg-black/50 p-4 text-sm text-purple-100 transition hover:border-yellow-300 hover:text-yellow-200',
              asset.status !== 'ready' && 'opacity-80',
              highlightedAssetId === asset.id && 'border-yellow-400 shadow-lg shadow-yellow-300/20',
            )}
            draggable
            onDragStart={(event) => {
              event.dataTransfer.setData('application/x-seidra-asset', asset.id)
              event.dataTransfer.effectAllowed = 'copyMove'
              setHighlightedAsset(asset.id)
            }}
            onDragEnd={() => setHighlightedAsset(null)}
            onMouseEnter={() => setHighlightedAsset(asset.id)}
            onMouseLeave={() => setHighlightedAsset(null)}
            data-testid={`asset-item-${asset.id}`}
          >
            <div className="flex flex-col">
              <span className="font-semibold">{asset.name}</span>
              <span className="text-xs text-purple-300">
                {asset.kind.toUpperCase()} · {formatBytes(asset.fileSize)} · {asset.duration.toFixed(1)}s
                {asset.mimeType ? ` · ${asset.mimeType}` : ''}
              </span>
              {asset.status !== 'ready' && (
                <span className="text-[10px] uppercase tracking-wider text-yellow-200">{asset.status}</span>
              )}
              {asset.errorMessage && (
                <span className="text-[11px] text-red-300">{asset.errorMessage}</span>
              )}
              {asset.kind === 'audio' && (
                <span className="text-[11px] text-purple-300" aria-live="polite">
                  {asset.waveformStatus === 'ready' && asset.waveformUpdatedAt
                    ? `Waveform calculée (${new Date(asset.waveformUpdatedAt).toLocaleTimeString('fr-FR', { hour12: false })})`
                    : asset.waveformStatus === 'loading'
                      ? 'Waveform en cours de calcul…'
                      : asset.waveformStatus === 'error' && asset.waveformError
                        ? `Waveform indisponible : ${asset.waveformError}`
                        : 'Waveform non calculée'}
                </span>
              )}
              {asset.downloadUrl && (
                <a
                  href={asset.downloadUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 w-fit text-[11px] font-semibold text-yellow-200 hover:underline"
                >
                  Ouvrir dans Media API
                </a>
              )}
            </div>
            <button
              type="button"
              className="rounded-full bg-red-500/80 px-3 py-1 text-xs font-semibold text-black opacity-0 transition group-hover:opacity-100 hover:bg-red-400"
              onClick={() => removeAsset(asset.id)}
              aria-label={`Supprimer ${asset.name}`}
            >
              Supprimer
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
