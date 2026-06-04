# TODO

## Core features/what I hope to finish

- [x] Project scaffold & configuration
- [x] Google OAuth authentication module
- [x] Gmail client with rate limiting
- [x] LLM extraction service (Qwen 2.5 3B via Ollama)
- [x] Google Sheets client with batching
- [x] State persistence & resume functionality
- [x] CLI entry point with `--since` flag

## low chance of happening

- [x] Duplicate detection (skip emails already in sheet)
- [x] `--until` date filter for date range queries
- [x] Dry-run preview mode
- [ ] Custom Gmail query filter via CLI
- [ ] Multiple LLM backend support (llama.cpp, transformers)
- [X] Progress bar with estimated time remaining
- [ ] Configurable spreadsheet column mapping
- [ ] remove Google Cloud setup
- [ ] auto-create spreadsheet
- [ ] first run wizard
- [ ] publish
- [ ] allow api hookup for non-local LLMs (if you don't care about privacy)
- [ ] doctor cli option
