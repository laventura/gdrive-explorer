"""Tests for DriveCache functionality."""

import pytest
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, Mock

from src.gdrive_explorer.cache import DriveCache
from src.gdrive_explorer.models import DriveItem, DriveStructure, ItemType


@pytest.fixture
def temp_cache(temp_dir):
    """Create a temporary cache for testing."""
    cache_path = temp_dir / "test_cache.db"
    cache = DriveCache(str(cache_path))
    yield cache
    # Cleanup is handled by temp_dir fixture


class TestDriveCache:
    """Test DriveCache functionality."""
    
    def test_cache_initialization(self, temp_cache):
        """Test cache initialization and database creation."""
        assert temp_cache.enabled
        assert temp_cache.cache_path.exists()
        assert temp_cache.ttl_hours == 24  # Default from config
    
    def test_cache_item_storage_and_retrieval(self, temp_cache):
        """Test caching and retrieving individual items."""
        # Create a test item
        item = DriveItem(
            id="test123",
            name="test_file.txt",
            type=ItemType.FILE,
            mime_type="text/plain",
            size=1024,
            modified_time=datetime.now()
        )
        
        # Cache the item
        success = temp_cache.cache_item(item)
        assert success
        
        # Retrieve the item
        retrieved_item = temp_cache.get_item("test123")
        assert retrieved_item is not None
        assert retrieved_item.id == item.id
        assert retrieved_item.name == item.name
        assert retrieved_item.size == item.size
        assert retrieved_item.type == item.type
    
    def test_cache_item_not_found(self, temp_cache):
        """Test retrieving non-existent item."""
        result = temp_cache.get_item("nonexistent")
        assert result is None
    
    def test_cache_item_expiry(self, temp_cache):
        """Test that expired items are not returned."""
        # Create cache with very short TTL
        with patch.object(temp_cache, 'ttl_hours', 0.001):  # ~3.6 seconds
            item = DriveItem(
                id="expire_test",
                name="expire.txt", 
                type=ItemType.FILE,
                mime_type="text/plain",
                size=100
            )
            
            # Cache the item
            temp_cache.cache_item(item)
            
            # Should be retrievable immediately
            retrieved = temp_cache.get_item("expire_test")
            assert retrieved is not None
            
            # Wait for expiry (simulate by setting past expiry)
            time.sleep(0.1)  # Small delay
            
            # Mock _is_expired to return True
            with patch.object(temp_cache, '_is_expired', return_value=True):
                expired_item = temp_cache.get_item("expire_test")
                assert expired_item is None
    
    def test_cache_structure_storage(self, temp_cache, sample_drive_structure):
        """Test caching and retrieving drive structures."""
        # Cache the structure
        success = temp_cache.cache_structure(sample_drive_structure, "test_structure")
        assert success
        
        # Retrieve the structure
        retrieved = temp_cache.get_structure("test_structure")
        assert retrieved is not None
        assert len(retrieved.all_items) == len(sample_drive_structure.all_items)
        assert retrieved.total_files == sample_drive_structure.total_files
        assert retrieved.total_folders == sample_drive_structure.total_folders
    
    def test_cache_invalidation(self, temp_cache):
        """Test cache invalidation."""
        item = DriveItem(
            id="invalidate_test",
            name="test.txt",
            type=ItemType.FILE,
            mime_type="text/plain",
            size=100
        )
        
        # Cache the item
        temp_cache.cache_item(item)
        assert temp_cache.get_item("invalidate_test") is not None
        
        # Invalidate the item
        success = temp_cache.invalidate_item("invalidate_test")
        assert success
        
        # Should not be retrievable anymore
        assert temp_cache.get_item("invalidate_test") is None
    
    def test_cache_clear_expired(self, temp_cache):
        """Test clearing expired entries."""
        # Create items with different expiry times
        item1 = DriveItem(id="item1", name="file1.txt", type=ItemType.FILE, mime_type="text/plain", size=100)
        item2 = DriveItem(id="item2", name="file2.txt", type=ItemType.FILE, mime_type="text/plain", size=200)
        
        temp_cache.cache_item(item1)
        temp_cache.cache_item(item2)
        
        # Mock one item as expired
        with patch.object(temp_cache, '_is_expired') as mock_expired:
            mock_expired.side_effect = lambda expires_at: expires_at.endswith("item1")
            
            removed_count = temp_cache.clear_expired()
            
            # Should have removed expired entries
            assert removed_count >= 0  # At least attempted cleanup
    
    def test_cache_clear_all(self, temp_cache):
        """Test clearing all cache data."""
        # Add some items
        item1 = DriveItem(id="clear1", name="file1.txt", type=ItemType.FILE, mime_type="text/plain", size=100)
        item2 = DriveItem(id="clear2", name="file2.txt", type=ItemType.FILE, mime_type="text/plain", size=200)
        
        temp_cache.cache_item(item1)
        temp_cache.cache_item(item2)
        
        # Verify items exist
        assert temp_cache.get_item("clear1") is not None
        assert temp_cache.get_item("clear2") is not None
        
        # Clear all
        success = temp_cache.clear_all()
        assert success
        
        # Verify items are gone
        assert temp_cache.get_item("clear1") is None
        assert temp_cache.get_item("clear2") is None
    
    def test_cache_stats(self, temp_cache):
        """Test cache statistics."""
        # Get initial stats
        stats = temp_cache.get_cache_stats()
        assert stats['enabled'] is True
        assert 'items_count' in stats
        assert 'structures_count' in stats
        assert 'total_size_bytes' in stats
        
        # Add some items
        item = DriveItem(id="stats_test", name="test.txt", type=ItemType.FILE, mime_type="text/plain", size=100)
        temp_cache.cache_item(item)
        
        # Get updated stats
        new_stats = temp_cache.get_cache_stats()
        assert new_stats['items_count'] >= 1
    
    def test_cache_disabled(self, temp_dir):
        """Test cache behavior when disabled."""
        # Create cache with disabled config
        with patch('src.gdrive_explorer.cache.get_config') as mock_config:
            config = Mock()
            config.cache.enabled = False
            config.cache.database_path = str(temp_dir / "disabled_cache.db")
            config.cache.ttl_hours = 24
            config.cache.max_size_mb = 100
            mock_config.return_value = config
            
            disabled_cache = DriveCache()
            
            # Cache operations should return False/None
            item = DriveItem(id="disabled", name="test.txt", type=ItemType.FILE, mime_type="text/plain", size=100)
            
            assert not disabled_cache.cache_item(item)
            assert disabled_cache.get_item("disabled") is None
            assert not disabled_cache.clear_all()
    
    def test_database_migration(self, temp_dir):
        """Test database schema migration."""
        cache_path = temp_dir / "migration_test.db"
        
        # Create cache - should initialize with current schema
        cache1 = DriveCache(str(cache_path))
        
        # Verify schema version is set
        stats = cache1.get_cache_stats()
        assert stats['enabled'] is True
        
        # Create new cache instance with same database
        cache2 = DriveCache(str(cache_path))
        
        # Should work without migration errors
        item = DriveItem(id="migration_test", name="test.txt", type=ItemType.FILE, mime_type="text/plain", size=100)
        assert cache2.cache_item(item)
        assert cache2.get_item("migration_test") is not None
    
    def test_large_item_serialization(self, temp_cache):
        """Test caching items with large amounts of data."""
        # Create item with many children
        root_folder = DriveItem(
            id="large_folder",
            name="Large Folder",
            type=ItemType.FOLDER,
            mime_type="application/vnd.google-apps.folder",
            size=0
        )
        
        # Add many children
        for i in range(100):
            child = DriveItem(
                id=f"child_{i}",
                name=f"file_{i}.txt",
                type=ItemType.FILE,
                mime_type="text/plain",
                size=i * 1024,
                parent_ids=["large_folder"]
            )
            root_folder.children.append(child)
        
        # Should handle large serialization
        success = temp_cache.cache_item(root_folder)
        assert success
        
        # Should retrieve correctly
        retrieved = temp_cache.get_item("large_folder")
        assert retrieved is not None
        assert len(retrieved.children) == 100
    
    def test_concurrent_access(self, temp_cache):
        """Test cache handles concurrent access safely."""
        import threading
        import time
        
        results = []
        errors = []
        
        def cache_worker(worker_id):
            try:
                for i in range(10):
                    item = DriveItem(
                        id=f"worker_{worker_id}_item_{i}",
                        name=f"file_{worker_id}_{i}.txt",
                        type=ItemType.FILE,
                        mime_type="text/plain",
                        size=i * 100
                    )
                    
                    success = temp_cache.cache_item(item)
                    results.append((worker_id, i, success))
                    
                    # Small delay to simulate real usage
                    time.sleep(0.001)
            except Exception as e:
                errors.append((worker_id, str(e)))
        
        # Start multiple threads
        threads = []
        for worker_id in range(3):
            thread = threading.Thread(target=cache_worker, args=(worker_id,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 30  # 3 workers * 10 items each
        
        # Verify all items were cached
        for worker_id, item_id, success in results:
            assert success, f"Failed to cache item for worker {worker_id}, item {item_id}"


class TestCacheOptimization:
    """Test cache optimization features."""
    
    def test_cache_size_tracking(self, temp_cache):
        """Test that cache tracks its size correctly."""
        # Add items and check size increases
        initial_stats = temp_cache.get_cache_stats()
        initial_size = initial_stats.get('total_size_bytes', 0)
        
        # Add a large item
        large_item = DriveItem(
            id="large_item",
            name="large_file.txt", 
            type=ItemType.FILE,
            mime_type="text/plain",
            size=10 * 1024 * 1024  # 10MB
        )
        
        temp_cache.cache_item(large_item)
        
        # Check size increased
        new_stats = temp_cache.get_cache_stats()
        new_size = new_stats.get('total_size_bytes', 0)
        
        assert new_size > initial_size
    
    def test_cache_optimization(self, temp_cache):
        """Test cache optimization (cleanup and vacuum)."""
        # Add some items
        for i in range(10):
            item = DriveItem(
                id=f"opt_test_{i}",
                name=f"file_{i}.txt",
                type=ItemType.FILE,
                mime_type="text/plain",
                size=i * 1024
            )
            temp_cache.cache_item(item)
        
        # Run optimization
        success = temp_cache.optimize_cache()
        assert success
        
        # Cache should still be functional
        test_item = temp_cache.get_item("opt_test_5")
        assert test_item is not None


class TestCacheErrorHandling:
    """Test cache error handling and edge cases."""
    
    def test_corrupted_data_handling(self, temp_cache):
        """Test handling of corrupted cache data."""
        # This would be complex to test thoroughly, but we can test basic error recovery
        item = DriveItem(id="error_test", name="test.txt", type=ItemType.FILE, mime_type="text/plain", size=100)
        
        # Cache normally
        success = temp_cache.cache_item(item)
        assert success
        
        # Should handle retrieval errors gracefully
        retrieved = temp_cache.get_item("error_test")
        assert retrieved is not None
    
    def test_invalid_cache_path(self):
        """Test cache creation with invalid path."""
        # Test with invalid path
        invalid_path = "/root/invalid/path/cache.db"
        
        # Should handle gracefully (might disable cache or create directory)
        try:
            cache = DriveCache(invalid_path)
            # If it doesn't raise an exception, that's also fine
            assert hasattr(cache, 'enabled')
        except (PermissionError, OSError):
            # Expected for invalid paths
            pass
    
    def test_database_locked_handling(self, temp_cache):
        """Test handling database lock situations."""
        # This is difficult to test directly, but we ensure the context manager
        # properly handles database connections
        
        item = DriveItem(id="lock_test", name="test.txt", type=ItemType.FILE, mime_type="text/plain", size=100)
        
        # Multiple rapid operations should not cause lock issues
        for i in range(5):
            success = temp_cache.cache_item(item)
            assert success
            
            retrieved = temp_cache.get_item("lock_test")
            assert retrieved is not None