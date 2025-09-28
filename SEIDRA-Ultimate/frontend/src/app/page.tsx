'use client'

import { useEffect, useState } from 'react'
import { Header } from '@/components/layout/header'
import { Sidebar } from '@/components/layout/sidebar'
import { GenerationInterface } from '@/components/generation/generation-interface'
import { PersonaManager } from '@/components/personas/persona-manager'
import { MediaGallery } from '@/components/media/media-gallery'
import { ModelManager } from '@/components/models/model-manager'
import { JobMonitor } from '@/components/jobs/job-monitor'
import { SettingsPanel } from '@/components/settings/settings-panel'
import { WebSocketProvider } from '@/lib/websocket-context'
import { Toaster } from 'react-hot-toast'
import { OnboardingWizard } from '@/components/onboarding/onboarding-wizard'

export default function HomePage() {
  const [activeTab, setActiveTab] = useState('generate')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [showOnboarding, setShowOnboarding] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }

    const hasCompleted = window.localStorage.getItem('seidra_onboarding_completed')
    if (!hasCompleted) {
      setShowOnboarding(true)
    }
  }, [])

  return (
    <WebSocketProvider>
      <div className="min-h-screen seidra-mystical-bg">
        {/* Header */}
        <Header />
        
        <div className="flex">
          {/* Sidebar */}
          <Sidebar 
            activeTab={activeTab} 
            onTabChange={setActiveTab}
            collapsed={sidebarCollapsed}
            onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
          />
          
          {/* Main Content */}
          <main className={`flex-1 transition-all duration-300 ${
            sidebarCollapsed ? 'ml-20' : 'ml-72'
          }`}>
            <div className="p-6">
              {/* Tab Content */}
              {activeTab === 'generate' && <GenerationInterface />}
              {activeTab === 'personas' && <PersonaManager />}
              {activeTab === 'media' && <MediaGallery />}
              {activeTab === 'models' && <ModelManager />}
              {activeTab === 'jobs' && <JobMonitor />}
              {activeTab === 'settings' && <SettingsPanel />}
            </div>
          </main>
        </div>
        
        {/* Toast notifications */}
        <Toaster
          position="bottom-right"
          toastOptions={{
            duration: 4000,
            style: {
              background: 'rgba(13, 12, 40, 0.92)',
              color: '#F4C95D',
              border: '1px solid rgba(244, 201, 93, 0.35)',
              backdropFilter: 'blur(12px)',
            },
            success: {
              iconTheme: {
                primary: '#F4C95D',
                secondary: '#18183F',
              },
            },
            error: {
              iconTheme: {
                primary: '#F16A6F',
                secondary: '#18183F',
              },
            },
          }}
        />
        <OnboardingWizard isOpen={showOnboarding} onClose={() => setShowOnboarding(false)} />
      </div>
    </WebSocketProvider>
  )
}