import path from 'node:path'

import { expect, test } from '@playwright/test'

const fixture = path.join(__dirname, 'fixtures', 'sample-audio.mp3')

test.describe('Studio vidéo', () => {
  test('ouverture du studio sur chaque navigateur', async ({ page }) => {
    await page.goto('/studio/video')

    await expect(page.getByRole('heading', { name: 'Studio vidéo' })).toBeVisible()
    await expect(page.getByTestId('asset-file-input')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sauvegarder la timeline' })).toBeVisible()
  })

  test.describe('Scénarios spécifiques Chromium', () => {
    test.skip(({ browserName }) => browserName !== 'chromium', 'Le glisser-déposer de la timeline est stabilisé uniquement sous Chromium pour le moment.')

    test('upload d’un asset et placement sur la timeline', async ({ page }) => {
      const uploadedId = 'asset-123'
      const timelineId = 'timeline-456'
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
              duration: 8,
              file_size: 1024,
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

      await page.route(`**/api/generate/video/timeline`, async (route, request) => {
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
              total_duration: payload.total_duration ?? 8,
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

      await page.route(`**/api/generate/video/timeline/${timelineId}/render`, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            job_id: 'job-video-1',
            status: 'queued',
            message: 'Timeline render job queued successfully',
            estimated_time: 12,
          }),
        })
      })

      await page.route('**/api/jobs**', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            total: 1,
            jobs: [
              {
                job_id: 'job-video-1',
                status: 'queued',
                progress: 0.25,
                job_type: 'video_timeline',
                created_at: now,
                updated_at: now,
                result_images: ['https://example.com/render.mp4'],
                message: 'En file d’attente',
              },
            ],
          }),
        })
      })

      await page.goto('/studio/video')

      await expect(page.getByRole('heading', { name: 'Studio vidéo' })).toBeVisible()

      await page.setInputFiles('[data-testid="asset-file-input"]', fixture)

      const assetItem = page.locator('[data-testid^="asset-item-"]').first()
      await expect(assetItem).toContainText('sample-audio.mp3')
      await expect(assetItem.getByText('Ouvrir dans Media API')).toBeVisible()

      const videoTrack = page.locator('[data-testid="timeline-video-track"]')
      await assetItem.dragTo(videoTrack)

      await expect(page.locator('[data-testid^="timeline-clip-"]')).toHaveCount(1)

      await page.getByRole('button', { name: 'Sauvegarder la timeline' }).click()
      await page.getByRole('button', { name: 'Lancer un rendu' }).click()

      const slider = page.locator('[data-testid="frame-slider"]')
      await slider.evaluate((element, value) => {
        const input = element as HTMLInputElement
        input.value = value
        input.dispatchEvent(new Event('input', { bubbles: true }))
        input.dispatchEvent(new Event('change', { bubbles: true }))
      }, '120')

      await expect(page.locator('[data-testid="frame-value"]')).toHaveText('120')
      await expect(page.getByText(`ID backend : ${timelineId}`)).toBeVisible()
      await expect(page.getByText('En file d’attente')).toBeVisible()
      await expect(page.getByRole('link', { name: 'Voir le média' })).toBeVisible()
    })
  })
})
