# Windows GUI Interaction Paradigms

## Summary
Windows GUI interaction layers, state verification, and error recovery for CUA on Windows 11

## Context
When interacting with any Windows application, CUA must choose the right interaction layer
and verify every action's outcome before proceeding.

## Guidance
- **Interaction Priority**: COM (Office only) > UIA > keyboard shortcut > visual coordinate click
- **Programmatic Layer**: Use UIA, Win32, MSAA, COM for standard controls and Office apps
- **Visual Fallback**: Screen capture + VLM/OCR for custom-drawn UI, non-standard controls
- **Input**: Prefer clipboard paste (Ctrl+C/V) over per-character keystrokes for text insertion
- **Stepwise Validation**: Verify every action outcome before proceeding to next step
- **Retry**: Retry failed operations 2-3 times with incremental wait time
- **Interruption Handling**: Dismiss ad pop-ups, update prompts, UAC dialogs with predefined rules
- **State Tracking**: Track foreground window handle, process ID, and window title
