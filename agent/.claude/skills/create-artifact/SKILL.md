---
name: create-artifact
description: >
  Use the create_artifact tool to write a file and register it as a downloadable
  artifact in the chat UI. Invoke this skill whenever the user asks for a report,
  document, spreadsheet, data export, or any output they would want to download or
  keep. Do NOT use the plain Write tool for user-facing files — use create_artifact
  so the file appears in the Artifacts panel automatically.
user-invocable: false
allowed-tools: mcp__artifact_tools__create_artifact
---

## When to use `create_artifact`

Use `mcp__artifact_tools__create_artifact` — not the built-in `Write` tool — whenever
the output is a file the user would want to download, share, or open externally:

- A report or summary document → `md` or `txt`
- Tabular data, calculations, or an export → `csv`
- Any file the user asks you to "generate", "create", "export", or "write me"

Use the built-in `Write` tool only for internal/intermediate files (helper scripts,
config files, temp data) that are not meant to surface to the user.

## Tool signature

```
mcp__artifact_tools__create_artifact(
  filename: str,   # Descriptive base name, no path separators — e.g. "tax_summary.md"
  content:  str,   # Complete UTF-8 text content to write
  format:   str    # One of: txt · md · csv
)
```

### Supported formats

| format | Use for |
|--------|---------|
| `txt`  | Plain-text output, notes, unformatted summaries |
| `md`   | Structured documents — headings, tables, bullet lists |
| `csv`  | Tabular data; always include a header row as the first line |

## Examples

**"Give me a CSV of standard deduction amounts by filing status for 2024"**
```
mcp__artifact_tools__create_artifact(
  filename="standard_deductions_2024.csv",
  content="Filing Status,Standard Deduction\nSingle,14600\nMarried Filing Jointly,29200\nHead of Household,21900",
  format="csv"
)
```

**"Write me a freelancer tax filing guide"**
```
mcp__artifact_tools__create_artifact(
  filename="freelancer_filing_guide.md",
  content="# Freelancer Tax Filing Guide\n\n## Overview\n...",
  format="md"
)
```

## Naming conventions

- Lowercase, words separated by underscores: `quarterly_tax_estimate.csv`
- No path separators (`/`, `\`) — they are stripped automatically
- Be descriptive so the user recognises the file in the panel

## After creating an artifact

Briefly confirm what was created and what it contains, e.g.:
> "I've created `freelancer_filing_guide.md` with a step-by-step guide covering
> quarterly estimated taxes, self-employment deductions, and record-keeping. It's
> available in the Artifacts panel."
