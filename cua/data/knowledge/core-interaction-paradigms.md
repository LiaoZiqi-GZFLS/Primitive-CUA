# Windows GUI Interaction Paradigms

## Summary
Windows GUI interaction layers: when to use each automation approach on Windows 11

## Context
Windows applications expose different levels of programmatic access. Knowing which layer
to use for each situation is critical for reliable automation.

## The Layers (priority order)

| Priority | Layer | Best For | Avoid For |
|----------|-------|----------|-----------|
| 1 | **COM** | Office apps (Word, Excel, PPT) — full object model access | Non-Office apps |
| 2 | **UIA** (UI Automation) | Native Windows apps, Office ribbon, standard controls | Custom-drawn UI, web content |
| 3 | **Keyboard shortcuts** | Quick navigation, menu access, standard operations | Text input (use paste instead) |
| 4 | **Visual + coordinates** | Custom-drawn UI, games, non-standard controls | Anything a structured tool can access |

## When to Fall Back

- **UIA fails**: Control not found, wrong window focused, custom UI → fall back to screenshot + OCR + coordinates
- **Keyboard unclear**: Unknown shortcut, IME interference, non-standard layout → use UIA or visual
- **Visual unreliable**: Resolution changes, DPI scaling, animations → prefer structured tools

## State Tracking

After each action, verify one of: foreground window handle, process ID, window title, or OCR text.
Track what changed and whether it matches expectations.
