import TaskDetail from '@/components/agent/TaskDetail'

export default async function TaskDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  return <TaskDetail taskId={id} />
}
