import CodeBlock from '@/components/CodeBlock'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'API Documentation — OAP Registry',
  description: 'OAP Registry API documentation for developers and AI agents.',
}

export default function ApiDocsPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-bold text-gray-900">Registry API Documentation</h1>
      <p className="mt-2 text-gray-600">
        Base URL: <code className="rounded bg-gray-100 px-1.5 py-0.5 text-sm">https://registry.oap.dev</code>
      </p>

      {/* For AI Agents */}
      <div className="mt-8 rounded-lg border border-primary-200 bg-primary-50 p-6">
        <h2 className="font-semibold text-primary-800">For AI Agents</h2>
        <p className="mt-2 text-sm text-primary-700">
          Use the search endpoint to find applications matching user needs. The response
          includes trust signals (DNS verification, health status, uptime) to help evaluate
          application quality. All responses are JSON.
        </p>
      </div>

      <div className="mt-8 space-y-10">
        <Endpoint
          method="POST"
          path="/api/v1/register"
          description="Register a new app. The app must have a valid OAP manifest at /.well-known/oap.json."
          request={`{
  "url": "https://yourapp.com"
}`}
          response={`{
  "status": "registered",
  "domain": "yourapp.com",
  "manifest_url": "https://yourapp.com/.well-known/oap.json",
  "dns_verified": false,
  "manifest_valid": true,
  "health_ok": true,
  "indexed_at": "2025-01-15T12:00:00.000Z",
  "dns_hint": "Add DNS TXT record: _oap.yourapp.com → v=oap1; ..."
}`}
        />

        <Endpoint
          method="GET"
          path="/api/v1/search?q={query}"
          description="Search for apps by keyword. Returns up to 20 results sorted by relevance."
          response={`{
  "query": "CRM",
  "results": [
    {
      "domain": "xuru.ai",
      "name": "Xuru",
      "tagline": "AI-powered support ticket CRM",
      "trust_signals": {
        "dns_verified": true,
        "health_ok": true
      },
      "pricing": { "model": "subscription", "starting_price": "$5/seat/month" },
      "categories": ["crm", "support-tickets"],
      "match_score": 0.83
    }
  ],
  "total": 1,
  "searched_at": "2025-01-15T12:00:00.000Z"
}`}
        />

        <Endpoint
          method="GET"
          path="/api/v1/categories"
          description="List all categories with app counts."
          response={`{
  "categories": [
    { "category": "crm", "count": 1 },
    { "category": "civic-tech", "count": 1 }
  ],
  "total": 2
}`}
        />

        <Endpoint
          method="GET"
          path="/api/v1/categories/{category}?page=1&limit=20"
          description="Browse apps in a category with pagination."
          response={`{
  "category": "crm",
  "apps": [ ... ],
  "total": 1,
  "page": 1
}`}
        />

        <Endpoint
          method="GET"
          path="/api/v1/apps/{domain}"
          description="Get full app details including the complete manifest and registry metadata."
          response={`{
  "domain": "xuru.ai",
  "manifest": { ... },
  "registry_meta": {
    "registered_at": "2025-01-15T12:00:00.000Z",
    "dns_verified": true,
    "health_ok": true,
    "manifest_hash": "sha256:abc123...",
    "builder_other_apps": [
      { "domain": "provexa.ai", "name": "ProveXa" }
    ]
  }
}`}
        />

        <Endpoint
          method="PUT"
          path="/api/v1/apps/{domain}/refresh"
          description="Force re-fetch the manifest from the source domain. Re-validates and re-verifies."
          response={`{
  "status": "refreshed",
  "domain": "xuru.ai",
  "manifest_hash": "sha256:def456..."
}`}
        />

        <Endpoint
          method="GET"
          path="/api/v1/all?page=1&limit=100"
          description="Paginated dump of all registered apps. Useful for registry mirroring."
          response={`{
  "apps": [
    {
      "domain": "xuru.ai",
      "manifest_url": "https://xuru.ai/.well-known/oap.json",
      "manifest_hash": "sha256:abc123...",
      "last_verified": "2025-01-15T12:00:00.000Z"
    }
  ],
  "total": 3,
  "page": 1
}`}
        />

        <Endpoint
          method="GET"
          path="/api/v1/stats"
          description="Registry statistics."
          response={`{
  "total_apps": 3,
  "categories": 15,
  "verified_healthy": 3,
  "registered_today": 0,
  "registry_version": "0.1"
}`}
        />
      </div>
    </div>
  )
}

function Endpoint({
  method,
  path,
  description,
  request,
  response,
}: {
  method: string
  path: string
  description: string
  request?: string
  response: string
}) {
  const methodColor = method === 'GET'
    ? 'bg-green-100 text-green-800'
    : method === 'POST'
    ? 'bg-blue-100 text-blue-800'
    : 'bg-yellow-100 text-yellow-800'

  return (
    <div>
      <div className="flex items-center gap-3">
        <span className={`rounded px-2 py-0.5 text-xs font-bold ${methodColor}`}>
          {method}
        </span>
        <code className="text-sm font-medium text-gray-900">{path}</code>
      </div>
      <p className="mt-2 text-sm text-gray-600">{description}</p>
      {request && (
        <div className="mt-3">
          <p className="mb-1 text-xs font-medium text-gray-500">Request Body</p>
          <CodeBlock code={request} />
        </div>
      )}
      <div className="mt-3">
        <p className="mb-1 text-xs font-medium text-gray-500">Response</p>
        <CodeBlock code={response} />
      </div>
    </div>
  )
}
