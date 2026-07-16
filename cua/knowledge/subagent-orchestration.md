# Subagent Orchestration Framework

## Summary
1 main agent + 2 subagents architecture for content generation and SVG creation

## Context
CUA uses a modular architecture where the main agent owns GUI interaction and subagents
handle specialized content generation tasks with no direct GUI access.

## Guidance
- **Content Generation Subagent**: Article drafting, outlining, tone alignment, short text composition
- **SVG Asset Generation Subagent**: Vector illustration, icon design, diagram rendering
- Strict separation: GUI logic stays in main agent; content logic stays in subagents
- Idempotent output: Same input produces same output for retry safety
- Fallback: SVG insertion fails → rasterized PNG; content generation fails → template text
- Reuse same subagent parameters across phases for content consistency
