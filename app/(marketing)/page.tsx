import Link from 'next/link'
import CodeBlock from '@/components/CodeBlock'

export default function LandingPage() {
  return (
    <div>
      {/* Hero */}
      <section className="bg-gradient-to-b from-primary-50 to-white px-4 py-20 text-center">
        <h1 className="mx-auto max-w-3xl text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl">
          The discovery layer for web apps,{' '}
          <span className="text-primary">designed for AI agents</span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-gray-600">
          Open Application Protocol (OAP) is a decentralized discovery and trust layer
          that lets AI agents find, evaluate, and recommend applications on behalf of users.
        </p>
        <div className="mt-8 flex items-center justify-center gap-4">
          <Link
            href="/docs/quickstart"
            className="rounded-lg bg-primary px-6 py-3 text-sm font-medium text-white hover:bg-primary-600"
          >
            Get Started in 5 Minutes
          </Link>
          <Link
            href="/spec"
            className="rounded-lg border border-gray-300 px-6 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Read the Spec
          </Link>
        </div>
      </section>

      {/* Problem Statement */}
      <section className="mx-auto max-w-4xl px-4 py-16">
        <h2 className="text-center text-2xl font-bold text-gray-900">The Discovery Gap</h2>
        <p className="mx-auto mt-4 max-w-2xl text-center text-gray-600">
          AI agents can execute tasks through MCP and communicate through A2A &mdash;
          but they have no standard way to discover which applications exist and whether they can be trusted.
        </p>
        <blockquote className="mx-auto mt-8 max-w-xl border-l-4 border-primary pl-4 text-gray-700 italic">
          &ldquo;MCP connects AI to tools. A2A connects agents to each other. OAP connects
          both to the applications humans actually use.&rdquo;
        </blockquote>
      </section>

      {/* How It Works */}
      <section className="bg-gray-50 px-4 py-16">
        <div className="mx-auto max-w-4xl">
          <h2 className="text-center text-2xl font-bold text-gray-900">How It Works</h2>
          <div className="mt-12 grid gap-8 md:grid-cols-3">
            <Step
              number={1}
              title="Declare"
              description="Host a JSON manifest at /.well-known/oap.json describing your app's identity, capabilities, pricing, and trust signals."
            />
            <Step
              number={2}
              title="Verify"
              description="Add a DNS TXT record at _oap.yourdomain.com to prove domain ownership. Optional but builds trust."
            />
            <Step
              number={3}
              title="Discover"
              description="Register with any OAP registry. AI agents search, evaluate, and recommend your app to users."
            />
          </div>

          <div className="mt-12">
            <CodeBlock
              title="/.well-known/oap.json"
              code={`{
  "oap_version": "0.1",
  "identity": {
    "name": "Your App",
    "tagline": "One-line description",
    "description": "What your app does, for AI comprehension",
    "url": "https://yourapp.com"
  },
  "capabilities": {
    "summary": "Natural language description of what your app does...",
    "categories": ["your-category"],
    "solves": ["problems your app solves"]
  },
  "pricing": { "model": "freemium", "trial": { "available": true } },
  "trust": { ... },
  "integration": { ... },
  "verification": { "health_endpoint": "https://yourapp.com/api/health" }
}`}
            />
          </div>
        </div>
      </section>

      {/* Who It's For */}
      <section className="mx-auto max-w-4xl px-4 py-16">
        <h2 className="text-center text-2xl font-bold text-gray-900">Who It&apos;s For</h2>
        <div className="mt-8 grid gap-6 sm:grid-cols-2">
          <Audience
            title="App Developers"
            description="Make your app discoverable by AI agents with a simple JSON file. 5 minutes to adopt, zero cost to list."
          />
          <Audience
            title="AI Agent Builders"
            description="Query OAP registries to find the right application for any user need. Structured data, not guesswork."
          />
          <Audience
            title="Users"
            description="Get better app recommendations from your AI assistant. Trust signals help agents filter out bad actors."
          />
          <Audience
            title="Registry Operators"
            description="Run your own OAP registry, like running an npm registry. Open protocol, open data, no gatekeepers."
          />
        </div>
      </section>

      {/* Open Infrastructure */}
      <section className="bg-gray-50 px-4 py-16">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="text-2xl font-bold text-gray-900">Open Infrastructure</h2>
          <p className="mt-4 text-gray-600">
            OAP is released under CC0 1.0 Universal (public domain). No company controls it.
            Anyone can implement it, extend it, or run a registry. The protocol is designed to be
            as decentralized as DNS itself.
          </p>
          <div className="mt-8 flex items-center justify-center gap-4">
            <a
              href="https://github.com/OpenApplicationProtocol/oap"
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-lg border border-gray-300 px-6 py-3 text-sm font-medium text-gray-700 hover:bg-white"
            >
              View on GitHub
            </a>
            <a
              href="https://registry.oap.dev"
              className="rounded-lg bg-primary px-6 py-3 text-sm font-medium text-white hover:bg-primary-600"
            >
              Browse the Registry
            </a>
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

function Audience({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5">
      <h3 className="font-semibold text-gray-900">{title}</h3>
      <p className="mt-2 text-sm text-gray-600">{description}</p>
    </div>
  )
}
