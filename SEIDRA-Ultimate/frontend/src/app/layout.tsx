import type { Metadata, Viewport } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'

const inter = Inter({ subsets: ['latin'] })

const DEFAULT_SITE_URL = 'http://localhost:3000'

const metadataBase = (() => {
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL

  try {
    return new URL(siteUrl ?? DEFAULT_SITE_URL)
  } catch {
    return new URL(DEFAULT_SITE_URL)
  }
})()

export const metadata: Metadata = {
  metadataBase,
  title: 'SEIDRA - Build your own myth',
  description: 'Premium AI content generation platform with Stable Diffusion XL and mystical design',
  keywords: 'AI, Stable Diffusion, LoRA, image generation, mystical, premium',
  authors: [{ name: 'SEIDRA Team' }],
  icons: {
    icon: '/favicon.ico',
    apple: '/apple-touch-icon.png',
  },
  openGraph: {
    title: 'SEIDRA - Build your own myth',
    description: 'Premium AI content generation platform',
    type: 'website',
    locale: 'en_US',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'SEIDRA - Build your own myth',
    description: 'Premium AI content generation platform',
  },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#FFD700',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} seidra-mystical-bg min-h-screen`}>
        {/* Mystical floating particles */}
        <div className="seidra-floating-particles">
          <div className="seidra-particle"></div>
          <div className="seidra-particle"></div>
          <div className="seidra-particle"></div>
          <div className="seidra-particle"></div>
          <div className="seidra-particle"></div>
          <div className="seidra-particle"></div>
          <div className="seidra-particle"></div>
          <div className="seidra-particle"></div>
          <div className="seidra-particle"></div>
        </div>
        
        {children}
      </body>
    </html>
  )
}