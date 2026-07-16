# Application Launch & Context Switching

## Summary
How to launch Windows applications and switch between them reliably

## Context
Before interacting with any application, CUA must launch it and confirm it is the active window.

## Guidance
- Launch: Start menu search, desktop shortcut, shell:AppsFolder, command-line
- Activation: SetForegroundWindow + focus verification; restore minimized via ShowWindow
- Cross-app switching: Preserve context state when switching; avoid race conditions
- Clean state: Start each task from clean desktop; close interfering apps first
- Verify main editing window is fully loaded and in edit mode before interaction
