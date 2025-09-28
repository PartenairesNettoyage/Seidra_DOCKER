'use client'

import React, { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import Image from 'next/image'
import { toast } from 'react-hot-toast'

import { ProgressBar } from '@/components/ui/progress-bar'
import {
  buildGenerationPayload,
  useModels,
  usePersonas,
  useVideoGeneration,
} from '@/lib/hooks'
import {
  apiClient,
  type JobItem,
  type ModelInfo,
  type ModelStatus,
  type Persona,
} from '@/lib/api-client'
import { extractJobMessages, mergeJobUpdates } from '@/lib/realtime-utils'
import { useWebSocketStatus, type JobRealtimeUpdate } from '@/lib/websocket-context'

const DEFAULT_PROMPT = 'A portrait of a celestial sorceress made of stardust'
const DEFAULT_NEGATIVE = 'low quality, blurry, distorted anatomy'
const SCHEDULERS = ['ddim', 'ddpm', 'euler_a', 'dpm++_2m']
const QUALITY_PRESETS = ['draft', 'standard', 'high']

const MAX_IMAGES = 4

function asNumber(value: unknown, fallback: number): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string') {
    const parsed = Number.parseInt(value, 10)
    return Number.isFinite(parsed) ? parsed : fallback
  }
  return fallback
}

type JobHistoryPanelProps = {
  jobs: JobItem[]
  jobMessages: Record<string, string | undefined>
}

type ImageGenerationPanelProps = {
  personas: Persona[]
  personasLoading: boolean
  personasError: string | null
  websocketStatus: string
  models: ModelInfo[]
  modelsLoading: boolean
  modelStatus: ModelStatus | null
  pendingModels: Set<string>
  downloadModel: (modelId: string) => Promise<void>
  onJobQueued: (update: JobRealtimeUpdate) => void
}

type VideoGenerationPanelProps = {
  onJobQueued: (update: JobRealtimeUpdate) => void
}

export function GenerationInterface() {
  const { personas, isLoading: personasLoading, error: personasError } = usePersonas()
  const {
    models,
    status: modelStatus,
    isLoading: modelsLoading,
    pending: pendingModels,
    downloadModel,
  } = useModels()

  const [jobs, setJobs] = useState<JobItem[]>([])
  const { status: websocketStatus, jobUpdates } = useWebSocketStatus()
  const jobMessages = useMemo(() => extractJobMessages(jobUpdates), [jobUpdates])

  useEffect(() => {
    apiClient
      .listJobs({ limit: 12 })
      .then((data) => setJobs(data.jobs ?? []))
      .catch(() => setJobs([]))
  }, [])

  useEffect(() => {
    const updates = Object.values(jobUpdates)
    if (updates.length === 0) return
    setJobs((previous) => mergeJobUpdates(previous, updates))
  }, [jobUpdates])

  const handleJobQueued = useCallback((update: JobRealtimeUpdate) => {
    setJobs((previous) => mergeJobUpdates(previous, [update]))
  }, [])

  return (
    <div className="space-y-8">
      <ImageGenerationPanel
        personas={personas}
        personasLoading={personasLoading}
        personasError={personasError}
        websocketStatus={websocketStatus}
        models={models}
        modelsLoading={modelsLoading}
        modelStatus={modelStatus}
        pendingModels={pendingModels}
        downloadModel={downloadModel}
        onJobQueued={handleJobQueued}
      />

      <VideoGenerationPanel onJobQueued={handleJobQueued} />

      <JobHistoryPanel jobs={jobs} jobMessages={jobMessages} />
    </div>
  )
}

function ImageGenerationPanel({
  personas,
  personasLoading,
  personasError,
  websocketStatus,
  models,
  modelsLoading,
  modelStatus,
  pendingModels,
  downloadModel,
  onJobQueued,
}: ImageGenerationPanelProps) {
  const [selectedPersonaId, setSelectedPersonaId] = useState<number | null>(null)
  const [syncPersonaPrompt, setSyncPersonaPrompt] = useState(true)
  const [syncPersonaSettings, setSyncPersonaSettings] = useState(true)
  const [syncPersonaLoras, setSyncPersonaLoras] = useState(true)
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT)
  const [negativePrompt, setNegativePrompt] = useState(DEFAULT_NEGATIVE)
  const [selectedModelId, setSelectedModelId] = useState('sdxl-base')
  const [selectedLoras, setSelectedLoras] = useState<string[]>([])
  const [imageCount, setImageCount] = useState(1)
  const [width, setWidth] = useState(768)
  const [height, setHeight] = useState(768)
  const [steps, setSteps] = useState(25)
  const [guidance, setGuidance] = useState(7)
  const [scheduler, setScheduler] = useState(SCHEDULERS[0])
  const [quality, setQuality] = useState<'draft' | 'standard' | 'high'>('high')
  const [seed, setSeed] = useState<string>('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)

  const baseModels = useMemo(
    () => models.filter((model) => model.type === 'base'),
    [models],
  )
  const loraModels = useMemo(
    () => models.filter((model) => model.type === 'lora'),
    [models],
  )

  const selectedPersona = useMemo(
    () => personas.find((persona) => persona.id === selectedPersonaId) ?? null,
    [personas, selectedPersonaId],
  )

  useEffect(() => {
    if (!selectedPersonaId && personas.length > 0) {
      setSelectedPersonaId(personas[0]?.id ?? null)
    }
  }, [personas, selectedPersonaId])

  useEffect(() => {
    if (!selectedPersona) return

    if (syncPersonaPrompt) {
      setPrompt(selectedPersona.style_prompt)
      setNegativePrompt(selectedPersona.negative_prompt || DEFAULT_NEGATIVE)
    }

    if (syncPersonaSettings) {
      const params = selectedPersona.generation_params ?? {}
      if (typeof params.width === 'number') setWidth(params.width)
      if (typeof params.height === 'number') setHeight(params.height)
      if (typeof params.num_inference_steps === 'number') setSteps(params.num_inference_steps)
      if (typeof params.guidance_scale === 'number') setGuidance(params.guidance_scale)
      if (typeof params.scheduler === 'string') setScheduler(params.scheduler)
      if (typeof params.quality === 'string') {
        const normalized = params.quality as 'draft' | 'standard' | 'high'
        if (QUALITY_PRESETS.includes(normalized)) {
          setQuality(normalized)
        }
      }
      if (typeof params.num_images === 'number') {
        setImageCount(Math.min(MAX_IMAGES, Math.max(1, params.num_images)))
      }
      if (typeof params.seed === 'number') {
        setSeed(String(params.seed))
      }
      if (typeof params.model_name === 'string') {
        setSelectedModelId(params.model_name)
      }
    }

    if (syncPersonaLoras) {
      const personaLoras = Array.isArray(selectedPersona.lora_models)
        ? selectedPersona.lora_models
        : []
      if (personaLoras.length > 0) {
        setSelectedLoras((prev) => {
          const unique = new Set(prev)
          for (const entry of personaLoras) {
            if (typeof entry === 'string' && entry.length > 0) {
              unique.add(entry)
            }
          }
          return Array.from(unique)
        })
      }
    }
  }, [selectedPersona, syncPersonaPrompt, syncPersonaSettings, syncPersonaLoras])

  const toggleLoraSelection = useCallback((loraId: string) => {
    setSelectedLoras((prev) =>
      prev.includes(loraId) ? prev.filter((entry) => entry !== loraId) : [...prev, loraId],
    )
  }, [])

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      if (!prompt.trim()) {
        toast.error('Prompt cannot be empty')
        return
      }
      setIsSubmitting(true)
      try {
        const payload = buildGenerationPayload(
          {
            prompt,
            negative_prompt: negativePrompt,
            width,
            height,
            num_inference_steps: steps,
            guidance_scale: guidance,
            num_images: imageCount,
            persona_id: selectedPersonaId ?? undefined,
            lora_models: selectedLoras,
            seed: seed.trim().length ? Number(seed) : undefined,
            model_name: selectedModelId,
            scheduler,
            quality,
            metadata: {
              ui: 'seidra-ultimate',
              personaName: selectedPersona?.name ?? null,
              requestedAt: new Date().toISOString(),
            },
          },
          {
            prompt: DEFAULT_PROMPT,
            negative_prompt: DEFAULT_NEGATIVE,
            width: 768,
            height: 768,
            num_inference_steps: 30,
            guidance_scale: 7.5,
            num_images: 1,
            model_name: 'sdxl-base',
            scheduler: 'ddim',
            quality: 'high',
          },
        )

        const response = await apiClient.generateImage(payload)
        const createdAt = new Date().toISOString()
        onJobQueued({
          jobId: response.job_id,
          status: 'queued',
          progress: 0,
          jobType: payload.job_type ?? 'image',
          modelName: payload.model_name ?? 'sdxl-base',
          message: 'Queued locally – awaiting worker',
          metadata: {
            prompt: payload.prompt,
            personaId: payload.persona_id,
            createdAt,
          },
        })
        toast.success('Generation job queued')
      } catch (error) {
        toast.error((error as Error).message)
        console.error(error)
      } finally {
        setIsSubmitting(false)
      }
    },
    [
      prompt,
      negativePrompt,
      width,
      height,
      steps,
      guidance,
      imageCount,
      selectedPersonaId,
      selectedLoras,
      seed,
      selectedModelId,
      scheduler,
      quality,
      selectedPersona?.name,
      onJobQueued,
    ],
  )

  const personaOptions = useMemo(() => {
    if (personas.length === 0) return []
    return personas.map((persona) => ({
      id: persona.id,
      label: persona.name,
    }))
  }, [personas])

  const personaMetadata = selectedPersona?.generation_params ?? {}

  return (
    <section className="rounded-2xl border border-purple-500/30 bg-black/40 p-6 text-purple-100 shadow-xl">
      <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold text-yellow-200">Create new artwork</h2>
          <p className="text-xs text-purple-300">
            Realtime channel status:{' '}
            <span className="font-semibold text-yellow-200">{websocketStatus}</span>
          </p>
        </div>
        {modelStatus && (
          <div className="grid gap-1 text-right text-xs text-purple-300">
            <span>Loaded models: {modelStatus.loaded_models.length}</span>
            <span>Cache: {modelStatus.cache_size}</span>
            <span>Optimal batch size: {modelStatus.optimal_batch_size}</span>
          </div>
        )}
      </div>

      <div className="grid gap-8 lg:grid-cols-[420px_1fr]">
        <form className="space-y-6" onSubmit={handleSubmit}>
          <div className="space-y-4">
            <label className="block text-sm font-medium text-purple-200">Persona</label>
            <select
              value={selectedPersonaId ?? ''}
              onChange={(event) =>
                setSelectedPersonaId(event.target.value ? Number(event.target.value) : null)
              }
              className="w-full rounded-lg border border-purple-500/40 bg-black/60 p-3 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
            >
              <option value="">Custom setup</option>
              {personaOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
            {(personasLoading || modelsLoading) && (
              <p className="text-xs text-purple-300">Loading personas &amp; models…</p>
            )}
            {personasError && <p className="text-xs text-red-400">{personasError}</p>}
          </div>

          <div className="flex items-center gap-3 text-xs text-purple-300">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={syncPersonaPrompt}
                onChange={() => setSyncPersonaPrompt((prev) => !prev)}
              />
              Sync prompt
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={syncPersonaSettings}
                onChange={() => setSyncPersonaSettings((prev) => !prev)}
              />
              Sync settings
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={syncPersonaLoras}
                onChange={() => setSyncPersonaLoras((prev) => !prev)}
              />
              Sync LoRAs
            </label>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-2 block text-sm font-medium text-purple-200">Base model</label>
              <select
                value={selectedModelId}
                onChange={(event) => setSelectedModelId(event.target.value)}
                className="w-full rounded-lg border border-purple-500/40 bg-black/60 p-3 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
              >
                {baseModels.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.name} {model.is_downloaded ? '' : '(remote)'}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium text-purple-200">Images per job</label>
              <input
                type="number"
                min={1}
                max={MAX_IMAGES}
                value={imageCount}
                onChange={(event) => setImageCount(asNumber(event.target.value, 1))}
                className="w-full rounded-lg border border-purple-500/40 bg-black/60 p-3 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-purple-200">Prompt</label>
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              className="w-full rounded-lg border border-purple-500/40 bg-black/60 p-3 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
              rows={3}
              required
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-purple-200">Negative prompt</label>
            <textarea
              value={negativePrompt}
              onChange={(event) => setNegativePrompt(event.target.value)}
              className="w-full rounded-lg border border-purple-500/40 bg-black/60 p-3 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
              rows={2}
            />
          </div>

          <div className="space-y-3 rounded-xl border border-purple-500/30 bg-black/30 p-4">
            <button
              type="button"
              className="flex w-full items-center justify-between text-sm font-semibold text-yellow-200"
              onClick={() => setShowAdvanced((prev) => !prev)}
            >
              Advanced parameters
              <span className="text-xs text-purple-300">{showAdvanced ? 'Hide' : 'Show'}</span>
            </button>

            {showAdvanced && (
              <div className="space-y-4 text-sm text-purple-200">
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="flex flex-col gap-2">
                    <span>Width</span>
                    <input
                      type="number"
                      min={512}
                      max={2048}
                      value={width}
                      onChange={(event) => setWidth(asNumber(event.target.value, width))}
                      className="rounded-lg border border-purple-500/40 bg-black/60 p-2 focus:border-yellow-300 focus:outline-none"
                    />
                  </label>
                  <label className="flex flex-col gap-2">
                    <span>Height</span>
                    <input
                      type="number"
                      min={512}
                      max={2048}
                      value={height}
                      onChange={(event) => setHeight(asNumber(event.target.value, height))}
                      className="rounded-lg border border-purple-500/40 bg-black/60 p-2 focus:border-yellow-300 focus:outline-none"
                    />
                  </label>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="flex flex-col gap-2">
                    <span>Inference steps</span>
                    <input
                      type="number"
                      min={10}
                      max={100}
                      value={steps}
                      onChange={(event) => setSteps(asNumber(event.target.value, steps))}
                      className="rounded-lg border border-purple-500/40 bg-black/60 p-2 focus:border-yellow-300 focus:outline-none"
                    />
                  </label>
                  <label className="flex flex-col gap-2">
                    <span>Guidance scale</span>
                    <input
                      type="number"
                      min={1}
                      max={20}
                      step={0.5}
                      value={guidance}
                      onChange={(event) => setGuidance(Number(event.target.value))}
                      className="rounded-lg border border-purple-500/40 bg-black/60 p-2 focus:border-yellow-300 focus:outline-none"
                    />
                  </label>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="flex flex-col gap-2">
                    <span>Scheduler</span>
                    <select
                      value={scheduler}
                      onChange={(event) => setScheduler(event.target.value)}
                      className="rounded-lg border border-purple-500/40 bg-black/60 p-2 focus:border-yellow-300 focus:outline-none"
                    >
                      {SCHEDULERS.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-2">
                    <span>Quality preset</span>
                    <select
                      value={quality}
                      onChange={(event) => setQuality(event.target.value as typeof quality)}
                      className="rounded-lg border border-purple-500/40 bg-black/60 p-2 focus:border-yellow-300 focus:outline-none"
                    >
                      {QUALITY_PRESETS.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <label className="flex flex-col gap-2">
                  <span>Seed (optional)</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={seed}
                    onChange={(event) => setSeed(event.target.value)}
                    className="rounded-lg border border-purple-500/40 bg-black/60 p-2 focus:border-yellow-300 focus:outline-none"
                  />
                </label>
              </div>
            )}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg bg-gradient-to-r from-yellow-400 to-amber-500 p-3 text-sm font-semibold text-black shadow-lg transition hover:from-yellow-300 hover:to-amber-400 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isSubmitting ? 'Queuing…' : 'Generate artwork'}
          </button>
        </form>

        <aside className="space-y-6 text-sm text-purple-200">
          {selectedPersona ? (
            <div className="rounded-2xl border border-purple-500/30 bg-black/30 p-4">
              <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-yellow-200">
                Persona insights
              </h3>
              <p className="text-xs text-purple-300">Latest parameters synced from persona.</p>
              <ul className="mt-3 space-y-1">
                {Object.entries(personaMetadata).slice(0, 6).map(([key, value]) => (
                  <li key={key} className="flex items-center justify-between">
                    <span className="text-purple-300">{key}</span>
                    <span className="text-purple-100">{String(value)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-xs text-purple-300">Select a persona to preload style settings.</p>
          )}

          <div className="rounded-2xl border border-purple-500/30 bg-black/30 p-4 text-sm text-purple-200">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-yellow-200">LoRA presets</h3>
              <button
                type="button"
                className="text-xs text-purple-300 hover:text-yellow-200"
                onClick={() => setSelectedLoras([])}
              >
                Clear
              </button>
            </div>
            {loraModels.length === 0 && (
              <p className="text-xs text-purple-300">No LoRA presets available yet.</p>
            )}
            <div className="space-y-2">
              {loraModels.map((model) => (
                <label
                  key={model.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-purple-500/20 bg-black/40 p-3"
                >
                  <div>
                    <p className="font-semibold text-yellow-200">{model.name}</p>
                    <p className="text-[11px] text-purple-300">{model.category ?? model.type} · {model.size}</p>
                  </div>
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-purple-500/50 bg-black/60"
                    checked={selectedLoras.includes(model.id)}
                    onChange={() => toggleLoraSelection(model.id)}
                  />
                </label>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-purple-500/30 bg-black/30 p-4 text-sm text-purple-200">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-yellow-200">Model downloads</h3>
            <div className="space-y-2 text-xs text-purple-300">
              {models.map((model) => (
                <div
                  key={model.id}
                  className="flex items-center justify-between rounded-lg border border-purple-500/20 bg-black/40 p-3"
                >
                  <div>
                    <p className="text-sm text-purple-100">{model.name}</p>
                    <p className="text-[11px] text-purple-300">{model.type.toUpperCase()} · {model.size}</p>
                  </div>
                  {model.is_downloaded ? (
                    <span className="text-xs text-green-300">Ready</span>
                  ) : (
                    <button
                      type="button"
                      className="text-xs text-yellow-200 hover:text-yellow-100"
                      disabled={pendingModels.has(model.id)}
                      onClick={() => {
                        toast.promise(downloadModel(model.id), {
                          loading: 'Downloading…',
                          success: 'Download queued',
                          error: 'Failed to download',
                        })
                      }}
                    >
                      {pendingModels.has(model.id) ? 'Queued…' : 'Download'}
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </section>
  )
}

function VideoGenerationPanel({ onJobQueued }: VideoGenerationPanelProps) {
  const {
    prompt,
    setPrompt,
    referenceImage,
    setReferenceImage,
    durationSeconds,
    setDurationSeconds,
    audioFile,
    setAudioFile,
    isSubmitting,
    submit,
    minDuration,
    maxDuration,
  } = useVideoGeneration({ onQueued: onJobQueued })

  const handleAudioChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0] ?? null
      if (file && !file.type.startsWith('audio/')) {
        toast.error('Audio file must be in a supported audio format')
        event.target.value = ''
        setAudioFile(null)
        return
      }
      setAudioFile(file)
    },
    [setAudioFile],
  )

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      try {
        await submit()
        toast.success('Video generation job queued')
      } catch (error) {
        toast.error((error as Error).message)
      }
    },
    [submit],
  )

  return (
    <section className="rounded-2xl border border-cyan-500/30 bg-black/40 p-6 text-cyan-100 shadow-xl">
      <h2 className="mb-6 text-xl font-semibold text-cyan-200">Bring characters to life</h2>
      <form className="grid gap-6 lg:grid-cols-[420px_1fr]" onSubmit={handleSubmit}>
        <div className="space-y-4">
          <div>
            <label htmlFor="videoPrompt" className="mb-2 block text-sm font-medium text-cyan-100">
              Video prompt
            </label>
            <textarea
              id="videoPrompt"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              className="w-full rounded-lg border border-cyan-500/40 bg-black/60 p-3 text-sm text-cyan-50 focus:border-cyan-200 focus:outline-none"
              rows={3}
              required
            />
          </div>

          <div>
            <label
              htmlFor="videoReference"
              className="mb-2 block text-sm font-medium text-cyan-100"
            >
              Reference image URL (optional)
            </label>
            <input
              id="videoReference"
              type="url"
              value={referenceImage}
              onChange={(event) => setReferenceImage(event.target.value)}
              placeholder="https://example.com/reference.png"
              className="w-full rounded-lg border border-cyan-500/40 bg-black/60 p-3 text-sm text-cyan-50 focus:border-cyan-200 focus:outline-none"
            />
          </div>

          <div>
            <label htmlFor="videoAudio" className="mb-2 block text-sm font-medium text-cyan-100">
              Audio track
            </label>
            <input
              id="videoAudio"
              type="file"
              accept="audio/*"
              onChange={handleAudioChange}
              className="w-full text-sm text-cyan-50"
            />
            {audioFile ? (
              <p className="mt-2 text-xs text-cyan-200">Selected: {audioFile.name}</p>
            ) : (
              <p className="mt-2 text-xs text-cyan-300">Upload narration or dialogue to animate lip-sync.</p>
            )}
          </div>

          <div>
            <label htmlFor="videoDuration" className="mb-2 block text-sm font-medium text-cyan-100">
              Duration (seconds)
            </label>
            <input
              id="videoDuration"
              type="number"
              min={minDuration}
              max={maxDuration}
              value={durationSeconds}
              onChange={(event) => setDurationSeconds(Number(event.target.value))}
              className="w-full rounded-lg border border-cyan-500/40 bg-black/60 p-3 text-sm text-cyan-50 focus:border-cyan-200 focus:outline-none"
            />
            <p className="mt-1 text-xs text-cyan-300">
              Recommended range: {minDuration} to {maxDuration} seconds.
            </p>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg bg-gradient-to-r from-cyan-400 to-blue-500 p-3 text-sm font-semibold text-black shadow-lg transition hover:from-cyan-300 hover:to-blue-400 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isSubmitting ? 'Queuing…' : 'Generate video'}
          </button>
        </div>

        <div className="rounded-2xl border border-cyan-500/20 bg-black/30 p-5 text-sm text-cyan-50">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-cyan-200">
            Tips for expressive videos
          </h3>
          <ul className="space-y-2 text-xs text-cyan-100">
            <li>Use vivid prompts to describe the character, emotion, and lighting.</li>
            <li>Keep the audio clip clean—remove background noise before uploading.</li>
            <li>Reference images help preserve identity across multiple shots.</li>
          </ul>
        </div>
      </form>
    </section>
  )
}

function JobHistoryPanel({ jobs, jobMessages }: JobHistoryPanelProps) {
  return (
    <section className="rounded-2xl border border-purple-500/30 bg-black/30 p-6 text-purple-100 shadow-xl">
      <h2 className="mb-4 text-xl font-semibold text-yellow-200">Recent jobs</h2>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {jobs.length === 0 && (
          <p className="text-sm text-purple-300">No jobs yet. Launch a generation to see results.</p>
        )}
        {jobs.map((job) => {
          const outputs = job.result_images ?? []
          return (
            <article key={job.job_id} className="rounded-xl border border-purple-500/30 bg-black/40 p-4">
              <div className="flex items-center justify-between text-sm">
                <span className="font-semibold text-yellow-200">{job.status.toUpperCase()}</span>
                <span className="text-xs text-purple-300">{new Date(job.created_at).toLocaleString()}</span>
              </div>
              <ProgressBar value={job.progress ?? 0} status={job.status} className="mt-3" />
              {jobMessages[job.job_id] && (
                <p className="mt-2 text-xs text-purple-300">{jobMessages[job.job_id]}</p>
              )}
              {outputs.length > 0 && (
                <div className="mt-3 space-y-2">
                  {outputs.map((output) => {
                    const fileName = output.split('/').pop() ?? output
                    const src = `/media/${fileName}`
                    const isVideo = /\.(mp4|mov|webm)$/i.test(fileName)
                    return isVideo ? (
                      <video
                        key={output}
                        src={src}
                        controls
                        className="w-full rounded-lg border border-purple-500/40"
                      />
                    ) : (
                      <Image
                        key={output}
                        src={src}
                        alt="Generated artwork"
                        width={512}
                        height={512}
                        className="w-full rounded-lg border border-purple-500/40 object-cover"
                        unoptimized
                      />
                    )
                  })}
                </div>
              )}
            </article>
          )
        })}
      </div>
    </section>
  )
}
