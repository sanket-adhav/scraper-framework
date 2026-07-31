# ADR 0002 — SecretsProvider contract for `secret://` references

**Date:** 2026-07-17 · **Status:** accepted · **Plan:** 03

## Context

plan2.md §9 rule 3: config carries `secret://` references only; plaintext
credentials fail validation. Something has to turn a reference into the real
value at runtime, and Plan 10 must be able to swap env-vars for a vault
without touching core.

## Decision

Add a `SecretsProvider` contract (`core/contracts/secrets_provider.py`) with a
single `resolve(ref) -> str` method. `EnvSecretsProvider` in
`components/secrets/` handles `secret://env/NAME` from environment variables.
The config loader stores references untouched (the fingerprint never sees
secret values); `resolve_secret_refs()` is applied at component-build time.

## Consequences

- Vault/AWS-SM in Plan 10 is a new component behind the same contract — a
  config change, as promised.
- Secrets never enter the config fingerprint or logs by construction.
