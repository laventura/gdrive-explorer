"""Tests for DriveItem and DriveStructure models."""

import pytest
from datetime import datetime, timedelta
from src.gdrive_explorer.models import DriveItem, DriveStructure, ItemType


class TestDriveItem:
    """Test DriveItem model functionality."""
    
    def test_create_file_item(self):
        """Test creating a file item."""
        now = datetime.now()
        item = DriveItem(
            id="file123",
            name="test.pdf",
            type=ItemType.FILE,
            mime_type="application/pdf",
            size=1024,
            modified_time=now,
            parent_ids=["folder456"]
        )
        
        assert item.id == "file123"
        assert item.name == "test.pdf"
        assert item.type == ItemType.FILE
        assert item.size == 1024
        assert item.modified_time == now
        assert "folder456" in item.parent_ids
        assert not item.is_folder
        assert not item.is_google_workspace_file
        assert item.calculated_size is None
        assert item.children == []
    
    def test_create_folder_item(self):
        """Test creating a folder item."""
        item = DriveItem(
            id="folder123",
            name="My Folder",
            type=ItemType.FOLDER,
            mime_type="application/vnd.google-apps.folder",
            size=0,
            parent_ids=[]
        )
        
        assert item.is_folder
        assert item.size == 0
        assert len(item.parent_ids) == 0
    
    def test_google_workspace_file(self):
        """Test Google Workspace file detection."""
        item = DriveItem(
            id="doc123",
            name="My Document",
            type=ItemType.GOOGLE_DOC,
            size=0,
            mime_type="application/vnd.google-apps.document"
        )
        
        assert item.is_google_workspace_file
        assert not item.is_folder
    
    def test_add_child_to_folder(self):
        """Test adding children to folder."""
        folder = DriveItem(
            id="folder1",
            name="Parent",
            type=ItemType.FOLDER,
            mime_type="application/vnd.google-apps.folder",
            size=0
        )
        
        file1 = DriveItem(
            id="file1",
            name="child1.txt",
            type=ItemType.FILE,
            mime_type="text/plain",
            size=100,
            parent_ids=["folder1"]
        )
        
        file2 = DriveItem(
            id="file2", 
            name="child2.txt",
            type=ItemType.FILE,
            mime_type="text/plain",
            size=200,
            parent_ids=["folder1"]
        )
        
        folder.children.extend([file1, file2])
        
        assert len(folder.children) == 2
        assert file1 in folder.children
        assert file2 in folder.children
    
    def test_item_equality(self):
        """Test DriveItem equality comparison."""
        item1 = DriveItem(id="123", name="test", type=ItemType.FILE, mime_type="text/plain", size=100)
        item2 = DriveItem(id="123", name="different", type=ItemType.FOLDER, mime_type="application/vnd.google-apps.folder", size=0)
        item3 = DriveItem(id="456", name="test", type=ItemType.FILE, mime_type="text/plain", size=100)
        
        # Items are equal if they have the same ID
        assert item1 == item2
        assert item1 != item3
    
    def test_calculated_size_updates(self):
        """Test calculated size and metadata updates."""
        folder = DriveItem(
            id="folder1",
            name="Test Folder",
            type=ItemType.FOLDER,
            mime_type="application/vnd.google-apps.folder",
            size=0
        )
        
        # Initially no calculated size
        assert folder.calculated_size is None
        assert folder.file_count == 0
        assert folder.folder_count == 0
        assert not folder.scan_complete
        
        # Update calculated values
        folder.calculated_size = 1500
        folder.file_count = 10
        folder.folder_count = 2
        folder.scan_complete = True
        folder.last_scanned = datetime.now()
        
        assert folder.calculated_size == 1500
        assert folder.file_count == 10
        assert folder.folder_count == 2
        assert folder.scan_complete


class TestDriveStructure:
    """Test DriveStructure functionality."""
    
    def test_create_empty_structure(self):
        """Test creating an empty drive structure."""
        structure = DriveStructure()
        
        assert len(structure.all_items) == 0
        assert structure.total_files == 0
        assert structure.total_folders == 0
        assert structure.total_size == 0
        assert not structure.scan_complete
        assert structure.scan_timestamp is None
    
    def test_add_items_to_structure(self, sample_drive_items):
        """Test adding items to structure."""
        structure = DriveStructure()
        
        for item in sample_drive_items.values():
            structure.add_item(item)
        
        assert len(structure.all_items) == len(sample_drive_items)
        
        # Test we can retrieve items by ID
        for item_id, item in sample_drive_items.items():
            assert structure.get_item(item_id) == item
    
    def test_set_root_item(self, sample_drive_items):
        """Test setting root item."""
        structure = DriveStructure()
        root_item = sample_drive_items['root']
        
        structure.add_item(root_item)
        
        # Verify root was added to structure
        assert structure.get_item("root") == root_item
        assert structure.get_item("root").name == "My Drive"
    
    def test_get_files_only(self, sample_drive_structure):
        """Test getting only files from structure."""
        files = [item for item in sample_drive_structure.all_items.values() if not item.is_folder]
        
        # Should have 4 files based on fixture
        assert len(files) == 4
        
        for file_item in files:
            assert not file_item.is_folder
            assert file_item.type in [ItemType.FILE, ItemType.GOOGLE_DOC, ItemType.GOOGLE_SHEET, ItemType.GOOGLE_SLIDE]
    
    def test_get_folders_only(self, sample_drive_structure):
        """Test getting only folders from structure."""
        folders = [item for item in sample_drive_structure.all_items.values() if item.is_folder]
        
        # Should have 4 folders based on fixture (root + 3 subfolders)
        assert len(folders) == 4
        
        for folder in folders:
            assert folder.is_folder
            assert folder.type == ItemType.FOLDER
    
    def test_find_item_by_name(self, sample_drive_structure):
        """Test finding items by name."""
        # Find exact match
        documents = [item for item in sample_drive_structure.all_items.values() if item.name == "Documents"]
        assert len(documents) == 1
        assert documents[0].name == "Documents"
        
        # Find partial match
        doc_items = [item for item in sample_drive_structure.all_items.values() if "doc" in item.name.lower()]
        assert len(doc_items) >= 2  # "Documents" folder and "google_doc" file
    
    def test_get_folder_contents(self, sample_drive_structure):
        """Test getting folder contents."""
        # Get root folder contents by checking parent_ids
        root_contents = [item for item in sample_drive_structure.all_items.values() if "root" in item.parent_ids]
        
        # Should contain 2 direct subfolders
        folder_children = [item for item in root_contents if item.is_folder]
        assert len(folder_children) == 2
        
        # Test folder that doesn't exist
        empty_contents = [item for item in sample_drive_structure.all_items.values() if "nonexistent" in item.parent_ids]
        assert len(empty_contents) == 0
    
    def test_structure_statistics_update(self, sample_drive_structure):
        """Test updating structure statistics."""
        # Update statistics
        sample_drive_structure.total_files = 4
        sample_drive_structure.total_folders = 4
        sample_drive_structure.total_size = 3 * 1024 * 1024 + 512 * 1024  # Sum of file sizes
        sample_drive_structure.scan_complete = True
        sample_drive_structure.scan_timestamp = datetime.now()
        
        assert sample_drive_structure.total_files == 4
        assert sample_drive_structure.total_folders == 4
        assert sample_drive_structure.total_size > 0
        assert sample_drive_structure.scan_complete
        assert sample_drive_structure.scan_timestamp is not None
    
    def test_structure_serialization(self, sample_drive_structure):
        """Test that structure can be serialized/deserialized."""
        # Get dictionary representation
        structure_dict = sample_drive_structure.dict()
        
        assert "all_items" in structure_dict
        assert "total_files" in structure_dict
        assert "total_folders" in structure_dict
        assert "scan_complete" in structure_dict
        
        # Reconstruct from dict
        new_structure = DriveStructure(**structure_dict)
        
        assert len(new_structure.all_items) == len(sample_drive_structure.all_items)
        assert new_structure.total_files == sample_drive_structure.total_files
        assert new_structure.scan_complete == sample_drive_structure.scan_complete


class TestItemTypeEnum:
    """Test ItemType enumeration."""
    
    def test_item_type_values(self):
        """Test ItemType enum values."""
        assert ItemType.FILE == "file"
        assert ItemType.FOLDER == "folder"
    
    def test_item_type_comparison(self):
        """Test ItemType comparison."""
        assert ItemType.FILE != ItemType.FOLDER
        assert ItemType.FILE == "file"
        assert ItemType.FOLDER == "folder"


class TestModelValidation:
    """Test model validation and edge cases."""
    
    def test_invalid_item_type(self):
        """Test that invalid item types are rejected."""
        with pytest.raises(ValueError):
            DriveItem(
                id="test",
                name="test",
                type="invalid_type",  # Should cause validation error
                mime_type="text/plain",
                size=0
            )
    
    def test_negative_size(self):
        """Test that negative sizes are handled."""
        # Should be allowed (some edge cases might have negative sizes)
        item = DriveItem(
            id="test",
            name="test", 
            type=ItemType.FILE,
            mime_type="text/plain",
            size=-1
        )
        assert item.size == -1
    
    def test_empty_name(self):
        """Test items with empty names."""
        item = DriveItem(
            id="test",
            name="",
            type=ItemType.FILE,
            mime_type="text/plain",
            size=0
        )
        assert item.name == ""
    
    def test_very_large_size(self):
        """Test items with very large sizes."""
        large_size = 10**15  # 1 Petabyte
        item = DriveItem(
            id="test",
            name="huge_file",
            type=ItemType.FILE,
            mime_type="text/plain",
            size=large_size
        )
        assert item.size == large_size
    
    def test_future_modified_time(self):
        """Test items with future modification times."""
        future_time = datetime.now() + timedelta(days=365)
        item = DriveItem(
            id="test",
            name="future_file",
            type=ItemType.FILE,
            mime_type="text/plain",
            size=100,
            modified_time=future_time
        )
        assert item.modified_time == future_time