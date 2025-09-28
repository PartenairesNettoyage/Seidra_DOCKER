import React from 'react'
import { clsx } from 'clsx'
import type { LucideIcon } from 'lucide-react'
import { AlertTriangle, CheckCircle2, Clock3, Loader2, Sparkles } from 'lucide-react'

type ProgressBarProps = {
  /**
   * Progress value as a fraction (0-1) or percentage (0-100).
   */
  value: number
  /**
   * Optional label displayed above the progress bar.
   */
  label?: string
  /**
   * Optional status badge rendered next to the label.
   */
  status?: string
  /**
   * Additional classes for the container element.
   */
  className?: string
}

type ProgressVisuals = {
  bar: string
  badge: string
  icon: LucideIcon
  iconBg: string
  iconClassName?: string
  description: string
}

function getProgressVisuals(status?: string): ProgressVisuals {
  if (!status) {
    return {
      bar: 'seidra-progress-bar bg-gradient-to-r from-purple-500 via-yellow-400 to-amber-300',
      badge: 'border border-purple-500/40 bg-purple-500/10 text-purple-100',
      icon: Sparkles,
      iconBg: 'border border-purple-500/40 bg-purple-500/10 text-purple-100',
      description: 'Awaiting status update',
    }
  }

  const normalized = status.toLowerCase()

  if (normalized.includes('complete')) {
    return {
      bar: 'seidra-progress-bar bg-gradient-to-r from-emerald-500 via-green-400 to-emerald-600 shadow-[0_0_20px_rgba(16,185,129,0.35)]',
      badge: 'border border-emerald-400/50 bg-emerald-500/15 text-emerald-100',
      icon: CheckCircle2,
      iconBg: 'border border-emerald-400/60 bg-emerald-500/15 text-emerald-100',
      description: 'Generation finished successfully',
    }
  }

  if (normalized.includes('fail') || normalized.includes('cancel')) {
    return {
      bar: 'seidra-progress-bar bg-gradient-to-r from-rose-600 via-red-500 to-rose-700 shadow-[0_0_16px_rgba(244,63,94,0.35)]',
      badge: 'border border-rose-400/50 bg-rose-500/15 text-rose-100',
      icon: AlertTriangle,
      iconBg: 'border border-rose-400/60 bg-rose-500/15 text-rose-100',
      description: 'Something went wrong during the generation',
    }
  }

  if (normalized.includes('queue') || normalized.includes('pending')) {
    return {
      bar: 'seidra-progress-bar seidra-progress-waiting bg-gradient-to-r from-sky-500 via-blue-400 to-sky-500 shadow-[0_0_18px_rgba(56,189,248,0.35)]',
      badge: 'border border-sky-400/40 bg-sky-500/15 text-sky-100',
      icon: Clock3,
      iconBg: 'border border-sky-400/50 bg-sky-500/15 text-sky-100',
      description: 'Queued and waiting for available resources',
    }
  }

  if (normalized.includes('progress') || normalized.includes('process') || normalized.includes('running') || normalized.includes('generat')) {
    return {
      bar: 'seidra-progress-bar seidra-progress-active bg-gradient-to-r from-amber-400 via-yellow-300 to-purple-400 shadow-[0_0_18px_rgba(251,191,36,0.35)]',
      badge: 'border border-amber-400/40 bg-amber-500/15 text-amber-100',
      icon: Loader2,
      iconBg: 'border border-amber-400/60 bg-amber-500/15 text-amber-100',
      iconClassName: 'animate-spin',
      description: 'Actively generating your media',
    }
  }

  return {
    bar: 'seidra-progress-bar bg-gradient-to-r from-purple-500 via-yellow-400 to-amber-300',
    badge: 'border border-purple-500/40 bg-purple-500/10 text-purple-100',
    icon: Sparkles,
    iconBg: 'border border-purple-500/40 bg-purple-500/10 text-purple-100',
    description: 'Awaiting status update',
  }
}

function normalizePercentage(value: number): number {
  if (!Number.isFinite(value)) {
    return 0
  }

  const raw = value <= 1 ? value * 100 : value
  return Math.max(0, Math.min(100, raw))
}

export function ProgressBar({ value, label = 'Progress', status, className }: ProgressBarProps) {
  const percentage = Math.round(normalizePercentage(value))
  const visuals = getProgressVisuals(status)
  const statusText = status?.replace(/[_-]+/g, ' ') ?? ''
  const statusLabel = statusText
    ? statusText.replace(/\b\w/g, (character) => character.toUpperCase())
    : ''
  const StatusIcon = visuals.icon
  const markers = [0, 25, 50, 75, 100]

  return (
    <div className={clsx('space-y-2', className)}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className={clsx('flex h-9 w-9 items-center justify-center rounded-full bg-black/40 text-sm shadow-inner', visuals.iconBg)}>
            <StatusIcon className={clsx('h-4 w-4', visuals.iconClassName)} aria-hidden="true" />
          </div>
          <div className="flex flex-col">
            <span className="text-xs font-semibold uppercase tracking-wide text-purple-200">{label}</span>
            {status && (
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-purple-200/80">
                <span className={clsx('rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider', visuals.badge)}>
                  {statusLabel}
                </span>
                <span className="text-purple-200/70">{visuals.description}</span>
              </div>
            )}
          </div>
        </div>
        <span className="text-xs font-semibold text-yellow-200">{percentage}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-purple-950/60">
        <div
          className={clsx('relative h-full rounded-full transition-all duration-700 ease-out', visuals.bar)}
          style={{ width: `${percentage}%` }}
          role="progressbar"
          aria-valuenow={percentage}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <span className="sr-only">
            {label} {percentage}%
          </span>
        </div>
      </div>
      <div className="flex items-center justify-between text-[10px] font-medium uppercase tracking-wide text-purple-300/70">
        {markers.map((marker) => (
          <div key={marker} className="flex flex-col items-center gap-1">
            <span
              className={clsx(
                'h-2 w-2 rounded-full border',
                percentage >= marker ? 'border-yellow-300 bg-yellow-300 shadow-[0_0_8px_rgba(253,224,71,0.6)]' : 'border-purple-500/40 bg-purple-950/80',
              )}
            />
            <span>{marker}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

