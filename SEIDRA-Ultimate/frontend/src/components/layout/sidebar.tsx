'use client'

import { useEffect, useRef } from 'react'
import type { KeyboardEvent } from 'react'

const tabs = [
  { id: 'generate', label: 'Generate' },
  { id: 'personas', label: 'Personas' },
  { id: 'media', label: 'Media' },
  { id: 'models', label: 'Models' },
  { id: 'jobs', label: 'Jobs' },
  { id: 'settings', label: 'Settings' },
]

type SidebarProps = {
  activeTab: string
  onTabChange: (tab: string) => void
  collapsed: boolean
  onToggleCollapse: () => void
}

export function Sidebar({ activeTab, onTabChange, collapsed, onToggleCollapse }: SidebarProps) {
  const navId = 'seidra-primary-navigation'
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([])

  useEffect(() => {
    itemRefs.current = itemRefs.current.slice(0, tabs.length)
  }, [])

  const focusByOffset = (currentIndex: number, offset: number) => {
    const nextIndex = (currentIndex + offset + tabs.length) % tabs.length
    itemRefs.current[nextIndex]?.focus()
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    switch (event.key) {
      case 'ArrowDown': {
        event.preventDefault()
        focusByOffset(index, 1)
        break
      }
      case 'ArrowUp': {
        event.preventDefault()
        focusByOffset(index, -1)
        break
      }
      case 'Home': {
        event.preventDefault()
        itemRefs.current[0]?.focus()
        break
      }
      case 'End': {
        event.preventDefault()
        itemRefs.current[tabs.length - 1]?.focus()
        break
      }
      default:
        break
    }
  }

  return (
    <aside
      aria-label="Barre latérale principale"
      className={`${collapsed ? 'w-20' : 'w-72'} relative min-h-[calc(100vh-64px)] border-r border-midnight-700/60 bg-midnight-900/60 text-midnight-100 backdrop-blur transition-all`}
    >
      <button
        onClick={onToggleCollapse}
        aria-controls={navId}
        aria-expanded={!collapsed}
        aria-label={collapsed ? 'Déployer la navigation' : 'Réduire la navigation'}
        className="absolute -right-3 top-6 rounded-full border border-midnight-600/70 bg-midnight-800 px-2 py-1 text-xs text-gold-200 transition hover:bg-midnight-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold-300"
        type="button"
      >
        {collapsed ? '→' : '←'}
      </button>
      <nav
        aria-label="Navigation principale"
        className="mt-16 flex flex-col gap-2 px-4"
        id={navId}
        role="navigation"
      >
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            aria-current={activeTab === tab.id ? 'page' : undefined}
            aria-label={collapsed ? tab.label : undefined}
            className={`rounded-lg px-4 py-3 text-left text-sm font-medium transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold-300 ${
              activeTab === tab.id
                ? 'bg-midnight-700 text-gold-100'
                : 'text-midnight-50 hover:bg-midnight-800'
            }`}
            onClick={() => onTabChange(tab.id)}
            onKeyDown={(event) => handleKeyDown(event, index)}
            ref={(element) => {
              itemRefs.current[index] = element
            }}
            type="button"
          >
            {collapsed ? tab.label.charAt(0) : tab.label}
          </button>
        ))}
      </nav>
    </aside>
  )
}
