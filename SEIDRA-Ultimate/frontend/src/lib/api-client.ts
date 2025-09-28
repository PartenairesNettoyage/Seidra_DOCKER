const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const isFormData = options?.body instanceof FormData
  const headers = new Headers(options?.headers)

  if (!isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_BASE}${path}`, {
    headers,
    credentials: 'include',
    ...options,
  })

  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || `Request failed with status ${response.status}`)
  }

  if (response.status === 204) {
    return undefined as T
  }

  const contentType = response.headers.get('Content-Type') ?? ''
  if (contentType.includes('application/json')) {
    return (await response.json()) as T
  }


  const textPayload = await response.text()
  return textPayload as unknown as T
}

export type Persona = {
  id: number
  name: string
  description: string
  style_prompt: string
  negative_prompt: string
  lora_models: string[]
  generation_params: Record<string, unknown>
  created_at: string
  updated_at: string
  tags?: string[]
  is_favorite?: boolean
  is_nsfw?: boolean
  metadata?: Record<string, unknown>
}

export type PersonaCreatePayload = {
  name: string
  description?: string
  style_prompt: string
  negative_prompt?: string
  lora_models?: string[]
  generation_params?: Record<string, unknown>
}

export type PersonaUpdatePayload = Partial<PersonaCreatePayload>

export type PersonaPreviewResponse = {
  job_id: string
  status: string
  message: string
  persona_id: number
  estimated_time?: number
}

export type MediaItem = {
  id: string
  user_id: number
  job_id: string
  file_path: string
  thumbnail_path?: string | null
  file_type: string
  mime_type?: string | null
  metadata: Record<string, unknown>
  tags: string[]
  is_favorite: boolean
  is_nsfw: boolean
  nsfw_tags: string[]
  created_at: string
}

export type MediaListResponse = {
  total: number
  items: MediaItem[]
}

export type MediaStatsResponse = {
  total_images: number
  total_size: string
  favorites_count: number
  recent_count: number
  by_persona: Record<string, number>
  by_date: Record<string, number>
}

export type MediaFilters = {
  limit?: number
  offset?: number
  tags?: string[]
  favorites_only?: boolean
  search?: string
  date_from?: string
  date_to?: string
  persona_id?: number
}

export type MediaBulkActionResponse = {
  action: string
  processed: number
  failed: number
  media_ids: string[]
}

export type JobItem = {
  job_id: string
  status: string
  prompt?: string
  progress: number
  job_type: string
  model_name: string
  persona_id?: number | null
  created_at: string
  updated_at?: string
  completed_at?: string
  result_images?: string[]
  message?: string
}

export type JobHistoryResponse = {
  total: number
  jobs: JobItem[]
}

export type JobDetail = JobItem & {
  negative_prompt: string
  parameters: Record<string, unknown>
  metadata: Record<string, unknown>
  error_message?: string | null
}

export type JobStats = {
  total: number
  by_status: Record<string, number>
  average_duration: number | null
  last_completed: string | null
}

export type JobStatusResponse = JobItem & {
  result_images: string[]
  error_message?: string | null
}

export type GenerationJobPayload = {
  prompt: string
  negative_prompt?: string
  width?: number
  height?: number
  num_inference_steps?: number
  guidance_scale?: number
  num_images?: number
  persona_id?: number | null
  lora_models?: string[]
  lora_weights?: number[]
  seed?: number | null
  model_name?: string
  scheduler?: string
  style?: string | null
  quality?: string
  is_nsfw?: boolean
  job_type?: string
  metadata?: Record<string, unknown>
}

export type GenerationJobResponse = {
  job_id: string
  status: string
  message: string
  estimated_time?: number
}

export type VideoGenerationPayload = {
  prompt: string
  duration_seconds: number
  reference_image?: string
  model_name?: string
  persona_id?: number | null
  metadata?: Record<string, unknown>
  audio_file?: File
}

export type VideoAssetUploadResponse = {
  id: string
  name: string
  kind: 'video' | 'audio' | 'image'
  duration: number
  file_size: number
  status: string
  url: string
  download_url: string
  created_at: string
  mime_type: string
}

export type VideoTimelineAssetPayload = {
  id: string
  name: string
  kind: 'video' | 'audio' | 'image'
  duration: number
  status: string
  url?: string | null
  download_url?: string | null
  waveform?: number[]
  file_size?: number
  job_id?: string | null
  created_at?: string
  mime_type?: string | null
}

export type VideoTimelineClipPayload = {
  id: string
  asset_id: string
  start: number
  duration: number
  layer: 'video' | 'audio'
}

export type VideoTimelinePayload = {
  id?: string
  name: string
  description?: string
  frame_rate?: number
  total_duration?: number
  assets: VideoTimelineAssetPayload[]
  clips: VideoTimelineClipPayload[]
}

export type VideoTimelineResponse = VideoTimelinePayload & {
  id: string
  description: string
  frame_rate: number
  total_duration: number
  job_id?: string | null
  created_at: string
  updated_at: string
}

export type VideoProxyPreviewResponse = {
  job_id?: string | null
  status: 'idle' | 'processing' | 'ready' | 'failed' | 'error'
  proxy_url?: string | null
  updated_at?: string | null
  message?: string | null
}

export type VideoAssetWaveformResponse = {
  asset_id: string
  waveform: number[]
  sample_rate?: number
  peak_amplitude?: number
  generated_at?: string
  status?: 'processing' | 'ready' | 'failed'
}

export type ModelInfo = {
  id: string
  name: string
  description: string
  type: string
  size: string
  is_downloaded: boolean
  download_url?: string | null
  category?: string
  tags?: string[]
}

export type LoRAModel = {
  id: string
  name: string
  description: string
  file_path: string
  download_url?: string | null
  category: string
  tags: string[]
  is_downloaded: boolean
  file_size: number
}

export type ModelStatus = {
  loaded_models: string[]
  available_loras: string[]
  gpu_info: Record<string, unknown>
  cache_size: string
  optimal_batch_size: number
}

export type SettingsResponse = {
  theme: string
  language: string
  notifications: Record<string, boolean>
  telemetry_opt_in: boolean
  extra: Record<string, unknown>
}

export type SettingsUpdatePayload = Partial<Omit<SettingsResponse, 'extra'>> & {
  extra?: Record<string, unknown>
}

export type NSFWSettingsPayload = {
  enabled: boolean
  age_verified: boolean
  intensity: 'low' | 'medium' | 'high'
  categories: Record<string, boolean>
  overrides: Record<string, unknown>
}

export type SystemHealthResponse = {
  status: string
  gpu: Record<string, unknown>
  models_loaded: number
  active_connections: number
}

export type RealtimeNotification = {
  id: string
  level: 'info' | 'warning' | 'error' | 'success'
  title: string
  message: string
  category: string
  metadata: Record<string, unknown>
  tags: string[]
  timestamp: string
}

export type NotificationFeedResponse = {
  items: RealtimeNotification[]
  total: number
  limit: number
  offset: number
  hasMore: boolean
}

export type SystemInfoResponse = {
  timestamp: string
  environment: string
  debug: boolean
  gpu: Record<string, unknown>
  models: Array<Record<string, unknown>>
  model_info: Record<string, unknown>
  connections: Record<string, unknown>
  system: Record<string, unknown>
  media_directory: string
  notifications: RealtimeNotification[]
}

function appendSearchParams(query: URLSearchParams, params: Record<string, unknown>) {
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    if (Array.isArray(value)) {
      if (value.length === 0) return
      query.set(key, value.join(','))
      return
    }
    query.set(key, String(value))
  })
}

export const apiClient = {
  async generateImage(payload: GenerationJobPayload) {
    return request<GenerationJobResponse>(`/generate/single`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  async generateVideo(payload: VideoGenerationPayload) {
    const formData = new FormData()
    formData.append('prompt', payload.prompt)
    formData.append('duration_seconds', String(payload.duration_seconds))

    if (payload.reference_image) {
      formData.append('reference_image', payload.reference_image)
    }

    if (payload.model_name) {
      formData.append('model_name', payload.model_name)
    }

    if (payload.persona_id) {
      formData.append('persona_id', String(payload.persona_id))
    }

    if (payload.metadata) {
      formData.append('metadata', JSON.stringify(payload.metadata))
    }

    if (payload.audio_file) {
      formData.append('audio_file', payload.audio_file)
    }

    return request<GenerationJobResponse>(`/generate/video`, {
      method: 'POST',
      body: formData,
    })
  },
  async uploadVideoAsset(file: File, options?: { duration?: number; kind?: string }) {
    const formData = new FormData()
    formData.append('file', file)
    if (typeof options?.duration === 'number') {
      formData.append('duration', String(options.duration))
    }
    if (options?.kind) {
      formData.append('kind', options.kind)
    }
    return request<VideoAssetUploadResponse>(`/media/video-assets`, {
      method: 'POST',
      body: formData,
    })
  },
  async createVideoTimeline(payload: VideoTimelinePayload) {
    return request<VideoTimelineResponse>(`/generate/video/timeline`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  async queueVideoRender(timelineId: string) {
    return request<GenerationJobResponse>(`/generate/video/timeline/${timelineId}/render`, {
      method: 'POST',
    })
  },
  async queueVideoProxyRender(timelineId: string, options?: { force?: boolean }) {
    const query = options?.force ? '?force=1' : ''
    return request<VideoProxyPreviewResponse>(`/generate/video/timeline/${timelineId}/proxy${query}`, {
      method: 'POST',
    })
  },
  async getVideoProxyPreview(timelineId: string) {
    return request<VideoProxyPreviewResponse>(`/generate/video/timeline/${timelineId}/proxy`)
  },
  async getVideoAssetWaveform(assetId: string, options?: { samplePoints?: number; force?: boolean }) {
    const query = new URLSearchParams()
    if (options?.samplePoints) {
      query.set('sample_points', String(options.samplePoints))
    }
    if (options?.force) {
      query.set('force', '1')
    }
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request<VideoAssetWaveformResponse>(`/media/video-assets/${assetId}/waveform${suffix}`)
  },
  async listJobs(params?: {
    limit?: number
    offset?: number
    status?: string
    job_type?: string
    persona_id?: number
    search?: string
  }) {
    const query = new URLSearchParams()
    if (params) {
      appendSearchParams(query, params)
    }
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request<JobHistoryResponse>(`/jobs${suffix}`)
  },
  async getJob(jobId: string) {
    return request<JobDetail>(`/jobs/${jobId}`)
  },
  async cancelJob(jobId: string) {
    return request<{ message: string; job_id: string }>(`/jobs/${jobId}/cancel`, {
      method: 'POST',
    })
  },
  async retryJob(jobId: string) {
    return request<{ job_id: string; new_job_id: string; status: string; message: string }>(`/jobs/${jobId}/retry`, {
      method: 'POST',
    })
  },
  async getJobStats() {
    return request<JobStats>(`/jobs/stats`)
  },
  async listPersonas() {
    return request<Persona[]>(`/personas/`)
  },
  async createPersona(payload: PersonaCreatePayload) {
    return request<Persona>(`/personas/`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  async updatePersona(id: number, payload: PersonaUpdatePayload) {
    return request<Persona>(`/personas/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  },
  async deletePersona(id: number) {
    await request(`/personas/${id}`, { method: 'DELETE' })
  },
  async duplicatePersona(id: number, newName: string) {
    const query = new URLSearchParams({ new_name: newName })
    return request<Persona>(`/personas/${id}/duplicate?${query.toString()}`, {
      method: 'POST',
    })
  },
  async previewPersona(id: number) {
    return request<PersonaPreviewResponse>(`/personas/${id}/preview`)
  },
  async listMedia(filters?: MediaFilters) {
    const query = new URLSearchParams()
    if (filters) {
      appendSearchParams(query, filters)
    }
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request<MediaListResponse>(`/media${suffix}`)
  },
  async getMediaStats() {
    return request<MediaStatsResponse>(`/media/stats`)
  },
  async toggleMediaFavorite(id: string) {
    return request<{ media_id: string; is_favorite: boolean; message: string }>(`/media/${id}/favorite`, {
      method: 'PUT',
    })
  },
  async updateMediaTags(id: string, tags: string[]) {
    return request<{ media_id: string; tags: string[]; message: string }>(`/media/${id}/tags`, {
      method: 'PUT',
      body: JSON.stringify(tags),
    })
  },
  async deleteMedia(id: string) {
    await request(`/media/${id}`, { method: 'DELETE' })
  },
  async bulkMediaAction(payload: { action: string; media_ids: string[]; tags?: string[] }) {
    return request<MediaBulkActionResponse>(`/media/bulk-action`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  async getModelStatus() {
    return request<ModelStatus>(`/models/status`)
  },
  async listAvailableModels() {
    return request<ModelInfo[]>(`/models/available`)
  },
  async listLoraModels() {
    return request<LoRAModel[]>(`/models/lora`)
  },
  async downloadModel(modelId: string, priority: 'low' | 'normal' | 'high' = 'normal') {
    return request<{ message: string; model_id: string; estimated_time?: string }>(`/models/download`, {
      method: 'POST',
      body: JSON.stringify({ model_id: modelId, priority }),
    })
  },
  async deleteModel(modelId: string) {
    return request<{ message: string }>(`/models/${modelId}`, { method: 'DELETE' })
  },
  async reloadModels() {
    return request<{ message: string }>(`/models/reload`, { method: 'POST' })
  },
  async clearModelCache() {
    return request<{ message: string }>(`/models/clear-cache`, { method: 'POST' })
  },
  async getSettings() {
    return request<SettingsResponse>(`/settings/`)
  },
  async updateSettings(payload: SettingsUpdatePayload) {
    return request<SettingsResponse>(`/settings/`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  },
  async getNsfwSettings() {
    return request<NSFWSettingsPayload>(`/settings/nsfw`)
  },
  async updateNsfwSettings(payload: NSFWSettingsPayload) {
    return request<NSFWSettingsPayload>(`/settings/nsfw`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  },
  async getHealth() {
    return request<SystemHealthResponse>(`/health`)
  },
  async getSystemInfo() {
    return request<SystemInfoResponse>(`/system/info`)
  },
  async listSystemNotifications(params?: { limit?: number; offset?: number }) {
    const query = new URLSearchParams()
    appendSearchParams(query, {
      limit: params?.limit ?? 20,
      offset: params?.offset ?? 0,
    })
    return request<NotificationFeedResponse>(`/system/notifications?${query.toString()}`)
  },
}
