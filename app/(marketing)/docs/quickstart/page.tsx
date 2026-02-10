import CodeBlock from '@/components/CodeBlock'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Quick Start — OAP',
  description: 'Get your app discoverable by AI agents in 5 minutes.',
}

export default function QuickStartPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
      <h1 className="text-3xl font-bold text-gray-900">Quick Start</h1>
      <p className="mt-2 text-gray-600">
        Get your app discoverable by AI agents in 5 minutes.
      </p>

      {/* Step 1 */}
      <div className="mt-10">
        <StepHeader number={1} title="Create your manifest" />
        <p className="mt-2 text-sm text-gray-600">
          Create a file at <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs">/.well-known/oap.json</code> in your app&apos;s public root.
          Use the interactive generator or write it by hand:
        </p>
        <div className="mt-4">
          <CodeBlock
            title="/.well-known/oap.json"
            code={`{
  "oap_version": "0.1",
  "identity": {
    "name": "Your App Name",
    "tagline": "One-line description (max 120 chars)",
    "description": "What your app does — written for AI comprehension (max 500 chars)",
    "url": "https://yourapp.com"
  },
  "builder": {
    "name": "Your Name or Company"
  },
  "capabilities": {
    "summary": "Detailed natural language description for semantic matching...",
    "solves": [
      "problem your app solves #1",
      "problem your app solves #2",
      "problem your app solves #3"
    ],
    "ideal_for": [
      "target user #1",
      "target user #2"
    ],
    "categories": ["your-category"],
    "differentiators": ["what makes you unique"]
  },
  "pricing": {
    "model": "freemium",
    "trial": { "available": true }
  },
  "trust": {
    "data_practices": {
      "collects": ["email addresses"],
      "stores_in": "US-based cloud",
      "shares_with": ["none"]
    },
    "security": {
      "authentication": ["email/password"]
    },
    "external_connections": ["AI language model API"]
  },
  "integration": {
    "api": { "available": false }
  },
  "verification": {
    "health_endpoint": "https://yourapp.com/api/health"
  }
}`}
          />
        </div>
        <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">
          Or use the CLI generator: <code className="rounded bg-blue-100 px-1.5 py-0.5 text-xs">node tools/generate.js</code>
        </div>
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
curl https://yourapp.com/.well-known/oap.json | jq .

# Validate it against the spec
node tools/validate.js https://yourapp.com/.well-known/oap.json`}
          />
        </div>
      </div>

      {/* Step 3 */}
      <div className="mt-10">
        <StepHeader number={3} title="Add DNS TXT record (optional)" />
        <p className="mt-2 text-sm text-gray-600">
          Add a TXT record at <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs">_oap.yourapp.com</code> to prove domain ownership.
          This is optional but increases trust signals for AI agents.
        </p>
        <div className="mt-4">
          <CodeBlock
            title="DNS TXT Record"
            code={`_oap.yourapp.com  TXT  "v=oap1; cat=your-category; manifest=https://yourapp.com/.well-known/oap.json"`}
          />
        </div>
      </div>

      {/* Step 4 */}
      <div className="mt-10">
        <StepHeader number={4} title="Register with the OAP Registry" />
        <p className="mt-2 text-sm text-gray-600">
          Register your app with a single API call. No approval needed &mdash; it&apos;s like publishing to npm.
        </p>
        <div className="mt-4">
          <CodeBlock
            code={`curl -X POST https://registry.oap.dev/api/v1/register \\
  -H "Content-Type: application/json" \\
  -d '{"url": "https://yourapp.com"}'`}
          />
        </div>
      </div>

      {/* Step 5 */}
      <div className="mt-10">
        <StepHeader number={5} title="Verify" />
        <p className="mt-2 text-sm text-gray-600">
          Check that your app appears in the registry:
        </p>
        <div className="mt-4">
          <CodeBlock
            code={`# Check your app details
curl https://registry.oap.dev/api/v1/apps/yourapp.com | jq .

# Search for your app
curl "https://registry.oap.dev/api/v1/search?q=your+app+name" | jq .`}
          />
        </div>
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
