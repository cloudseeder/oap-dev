import { Outlet } from 'react-router'
import AgentSidebar from './AgentSidebar'
import AgentEventProvider from './AgentEventProvider'

export default function AgentLayout() {
  return (
    <AgentEventProvider>
      <div className="flex h-screen overflow-hidden bg-white">
        <AgentSidebar />
        <main className="flex flex-1 flex-col overflow-hidden">
          <Outlet />
        </main>
      </div>
    </AgentEventProvider>
  )
}
