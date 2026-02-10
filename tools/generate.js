#!/usr/bin/env node

/**
 * OAP Manifest Generator
 * 
 * Interactive CLI tool to generate an Open Application Protocol manifest.
 * Run: npx oap-init  (or node generate.js)
 * 
 * Generates /.well-known/oap.json and DNS TXT record instructions.
 */

const readline = require('readline');
const fs = require('fs');
const path = require('path');

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

function ask(question, defaultVal = '') {
  const suffix = defaultVal ? ` (${defaultVal})` : '';
  return new Promise(resolve => {
    rl.question(`${question}${suffix}: `, answer => {
      resolve(answer.trim() || defaultVal);
    });
  });
}

function askList(question, hint = '') {
  const hintText = hint ? ` ${hint}` : '';
  return new Promise(resolve => {
    rl.question(`${question}${hintText}: `, answer => {
      resolve(answer.split(',').map(s => s.trim()).filter(Boolean));
    });
  });
}

function askYN(question, defaultVal = true) {
  const hint = defaultVal ? 'Y/n' : 'y/N';
  return new Promise(resolve => {
    rl.question(`${question} (${hint}): `, answer => {
      if (!answer.trim()) return resolve(defaultVal);
      resolve(answer.trim().toLowerCase().startsWith('y'));
    });
  });
}

async function main() {
  console.log(`
╔══════════════════════════════════════════════════╗
║     Open Application Protocol (OAP) Generator    ║
║                                                  ║
║  Generate your app manifest in under 5 minutes   ║
║  https://oap.dev                                 ║
╚══════════════════════════════════════════════════╝
`);

  // === IDENTITY ===
  console.log('\n── IDENTITY ──\n');
  const name = await ask('App name');
  const tagline = await ask('One-line tagline (max 120 chars)');
  const description = await ask('What does your app do? (max 500 chars)');
  const url = await ask('App URL (e.g. https://myapp.com)');
  const launched = await ask('Launch date (YYYY-MM-DD, or leave blank)', '');

  // === BUILDER ===
  console.log('\n── BUILDER ──\n');
  const builderName = await ask('Your name or company name');
  const builderUrl = await ask('Your website (optional)', '');
  const builderContact = await ask('Contact email (optional)', '');
  const verifiedDomains = await askList('Other domains you own', '(comma-separated, optional)');

  // === CAPABILITIES ===
  console.log('\n── CAPABILITIES ──\n');
  console.log('This is the most important section. Write for AI agents, not humans.');
  console.log('Be specific about what your app does and who it\'s for.\n');
  
  const summary = await ask('Detailed capability summary (max 1000 chars)\n  What does your app do, how, and for whom?');
  
  console.log('\nList problems your app solves (as a user would describe them).');
  console.log('Example: "support tickets pile up because my team is too small"');
  const solves = await askList('Problems solved', '(comma-separated)');
  
  console.log('\nWho is your ideal user?');
  const idealFor = await askList('Ideal users', '(comma-separated)');
  
  const categories = await askList('Categories/tags', '(comma-separated, e.g. crm, ai, support)');
  
  console.log('\nWhat makes you different from alternatives?');
  const differentiators = await askList('Key differentiators', '(comma-separated)');

  // === PRICING ===
  console.log('\n── PRICING ──\n');
  const pricingModel = await ask('Pricing model (free/freemium/subscription/one_time/usage_based)', 'subscription');
  const startingPrice = await ask('Starting price (e.g. "$5/seat/month")', '');
  const hasTrial = await askYN('Free trial available?', true);
  let trialDays = 0;
  let trialCC = false;
  if (hasTrial) {
    trialDays = parseInt(await ask('Trial duration (days)', '30')) || 30;
    trialCC = await askYN('Requires credit card?', false);
  }
  const pricingUrl = await ask('Pricing page URL (optional)', '');

  // === TRUST ===
  console.log('\n── TRUST & DATA PRACTICES ──\n');
  const collects = await askList('What user data do you collect?', '(comma-separated)');
  const storesIn = await ask('Where is data stored?', 'US-based cloud');
  const sharesWith = await askList('Third parties you share data with', '(comma-separated, or type "none")');
  const encryption = await ask('Encryption practices', 'at rest and in transit');
  const auth = await askList('Authentication methods', '(comma-separated, e.g. email/password, OAuth, SSO)');
  const compliance = await askList('Compliance certifications (optional)', '(comma-separated, e.g. SOC2, GDPR)');
  const externalConnections = await askList('External APIs/services your app connects to', '(comma-separated)');
  const privacyUrl = await ask('Privacy policy URL (optional)', '');
  const termsUrl = await ask('Terms of service URL (optional)', '');

  // === INTEGRATION ===
  console.log('\n── INTEGRATION ──\n');
  const hasAPI = await askYN('Do you have a public API?', false);
  let apiDocs = '';
  let apiAuth = '';
  if (hasAPI) {
    apiDocs = await ask('API docs URL', '');
    apiAuth = await ask('API auth method (e.g. API key, OAuth2)', '');
  }
  const hasWebhooks = await askYN('Do you support webhooks?', false);
  const importFrom = await askList('Services users can import from (optional)', '(comma-separated)');
  const exportFormats = await askList('Export formats (optional)', '(comma-separated, e.g. CSV, JSON, PDF)');

  // === VERIFICATION ===
  console.log('\n── VERIFICATION ──\n');
  const healthEndpoint = await ask('Health check endpoint (optional, e.g. /api/health)', '');
  const statusUrl = await ask('Public status page URL (optional)', '');
  const demoUrl = await ask('Demo or signup URL (optional)', '');

  // === BUILD MANIFEST ===
  const manifest = {
    "$schema": "https://oap.dev/schema/v0.1.json",
    "oap_version": "0.1",
    "identity": {
      "name": name,
      "tagline": tagline,
      "description": description,
      "url": url,
      ...(launched && { "launched": launched })
    },
    "builder": {
      "name": builderName,
      ...(builderUrl && { "url": builderUrl }),
      ...(builderContact && { "contact": builderContact }),
      ...(verifiedDomains.length && { "verified_domains": verifiedDomains })
    },
    "capabilities": {
      "summary": summary,
      "solves": solves,
      "ideal_for": idealFor,
      "categories": categories,
      "differentiators": differentiators
    },
    "pricing": {
      "model": pricingModel,
      ...(startingPrice && { "starting_price": startingPrice }),
      "trial": {
        "available": hasTrial,
        ...(hasTrial && { "duration_days": trialDays }),
        ...(hasTrial && { "requires_credit_card": trialCC })
      },
      ...(pricingUrl && { "pricing_url": pricingUrl })
    },
    "trust": {
      "data_practices": {
        "collects": collects,
        "stores_in": storesIn,
        "shares_with": sharesWith,
        ...(encryption && { "encryption": encryption })
      },
      "security": {
        "authentication": auth,
        ...(compliance.length && { "compliance": compliance })
      },
      "external_connections": externalConnections,
      ...(privacyUrl && { "privacy_url": privacyUrl }),
      ...(termsUrl && { "terms_url": termsUrl })
    },
    "integration": {
      ...(hasAPI || apiDocs ? {
        "api": {
          "available": hasAPI,
          ...(apiDocs && { "docs_url": apiDocs }),
          ...(apiAuth && { "auth_method": apiAuth })
        }
      } : { "api": { "available": false } }),
      ...(hasWebhooks !== undefined && { "webhooks": hasWebhooks }),
      ...(importFrom.length && { "import_from": importFrom }),
      ...(exportFormats.length && { "export_formats": exportFormats })
    },
    "verification": {
      ...(healthEndpoint && { "health_endpoint": healthEndpoint.startsWith('http') ? healthEndpoint : `${url}${healthEndpoint}` }),
      ...(statusUrl && { "status_url": statusUrl }),
      ...(demoUrl && { "demo_url": demoUrl })
    }
  };

  // === OUTPUT ===
  const outputDir = path.join(process.cwd(), '.well-known');
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }
  
  const outputPath = path.join(outputDir, 'oap.json');
  fs.writeFileSync(outputPath, JSON.stringify(manifest, null, 2));

  // Extract domain from URL
  let domain = '';
  try {
    domain = new URL(url).hostname;
  } catch (e) {
    domain = 'yourdomain.com';
  }

  console.log(`
╔══════════════════════════════════════════════════╗
║                  MANIFEST CREATED                ║
╚══════════════════════════════════════════════════╝

  File: ${outputPath}

── NEXT STEPS ──

1. DEPLOY THE MANIFEST
   Copy .well-known/oap.json to your web server so it's
   accessible at: ${url}/.well-known/oap.json

   Make sure your server returns Content-Type: application/json

2. ADD DNS TXT RECORD
   Add this TXT record to your DNS:

   Host:  _oap.${domain}
   Value: v=oap1; cat=${categories.slice(0, 3).join(',')}; price=${pricingModel}; manifest=${url}/.well-known/oap.json

3. VERIFY
   curl ${url}/.well-known/oap.json
   dig TXT _oap.${domain}

4. TELL THE WORLD
   Your app is now discoverable by any OAP-aware AI agent.
   Learn more: https://oap.dev

`);

  rl.close();
}

main().catch(err => {
  console.error('Error:', err);
  rl.close();
  process.exit(1);
});
