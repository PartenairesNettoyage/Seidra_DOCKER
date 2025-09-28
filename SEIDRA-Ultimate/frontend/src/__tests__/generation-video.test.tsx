import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { GenerationInterface } from '../components/generation/generation-interface'

const fetchMock = vi.hoisted(() => vi.fn())

vi.mock('react-hot-toast', () => {
  const toast = {
    success: vi.fn(),
    error: vi.fn(),
    promise: vi.fn(),
  }
  return { toast }
})

vi.mock('@/lib/hooks', async () => {
  const actual = await vi.importActual<typeof import('@/lib/hooks')>('@/lib/hooks')
  return {
    ...actual,
    usePersonas: vi.fn(() => ({ personas: [], isLoading: false, error: null })),
    useModels: vi.fn(() => ({
      models: [
        {
          id: 'sdxl-base',
          name: 'SDXL Base',
          description: 'Base diffusion model',
          type: 'base',
          size: '1.5GB',
          is_downloaded: true,
        },
      ],
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

vi.mock('@/lib/websocket-context', () => ({
  useWebSocketStatus: vi.fn(() => ({ status: 'connected', jobUpdates: {} })),
}))

const originalFetch = global.fetch

const jsonHeaders = {
  get: (name: string) => (name.toLowerCase() === 'content-type' ? 'application/json' : null),
}

describe('GenerationInterface video workflow', () => {
  beforeEach(() => {
    fetchMock.mockImplementation((input) => {
      const url = String(input)
      if (url.includes('/jobs')) {
        const data = { jobs: [] }
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: jsonHeaders,
          json: async () => data,
          text: async () => JSON.stringify(data),
        })
      }
      if (url.includes('/generate/video')) {
        const data = { job_id: 'job-video-001', status: 'queued', message: 'queued' }
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

  it('queues a video generation job with audio payload', async () => {
    const user = userEvent.setup()
    render(<GenerationInterface />)

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())

    await user.type(screen.getByLabelText('Video prompt'), 'Epic hero speech in neon city')
    await user.type(
      screen.getByLabelText('Reference image URL (optional)'),
      'https://example.com/hero.png',
    )

    const audioFile = new File(['test'], 'voice.wav', { type: 'audio/wav' })
    await user.upload(screen.getByLabelText('Audio track'), audioFile)

    const durationInput = screen.getByLabelText('Duration (seconds)') as HTMLInputElement
    fireEvent.change(durationInput, { target: { value: '12' } })
    await waitFor(() => expect(durationInput).toHaveValue(12))

    await user.click(screen.getByRole('button', { name: 'Generate video' }))

    await waitFor(() => {
      const videoCall = fetchMock.mock.calls.find((call) => String(call[0]).includes('/generate/video'))
      expect(videoCall).toBeDefined()
    })

    const videoCall = fetchMock.mock.calls.find((call) => String(call[0]).includes('/generate/video'))
    const requestInit = (videoCall?.[1] ?? {}) as RequestInit
    expect(requestInit.body).toBeInstanceOf(FormData)
    const formData = requestInit.body as FormData
    expect(formData.get('prompt')).toBe('Epic hero speech in neon city')
    expect(formData.get('reference_image')).toBe('https://example.com/hero.png')
    expect(formData.get('duration_seconds')).toBe('12')
    expect(formData.get('audio_file')).toBeInstanceOf(File)

    await waitFor(() => expect(screen.getByText('QUEUED')).toBeInTheDocument())
  })

  it('shows validation error when audio is missing', async () => {
    const user = userEvent.setup()
    render(<GenerationInterface />)

    await user.type(screen.getByLabelText('Video prompt'), 'A silent prompt')
    await user.click(screen.getByRole('button', { name: 'Generate video' }))

    const { toast } = await import('react-hot-toast')
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('An audio track is required'))
    const videoCall = fetchMock.mock.calls.find((call) => String(call[0]).includes('/generate/video'))
    expect(videoCall).toBeUndefined()
  })
})
