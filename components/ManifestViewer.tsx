import type { OAPManifest } from '@/lib/types-v1'

export default function ManifestViewer({ manifest }: { manifest: OAPManifest }) {
  return (
    <div className="space-y-5">
      {/* Core */}
      <Section title="Core">
        <Field label="OAP Version" value={manifest.oap} />
        <Field label="Name" value={manifest.name} />
        <Field label="Description" value={manifest.description} />
      </Section>

      {/* Invoke */}
      <Section title="Invoke">
        <Field label="Method" value={manifest.invoke.method} />
        <Field label="URL" value={manifest.invoke.url} link={manifest.invoke.method !== 'stdio'} />
        {manifest.invoke.auth && <Field label="Auth" value={manifest.invoke.auth} />}
        {manifest.invoke.auth_url && <Field label="Auth URL" value={manifest.invoke.auth_url} link />}
        {manifest.invoke.auth_in && <Field label="Auth In" value={manifest.invoke.auth_in} />}
        {manifest.invoke.auth_name && <Field label="Auth Name" value={manifest.invoke.auth_name} />}
        {manifest.invoke.streaming !== undefined && (
          <Field label="Streaming" value={manifest.invoke.streaming ? 'Yes' : 'No'} />
        )}
        {manifest.invoke.headers && (
          <Field label="Headers" value={Object.entries(manifest.invoke.headers).map(([k, v]) => `${k}: ${v}`).join(', ')} />
        )}
      </Section>

      {/* Input/Output */}
      {manifest.input && (
        <Section title="Input">
          <Field label="Format" value={manifest.input.format} />
          <Field label="Description" value={manifest.input.description} />
          {manifest.input.schema && <Field label="Schema" value={manifest.input.schema} link />}
        </Section>
      )}
      {manifest.output && (
        <Section title="Output">
          <Field label="Format" value={manifest.output.format} />
          <Field label="Description" value={manifest.output.description} />
          {manifest.output.schema && <Field label="Schema" value={manifest.output.schema} link />}
        </Section>
      )}

      {/* Publisher */}
      {manifest.publisher && (
        <Section title="Publisher">
          {manifest.publisher.name && <Field label="Name" value={manifest.publisher.name} />}
          {manifest.publisher.contact && <Field label="Contact" value={manifest.publisher.contact} />}
          {manifest.publisher.url && <Field label="URL" value={manifest.publisher.url} link />}
        </Section>
      )}

      {/* Examples */}
      {manifest.examples && manifest.examples.length > 0 && (
        <Section title="Examples">
          {manifest.examples.map((ex, i) => (
            <div key={i} className="rounded border border-gray-200 p-3 text-sm">
              {ex.description && <p className="mb-1 text-gray-600">{ex.description}</p>}
              {ex.input && (
                <div className="mt-1">
                  <span className="text-xs font-medium text-gray-500">Input:</span>
                  <pre className="mt-0.5 overflow-x-auto rounded bg-gray-50 p-2 text-xs">{typeof ex.input === 'string' ? ex.input : JSON.stringify(ex.input, null, 2)}</pre>
                </div>
              )}
              {ex.output && (
                <div className="mt-1">
                  <span className="text-xs font-medium text-gray-500">Output:</span>
                  <pre className="mt-0.5 overflow-x-auto rounded bg-gray-50 p-2 text-xs">{typeof ex.output === 'string' ? ex.output : JSON.stringify(ex.output, null, 2)}</pre>
                </div>
              )}
            </div>
          ))}
        </Section>
      )}

      {/* Metadata */}
      {(manifest.tags || manifest.health || manifest.docs || manifest.version || manifest.updated || manifest.url) && (
        <Section title="Metadata">
          {manifest.url && <Field label="URL" value={manifest.url} link />}
          {manifest.version && <Field label="Version" value={manifest.version} />}
          {manifest.updated && <Field label="Updated" value={manifest.updated} />}
          {manifest.health && <Field label="Health" value={manifest.health} link />}
          {manifest.docs && <Field label="Docs" value={manifest.docs} link />}
          {manifest.tags && <Field label="Tags" value={manifest.tags.join(', ')} />}
        </Section>
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-gray-500">{title}</h3>
      <div className="space-y-1.5">{children}</div>
    </div>
  )
}

function Field({ label, value, link }: { label: string; value: string; link?: boolean }) {
  return (
    <div className="flex gap-3 text-sm">
      <span className="w-28 shrink-0 text-gray-500">{label}</span>
      {link ? (
        <a href={value} target="_blank" rel="noopener noreferrer" className="truncate text-primary hover:underline">
          {value}
        </a>
      ) : (
        <span className="text-gray-900">{value}</span>
      )}
    </div>
  )
}
