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

### Service Account Chat Interface (CRITICAL)

After following a service account (服务号) and entering its chat, the screen layout is NOT the normal WeChat chat interface. You will see:

1. **Top area**: Service account articles, cards, images, and text content pushed by the account
2. **Bottom area**: Multiple expandable menu buttons with labels like 产品介绍, 联系我们, 服务大厅 — NOT the normal chat input bar
3. **To access chat input**: Look for a small, inconspicuous GRAY button on the RIGHT side of those menu buttons. This button is a circle containing a keyboard icon. It is very small and gray — easily missed on dark backgrounds.
4. **DO NOT click the person/profile icon** (人像) in the top right corner — that opens the service account's profile page, NOT the chat input.
5. **After clicking the keyboard button**: The menu buttons collapse and a normal text input area appears at the bottom. You can then type and send messages normally.

**Troubleshooting**: If you cannot find the keyboard button, use magnifier to zoom into the bottom-right area of the window. The button is often near the right edge, below the article content, at the same row as the menu buttons. If the keyboard icon is not visible, the account may have disabled chat — verify with the user.
