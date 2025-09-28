'use client'

import { useMemo, useState } from 'react'
import { toast } from 'react-hot-toast'

import { useModels } from '@/lib/hooks'

export function ModelManager() {
  const {
    models,
    status,
    isLoading,
    error,
    pending,
    downloadModel,
    deleteModel,
    reloadModels,
    clearModelCache,
  } = useModels()

  const [search, setSearch] = useState('')

  const filteredModels = useMemo(() => {
    if (!search) return models
    return models.filter((model) => model.name.toLowerCase().includes(search.toLowerCase()))
  }, [models, search])

  const baseModels = useMemo(() => filteredModels.filter((model) => model.type === 'base'), [filteredModels])
  const loraModels = useMemo(() => filteredModels.filter((model) => model.type === 'lora'), [filteredModels])

  return (
    <div className="space-y-8">
      <section className="rounded-2xl border border-purple-500/30 bg-black/40 p-6 text-purple-100 shadow-xl">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-yellow-200">Runtime status</h2>
            {error && <p className="text-xs text-red-400">{error}</p>}
            {isLoading && <p className="text-xs text-purple-300">Loading model status…</p>}
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-purple-300">
            <button
              type="button"
              className="rounded border border-purple-500/40 px-3 py-1 text-purple-200 hover:border-yellow-300 hover:text-yellow-200"
              onClick={() => toast.promise(reloadModels(), {
                loading: 'Reloading models…',
                success: 'Models reloaded',
                error: 'Failed to reload',
              })}
            >
              Reload models
            </button>
            <button
              type="button"
              className="rounded border border-purple-500/40 px-3 py-1 text-purple-200 hover:border-yellow-300 hover:text-yellow-200"
              onClick={() => toast.promise(clearModelCache(), {
                loading: 'Clearing cache…',
                success: 'Cache cleared',
                error: 'Failed to clear cache',
              })}
            >
              Clear cache
            </button>
          </div>
        </div>

        {status ? (
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-xl border border-purple-500/30 bg-black/30 p-4 text-sm text-purple-200">
              <p className="text-xs font-semibold uppercase tracking-wide text-yellow-200">Loaded pipelines</p>
              <p className="mt-2 text-2xl font-semibold text-yellow-200">{status.loaded_models.length}</p>
              <p className="text-xs text-purple-300">{status.loaded_models.join(', ') || 'None'}</p>
            </div>
            <div className="rounded-xl border border-purple-500/30 bg-black/30 p-4 text-sm text-purple-200">
              <p className="text-xs font-semibold uppercase tracking-wide text-yellow-200">Available LoRAs</p>
              <p className="mt-2 text-2xl font-semibold text-yellow-200">{status.available_loras.length}</p>
              <p className="text-xs text-purple-300">{status.available_loras.join(', ') || 'None'}</p>
            </div>
            <div className="rounded-xl border border-purple-500/30 bg-black/30 p-4 text-sm text-purple-200">
              <p className="text-xs font-semibold uppercase tracking-wide text-yellow-200">GPU cache</p>
              <p className="mt-2 text-2xl font-semibold text-yellow-200">{status.cache_size}</p>
              <p className="text-xs text-purple-300">Optimal batch size: {status.optimal_batch_size}</p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-purple-300">No runtime metrics available.</p>
        )}
      </section>

      <section className="rounded-2xl border border-purple-500/30 bg-black/30 p-6 text-purple-100 shadow-xl">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-xl font-semibold text-yellow-200">Model catalogue</h2>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search models"
            className="w-full max-w-xs rounded-lg border border-purple-500/40 bg-black/60 p-2 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
          />
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <div className="rounded-2xl border border-purple-500/30 bg-black/30 p-5">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-yellow-200">Base pipelines</h3>
            <div className="space-y-3 text-sm text-purple-200">
              {baseModels.map((model) => (
                <div key={model.id} className="rounded-xl border border-purple-500/20 bg-black/40 p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-base font-semibold text-yellow-200">{model.name}</p>
                      <p className="text-xs text-purple-300">{model.description}</p>
                    </div>
                    <span className="text-xs text-purple-300">{model.size}</span>
                  </div>
                  <p className="mt-2 text-xs text-purple-300">{model.tags?.join(', ')}</p>
                  {!model.is_downloaded && model.download_url && (
                    <button
                      type="button"
                      className="mt-3 rounded border border-purple-500/40 px-3 py-1 text-xs text-yellow-200 hover:border-yellow-300 hover:text-yellow-100"
                      disabled={pending.has(model.id)}
                      onClick={() =>
                        toast.promise(downloadModel(model.id), {
                          loading: 'Downloading…',
                          success: 'Download queued',
                          error: 'Failed to download',
                        })
                      }
                    >
                      {pending.has(model.id) ? 'Pending…' : 'Download preset'}
                    </button>
                  )}
                </div>
              ))}
              {baseModels.length === 0 && <p className="text-xs text-purple-300">No base models found.</p>}
            </div>
          </div>

          <div className="rounded-2xl border border-purple-500/30 bg-black/30 p-5">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-yellow-200">LoRA presets</h3>
            <div className="space-y-3 text-sm text-purple-200">
              {loraModels.map((model) => (
                <div key={model.id} className="rounded-xl border border-purple-500/20 bg-black/40 p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-base font-semibold text-yellow-200">{model.name}</p>
                      <p className="text-xs text-purple-300">{model.description}</p>
                    </div>
                    <span className="text-xs text-purple-300">{model.size}</span>
                  </div>
                  <p className="mt-2 text-xs text-purple-300">Tags: {model.tags?.join(', ') || '—'}</p>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs text-purple-300">
                    {model.is_downloaded ? (
                      <button
                        type="button"
                        className="rounded border border-red-500/40 px-3 py-1 text-red-300 hover:border-red-300"
                        disabled={pending.has(model.id)}
                        onClick={() =>
                          toast.promise(deleteModel(model.id), {
                            loading: 'Removing…',
                            success: 'Model removed',
                            error: 'Failed to remove',
                          })
                        }
                      >
                        {pending.has(model.id) ? 'Removing…' : 'Remove local copy'}
                      </button>
                    ) : model.download_url ? (
                      <button
                        type="button"
                        className="rounded border border-purple-500/40 px-3 py-1 text-yellow-200 hover:border-yellow-300 hover:text-yellow-100"
                        disabled={pending.has(model.id)}
                        onClick={() =>
                          toast.promise(downloadModel(model.id), {
                            loading: 'Downloading…',
                            success: 'Download queued',
                            error: 'Failed to download',
                          })
                        }
                      >
                        {pending.has(model.id) ? 'Pending…' : 'Download'}
                      </button>
                    ) : (
                      <span className="rounded border border-purple-500/40 px-3 py-1 text-purple-300">Remote only</span>
                    )}
                  </div>
                </div>
              ))}
              {loraModels.length === 0 && <p className="text-xs text-purple-300">No LoRA presets match this search.</p>}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
