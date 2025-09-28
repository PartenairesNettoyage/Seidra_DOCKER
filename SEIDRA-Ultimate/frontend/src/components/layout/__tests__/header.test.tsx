import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Header } from '../header'

;(globalThis as unknown as { React?: typeof React }).React = React

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    getHealth: vi.fn().mockResolvedValue({}),
  },
}))

describe('Header', () => {
  it('annonce le statut de santé avec les attributs ARIA attendus', async () => {
    render(<Header />)

    const banner = screen.getByRole('banner')
    expect(banner).toBeInTheDocument()

    const statusRegion = screen.getByRole('status')
    expect(statusRegion).toHaveAttribute('aria-live', 'polite')

    await waitFor(() => {
      expect(screen.getByText(/Statut de la plateforme/i)).toBeInTheDocument()
    })

    const statusBadge = screen.getByText(/Statut de la plateforme/i)
    expect(statusBadge).toHaveAccessibleName(/Statut de la plateforme/i)
  })
})
