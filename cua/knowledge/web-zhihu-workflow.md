# Zhihu Web Task Workflow

## Summary
Browser-based workflow for creating and publishing articles on Zhihu

## Context
When the task involves creating content on Zhihu, use web tools with the built-in Playwright browser.

## Guidance
- Navigate to zhihu.com, authenticate (prefer cookie injection; fallback credential input)
- Enter article editor via "Write Article" entry
- Use DraftContent subagent for article text, GenerateImage subagent for illustrations
- Inject content via clipboard paste (not keystrokes) — editor uses nested iframes
- SVG insertion: rasterize to PNG → upload via file picker (most compatible); or paste bitmap
- Add human-like delays and non-uniform intervals to reduce CAPTCHA
- Post-publication: poll with exponential backoff to confirm article appears in search
- Login CAPTCHA: fall back to human-in-the-loop; prefer persistent cookies
- Iframe navigation: switch frame context before locating editor elements
- Save draft before retrying if publication fails
