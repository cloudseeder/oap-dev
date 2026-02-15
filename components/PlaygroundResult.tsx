import ManifestViewer from '@/components/ManifestViewer'
import type { OAPManifest } from '@/lib/types-v1'
import type { ValidationResult } from '@/lib/manifest-v1'

interface PlaygroundResultProps {
  result: ValidationResult
  manifest: OAPManifest | null
}

export default function PlaygroundResult({ result, manifest }: PlaygroundResultProps) {
  return (
    <div className="space-y-4">
      {/* Status */}
      <div className={`rounded-lg border p-4 ${result.valid ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}`}>
        <div className="flex items-center gap-2">
          <span className={`text-lg ${result.valid ? 'text-green-600' : 'text-red-600'}`}>
            {result.valid ? '\u2713' : '\u2717'}
          </span>
          <span className={`font-medium ${result.valid ? 'text-green-800' : 'text-red-800'}`}>
            {result.valid ? 'Valid OAP v1.0 manifest' : 'Invalid manifest'}
          </span>
        </div>
      </div>

      {/* Errors */}
      {result.errors.length > 0 && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <h3 className="text-sm font-semibold text-red-800">Errors</h3>
          <ul className="mt-2 space-y-1 text-sm text-red-700">
            {result.errors.map((err, i) => (
              <li key={i}>{err}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Warnings */}
      {result.warnings.length > 0 && (
        <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4">
          <h3 className="text-sm font-semibold text-yellow-800">Warnings</h3>
          <ul className="mt-2 space-y-1 text-sm text-yellow-700">
            {result.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Preview */}
      {manifest && (
        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500">Preview</h3>
          <ManifestViewer manifest={manifest} />
        </div>
      )}
    </div>
  )
}
