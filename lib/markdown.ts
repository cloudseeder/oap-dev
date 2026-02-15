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

  // Extract headings from the rendered HTML so IDs match rehype-slug exactly
  const headings: Heading[] = []
  const headingRegex = /<h([1-4])\s+id="([^"]+)"[^>]*>(?:<a[^>]*>)?([^<]*(?:<code>[^<]*<\/code>[^<]*)*)(?:<\/a>)?<\/h[1-4]>/g
  let match
  while ((match = headingRegex.exec(html)) !== null) {
    const level = parseInt(match[1], 10)
    const id = match[2]
    const text = match[3].replace(/<[^>]+>/g, '').trim()
    if (id && text) {
      headings.push({ id, text, level })
    }
  }

  return { html, headings }
}
