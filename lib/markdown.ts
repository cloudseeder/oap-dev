import { unified } from 'unified'
import remarkParse from 'remark-parse'
import remarkGfm from 'remark-gfm'
import remarkRehype from 'remark-rehype'
import rehypeSlug from 'rehype-slug'
import rehypeAutolinkHeadings from 'rehype-autolink-headings'
import rehypeHighlight from 'rehype-highlight'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import rehypeStringify from 'rehype-stringify'

// Allow highlight.js classes through sanitization
const sanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    code: [...(defaultSchema.attributes?.code || []), 'className'],
    span: [...(defaultSchema.attributes?.span || []), 'className'],
  },
}

export interface Heading {
  id: string
  text: string
  level: number
}

export async function renderMarkdown(content: string): Promise<{ html: string; headings: Heading[] }> {
  const result = await unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkRehype)
    .use(rehypeSlug)
    .use(rehypeAutolinkHeadings, { behavior: 'wrap' })
    .use(rehypeHighlight, { detect: true })
    .use(rehypeSanitize, sanitizeSchema)
    .use(rehypeStringify)
    .process(content)

  const html = String(result)

  // Extract headings from the markdown source
  const headings: Heading[] = []
  const headingRegex = /^(#{1,4})\s+(.+)$/gm
  let match
  while ((match = headingRegex.exec(content)) !== null) {
    const level = match[1].length
    const text = match[2].replace(/\*\*/g, '').replace(/`/g, '').trim()
    const id = text
      .toLowerCase()
      .replace(/[^\w\s-]/g, '')
      .replace(/\s+/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '')
    headings.push({ id, text, level })
  }

  return { html, headings }
}
