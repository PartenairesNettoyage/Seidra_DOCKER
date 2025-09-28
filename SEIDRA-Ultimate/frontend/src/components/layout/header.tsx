'use client'

import { useEffect, useState } from 'react'
import { apiClient } from '@/lib/api-client'

export function Header() {
  const [health, setHealth] = useState<string>('Loading...')

  useEffect(() => {
    apiClient
      .getHealth()
      .then(() => setHealth('Online'))
      .catch(() => setHealth('Offline'))
  }, [])

  return (
    <header
      className="sticky top-0 z-10 flex items-center justify-between border-b border-midnight-700/60 bg-midnight-900/90 px-6 py-4 text-midnight-50 backdrop-blur"
      role="banner"
    >
      <div>
        <h1 className="text-2xl font-semibold text-gold-200">SEIDRA Ultimate</h1>
        <p className="text-sm text-midnight-100">Build your own myth</p>
      </div>
      <div className="flex items-center gap-3 text-sm text-midnight-100" role="status" aria-live="polite">
        <span className="rounded-full border border-midnight-600/70 px-3 py-1" aria-label={`Statut de la plateforme ${health}`}>
          Statut de la plateforme : <strong className="text-gold-100">{health}</strong>
        </span>
      </div>
    </header>
  )
}
