import { readFileSync } from 'fs'
import { join } from 'path'
import { renderMarkdown } from '@/lib/markdown'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'OAP + A2A — OAP',
  description: 'How OAP and Google A2A complement each other: discovery meets conversation.',
}

export default async function A2APage() {
  const content = readFileSync(join(process.cwd(), 'docs/A2A.md'), 'utf-8')
  const { html, headings } = await renderMarkdown(content)

  const toc = headings.filter(h => h.level <= 3)

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="lg:grid lg:grid-cols-[240px_1fr] lg:gap-8">
        <aside className="hidden lg:block">
          <nav className="sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
              On this page
            </h2>
            <ul className="space-y-1 text-sm">
              {toc.map((heading) => (
                <li
                  key={heading.id}
                  style={{ paddingLeft: `${(heading.level - 1) * 0.75}rem` }}
                >
                  <a
                    href={`#${heading.id}`}
                    className="block py-1 text-gray-600 hover:text-gray-900"
                  >
                    {heading.text}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </aside>

        <article
          className="prose prose-slate min-w-0 max-w-none overflow-hidden prose-headings:scroll-mt-20"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </div>
    </div>
  )
}
