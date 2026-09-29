# BYOK provider fallback

NEXUS can continue a BYOK request with another configured provider when the selected provider returns a transient HTTP failure.

## Fallback order

1. The provider selected by the request is attempted first when it is configured.
2. The user's preferred provider is tried next when it is different from the requested provider.
3. Any remaining configured providers are tried in their configured order.
4. Non-transient provider errors are returned immediately instead of silently switching providers.

Transient HTTP responses currently include **408, 429, 500, 502, 503, and 504**.

This keeps an explicit model choice predictable while still allowing NEXUS to recover from temporary provider outages or rate limits.

## Safety

BYOK credentials are never included in fallback errors or this documentation. Test fixtures should use clearly fake credential values and must never contain real API keys.
