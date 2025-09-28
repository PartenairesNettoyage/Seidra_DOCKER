import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import HomePage from '@/app/page'

const globalWithReact = globalThis as typeof globalThis & { React?: typeof React }
globalWithReact.React = React

vi.mock('@/components/layout/header', () => ({
  Header: () => <div data-testid="header-status">Tableau de bord connecté</div>,
}))

vi.mock('@/components/generation/generation-interface', () => ({
  GenerationInterface: () => <div>Module de génération prêt</div>,
}))

vi.mock('@/components/personas/persona-manager', () => ({
  PersonaManager: () => <div>Gestionnaire de personas actif</div>,
}))

vi.mock('@/components/media/media-gallery', () => ({
  MediaGallery: () => <div>Galerie multimédia active</div>,
}))

vi.mock('@/components/models/model-manager', () => ({
  ModelManager: () => <div>Gestionnaire de modèles</div>,
}))

vi.mock('@/components/jobs/job-monitor', () => ({
  JobMonitor: () => <div>Suivi des jobs</div>,
}))

vi.mock('@/components/settings/settings-panel', () => ({
  SettingsPanel: () => <div>Paramètres généraux</div>,
}))

vi.mock('@/components/onboarding/onboarding-wizard', () => ({
  OnboardingWizard: ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) => (
    <div data-testid="onboarding" data-open={String(isOpen)}>
      {isOpen ? 'Onboarding ouvert' : 'Onboarding fermé'}
      <button onClick={onClose} type="button">
        Fermer l’onboarding
      </button>
    </div>
  ),
}))

vi.mock('@/lib/websocket-context', () => ({
  WebSocketProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

describe('Parcours bout-en-bout depuis la page d\'accueil', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('permet à un utilisateur authentifié de passer de la gestion des personas à la génération puis à la galerie', async () => {
    window.localStorage.setItem('seidra_onboarding_completed', 'true')

    const user = userEvent.setup()
    render(<HomePage />)

    expect(screen.getByTestId('header-status')).toBeInTheDocument()
    expect(screen.getByText('Module de génération prêt')).toBeInTheDocument()
    expect(screen.getByTestId('onboarding')).toHaveAttribute('data-open', 'false')

    await user.click(screen.getByRole('button', { name: 'Personas' }))
    await waitFor(() => {
      expect(screen.getByText('Gestionnaire de personas actif')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'Generate' }))
    await waitFor(() => {
      expect(screen.getByText('Module de génération prêt')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'Media' }))
    await waitFor(() => {
      expect(screen.getByText('Galerie multimédia active')).toBeInTheDocument()
    })
  })

  it('affiche l\'onboarding lors de la première connexion et permet de le fermer', async () => {
    const user = userEvent.setup()
    render(<HomePage />)

    const onboarding = await screen.findByTestId('onboarding')
    expect(onboarding).toHaveAttribute('data-open', 'true')

    await user.click(screen.getByText('Fermer l’onboarding'))

    await waitFor(() => {
      expect(screen.getByTestId('onboarding')).toHaveAttribute('data-open', 'false')
    })
  })
})
