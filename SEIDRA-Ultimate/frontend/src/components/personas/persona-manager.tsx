'use client'

import { FormEvent, useEffect, useMemo, useState } from 'react'
import { toast } from 'react-hot-toast'

import { useModels, usePersonaPreview, usePersonas } from '@/lib/hooks'
import type { Persona } from '@/lib/api-client'

const EMPTY_FORM = {
  name: '',
  description: '',
  style_prompt: '',
  negative_prompt: '',
  lora_models: [] as string[],
  generation_params: {
    width: 768,
    height: 768,
    num_inference_steps: 25,
    guidance_scale: 7,
    scheduler: 'ddim',
    num_images: 1,
  } as Record<string, unknown>,
}

function normalisePersona(persona: Persona) {
  return {
    name: persona.name,
    description: persona.description ?? '',
    style_prompt: persona.style_prompt,
    negative_prompt: persona.negative_prompt ?? '',
    lora_models: Array.isArray(persona.lora_models) ? persona.lora_models : [],
    generation_params: persona.generation_params ?? {},
  }
}

export function PersonaManager() {
  const {
    personas,
    isLoading,
    error,
    createPersona,
    updatePersona,
    deletePersona,
    duplicatePersona,
    isMutating,
  } = usePersonas()
  const { models } = useModels()
  const { previewPersona, previewJob, isPreviewing, previewError } = usePersonaPreview()

  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [formState, setFormState] = useState(EMPTY_FORM)

  useEffect(() => {
    if (!selectedId) {
      setFormState(EMPTY_FORM)
      return
    }
    const persona = personas.find((entry) => entry.id === selectedId)
    if (!persona) return
    setFormState(normalisePersona(persona))
  }, [selectedId, personas])

  const filteredPersonas = useMemo(() => {
    if (!search) return personas
    return personas.filter((persona) => persona.name.toLowerCase().includes(search.toLowerCase()))
  }, [personas, search])

  const loraOptions = useMemo(
    () => models.filter((model) => model.type === 'lora'),
    [models],
  )

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const payload = {
      ...formState,
      lora_models: formState.lora_models ?? [],
      generation_params: formState.generation_params ?? {},
    }

    try {
      if (selectedId) {
        await updatePersona(selectedId, payload)
        toast.success('Persona updated')
      } else {
        const persona = await createPersona(payload)
        toast.success('Persona created')
        setSelectedId(persona.id)
      }
    } catch (err) {
      toast.error((err as Error).message)
    }
  }

  const handleDuplicate = async (persona: Persona) => {
    try {
      const copyName = `${persona.name} copy`
      const duplicate = await duplicatePersona(persona.id, copyName)
      toast.success(`Duplicated ${persona.name}`)
      setSelectedId(duplicate.id)
    } catch (err) {
      toast.error((err as Error).message)
    }
  }

  const handlePreview = async (persona: Persona) => {
    try {
      const job = await previewPersona(persona.id)
      const eta = typeof job.estimated_time === 'number' ? ` (ETA ~${job.estimated_time}s)` : ''
      toast.success(`Preview job ${job.job_id} ${job.status}.${eta}`)
    } catch (err) {
      toast.error((err as Error).message)
    }
  }

  const handleDelete = async (persona: Persona) => {
    const confirmation = window.confirm(`Delete persona “${persona.name}”?`)
    if (!confirmation) return
    try {
      await deletePersona(persona.id)
      toast.success(`Persona ${persona.name} deleted`)
      if (selectedId === persona.id) {
        setSelectedId(null)
        setFormState(EMPTY_FORM)
      }
    } catch (err) {
      toast.error((err as Error).message)
    }
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[320px_1fr]">
      <aside className="rounded-2xl border border-purple-500/30 bg-black/30 p-5 text-purple-100 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-yellow-200">Personas</h2>
          <span className="text-xs text-purple-300">{personas.length} saved</span>
        </div>
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search personas"
          className="mb-4 w-full rounded-lg border border-purple-500/40 bg-black/60 p-2 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
        />
        {isLoading && <p className="text-xs text-purple-300">Loading personas…</p>}
        {error && <p className="text-xs text-red-400">{error}</p>}
        <div className="space-y-3 text-sm text-purple-200">
          {filteredPersonas.map((persona) => (
            <article
              key={persona.id}
              className={`cursor-pointer rounded-xl border border-purple-500/30 p-4 transition hover:border-yellow-400/50 ${
                persona.id === selectedId ? 'bg-purple-900/40' : 'bg-black/40'
              }`}
              onClick={() => setSelectedId(persona.id)}
            >
              <h3 className="text-base font-semibold text-yellow-200">{persona.name}</h3>
              <p className="mt-1 line-clamp-3 text-xs text-purple-300">{persona.description || 'No description'}</p>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-purple-400">
                <button
                  type="button"
                  className="rounded border border-purple-500/40 px-2 py-0.5 hover:border-yellow-300 hover:text-yellow-200 disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={isPreviewing}
                  onClick={(event) => {
                    event.stopPropagation()
                    void handlePreview(persona)
                  }}
                >
                  {isPreviewing ? 'Previewing…' : 'Preview'}
                </button>
                <button
                  type="button"
                  className="rounded border border-purple-500/40 px-2 py-0.5 hover:border-yellow-300 hover:text-yellow-200"
                  onClick={(event) => {
                    event.stopPropagation()
                    void handleDuplicate(persona)
                  }}
                >
                  Duplicate
                </button>
                <button
                  type="button"
                  className="rounded border border-red-500/40 px-2 py-0.5 text-red-300 hover:border-red-300"
                  onClick={(event) => {
                    event.stopPropagation()
                    void handleDelete(persona)
                  }}
                >
                  Delete
                </button>
              </div>
            </article>
          ))}
          {filteredPersonas.length === 0 && !isLoading && (
            <p className="text-xs text-purple-300">No personas match this search.</p>
          )}
        </div>
      </aside>

      <section className="rounded-2xl border border-purple-500/30 bg-black/40 p-6 text-purple-100 shadow-xl">
        {previewError && (
          <p className="mb-4 rounded-lg border border-red-500/40 bg-red-900/30 p-3 text-xs text-red-300">{previewError}</p>
        )}
        {previewJob && (
          <div className="mb-4 rounded-lg border border-purple-500/40 bg-black/50 p-4 text-xs text-purple-200">
            <p className="font-semibold text-yellow-200">Preview job started</p>
            <p className="mt-1">Job ID: {previewJob.job_id}</p>
            <p className="mt-1 capitalize">Status: {previewJob.status}</p>
            {previewJob.message && <p className="mt-1">{previewJob.message}</p>}
            {typeof previewJob.estimated_time === 'number' && (
              <p className="mt-1">Estimated time: ~{previewJob.estimated_time}s</p>
            )}
          </div>
        )}
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-yellow-200">
              {selectedId ? 'Edit persona' : 'Create a persona'}
            </h2>
            <p className="text-xs text-purple-300">
              Craft reusable stylistic presets. Parameters are applied automatically when generating.
            </p>
          </div>
          {selectedId && (
            <button
              type="button"
              onClick={() => {
                setSelectedId(null)
                setFormState(EMPTY_FORM)
              }}
              className="rounded border border-purple-500/40 px-3 py-1 text-xs text-purple-200 hover:border-yellow-300 hover:text-yellow-200"
            >
              New persona
            </button>
          )}
        </div>

        <form className="space-y-6" onSubmit={handleSubmit}>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm text-purple-200">
              Name
              <input
                name="name"
                value={formState.name}
                onChange={(event) => setFormState((prev) => ({ ...prev, name: event.target.value }))}
                required
                className="rounded-lg border border-purple-500/40 bg-black/60 p-2 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-2 text-sm text-purple-200">
              Description
              <input
                name="description"
                value={formState.description}
                onChange={(event) => setFormState((prev) => ({ ...prev, description: event.target.value }))}
                className="rounded-lg border border-purple-500/40 bg-black/60 p-2 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
              />
            </label>
          </div>

          <label className="flex flex-col gap-2 text-sm text-purple-200">
            Style prompt
            <textarea
              name="style_prompt"
              value={formState.style_prompt}
              onChange={(event) => setFormState((prev) => ({ ...prev, style_prompt: event.target.value }))}
              required
              rows={3}
              className="rounded-lg border border-purple-500/40 bg-black/60 p-3 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
            />
          </label>

          <label className="flex flex-col gap-2 text-sm text-purple-200">
            Negative prompt
            <textarea
              name="negative_prompt"
              value={formState.negative_prompt}
              onChange={(event) => setFormState((prev) => ({ ...prev, negative_prompt: event.target.value }))}
              rows={2}
              className="rounded-lg border border-purple-500/40 bg-black/60 p-3 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
            />
          </label>

          <div className="space-y-4 rounded-xl border border-purple-500/30 bg-black/30 p-4">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-yellow-200">Generation defaults</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-2 text-xs text-purple-200">
                Width
                <input
                  type="number"
                  min={512}
                  max={2048}
                value={(formState.generation_params.width as number | undefined) ?? 768}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      generation_params: {
                        ...prev.generation_params,
                        width: Number(event.target.value),
                      },
                    }))
                  }
                  className="rounded-lg border border-purple-500/40 bg-black/60 p-2 focus:border-yellow-300 focus:outline-none"
                />
              </label>
              <label className="flex flex-col gap-2 text-xs text-purple-200">
                Height
                <input
                  type="number"
                  min={512}
                  max={2048}
                  value={(formState.generation_params.height as number | undefined) ?? 768}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      generation_params: {
                        ...prev.generation_params,
                        height: Number(event.target.value),
                      },
                    }))
                  }
                  className="rounded-lg border border-purple-500/40 bg-black/60 p-2 focus:border-yellow-300 focus:outline-none"
                />
              </label>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-2 text-xs text-purple-200">
                Steps
                <input
                  type="number"
                  min={10}
                  max={100}
                  value={(formState.generation_params.num_inference_steps as number | undefined) ?? 25}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      generation_params: {
                        ...prev.generation_params,
                        num_inference_steps: Number(event.target.value),
                      },
                    }))
                  }
                  className="rounded-lg border border-purple-500/40 bg-black/60 p-2 focus:border-yellow-300 focus:outline-none"
                />
              </label>
              <label className="flex flex-col gap-2 text-xs text-purple-200">
                Guidance
                <input
                  type="number"
                  min={1}
                  max={20}
                  step={0.5}
                  value={(formState.generation_params.guidance_scale as number | undefined) ?? 7}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      generation_params: {
                        ...prev.generation_params,
                        guidance_scale: Number(event.target.value),
                      },
                    }))
                  }
                  className="rounded-lg border border-purple-500/40 bg-black/60 p-2 focus:border-yellow-300 focus:outline-none"
                />
              </label>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-2 text-xs text-purple-200">
                Scheduler
                <input
                  type="text"
                  value={(formState.generation_params.scheduler as string | undefined) ?? 'ddim'}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      generation_params: {
                        ...prev.generation_params,
                        scheduler: event.target.value,
                      },
                    }))
                  }
                  className="rounded-lg border border-purple-500/40 bg-black/60 p-2 focus:border-yellow-300 focus:outline-none"
                />
              </label>
              <label className="flex flex-col gap-2 text-xs text-purple-200">
                Images per job
                <input
                  type="number"
                  min={1}
                  max={4}
                  value={(formState.generation_params.num_images as number | undefined) ?? 1}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      generation_params: {
                        ...prev.generation_params,
                        num_images: Number(event.target.value),
                      },
                    }))
                  }
                  className="rounded-lg border border-purple-500/40 bg-black/60 p-2 focus:border-yellow-300 focus:outline-none"
                />
              </label>
            </div>
          </div>

          <div className="rounded-xl border border-purple-500/30 bg-black/30 p-4">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-yellow-200">Preferred LoRA models</h3>
            {loraOptions.length === 0 && <p className="text-xs text-purple-300">No LoRA models available.</p>}
            <div className="grid gap-2 md:grid-cols-2">
              {loraOptions.map((model) => (
                <label key={model.id} className="flex items-center justify-between gap-3 rounded-lg border border-purple-500/20 bg-black/40 p-3 text-xs text-purple-200">
                  <span>
                    <span className="block text-sm text-purple-100">{model.name}</span>
                    <span className="text-[10px] text-purple-400">{model.category ?? model.type}</span>
                  </span>
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-purple-500/40 bg-black/60"
                    checked={formState.lora_models.includes(model.id)}
                    onChange={(event) => {
                      setFormState((prev) => ({
                        ...prev,
                        lora_models: event.target.checked
                          ? [...prev.lora_models, model.id]
                          : prev.lora_models.filter((entry) => entry !== model.id),
                      }))
                    }}
                  />
                </label>
              ))}
            </div>
          </div>

          <button
            type="submit"
            disabled={isMutating}
            className="rounded-lg bg-gradient-to-r from-purple-600 to-yellow-400 px-6 py-2 text-sm font-semibold text-black shadow-lg transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isMutating ? 'Saving…' : selectedId ? 'Update persona' : 'Create persona'}
          </button>
        </form>
      </section>
    </div>
  )
}
