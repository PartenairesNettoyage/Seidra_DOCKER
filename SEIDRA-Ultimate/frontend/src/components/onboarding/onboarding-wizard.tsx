'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'

const STORAGE_KEYS = {
  progress: 'seidra_onboarding_progress',
  completed: 'seidra_onboarding_completed',
}

type WizardStep = {
  id: string
  title: string
  description: string
  bullets: string[]
}

type OnboardingWizardProps = {
  isOpen: boolean
  onClose: () => void
}

export function OnboardingWizard({ isOpen, onClose }: OnboardingWizardProps) {
  const steps = useMemo<WizardStep[]>(
    () => [
      {
        id: 'generation',
        title: 'Démarrer vos générations',
        description:
          'Configurez vos prompts, choisissez les modèles adaptés et suivez chaque rendu en direct.',
        bullets: [
          'Accédez à la rubrique « Generate » pour lancer des créations guidées.',
          'Sauvegardez vos paramètres favoris pour les réutiliser rapidement.',
          'Activez les notifications pour être informé dès qu’un rendu est terminé.',
        ],
      },
      {
        id: 'personas',
        title: 'Façonner des personas vivants',
        description:
          'Centralisez les profils de vos personnages et gérez leurs évolutions narratives.',
        bullets: [
          'Créez des fiches complètes avec tonalité, objectifs et assets dédiés.',
          'Partagez des personas avec votre équipe pour collaborer en temps réel.',
          'Maintenez l’historique des décisions clés directement dans la fiche.',
        ],
      },
      {
        id: 'studio',
        title: 'Explorer le studio vidéo',
        description:
          'Montez vos séquences, générez des scripts et orchestrez les scènes en quelques minutes.',
        bullets: [
          'Synchronisez vos médias générés avec les dialogues et les voix off.',
          'Prévisualisez vos montages avant export pour assurer la cohérence.',
          'Publiez et archivez vos projets finaux dans la médiathèque partagée.',
        ],
      },
    ],
    [],
  )

  const [currentStepIndex, setCurrentStepIndex] = useState(0)
  const dialogRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!isOpen || typeof window === 'undefined') {
      return
    }

    const savedProgress = window.localStorage.getItem(STORAGE_KEYS.progress)
    if (savedProgress) {
      const indexFromStorage = steps.findIndex((step) => step.id === savedProgress)
      if (indexFromStorage >= 0) {
        setCurrentStepIndex(indexFromStorage)
      }
    }

    requestAnimationFrame(() => {
      dialogRef.current?.focus()
    })
  }, [isOpen, steps])

  useEffect(() => {
    if (!isOpen || typeof window === 'undefined') {
      return
    }

    window.localStorage.setItem(STORAGE_KEYS.progress, steps[currentStepIndex].id)
  }, [currentStepIndex, isOpen, steps])

  const currentStep = steps[currentStepIndex]
  const isLastStep = currentStepIndex === steps.length - 1

  const closeWizard = () => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEYS.completed, 'true')
    }
    onClose()
  }

  const goToNextStep = () => {
    if (isLastStep) {
      closeWizard()
      return
    }
    setCurrentStepIndex((index) => Math.min(steps.length - 1, index + 1))
  }

  const goToPreviousStep = () => {
    setCurrentStepIndex((index) => Math.max(0, index - 1))
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.stopPropagation()
      closeWizard()
    }
  }

  if (!isOpen) {
    return null
  }

  return (
    <div
      aria-labelledby="onboarding-title"
      aria-modal="true"
      className="fixed inset-0 z-40 flex items-center justify-center bg-midnight-900/80 backdrop-blur-sm"
      role="dialog"
    >
      <div
        ref={dialogRef}
        aria-describedby="onboarding-description"
        className="max-h-[90vh] w-full max-w-2xl overflow-hidden rounded-2xl border border-gold-400/40 bg-midnight-800 text-midnight-50 shadow-2xl outline-none"
        tabIndex={-1}
        onKeyDown={handleKeyDown}
      >
        <header className="flex items-center justify-between border-b border-midnight-600/70 bg-midnight-900/80 px-6 py-4">
          <div>
            <h2 className="text-xl font-semibold text-gold-200" id="onboarding-title">
              Atelier de découverte SEIDRA
            </h2>
            <p className="text-sm text-midnight-100" id="onboarding-description">
              {currentStepIndex + 1} / {steps.length} · {currentStep.title}
            </p>
          </div>
          <button
            className="rounded-full px-4 py-2 text-sm font-medium text-midnight-50 transition hover:bg-midnight-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold-300"
            onClick={closeWizard}
            type="button"
          >
            Passer
          </button>
        </header>

        <section className="space-y-4 px-6 py-6">
          <p className="text-base text-gold-100">{currentStep.description}</p>
          <ul className="list-disc space-y-2 pl-6 text-sm text-midnight-50">
            {currentStep.bullets.map((bullet) => (
              <li key={bullet}>{bullet}</li>
            ))}
          </ul>
        </section>

        <footer className="flex items-center justify-between border-t border-midnight-600/70 bg-midnight-900/70 px-6 py-4">
          <div className="flex items-center gap-2" role="group" aria-label="Progression de l'onboarding">
            {steps.map((step, index) => {
              const isActive = index === currentStepIndex
              return (
                <span
                  key={step.id}
                  aria-label={`Étape ${index + 1} : ${step.title}${isActive ? ' (en cours)' : ''}`}
                  aria-current={isActive}
                  className={`h-2 w-12 rounded-full transition ${
                    isActive ? 'bg-gold-300' : 'bg-midnight-600'
                  }`}
                  role="presentation"
                />
              )
            })}
          </div>

          <div className="flex items-center gap-3">
            <button
              className="rounded-full px-4 py-2 text-sm font-medium text-midnight-50 transition hover:bg-midnight-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold-300 disabled:opacity-50"
              onClick={goToPreviousStep}
              type="button"
              disabled={currentStepIndex === 0}
            >
              Étape précédente
            </button>
            <button
              className="rounded-full bg-gold-300 px-4 py-2 text-sm font-semibold text-midnight-900 transition hover:bg-gold-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold-400"
              onClick={goToNextStep}
              type="button"
            >
              {isLastStep ? 'Terminer' : 'Étape suivante'}
            </button>
          </div>
        </footer>
      </div>
    </div>
  )
}
