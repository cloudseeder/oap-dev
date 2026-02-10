import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'OAP — Open Application Protocol',
  description: 'A decentralized discovery and trust layer for web applications, designed for AI agents.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">
        {children}
      </body>
    </html>
  )
}
