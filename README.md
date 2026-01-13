# Lazy Email to Spreadsheet (NOT FUNCTIONAL AT THE MOMENT)

> I really don't like manually putting information into spreadsheets, so here is a very personal solution.

A lightweight Python CLI tool that automatically extracts job application data from Gmail emails using a local LLM (Qwen 2.5 3B via Ollama) and populates a Google Sheet.

## Features

- **Gmail Integration**: Reads emails from your primary inbox
- **Local LLM Processing**: Uses Qwen 2.5 3B (via Ollama) or whichever local llm you desire to extract company, role, and status
- **Google Sheets Output**: Automatically populates a specific job tracking spreadsheet (template coming soon)
- **Stop/Resume**: Gracefully handle interruptions and resume processing
- **Rate Limiting**: Respects API quotas with exponential backoff so we don't get a $10,000 bill from google cloud

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

- Python 3.10+
- [Ollama](https://ollama.ai/) with Qwen 2.5 3B model or another equivalent model (recommend lightweight ones)
- Google Cloud Project with Gmail and Sheets APIs enabled 
- OAuth 2.0 credentials (`credentials.json`)

## Installation coming soon (whenever I finish the whole thing)

## thing i added to preserve my sanity

cd /Users/placeholder/lazy-email-to-spreadsheet
uv sync --extra dev
uv run pytest
