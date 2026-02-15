---
description: Run a security audit on staged changes before committing
---

You are performing a security code review on the staged changes in this repository.

## Your Task

1. Use `git diff --staged` to see what files and code are about to be committed
2. Analyze the changes for security vulnerabilities including:
   - SQL injection risks
   - XSS (Cross-Site Scripting) vulnerabilities
   - Authentication/authorization bypasses
   - Sensitive data exposure (API keys, credentials, CRON_SECRET, etc.)
   - OWASP Top 10 vulnerabilities
   - TypeScript type safety issues that could lead to runtime errors
   - Undefined value handling in Firebase/Firestore operations
3. Review any API route code to ensure:
   - Authentication is present where needed (CRON_SECRET for cron routes, etc.)
   - Input validation is performed
   - Error handling with try-catch is present
   - No user input is passed unsanitized to Firestore queries
4. Provide a clear summary of findings:
   - ✅ If no issues found: "Security review passed - safe to commit"
   - ⚠️ If minor issues found: List them with severity and suggested fixes
   - 🚨 If critical issues found: Block the commit and explain why

## Output Format

**Security Review Summary**

Files reviewed: [count]

**Findings:**
[List any security concerns found, or state "No security issues detected"]

**Recommendation:**
[Safe to commit / Fix before committing / Critical - do not commit]
