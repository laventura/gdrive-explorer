# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Google Drive Explorer - A Python CLI application that explores Google Drive, calculates folder sizes recursively, and displays results sorted by size (largest first) with rich CLI output.

## Architecture

- **Authentication**: OAuth 2.0 user authentication (no service accounts)
- **CLI-focused**: Rich terminal output using `rich` library, no web UI
- **Caching**: SQLite-based caching for performance
- **Structure**: Clean Python package with clear separation of concerns

## Key Dependencies

- `google-api-python-client` - Google Drive API client
- `google-auth-oauthlib` - OAuth 2.0 authentication  
- `click` - CLI framework
- `rich` - Beautiful CLI output and progress bars
- `pydantic` - Data validation and type safety

## Development Phases

Implementation follows 5 phases as outlined in IMPLEMENTATION_PLAN.md:
1. Core Foundation (OAuth + basic API)
2. Data Models & Traversal 
3. Size Calculation Engine
4. CLI Visualization & Sorting
5. Export & Advanced Features

## Common Commands

```bash
# Authentication
uv run python main.py auth                    # Authenticate with Google Drive
uv run python main.py clear-auth              # Clear stored credentials

# Basic operations  
uv run python main.py info                    # Show configuration
uv run python main.py test                    # Test connection and list files

# Phase 2 features
uv run python main.py scan                    # Scan and analyze Drive (preview)
uv run python main.py cache                   # Show cache statistics
uv run python main.py cache-clear             # Clear cache data

# Development
uv run pytest                                 # Run tests (when implemented)
uv run black src/                             # Format code
uv run mypy src/                              # Type checking
```

## Project Structure

```
src/gdrive_explorer/
├── auth.py          # OAuth authentication
├── client.py        # Google Drive API wrapper
├── models.py        # Data models
├── explorer.py      # Core traversal logic
├── calculator.py    # Size calculation
├── cache.py         # SQLite caching
├── cli.py           # CLI interface
├── display.py       # Rich output formatting
└── exporter.py      # Export functionality
```