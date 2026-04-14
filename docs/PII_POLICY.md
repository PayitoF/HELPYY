# PII Policy

See CLAUDE.md section "PII SECURITY POLICY" for the full policy.

## Summary

No LLM (local or cloud) may see PII in plaintext. All PII is tokenized
in FastAPI middleware before reaching any agent, and detokenized (with
partial values only) before sending responses to users.

<!-- TODO: document compliance requirements, audit procedures -->
