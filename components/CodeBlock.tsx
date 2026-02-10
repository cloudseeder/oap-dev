interface CodeBlockProps {
  code: string
  language?: string
  title?: string
}

export default function CodeBlock({ code, title }: CodeBlockProps) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-800 bg-slate-900">
      {title && (
        <div className="border-b border-gray-700 bg-slate-800 px-4 py-2 text-xs text-gray-400">
          {title}
        </div>
      )}
      <pre className="overflow-x-auto p-4 text-sm leading-relaxed text-gray-100">
        <code>{code}</code>
      </pre>
    </div>
  )
}
