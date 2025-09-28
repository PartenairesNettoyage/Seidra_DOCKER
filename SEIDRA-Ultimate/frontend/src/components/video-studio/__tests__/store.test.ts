import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api-client', () => {
  return {
    apiClient: {
      uploadVideoAsset: vi.fn(),
      createVideoTimeline: vi.fn(),
      queueVideoRender: vi.fn(),
      listJobs: vi.fn(),
      getVideoAssetWaveform: vi.fn(),
      queueVideoProxyRender: vi.fn(),
      getVideoProxyPreview: vi.fn(),
    },
  }
})

import { apiClient } from '@/lib/api-client'
import { proxyPreviewInitialState, useVideoStudioStore } from '../store'

type MockedClient = typeof apiClient & {
  getVideoAssetWaveform: ReturnType<typeof vi.fn>
  queueVideoProxyRender: ReturnType<typeof vi.fn>
}

const mockedApi = apiClient as MockedClient

describe('useVideoStudioStore – récupération distante', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useVideoStudioStore.getState().reset()
  })

  it('récupère la waveform distante et met à jour les métadonnées', async () => {
    const waveform = [0.12, 0.45, 0.67]
    mockedApi.getVideoAssetWaveform.mockResolvedValue({
      asset_id: 'asset-1',
      waveform,
      generated_at: '2024-01-01T00:00:00Z',
      status: 'ready',
      sample_rate: 44100,
    })

    useVideoStudioStore.setState((state) => ({
      assets: [
        {
          id: 'asset-1',
          name: 'Audio test',
          kind: 'audio',
          duration: 4,
          status: 'ready',
          fileSize: 1024,
          createdAt: new Date().toISOString(),
          waveform: undefined,
          waveformStatus: 'idle',
          waveformUpdatedAt: null,
          waveformError: null,
        },
        ...state.assets,
      ],
    }))

    const result = await useVideoStudioStore.getState().fetchWaveform('asset-1')
    const asset = useVideoStudioStore.getState().assets.find((item) => item.id === 'asset-1')

    expect(result).toEqual(waveform)
    expect(asset?.waveformStatus).toBe('ready')
    expect(asset?.waveform).toEqual(waveform)
    expect(asset?.waveformUpdatedAt).toBe('2024-01-01T00:00:00Z')
    expect(mockedApi.getVideoAssetWaveform).toHaveBeenCalledWith('asset-1')
  })

  it("laisse l’asset en chargement lorsque l’API signale un calcul en cours", async () => {
    mockedApi.getVideoAssetWaveform.mockResolvedValue({
      asset_id: 'asset-2',
      waveform: [],
      status: 'processing',
    })

    useVideoStudioStore.setState((state) => ({
      assets: [
        {
          id: 'asset-2',
          name: 'Audio en attente',
          kind: 'audio',
          duration: 8,
          status: 'ready',
          fileSize: 2048,
          createdAt: new Date().toISOString(),
          waveform: [],
          waveformStatus: 'loading',
          waveformUpdatedAt: null,
          waveformError: null,
        },
        ...state.assets,
      ],
    }))

    const result = await useVideoStudioStore.getState().fetchWaveform('asset-2')
    const asset = useVideoStudioStore.getState().assets.find((item) => item.id === 'asset-2')

    expect(result).toBeNull()
    expect(asset?.waveformStatus).toBe('loading')
    expect(asset?.waveform).toEqual([])
  })

  it('réutilise le proxy en cache lorsque déjà prêt', async () => {
    mockedApi.queueVideoProxyRender.mockResolvedValue({
      job_id: 'proxy-job',
      status: 'ready',
      proxy_url: 'https://example.com/proxy.mp4',
      updated_at: '2024-01-01T00:00:00Z',
      message: 'Proxy prêt',
    })

    useVideoStudioStore.setState({
      timelineId: 'timeline-123',
      proxyPreview: {
        ...proxyPreviewInitialState,
        status: 'ready',
        url: 'https://example.com/proxy.mp4',
        jobId: 'proxy-job',
        updatedAt: '2024-01-01T00:00:00Z',
      },
    })

    const response = await useVideoStudioStore.getState().requestProxyPreview()

    expect(response?.proxy_url).toBe('https://example.com/proxy.mp4')
    expect(mockedApi.queueVideoProxyRender).not.toHaveBeenCalled()
  })

  it('permet de forcer un nouveau rendu proxy', async () => {
    mockedApi.queueVideoProxyRender.mockResolvedValue({
      job_id: 'proxy-new',
      status: 'processing',
      proxy_url: null,
      updated_at: '2024-01-02T00:00:00Z',
      message: 'Proxy relancé',
    })

    useVideoStudioStore.setState({ timelineId: 'timeline-999' })

    const response = await useVideoStudioStore.getState().requestProxyPreview({ force: true })

    expect(mockedApi.queueVideoProxyRender).toHaveBeenCalledWith('timeline-999', { force: true })
    expect(response?.status).toBe('processing')
  })

  it('reset réinitialise la prévisualisation proxy', () => {
    useVideoStudioStore.setState({
      assets: [
        {
          id: 'asset-x',
          name: 'Vidéo',
          kind: 'video',
          duration: 10,
          status: 'ready',
          fileSize: 2048,
          createdAt: new Date().toISOString(),
        },
      ],
      proxyPreview: {
        ...proxyPreviewInitialState,
        status: 'ready',
        url: 'https://example.com/cache.mp4',
      },
    })

    useVideoStudioStore.getState().reset()

    expect(useVideoStudioStore.getState().assets).toHaveLength(0)
    expect(useVideoStudioStore.getState().proxyPreview).toEqual(proxyPreviewInitialState)
  })
})
