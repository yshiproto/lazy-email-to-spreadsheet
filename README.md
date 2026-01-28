# Lazy Email to Spreadsheet

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
- Google Cloud Project with Gmail and Sheets APIs enabled (see setup below)

## Google Cloud Setup (One-Time, ~5 minutes)

You need to create credentials so the tool can access your Gmail and Google Sheets. This is a one-time setup.

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown (top-left, next to "Google Cloud")
3. Click **"New Project"**
4. Name it something like `lazy-email` and click **Create**
5. Make sure your new project is selected in the dropdown

### Step 2: Enable the APIs

1. Go to [APIs & Services > Library](https://console.cloud.google.com/apis/library)
2. Search for **"Gmail API"** → Click it → Click **Enable**
3. Search for **"Google Sheets API"** → Click it → Click **Enable**

### Step 3: Configure OAuth Consent Screen

1. Go to [APIs & Services > OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent)
2. Select **"External"** → Click **Create**
3. Fill in the required fields:
   - **App name**: `Lazy Email` (or whatever you want)
   - **User support email**: Select your email
   - **Developer contact email**: Enter your email
4. Click **Save and Continue**
5. On "Scopes" page, click **Save and Continue** (no changes needed)
6. On "Test users" page, click **Add Users** → Enter your Gmail address → Click **Save and Continue**
7. Click **Back to Dashboard**

### Step 4: Create OAuth Credentials

1. Go to [APIs & Services > Credentials](https://console.cloud.google.com/apis/credentials)
2. Click **"+ Create Credentials"** → Select **"OAuth client ID"**
3. Application type: **"Desktop app"**
4. Name: `Lazy Email CLI` (or whatever)
5. Click **Create**
6. Click **"Download JSON"** (⬇ icon)
7. **Move/rename the downloaded file** to your project folder as `credentials.json`:
   ```bash
   mv ~/Downloads/client_secret_*.json ./credentials.json
   ```

That's it! The first time you run the tool, a browser window will open asking you to authorize access to your Gmail and Sheets.

---

## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh
OR
brew install uv

# Clone and enter the project
cd lazy-email-to-spreadsheet

# Install dependencies (uv handles Python 3.10+ automatically)
uv sync

# Pull the LLM model (first time only)
ollama serve
ollama pull qwen2.5:3b

# Run with your spreadsheet URL - that's it!
uv run lazy-email --since 2025-01-01 --spreadsheet-id "https://docs.google.com/spreadsheets/d/YOUR_ID/edit"
```

If you don't provide `--spreadsheet-id`, the tool will prompt you to paste it interactively.

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

# Verbose logging
uv run lazy-email --since 2025-01-01 -v
```

### All CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--since` | Process emails since this date (YYYY-MM-DD) | Required |
| `--spreadsheet-id` | Google Sheets URL or ID | Prompted if not set |
| `--sheet-name` | Name of sheet tab to write to | Sheet1 |
| `--model` | Ollama model to use | qwen2.5:3b |
| `--max-emails` | Maximum emails to process | Unlimited |
| `--reset` | Reset state and start fresh | - |
| `-v, --verbose` | Enable verbose logging | - |

## ⚠️ Important Notes

### Credentials File
When downloading OAuth credentials from Google Cloud Console, the file will be named something like `client_secret_XXXXX.json`. You **must** rename it to exactly `credentials.json` and place it in your project root folder:
```bash
mv ~/Downloads/client_secret_*.json ./credentials.json
```

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
