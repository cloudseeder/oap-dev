// Ported from tools/validate.js and registry/server.js

const REQUIRED_FIELDS: Record<string, string> = {
  'oap_version': 'string',
  'identity.name': 'string',
  'identity.tagline': 'string',
  'identity.description': 'string',
  'identity.url': 'string',
  'builder.name': 'string',
  'capabilities.summary': 'string',
  'capabilities.solves': 'array',
  'capabilities.ideal_for': 'array',
  'capabilities.categories': 'array',
  'capabilities.differentiators': 'array',
  'pricing.model': 'string',
  'pricing.trial.available': 'boolean',
  'trust.data_practices.collects': 'array',
  'trust.data_practices.stores_in': 'string',
  'trust.data_practices.shares_with': 'array',
  'trust.security.authentication': 'array',
  'trust.external_connections': 'array',
}

const VALID_PRICING_MODELS = ['free', 'freemium', 'subscription', 'one_time', 'usage_based']

export function getNestedValue(obj: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>(
    (current, key) => (current && typeof current === 'object') ? (current as Record<string, unknown>)[key] : undefined,
    obj
  )
}

export function validateManifest(manifest: Record<string, unknown>): { errors: string[]; warnings: string[] } {
  const errors: string[] = []
  const warnings: string[] = []

  // Check required fields and types
  for (const [fieldPath, expectedType] of Object.entries(REQUIRED_FIELDS)) {
    const value = getNestedValue(manifest, fieldPath)
    if (value === undefined || value === null) {
      errors.push(`Missing required field: ${fieldPath}`)
    } else if (expectedType === 'array' && !Array.isArray(value)) {
      errors.push(`${fieldPath} must be an array`)
    } else if (expectedType === 'string' && typeof value !== 'string') {
      errors.push(`${fieldPath} must be a string`)
    } else if (expectedType === 'boolean' && typeof value !== 'boolean') {
      errors.push(`${fieldPath} must be a boolean`)
    }
  }

  // Validate lengths
  const identity = manifest.identity as Record<string, unknown> | undefined
  if (identity) {
    const tagline = identity.tagline as string | undefined
    if (tagline && tagline.length > 120) {
      warnings.push(`identity.tagline exceeds 120 chars (${tagline.length})`)
    }
    const description = identity.description as string | undefined
    if (description && description.length > 500) {
      warnings.push(`identity.description exceeds 500 chars (${description.length})`)
    }
  }

  const capabilities = manifest.capabilities as Record<string, unknown> | undefined
  if (capabilities) {
    const summary = capabilities.summary as string | undefined
    if (summary && summary.length > 1000) {
      warnings.push(`capabilities.summary exceeds 1000 chars (${summary.length})`)
    }
  }

  // Validate pricing model enum
  const pricing = manifest.pricing as Record<string, unknown> | undefined
  if (pricing?.model) {
    if (!VALID_PRICING_MODELS.includes(pricing.model as string)) {
      errors.push(`pricing.model must be one of: ${VALID_PRICING_MODELS.join(', ')}`)
    }
  }

  // Validate URL fields
  const urlFields = ['identity.url', 'builder.url', 'pricing.pricing_url', 'trust.privacy_url', 'trust.terms_url']
  for (const fieldPath of urlFields) {
    const value = getNestedValue(manifest, fieldPath)
    if (value && typeof value === 'string') {
      try {
        new URL(value)
      } catch {
        errors.push(`${fieldPath} is not a valid URL: ${value}`)
      }
    }
  }

  // Quality warnings
  if (capabilities) {
    const solves = capabilities.solves as string[] | undefined
    if (Array.isArray(solves) && solves.length < 3) {
      warnings.push('Consider adding more "solves" entries (recommend 3-8)')
    }
    const idealFor = capabilities.ideal_for as string[] | undefined
    if (Array.isArray(idealFor) && idealFor.length < 2) {
      warnings.push('Consider adding more "ideal_for" entries (recommend 2-5)')
    }
    const categories = capabilities.categories as string[] | undefined
    if (Array.isArray(categories) && categories.length < 2) {
      warnings.push('Consider adding more categories (recommend 2-5)')
    }
  }

  // Trust completeness
  const trust = manifest.trust as Record<string, unknown> | undefined
  if (trust) {
    if (!trust.privacy_url) {
      warnings.push('No privacy_url provided')
    }
    if (!trust.terms_url) {
      warnings.push('No terms_url provided')
    }
  }

  // Verification
  const verification = manifest.verification as Record<string, unknown> | undefined
  if (!verification || Object.keys(verification).length === 0) {
    warnings.push('No verification endpoints')
  }

  return { errors, warnings }
}
