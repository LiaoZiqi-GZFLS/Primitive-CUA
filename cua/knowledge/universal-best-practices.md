# Universal CUA Best Practices for Windows 11

## Summary
Cross-cutting best practices for all CUA desktop automation tasks

## Context
Applies to every task regardless of application or workflow phase.

## Guidance
- **Interaction priority**: COM (Office only) > UIA > keyboard shortcut > visual coordinate click
- **DPI awareness**: Ensure runtime is DPI-aware to avoid coordinate offsets on high-DPI displays
- **Wait strategy**: Event-driven waiting (wait for element/COM ready) > fixed sleep; add timeouts
- **Idempotent operations**: Design each step to be retry-safe (check state before acting)
- **Fallback layering**: Every operation needs primary method + at least one fallback path
- **Clean state**: Start from clean desktop; close interfering apps before execution
- **Clipboard preference**: Use clipboard paste for all text input; type_keys only for shortcuts
- **Verify every action**: Confirm outcome before next step; use verify screenshots + OCR + analyst
- **Handle interruptions**: Notifications, update prompts, UAC dialogs should be dismissed before task
- **Absolute paths**: Always use absolute file paths; verify file existence after file operations
- **App launch verification**: After `launch_app()`, use `list_windows()` to confirm the target app actually opened. If the app is not installed, Windows Start menu search will silently fall back to a Bing search in Edge instead — always check.
