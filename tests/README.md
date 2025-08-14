# Google Drive Explorer Test Suite

This directory contains comprehensive tests for the Google Drive Explorer application.

## Test Structure

### Core Test Files

- **`test_basic.py`** - Basic functionality tests to ensure core components work
- **`test_models.py`** - Tests for DriveItem and DriveStructure data models  
- **`test_cache.py`** - Tests for SQLite caching functionality
- **`test_calculator.py`** - Tests for size calculation engine
- **`test_integration.py`** - Integration tests between components

### Test Configuration

- **`conftest.py`** - Test fixtures and configuration
- **`__init__.py`** - Package marker

## Test Categories

### Unit Tests
- Model validation and serialization
- Cache operations (store, retrieve, expire)
- Calculator algorithms and error handling
- Configuration and utilities

### Integration Tests  
- End-to-end workflow testing
- Component interaction validation
- CLI command testing
- Error recovery scenarios

### Performance Tests
- Large dataset handling
- Memory usage validation  
- Cache performance
- Calculation efficiency

## Test Coverage

The test suite covers:

✅ **Phase 1**: Authentication and API client  
✅ **Phase 2**: Data models and structure traversal  
✅ **Phase 3**: Size calculation engine with error handling  
✅ **Phase 4**: CLI visualization and display  
✅ **Cache System**: SQLite caching with migration  
✅ **Error Handling**: Permission errors, rate limits, API failures  

## Running Tests

### Basic Tests (Fastest)
```bash
uv run pytest tests/test_basic.py -v
```

### Full Test Suite
```bash
uv run pytest tests/ -v
```

### With Coverage
```bash
uv run pytest tests/ --cov=src/gdrive_explorer --cov-report=html
```

### Specific Test Categories
```bash
# Model tests only
uv run pytest tests/test_models.py -v

# Cache tests only  
uv run pytest tests/test_cache.py -v

# Calculator tests only
uv run pytest tests/test_calculator.py -v

# Integration tests only
uv run pytest tests/test_integration.py -v
```

## Test Fixtures

The test suite includes comprehensive fixtures in `conftest.py`:

- **Sample Data**: Realistic Google Drive structures for testing
- **Mock Objects**: Mocked API clients, cache, and configuration
- **Temporary Resources**: Temporary directories and databases
- **Large Datasets**: Performance testing with 1000+ files

## Test Philosophy

Tests follow these principles:

1. **Fast by Default**: Unit tests run in milliseconds
2. **Isolated**: Each test is independent with proper setup/teardown  
3. **Realistic**: Test data mimics real Google Drive structures
4. **Comprehensive**: Cover happy path, edge cases, and error conditions
5. **Maintainable**: Clear naming and documentation

## Key Test Scenarios

### Data Model Tests
- Item creation and validation
- Parent-child relationships
- Google Workspace file detection
- Structure building and querying

### Cache Tests
- Item storage and retrieval
- Structure caching
- Expiry and invalidation
- Database migration
- Concurrent access safety

### Calculator Tests
- Recursive size calculation
- Performance optimizations
- Error handling (permissions, rate limits)
- Cache integration
- Large dataset processing

### Integration Tests
- Complete scan workflows
- CLI command execution
- Error recovery
- Cache persistence across sessions

## Adding New Tests

When adding new functionality:

1. Add unit tests to the appropriate `test_*.py` file
2. Add integration tests to `test_integration.py` if needed
3. Update fixtures in `conftest.py` if new test data is required
4. Follow existing naming conventions and documentation style

## Troubleshooting

### Common Issues

**Import Errors**: Ensure you're running tests with `uv run pytest` to use the correct environment.

**Database Errors**: Tests use temporary databases. If you see SQLite errors, check that the cache migration logic handles new databases correctly.

**Mock Errors**: If mocks aren't working, verify the import paths match the actual module structure.

### Debug Mode

Run tests with verbose output and no capture for debugging:

```bash
uv run pytest tests/test_basic.py -v -s --tb=long
```

## Performance Benchmarks

The test suite includes performance benchmarks:

- **Model Operations**: < 1ms per operation
- **Cache Operations**: < 10ms per item
- **Small Calculations**: < 100ms for 100 folders
- **Large Calculations**: < 30s for 1000+ folders
- **Memory Usage**: < 10MB growth for large datasets

Tests will fail if performance degrades significantly beyond these benchmarks.