import path from 'node:path'

import { expect, test } from '@playwright/test'

const fixture = path.join(__dirname, 'fixtures', 'sample-audio.mp3')

test.describe('Studio vidéo – rendus proxy', () => {
  test('interface proxy accessible sur chaque navigateur', async ({ page }) => {
    await page.goto('/studio/video')

    await expect(page.getByRole('heading', { name: 'Studio vidéo' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Générer un proxy' })).toBeVisible()
  })

  test.describe('Scénarios spécifiques Chromium', () => {
    test.skip(({ browserName }) => browserName !== 'chromium', 'Workflow proxy complet stabilisé uniquement sous Chromium actuellement.')

    test('génération d’un proxy et affichage des waveforms', async ({ page }) => {
      const uploadedId = 'asset-audio'
      const timelineId = 'timeline-proxy'
      const now = new Date().toISOString()

      await page.route('**/api/media/video-assets', async (route, request) => {
        if (request.method() === 'POST') {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              id: uploadedId,
              name: 'sample-audio.mp3',
              kind: 'audio',
              duration: 6,
              file_size: 2048,
              status: 'ready',
              url: `/media/video-assets/${uploadedId}`,
              download_url: `/media/video-assets/${uploadedId}`,
              created_at: now,
              mime_type: 'audio/mpeg',
            }),
          })
          return
        }
        await route.continue()
      })

      await page.route(`**/api/media/video-assets/${uploadedId}/waveform`, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            asset_id: uploadedId,
            waveform: Array.from({ length: 32 }, (_, index) => Number((Math.abs(Math.sin(index)) * 0.8 + 0.1).toFixed(2))),
            generated_at: now,
          }),
        })
      })

      await page.route('**/api/generate/video/timeline', async (route, request) => {
        if (request.method() === 'POST') {
          const payload = request.postDataJSON() as Record<string, unknown>
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              id: timelineId,
              name: payload.name ?? 'Montage',
              description: payload.description ?? '',
              frame_rate: payload.frame_rate ?? 24,
              total_duration: payload.total_duration ?? 6,
              job_id: null,
              created_at: now,
              updated_at: now,
              assets: payload.assets ?? [],
              clips: payload.clips ?? [],
            }),
          })
          return
        }
        await route.continue()
      })

      await page.route(`**/api/generate/video/timeline/${timelineId}/proxy`, async (route, request) => {
        if (request.method() === 'POST') {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              job_id: 'proxy-job-1',
              status: 'ready',
              proxy_url: 'https://example.com/proxy.mp4',
              updated_at: now,
              message: 'Proxy disponible',
            }),
          })
          return
        }

        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            job_id: 'proxy-job-1',
            status: 'ready',
            proxy_url: 'https://example.com/proxy.mp4',
            updated_at: now,
            message: 'Proxy disponible',
          }),
        })
      })

      await page.goto('/studio/video')

      await page.setInputFiles('[data-testid="asset-file-input"]', fixture)

      const assetItem = page.locator('[data-testid^="asset-item-"]').first()
      await expect(assetItem).toContainText('Waveform calculée')

      const videoTrack = page.locator('[data-testid="timeline-video-track"]')
      await assetItem.dragTo(videoTrack)

      await page.getByRole('button', { name: 'Sauvegarder la timeline' }).click()
      await page.getByRole('button', { name: 'Générer un proxy' }).click()

      await expect(page.getByRole('link', { name: 'Ouvrir le proxy' })).toBeVisible()
      await expect(page.locator('[data-testid="proxy-preview-video"]')).toHaveAttribute('src', 'https://example.com/proxy.mp4')
      await expect(page.getByText('Proxy prêt')).toBeVisible()
    })
  })
})
