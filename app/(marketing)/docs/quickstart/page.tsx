import CodeBlock from '@/components/CodeBlock'
import Link from 'next/link'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Quick Start — OAP',
  description: 'Get your capability discoverable by AI agents in 5 minutes.',
}

export default function QuickStartPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
      <h1 className="text-3xl font-bold text-gray-900">Quick Start</h1>
      <p className="mt-2 text-gray-600">
        Make your capability discoverable by AI agents in 5 minutes.
      </p>

      {/* Step 1 */}
      <div className="mt-10">
        <StepHeader number={1} title="Create your manifest" />
        <p className="mt-2 text-sm text-gray-600">
          Create a file at <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs">/.well-known/oap.json</code> in your app&apos;s public root.
          Only four fields are required: <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs">oap</code>,{' '}
          <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs">name</code>,{' '}
          <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs">description</code>,{' '}
          <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs">invoke</code>.
        </p>
        <div className="mt-4">
          <CodeBlock
            title="/.well-known/oap.json"
            code={`{
  "oap": "1.0",
  "name": "Your Capability",
  "description": "What this does, what it accepts, what it produces. Write it like a man page — specific, clear, action-oriented. Max 1000 chars.",
  "input": {
    "format": "application/json",
    "description": "JSON object with a text field"
  },
  "output": {
    "format": "application/json",
    "description": "JSON object with a result field"
  },
  "invoke": {
    "method": "POST",
    "url": "https://yourapp.com/api/endpoint"
  },
  "tags": ["your-category"],
  "publisher": { "name": "Your Name" }
}`}
          />
        </div>
        <p className="mt-3 text-sm text-gray-500">
          The <code className="rounded bg-gray-100 px-1 py-0.5 text-xs">description</code> field
          is the most important &mdash; it&apos;s the text an LLM reads to decide if your capability
          fits a task.{' '}
          <Link href="/spec" className="text-primary hover:underline">Read the full spec</Link>.
        </p>
      </div>

      {/* Step 2 */}
      <div className="mt-10">
        <StepHeader number={2} title="Deploy your manifest" />
        <p className="mt-2 text-sm text-gray-600">
          Make sure your manifest is accessible at <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs">https://yourapp.com/.well-known/oap.json</code>.
          Most frameworks serve static files from a <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs">public/</code> directory.
        </p>
        <div className="mt-4">
          <CodeBlock
            code={`# Test that your manifest is accessible
curl https://yourapp.com/.well-known/oap.json | jq .`}
          />
        </div>
      </div>

      {/* Step 3 */}
      <div className="mt-10">
        <StepHeader number={3} title="Validate" />
        <p className="mt-2 text-sm text-gray-600">
          Use the <Link href="/playground" className="text-primary hover:underline">Playground</Link> to
          validate your manifest against the v1.0 spec. Paste the JSON or enter your URL.
        </p>
      </div>

      {/* Step 4 */}
      <div className="mt-10">
        <StepHeader number={4} title="Get discovered" />
        <p className="mt-2 text-sm text-gray-600">
          That&apos;s it. Crawlers index manifests at the well-known path. Anyone running a{' '}
          <Link href="/docs/architecture" className="text-primary hover:underline">discovery stack</Link>{' '}
          will find your capability via vector search + LLM matching.
        </p>
        <p className="mt-2 text-sm text-gray-600">
          No registration, no approval, no fees. The web model, not the registry model.
        </p>
      </div>

      {/* Optional: Trust */}
      <div className="mt-10">
        <StepHeader number={5} title="Build trust (optional)" />
        <p className="mt-2 text-sm text-gray-600">
          Add a <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs">health</code> endpoint
          to your manifest for liveness checks. For higher trust, use the{' '}
          <Link href="/trust" className="text-primary hover:underline">trust overlay</Link> to
          get domain and capability attestations.
        </p>
      </div>

      {/* AI Agent Callout */}
      <div className="mt-12 rounded-lg border border-primary-200 bg-primary-50 p-6">
        <h3 className="font-semibold text-primary-800">For AI Coding Tools</h3>
        <p className="mt-2 text-sm text-primary-700">
          You can tell your AI coding assistant: &ldquo;Add OAP support to my app.
          Read the spec at oap.dev/spec and create a manifest at .well-known/oap.json
          that accurately describes this application.&rdquo;
        </p>
      </div>
    </div>
  )
}

function StepHeader({ number, title }: { number: number; title: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-sm font-bold text-white">
        {number}
      </div>
      <h2 className="text-xl font-semibold text-gray-900">{title}</h2>
    </div>
  )
}
