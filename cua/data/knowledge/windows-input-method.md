# Windows Chinese Input Method Handling

## Summary
How to handle Chinese IME when typing text on Windows desktop

## Context
When typing in any Windows application with Chinese IME enabled, keystrokes
may be intercepted by the IME instead of reaching the application directly.

## Guidance
- Always prefer paste_text over type_keys for any text content
- If IME pops up unexpectedly, press Escape to close it
- Enter confirms raw English input when IME is active
- Space selects first candidate when typing Pinyin
- Shift toggles between Chinese and English mode
- For Chinese app names, paste into Start menu search instead of typing
