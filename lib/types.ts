// === Manifest Types (derived from docs/SPEC.md) ===

export interface OAPIdentity {
  name: string
  tagline: string
  description: string
  url: string
  logo?: string
  version?: string
  launched?: string
}

export interface OAPBuilder {
  name: string
  url?: string
  contact?: string
  verified_domains?: string[]
}

export interface OAPCapabilities {
  summary: string
  solves: string[]
  ideal_for: string[]
  categories: string[]
  differentiators: string[]
}

export interface OAPTrial {
  available: boolean
  duration_days?: number
  requires_credit_card?: boolean
}

export interface OAPPricing {
  model: PricingModel
  starting_price?: string
  trial: OAPTrial
  pricing_url?: string
}

export interface OAPDataPractices {
  collects: string[]
  stores_in: string
  shares_with: string[]
  retention?: string
  encryption?: string
}

export interface OAPSecurity {
  authentication: string[]
  compliance?: string[]
  audit_log?: boolean
  multi_tenant_isolation?: boolean
}

export interface OAPTrust {
  data_practices: OAPDataPractices
  security: OAPSecurity
  external_connections: string[]
  privacy_url?: string
  terms_url?: string
}

export interface OAPApi {
  available: boolean
  docs_url?: string
  auth_method?: string
}

export interface OAPIntegration {
  mcp_endpoint?: string
  api: OAPApi
  webhooks?: boolean
  import_from?: string[]
  export_formats?: string[]
}

export interface OAPVerification {
  status_url?: string
  health_endpoint?: string
  demo_url?: string
}

export interface OAPManifest {
  $schema?: string
  oap_version: string
  identity: OAPIdentity
  builder: OAPBuilder
  capabilities: OAPCapabilities
  pricing: OAPPricing
  trust: OAPTrust
  integration: OAPIntegration
  verification: OAPVerification
}

// === Firestore Document Types ===

export interface AppDocument {
  domain: string
  manifest_url: string
  manifest_json: string // JSON stringified OAPManifest
  manifest_hash: string

  // Cached identity
  name: string
  tagline: string
  description: string
  app_url: string

  // Cached capabilities
  summary: string
  solves: string[]
  ideal_for: string[]
  categories: string[]
  differentiators: string[]

  // Cached pricing
  pricing_model: PricingModel
  starting_price: string | null

  // Cached builder
  builder_name: string
  builder_verified_domains: string[]

  // Verification state
  dns_verified: boolean
  health_ok: boolean
  manifest_valid: boolean

  // Tracking
  registered_at: string
  last_verified: string | null
  last_fetched: string | null
  uptime_checks_passed: number
  uptime_checks_total: number

  // Status
  flagged: boolean
  flag_reason: string | null
  delisted: boolean
}

export interface CategoryDocument {
  category: string
  count: number
  domains: string[]
}

export interface StatsDocument {
  total_apps: number
  total_categories: number
  verified_healthy: number
  registered_today: number
  last_updated: string
}

export interface AppResult {
  domain: string
  name: string
  tagline: string
  manifest_url: string
  trust_signals: {
    dns_verified: boolean
    health_ok: boolean
    last_checked: string | null
    uptime_30d?: number
  }
  pricing: {
    model: string
    starting_price?: string
  }
  categories: string[]
  match_score?: number
}

export type PricingModel = 'free' | 'freemium' | 'subscription' | 'one_time' | 'usage_based'
