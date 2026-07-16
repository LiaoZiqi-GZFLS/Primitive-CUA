# WeChat Desktop Client Workflow

## Summary
UIA-first workflow for WeChat Windows client — search, follow accounts, send messages

## Context
WeChat desktop client uses custom UI with anti-screenshot mechanisms. UIA is the primary interaction
method; visual fallback for elements without programmatic access.

## Guidance
- Confirm logged-in state before starting; detect QR code login screen and alert if logged out
- Search bar at top of left navigation bar; results use tabbed category filters
- **Service Account identification**: Look for "服务号" label text next to result items
- **Navigation fallback**: Arrow keys + Enter when direct click positioning fails
- **Message sending**: Confirm text in input box before Enter; verify message in chat history
- Screenshot restriction: Use UIA element retrieval as primary method
- Search result changes: Use exact name matching via OCR instead of fixed-position clicks
- Multiple instances: Track process IDs to target correct WeChat window
- Idempotent check: Verify follow state before clicking follow button
