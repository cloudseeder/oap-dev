#!/bin/bash

# Pre-commit Security Check Script
# Performs automated security checks on staged changes

set -e

echo "🔒 Running security checks on staged changes..."

# Get list of staged files
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM)

if [ -z "$STAGED_FILES" ]; then
  echo "✅ No staged files to check"
  exit 0
fi

# Initialize counters
ISSUES_FOUND=0
WARNINGS=0

# Color codes
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo ""
echo "📁 Checking ${#STAGED_FILES[@]} staged files..."
echo ""

# Check 1: Scan for potential secrets/credentials
echo "🔍 Checking for exposed secrets..."
if echo "$STAGED_FILES" | grep -E '\.(ts|tsx|js|jsx|json)$' > /dev/null; then
  # Look for actual secret values, not just the words - only check ADDED lines (not removed lines)
  SECRETS=$(git diff --cached --diff-filter=ACM | grep '^+' | grep -E '(apiKey\s*[:=]\s*["\x27]|api_key\s*[:=]\s*["\x27]|secret\s*[:=]\s*["\x27]|password\s*[:=]\s*["\x27]|token\s*[:=]\s*["\x27]|private_key\s*[:=]\s*["\x27]|AWS_ACCESS|FIREBASE_API_KEY|ANTHROPIC_API_KEY|GOOGLE_API_KEY|Bearer\s+[A-Za-z0-9\-_\.]+)' | grep -v "// " | grep -v "process.env" | grep -v "placeholder" | grep -v "your-" | grep -v "example" || true)

  if [ ! -z "$SECRETS" ]; then
    echo -e "${RED}🚨 CRITICAL: Potential secrets detected in staged changes!${NC}"
    echo "$SECRETS"
    echo ""
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
  fi
fi

# Check 2: Scan for SQL injection risks
echo "🔍 Checking for SQL injection risks..."
if echo "$STAGED_FILES" | grep -E '\.(ts|tsx|js|jsx)$' > /dev/null; then
  SQL_RISKS=$(git diff --cached --diff-filter=ACM | grep -E '\$\{.*\}.*SELECT|query.*\+.*WHERE|execute.*\+' || true)

  if [ ! -z "$SQL_RISKS" ]; then
    echo -e "${YELLOW}⚠️  WARNING: Potential SQL injection risk detected${NC}"
    echo "$SQL_RISKS"
    echo ""
    WARNINGS=$((WARNINGS + 1))
  fi
fi

# Check 3: Check for XSS vulnerabilities (dangerouslySetInnerHTML)
echo "🔍 Checking for XSS vulnerabilities..."
if echo "$STAGED_FILES" | grep -E '\.(tsx|jsx)$' > /dev/null; then
  XSS_RISKS=$(git diff --cached --diff-filter=ACM | grep -i "dangerouslySetInnerHTML" || true)

  if [ ! -z "$XSS_RISKS" ]; then
    echo -e "${YELLOW}⚠️  WARNING: Use of dangerouslySetInnerHTML detected${NC}"
    echo "Ensure content is properly sanitized"
    echo ""
    WARNINGS=$((WARNINGS + 1))
  fi
fi

# Check 4: Check for missing authentication in API routes
echo "🔍 Checking API routes for authentication..."
if echo "$STAGED_FILES" | grep -E 'app/api/.*route\.ts$' > /dev/null; then
  for file in $(echo "$STAGED_FILES" | grep -E 'app/api/.*route\.ts$'); do
    if git diff --cached "$file" | grep -E '^\+.*export async function (GET|POST|PUT|DELETE)' > /dev/null; then
      # Check if auth check is present (CRON_SECRET or other auth)
      if ! git diff --cached "$file" | grep -E '^\+.*(CRON_SECRET|authenticate\(|authorization|Authorization)' > /dev/null; then
        echo -e "${YELLOW}⚠️  WARNING: New API route handler in $file may be missing authentication${NC}"
        echo "Verify that authentication is properly implemented"
        echo ""
        WARNINGS=$((WARNINGS + 1))
      fi
    fi
  done
fi

# Check 5: Check for console.log in production code
echo "🔍 Checking for debug statements..."
if echo "$STAGED_FILES" | grep -E '\.(ts|tsx|js|jsx)$' > /dev/null; then
  DEBUG_LOGS=$(git diff --cached --diff-filter=ACM | grep -E '^\+.*console\.(log|debug|info)' || true)

  if [ ! -z "$DEBUG_LOGS" ]; then
    echo -e "${YELLOW}⚠️  INFO: console.log statements detected${NC}"
    echo "Consider removing debug statements before production"
    echo ""
  fi
fi

# Check 6: Check for missing error handling
echo "🔍 Checking for error handling..."
if echo "$STAGED_FILES" | grep -E 'app/api/.*route\.ts$' > /dev/null; then
  for file in $(echo "$STAGED_FILES" | grep -E 'app/api/.*route\.ts$'); do
    if git diff --cached "$file" | grep -E '^\+.*export async function' > /dev/null; then
      # Check if try-catch is present
      if ! git diff --cached "$file" | grep -E '^\+.*(try|catch)' > /dev/null; then
        echo -e "${YELLOW}⚠️  WARNING: API route in $file may be missing error handling${NC}"
        echo "Ensure proper try-catch blocks are present"
        echo ""
        WARNINGS=$((WARNINGS + 1))
      fi
    fi
  done
fi

# Check 7: Check for .env file changes
echo "🔍 Checking for environment variable files..."
if echo "$STAGED_FILES" | grep -E '\.env' > /dev/null; then
  echo -e "${RED}🚨 CRITICAL: .env file is staged!${NC}"
  echo "Environment files should never be committed"
  echo ""
  ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Security Check Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $ISSUES_FOUND -gt 0 ]; then
  echo -e "${RED}🚨 CRITICAL ISSUES FOUND: $ISSUES_FOUND${NC}"
  echo ""
  echo "❌ Commit blocked due to security issues"
  echo ""
  echo "Please fix the critical issues above before committing."
  echo ""
  exit 1
fi

if [ $WARNINGS -gt 0 ]; then
  echo -e "${YELLOW}⚠️  Warnings: $WARNINGS${NC}"
  echo ""
  echo "⚠️  Security warnings detected"
  echo ""
  echo "Review the warnings above. If they are false positives or"
  echo "have been addressed, you can proceed with the commit."
  echo ""
fi

if [ $ISSUES_FOUND -eq 0 ] && [ $WARNINGS -eq 0 ]; then
  echo -e "${GREEN}✅ No security issues detected${NC}"
  echo ""
fi

exit 0
