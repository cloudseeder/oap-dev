/** OAP v1.0 manifest validation — ported from reference/oap_discovery/oap_discovery/validate.py */

export interface ValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
}

export function validateManifest(data: unknown): ValidationResult {
  const errors: string[] = []
  const warnings: string[] = []

  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    return { valid: false, errors: ['Manifest must be a JSON object'], warnings: [] }
  }

  const obj = data as Record<string, unknown>

  // Check required fields exist
  for (const key of ['oap', 'name', 'description', 'invoke']) {
    if (!(key in obj)) {
      errors.push(`Missing required field: ${key}`)
    }
  }

  if (errors.length > 0) {
    return { valid: false, errors, warnings }
  }

  // Check oap version
  if (obj.oap !== '1.0') {
    errors.push(`Unsupported oap version: ${obj.oap} (expected "1.0")`)
  }

  // Check name is a non-empty string
  if (typeof obj.name !== 'string' || obj.name.trim().length === 0) {
    errors.push('name must be a non-empty string')
  }

  // Check description is a non-empty string
  if (typeof obj.description !== 'string' || obj.description.trim().length === 0) {
    errors.push('description must be a non-empty string')
  }

  // Check invoke has required subfields
  const invoke = obj.invoke
  if (!invoke || typeof invoke !== 'object' || Array.isArray(invoke)) {
    errors.push('invoke must be an object')
  } else {
    const inv = invoke as Record<string, unknown>
    if (!('method' in inv)) {
      errors.push('invoke.method is required')
    } else if (typeof inv.method !== 'string') {
      errors.push('invoke.method must be a string')
    }
    if (!('url' in inv)) {
      errors.push('invoke.url is required')
    } else if (typeof inv.url !== 'string') {
      errors.push('invoke.url must be a string')
    }
  }

  // Validate optional fields when present
  if ('input' in obj && obj.input !== undefined) {
    validateIOSpec(obj.input, 'input', errors)
  }
  if ('output' in obj && obj.output !== undefined) {
    validateIOSpec(obj.output, 'output', errors)
  }

  if ('tags' in obj && obj.tags !== undefined) {
    if (!Array.isArray(obj.tags)) {
      errors.push('tags must be an array')
    } else if (!obj.tags.every((t: unknown) => typeof t === 'string')) {
      errors.push('tags must be an array of strings')
    }
  }

  if ('examples' in obj && obj.examples !== undefined) {
    if (!Array.isArray(obj.examples)) {
      errors.push('examples must be an array')
    }
  }

  if ('publisher' in obj && obj.publisher !== undefined) {
    if (!obj.publisher || typeof obj.publisher !== 'object' || Array.isArray(obj.publisher)) {
      errors.push('publisher must be an object')
    }
  }

  // Warnings for missing recommended fields
  if (!('input' in obj)) {
    warnings.push('Missing recommended field: input')
  }
  if (!('output' in obj)) {
    warnings.push('Missing recommended field: output')
  }

  // Warn on long descriptions
  if (typeof obj.description === 'string' && obj.description.length > 1000) {
    warnings.push(`Description is ${obj.description.length} chars (recommended max 1000)`)
  }

  return { valid: errors.length === 0, errors, warnings }
}

function validateIOSpec(spec: unknown, field: string, errors: string[]) {
  if (!spec || typeof spec !== 'object' || Array.isArray(spec)) {
    errors.push(`${field} must be an object`)
    return
  }
  const s = spec as Record<string, unknown>
  if (!('format' in s) || typeof s.format !== 'string') {
    errors.push(`${field}.format is required and must be a string`)
  }
  if (!('description' in s) || typeof s.description !== 'string') {
    errors.push(`${field}.description is required and must be a string`)
  }
}
