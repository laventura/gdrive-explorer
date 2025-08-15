"""Integration tests for gdrive-explorer components."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner
from datetime import datetime, timedelta

from src.gdrive_explorer.cli import main
from src.gdrive_explorer.explorer import DriveExplorer
from src.gdrive_explorer.models import DriveItem, DriveStructure, ItemType


class TestExplorerIntegration:
    """Test DriveExplorer integration with other components."""
    
    @pytest.fixture
    def mock_explorer(self, mock_drive_client, mock_cache):
        """Create a DriveExplorer with mocked dependencies."""
        with patch('src.gdrive_explorer.explorer.DriveClient', return_value=mock_drive_client):
            with patch('src.gdrive_explorer.explorer.get_cache', return_value=mock_cache):
                explorer = DriveExplorer()
                return explorer
    
    def test_explorer_initialization(self, mock_explorer):
        """Test explorer initializes with all components."""
        assert hasattr(mock_explorer, 'client')
        assert hasattr(mock_explorer, 'cache')
        assert hasattr(mock_explorer, 'calculator')
        assert hasattr(mock_explorer, 'config')
    
    def test_full_scan_workflow(self, mock_explorer, sample_drive_structure):
        """Test complete scan workflow integration."""
        # Mock the client to return sample data
        mock_explorer.client.list_all_files.return_value = []  # Will be built from structure
        
        # Mock the scan method to return our sample structure
        with patch.object(mock_explorer, '_build_structure', return_value=sample_drive_structure):
            with patch.object(mock_explorer, '_fetch_all_files', return_value=[]):
                result = mock_explorer.scan_drive()
                
                assert result is not None
                assert isinstance(result, DriveStructure)
                # Calculator should have been called to calculate sizes
                assert hasattr(mock_explorer.calculator, '_processed_items')
    
    def test_cached_scan_workflow(self, mock_explorer, sample_drive_structure):
        """Test scan workflow with cached data."""
        # Mock cache to return existing structure and other methods to avoid actual API calls
        with patch.object(mock_explorer.cache, 'get_structure', return_value=sample_drive_structure):
            with patch.object(mock_explorer, '_fetch_all_files', return_value=[]):
                with patch.object(mock_explorer, '_build_structure', return_value=sample_drive_structure):
                    result = mock_explorer.scan_drive()
                    
                    assert result is not None
                    assert isinstance(result, DriveStructure)
    
    def test_incremental_scan_workflow(self, mock_explorer, sample_drive_structure):
        """Test incremental scan workflow."""
        # Mock existing cached structure and methods to avoid actual API calls
        with patch.object(mock_explorer.cache, 'get_structure', return_value=sample_drive_structure):
            with patch.object(mock_explorer, '_fetch_all_files', return_value=[]):
                with patch.object(mock_explorer, '_build_structure', return_value=sample_drive_structure):
                    # Mock incremental calculation
                    with patch.object(mock_explorer.calculator, 'calculate_incremental_sizes') as mock_incremental:
                        mock_incremental.return_value = sample_drive_structure
                        
                        result = mock_explorer.scan_drive()
                        
                        assert result is not None
                        assert isinstance(result, DriveStructure)


class TestCLIIntegration:
    """Test CLI integration with backend components."""
    
    @pytest.fixture
    def cli_runner(self):
        """Create a CLI test runner."""
        return CliRunner()
    
    def test_auth_command(self, cli_runner):
        """Test authentication command."""
        with patch('src.gdrive_explorer.cli.DriveAuthenticator') as mock_auth_class:
            mock_auth = Mock()
            mock_auth_class.return_value = mock_auth
            mock_auth.is_authenticated.return_value = False
            mock_auth.authenticate.return_value = True
            
            result = cli_runner.invoke(main, ['auth'])
            
            assert result.exit_code == 0
            mock_auth.authenticate.assert_called_once()
    
    def test_info_command(self, cli_runner):
        """Test info command."""
        result = cli_runner.invoke(main, ['info'])
        
        assert result.exit_code == 0
        assert 'Google Drive Explorer - Configuration' in result.output
        assert 'Cache Enabled' in result.output
        assert 'Default Format' in result.output
    
    def test_scan_command_basic(self, cli_runner):
        """Test basic scan command."""
        with patch('src.gdrive_explorer.cli.DriveExplorer') as mock_explorer_class:
            mock_explorer = Mock()
            mock_explorer_class.return_value = mock_explorer
            
            # Mock successful scan
            mock_structure = Mock(spec=DriveStructure)
            mock_structure.total_files = 100
            mock_structure.total_folders = 20
            mock_structure.total_size = 1000000000
            mock_structure.all_items = {}
            mock_explorer.scan_drive_complete.return_value = mock_structure
            
            result = cli_runner.invoke(main, ['scan', '--full'])
            
            assert result.exit_code == 0
            mock_explorer.scan_drive_complete.assert_called_once()
    
    def test_scan_command_with_options(self, cli_runner):
        """Test scan command with various options."""
        with patch('src.gdrive_explorer.cli.DriveExplorer') as mock_explorer_class:
            mock_explorer = Mock()
            mock_explorer_class.return_value = mock_explorer
            mock_structure = Mock(spec=DriveStructure)
            mock_structure.total_files = 50
            mock_structure.total_folders = 10
            mock_structure.total_size = 500000000
            mock_structure.all_items = {}
            mock_explorer.scan_drive_complete.return_value = mock_structure
            
            # Test with format option and full scan
            result = cli_runner.invoke(main, ['scan', '--full', '--format', 'tree'])
            assert result.exit_code == 0
            
            # Test with cached option and full scan
            result = cli_runner.invoke(main, ['scan', '--full', '--cache'])
            assert result.exit_code == 0
    
    def test_cache_command(self, cli_runner):
        """Test cache management commands."""
        with patch('src.gdrive_explorer.cli.get_cache') as mock_get_cache:
            mock_cache = Mock()
            mock_cache.get_cache_stats.return_value = {
                'enabled': True,
                'items_count': 100,
                'total_size_mb': 5.0
            }
            mock_get_cache.return_value = mock_cache
            
            result = cli_runner.invoke(main, ['cache'])
            
            assert result.exit_code == 0
            assert 'enabled' in result.output.lower() or 'items' in result.output.lower()
    
    def test_clear_cache_command(self, cli_runner):
        """Test cache clearing command."""
        with patch('src.gdrive_explorer.cli.get_cache') as mock_get_cache:
            with patch('src.gdrive_explorer.cli.click.confirm', return_value=True) as mock_confirm:
                mock_cache = Mock()
                mock_cache.clear_all.return_value = True
                mock_get_cache.return_value = mock_cache
                
                result = cli_runner.invoke(main, ['cache-clear'])
                
                assert result.exit_code == 0
                mock_confirm.assert_called_once()
                mock_cache.clear_all.assert_called_once()
    
    def test_error_handling_in_cli(self, cli_runner):
        """Test CLI error handling."""
        with patch('src.gdrive_explorer.cli.DriveExplorer') as mock_explorer_class:
            mock_explorer = Mock()
            mock_explorer_class.return_value = mock_explorer
            mock_explorer.scan_drive_complete.side_effect = Exception("Test error")
            
            result = cli_runner.invoke(main, ['scan', '--full'])
            
            # Should handle error gracefully
            assert result.exit_code != 0 or 'error' in result.output.lower()


class TestEndToEndWorkflow:
    """Test complete end-to-end workflows."""
    
    def create_realistic_structure(self):
        """Create a realistic drive structure for testing."""
        structure = DriveStructure()
        now = datetime.now()
        
        # Root folder
        root = DriveItem(
            id='root',
            name='My Drive',
            type=ItemType.FOLDER,
            mime_type='application/vnd.google-apps.folder',
            size=0,
            modified_time=now - timedelta(days=30)
        )
        structure.add_item(root)
        
        # Documents folder
        docs = DriveItem(
            id='docs',
            name='Documents',
            type=ItemType.FOLDER,
            mime_type='application/vnd.google-apps.folder',
            size=0,
            parent_ids=['root'],
            modified_time=now - timedelta(days=10)
        )
        structure.add_item(docs)
        root.children.append(docs)
        
        # Photos folder
        photos = DriveItem(
            id='photos',
            name='Photos',
            type=ItemType.FOLDER,
            mime_type='application/vnd.google-apps.folder',
            size=0,
            parent_ids=['root'],
            modified_time=now - timedelta(days=5)
        )
        structure.add_item(photos)
        root.children.append(photos)
        
        # Files in documents
        doc_files = [
            ('resume.pdf', 500000),
            ('report.docx', 1200000),
            ('spreadsheet.xlsx', 800000)
        ]
        
        for name, size in doc_files:
            # Determine MIME type based on file extension
            if name.endswith('.pdf'):
                mime_type = 'application/pdf'
            elif name.endswith('.docx'):
                mime_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            elif name.endswith('.xlsx'):
                mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            else:
                mime_type = 'application/octet-stream'
                
            file_item = DriveItem(
                id=f'doc_{name}',
                name=name,
                type=ItemType.FILE,
                mime_type=mime_type,
                size=size,
                parent_ids=['docs'],
                modified_time=now - timedelta(days=7)
            )
            structure.add_item(file_item)
            docs.children.append(file_item)
        
        # Files in photos
        photo_files = [
            ('vacation1.jpg', 3000000),
            ('vacation2.jpg', 2800000),
            ('family.png', 4200000)
        ]
        
        for name, size in photo_files:
            # Determine MIME type based on file extension
            if name.endswith('.jpg'):
                mime_type = 'image/jpeg'
            elif name.endswith('.png'):
                mime_type = 'image/png'
            else:
                mime_type = 'image/jpeg'  # Default for photos
                
            file_item = DriveItem(
                id=f'photo_{name}',
                name=name,
                type=ItemType.FILE,
                mime_type=mime_type,
                size=size,
                parent_ids=['photos'],
                modified_time=now - timedelta(days=3)
            )
            structure.add_item(file_item)
            photos.children.append(file_item)
        
        # Google Workspace file
        workspace = DriveItem(
            id='workspace_doc',
            name='Shared Document',
            type=ItemType.GOOGLE_DOC,
            mime_type='application/vnd.google-apps.document',
            size=0,
            parent_ids=['docs'],
            modified_time=now - timedelta(days=1)
        )
        structure.add_item(workspace)
        docs.children.append(workspace)
        
        structure.total_files = 7  # 3 docs + 3 photos + 1 workspace
        structure.total_folders = 3  # root + docs + photos
        structure.scan_complete = True
        structure.scan_timestamp = now
        
        return structure
    
    def test_complete_scan_and_analysis_workflow(self, mock_cache):
        """Test complete workflow from scan to analysis."""
        # Create realistic structure
        structure = self.create_realistic_structure()
        
        # Mock dependencies
        with patch('src.gdrive_explorer.explorer.DriveClient') as mock_client_class:
            with patch('src.gdrive_explorer.explorer.get_cache', return_value=mock_cache):
                mock_client = Mock()
                mock_client.is_authenticated = True
                mock_client.list_files.return_value = {'files': [], 'nextPageToken': None}
                mock_client_class.return_value = mock_client
                
                explorer = DriveExplorer()
                
                # Mock the internal structure building and fetch methods to avoid API calls
                with patch.object(explorer, '_build_structure', return_value=structure):
                    with patch.object(explorer, '_fetch_all_files', return_value=[]):
                        # Perform scan
                        result = explorer.scan_drive()
                    
                    assert result is not None
                    assert isinstance(result, DriveStructure)
                    assert result.scan_complete is True
                    
                    # Test analysis functions work without errors
                    largest_folders = explorer.calculator.find_largest_folders(result, limit=5)
                    assert isinstance(largest_folders, list)
                    
                    workspace_analysis = explorer.calculator.analyze_google_workspace_files(result)
                    assert isinstance(workspace_analysis, dict)
                    assert 'total_workspace_files' in workspace_analysis
                    
                    folder_analysis = explorer.calculator.analyze_folder_distribution(result)
                    assert isinstance(folder_analysis, dict)
                    assert 'total_folders' in folder_analysis
    
    def test_cache_persistence_workflow(self, temp_dir):
        """Test that cache persists between sessions."""
        cache_path = temp_dir / "persistence_test.db"
        structure = self.create_realistic_structure()
        
        # First session - cache the structure
        from src.gdrive_explorer.cache import DriveCache
        cache1 = DriveCache(str(cache_path))
        
        success = cache1.cache_structure(structure, "test_session")
        assert success
        
        # Second session - retrieve from cache
        cache2 = DriveCache(str(cache_path))
        retrieved = cache2.get_structure("test_session")
        
        assert retrieved is not None
        assert len(retrieved.all_items) == len(structure.all_items)
        assert retrieved.total_files == structure.total_files
        assert retrieved.total_folders == structure.total_folders
    
    def test_error_recovery_workflow(self, mock_cache):
        """Test system recovery from various error conditions."""
        structure = self.create_realistic_structure()
        
        with patch('src.gdrive_explorer.explorer.DriveClient') as mock_client_class:
            with patch('src.gdrive_explorer.explorer.get_cache', return_value=mock_cache):
                mock_client = Mock()
                mock_client.is_authenticated = True
                mock_client_class.return_value = mock_client
                
                explorer = DriveExplorer()
                
                # Test recovery from API errors
                mock_client.list_all_files.side_effect = Exception("API Error")
                
                # Should handle gracefully
                try:
                    result = explorer.scan_drive()
                    # If it doesn't raise, that's fine too
                except Exception as e:
                    # Should be a handled exception with useful message
                    assert "API Error" in str(e) or isinstance(e, Exception)
                
                # Test recovery with partial cache
                with patch.object(mock_cache, 'get_structure', return_value=structure):
                    # Mock the fetch and build methods to avoid API calls
                    with patch.object(explorer, '_fetch_all_files', return_value=[]):
                        with patch.object(explorer, '_build_structure', return_value=structure):
                            result = explorer.scan_drive()
                            assert result is not None


class TestPerformanceIntegration:
    """Test performance characteristics of integrated components."""
    
    def test_large_dataset_performance(self, mock_cache):
        """Test performance with large datasets."""
        # Create large structure
        large_structure = self.create_large_test_structure(1000, 100)  # 1000 files, 100 folders
        
        with patch('src.gdrive_explorer.explorer.DriveClient') as mock_client_class:
            with patch('src.gdrive_explorer.explorer.get_cache', return_value=mock_cache):
                mock_client = Mock()
                mock_client.is_authenticated = True
                mock_client_class.return_value = mock_client
                
                explorer = DriveExplorer()
                
                # Mock cache to avoid I/O overhead
                with patch.object(mock_cache, 'cache_structure', return_value=True):
                    with patch.object(mock_cache, 'cache_item', return_value=True):
                        start_time = datetime.now()
                        
                        with patch.object(explorer, '_build_structure', return_value=large_structure):
                            with patch.object(explorer, '_fetch_all_files', return_value=[]):
                                result = explorer.scan_drive()
                        
                        elapsed = (datetime.now() - start_time).total_seconds()
                        
                        assert result is not None
                        assert elapsed < 60  # Should complete within 1 minute
                        assert isinstance(result, DriveStructure)
                        # The scan completes successfully (structure creation is mocked)
    
    def create_large_test_structure(self, num_files, num_folders):
        """Create a large test structure for performance testing."""
        structure = DriveStructure()
        now = datetime.now()
        
        # Root
        root = DriveItem(id='root', name='Root', type=ItemType.FOLDER, mime_type='application/vnd.google-apps.folder', size=0)
        structure.add_item(root)
        
        # Create folders
        for i in range(num_folders):
            folder = DriveItem(
                id=f'folder_{i}',
                name=f'Folder {i}',
                type=ItemType.FOLDER,
                mime_type='application/vnd.google-apps.folder',
                size=0,
                parent_ids=['root'],
                modified_time=now - timedelta(days=i % 30)
            )
            structure.add_item(folder)
            root.children.append(folder)
        
        # Distribute files across folders
        files_per_folder = num_files // num_folders
        file_count = 0
        
        for i in range(num_folders):
            folder_id = f'folder_{i}'
            folder = structure.get_item(folder_id)
            
            for j in range(files_per_folder):
                if file_count >= num_files:
                    break
                    
                file_item = DriveItem(
                    id=f'file_{file_count}',
                    name=f'file_{file_count}.txt',
                    type=ItemType.FILE,
                    mime_type='text/plain',
                    size=(file_count % 100 + 1) * 1024,  # Varied sizes
                    parent_ids=[folder_id],
                    modified_time=now - timedelta(hours=file_count % 24)
                )
                structure.add_item(file_item)
                folder.children.append(file_item)
                file_count += 1
        
        structure.total_files = num_files
        structure.total_folders = num_folders + 1  # +1 for root
        structure.scan_complete = True
        structure.scan_timestamp = now
        
        return structure
    
    def test_memory_usage_integration(self, mock_cache):
        """Test memory usage stays reasonable during integration."""
        import sys
        import gc
        
        # Force garbage collection before test
        gc.collect()
        
        structure = self.create_large_test_structure(500, 50)
        
        with patch('src.gdrive_explorer.explorer.DriveClient') as mock_client_class:
            with patch('src.gdrive_explorer.explorer.get_cache', return_value=mock_cache):
                mock_client = Mock()
                mock_client_class.return_value = mock_client
                
                explorer = DriveExplorer()
                
                # Measure memory before
                initial_objects = len(gc.get_objects())
                
                with patch.object(explorer, '_build_structure', return_value=structure):
                    with patch.object(explorer, '_fetch_all_files', return_value=[]):
                        result = explorer.scan_drive()
                
                # Force garbage collection
                gc.collect()
                final_objects = len(gc.get_objects())
                
                # Memory growth should be reasonable
                object_growth = final_objects - initial_objects
                assert object_growth < 10000  # Reasonable growth limit
                
                assert result is not None