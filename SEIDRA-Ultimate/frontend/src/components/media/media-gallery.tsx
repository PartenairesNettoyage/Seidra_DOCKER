'use client'

import Image from 'next/image'
import { FormEvent, useMemo, useState } from 'react'
import { toast } from 'react-hot-toast'

import { useMediaLibrary, usePersonas } from '@/lib/hooks'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api'

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString()
}

export function MediaGallery() {
  const { personas } = usePersonas()
  const {
    media,
    total,
    stats,
    isLoading,
    error,
    applyFilters,
    loadMore,
    refresh,
    toggleFavorite,
    updateTags,
    deleteMedia,
  } = useMediaLibrary(12)

  const [search, setSearch] = useState('')
  const [personaFilter, setPersonaFilter] = useState('')
  const [favoritesOnly, setFavoritesOnly] = useState(false)
  const [tagsFilter, setTagsFilter] = useState('')

  const handleFilterSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    applyFilters({
      search: search || undefined,
      persona_id: personaFilter ? Number(personaFilter) : undefined,
      favorites_only: favoritesOnly,
      tags: tagsFilter ? tagsFilter.split(',').map((tag) => tag.trim()).filter(Boolean) : undefined,
      offset: 0,
    })
  }

  const resetFilters = () => {
    setSearch('')
    setPersonaFilter('')
    setFavoritesOnly(false)
    setTagsFilter('')
    applyFilters({
      search: undefined,
      persona_id: undefined,
      favorites_only: false,
      tags: undefined,
      offset: 0,
    })
  }

  const totalFavorites = stats?.favorites_count ?? 0
  const recentCount = stats?.recent_count ?? 0

  const personaMap = useMemo(() => {
    const map = new Map<number, string>()
    for (const persona of personas) {
      map.set(persona.id, persona.name)
    }
    return map
  }, [personas])

  return (
    <section className="space-y-6">
      <div className="rounded-2xl border border-purple-500/30 bg-black/40 p-6 text-purple-100 shadow-xl">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-yellow-200">Gallery overview</h2>
            <p className="text-xs text-purple-300">
              {stats
                ? `Total images: ${stats.total_images} · Favorites: ${totalFavorites} · Recent week: ${recentCount}`
                : 'Loading statistics…'}
            </p>
            {error && <p className="text-xs text-red-400">{error}</p>}
          </div>
          <button
            type="button"
            onClick={() => refresh()}
            className="rounded border border-purple-500/40 px-3 py-1 text-xs text-purple-200 hover:border-yellow-300 hover:text-yellow-200"
          >
            Refresh
          </button>
        </div>

        <form className="grid gap-4 md:grid-cols-[repeat(5,minmax(0,1fr))]" onSubmit={handleFilterSubmit}>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search caption or tags"
            className="rounded-lg border border-purple-500/40 bg-black/60 p-2 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
          />
          <input
            value={tagsFilter}
            onChange={(event) => setTagsFilter(event.target.value)}
            placeholder="Tags (comma separated)"
            className="rounded-lg border border-purple-500/40 bg-black/60 p-2 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
          />
          <select
            value={personaFilter}
            onChange={(event) => setPersonaFilter(event.target.value)}
            className="rounded-lg border border-purple-500/40 bg-black/60 p-2 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
          >
            <option value="">All personas</option>
            {personas.map((persona) => (
              <option key={persona.id} value={persona.id}>
                {persona.name}
              </option>
            ))}
          </select>
          <label className="flex items-center justify-center gap-2 text-xs text-purple-200">
            <input
              type="checkbox"
              checked={favoritesOnly}
              onChange={(event) => setFavoritesOnly(event.target.checked)}
              className="h-4 w-4 rounded border-purple-500/40 bg-black/60"
            />
            Favorites only
          </label>
          <div className="flex items-center gap-2">
            <button
              type="submit"
              className="flex-1 rounded-lg bg-gradient-to-r from-purple-600 to-yellow-400 px-3 py-2 text-xs font-semibold text-black shadow-lg hover:opacity-90"
            >
              Apply filters
            </button>
            <button
              type="button"
              onClick={resetFilters}
              className="rounded-lg border border-purple-500/40 px-3 py-2 text-xs text-purple-200 hover:border-yellow-300 hover:text-yellow-200"
            >
              Reset
            </button>
          </div>
        </form>
      </div>

      <div className="rounded-2xl border border-purple-500/30 bg-black/30 p-6 text-purple-100 shadow-xl">
        <h3 className="mb-4 text-xl font-semibold text-yellow-200">Latest creations</h3>
        {media.length === 0 && !isLoading && <p className="text-sm text-purple-300">No media match the current filters.</p>}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {media.map((item) => (
            <figure key={item.id} className="rounded-xl border border-purple-500/30 bg-black/40 p-3">
              <Image
                src={`/media/${item.file_path.split('/').pop() ?? item.file_path}`}
                alt={String(item.metadata?.prompt ?? 'Generated artwork')}
                width={512}
                height={512}
                className="mb-2 w-full rounded-lg border border-purple-500/40 object-cover"
                unoptimized
              />
              <figcaption className="space-y-2 text-xs text-purple-300">
                <div className="flex items-center justify-between">
                  <span>{formatDate(item.created_at)}</span>
                  <button
                    type="button"
                    onClick={() =>
                      toast.promise(toggleFavorite(item.id), {
                        loading: 'Updating…',
                        success: (isFav) => (isFav ? 'Added to favorites' : 'Removed from favorites'),
                        error: 'Failed to toggle favorite',
                      })
                    }
                    className={`rounded px-2 py-1 text-[11px] font-semibold ${
                      item.is_favorite
                        ? 'border border-yellow-300 text-yellow-200'
                        : 'border border-purple-500/40 text-purple-200'
                    }`}
                  >
                    {item.is_favorite ? 'Favorited' : 'Favorite'}
                  </button>
                </div>
                <p className="text-purple-200">
                  Persona:{' '}
                  {
                    (item.metadata?.persona_name as string | undefined) ??
                      (item.metadata?.personaName as string | undefined) ??
                      (typeof item.metadata?.persona_id === 'number'
                        ? personaMap.get(item.metadata.persona_id as number)
                        : '—') ??
                      '—'
                  }
                </p>
                {item.tags.length > 0 && (
                  <p className="text-purple-200">Tags: {item.tags.join(', ')}</p>
                )}
                <div className="flex gap-2">
                  <input
                    type="text"
                    defaultValue={item.tags.join(', ')}
                    onBlur={(event) =>
                      event.target.value !== item.tags.join(', ')
                        ? toast.promise(
                            updateTags(
                              item.id,
                              event.target.value
                                .split(',')
                                .map((tag) => tag.trim())
                                .filter(Boolean),
                            ),
                            {
                              loading: 'Updating tags…',
                              success: 'Tags updated',
                              error: 'Failed to update tags',
                            },
                          )
                        : undefined
                    }
                    className="flex-1 rounded border border-purple-500/40 bg-black/60 p-1 text-[11px] text-purple-100 focus:border-yellow-300 focus:outline-none"
                  />
                  <a
                    href={`${API_BASE}/media/${item.id}/download`}
                    className="rounded border border-purple-500/40 px-2 py-1 text-[11px] text-purple-200 hover:border-yellow-300 hover:text-yellow-200"
                  >
                    Download
                  </a>
                  <button
                    type="button"
                    onClick={() =>
                      toast.promise(deleteMedia(item.id), {
                        loading: 'Deleting…',
                        success: 'Media deleted',
                        error: 'Failed to delete media',
                      })
                    }
                    className="rounded border border-red-500/40 px-2 py-1 text-[11px] text-red-300 hover:border-red-300"
                  >
                    Delete
                  </button>
                </div>
              </figcaption>
            </figure>
          ))}
        </div>

        {media.length < total && (
          <div className="mt-6 flex justify-center">
            <button
              type="button"
              onClick={() => loadMore()}
              className="rounded-lg border border-purple-500/40 px-4 py-2 text-sm text-purple-200 hover:border-yellow-300 hover:text-yellow-200"
            >
              Load more
            </button>
          </div>
        )}
      </div>
    </section>
  )
}
