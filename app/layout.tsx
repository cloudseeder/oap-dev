import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'OAP — Open Application Protocol',
  description: 'A cognitive API layer for artificial intelligence. Manifest spec that lets AI learn about capabilities at runtime.',
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
