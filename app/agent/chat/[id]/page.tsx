import ChatView from '@/components/agent/ChatView'

export default async function ExistingChatPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  return <ChatView conversationId={id} />
}
