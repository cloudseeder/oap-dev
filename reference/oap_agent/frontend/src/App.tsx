import { Routes, Route, Navigate } from 'react-router'
import AgentLayout from '@/components/AgentLayout'
import ChatView from '@/components/ChatView'
import TaskList from '@/components/TaskList'
import TaskDetail from '@/components/TaskDetail'

export default function App() {
  return (
    <Routes>
      <Route element={<AgentLayout />}>
        <Route index element={<Navigate to="/chat" replace />} />
        <Route path="chat" element={<ChatView />} />
        <Route path="chat/:id" element={<ChatView />} />
        <Route path="tasks" element={<TaskList />} />
        <Route path="tasks/:id" element={<TaskDetail />} />
      </Route>
    </Routes>
  )
}
