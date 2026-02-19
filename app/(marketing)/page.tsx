import Link from 'next/link'
import CodeBlock from '@/components/CodeBlock'

export default function LandingPage() {
  return (
    <div>
      {/* Hero */}
      <section className="bg-gradient-to-b from-primary-50 to-white px-4 py-20 text-center">
        <h1 className="mx-auto max-w-3xl text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl">
          The cognitive API layer{' '}
          <span className="text-primary">for artificial intelligence</span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-gray-600">
          OAP is a manifest spec that lets AI learn about capabilities that weren&apos;t in its
          training data, at runtime, without retraining. Publish a JSON file. Get discovered.
        </p>
        <div className="mt-8 flex items-center justify-center gap-4">
          <Link
            href="/playground"
            className="rounded-lg bg-primary px-6 py-3 text-sm font-medium text-white hover:bg-primary-600"
          >
            Open Playground
          </Link>
          <Link
            href="/spec"
            className="rounded-lg border border-gray-300 px-6 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Read the Spec
          </Link>
        </div>
      </section>

      {/* What It Does */}
      <section className="mx-auto max-w-4xl px-4 py-16">
        <h2 className="text-center text-2xl font-bold text-gray-900">How It Works</h2>
        <div className="mt-12 grid gap-8 md:grid-cols-3">
          <Step
            number={1}
            title="Describe"
            description="Host a JSON manifest at /.well-known/oap.json. Four required fields: name, description, invoke, version."
          />
          <Step
            number={2}
            title="Discover"
            description="Crawlers index your manifest. A small LLM matches agent tasks to capability descriptions via vector search."
          />
          <Step
            number={3}
            title="Invoke"
            description="The agent reads the manifest, understands what you accept and produce, and calls your endpoint."
          />
        </div>

        <div className="mt-12">
          <CodeBlock
            title="/.well-known/oap.json"
            code={`{
  "oap": "1.0",
  "name": "Text Summarizer",
  "description": "Accepts plain text (max 10,000 words) and returns a concise summary. Preserves key facts, strips filler. Input: raw text via POST body. Output: JSON with summary field.",
  "input": { "format": "text/plain", "description": "Raw text to summarize" },
  "output": { "format": "application/json", "description": "JSON with summary field" },
  "invoke": { "method": "POST", "url": "https://example.com/api/summarize" }
}`}
          />
        </div>
      </section>

      {/* Developer Tools */}
      <section className="bg-gray-50 px-4 py-16">
        <div className="mx-auto max-w-4xl">
          <h2 className="text-center text-2xl font-bold text-gray-900">Developer Tools</h2>
          <div className="mt-8 grid gap-6 sm:grid-cols-2">
            <ToolCard
              title="Playground"
              description="Validate manifests against the v1.0 spec. Paste JSON or fetch from a live URL."
              href="/playground"
            />
            <ToolCard
              title="Discovery"
              description="Search the manifest index with natural language. See how vector search + small LLM matching works."
              href="/discover"
            />
            <ToolCard
              title="Trust"
              description="Run the attestation flow: Layer 0 baseline checks, Layer 1 domain verification, Layer 2 capability testing."
              href="/trust"
            />
            <ToolCard
              title="Dashboard"
              description="Track manifest adoption across the ecosystem. Live stats, health monitoring, growth trends."
              href="/dashboard"
            />
          </div>
        </div>
      </section>

      {/* Design Principles */}
      <section className="mx-auto max-w-4xl px-4 py-16">
        <h2 className="text-center text-2xl font-bold text-gray-900">Design Principles</h2>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Principle title="One-page spec" description="If it doesn't fit on one page, it's too complex." />
          <Principle title="Five-minute adoption" description="A solo developer can add OAP in the time it takes to write a README." />
          <Principle title="No gatekeepers" description="No registration, no approval, no fees. Publish and you're in." />
          <Principle title="Machine-first" description="Designed for AI to consume, but any developer can read and write a manifest." />
          <Principle title="Unix philosophy" description="Describe what you accept and what you produce. Let the invoker compose." />
          <Principle title="The web model" description="Standardize the format. Let the ecosystem build the discovery." />
        </div>
      </section>

      {/* Experimental */}
      <section className="px-4 py-16">
        <div className="mx-auto max-w-4xl">
          <h2 className="text-center text-2xl font-bold text-gray-900">Experimental</h2>
          <p className="mx-auto mt-4 max-w-2xl text-center text-gray-600">
            Active research extending OAP into new domains.
          </p>
          <div className="mt-8 grid gap-6 sm:grid-cols-2">
            <ToolCard
              title="Robotics"
              description="Manifests as the cognitive interface for physical capabilities — sensors, actuators, tools, and robotic systems."
              href="/docs/robotics"
            />
            <ToolCard
              title="Procedural Memory"
              description="Using OAP manifests as a learning substrate for small language models — experience-driven skill acquisition without retraining."
              href="/docs/procedural-memory"
            />
          </div>
        </div>
      </section>

      {/* Open Infrastructure */}
      <section className="bg-gray-50 px-4 py-16">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="text-2xl font-bold text-gray-900">Open Infrastructure</h2>
          <p className="mt-4 text-gray-600">
            OAP is released under CC0 1.0 Universal (public domain). No company controls it.
            Anyone can implement it, extend it, or run discovery infrastructure.
          </p>
          <div className="mt-8 flex items-center justify-center gap-4">
            <a
              href="https://github.com/cloudseeder/oap-dev"
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-lg border border-gray-300 px-6 py-3 text-sm font-medium text-gray-700 hover:bg-white"
            >
              View on GitHub
            </a>
            <Link
              href="/docs/quickstart"
              className="rounded-lg bg-primary px-6 py-3 text-sm font-medium text-white hover:bg-primary-600"
            >
              Quick Start
            </Link>
          </div>
        </div>
      </section>
    </div>
  )
}

function Step({ number, title, description }: { number: number; title: string; description: string }) {
  return (
    <div className="text-center">
      <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-primary text-sm font-bold text-white">
        {number}
      </div>
      <h3 className="mt-4 font-semibold text-gray-900">{title}</h3>
      <p className="mt-2 text-sm text-gray-600">{description}</p>
    </div>
  )
}

function ToolCard({ title, description, href }: { title: string; description: string; href: string }) {
  return (
    <Link href={href} className="block rounded-lg border border-gray-200 bg-white p-5 hover:border-primary-200 hover:shadow-sm">
      <h3 className="font-semibold text-gray-900">{title}</h3>
      <p className="mt-2 text-sm text-gray-600">{description}</p>
    </Link>
  )
}

function Principle({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="font-semibold text-gray-900">{title}</h3>
      <p className="mt-1 text-sm text-gray-600">{description}</p>
    </div>
  )
}
