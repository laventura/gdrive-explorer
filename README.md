# Google Drive Explorer

A Python CLI application that explores Google Drive, calculates folder sizes recursively, and displays results sorted by size (largest first) with rich CLI output.

## Features

- 🔐 OAuth 2.0 authentication with Google Drive
- 📁 Recursive folder traversal and size calculation
- 📊 Rich CLI output with tables and progress bars
- 🚀 Efficient caching for better performance
- 📤 Export results to CSV/JSON formats
- 🎯 Advanced filtering and sorting options

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd gdrive-explorer
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up Google Drive API credentials:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one
   - Enable the Google Drive API
   - Create OAuth 2.0 credentials (Desktop Application)
   - Download the credentials JSON file
   - Save it as `config/credentials.json`

## Quick Start

1. **Authenticate with Google Drive:**
   ```bash
   python main.py auth
   ```

2. **Test the connection:**
   ```bash
   python main.py test
   ```

3. **View configuration:**
   ```bash
   python main.py info
   ```

## Available Commands

- `gdrive-explorer auth` - Authenticate with Google Drive
- `gdrive-explorer test` - Test connection and list sample files
- `gdrive-explorer info` - Show configuration information
- `gdrive-explorer clear-auth` - Clear stored credentials

## Configuration

The application uses `config/settings.yaml` for configuration. You can also override settings with environment variables:

- `GDRIVE_EXPLORER_CREDENTIALS_FILE` - Path to credentials file
- `GDRIVE_EXPLORER_LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)
- `GDRIVE_EXPLORER_SHOW_PROGRESS` - Show progress bars (true/false)

## Current Status

**Phase 1 Complete:** ✅ Core Foundation
- OAuth 2.0 authentication
- Basic Google Drive API integration
- Configuration management
- CLI framework with basic commands

**Coming Next:** Phase 2 - Data Models & Traversal
- Complete folder structure discovery
- Recursive size calculation
- Advanced caching system

## Development

Install development dependencies:
```bash
pip install -r requirements.txt
```

Run tests:
```bash
pytest
```

Format code:
```bash
black src/
```

Type checking:
```bash
mypy src/
```

## License

MIT License - see LICENSE file for details.