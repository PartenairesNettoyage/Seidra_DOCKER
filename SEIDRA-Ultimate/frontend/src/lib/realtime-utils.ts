'use client'

import type { JobItem } from './api-client'
import type { JobRealtimeUpdate } from './websocket-context'

const MAX_TRACKED_JOBS = 200

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined
}

function asNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function normaliseTimestamp(value?: string): string {
  if (!value) return new Date().toISOString()
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return new Date().toISOString()
  }
  return date.toISOString()
}

export function mergeJobUpdates(existing: JobItem[], updates: JobRealtimeUpdate[]): JobItem[] {
  if (!updates.length) {
    return existing
  }

  const map = new Map<string, JobItem>()
  for (const job of existing) {
    map.set(job.job_id, { ...job })
  }

  for (const update of updates) {
    if (!update.jobId) continue
    const current = map.get(update.jobId)
    const metadata = update.metadata ?? {}

    const createdAt =
      update.createdAt ??
      asString(metadata.createdAt) ??
      current?.created_at ??
      update.timestamp ??
      new Date().toISOString()

    const completedAt = update.completedAt ?? asString(metadata.completedAt) ?? current?.completed_at
    const jobType =
      update.jobType ??
      asString(metadata.jobType) ??
      current?.job_type ??
      (metadata.job_type as string | undefined) ??
      'image'
    const modelName =
      update.modelName ??
      asString(metadata.modelName) ??
      current?.model_name ??
      (metadata.model_name as string | undefined) ??
      'sdxl-base'

    const merged: JobItem = {
      job_id: update.jobId,
      status: update.status ?? (metadata.status as string | undefined) ?? current?.status ?? 'queued',
      progress: update.progress ?? asNumber(metadata.progress) ?? current?.progress ?? 0,
      prompt: asString(metadata.prompt) ?? current?.prompt,
      job_type: jobType,
      model_name: modelName,
      persona_id: current?.persona_id,
      created_at: normaliseTimestamp(createdAt),
      updated_at: normaliseTimestamp(update.timestamp ?? current?.updated_at ?? createdAt),
      completed_at: completedAt ? normaliseTimestamp(completedAt) : current?.completed_at,
      result_images:
        update.resultImages ??
        (Array.isArray(metadata.result) ? (metadata.result as string[]) : undefined) ??
        current?.result_images ??
        [],
      message: update.message ?? (metadata.message as string | undefined) ?? current?.message,
    }

    map.set(update.jobId, merged)
  }

  const mergedList = Array.from(map.values())
  mergedList.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  return mergedList.slice(0, MAX_TRACKED_JOBS)
}

export function extractJobMessages(jobUpdates: Record<string, JobRealtimeUpdate>): Record<string, string | undefined> {
  const result: Record<string, string | undefined> = {}
  for (const update of Object.values(jobUpdates)) {
    if (!update.jobId) continue
    if (update.message) {
      result[update.jobId] = update.message
    }
  }
  return result
}
