import { Routes, Route, Navigate } from 'react-router'
import AgentLayout from '@/components/AgentLayout'
import ChatView from '@/components/ChatView'
import TaskList from '@/components/TaskList'
import TaskDetail from '@/components/TaskDetail'
import SettingsView from '@/components/SettingsView'

export default function App() {
  return (
    <Routes>
      <Route element={<AgentLayout />}>
        <Route index element={<Navigate to="/chat" replace />} />
        <Route path="chat" element={<ChatView />} />
        <Route path="chat/:id" element={<ChatView />} />
        <Route path="tasks" element={<TaskList />} />
        <Route path="tasks/:id" element={<TaskDetail />} />
        <Route path="settings" element={<SettingsView />} />
      </Route>
    </Routes>
  )
}
