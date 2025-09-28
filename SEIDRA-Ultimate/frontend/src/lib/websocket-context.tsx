'use client'

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { toast } from 'react-hot-toast'

import { apiClient, type RealtimeNotification } from './api-client'

const MAX_NOTIFICATIONS = 200

export type JobRealtimeUpdate = {
  jobId?: string
  status?: string
  progress?: number
  message?: string
  resultImages?: string[]
  timestamp?: string
  jobType?: string
  modelName?: string
  createdAt?: string
  completedAt?: string
  metadata?: Record<string, unknown>
  lastEvent?: string
  error?: string
}

type SystemSnapshot = Record<string, unknown>

type WebSocketContextValue = {
  status: 'disconnected' | 'connecting' | 'connected'
  systemStatus: SystemSnapshot | null
  jobUpdates: Record<string, JobRealtimeUpdate>
  notifications: RealtimeNotification[]
  notificationsTotal: number
  canLoadMoreNotifications: boolean
  loadMoreNotifications: () => Promise<void>
  loadingNotifications: boolean
  send: (payload: Record<string, unknown>) => void
}

const defaultValue: WebSocketContextValue = {
  status: 'disconnected',
  systemStatus: null,
  jobUpdates: {},
  notifications: [],
  notificationsTotal: 0,
  canLoadMoreNotifications: false,
  loadMoreNotifications: async () => undefined,
  loadingNotifications: false,
  send: () => undefined,
}

const WebSocketContext = createContext<WebSocketContextValue>(defaultValue)

function mergeNotifications(
  next: RealtimeNotification[],
  previous: RealtimeNotification[],
): RealtimeNotification[] {
  const map = new Map<string, RealtimeNotification>()
  for (const item of [...next, ...previous]) {
    if (!item?.id) continue
    map.set(item.id, item)
  }
  return Array.from(map.values()).sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
  )
}

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<'disconnected' | 'connecting' | 'connected'>(
    'disconnected',
  )
  const [systemStatus, setSystemStatus] = useState<SystemSnapshot | null>(null)
  const [jobUpdates, setJobUpdates] = useState<Record<string, JobRealtimeUpdate>>({})
  const [notifications, setNotifications] = useState<RealtimeNotification[]>([])
  const [notificationMeta, setNotificationMeta] = useState<{
    total: number
    limit: number
    nextOffset: number
    hasMore: boolean
  }>({ total: 0, limit: 20, nextOffset: 0, hasMore: false })
  const [loadingNotifications, setLoadingNotifications] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)

  const storeJobUpdate = useCallback((update: JobRealtimeUpdate) => {
    const jobId = update.jobId
    if (!jobId) return
    setJobUpdates((prev) => {
      const current = prev[jobId]
      const merged: JobRealtimeUpdate = {
        jobId,
        status: update.status ?? current?.status,
        progress: update.progress ?? current?.progress,
        message: update.message ?? current?.message,
        resultImages: update.resultImages ?? current?.resultImages,
        timestamp: update.timestamp ?? current?.timestamp,
        jobType: update.jobType ?? current?.jobType,
        modelName: update.modelName ?? current?.modelName,
        createdAt: update.createdAt ?? current?.createdAt,
        completedAt: update.completedAt ?? current?.completedAt,
        metadata: { ...(current?.metadata ?? {}), ...(update.metadata ?? {}) },
        lastEvent: update.lastEvent ?? current?.lastEvent,
        error: update.error ?? current?.error,
      }

      const next: Record<string, JobRealtimeUpdate> = { ...prev, [jobId]: merged }
      const entries = Object.entries(next) as Array<[string, JobRealtimeUpdate]>
      if (entries.length <= 200) {
        return next
      }
      const resolveTimestamp = (entry: JobRealtimeUpdate): number => {
        const candidate = entry.timestamp ?? entry.createdAt
        if (!candidate) return 0
        const value = new Date(candidate).getTime()
        return Number.isNaN(value) ? 0 : value
      }
      entries.sort((a, b) => resolveTimestamp(b[1]) - resolveTimestamp(a[1]))
      return Object.fromEntries(entries.slice(0, 200))
    })
  }, [])

  const handleNotification = useCallback((entry: RealtimeNotification) => {
    setNotifications((prev) => mergeNotifications([entry], prev).slice(0, MAX_NOTIFICATIONS))

    setNotificationMeta((prev) => {
      const total = prev.total + 1
      const hasMore = total > prev.nextOffset
      return { ...prev, total, hasMore }
    })

    const summary = entry.message ? `${entry.title}: ${entry.message}` : entry.title
    if (entry.level === 'error') {
      toast.error(summary)
    } else if (entry.level === 'warning') {
      toast(summary, { icon: '⚠️' })
    } else if (entry.level === 'success') {
      toast.success(summary)
    } else {
      toast(summary, { icon: 'ℹ️' })
    }
  }, [])

  const handleMessage = useCallback(
    (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data)
        if (!payload || typeof payload !== 'object') return

        switch (payload.type) {
          case 'system_status':
            setSystemStatus(payload.data ?? null)
            break
          case 'job_queued':
            storeJobUpdate({
              jobId: payload.jobId,
              status: 'queued',
              progress: 0,
              timestamp: payload.timestamp,
              jobType: payload.jobType,
              modelName: payload.modelName,
              createdAt: payload.createdAt,
              metadata: payload,
            })
            break
          case 'generation_progress':
            storeJobUpdate({
              jobId: payload.jobId,
              status: payload.status,
              progress: payload.progress,
              message: payload.message,
              timestamp: payload.timestamp,
              jobType: payload.metadata?.jobType ?? payload.jobType,
              modelName: payload.metadata?.modelName ?? payload.modelName,
              createdAt: payload.metadata?.createdAt ?? payload.createdAt,
              metadata: payload.metadata ?? payload,
            })
            break
          case 'generation_complete':
            storeJobUpdate({
              jobId: payload.jobId,
              status: 'completed',
              progress: 1,
              resultImages: payload.result,
              timestamp: payload.timestamp,
              message: 'Generation completed',
              metadata: payload.metadata ?? payload,
              completedAt: payload.metadata?.completedAt,
            })
            break
          case 'generation_error':
            storeJobUpdate({
              jobId: payload.jobId,
              status: 'failed',
              progress: 1,
              message: payload.error,
              error: payload.error,
              timestamp: payload.timestamp,
            })
            break
          case 'batch_queued':
            // handled via notifications for user feedback
            break
          case 'notification':
            handleNotification({
              id: payload.id,
              level: payload.level ?? 'info',
              title: payload.title ?? 'Notification',
              message: payload.message ?? '',
              category: payload.category ?? 'system',
              metadata: payload.metadata ?? {},
              tags: payload.tags ?? [],
              timestamp: payload.timestamp ?? new Date().toISOString(),
            })
            break
          default:
            break
        }
      } catch (error) {
        console.warn('Failed to parse websocket message', error)
      }
    },
    [handleNotification, storeJobUpdate],
  )

  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      try {
        const info = await apiClient.getSystemInfo()
        if (!cancelled) {
          setSystemStatus(info)
          if (Array.isArray(info.notifications) && info.notifications.length) {
            setNotifications((prev) =>
              mergeNotifications(info.notifications, prev).slice(0, MAX_NOTIFICATIONS),
            )
          }
        }
      } catch (error) {
        console.warn('Failed to fetch system info', error)
      }

      try {
        const feed = await apiClient.listSystemNotifications({ limit: 20, offset: 0 })
        if (!cancelled && Array.isArray(feed.items)) {
          setNotifications((prev) =>
            mergeNotifications(feed.items, prev).slice(0, MAX_NOTIFICATIONS),
          )
          setNotificationMeta({
            total: feed.total ?? feed.items.length,
            limit: feed.limit ?? 20,
            nextOffset: (feed.offset ?? 0) + feed.items.length,
            hasMore:
              feed.hasMore ?? (feed.offset ?? 0) + feed.items.length < (feed.total ?? feed.items.length),
          })
        }
      } catch (error) {
        console.warn('Failed to fetch notification feed', error)
      }
    }

    bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return

    const wsUrl = process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000/ws/frontend'
    const token = process.env.NEXT_PUBLIC_WS_TOKEN ?? 'ultimate-demo-token'
    const userId = process.env.NEXT_PUBLIC_WS_USER_ID ?? '1'

    setStatus('connecting')

    try {
      const url = new URL(wsUrl)
      url.searchParams.set('token', token)
      url.searchParams.set('userId', userId)
      url.searchParams.set('channels', 'jobs,system,notifications')

      const socket = new WebSocket(url.toString())
      socketRef.current = socket

      socket.addEventListener('open', () => {
        setStatus('connected')
        socket.send(
          JSON.stringify({ type: 'subscribe', channels: ['jobs', 'system', 'notifications'] }),
        )
      })
      socket.addEventListener('close', () => setStatus('disconnected'))
      socket.addEventListener('error', () => setStatus('disconnected'))
      socket.addEventListener('message', handleMessage)

      return () => {
        socket.removeEventListener('message', handleMessage)
        socket.close()
        socketRef.current = null
      }
    } catch (error) {
      console.warn('WebSocket connection failed', error)
      setStatus('disconnected')
    }
  }, [handleMessage])

  useEffect(() => {
    if (status !== 'connected') return
    const interval = window.setInterval(() => {
      if (socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)
    return () => window.clearInterval(interval)
  }, [status])

  const send = useCallback((payload: Record<string, unknown>) => {
    const socket = socketRef.current
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(payload))
    }
  }, [])

  const loadMoreNotifications = useCallback(async () => {
    if (loadingNotifications || !notificationMeta.hasMore) {
      return
    }
    setLoadingNotifications(true)
    try {
      const limit = notificationMeta.limit || 20
      const offset = notificationMeta.nextOffset
      const feed = await apiClient.listSystemNotifications({ limit, offset })
      setNotifications((prev) =>
        mergeNotifications(feed.items, prev).slice(0, MAX_NOTIFICATIONS),
      )
      setNotificationMeta((prev) => {
        const baseOffset = feed.offset ?? offset
        const nextOffset = baseOffset + feed.items.length
        const total = feed.total ?? prev.total
        const hasMore = feed.hasMore ?? nextOffset < total
        return {
          total,
          limit: feed.limit ?? prev.limit,
          nextOffset,
          hasMore,
        }
      })
    } catch (error) {
      console.warn('Failed to extend notification feed', error)
    } finally {
      setLoadingNotifications(false)
    }
  }, [loadingNotifications, notificationMeta.hasMore, notificationMeta.limit, notificationMeta.nextOffset])

  const totalNotifications = Math.max(notificationMeta.total, notifications.length)

  const value = useMemo(
    () => ({
      status,
      systemStatus,
      jobUpdates,
      notifications,
      notificationsTotal: totalNotifications,
      canLoadMoreNotifications: notificationMeta.hasMore,
      loadMoreNotifications,
      loadingNotifications,
      send,
    }),
    [
      jobUpdates,
      loadMoreNotifications,
      loadingNotifications,
      notificationMeta.hasMore,
      notifications,
      send,
      status,
      systemStatus,
      totalNotifications,
    ],
  )

  return <WebSocketContext.Provider value={value}>{children}</WebSocketContext.Provider>
}

export function useRealtime() {
  return useContext(WebSocketContext)
}

export function useWebSocketStatus() {
  return useRealtime()
}
