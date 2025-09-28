'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'react-hot-toast'

import { useUltimateSettings } from '@/lib/hooks'
import { useWebSocketStatus } from '@/lib/websocket-context'

function formatPercent(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? `${value.toFixed(1)}%`
    : 'n/a'
}

function formatCelsius(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(1)}°C` : 'n/a'
}

function formatSeconds(value: unknown): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'n/a'
  if (value < 1) {
    return `${(value * 1000).toFixed(0)} ms`
  }
  return `${value.toFixed(2)} s`
}

function formatMegabytes(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(0)} MB` : 'n/a'
}

export function SettingsPanel() {
  const {
    status,
    systemStatus,
    notifications,
    notificationsTotal,
    loadMoreNotifications,
    canLoadMoreNotifications,
    loadingNotifications,
  } = useWebSocketStatus()
  const { settings, nsfwSettings, isLoading, isSaving, error, updateSettings, updateNsfw } = useUltimateSettings()
  const [localSettings, setLocalSettings] = useState(settings)
  const [localNsfw, setLocalNsfw] = useState(nsfwSettings)
  const [showAllNotifications, setShowAllNotifications] = useState(false)

  useEffect(() => {
    setLocalSettings(settings)
  }, [settings])

  useEffect(() => {
    setLocalNsfw(nsfwSettings)
  }, [nsfwSettings])


  const gpuMetrics = useMemo(() => (systemStatus?.gpu as Record<string, unknown>) ?? {}, [systemStatus])
  const systemMetrics = useMemo(
    () => (systemStatus?.system as Record<string, unknown>) ?? {},
    [systemStatus],
  )
  const connectionStats = useMemo(
    () => (systemStatus?.connections as Record<string, unknown>) ?? {},
    [systemStatus],
  )
  const displayedNotifications = useMemo(
    () => (showAllNotifications ? notifications : notifications.slice(0, 5)),
    [notifications, showAllNotifications],
  )

  const toggleNotifications = useCallback(() => {
    setShowAllNotifications((prev) => !prev)
  }, [])

  const handleLoadMoreNotifications = useCallback(async () => {
    try {
      await loadMoreNotifications()
    } catch (loadError) {
      console.warn('Failed to load more notifications', loadError)
    }
  }, [loadMoreNotifications])

  const generalDirty = useMemo(() => {
    if (!settings || !localSettings) return false
    return JSON.stringify(settings) !== JSON.stringify(localSettings)
  }, [settings, localSettings])

  const nsfwDirty = useMemo(() => {
    if (!nsfwSettings || !localNsfw) return false
    return JSON.stringify(nsfwSettings) !== JSON.stringify(localNsfw)
  }, [nsfwSettings, localNsfw])

  const categoryKeys = useMemo(() => {
    if (localNsfw?.categories) {
      return Object.keys(localNsfw.categories)
    }
    return ['nudity', 'violence', 'fetish', 'gore']
  }, [localNsfw])

  return (
    <section className="space-y-6">
      <div className="rounded-2xl border border-purple-500/30 bg-black/40 p-6 text-purple-100 shadow-xl">
        <h2 className="mb-4 text-xl font-semibold text-yellow-200">Realtime health</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-purple-500/30 bg-black/30 p-4 text-sm text-purple-200">
            <h3 className="text-sm font-semibold text-yellow-200">WebSocket</h3>
            <p className="text-xs text-purple-300">Status: {status}</p>
            {error && <p className="text-xs text-red-400">{error}</p>}
            {isLoading && <p className="text-xs text-purple-300">Loading settings…</p>}
          </div>
          <div className="rounded-xl border border-purple-500/30 bg-black/30 p-4 text-sm text-purple-200">
            <h3 className="text-sm font-semibold text-yellow-200">GPU metrics</h3>
            <p className="text-xs text-purple-300">Available: {gpuMetrics.gpu_available ? 'Yes' : 'No'}</p>
            <p className="text-xs text-purple-300">Temperature: {formatCelsius(gpuMetrics.temperature)}</p>
            <p className="text-xs text-purple-300">Utilisation: {formatPercent(gpuMetrics.utilization)}</p>
            <p className="text-xs text-purple-300">
              Inference (avg): {formatSeconds(gpuMetrics.inference_avg_seconds ?? gpuMetrics.inferenceAvgSeconds)}
            </p>
            <p className="text-xs text-purple-300">
              VRAM max allocated: {formatMegabytes(gpuMetrics.memory_max_allocated ?? gpuMetrics.memoryMaxAllocated)}
            </p>
            <p className="text-xs text-purple-300">
              CUDA errors: {String(gpuMetrics.cuda_error_count ?? gpuMetrics.cudaErrorCount ?? 0)}
            </p>
          </div>
          <div className="rounded-xl border border-purple-500/30 bg-black/30 p-4 text-sm text-purple-200">
            <h3 className="text-sm font-semibold text-yellow-200">System load</h3>
            <p className="text-xs text-purple-300">CPU usage: {formatPercent(systemMetrics.cpuPercent)}</p>
            <p className="text-xs text-purple-300">Memory usage: {formatPercent(systemMetrics.memoryPercent)}</p>
            <p className="text-xs text-purple-300">Active connections: {String(connectionStats.total_connections ?? 0)}</p>
          </div>
          <div className="rounded-xl border border-purple-500/30 bg-black/30 p-4 text-sm text-purple-200">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-yellow-200">Notifications</h3>
              {notifications.length > 5 && (
                <button
                  type="button"
                  onClick={toggleNotifications}
                  className="rounded border border-purple-500/40 px-2 py-1 text-[10px] uppercase tracking-wide text-yellow-200 hover:border-yellow-300 hover:text-yellow-100"
                >
                  {showAllNotifications ? 'Réduire' : 'Voir tout'}
                </button>
              )}
            </div>
            {displayedNotifications.length === 0 && (
              <p className="mt-2 text-xs text-purple-300">No notifications received yet.</p>
            )}
            {displayedNotifications.length > 0 && (
              <div className={`mt-2 ${showAllNotifications ? 'max-h-64 overflow-y-auto pr-1' : ''}`}>
                <ul className="space-y-2 text-xs">
                  {displayedNotifications.map((notification) => {
                    const accent =
                      notification.level === 'error'
                        ? 'text-red-300'
                        : notification.level === 'warning'
                          ? 'text-yellow-200'
                          : notification.level === 'success'
                            ? 'text-green-300'
                            : 'text-purple-200'
                    return (
                      <li key={notification.id} className="rounded-lg border border-purple-500/20 bg-black/40 p-3">
                        <p className={`font-semibold ${accent}`}>{notification.title}</p>
                        {notification.message && <p className="mt-1 text-purple-200">{notification.message}</p>}
                        <p className="mt-1 text-[10px] text-purple-400">
                          {new Date(notification.timestamp).toLocaleString()} · {notification.level}
                        </p>
                      </li>
                    )
                  })}
                </ul>
              </div>
            )}
            <div className="mt-2 flex items-center justify-between text-[10px] text-purple-400">
              <span>Total historisé : {notificationsTotal}</span>
              {showAllNotifications && canLoadMoreNotifications && (
                <button
                  type="button"
                  onClick={handleLoadMoreNotifications}
                  disabled={loadingNotifications}
                  className="rounded border border-purple-500/40 px-2 py-1 text-[10px] uppercase tracking-wide text-yellow-200 hover:border-yellow-300 hover:text-yellow-100 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {loadingNotifications ? 'Chargement…' : 'Charger plus'}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-purple-500/30 bg-black/40 p-6 text-purple-100 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-yellow-200">Application preferences</h3>
          {generalDirty && localSettings && (
            <button
              type="button"
              className="rounded border border-purple-500/40 px-3 py-1 text-xs text-yellow-200 hover:border-yellow-300 hover:text-yellow-100"
              onClick={() =>
                toast.promise(updateSettings(localSettings), {
                  loading: 'Saving settings…',
                  success: 'Settings saved',
                  error: 'Failed to save settings',
                })
              }
            >
              {isSaving ? 'Saving…' : 'Save changes'}
            </button>
          )}
        </div>

        {localSettings ? (
          <div className="space-y-4 text-sm text-purple-200">
            <div className="grid gap-4 md:grid-cols-2">
              <label className="flex flex-col gap-2">
                <span className="text-xs uppercase tracking-wide text-purple-300">Theme</span>
                <select
                  value={localSettings.theme}
                  onChange={(event) =>
                    setLocalSettings((prev) => prev && { ...prev, theme: event.target.value })
                  }
                  className="rounded-lg border border-purple-500/40 bg-black/60 p-2 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
                >
                  <option value="ultimate">Ultimate</option>
                  <option value="classic">Classic</option>
                  <option value="minimal">Minimal</option>
                </select>
              </label>
              <label className="flex flex-col gap-2">
                <span className="text-xs uppercase tracking-wide text-purple-300">Language</span>
                <select
                  value={localSettings.language}
                  onChange={(event) =>
                    setLocalSettings((prev) => prev && { ...prev, language: event.target.value })
                  }
                  className="rounded-lg border border-purple-500/40 bg-black/60 p-2 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
                >
                  <option value="en">English</option>
                  <option value="fr">Français</option>
                </select>
              </label>
            </div>

            <div className="space-y-2 text-xs text-purple-200">
              <p className="text-xs font-semibold uppercase tracking-wide text-yellow-200">Notifications</p>
              {Object.entries(localSettings.notifications ?? {}).map(([channel, enabled]) => (
                <label key={channel} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={Boolean(enabled)}
                    onChange={(event) =>
                      setLocalSettings((prev) =>
                        prev && {
                          ...prev,
                          notifications: {
                            ...prev.notifications,
                            [channel]: event.target.checked,
                          },
                        },
                      )
                    }
                    className="h-4 w-4 rounded border-purple-500/40 bg-black/60"
                  />
                  <span className="capitalize">{channel}</span>
                </label>
              ))}
            </div>

            <label className="flex items-center gap-3 text-xs text-purple-200">
              <input
                type="checkbox"
                checked={Boolean(localSettings.telemetry_opt_in)}
                onChange={(event) =>
                  setLocalSettings((prev) => prev && { ...prev, telemetry_opt_in: event.target.checked })
                }
                className="h-4 w-4 rounded border-purple-500/40 bg-black/60"
              />
              Share anonymous telemetry to improve stability
            </label>
          </div>
        ) : (
          <p className="text-sm text-purple-300">Preferences unavailable.</p>
        )}
      </div>

      <div className="rounded-2xl border border-purple-500/30 bg-black/40 p-6 text-purple-100 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-yellow-200">NSFW moderation</h3>
          {nsfwDirty && localNsfw && (
            <button
              type="button"
              className="rounded border border-purple-500/40 px-3 py-1 text-xs text-yellow-200 hover:border-yellow-300 hover:text-yellow-100"
              onClick={() =>
                toast.promise(updateNsfw(localNsfw), {
                  loading: 'Saving NSFW settings…',
                  success: 'NSFW settings saved',
                  error: 'Failed to save NSFW settings',
                })
              }
            >
              {isSaving ? 'Saving…' : 'Save changes'}
            </button>
          )}
        </div>

        {localNsfw ? (
          <div className="space-y-4 text-sm text-purple-200">
            <label className="flex items-center gap-3 text-xs text-purple-200">
              <input
                type="checkbox"
                checked={localNsfw.enabled}
                onChange={(event) => setLocalNsfw((prev) => prev && { ...prev, enabled: event.target.checked })}
                className="h-4 w-4 rounded border-purple-500/40 bg-black/60"
              />
              Enable NSFW content
            </label>
            <label className="flex items-center gap-3 text-xs text-purple-200">
              <input
                type="checkbox"
                checked={localNsfw.age_verified}
                onChange={(event) => setLocalNsfw((prev) => prev && { ...prev, age_verified: event.target.checked })}
                className="h-4 w-4 rounded border-purple-500/40 bg-black/60"
              />
              User is age verified
            </label>

            <label className="flex flex-col gap-2 text-xs text-purple-200">
              Intensity
              <select
                value={localNsfw.intensity}
                onChange={(event) => setLocalNsfw((prev) => prev && { ...prev, intensity: event.target.value as typeof prev.intensity })}
                className="max-w-xs rounded-lg border border-purple-500/40 bg-black/60 p-2 text-sm text-purple-100 focus:border-yellow-300 focus:outline-none"
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </label>

            <div className="space-y-2 text-xs text-purple-200">
              <p className="text-xs font-semibold uppercase tracking-wide text-yellow-200">Categories</p>
              {categoryKeys.map((category) => (
                <label key={category} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={Boolean(localNsfw.categories?.[category])}
                    onChange={(event) =>
                      setLocalNsfw((prev) =>
                        prev && {
                          ...prev,
                          categories: {
                            ...(prev.categories ?? {}),
                            [category]: event.target.checked,
                          },
                        },
                      )
                    }
                    className="h-4 w-4 rounded border-purple-500/40 bg-black/60"
                  />
                  <span className="capitalize">{category.replace(/_/g, ' ')}</span>
                </label>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-sm text-purple-300">No NSFW configuration found.</p>
        )}
      </div>
    </section>
  )
}
