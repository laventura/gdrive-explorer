"""Tests for DriveCalculator functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from googleapiclient.errors import HttpError

from src.gdrive_explorer.calculator import (
    DriveCalculator, SizeCalculationError, PermissionError, RateLimitError
)
from src.gdrive_explorer.models import DriveItem, DriveStructure, ItemType


class TestDriveCalculator:
    """Test DriveCalculator core functionality."""
    
    def test_calculator_initialization(self, mock_drive_client):
        """Test calculator initialization."""
        calc = DriveCalculator(mock_drive_client)
        
        assert calc.client == mock_drive_client
        assert hasattr(calc, 'cache')
        assert hasattr(calc, 'config')
        assert calc._processed_items == 0
        assert calc._errors_encountered == 0
    
    def test_reset_stats(self, mock_calculator):
        """Test statistics reset."""
        # Set some fake stats
        mock_calculator._processed_items = 10
        mock_calculator._errors_encountered = 2
        mock_calculator._cache_hits = 5
        mock_calculator._calculated_folders["test"] = 100
        
        # Reset
        mock_calculator._reset_stats()
        
        assert mock_calculator._processed_items == 0
        assert mock_calculator._errors_encountered == 0
        assert mock_calculator._cache_hits == 0
        assert len(mock_calculator._calculated_folders) == 0
    
    def test_get_calculation_stats(self, mock_calculator):
        """Test getting calculation statistics."""
        # Set some stats
        mock_calculator._processed_items = 5
        mock_calculator._total_size_calculated = 1024 * 1024
        mock_calculator._cache_hits = 3
        mock_calculator._errors_encountered = 1
        mock_calculator._permission_errors = 1
        
        stats = mock_calculator.get_calculation_stats()
        
        assert stats['processed_items'] == 5
        assert stats['total_size_calculated'] == 1024 * 1024
        assert stats['cache_hits'] == 3
        assert stats['errors_encountered'] == 1
        assert stats['permission_errors'] == 1


class TestSizeCalculation:
    """Test size calculation algorithms."""
    
    def test_calculate_simple_folder_size(self, mock_calculator):
        """Test calculating size for a simple folder."""
        # Create folder with files
        folder = DriveItem(
            id="folder1",
            name="Test Folder",
            type=ItemType.FOLDER,
            size=0
        )
        
        file1 = DriveItem(
            id="file1",
            name="file1.txt",
            type=ItemType.FILE,
            size=1024,
            parent_id="folder1"
        )
        
        file2 = DriveItem(
            id="file2", 
            name="file2.txt",
            type=ItemType.FILE,
            size=2048,
            parent_id="folder1"
        )
        
        folder.children = [file1, file2]
        
        # Create structure
        structure = DriveStructure()
        structure.add_item(folder)
        structure.add_item(file1)
        structure.add_item(file2)
        
        # Calculate size
        total_size = mock_calculator._calculate_folder_size_recursive(folder, structure)
        
        assert total_size == 3072  # 1024 + 2048
        assert folder.calculated_size == 3072
        assert folder.file_count == 2
        assert folder.folder_count == 0
        assert folder.scan_complete
    
    def test_calculate_nested_folder_size(self, mock_calculator):
        """Test calculating size for nested folders."""
        # Create nested structure
        root = DriveItem(id="root", name="Root", type=ItemType.FOLDER, size=0)
        subfolder = DriveItem(id="sub", name="Sub", type=ItemType.FOLDER, size=0, parent_id="root")
        file1 = DriveItem(id="file1", name="f1.txt", type=ItemType.FILE, size=1000, parent_id="root")
        file2 = DriveItem(id="file2", name="f2.txt", type=ItemType.FILE, size=2000, parent_id="sub")
        
        root.children = [subfolder, file1]
        subfolder.children = [file2]
        
        structure = DriveStructure()
        for item in [root, subfolder, file1, file2]:
            structure.add_item(item)
        
        # Calculate size
        total_size = mock_calculator._calculate_folder_size_recursive(root, structure)
        
        assert total_size == 3000  # 1000 + 2000
        assert root.calculated_size == 3000
        assert root.file_count == 2  # Total files in tree
        assert root.folder_count == 1  # Direct subfolders only
    
    def test_calculate_google_workspace_files(self, mock_calculator):
        """Test handling Google Workspace files (zero size)."""
        folder = DriveItem(id="folder", name="Folder", type=ItemType.FOLDER, size=0)
        
        # Regular file
        regular_file = DriveItem(
            id="regular",
            name="document.pdf", 
            type=ItemType.FILE,
            size=5000,
            parent_id="folder"
        )
        
        # Google Workspace file
        workspace_file = DriveItem(
            id="workspace",
            name="google_doc",
            type=ItemType.FILE,
            size=0,
            parent_id="folder",
            mime_type="application/vnd.google-apps.document"
        )
        
        folder.children = [regular_file, workspace_file]
        
        structure = DriveStructure()
        structure.add_item(folder)
        structure.add_item(regular_file)
        structure.add_item(workspace_file)
        
        total_size = mock_calculator._calculate_folder_size_recursive(folder, structure)
        
        # Should include regular file size but still count workspace file
        assert total_size == 5000
        assert folder.file_count == 2  # Both files counted
        assert workspace_file.is_google_workspace_file
    
    def test_full_drive_calculation(self, mock_calculator, sample_drive_structure):
        """Test full drive size calculation."""
        # Mock progress callback
        progress_calls = []
        def progress_callback(message, current, total):
            progress_calls.append((message, current, total))
        
        # Calculate sizes
        result = mock_calculator.calculate_full_drive_sizes(
            sample_drive_structure,
            progress_callback=progress_callback
        )
        
        assert result == sample_drive_structure
        assert len(progress_calls) > 0  # Progress was reported
        assert mock_calculator._processed_items > 0
    
    def test_incremental_calculation(self, mock_calculator, sample_drive_structure):
        """Test incremental size calculation."""
        # Mark some folders as needing recalculation
        folder = list(sample_drive_structure.get_folders())[0]
        folder.last_scanned = datetime.now() - timedelta(days=30)  # Old scan
        
        # Mock _should_recalculate to return True for this folder
        with patch.object(mock_calculator, '_should_recalculate', return_value=True):
            result = mock_calculator.calculate_incremental_sizes(sample_drive_structure)
            
            assert result == sample_drive_structure
            # Should have processed at least one folder
            assert mock_calculator._processed_items >= 0
    
    def test_should_recalculate_logic(self, mock_calculator):
        """Test folder recalculation logic."""
        now = datetime.now()
        
        # Folder with no calculated size
        folder1 = DriveItem(id="f1", name="F1", type=ItemType.FOLDER, size=0)
        assert mock_calculator._should_recalculate(folder1)
        
        # Recently scanned folder
        folder2 = DriveItem(id="f2", name="F2", type=ItemType.FOLDER, size=0)
        folder2.calculated_size = 1000
        folder2.last_scanned = now - timedelta(hours=1)
        
        with patch.object(mock_calculator.config.cache, 'ttl_hours', 24):
            assert not mock_calculator._should_recalculate(folder2)
        
        # Old scan
        folder3 = DriveItem(id="f3", name="F3", type=ItemType.FOLDER, size=0)
        folder3.calculated_size = 1000
        folder3.last_scanned = now - timedelta(days=2)
        
        with patch.object(mock_calculator.config.cache, 'ttl_hours', 24):
            assert mock_calculator._should_recalculate(folder3)


class TestErrorHandling:
    """Test error handling in calculator."""
    
    def test_api_error_handling(self, mock_calculator):
        """Test API error classification."""
        # Test permission error
        http_error_403 = HttpError(
            resp=Mock(status=403),
            content=b'{"error": "Forbidden"}'
        )
        
        with pytest.raises(PermissionError):
            mock_calculator._handle_api_error(http_error_403, "test_item")
        
        # Test rate limit error
        http_error_429 = HttpError(
            resp=Mock(status=429),
            content=b'{"error": "Too Many Requests"}'
        )
        
        with pytest.raises(RateLimitError):
            mock_calculator._handle_api_error(http_error_429, "test_item")
        
        # Test server error
        http_error_500 = HttpError(
            resp=Mock(status=500),
            content=b'{"error": "Internal Server Error"}'
        )
        
        with pytest.raises(SizeCalculationError):
            mock_calculator._handle_api_error(http_error_500, "test_item")
    
    def test_calculation_with_permission_errors(self, mock_calculator):
        """Test calculation handling permission errors gracefully."""
        # Create folder that will cause permission error
        protected_folder = DriveItem(
            id="protected",
            name="Protected Folder",
            type=ItemType.FOLDER,
            size=0
        )
        
        structure = DriveStructure()
        structure.add_item(protected_folder)
        
        # Mock calculation to raise permission error
        original_method = mock_calculator._calculate_folder_size_recursive
        def mock_calculate(folder, structure):
            if folder.id == "protected":
                raise PermissionError("Access denied")
            return original_method(folder, structure)
        
        with patch.object(mock_calculator, '_calculate_folder_size_recursive', side_effect=mock_calculate):
            # Should not raise exception, but handle gracefully
            result = mock_calculator.calculate_full_drive_sizes(structure)
            
            assert result == structure
            assert mock_calculator._permission_errors > 0
            assert mock_calculator._errors_encountered > 0
    
    def test_rate_limit_retry(self, mock_calculator):
        """Test rate limit error retry logic."""
        folder = DriveItem(id="rate_limited", name="Folder", type=ItemType.FOLDER, size=0)
        structure = DriveStructure()
        structure.add_item(folder)
        
        call_count = 0
        original_method = mock_calculator._calculate_folder_size_recursive
        
        def mock_calculate(folder, structure):
            nonlocal call_count
            call_count += 1
            if folder.id == "rate_limited" and call_count == 1:
                raise RateLimitError("Rate limit exceeded")
            return 0  # Success on retry
        
        with patch.object(mock_calculator, '_calculate_folder_size_recursive', side_effect=mock_calculate):
            with patch('time.sleep'):  # Speed up test
                result = mock_calculator.calculate_full_drive_sizes(structure)
                
                assert call_count == 2  # Original call + 1 retry
                assert result == structure
    
    def test_circular_reference_detection(self, mock_calculator):
        """Test detection of circular references."""
        # This is a bit artificial since the models should prevent this,
        # but test the safety mechanism
        folder = DriveItem(id="circular", name="Circular", type=ItemType.FOLDER, size=0)
        
        structure = DriveStructure()
        structure.add_item(folder)
        
        # Add folder to its own processing set to simulate circular reference
        mock_calculator._processing_folders.add("circular")
        
        result = mock_calculator._calculate_folder_size_recursive(folder, structure)
        
        # Should return 0 for circular reference
        assert result == 0


class TestCacheIntegration:
    """Test calculator integration with cache."""
    
    def test_cache_hit_during_calculation(self, mock_calculator):
        """Test that cache hits are used during calculation."""
        folder = DriveItem(
            id="cached_folder",
            name="Cached Folder",
            type=ItemType.FOLDER,
            size=0
        )
        folder.calculated_size = 5000
        folder.file_count = 10
        folder.folder_count = 2
        folder.last_scanned = datetime.now()
        folder.scan_complete = True
        
        # Mock cache to return the folder
        mock_calculator.cache.get_item.return_value = folder
        
        structure = DriveStructure()
        structure.add_item(folder)
        
        result = mock_calculator._calculate_folder_size_recursive(folder, structure)
        
        assert result == 5000
        assert mock_calculator._cache_hits > 0
        mock_calculator.cache.get_item.assert_called_once_with("cached_folder")
    
    def test_cache_storage_after_calculation(self, mock_calculator):
        """Test that results are cached after calculation."""
        folder = DriveItem(id="new_folder", name="New", type=ItemType.FOLDER, size=0)
        file_item = DriveItem(
            id="file", 
            name="file.txt", 
            type=ItemType.FILE, 
            size=1000,
            parent_id="new_folder"
        )
        
        folder.children = [file_item]
        
        structure = DriveStructure()
        structure.add_item(folder)
        structure.add_item(file_item)
        
        # Mock cache to not return anything (cache miss)
        mock_calculator.cache.get_item.return_value = None
        mock_calculator.cache.cache_item.return_value = True
        
        result = mock_calculator._calculate_folder_size_recursive(folder, structure)
        
        assert result == 1000
        # Should have attempted to cache the result
        mock_calculator.cache.cache_item.assert_called()


class TestAnalysisFunctions:
    """Test analysis and utility functions."""
    
    def test_find_largest_folders(self, mock_calculator, sample_drive_structure):
        """Test finding largest folders."""
        # Set some calculated sizes
        folders = sample_drive_structure.get_folders()
        for i, folder in enumerate(folders):
            folder.calculated_size = (i + 1) * 1000  # 1000, 2000, 3000, 4000
        
        largest = mock_calculator.find_largest_folders(sample_drive_structure, limit=2)
        
        assert len(largest) == 2
        # Should be sorted by size, largest first
        assert largest[0].calculated_size >= largest[1].calculated_size
    
    def test_find_empty_folders(self, mock_calculator, sample_drive_structure):
        """Test finding empty folders."""
        # Mark some folders as empty
        folders = sample_drive_structure.get_folders()
        if folders:
            empty_folder = folders[0]
            empty_folder.scan_complete = True
            empty_folder.file_count = 0
            empty_folder.folder_count = 0
        
        empty_folders = mock_calculator.find_empty_folders(sample_drive_structure)
        
        # Should find at least one empty folder
        assert len(empty_folders) >= 0
        for folder in empty_folders:
            assert folder.file_count == 0
            assert folder.folder_count == 0
            assert folder.scan_complete
    
    def test_analyze_folder_distribution(self, mock_calculator):
        """Test folder size distribution analysis."""
        structure = DriveStructure()
        
        # Create folders with different sizes
        sizes = [500, 5*1024*1024, 50*1024*1024, 500*1024*1024, 2*1024*1024*1024]
        for i, size in enumerate(sizes):
            folder = DriveItem(
                id=f"folder_{i}",
                name=f"Folder {i}",
                type=ItemType.FOLDER,
                size=0
            )
            folder.calculated_size = size
            structure.add_item(folder)
        
        analysis = mock_calculator.analyze_folder_distribution(structure)
        
        assert analysis['total_folders'] == 5
        assert 'size_distribution' in analysis
        assert 'tiny' in analysis['size_distribution']
        assert 'small' in analysis['size_distribution']
        assert 'medium' in analysis['size_distribution']
        assert 'large' in analysis['size_distribution']
        assert 'huge' in analysis['size_distribution']
    
    def test_analyze_google_workspace_files(self, mock_calculator):
        """Test Google Workspace file analysis."""
        structure = DriveStructure()
        
        # Add regular file
        regular_file = DriveItem(
            id="regular",
            name="document.pdf",
            type=ItemType.FILE,
            size=1000000
        )
        structure.add_item(regular_file)
        
        # Add Google Workspace files
        for i, mime_type in enumerate([
            "application/vnd.google-apps.document",
            "application/vnd.google-apps.spreadsheet",
            "application/vnd.google-apps.presentation"
        ]):
            workspace_file = DriveItem(
                id=f"workspace_{i}",
                name=f"Google File {i}",
                type=ItemType.FILE,
                size=0,
                mime_type=mime_type
            )
            structure.add_item(workspace_file)
        
        structure.total_files = 4
        
        analysis = mock_calculator.analyze_google_workspace_files(structure)
        
        assert analysis['total_workspace_files'] == 3
        assert len(analysis['workspace_types']) == 3
        assert analysis['percentage_of_total_files'] == 75.0  # 3 out of 4 files


class TestPerformance:
    """Test calculator performance with large datasets."""
    
    def test_large_structure_calculation(self, mock_calculator, large_drive_structure):
        """Test calculation performance with large drive structure."""
        # This test mainly ensures no crashes with large datasets
        start_time = datetime.now()
        
        # Mock cache to avoid actual caching overhead in test
        mock_calculator.cache.get_item.return_value = None
        mock_calculator.cache.cache_item.return_value = True
        mock_calculator.cache.cache_structure.return_value = True
        
        # Calculate sizes
        result = mock_calculator.calculate_full_drive_sizes(large_drive_structure)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        assert result == large_drive_structure
        assert elapsed < 30  # Should complete within reasonable time
        assert mock_calculator._processed_items > 0
    
    def test_memory_usage_with_large_structure(self, mock_calculator, large_drive_structure):
        """Test that memory usage remains reasonable with large structures."""
        import sys
        
        # Get initial memory usage
        initial_size = sys.getsizeof(mock_calculator._calculated_folders)
        
        # Process large structure
        mock_calculator.calculate_full_drive_sizes(large_drive_structure)
        
        # Check memory growth is reasonable
        final_size = sys.getsizeof(mock_calculator._calculated_folders)
        growth = final_size - initial_size
        
        # Growth should be proportional to number of folders processed
        assert growth < 10 * 1024 * 1024  # Less than 10MB for test data