# Lazy Application Tracker (LAT, formerly lazy-email-to-spreadsheet)

> I really don't like manually putting information into spreadsheets, so here is a very personal solution.

A lightweight Python CLI tool that automatically extracts job application data from Gmail emails using a local LLM (Qwen 2.5 3B via Ollama) and populates a Google Sheet.

## Features

- **Gmail Integration**: Reads emails from your primary inbox
- **Local LLM Processing**: Uses Qwen 2.5 3B (via Ollama) or whichever local llm you desire to extract company, role, and status
- **Google Sheets Output**: Automatically populates a specific job tracking spreadsheet (template coming soon)
- **Smart Deduplication**: Multiple emails about the same job (company + role) are merged into one row
- **Automatic Status Updates**: When you receive an OA or interview invite, existing applications are automatically updated
- **Fuzzy Matching**: Handles variations like "Google" vs "Google LLC", "SWE" vs "Software Engineer Intern"
- **Stop/Resume**: Gracefully handle interruptions and resume processing
- **Rate Limiting**: Respects API quotas with exponential backoff so we don't get a $10,000 bill from google cloud
- **Zero Config Required**: Pass spreadsheet URL and all options via command line - no editing files needed!
- **Ollama Auto-Start**: Prompts to start Ollama if not running

## Spreadsheet Structure

The tool writes to a Google Sheet with the following columns (template coming soon):

| Column | Description |
|--------|-------------|
| Company Name | Extracted employer name |
| Application Status | Dropdown: "Submitted Application - Pending Response", "Rejected", "Interview", "OA Invite", "N/A" |
| Role | Extracted job title |
| Date Submitted | Email received date (YYYY-MM-DD) |
| Link to Job Email | Direct Gmail link |

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager - handles Python version automatically)
- [Ollama](https://ollama.ai/) with Qwen 2.5 3B model or another equivalent model (recommend lightweight ones)

## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh
# or: brew install uv

# Clone and enter the project
cd lazy-email-to-spreadsheet

# Install dependencies (uv handles Python 3.10+ automatically)
uv sync

# Run the setup wizard (first time only)
uv run lazy-email setup

# Run!
uv run lazy-email --since 2025-01-01 --spreadsheet-id "https://docs.google.com/spreadsheets/d/YOUR_ID/edit"
```

If you don't provide `--spreadsheet-id`, the tool will prompt you to paste it interactively.

### Setup Wizard

`lazy-email setup` walks you through every prerequisite interactively:

```
[1/5] Google Authentication
  ✓ Authenticated as you@gmail.com

[2/5] Google Sheet
  ✓ Spreadsheet configured: ABC123

[3/5] Ollama
  ✓ Ollama is running

[4/5] LLM Model
  ✗ Model qwen2.5:3b is not available.
  Pull it now? [Y/n]: y
  Pulling qwen2.5:3b...
  ✓ Model qwen2.5:3b ready

[5/5] Verify Connections
  ✓ All connections verified
```

For Google Authentication, you'll need an OAuth credentials file:
1. [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials
2. Create OAuth client ID → Desktop app → Download JSON
3. Save as `credentials.json` in the project folder (gitignored, never committed)

Your auth token is saved at `~/.config/lazy-email/token.json` — you won't need to re-authenticate unless you revoke access.

To re-authenticate at any time:
```bash
uv run lazy-email login --reauth
```

---

## Usage

```bash
# Basic usage - just date and spreadsheet
uv run lazy-email --since 2025-01-01 --spreadsheet-id YOUR_SPREADSHEET_URL

# Specify sheet tab name (default: Sheet1)
uv run lazy-email --since 2025-01-01 --spreadsheet-id YOUR_ID --sheet-name "Applications"

# Use a different LLM model
uv run lazy-email --since 2025-01-01 --spreadsheet-id YOUR_ID --model llama3:8b

# Process more emails
uv run lazy-email --since 2025-01-01 --spreadsheet-id YOUR_ID --max-emails 200

# Reset processing state and start fresh
uv run lazy-email --since 2025-01-01 --spreadsheet-id YOUR_ID --reset

# Preview extracted data without writing to Sheets
uv run lazy-email --since 2025-01-01 --dry-run

# Use old print-based output for development/debugging
uv run lazy-email --since 2025-01-01 --legacy-output

# Verbose logging
uv run lazy-email --since 2025-01-01 -v
```

### All CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--since` | Process emails since this date (YYYY-MM-DD) | Required |
| `--until` | Process emails until this date (YYYY-MM-DD, exclusive) | None |
| `--spreadsheet-id` | Google Sheets URL or ID | Prompted if not set |
| `--sheet-name` | Name of sheet tab to write to | Sheet1 |
| `--model` | Ollama model to use | qwen2.5:3b |
| `--max-emails` | Maximum emails to process | Unlimited |
| `--reset` | Reset state and start fresh | - |
| `--dry-run` | Preview extracted data without writing to Sheets | - |
| `--legacy-output` | Use the previous print-based output instead of progress bars | - |
| `-v, --verbose` | Enable verbose logging | - |

## ⚠️ Important Notes

### CLI Progress Output
Normal runs show progress bars when the total amount of work is known and spinner/status indicators for phases with unknown duration. Use `--legacy-output` to restore the previous print-based output for development or debugging. Dry-run output stays stable for testing and preview purposes.

### Large Email Volumes
Processing many emails can take significant time since each email requires an LLM call. Consider:
- Start with `--max-emails 50` for testing
- The tool processes ~1-2 emails per second depending on your hardware
- Processing 1000+ emails may take 10-20 minutes
- The tool saves progress, so you can safely Ctrl+C and resume later

### Spreadsheet Renaming
After processing completes, the tool automatically appends the current date (MM/DD/YYYY) to your spreadsheet title to help you track when it was last updated.

## Ollama Auto-Start

If Ollama isn't running, the tool will ask if you want to start it automatically:

```
  ⚠ Ollama is not running.
  Start Ollama automatically? (y/n): y
  Starting Ollama... ✓
```

## Development

```bash
cd /Users/placeholder/lazy-email-to-spreadsheet
uv sync --extra dev
uv run pytest
```
