"""Basic functionality tests to ensure core components work."""

import pytest
from datetime import datetime
from src.gdrive_explorer.models import DriveItem, DriveStructure, ItemType


class TestBasicFunctionality:
    """Test basic functionality works."""
    
    def test_drive_item_creation(self):
        """Test basic DriveItem creation."""
        item = DriveItem(
            id="test123",
            name="test_file.txt",
            type=ItemType.FILE,
            mime_type="text/plain",
            size=1024
        )
        
        assert item.id == "test123"
        assert item.name == "test_file.txt"
        assert item.size == 1024
        assert item.type == ItemType.FILE
        assert not item.is_folder
    
    def test_drive_folder_creation(self):
        """Test basic folder creation."""
        folder = DriveItem(
            id="folder123",
            name="My Folder",
            type=ItemType.FOLDER,
            mime_type="application/vnd.google-apps.folder",
            size=0
        )
        
        assert folder.is_folder
        assert folder.type == ItemType.FOLDER
        assert folder.size == 0
    
    def test_drive_structure_creation(self):
        """Test basic DriveStructure creation."""
        structure = DriveStructure()
        
        assert len(structure.all_items) == 0
        assert structure.total_files == 0
        assert structure.total_folders == 0
        assert not structure.scan_complete
    
    def test_add_item_to_structure(self):
        """Test adding items to structure."""
        structure = DriveStructure()
        
        item = DriveItem(
            id="test",
            name="test.txt",
            type=ItemType.FILE,
            mime_type="text/plain",
            size=100
        )
        
        structure.add_item(item)
        
        assert len(structure.all_items) == 1
        assert structure.get_item("test") == item
    
    def test_folder_children(self):
        """Test folder parent-child relationships."""
        folder = DriveItem(
            id="parent",
            name="Parent Folder", 
            type=ItemType.FOLDER,
            mime_type="application/vnd.google-apps.folder",
            size=0
        )
        
        file_item = DriveItem(
            id="child",
            name="child.txt",
            type=ItemType.FILE,
            mime_type="text/plain",
            size=200,
            parent_ids=["parent"]
        )
        
        folder.children.append(file_item)
        
        assert len(folder.children) == 1
        assert folder.children[0] == file_item
        assert "parent" in file_item.parent_ids
    
    def test_google_workspace_detection(self):
        """Test Google Workspace file detection."""
        workspace_file = DriveItem(
            id="workspace",
            name="My Document",
            type=ItemType.GOOGLE_DOC,  # Will be auto-set by validator
            mime_type="application/vnd.google-apps.document",
            size=0
        )
        
        assert workspace_file.is_google_workspace_file
        assert workspace_file.type == ItemType.GOOGLE_DOC
    
    def test_item_type_enum(self):
        """Test ItemType enum values."""
        assert ItemType.FILE == "file"
        assert ItemType.FOLDER == "folder"
        assert ItemType.GOOGLE_DOC == "google_doc"


class TestCalculatorBasics:
    """Test calculator can be imported and created."""
    
    def test_calculator_import(self):
        """Test calculator can be imported."""
        from src.gdrive_explorer.calculator import DriveCalculator
        
        # Should not raise an exception
        assert DriveCalculator is not None
    
    def test_calculator_creation(self):
        """Test calculator can be created with mock client."""
        from unittest.mock import Mock
        from src.gdrive_explorer.calculator import DriveCalculator
        
        mock_client = Mock()
        calc = DriveCalculator(mock_client)
        
        assert calc.client == mock_client
        assert hasattr(calc, '_processed_items')
        assert hasattr(calc, '_errors_encountered')


class TestCacheBasics:
    """Test cache can be imported and created."""
    
    def test_cache_import(self):
        """Test cache can be imported."""
        from src.gdrive_explorer.cache import DriveCache
        
        assert DriveCache is not None
    
    def test_cache_creation(self):
        """Test cache can be created."""
        from src.gdrive_explorer.cache import DriveCache
        
        # Use in-memory database for testing
        cache = DriveCache(":memory:")
        
        assert hasattr(cache, 'enabled')
        assert hasattr(cache, 'cache_path')


class TestErrorHandling:
    """Test basic error handling."""
    
    def test_calculator_errors_import(self):
        """Test calculator error classes can be imported."""
        from src.gdrive_explorer.calculator import (
            SizeCalculationError, PermissionError, RateLimitError
        )
        
        assert SizeCalculationError is not None
        assert PermissionError is not None
        assert RateLimitError is not None
    
    def test_error_creation(self):
        """Test error classes can be created."""
        from src.gdrive_explorer.calculator import SizeCalculationError
        
        error = SizeCalculationError("Test error")
        assert str(error) == "Test error"


class TestConfigAndUtils:
    """Test config and utilities."""
    
    def test_utils_import(self):
        """Test utils can be imported."""
        from src.gdrive_explorer.utils import format_file_size
        
        # Test basic formatting
        assert "1.0 KB" in format_file_size(1024)
        assert "1.0 MB" in format_file_size(1024 * 1024)
    
    def test_config_import(self):
        """Test config can be imported."""
        from src.gdrive_explorer.config import get_config
        
        # Should not raise an exception
        config = get_config()
        assert config is not None