import RegistryHeader from '@/components/RegistryHeader'
import Footer from '@/components/Footer'

export default function RegistryLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <RegistryHeader />
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  )
}
