import type { OAPManifest } from '@/lib/types'

export default function ManifestViewer({ manifest }: { manifest: OAPManifest }) {
  return (
    <div className="space-y-6">
      {/* Identity */}
      <Section title="Identity">
        <Field label="Name" value={manifest.identity.name} />
        <Field label="Tagline" value={manifest.identity.tagline} />
        <Field label="Description" value={manifest.identity.description} />
        <Field label="URL" value={manifest.identity.url} link />
        {manifest.identity.launched && <Field label="Launched" value={manifest.identity.launched} />}
      </Section>

      {/* Builder */}
      <Section title="Builder">
        <Field label="Name" value={manifest.builder.name} />
        {manifest.builder.url && <Field label="URL" value={manifest.builder.url} link />}
        {manifest.builder.verified_domains && (
          <Field label="Verified Domains" value={manifest.builder.verified_domains.join(', ')} />
        )}
      </Section>

      {/* Capabilities */}
      <Section title="Capabilities">
        <Field label="Summary" value={manifest.capabilities.summary} />
        <ListField label="Solves" items={manifest.capabilities.solves} />
        <ListField label="Ideal For" items={manifest.capabilities.ideal_for} />
        <ListField label="Differentiators" items={manifest.capabilities.differentiators} />
      </Section>

      {/* Pricing */}
      <Section title="Pricing">
        <Field label="Model" value={manifest.pricing.model} />
        {manifest.pricing.starting_price && <Field label="Starting Price" value={manifest.pricing.starting_price} />}
        <Field label="Trial Available" value={manifest.pricing.trial.available ? 'Yes' : 'No'} />
        {manifest.pricing.trial.duration_days !== undefined && (
          <Field label="Trial Duration" value={`${manifest.pricing.trial.duration_days} days`} />
        )}
      </Section>

      {/* Trust */}
      <Section title="Trust & Security">
        <ListField label="Data Collected" items={manifest.trust.data_practices.collects} />
        <Field label="Data Stored In" value={manifest.trust.data_practices.stores_in} />
        <ListField label="Shared With" items={manifest.trust.data_practices.shares_with} />
        {manifest.trust.data_practices.encryption && (
          <Field label="Encryption" value={manifest.trust.data_practices.encryption} />
        )}
        <ListField label="Authentication" items={manifest.trust.security.authentication} />
        {manifest.trust.security.compliance && (
          <ListField label="Compliance" items={manifest.trust.security.compliance} />
        )}
        <ListField label="External Connections" items={manifest.trust.external_connections} />
        {manifest.trust.privacy_url && <Field label="Privacy Policy" value={manifest.trust.privacy_url} link />}
        {manifest.trust.terms_url && <Field label="Terms of Service" value={manifest.trust.terms_url} link />}
      </Section>

      {/* Integration */}
      <Section title="Integration">
        <Field label="API Available" value={manifest.integration.api.available ? 'Yes' : 'No'} />
        {manifest.integration.api.docs_url && <Field label="API Docs" value={manifest.integration.api.docs_url} link />}
        {manifest.integration.mcp_endpoint && <Field label="MCP Endpoint" value={manifest.integration.mcp_endpoint} />}
        {manifest.integration.webhooks !== undefined && (
          <Field label="Webhooks" value={manifest.integration.webhooks ? 'Yes' : 'No'} />
        )}
        {manifest.integration.export_formats && (
          <Field label="Export Formats" value={manifest.integration.export_formats.join(', ')} />
        )}
      </Section>

      {/* Verification */}
      <Section title="Verification">
        {manifest.verification.health_endpoint && (
          <Field label="Health Endpoint" value={manifest.verification.health_endpoint} link />
        )}
        {manifest.verification.status_url && (
          <Field label="Status Page" value={manifest.verification.status_url} link />
        )}
        {manifest.verification.demo_url && (
          <Field label="Demo URL" value={manifest.verification.demo_url} link />
        )}
      </Section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-500">{title}</h3>
      <div className="space-y-2">{children}</div>
    </div>
  )
}

function Field({ label, value, link }: { label: string; value: string; link?: boolean }) {
  return (
    <div className="flex gap-3 text-sm">
      <span className="w-36 shrink-0 text-gray-500">{label}</span>
      {link ? (
        <a href={value} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
          {value}
        </a>
      ) : (
        <span className="text-gray-900">{value}</span>
      )}
    </div>
  )
}

function ListField({ label, items }: { label: string; items: string[] }) {
  return (
    <div className="flex gap-3 text-sm">
      <span className="w-36 shrink-0 text-gray-500">{label}</span>
      <ul className="list-inside list-disc space-y-0.5 text-gray-900">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  )
}
