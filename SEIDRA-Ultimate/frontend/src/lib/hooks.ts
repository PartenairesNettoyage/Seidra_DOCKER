'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  apiClient,
  type JobItem,
  type JobStats,
  type MediaFilters,
  type MediaItem,
  type MediaStatsResponse,
  type ModelInfo,
  type ModelStatus,
  type NSFWSettingsPayload,
  type GenerationJobPayload,
  type GenerationJobResponse,
  type Persona,
  type PersonaCreatePayload,
  type PersonaPreviewResponse,
  type PersonaUpdatePayload,
  type SettingsResponse,
  type SettingsUpdatePayload,
  type VideoGenerationPayload,
} from './api-client'
import type { JobRealtimeUpdate } from './websocket-context'

function sortByUpdatedAt<T extends { updated_at?: string; created_at?: string }>(entries: T[]): T[] {
  return [...entries].sort((a, b) => {
    const fallbackA = a.updated_at ?? a.created_at ?? ''
    const fallbackB = b.updated_at ?? b.created_at ?? ''
    return new Date(fallbackB).getTime() - new Date(fallbackA).getTime()
  })
}

// Personas -----------------------------------------------------------------
export function usePersonas() {
  const [personas, setPersonas] = useState<Persona[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isMutating, setIsMutating] = useState(false)

  const load = useCallback(async () => {
    setIsLoading(true)
    try {
      const data = await apiClient.listPersonas()
      setPersonas(sortByUpdatedAt(data))
      setError(null)
    } catch (err) {
      setError((err as Error).message)
      setPersonas([])
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const createPersona = useCallback(
    async (payload: PersonaCreatePayload) => {
      setIsMutating(true)
      try {
        const persona = await apiClient.createPersona(payload)
        setPersonas((prev) => sortByUpdatedAt([persona, ...prev]))
        return persona
      } finally {
        setIsMutating(false)
      }
    },
    [],
  )

  const updatePersona = useCallback(async (id: number, payload: PersonaUpdatePayload) => {
    setIsMutating(true)
    try {
      const updated = await apiClient.updatePersona(id, payload)
      setPersonas((prev) => sortByUpdatedAt(prev.map((entry) => (entry.id === id ? updated : entry))))
      return updated
    } finally {
      setIsMutating(false)
    }
  }, [])

  const deletePersona = useCallback(async (id: number) => {
    setIsMutating(true)
    try {
      await apiClient.deletePersona(id)
      setPersonas((prev) => prev.filter((entry) => entry.id !== id))
    } finally {
      setIsMutating(false)
    }
  }, [])

  const duplicatePersona = useCallback(async (id: number, newName: string) => {
    setIsMutating(true)
    try {
      const persona = await apiClient.duplicatePersona(id, newName)
      setPersonas((prev) => sortByUpdatedAt([persona, ...prev]))
      return persona
    } finally {
      setIsMutating(false)
    }
  }, [])

  return {
    personas,
    isLoading,
    error,
    isMutating,
    refresh: load,
    createPersona,
    updatePersona,
    deletePersona,
    duplicatePersona,
  }
}

export function usePersonaPreview() {
  const [previewJob, setPreviewJob] = useState<PersonaPreviewResponse | null>(null)
  const [isPreviewing, setIsPreviewing] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)

  const previewPersona = useCallback(async (id: number) => {
    setIsPreviewing(true)
    try {
      const job = await apiClient.previewPersona(id)
      setPreviewJob(job)
      setPreviewError(null)
      return job
    } catch (err) {
      const message = (err as Error).message ?? 'Unknown error'
      setPreviewError(message)
      setPreviewJob(null)
      throw err
    } finally {
      setIsPreviewing(false)
    }
  }, [])

  return { previewPersona, previewJob, isPreviewing, previewError }
}

// Models --------------------------------------------------------------------
export function useModels() {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [status, setStatus] = useState<ModelStatus | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<Set<string>>(new Set())

  const refresh = useCallback(async () => {
    setIsLoading(true)
    try {
      const [available, runtimeStatus] = await Promise.all([
        apiClient.listAvailableModels(),
        apiClient.getModelStatus().catch(() => null),
      ])
      setModels(available)
      setStatus(runtimeStatus)
      setError(null)
    } catch (err) {
      setError((err as Error).message)
      setModels([])
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const setPendingFlag = useCallback((modelId: string, enabled: boolean) => {
    setPending((prev) => {
      const next = new Set(prev)
      if (enabled) {
        next.add(modelId)
      } else {
        next.delete(modelId)
      }
      return next
    })
  }, [])

  const downloadModel = useCallback(async (modelId: string) => {
    setPendingFlag(modelId, true)
    try {
      await apiClient.downloadModel(modelId)
      setModels((prev) => prev.map((model) => (model.id === modelId ? { ...model, is_downloaded: true } : model)))
    } finally {
      setPendingFlag(modelId, false)
    }
  }, [setPendingFlag])

  const deleteModel = useCallback(async (modelId: string) => {
    setPendingFlag(modelId, true)
    try {
      await apiClient.deleteModel(modelId)
      setModels((prev) => prev.map((model) => (model.id === modelId ? { ...model, is_downloaded: false } : model)))
    } finally {
      setPendingFlag(modelId, false)
    }
  }, [setPendingFlag])

  const reloadModels = useCallback(async () => {
    await apiClient.reloadModels()
    await refresh()
  }, [refresh])

  const clearModelCache = useCallback(async () => {
    await apiClient.clearModelCache()
    await refresh()
  }, [refresh])

  return {
    models,
    status,
    isLoading,
    error,
    pending,
    refresh,
    downloadModel,
    deleteModel,
    reloadModels,
    clearModelCache,
  }
}

// Media ---------------------------------------------------------------------
type UseVideoGenerationOptions = {
  defaultDuration?: number
  minDuration?: number
  maxDuration?: number
  defaultModel?: string
  onQueued?: (update: JobRealtimeUpdate) => void
}

type VideoGenerationResult = {
  response: GenerationJobResponse
  update: JobRealtimeUpdate
}

export function useVideoGeneration({
  defaultDuration = 6,
  minDuration = 2,
  maxDuration = 30,
  defaultModel = 'sadtalker',
  onQueued,
}: UseVideoGenerationOptions = {}) {
  const [prompt, setPrompt] = useState('')
  const [referenceImage, setReferenceImage] = useState('')
  const [durationSeconds, setDurationSeconds] = useState(defaultDuration)
  const [audioFile, setAudioFile] = useState<File | null>(null)
  const [modelName, setModelName] = useState(defaultModel)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const clampDuration = useCallback(
    (value: number) => {
      if (!Number.isFinite(value)) {
        setDurationSeconds(defaultDuration)
        return
      }
      const next = Math.max(minDuration, Math.min(maxDuration, value))
      setDurationSeconds(next)
    },
    [defaultDuration, minDuration, maxDuration],
  )

  const reset = useCallback(() => {
    setPrompt('')
    setReferenceImage('')
    setDurationSeconds(defaultDuration)
    setAudioFile(null)
    setModelName(defaultModel)
  }, [defaultDuration, defaultModel])

  const submit = useCallback(async (): Promise<VideoGenerationResult> => {
    const trimmedPrompt = prompt.trim()
    if (!trimmedPrompt) {
      throw new Error('Prompt cannot be empty')
    }

    if (!audioFile) {
      throw new Error('An audio track is required')
    }

    if (!Number.isFinite(durationSeconds) || durationSeconds < minDuration || durationSeconds > maxDuration) {
      throw new Error(`Duration must be between ${minDuration} and ${maxDuration} seconds`)
    }

    setIsSubmitting(true)
    try {
      const payload: VideoGenerationPayload = {
        prompt: trimmedPrompt,
        duration_seconds: Math.round(durationSeconds),
        reference_image: referenceImage.trim() || undefined,
        model_name: modelName,
        audio_file: audioFile,
      }

      const response = await apiClient.generateVideo(payload)
      const createdAt = new Date().toISOString()
      const update: JobRealtimeUpdate = {
        jobId: response.job_id,
        status: 'queued',
        progress: 0,
        jobType: 'video',
        modelName,
        message: 'Queued locally – awaiting worker',
        metadata: {
          prompt: trimmedPrompt,
          reference_image: referenceImage.trim() || undefined,
          duration_seconds: Math.round(durationSeconds),
          createdAt,
        },
      }
      onQueued?.(update)
      return { response, update }
    } finally {
      setIsSubmitting(false)
    }
  }, [prompt, audioFile, durationSeconds, minDuration, maxDuration, referenceImage, modelName, onQueued])

  return {
    prompt,
    setPrompt,
    referenceImage,
    setReferenceImage,
    durationSeconds,
    setDurationSeconds: clampDuration,
    audioFile,
    setAudioFile,
    modelName,
    setModelName,
    isSubmitting,
    submit,
    reset,
    minDuration,
    maxDuration,
  }
}

export function useMediaLibrary(initialLimit = 12) {
  const defaultFilters = useMemo<MediaFilters>(() => ({ limit: initialLimit, offset: 0 }), [initialLimit])
  const [filters, setFilters] = useState<MediaFilters>(defaultFilters)
  const [media, setMedia] = useState<MediaItem[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<MediaStatsResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [statsLoading, setStatsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [instruction, setInstruction] = useState<{ filters: MediaFilters; append: boolean } | null>(null)

  const fetchMedia = useCallback(async (requestFilters: MediaFilters, append = false) => {
    setIsLoading(true)
    try {
      const response = await apiClient.listMedia(requestFilters)
      setTotal(response.total)
      setMedia((previous) => (append ? [...previous, ...response.items] : response.items))
      setError(null)
    } catch (err) {
      setError((err as Error).message)
      if (!append) {
        setMedia([])
        setTotal(0)
      }
    } finally {
      setIsLoading(false)
    }
  }, [])

  const fetchStats = useCallback(async () => {
    setStatsLoading(true)
    try {
      const response = await apiClient.getMediaStats()
      setStats(response)
    } catch {
      // ignore errors, stats are optional
    } finally {
      setStatsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!instruction) return
    void (async () => {
      await fetchMedia(instruction.filters, instruction.append)
      setInstruction(null)
    })()
  }, [instruction, fetchMedia])

  useEffect(() => {
    setInstruction({ filters: defaultFilters, append: false })
    void fetchStats()
  }, [defaultFilters, fetchStats])

  const applyFilters = useCallback((updates: Partial<MediaFilters>) => {
    setFilters((prev) => {
      const next: MediaFilters = {
        ...prev,
        ...updates,
        offset: updates.offset ?? 0,
      }
      setInstruction({ filters: next, append: false })
      return next
    })
  }, [])

  const refresh = useCallback(() => {
    setInstruction({ filters, append: false })
    void fetchStats()
  }, [filters, fetchStats])

  const loadMore = useCallback(() => {
    setFilters((prev) => {
      const limit = prev.limit ?? initialLimit
      const next: MediaFilters = {
        ...prev,
        offset: (prev.offset ?? 0) + limit,
      }
      setInstruction({ filters: next, append: true })
      return next
    })
  }, [initialLimit])

  const toggleFavorite = useCallback(async (mediaId: string) => {
    try {
      const response = await apiClient.toggleMediaFavorite(mediaId)
      setMedia((prev) =>
        prev.map((item) => (item.id === mediaId ? { ...item, is_favorite: response.is_favorite } : item)),
      )
      void fetchStats()
      return response.is_favorite
    } catch (err) {
      setError((err as Error).message)
      throw err
    }
  }, [fetchStats])

  const updateTags = useCallback(async (mediaId: string, tags: string[]) => {
    try {
      const response = await apiClient.updateMediaTags(mediaId, tags)
      setMedia((prev) => prev.map((item) => (item.id === mediaId ? { ...item, tags: response.tags } : item)))
      return response.tags
    } catch (err) {
      setError((err as Error).message)
      throw err
    }
  }, [])

  const deleteMedia = useCallback(async (mediaId: string) => {
    try {
      await apiClient.deleteMedia(mediaId)
      setMedia((prev) => prev.filter((item) => item.id !== mediaId))
      setTotal((prev) => Math.max(0, prev - 1))
      void fetchStats()
    } catch (err) {
      setError((err as Error).message)
      throw err
    }
  }, [fetchStats])

  return {
    media,
    total,
    filters,
    stats,
    isLoading,
    statsLoading,
    error,
    applyFilters,
    loadMore,
    refresh,
    toggleFavorite,
    updateTags,
    deleteMedia,
  }
}

// Jobs ----------------------------------------------------------------------
export function useJobHistory(initialLimit = 25) {
  const defaultFilters = useMemo(() => ({ limit: initialLimit, offset: 0 }), [initialLimit])
  const [filters, setFilters] = useState<Record<string, number | string | undefined>>(defaultFilters)
  const [jobs, setJobs] = useState<JobItem[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<JobStats | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [instruction, setInstruction] = useState<{ filters: typeof filters; append: boolean } | null>(null)

  const fetchJobs = useCallback(async (requestFilters: typeof filters, append = false) => {
    setIsLoading(true)
    try {
      const response = await apiClient.listJobs(requestFilters)
      setTotal(response.total)
      setJobs((prev) => (append ? [...prev, ...response.jobs] : response.jobs))
      setError(null)
    } catch (err) {
      setError((err as Error).message)
      if (!append) {
        setJobs([])
        setTotal(0)
      }
    } finally {
      setIsLoading(false)
    }
  }, [])

  const fetchStats = useCallback(async () => {
    try {
      const response = await apiClient.getJobStats()
      setStats(response)
    } catch {
      // optional stats
    }
  }, [])

  useEffect(() => {
    if (!instruction) return
    void (async () => {
      await fetchJobs(instruction.filters, instruction.append)
      setInstruction(null)
    })()
  }, [instruction, fetchJobs])

  useEffect(() => {
    setInstruction({ filters: defaultFilters, append: false })
    void fetchStats()
  }, [defaultFilters, fetchStats])

  const applyFilters = useCallback((updates: Partial<typeof filters>) => {
    setFilters((prev) => {
      const next = { ...prev, ...updates, offset: updates.offset ?? 0 }
      setInstruction({ filters: next, append: false })
      return next
    })
  }, [])

  const loadMore = useCallback(() => {
    setFilters((prev) => {
      const limit = Number(prev.limit ?? initialLimit)
      const offset = Number(prev.offset ?? 0)
      const next = { ...prev, offset: offset + limit }
      setInstruction({ filters: next, append: true })
      return next
    })
  }, [initialLimit])

  const refresh = useCallback(() => {
    setInstruction({ filters, append: false })
    void fetchStats()
  }, [filters, fetchStats])

  const cancelJob = useCallback(async (jobId: string) => {
    await apiClient.cancelJob(jobId)
    setJobs((prev) =>
      prev.map((job) => (job.job_id === jobId ? { ...job, status: 'cancelled', progress: 0 } : job)),
    )
    void fetchStats()
  }, [fetchStats])

  const retryJob = useCallback(async (jobId: string) => {
    const response = await apiClient.retryJob(jobId)
    const detail = await apiClient.getJob(response.new_job_id)
    setJobs((prev) => sortByUpdatedAt([detail, ...prev]))
    void fetchStats()
    return detail
  }, [fetchStats])

  return {
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
  }
}

// Settings ------------------------------------------------------------------
export function useUltimateSettings() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null)
  const [nsfwSettings, setNsfwSettings] = useState<NSFWSettingsPayload | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  const refresh = useCallback(async () => {
    setIsLoading(true)
    try {
      const [general, nsfw] = await Promise.all([
        apiClient.getSettings(),
        apiClient.getNsfwSettings(),
      ])
      setSettings(general)
      setNsfwSettings(nsfw)
      setError(null)
    } catch (err) {
      setError((err as Error).message)
      setSettings(null)
      setNsfwSettings(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const updateSettings = useCallback(async (payload: SettingsUpdatePayload) => {
    setIsSaving(true)
    try {
      const response = await apiClient.updateSettings(payload)
      setSettings(response)
      return response
    } finally {
      setIsSaving(false)
    }
  }, [])

  const updateNsfw = useCallback(async (payload: NSFWSettingsPayload) => {
    setIsSaving(true)
    try {
      const response = await apiClient.updateNsfwSettings(payload)
      setNsfwSettings(response)
      return response
    } finally {
      setIsSaving(false)
    }
  }, [])

  return {
    settings,
    nsfwSettings,
    isLoading,
    isSaving,
    error,
    refresh,
    updateSettings,
    updateNsfw,
  }
}

// Generation helper ---------------------------------------------------------
export function buildGenerationPayload(
  overrides: GenerationJobPayload,
  defaults: GenerationJobPayload,
): GenerationJobPayload {
  const merged: GenerationJobPayload = {
    ...defaults,
    ...overrides,
  }
  if (merged.seed === null || merged.seed === undefined || Number.isNaN(merged.seed)) {
    delete merged.seed
  }
  if (!merged.negative_prompt) {
    delete merged.negative_prompt
  }
  if (!merged.lora_models || merged.lora_models.length === 0) {
    delete merged.lora_models
  }
  return merged
}
