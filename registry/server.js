/**
 * OAP Registry — Reference Implementation
 * 
 * An open, npm-style registry for the Open Application Protocol.
 * Anyone can register. Anyone can query. Anyone can run their own.
 * 
 * Run: npm install && npm start
 */

const express = require('express');
const Database = require('better-sqlite3');
const { resolve } = require('dns').promises;
const path = require('path');
const crypto = require('crypto');

const app = express();
app.use(express.json());

// === DATABASE SETUP ===

const DB_PATH = process.env.OAP_DB_PATH || path.join(__dirname, 'oap-registry.db');
const db = new Database(DB_PATH);

db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

db.exec(`
  CREATE TABLE IF NOT EXISTS apps (
    domain TEXT PRIMARY KEY,
    manifest_url TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    
    -- Cached identity fields for fast search
    name TEXT NOT NULL,
    tagline TEXT,
    description TEXT,
    app_url TEXT,
    
    -- Cached capability fields
    summary TEXT,
    solves TEXT,           -- JSON array
    ideal_for TEXT,        -- JSON array
    categories TEXT,       -- JSON array, also stored normalized in app_categories
    differentiators TEXT,  -- JSON array
    
    -- Cached pricing
    pricing_model TEXT,
    starting_price TEXT,
    
    -- Cached builder
    builder_name TEXT,
    builder_verified_domains TEXT,  -- JSON array
    
    -- Verification state
    dns_verified INTEGER DEFAULT 0,
    health_ok INTEGER DEFAULT 0,
    manifest_valid INTEGER DEFAULT 1,
    
    -- Tracking
    registered_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_verified TEXT,
    last_fetched TEXT,
    uptime_checks_passed INTEGER DEFAULT 0,
    uptime_checks_total INTEGER DEFAULT 0,
    
    -- Status
    flagged INTEGER DEFAULT 0,
    flag_reason TEXT,
    delisted INTEGER DEFAULT 0
  );

  CREATE TABLE IF NOT EXISTS app_categories (
    domain TEXT NOT NULL,
    category TEXT NOT NULL,
    PRIMARY KEY (domain, category),
    FOREIGN KEY (domain) REFERENCES apps(domain) ON DELETE CASCADE
  );

  CREATE INDEX IF NOT EXISTS idx_categories ON app_categories(category);
  CREATE INDEX IF NOT EXISTS idx_apps_name ON apps(name);
  CREATE INDEX IF NOT EXISTS idx_apps_pricing ON apps(pricing_model);
  CREATE INDEX IF NOT EXISTS idx_apps_delisted ON apps(delisted);
`);

// === HELPERS ===

function hashManifest(json) {
  return 'sha256:' + crypto.createHash('sha256').update(JSON.stringify(json)).digest('hex').slice(0, 16);
}

async function fetchManifest(url) {
  const manifestUrl = url.replace(/\/$/, '') + '/.well-known/oap.json';
  const response = await fetch(manifestUrl, { 
    signal: AbortSignal.timeout(10000),
    headers: { 'User-Agent': 'OAP-Registry/0.1' }
  });
  if (!response.ok) throw new Error(`HTTP ${response.status} from ${manifestUrl}`);
  const json = await response.json();
  return { json, manifestUrl };
}

async function verifyDNS(domain) {
  try {
    const records = await resolve(`_oap.${domain}`, 'TXT');
    const flat = records.map(r => r.join('')).join(' ');
    return flat.includes('v=oap1');
  } catch (e) {
    return false;
  }
}

async function checkHealth(manifest) {
  const endpoint = manifest.verification?.health_endpoint;
  if (!endpoint) return null;
  try {
    const response = await fetch(endpoint, { 
      signal: AbortSignal.timeout(5000),
      headers: { 'User-Agent': 'OAP-Registry/0.1' }
    });
    return response.ok;
  } catch (e) {
    return false;
  }
}

function validateManifest(manifest) {
  const errors = [];
  const required = [
    ['identity.name', manifest?.identity?.name],
    ['identity.tagline', manifest?.identity?.tagline],
    ['identity.description', manifest?.identity?.description],
    ['identity.url', manifest?.identity?.url],
    ['builder.name', manifest?.builder?.name],
    ['capabilities.summary', manifest?.capabilities?.summary],
    ['capabilities.solves', manifest?.capabilities?.solves],
    ['capabilities.categories', manifest?.capabilities?.categories],
    ['pricing.model', manifest?.pricing?.model],
    ['trust.data_practices.collects', manifest?.trust?.data_practices?.collects],
    ['trust.data_practices.stores_in', manifest?.trust?.data_practices?.stores_in],
    ['trust.data_practices.shares_with', manifest?.trust?.data_practices?.shares_with],
    ['trust.external_connections', manifest?.trust?.external_connections],
  ];
  for (const [field, value] of required) {
    if (value === undefined || value === null || value === '') {
      errors.push(`Missing required field: ${field}`);
    }
  }
  return errors;
}

function extractDomain(url) {
  try {
    return new URL(url).hostname;
  } catch (e) {
    return null;
  }
}

function searchApps(query) {
  // Simple keyword matching for the reference implementation.
  // Production would use vector embeddings for semantic search.
  const keywords = query.toLowerCase().split(/\s+/).filter(w => w.length > 2);
  
  const allApps = db.prepare(`
    SELECT * FROM apps WHERE delisted = 0
  `).all();
  
  const scored = allApps.map(app => {
    const searchText = [
      app.name, app.tagline, app.description, app.summary,
      app.solves, app.ideal_for, app.categories, app.differentiators,
      app.pricing_model, app.starting_price
    ].filter(Boolean).join(' ').toLowerCase();
    
    let score = 0;
    const matchedKeywords = [];
    
    for (const keyword of keywords) {
      if (searchText.includes(keyword)) {
        score += 1;
        matchedKeywords.push(keyword);
      }
    }
    
    // Bonus for name/tagline matches
    const nameTagline = `${app.name} ${app.tagline}`.toLowerCase();
    for (const keyword of keywords) {
      if (nameTagline.includes(keyword)) score += 0.5;
    }
    
    // Normalize
    const normalizedScore = keywords.length > 0 ? score / (keywords.length * 1.5) : 0;
    
    return { app, score: Math.min(normalizedScore, 1.0), matchedKeywords };
  });
  
  return scored
    .filter(s => s.score > 0.1)
    .sort((a, b) => b.score - a.score)
    .slice(0, 20);
}

function formatAppResult(app, score = null, matchReasons = []) {
  const uptime = app.uptime_checks_total > 0
    ? ((app.uptime_checks_passed / app.uptime_checks_total) * 100).toFixed(1)
    : null;
  
  const result = {
    domain: app.domain,
    name: app.name,
    tagline: app.tagline,
    manifest_url: app.manifest_url,
    trust_signals: {
      dns_verified: !!app.dns_verified,
      health_ok: !!app.health_ok,
      last_checked: app.last_verified,
      ...(uptime && { uptime_30d: parseFloat(uptime) })
    },
    pricing: {
      model: app.pricing_model,
      ...(app.starting_price && { starting_price: app.starting_price })
    },
    categories: JSON.parse(app.categories || '[]')
  };
  
  if (score !== null) {
    result.match_score = parseFloat(score.toFixed(2));
  }
  
  return result;
}

// === API ROUTES ===

// POST /api/v1/register — Register an app
app.post('/api/v1/register', async (req, res) => {
  try {
    const { url } = req.body;
    if (!url) return res.status(400).json({ status: 'error', errors: ['url is required'] });
    
    const domain = extractDomain(url);
    if (!domain) return res.status(400).json({ status: 'error', errors: ['Invalid URL'] });
    
    // Check if already registered
    const existing = db.prepare('SELECT domain FROM apps WHERE domain = ?').get(domain);
    if (existing) {
      return res.status(409).json({ 
        status: 'error', 
        errors: [`${domain} is already registered. Use PUT /api/v1/apps/${domain}/refresh to update.`] 
      });
    }
    
    // Fetch manifest
    let manifest, manifestUrl;
    try {
      ({ json: manifest, manifestUrl } = await fetchManifest(url));
    } catch (e) {
      return res.status(400).json({ 
        status: 'error', 
        errors: [`Could not fetch manifest from ${url}/.well-known/oap.json: ${e.message}`] 
      });
    }
    
    // Validate manifest
    const validationErrors = validateManifest(manifest);
    if (validationErrors.length > 0) {
      return res.status(400).json({ status: 'error', errors: validationErrors });
    }
    
    // Verify DNS (non-blocking — register even if DNS not set up yet)
    const dnsVerified = await verifyDNS(domain);
    
    // Check health endpoint
    const healthOk = await checkHealth(manifest);
    
    // Index the app
    const manifestHash = hashManifest(manifest);
    const now = new Date().toISOString();
    const categories = manifest.capabilities?.categories || [];
    
    db.prepare(`
      INSERT INTO apps (
        domain, manifest_url, manifest_json, manifest_hash,
        name, tagline, description, app_url,
        summary, solves, ideal_for, categories, differentiators,
        pricing_model, starting_price,
        builder_name, builder_verified_domains,
        dns_verified, health_ok, manifest_valid,
        last_verified, last_fetched
      ) VALUES (
        ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?, ?, ?,
        ?, ?,
        ?, ?,
        ?, ?, 1,
        ?, ?
      )
    `).run(
      domain, manifestUrl, JSON.stringify(manifest), manifestHash,
      manifest.identity.name, manifest.identity.tagline, manifest.identity.description, manifest.identity.url,
      manifest.capabilities?.summary, JSON.stringify(manifest.capabilities?.solves || []),
      JSON.stringify(manifest.capabilities?.ideal_for || []),
      JSON.stringify(categories),
      JSON.stringify(manifest.capabilities?.differentiators || []),
      manifest.pricing?.model, manifest.pricing?.starting_price,
      manifest.builder?.name, JSON.stringify(manifest.builder?.verified_domains || []),
      dnsVerified ? 1 : 0, healthOk === null ? 1 : (healthOk ? 1 : 0),
      now, now
    );
    
    // Index categories
    const insertCat = db.prepare('INSERT OR IGNORE INTO app_categories (domain, category) VALUES (?, ?)');
    for (const cat of categories) {
      insertCat.run(domain, cat.toLowerCase());
    }
    
    res.status(201).json({
      status: 'registered',
      domain,
      manifest_url: manifestUrl,
      dns_verified: dnsVerified,
      manifest_valid: true,
      health_ok: healthOk !== false,
      indexed_at: now,
      ...(! dnsVerified && { 
        dns_hint: `Add DNS TXT record: _oap.${domain} → v=oap1; cat=${categories.slice(0,3).join(',')}; manifest=${manifestUrl}` 
      })
    });
    
  } catch (e) {
    console.error('Registration error:', e);
    res.status(500).json({ status: 'error', errors: ['Internal server error'] });
  }
});

// GET /api/v1/search — Semantic search for AI agents
app.get('/api/v1/search', (req, res) => {
  const { q } = req.query;
  if (!q) return res.status(400).json({ status: 'error', errors: ['q parameter required'] });
  
  const results = searchApps(q);
  
  res.json({
    query: q,
    results: results.map(r => formatAppResult(r.app, r.score)),
    total: results.length,
    registry: process.env.OAP_REGISTRY_HOST || 'registry.oap.dev',
    searched_at: new Date().toISOString()
  });
});

// GET /api/v1/categories — List all categories
app.get('/api/v1/categories', (req, res) => {
  const cats = db.prepare(`
    SELECT category, COUNT(*) as count 
    FROM app_categories ac
    JOIN apps a ON ac.domain = a.domain AND a.delisted = 0
    GROUP BY category 
    ORDER BY count DESC
  `).all();
  
  res.json({ categories: cats, total: cats.length });
});

// GET /api/v1/categories/:category — Browse a category
app.get('/api/v1/categories/:category', (req, res) => {
  const { category } = req.params;
  const page = parseInt(req.query.page) || 1;
  const limit = Math.min(parseInt(req.query.limit) || 20, 100);
  const offset = (page - 1) * limit;
  
  const apps = db.prepare(`
    SELECT a.* FROM apps a
    JOIN app_categories ac ON a.domain = ac.domain
    WHERE ac.category = ? AND a.delisted = 0
    ORDER BY a.registered_at DESC
    LIMIT ? OFFSET ?
  `).all(category.toLowerCase(), limit, offset);
  
  const total = db.prepare(`
    SELECT COUNT(*) as count FROM app_categories ac
    JOIN apps a ON ac.domain = a.domain AND a.delisted = 0
    WHERE ac.category = ?
  `).get(category.toLowerCase());
  
  res.json({
    category,
    apps: apps.map(a => formatAppResult(a)),
    total: total.count,
    page
  });
});

// GET /api/v1/apps/:domain — Get app details
app.get('/api/v1/apps/:domain', (req, res) => {
  const app = db.prepare('SELECT * FROM apps WHERE domain = ? AND delisted = 0').get(req.params.domain);
  if (!app) return res.status(404).json({ status: 'error', errors: ['App not found'] });
  
  const uptime = app.uptime_checks_total > 0
    ? ((app.uptime_checks_passed / app.uptime_checks_total) * 100).toFixed(1)
    : null;
  
  // Find other apps by same builder
  const builderDomains = JSON.parse(app.builder_verified_domains || '[]');
  const otherApps = builderDomains.length > 0
    ? db.prepare(`SELECT domain, name FROM apps WHERE domain IN (${builderDomains.map(() => '?').join(',')}) AND domain != ? AND delisted = 0`)
        .all(...builderDomains, app.domain)
    : [];
  
  res.json({
    domain: app.domain,
    manifest: JSON.parse(app.manifest_json),
    registry_meta: {
      registered_at: app.registered_at,
      last_verified: app.last_verified,
      dns_verified: !!app.dns_verified,
      health_ok: !!app.health_ok,
      manifest_hash: app.manifest_hash,
      ...(uptime && { uptime_30d: parseFloat(uptime) }),
      builder_other_apps: otherApps.map(a => ({ domain: a.domain, name: a.name }))
    }
  });
});

// PUT /api/v1/apps/:domain/refresh — Force re-fetch manifest
app.put('/api/v1/apps/:domain/refresh', async (req, res) => {
  const existing = db.prepare('SELECT * FROM apps WHERE domain = ?').get(req.params.domain);
  if (!existing) return res.status(404).json({ status: 'error', errors: ['App not found'] });
  
  try {
    const { json: manifest, manifestUrl } = await fetchManifest(existing.app_url);
    const validationErrors = validateManifest(manifest);
    if (validationErrors.length > 0) {
      return res.status(400).json({ status: 'error', errors: validationErrors });
    }
    
    const dnsVerified = await verifyDNS(existing.domain);
    const healthOk = await checkHealth(manifest);
    const manifestHash = hashManifest(manifest);
    const now = new Date().toISOString();
    const categories = manifest.capabilities?.categories || [];
    
    db.prepare(`
      UPDATE apps SET
        manifest_json = ?, manifest_hash = ?,
        name = ?, tagline = ?, description = ?, app_url = ?,
        summary = ?, solves = ?, ideal_for = ?, categories = ?, differentiators = ?,
        pricing_model = ?, starting_price = ?,
        builder_name = ?, builder_verified_domains = ?,
        dns_verified = ?, health_ok = ?, manifest_valid = 1,
        last_verified = ?, last_fetched = ?
      WHERE domain = ?
    `).run(
      JSON.stringify(manifest), manifestHash,
      manifest.identity.name, manifest.identity.tagline, manifest.identity.description, manifest.identity.url,
      manifest.capabilities?.summary, JSON.stringify(manifest.capabilities?.solves || []),
      JSON.stringify(manifest.capabilities?.ideal_for || []),
      JSON.stringify(categories),
      JSON.stringify(manifest.capabilities?.differentiators || []),
      manifest.pricing?.model, manifest.pricing?.starting_price,
      manifest.builder?.name, JSON.stringify(manifest.builder?.verified_domains || []),
      dnsVerified ? 1 : 0, healthOk === null ? 1 : (healthOk ? 1 : 0),
      now, now,
      existing.domain
    );
    
    // Rebuild categories
    db.prepare('DELETE FROM app_categories WHERE domain = ?').run(existing.domain);
    const insertCat = db.prepare('INSERT OR IGNORE INTO app_categories (domain, category) VALUES (?, ?)');
    for (const cat of categories) {
      insertCat.run(existing.domain, cat.toLowerCase());
    }
    
    res.json({ status: 'refreshed', domain: existing.domain, manifest_hash: manifestHash });
  } catch (e) {
    res.status(500).json({ status: 'error', errors: [e.message] });
  }
});

// GET /api/v1/all — Full registry dump for mirrors
app.get('/api/v1/all', (req, res) => {
  const page = parseInt(req.query.page) || 1;
  const limit = Math.min(parseInt(req.query.limit) || 100, 1000);
  const offset = (page - 1) * limit;
  
  const apps = db.prepare(`
    SELECT domain, manifest_url, manifest_hash, last_verified
    FROM apps WHERE delisted = 0
    ORDER BY registered_at ASC
    LIMIT ? OFFSET ?
  `).all(limit, offset);
  
  const total = db.prepare('SELECT COUNT(*) as count FROM apps WHERE delisted = 0').get();
  
  res.json({ apps, total: total.count, page });
});

// GET /api/v1/stats — Registry statistics
app.get('/api/v1/stats', (req, res) => {
  const total = db.prepare('SELECT COUNT(*) as count FROM apps WHERE delisted = 0').get();
  const categories = db.prepare('SELECT COUNT(DISTINCT category) as count FROM app_categories').get();
  const healthy = db.prepare('SELECT COUNT(*) as count FROM apps WHERE health_ok = 1 AND delisted = 0').get();
  const today = db.prepare(`SELECT COUNT(*) as count FROM apps WHERE registered_at >= date('now') AND delisted = 0`).get();
  
  res.json({
    total_apps: total.count,
    categories: categories.count,
    verified_healthy: healthy.count,
    registered_today: today.count,
    registry_version: '0.1'
  });
});

// GET / — Info page
app.get('/', (req, res) => {
  res.json({
    name: 'OAP Registry',
    version: '0.1',
    spec: 'https://oap.dev/spec',
    docs: 'https://oap.dev/registry',
    endpoints: {
      register: 'POST /api/v1/register',
      search: 'GET /api/v1/search?q=...',
      categories: 'GET /api/v1/categories',
      app_details: 'GET /api/v1/apps/:domain',
      refresh: 'PUT /api/v1/apps/:domain/refresh',
      all: 'GET /api/v1/all',
      stats: 'GET /api/v1/stats'
    }
  });
});

// === START ===

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`
╔══════════════════════════════════════════════════╗
║           OAP Registry v0.1 Running              ║
║                                                  ║
║  API:  http://localhost:${PORT}/api/v1              ║
║  Spec: https://oap.dev/spec                      ║
║                                                  ║
║  Open. Decentralized. No gatekeepers.            ║
╚══════════════════════════════════════════════════╝
  `);
});

module.exports = app;
