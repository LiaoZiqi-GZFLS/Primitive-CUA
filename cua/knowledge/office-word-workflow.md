# Microsoft Word Desktop Task Workflow

## Summary
COM-automation-first workflow for creating, formatting, and exporting Word documents

## Context
When working with **Microsoft Word** (NOT WPS), prioritize COM automation over UI interaction for maximum reliability.

**CRITICAL**: When a task says "Office" or "Word" without specifying, it means **Microsoft Office / Microsoft Word** (the globally standard office suite). Only use WPS if the task explicitly mentions "WPS" by name. These are different products with different UI and automation characteristics — do not confuse them.

## Guidance
- **COM Priority**: Document creation, text insertion, formatting via Document/Range objects
- **Style application**: Heading 1/2 via built-in styles; use Ctrl+Alt+1/2/3 shortcuts as fallback
- **SVG insertion**: Word natively supports SVG; use Shapes.AddPicture (COM) or Insert → Pictures (UIA)
- **PDF export**: Document.ExportAsFixedFormat (COM) or File → Save As PDF (UI)
- **File dialogs**: Input absolute path directly into path text box + Enter; COM bypasses dialogs entirely
- **Process readiness**: Check for Protected View, account prompts before interacting
- Protected View: detect "Enable Editing" banner, invoke via UIA
- Account prompts: predefine close button identifiers; use pre-activated Office
- SVG rendering fails: fall back to high-resolution PNG
- Export path: always use absolute paths; verify file existence after export
- Style not applied: verify text selection/range state; use Ctrl+A for full-document baseline
- **Wait strategy**: Use event-driven waiting (wait for element/COM object ready) instead of fixed sleep
