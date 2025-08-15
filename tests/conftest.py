"""Test configuration and fixtures for gdrive-explorer tests."""

import pytest
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, MagicMock
from typing import Dict, List

from src.gdrive_explorer.models import DriveItem, DriveStructure, ItemType
from src.gdrive_explorer.cache import DriveCache
from src.gdrive_explorer.client import DriveClient
from src.gdrive_explorer.calculator import DriveCalculator


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_config():
    """Create a mock configuration for testing."""
    config = Mock()
    config.cache.enabled = True
    config.cache.ttl_hours = 24
    config.cache.max_size_mb = 100
    config.cache.database_path = ":memory:"  # Use in-memory SQLite for tests
    config.api.rate_limit_delay = 0.1
    config.api.max_retries = 3
    config.api.timeout = 30
    return config


@pytest.fixture
def sample_files():
    """Create sample file data for testing."""
    now = datetime.now()
    return [
        {
            'id': 'file1',
            'name': 'document.pdf',
            'type': ItemType.FILE,
            'mime_type': 'application/pdf',
            'size': 1024 * 1024,  # 1MB
            'modified_time': now - timedelta(days=1),
            'parent_ids': ['folder1'],
            'is_google_workspace_file': False
        },
        {
            'id': 'file2', 
            'name': 'spreadsheet.xlsx',
            'type': ItemType.FILE,
            'mime_type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'size': 512 * 1024,  # 512KB
            'modified_time': now - timedelta(hours=12),
            'parent_ids': ['folder1'],
            'is_google_workspace_file': False
        },
        {
            'id': 'file3',
            'name': 'google_doc',
            'type': ItemType.GOOGLE_DOC,
            'mime_type': 'application/vnd.google-apps.document',
            'size': 0,  # Google Workspace file
            'modified_time': now - timedelta(hours=6),
            'parent_ids': ['folder2'],
            'is_google_workspace_file': True
        },
        {
            'id': 'file4',
            'name': 'image.jpg',
            'type': ItemType.FILE,
            'mime_type': 'image/jpeg',
            'size': 2 * 1024 * 1024,  # 2MB
            'modified_time': now - timedelta(hours=3),
            'parent_ids': ['folder2'],
            'is_google_workspace_file': False
        }
    ]


@pytest.fixture
def sample_folders():
    """Create sample folder data for testing."""
    now = datetime.now()
    return [
        {
            'id': 'root',
            'name': 'My Drive',
            'type': ItemType.FOLDER,
            'mime_type': 'application/vnd.google-apps.folder',
            'size': 0,
            'modified_time': now - timedelta(days=7),
            'parent_ids': [],
            'is_google_workspace_file': False
        },
        {
            'id': 'folder1',
            'name': 'Documents',
            'type': ItemType.FOLDER,
            'mime_type': 'application/vnd.google-apps.folder',
            'size': 0,
            'modified_time': now - timedelta(days=2),
            'parent_ids': ['root'],
            'is_google_workspace_file': False
        },
        {
            'id': 'folder2',
            'name': 'Photos',
            'type': ItemType.FOLDER,
            'mime_type': 'application/vnd.google-apps.folder',
            'size': 0,
            'modified_time': now - timedelta(days=1),
            'parent_ids': ['root'],
            'is_google_workspace_file': False
        },
        {
            'id': 'folder3',
            'name': 'Projects',
            'type': ItemType.FOLDER,
            'mime_type': 'application/vnd.google-apps.folder',
            'size': 0,
            'modified_time': now - timedelta(hours=8),
            'parent_ids': ['folder1'],
            'is_google_workspace_file': False
        }
    ]


@pytest.fixture
def sample_drive_items(sample_files, sample_folders):
    """Create DriveItem objects from sample data."""
    items = {}
    
    # Create folder items first
    for folder_data in sample_folders:
        items[folder_data['id']] = DriveItem(**folder_data)
    
    # Create file items
    for file_data in sample_files:
        items[file_data['id']] = DriveItem(**file_data)
    
    # Build parent-child relationships
    for item in items.values():
        if item.parent_ids:
            for parent_id in item.parent_ids:
                if parent_id in items:
                    parent = items[parent_id]
                    parent.children.append(item)
    
    return items


@pytest.fixture
def sample_drive_structure(sample_drive_items):
    """Create a complete DriveStructure for testing."""
    structure = DriveStructure()
    
    for item in sample_drive_items.values():
        structure.add_item(item)
    
    structure.scan_complete = True
    structure.scan_timestamp = datetime.now()
    
    return structure


@pytest.fixture
def mock_drive_client():
    """Create a mock DriveClient for testing."""
    client = Mock()
    client.is_authenticated = True
    client.get_user_info.return_value = {
        'user': {'displayName': 'Test User', 'emailAddress': 'test@example.com'},
        'storageQuota': {
            'limit': '15000000000',  # 15GB
            'usage': '5000000000'    # 5GB
        }
    }
    return client


@pytest.fixture
def mock_cache(temp_dir):
    """Create a real cache instance with temporary database."""
    cache_path = temp_dir / "test_cache.db"
    cache = DriveCache(str(cache_path))
    return cache


@pytest.fixture
def mock_calculator(mock_drive_client):
    """Create a calculator with mocked dependencies."""
    calc = DriveCalculator(mock_drive_client)
    # Replace with a mock cache for testing
    calc.cache = Mock()
    calc.cache.get_item.return_value = None
    calc.cache.cache_item.return_value = True
    calc.cache.cache_structure.return_value = True
    calc.cache.invalidate_item.return_value = True
    
    # Mock config with cache settings
    calc.config = Mock()
    calc.config.cache.ttl_hours = 24
    calc.config.cache.enabled = True
    
    return calc


@pytest.fixture
def large_drive_structure():
    """Create a large drive structure for performance testing."""
    structure = DriveStructure()
    now = datetime.now()
    
    # Create root
    root = DriveItem(
        id='root',
        name='My Drive',
        type=ItemType.FOLDER,
        mime_type='application/vnd.google-apps.folder',
        size=0,
        modified_time=now - timedelta(days=30),
        parent_ids=[]
    )
    structure.add_item(root)
    
    # Create 100 folders and 1000 files
    for i in range(100):
        folder = DriveItem(
            id=f'folder_{i}',
            name=f'Folder {i}',
            type=ItemType.FOLDER,
            mime_type='application/vnd.google-apps.folder',
            size=0,
            modified_time=now - timedelta(days=i % 30),
            parent_ids=['root']
        )
        structure.add_item(folder)
        root.children.append(folder)
        
        # Add 10 files to each folder
        for j in range(10):
            file_item = DriveItem(
                id=f'file_{i}_{j}',
                name=f'file_{i}_{j}.txt',
                type=ItemType.FILE,
                mime_type='text/plain',
                size=(i + j + 1) * 1024,  # Variable sizes
                modified_time=now - timedelta(hours=i + j),
                parent_ids=[folder.id]
            )
            structure.add_item(file_item)
            folder.children.append(file_item)
    
    structure.total_files = 1000
    structure.total_folders = 101  # 100 + root
    structure.scan_complete = True
    structure.scan_timestamp = now
    
    return structure


def pytest_configure(config):
    """Configure pytest for the entire test session."""
    # Disable logging during tests to reduce noise
    import logging
    logging.disable(logging.CRITICAL)


class MockResponse:
    """Mock HTTP response for testing API calls."""
    
    def __init__(self, status_code: int, data: Dict = None):
        self.status = status_code
        self.data = data or {}
    
    def get(self, key: str, default=None):
        return self.data.get(key, default)


@pytest.fixture
def mock_http_responses():
    """Create mock HTTP responses for various scenarios."""
    return {
        'success': MockResponse(200, {'items': []}),
        'permission_denied': MockResponse(403, {'error': 'Access denied'}),
        'rate_limited': MockResponse(429, {'error': 'Rate limit exceeded'}),
        'server_error': MockResponse(500, {'error': 'Internal server error'}),
        'not_found': MockResponse(404, {'error': 'File not found'})
    }