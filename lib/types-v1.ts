/** OAP v1.0 TypeScript types — ported from reference/oap_discovery/oap_discovery/models.py */

export interface InvokeSpec {
  method: string
  url: string
  auth?: string
  auth_url?: string
  auth_in?: string
  auth_name?: string
  headers?: Record<string, string>
  streaming?: boolean
}

export interface IOSpec {
  format: string
  description: string
  schema?: string
}

export interface Example {
  input?: string | Record<string, unknown>
  output?: string | Record<string, unknown>
  description?: string
}

export interface Publisher {
  name?: string
  contact?: string
  url?: string
}

export interface OAPManifest {
  oap: string
  name: string
  description: string
  invoke: InvokeSpec

  input?: IOSpec
  output?: IOSpec

  url?: string
  publisher?: Publisher
  examples?: Example[]
  tags?: string[]
  health?: string
  docs?: string
  version?: string
  updated?: string
}
