# Sandbox Provider Selection

The application setting `SANDBOX_PROVIDER` is an explicit safety gate for future sandbox runtime adapters.

- Default: `unavailable`.
- Currently supported value: `unavailable` only.
- Any other value fails settings validation at startup. There is no implicit fallback if a deployment requests an unsupported provider.
- This setting does not launch containers or enable sandbox execution. The unavailable controller remains the fail-closed implementation.

Example environment configuration:

```dotenv
SANDBOX_PROVIDER=unavailable
```

A concrete provider may be added only after its deployment target, isolation controls, configuration validation, reconciliation behavior, integration tests, and security review satisfy the [provider readiness checklist](sandbox-provider-readiness.md). Provider activation must be a separate explicit deployment decision with a tested kill switch.
