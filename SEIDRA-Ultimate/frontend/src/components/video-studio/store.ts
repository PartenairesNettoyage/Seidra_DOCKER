'use client'

import { create } from 'zustand'
import { v4 as uuid } from 'uuid'

import {
  apiClient,
  type GenerationJobResponse,
  type JobItem,
  type VideoAssetUploadResponse,
  type VideoProxyPreviewResponse,
  type VideoTimelinePayload,
  type VideoTimelineResponse,
} from '@/lib/api-client'
import type { JobRealtimeUpdate } from '@/lib/websocket-context'

export type VideoAssetType = 'video' | 'audio' | 'image'

export type WaveformStatus = 'idle' | 'loading' | 'ready' | 'error'

export type VideoAsset = {
  id: string
  name: string
  kind: VideoAssetType
  duration: number
  url?: string
  downloadUrl?: string | null
  previewUrl?: string | null
  waveform?: number[]
  waveformStatus?: WaveformStatus
  waveformUpdatedAt?: string | null
  waveformError?: string | null
  status: 'uploading' | 'ready' | 'error'
  fileSize: number
  jobId?: string | null
  createdAt: string
  mimeType?: string | null
  errorMessage?: string | null
}

export type TimelineClip = {
  id: string
  assetId: string
  start: number
  duration: number
  layer: 'video' | 'audio'
}

export type VideoJobState = {
  jobId: string
  status: string
  progress: number
  assetCount: number
  createdAt?: string
  updatedAt?: string
  jobType: string
  statusMessage?: string | null
  resultUrls?: string[]
  errorMessage?: string | null
}

export type ProxyPreviewState = {
  status: 'idle' | 'loading' | 'processing' | 'ready' | 'error'
  url: string | null
  jobId: string | null
  requestedAt: string | null
  updatedAt: string | null
  errorMessage: string | null
  message: string | null
}

export type VideoStudioState = {
  assets: VideoAsset[]
  timeline: TimelineClip[]
  videoJobs: VideoJobState[]
  selectedFrame: number
  frameRate: number
  isUploading: boolean
  uploadProgress: number
  highlightedAssetId: string | null
  timelineId: string | null
  timelineName: string
  timelineDescription: string
  lastSavedAt: string | null
  isSavingTimeline: boolean
  saveError: string | null
  isQueueingRender: boolean
  queueError: string | null
  isLoadingJobs: boolean
  jobError: string | null
  lastError: string | null
  proxyPreview: ProxyPreviewState
  queueUpload: (files: File[]) => Promise<VideoAsset[]>
  removeAsset: (assetId: string) => void
  createClipFromAsset: (assetId: string, layer: 'video' | 'audio', start?: number) => void
  moveClip: (clipId: string, start: number) => void
  trimClip: (clipId: string, duration: number) => void
  removeClip: (clipId: string) => void
  setHighlightedAsset: (assetId: string | null) => void
  setSelectedFrame: (frame: number) => void
  syncJobs: (jobs: JobItem[]) => void
  applyRealtimeUpdate: (update: JobRealtimeUpdate) => void
  saveTimeline: (options?: { name?: string; description?: string }) => Promise<VideoTimelineResponse | null>
  queueTimelineRender: () => Promise<GenerationJobResponse | null>
  refreshJobs: () => Promise<void>
  fetchWaveform: (assetId: string, existing?: number[] | null) => Promise<number[] | null>
  requestProxyPreview: (options?: { force?: boolean }) => Promise<VideoProxyPreviewResponse | null>
  refreshProxyPreview: () => Promise<VideoProxyPreviewResponse | null>
  reset: () => void
}

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max)

const determineKind = (file: File): VideoAssetType => {
  if (file.type.startsWith('audio/')) return 'audio'
  if (file.type.startsWith('video/')) return 'video'
  return 'image'
}

const defaultDuration = (file: File): number => {
  const kind = determineKind(file)
  if (kind === 'audio') return 30
  if (kind === 'video') return 12
  return 5
}

const buildAsset = (file: File): VideoAsset => {
  const id = uuid()
  const createdAt = new Date().toISOString()
  const duration = defaultDuration(file)
  const kind = determineKind(file)
  const previewUrl = typeof window !== 'undefined' ? URL.createObjectURL(file) : undefined
  return {
    id,
    name: file.name,
    kind,
    duration,
    fileSize: file.size,
    status: 'uploading',
    waveform: undefined,
    waveformStatus: kind === 'audio' ? 'idle' : 'idle',
    waveformUpdatedAt: null,
    waveformError: null,
    url: previewUrl,
    previewUrl,
    downloadUrl: null,
    jobId: null,
    createdAt,
    mimeType: file.type || null,
    errorMessage: null,
  }
}

const findLayerEnd = (timeline: TimelineClip[], layer: 'video' | 'audio') => {
  return timeline
    .filter((clip) => clip.layer === layer)
    .reduce((max, clip) => Math.max(max, clip.start + clip.duration), 0)
}

const computeTimelineDuration = (timeline: TimelineClip[]) =>
  timeline.reduce((max, clip) => Math.max(max, clip.start + clip.duration), 0)

const toTimelinePayload = (state: VideoStudioState, overrides?: { name?: string; description?: string }): VideoTimelinePayload => {
  const assets = state.assets.map((asset) => ({
    id: asset.id,
    name: asset.name,
    kind: asset.kind,
    duration: asset.duration,
    status: asset.status,
    url: asset.url ?? undefined,
    download_url: asset.downloadUrl ?? undefined,
    waveform: asset.waveform,
    file_size: asset.fileSize,
    job_id: asset.jobId ?? null,
    created_at: asset.createdAt,
    mime_type: asset.mimeType ?? null,
  }))
  const clips = state.timeline.map((clip) => ({
    id: clip.id,
    asset_id: clip.assetId,
    start: clip.start,
    duration: clip.duration,
    layer: clip.layer,
  }))

  return {
    id: state.timelineId ?? undefined,
    name: overrides?.name ?? state.timelineName ?? 'Montage vidéo',
    description: overrides?.description ?? state.timelineDescription ?? '',
    frame_rate: state.frameRate,
    total_duration: computeTimelineDuration(state.timeline),
    assets,
    clips,
  }
}

export const proxyPreviewInitialState: ProxyPreviewState = {
  status: 'idle',
  url: null,
  jobId: null,
  requestedAt: null,
  updatedAt: null,
  errorMessage: null,
  message: null,
}

const cloneProxyPreview = (): ProxyPreviewState => ({ ...proxyPreviewInitialState })

const computeWaveformFromAudio = async (audioUrl: string, samplePoints = 96): Promise<number[]> => {
  if (typeof window === 'undefined') {
    throw new Error('AudioContext indisponible côté serveur')
  }
  const response = await fetch(audioUrl)
  if (!response.ok) {
    throw new Error(`Impossible de récupérer l’audio (${response.status})`)
  }
  const arrayBuffer = await response.arrayBuffer()
  const AudioCtor: typeof AudioContext | undefined =
    (window as unknown as { AudioContext?: typeof AudioContext }).AudioContext ||
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!AudioCtor) {
    throw new Error('AudioContext non supporté par le navigateur')
  }
  const audioContext = new AudioCtor()
  try {
    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer.slice(0))
    const channelData = audioBuffer.numberOfChannels > 0 ? audioBuffer.getChannelData(0) : new Float32Array()
    if (channelData.length === 0) {
      throw new Error('Flux audio vide')
    }
    const step = Math.max(1, Math.floor(channelData.length / samplePoints))
    const waveform: number[] = []
    for (let index = 0; index < samplePoints; index += 1) {
      const start = index * step
      let peak = 0
      for (let offset = 0; offset < step && start + offset < channelData.length; offset += 1) {
        peak = Math.max(peak, Math.abs(channelData[start + offset]))
      }
      waveform.push(Number(peak.toFixed(3)))
    }
    return waveform
  } finally {
    void audioContext.close().catch(() => undefined)
  }
}

const mapProxyStatus = (status?: string | null): ProxyPreviewState['status'] => {
  const normalised = (status ?? '').toLowerCase()
  if (['ready', 'completed', 'done', 'success'].includes(normalised)) {
    return 'ready'
  }
  if (['processing', 'running', 'queued', 'rendering', 'pending'].includes(normalised)) {
    return 'processing'
  }
  if (['failed', 'error'].includes(normalised)) {
    return 'error'
  }
  if (['loading', 'fetching'].includes(normalised)) {
    return 'loading'
  }
  return 'idle'
}

export const useVideoStudioStore = create<VideoStudioState>((set, get) => ({
  assets: [],
  timeline: [],
  videoJobs: [],
  selectedFrame: 0,
  frameRate: 24,
  isUploading: false,
  uploadProgress: 0,
  highlightedAssetId: null,
  timelineId: null,
  timelineName: 'Montage vidéo',
  timelineDescription: '',
  lastSavedAt: null,
  isSavingTimeline: false,
  saveError: null,
  isQueueingRender: false,
  queueError: null,
  isLoadingJobs: false,
  jobError: null,
  lastError: null,
  proxyPreview: cloneProxyPreview(),
  async queueUpload(files) {
    if (files.length === 0) return []

    const entries = files.map((file) => ({ file, asset: buildAsset(file) }))
    set((state) => ({
      assets: [...state.assets, ...entries.map((entry) => entry.asset)],
      isUploading: true,
      uploadProgress: 0,
      lastError: null,
    }))

    for (let index = 0; index < entries.length; index += 1) {
      const { file, asset } = entries[index]
      try {
        const response: VideoAssetUploadResponse = await apiClient.uploadVideoAsset(file, {
          duration: asset.duration,
          kind: asset.kind,
        })
        const maybeWaveform =
          typeof (response as Record<string, unknown>).waveform !== 'undefined' &&
          Array.isArray((response as Record<string, unknown>).waveform)
            ? ((response as unknown as { waveform: number[] }).waveform ?? [])
            : undefined

        set((state) => ({
          assets: state.assets.map((item) =>
            item.id === asset.id
              ? {
                  ...item,
                  status: 'ready',
                  url: response.url,
                  downloadUrl: response.download_url,
                  fileSize: response.file_size,
                  createdAt: response.created_at,
                  duration: response.duration,
                  mimeType: response.mime_type,
                  errorMessage: null,
                  waveform: maybeWaveform && maybeWaveform.length > 0 ? maybeWaveform : item.waveform,
                  waveformStatus:
                    item.kind === 'audio'
                      ? maybeWaveform && maybeWaveform.length > 0
                        ? 'ready'
                        : 'loading'
                      : 'idle',
                  waveformUpdatedAt:
                    item.kind === 'audio' && maybeWaveform && maybeWaveform.length > 0
                      ? new Date().toISOString()
                      : item.waveformUpdatedAt ?? null,
                  waveformError: null,
                }
              : item,
          ),
          uploadProgress: (index + 1) / entries.length,
          isUploading: index + 1 < entries.length,
        }))

        if (asset.kind === 'audio') {
          void get().fetchWaveform(asset.id, maybeWaveform ?? null)
        }
      } catch (error) {
        const message = (error as Error).message ?? 'Upload échoué'
        set((state) => ({
          assets: state.assets.map((item) =>
            item.id === asset.id ? { ...item, status: 'error', errorMessage: message } : item,
          ),
          uploadProgress: (index + 1) / entries.length,
          isUploading: index + 1 < entries.length,
          lastError: message,
        }))
      }
    }

    set({ uploadProgress: 1, isUploading: false })
    const assetIds = entries.map((entry) => entry.asset.id)
    return get().assets.filter((asset) => assetIds.includes(asset.id))
  },
  removeAsset(assetId) {
    set((state) => {
      const asset = state.assets.find((entry) => entry.id === assetId)
      if (asset?.previewUrl) {
        URL.revokeObjectURL(asset.previewUrl)
      }
      return {
        assets: state.assets.filter((entry) => entry.id !== assetId),
        timeline: state.timeline.filter((clip) => clip.assetId !== assetId),
        highlightedAssetId: state.highlightedAssetId === assetId ? null : state.highlightedAssetId,
      }
    })
  },
  createClipFromAsset(assetId, layer, start) {
    const asset = get().assets.find((entry) => entry.id === assetId)
    if (!asset || asset.status !== 'ready') return

    const fallbackStart = findLayerEnd(get().timeline, layer)
    const clip: TimelineClip = {
      id: uuid(),
      assetId,
      start: start ?? fallbackStart,
      duration: asset.duration,
      layer,
    }
    set((state) => ({ timeline: [...state.timeline, clip] }))
  },
  moveClip(clipId, start) {
    const safeStart = Math.max(0, Number.isFinite(start) ? start : 0)
    set((state) => ({
      timeline: state.timeline.map((clip) =>
        clip.id === clipId ? { ...clip, start: Number(safeStart.toFixed(2)) } : clip,
      ),
    }))
  },
  trimClip(clipId, duration) {
    set((state) => ({
      timeline: state.timeline.map((clip) =>
        clip.id === clipId
          ? { ...clip, duration: clamp(Number(duration.toFixed(2)), 0.5, clip.duration * 2) }
          : clip,
      ),
    }))
  },
  removeClip(clipId) {
    set((state) => ({ timeline: state.timeline.filter((clip) => clip.id !== clipId) }))
  },
  setHighlightedAsset(assetId) {
    set({ highlightedAssetId: assetId })
  },
  setSelectedFrame(frame) {
    const safeFrame = Math.max(0, Math.floor(frame))
    set({ selectedFrame: safeFrame })
  },
  async saveTimeline(options) {
    const state = get()
    const payload = toTimelinePayload(state, options)
    set({
      isSavingTimeline: true,
      saveError: null,
      lastError: null,
      timelineName: payload.name,
      timelineDescription: payload.description ?? '',
    })

    try {
      const response = await apiClient.createVideoTimeline(payload)
      set({
        timelineId: response.id,
        lastSavedAt: response.updated_at,
        isSavingTimeline: false,
        timelineName: response.name,
        timelineDescription: response.description ?? '',
      })
      return response
    } catch (error) {
      const message = (error as Error).message ?? 'Sauvegarde impossible'
      set({ isSavingTimeline: false, saveError: message, lastError: message })
      return null
    }
  },
  async queueTimelineRender() {
    const state = get()
    set({ isQueueingRender: true, queueError: null, lastError: null })

    let timelineId = state.timelineId
    if (!timelineId) {
      const saved = await get().saveTimeline()
      if (!saved) {
        const message = get().saveError ?? 'Sauvegarde requise avant rendu'
        set({ isQueueingRender: false, queueError: message, lastError: message })
        return null
      }
      timelineId = saved.id
    }

    try {
      const job: GenerationJobResponse = await apiClient.queueVideoRender(timelineId)
      set((current) => ({
        isQueueingRender: false,
        videoJobs: [
          ...current.videoJobs.filter((entry) => entry.jobId !== job.job_id),
          {
            jobId: job.job_id,
            status: job.status,
            progress: 0,
            assetCount: 0,
            createdAt: new Date().toISOString(),
            updatedAt: undefined,
            jobType: 'video_timeline',
            statusMessage: job.message,
            resultUrls: [],
            errorMessage: null,
          },
        ],
      }))
      void get().refreshJobs()
      return job
    } catch (error) {
      const message = (error as Error).message ?? 'Impossible de lancer le rendu'
      set({ isQueueingRender: false, queueError: message, lastError: message })
      return null
    }
  },
  async refreshJobs() {
    set({ isLoadingJobs: true, jobError: null })
    try {
      const response = await apiClient.listJobs({ limit: 20 })
      get().syncJobs(response.jobs)
      set({ isLoadingJobs: false })
    } catch (error) {
      const message = (error as Error).message ?? 'Erreur lors du chargement des jobs'
      set({ isLoadingJobs: false, jobError: message, lastError: message, videoJobs: [] })
    }
  },
  async fetchWaveform(assetId, existing) {
    const asset = get().assets.find((entry) => entry.id === assetId)
    if (!asset || asset.kind !== 'audio') {
      return null
    }

    const updateAsset = (patch: Partial<VideoAsset>) => {
      set((state) => ({
        assets: state.assets.map((item) => (item.id === assetId ? { ...item, ...patch } : item)),
      }))
    }

    if (existing && existing.length > 0) {
      updateAsset({
        waveform: existing,
        waveformStatus: 'ready',
        waveformUpdatedAt: new Date().toISOString(),
        waveformError: null,
      })
      return existing
    }

    if (asset.waveformStatus === 'ready' && asset.waveform && asset.waveform.length > 0) {
      return asset.waveform
    }

    updateAsset({ waveformStatus: 'loading', waveformError: null })

    try {
      const response = await apiClient.getVideoAssetWaveform(assetId)
      const status = (response?.status ??
        (Array.isArray(response?.waveform) && response.waveform.length > 0 ? 'ready' : 'processing')) as
        | 'processing'
        | 'ready'
        | 'failed'

      if (status === 'ready' && Array.isArray(response.waveform) && response.waveform.length > 0) {
        updateAsset({
          waveform: response.waveform,
          waveformStatus: 'ready',
          waveformUpdatedAt: response.generated_at ?? new Date().toISOString(),
          waveformError: null,
        })
        return response.waveform
      }

      if (status === 'failed') {
        const message = "Waveform indisponible côté serveur"
        updateAsset({ waveformStatus: 'error', waveformError: message })
        set({ lastError: message })
        return null
      }

      updateAsset({ waveformStatus: 'loading', waveformError: null })
      return null
    } catch (error) {
      // On garde l’erreur pour potentiellement retenter en local
      const message = (error as Error).message ?? "Waveform API indisponible"
      updateAsset({ waveformError: message })
    }

    const fallbackUrl = asset.downloadUrl ?? asset.url ?? asset.previewUrl
    if (fallbackUrl) {
      try {
        const waveform = await computeWaveformFromAudio(fallbackUrl)
        updateAsset({
          waveform,
          waveformStatus: 'ready',
          waveformUpdatedAt: new Date().toISOString(),
          waveformError: null,
        })
        return waveform
      } catch (error) {
        const message = (error as Error).message ?? 'Impossible de calculer la waveform locale'
        updateAsset({ waveformStatus: 'error', waveformError: message })
        set({ lastError: message })
        return null
      }
    }

    const message = "Aucune source disponible pour la waveform"
    updateAsset({ waveformStatus: 'error', waveformError: message })
    set({ lastError: message })
    return null
  },
  syncJobs(jobs) {
    const videoJobs = jobs
      .filter((job) => job.job_type === 'video' || job.job_type === 'video_timeline')
      .map((job) => ({
        jobId: job.job_id,
        status: job.status,
        progress: job.progress ?? 0,
        assetCount: Array.isArray(job.result_images) ? job.result_images.length : 0,
        createdAt: job.created_at,
        updatedAt: job.updated_at,
        jobType: job.job_type,
        statusMessage: job.message ?? null,
        resultUrls: Array.isArray(job.result_images) ? job.result_images : [],
        errorMessage: job.status === 'failed' ? job.message ?? null : null,
      }))
      .sort((a, b) => {
        const aDate = a.updatedAt ?? a.createdAt ?? ''
        const bDate = b.updatedAt ?? b.createdAt ?? ''
        return new Date(bDate).getTime() - new Date(aDate).getTime()
      })
    set({ videoJobs })
  },
  async requestProxyPreview(options) {
    const state = get()
    const force = options?.force ?? false

    if (!force && state.proxyPreview.status === 'ready' && state.proxyPreview.url) {
      return {
        job_id: state.proxyPreview.jobId ?? undefined,
        status: 'ready',
        proxy_url: state.proxyPreview.url,
        updated_at: state.proxyPreview.updatedAt ?? undefined,
        message: state.proxyPreview.message ?? undefined,
      }
    }

    set((current) => ({
      proxyPreview: {
        ...current.proxyPreview,
        status: 'loading',
        errorMessage: null,
        message: null,
        requestedAt: new Date().toISOString(),
      },
      lastError: null,
    }))

    let timelineId = state.timelineId
    if (!timelineId) {
      const saved = await get().saveTimeline()
      if (!saved) {
        const message = get().saveError ?? 'Sauvegarde requise avant la génération proxy'
        set((current) => ({
          proxyPreview: { ...current.proxyPreview, status: 'error', errorMessage: message },
          lastError: message,
        }))
        return null
      }
      timelineId = saved.id
    }

    try {
      const response = await apiClient.queueVideoProxyRender(timelineId, { force })
      const status = response.proxy_url ? 'ready' : mapProxyStatus(response.status)
      set((current) => ({
        proxyPreview: {
          ...current.proxyPreview,
          status,
          url: response.proxy_url ?? current.proxyPreview.url,
          jobId: response.job_id ?? current.proxyPreview.jobId,
          updatedAt: response.updated_at ?? current.proxyPreview.updatedAt,
          errorMessage: status === 'error' ? response.message ?? current.proxyPreview.errorMessage : null,
          message: response.message ?? current.proxyPreview.message,
        },
      }))
      return response
    } catch (error) {
      const message = (error as Error).message ?? 'Impossible de lancer le rendu proxy'
      set((current) => ({
        proxyPreview: { ...current.proxyPreview, status: 'error', errorMessage: message },
        lastError: message,
      }))
      return null
    }
  },
  async refreshProxyPreview() {
    const { timelineId } = get()
    if (!timelineId) {
      return null
    }

    try {
      const response = await apiClient.getVideoProxyPreview(timelineId)
      const status = response.proxy_url ? 'ready' : mapProxyStatus(response.status)
      set((current) => ({
        proxyPreview: {
          ...current.proxyPreview,
          status,
          url: response.proxy_url ?? current.proxyPreview.url,
          jobId: response.job_id ?? current.proxyPreview.jobId,
          updatedAt: response.updated_at ?? current.proxyPreview.updatedAt,
          errorMessage:
            status === 'error' ? response.message ?? current.proxyPreview.errorMessage : current.proxyPreview.errorMessage,
          message: response.message ?? current.proxyPreview.message,
        },
      }))
      return response
    } catch (error) {
      const message = (error as Error).message ?? 'Impossible de rafraîchir le proxy'
      set((current) => ({
        proxyPreview: { ...current.proxyPreview, status: 'error', errorMessage: message },
        lastError: message,
      }))
      return null
    }
  },
  reset() {
    set((state) => {
      state.assets.forEach((asset) => {
        if (asset.previewUrl) {
          URL.revokeObjectURL(asset.previewUrl)
        }
      })
      return {
        assets: [],
        timeline: [],
        videoJobs: [],
        selectedFrame: 0,
        frameRate: 24,
        isUploading: false,
        uploadProgress: 0,
        highlightedAssetId: null,
        timelineId: null,
        timelineName: 'Montage vidéo',
        timelineDescription: '',
        lastSavedAt: null,
        isSavingTimeline: false,
        saveError: null,
        isQueueingRender: false,
        queueError: null,
        isLoadingJobs: false,
        jobError: null,
        lastError: null,
        proxyPreview: cloneProxyPreview(),
      }
    })
  },
  applyRealtimeUpdate(update) {
    if (!update.jobId) return
    if (update.jobType && !['video', 'video_timeline'].includes(update.jobType)) return

    set((state) => {
      const existing = state.videoJobs.find((entry) => entry.jobId === update.jobId)
      const assetCount = Array.isArray(update.metadata?.assets)
        ? (update.metadata?.assets as unknown[]).length
        : existing?.assetCount ?? 0

      if (!existing) {
        const next: VideoJobState = {
          jobId: update.jobId!,
          status: update.status ?? 'queued',
          progress: update.progress ?? 0,
          assetCount,
          createdAt: update.createdAt ?? new Date().toISOString(),
          updatedAt: update.completedAt ?? update.timestamp,
          jobType: update.jobType ?? 'video',
          statusMessage: update.message ?? null,
          resultUrls: [],
          errorMessage: update.status === 'failed' ? update.message ?? null : null,
        }
        return { videoJobs: [...state.videoJobs, next] }
      }

      const videoJobs = state.videoJobs.map((entry) =>
        entry.jobId === update.jobId
          ? {
              ...entry,
              status: update.status ?? entry.status,
              progress: update.progress ?? entry.progress,
              updatedAt: update.completedAt ?? update.timestamp ?? entry.updatedAt,
              assetCount,
              statusMessage: update.message ?? entry.statusMessage,
              errorMessage:
                (update.status ?? entry.status) === 'failed'
                  ? update.message ?? entry.errorMessage ?? null
                  : entry.errorMessage,
            }
          : entry,
      )
      return { videoJobs }
    })

    const assetCandidates = update.metadata?.assets
    if (Array.isArray(assetCandidates) && assetCandidates.length > 0) {
      const assets = get().assets
      const missing = assetCandidates.filter((candidate) =>
        typeof candidate === 'object' && candidate !== null && 'id' in candidate && 'name' in candidate,
      ) as Array<{
        id: string
        name: string
        duration?: number
        kind?: VideoAssetType
        download_url?: string
        waveform?: number[]
      }>

      if (missing.length > 0) {
        const now = new Date().toISOString()
        const newAudioAssets: Array<{ id: string; waveform?: number[] }> = []
        const additionalAssets: VideoAsset[] = missing
          .filter((candidate) => !assets.some((asset) => asset.id === candidate.id))
          .map((candidate) => {
            const kind = candidate.kind ?? 'video'
            if (kind === 'audio') {
              newAudioAssets.push({ id: candidate.id, waveform: candidate.waveform })
            }
            return {
              id: candidate.id,
              name: candidate.name,
              kind,
              duration: candidate.duration ?? 8,
              status: 'ready',
              url: candidate.download_url ?? undefined,
              downloadUrl: candidate.download_url ?? null,
              previewUrl: null,
              waveform: kind === 'audio' ? candidate.waveform ?? [] : undefined,
              waveformStatus: kind === 'audio' ? (candidate.waveform ? 'ready' : 'loading') : 'idle',
              waveformUpdatedAt:
                kind === 'audio' && candidate.waveform ? new Date().toISOString() : null,
              waveformError: null,
              fileSize: 0,
              jobId: update.jobId ?? null,
              createdAt: now,
              mimeType: null,
              errorMessage: null,
            }
          })

        if (additionalAssets.length > 0) {
          set((state) => ({ assets: [...state.assets, ...additionalAssets] }))
          newAudioAssets.forEach(({ id, waveform }) => {
            void get().fetchWaveform(id, waveform ?? null)
          })
        }
      }
    }
  },
}))

export const pxPerSecond = 48
