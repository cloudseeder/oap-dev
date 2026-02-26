import AgentSidebar from '@/components/agent/AgentSidebar'
import AgentEventProvider from '@/components/agent/AgentEventProvider'

export default function AgentLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <AgentEventProvider>
      <div className="flex h-screen overflow-hidden bg-white">
        <AgentSidebar />
        <main className="flex flex-1 flex-col overflow-hidden">
          {children}
        </main>
      </div>
    </AgentEventProvider>
  )
}
