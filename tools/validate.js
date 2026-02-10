#!/usr/bin/env node

/**
 * OAP Manifest Validator
 * 
 * Validates an oap.json manifest against the OAP spec.
 * Run: node validate.js path/to/oap.json
 *   or: node validate.js https://example.com/.well-known/oap.json
 */

const fs = require('fs');
const path = require('path');

const REQUIRED_FIELDS = {
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
};

const VALID_PRICING_MODELS = ['free', 'freemium', 'subscription', 'one_time', 'usage_based'];

function getNestedValue(obj, path) {
  return path.split('.').reduce((current, key) => current && current[key], obj);
}

function validate(manifest) {
  const errors = [];
  const warnings = [];

  // Check required fields
  for (const [fieldPath, expectedType] of Object.entries(REQUIRED_FIELDS)) {
    const value = getNestedValue(manifest, fieldPath);
    if (value === undefined || value === null) {
      errors.push(`Missing required field: ${fieldPath}`);
    } else if (expectedType === 'array' && !Array.isArray(value)) {
      errors.push(`${fieldPath} must be an array`);
    } else if (expectedType === 'string' && typeof value !== 'string') {
      errors.push(`${fieldPath} must be a string`);
    } else if (expectedType === 'boolean' && typeof value !== 'boolean') {
      errors.push(`${fieldPath} must be a boolean`);
    }
  }

  // Validate lengths
  if (manifest.identity) {
    if (manifest.identity.tagline && manifest.identity.tagline.length > 120) {
      warnings.push(`identity.tagline exceeds 120 chars (${manifest.identity.tagline.length})`);
    }
    if (manifest.identity.description && manifest.identity.description.length > 500) {
      warnings.push(`identity.description exceeds 500 chars (${manifest.identity.description.length})`);
    }
  }
  if (manifest.capabilities && manifest.capabilities.summary && manifest.capabilities.summary.length > 1000) {
    warnings.push(`capabilities.summary exceeds 1000 chars (${manifest.capabilities.summary.length})`);
  }

  // Validate pricing model
  if (manifest.pricing && manifest.pricing.model) {
    if (!VALID_PRICING_MODELS.includes(manifest.pricing.model)) {
      errors.push(`pricing.model must be one of: ${VALID_PRICING_MODELS.join(', ')}`);
    }
  }

  // Validate URL format
  const urlFields = ['identity.url', 'builder.url', 'pricing.pricing_url', 'trust.privacy_url', 'trust.terms_url'];
  for (const fieldPath of urlFields) {
    const value = getNestedValue(manifest, fieldPath);
    if (value && typeof value === 'string') {
      try {
        new URL(value);
      } catch (e) {
        errors.push(`${fieldPath} is not a valid URL: ${value}`);
      }
    }
  }

  // Validate oap_version
  if (manifest.oap_version && manifest.oap_version !== '0.1') {
    warnings.push(`Unknown oap_version: ${manifest.oap_version}. Current version is 0.1`);
  }

  // Quality checks
  if (manifest.capabilities) {
    if (manifest.capabilities.solves && manifest.capabilities.solves.length < 3) {
      warnings.push('Consider adding more "solves" entries (recommend 3-8 for better AI matching)');
    }
    if (manifest.capabilities.ideal_for && manifest.capabilities.ideal_for.length < 2) {
      warnings.push('Consider adding more "ideal_for" entries (recommend 2-5 for better targeting)');
    }
    if (manifest.capabilities.categories && manifest.capabilities.categories.length < 2) {
      warnings.push('Consider adding more categories (recommend 2-5)');
    }
  }

  // Trust completeness
  if (manifest.trust) {
    if (!manifest.trust.privacy_url) {
      warnings.push('No privacy_url provided — agents may deprioritize apps without privacy policies');
    }
    if (!manifest.trust.terms_url) {
      warnings.push('No terms_url provided — consider adding for increased trust');
    }
  }

  // Verification
  if (!manifest.verification || Object.keys(manifest.verification).length === 0) {
    warnings.push('No verification endpoints — agents cannot confirm app is live');
  }

  return { errors, warnings };
}

// === MAIN ===
async function main() {
  const input = process.argv[2];
  
  if (!input) {
    console.log('Usage: node validate.js <path-or-url>');
    console.log('  node validate.js .well-known/oap.json');
    console.log('  node validate.js https://example.com/.well-known/oap.json');
    process.exit(1);
  }

  let manifest;
  let source;

  if (input.startsWith('http')) {
    // Fetch from URL
    try {
      const response = await fetch(input);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      manifest = await response.json();
      source = input;
    } catch (e) {
      console.error(`\n❌ Could not fetch manifest from ${input}: ${e.message}`);
      process.exit(1);
    }
  } else {
    // Read from file
    try {
      const content = fs.readFileSync(input, 'utf-8');
      manifest = JSON.parse(content);
      source = path.resolve(input);
    } catch (e) {
      console.error(`\n❌ Could not read manifest from ${input}: ${e.message}`);
      process.exit(1);
    }
  }

  console.log(`\n── OAP Manifest Validator ──\n`);
  console.log(`Source: ${source}`);
  console.log(`App:    ${manifest.identity?.name || 'unknown'}`);
  console.log(`OAP:    v${manifest.oap_version || 'unknown'}\n`);

  const { errors, warnings } = validate(manifest);

  if (errors.length === 0 && warnings.length === 0) {
    console.log('✅ Manifest is valid with no warnings!\n');
    // Generate DNS record hint
    const domain = manifest.identity?.url ? new URL(manifest.identity.url).hostname : 'yourdomain.com';
    const cats = manifest.capabilities?.categories?.slice(0, 3).join(',') || '';
    console.log(`DNS TXT Record:`);
    console.log(`  _oap.${domain} → v=oap1; cat=${cats}; price=${manifest.pricing?.model || 'unknown'}; manifest=${manifest.identity?.url}/.well-known/oap.json\n`);
    process.exit(0);
  }

  if (errors.length > 0) {
    console.log(`❌ ERRORS (${errors.length}):`);
    errors.forEach(e => console.log(`   • ${e}`));
    console.log('');
  }

  if (warnings.length > 0) {
    console.log(`⚠️  WARNINGS (${warnings.length}):`);
    warnings.forEach(w => console.log(`   • ${w}`));
    console.log('');
  }

  process.exit(errors.length > 0 ? 1 : 0);
}

main();
