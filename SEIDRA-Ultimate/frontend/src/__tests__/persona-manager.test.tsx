import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { PersonaManager } from '../components/personas/persona-manager'

const fetchMock = vi.hoisted(() => vi.fn())

;(globalThis as unknown as { React?: typeof React }).React = React

vi.mock('react-hot-toast', () => {
  const toast = {
    success: vi.fn(),
    error: vi.fn(),
  }
  return { toast }
})

vi.mock('@/lib/hooks', async () => {
  const actual = await vi.importActual<typeof import('@/lib/hooks')>('@/lib/hooks')
  return {
    ...actual,
    usePersonas: vi.fn(() => ({
      personas: [
        {
          id: 1,
          name: 'Neon Muse',
          description: 'Cybernetic portrait artist',
          style_prompt: 'futuristic neon portrait',
          negative_prompt: '',
          lora_models: [],
          generation_params: {},
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      ],
      isLoading: false,
      error: null,
      isMutating: false,
      refresh: vi.fn(),
      createPersona: vi.fn(),
      updatePersona: vi.fn(),
      deletePersona: vi.fn(),
      duplicatePersona: vi.fn(),
    })),
    useModels: vi.fn(() => ({
      models: [],
      status: null,
      isLoading: false,
      error: null,
      pending: new Set<string>(),
      refresh: vi.fn(),
      downloadModel: vi.fn(),
      deleteModel: vi.fn(),
      reloadModels: vi.fn(),
      clearModelCache: vi.fn(),
    })),
  }
})

const originalFetch = global.fetch

const jsonHeaders = {
  get: (name: string) => (name.toLowerCase() === 'content-type' ? 'application/json' : null),
}

describe('PersonaManager preview workflow', () => {
  beforeEach(() => {
    fetchMock.mockImplementation((input) => {
      const url = String(input)
      if (url.includes('/personas/1/preview')) {
        const data = {
          job_id: 'preview-job-001',
          status: 'queued',
          message: 'Preview job queued',
          persona_id: 1,
          estimated_time: 30,
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: jsonHeaders,
          json: async () => data,
          text: async () => JSON.stringify(data),
        })
      }
      return Promise.reject(new Error(`Unhandled fetch URL: ${url}`))
    })
    global.fetch = fetchMock as unknown as typeof fetch
  })

  afterEach(() => {
    fetchMock.mockReset()
    global.fetch = originalFetch
  })

  it('launches a preview job and surfaces the job details', async () => {
    const user = userEvent.setup()
    render(<PersonaManager />)

    await user.click(await screen.findByRole('button', { name: 'Preview' }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find((entry) => String(entry[0]).includes('/personas/1/preview'))
      expect(call).toBeDefined()
    })

    await waitFor(() => expect(screen.getByText(/preview job started/i)).toBeInTheDocument())
    expect(screen.getByText('Job ID: preview-job-001')).toBeInTheDocument()
    expect(screen.getByText(/Estimated time: ~30s/)).toBeInTheDocument()

    const { toast } = await import('react-hot-toast')
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('preview-job-001 queued'))
  })
})
