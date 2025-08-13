"""Caching system for Google Drive Explorer using SQLite."""

import sqlite3
import json
import pickle
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from contextlib import contextmanager

from .models import DriveItem, DriveStructure
from .config import get_config
from .utils import ensure_directory_exists


logger = logging.getLogger(__name__)


class DriveCache:
    """SQLite-based cache for Google Drive data."""
    
    def __init__(self, cache_path: Optional[str] = None):
        """Initialize the cache.
        
        Args:
            cache_path: Path to SQLite database file
        """
        config = get_config()
        
        if cache_path is None:
            cache_path = config.cache.database_path
        
        self.cache_path = Path(cache_path)
        self.ttl_hours = config.cache.ttl_hours
        self.max_size_mb = config.cache.max_size_mb
        self.enabled = config.cache.enabled
        
        if self.enabled:
            self._init_database()
    
    def _init_database(self) -> None:
        """Initialize the SQLite database and create tables."""
        # Ensure cache directory exists
        ensure_directory_exists(self.cache_path.parent)
        
        with self._get_connection() as conn:
            # Create tables
            conn.execute('''
                CREATE TABLE IF NOT EXISTS drive_items (
                    id TEXT PRIMARY KEY,
                    data BLOB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    size_bytes INTEGER DEFAULT 0
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS drive_structures (
                    id TEXT PRIMARY KEY,
                    data BLOB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    size_bytes INTEGER DEFAULT 0
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes for performance
            conn.execute('CREATE INDEX IF NOT EXISTS idx_drive_items_expires ON drive_items(expires_at)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_structures_expires ON drive_structures(expires_at)')
            
            conn.commit()
            
        logger.debug(f"Cache database initialized: {self.cache_path}")
    
    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper error handling."""
        conn = None
        try:
            conn = sqlite3.connect(
                self.cache_path, 
                timeout=30.0,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            yield conn
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def _serialize_item(self, item: DriveItem) -> bytes:
        """Serialize a DriveItem for storage."""
        try:
            # Use pickle for efficient serialization
            return pickle.dumps(item.dict())
        except Exception as e:
            logger.error(f"Error serializing item {item.id}: {e}")
            raise
    
    def _deserialize_item(self, data: bytes) -> DriveItem:
        """Deserialize a DriveItem from storage."""
        try:
            item_dict = pickle.loads(data)
            return DriveItem(**item_dict)
        except Exception as e:
            logger.error(f"Error deserializing item: {e}")
            raise
    
    def _serialize_structure(self, structure: DriveStructure) -> bytes:
        """Serialize a DriveStructure for storage."""
        try:
            return pickle.dumps(structure.dict())
        except Exception as e:
            logger.error(f"Error serializing structure: {e}")
            raise
    
    def _deserialize_structure(self, data: bytes) -> DriveStructure:
        """Deserialize a DriveStructure from storage."""
        try:
            structure_dict = pickle.loads(data)
            return DriveStructure(**structure_dict)
        except Exception as e:
            logger.error(f"Error deserializing structure: {e}")
            raise
    
    def _calculate_expiry(self) -> datetime:
        """Calculate expiry time based on TTL."""
        return datetime.now() + timedelta(hours=self.ttl_hours)
    
    def _is_expired(self, expires_at: str) -> bool:
        """Check if cache entry is expired."""
        try:
            expiry = datetime.fromisoformat(expires_at)
            return datetime.now() > expiry
        except ValueError:
            return True
    
    def cache_item(self, item: DriveItem) -> bool:
        """Cache a DriveItem.
        
        Args:
            item: DriveItem to cache
            
        Returns:
            True if successfully cached
        """
        if not self.enabled:
            return False
        
        try:
            data = self._serialize_item(item)
            expires_at = self._calculate_expiry()
            
            with self._get_connection() as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO drive_items 
                    (id, data, updated_at, expires_at, size_bytes)
                    VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?)
                ''', (item.id, data, expires_at.isoformat(), len(data)))
                
                conn.commit()
                
            logger.debug(f"Cached item: {item.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error caching item {item.id}: {e}")
            return False
    
    def get_item(self, item_id: str) -> Optional[DriveItem]:
        """Retrieve a cached DriveItem.
        
        Args:
            item_id: Google Drive item ID
            
        Returns:
            Cached DriveItem or None if not found/expired
        """
        if not self.enabled:
            return None
        
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    'SELECT data, expires_at FROM drive_items WHERE id = ?',
                    (item_id,)
                )
                row = cursor.fetchone()
                
                if row is None:
                    return None
                
                if self._is_expired(row['expires_at']):
                    # Remove expired entry
                    conn.execute('DELETE FROM drive_items WHERE id = ?', (item_id,))
                    conn.commit()
                    return None
                
                return self._deserialize_item(row['data'])
                
        except Exception as e:
            logger.error(f"Error retrieving cached item {item_id}: {e}")
            return None
    
    def cache_structure(self, structure: DriveStructure, structure_id: str = "full_drive") -> bool:
        """Cache a complete DriveStructure.
        
        Args:
            structure: DriveStructure to cache
            structure_id: Unique ID for this structure
            
        Returns:
            True if successfully cached
        """
        if not self.enabled:
            return False
        
        try:
            data = self._serialize_structure(structure)
            expires_at = self._calculate_expiry()
            
            with self._get_connection() as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO drive_structures 
                    (id, data, updated_at, expires_at, size_bytes)
                    VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?)
                ''', (structure_id, data, expires_at.isoformat(), len(data)))
                
                conn.commit()
                
            logger.info(f"Cached drive structure: {structure_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error caching structure {structure_id}: {e}")
            return False
    
    def get_structure(self, structure_id: str = "full_drive") -> Optional[DriveStructure]:
        """Retrieve a cached DriveStructure.
        
        Args:
            structure_id: Unique ID for the structure
            
        Returns:
            Cached DriveStructure or None if not found/expired
        """
        if not self.enabled:
            return None
        
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    'SELECT data, expires_at FROM drive_structures WHERE id = ?',
                    (structure_id,)
                )
                row = cursor.fetchone()
                
                if row is None:
                    return None
                
                if self._is_expired(row['expires_at']):
                    # Remove expired entry
                    conn.execute('DELETE FROM drive_structures WHERE id = ?', (structure_id,))
                    conn.commit()
                    return None
                
                return self._deserialize_structure(row['data'])
                
        except Exception as e:
            logger.error(f"Error retrieving cached structure {structure_id}: {e}")
            return None
    
    def invalidate_item(self, item_id: str) -> bool:
        """Remove an item from cache.
        
        Args:
            item_id: Google Drive item ID
            
        Returns:
            True if successfully removed
        """
        if not self.enabled:
            return False
        
        try:
            with self._get_connection() as conn:
                cursor = conn.execute('DELETE FROM drive_items WHERE id = ?', (item_id,))
                conn.commit()
                
                if cursor.rowcount > 0:
                    logger.debug(f"Invalidated cached item: {item_id}")
                    return True
                
        except Exception as e:
            logger.error(f"Error invalidating item {item_id}: {e}")
        
        return False
    
    def clear_expired(self) -> int:
        """Remove all expired cache entries.
        
        Returns:
            Number of entries removed
        """
        if not self.enabled:
            return 0
        
        try:
            now = datetime.now().isoformat()
            removed_count = 0
            
            with self._get_connection() as conn:
                # Remove expired items
                cursor = conn.execute('DELETE FROM drive_items WHERE expires_at < ?', (now,))
                removed_count += cursor.rowcount
                
                # Remove expired structures
                cursor = conn.execute('DELETE FROM drive_structures WHERE expires_at < ?', (now,))
                removed_count += cursor.rowcount
                
                conn.commit()
                
            if removed_count > 0:
                logger.info(f"Removed {removed_count} expired cache entries")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Error clearing expired entries: {e}")
            return 0
    
    def clear_all(self) -> bool:
        """Clear all cache data.
        
        Returns:
            True if successfully cleared
        """
        if not self.enabled:
            return False
        
        try:
            with self._get_connection() as conn:
                conn.execute('DELETE FROM drive_items')
                conn.execute('DELETE FROM drive_structures')
                conn.execute('DELETE FROM cache_metadata')
                conn.commit()
                
            logger.info("Cache cleared successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        if not self.enabled:
            return {'enabled': False}
        
        try:
            stats = {'enabled': True}
            
            with self._get_connection() as conn:
                # Count items
                cursor = conn.execute('SELECT COUNT(*) as count FROM drive_items')
                stats['items_count'] = cursor.fetchone()['count']
                
                # Count structures
                cursor = conn.execute('SELECT COUNT(*) as count FROM drive_structures')
                stats['structures_count'] = cursor.fetchone()['count']
                
                # Total size
                cursor = conn.execute('SELECT SUM(size_bytes) as total_size FROM drive_items')
                items_size = cursor.fetchone()['total_size'] or 0
                
                cursor = conn.execute('SELECT SUM(size_bytes) as total_size FROM drive_structures')
                structures_size = cursor.fetchone()['total_size'] or 0
                
                total_size = items_size + structures_size
                stats['total_size_bytes'] = total_size
                stats['total_size_mb'] = total_size / (1024 * 1024)
                
                # Check database file size
                if self.cache_path.exists():
                    stats['database_size_bytes'] = self.cache_path.stat().st_size
                    stats['database_size_mb'] = stats['database_size_bytes'] / (1024 * 1024)
                
                # Expired entries
                now = datetime.now().isoformat()
                cursor = conn.execute('SELECT COUNT(*) as count FROM drive_items WHERE expires_at < ?', (now,))
                expired_items = cursor.fetchone()['count']
                
                cursor = conn.execute('SELECT COUNT(*) as count FROM drive_structures WHERE expires_at < ?', (now,))
                expired_structures = cursor.fetchone()['count']
                
                stats['expired_count'] = expired_items + expired_structures
                
            return stats
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {'enabled': True, 'error': str(e)}
    
    def optimize_cache(self) -> bool:
        """Optimize cache by removing expired entries and vacuuming database.
        
        Returns:
            True if successfully optimized
        """
        if not self.enabled:
            return False
        
        try:
            # Remove expired entries
            removed_count = self.clear_expired()
            
            # Check if cache is too large
            stats = self.get_cache_stats()
            if stats.get('database_size_mb', 0) > self.max_size_mb:
                logger.warning(f"Cache size ({stats['database_size_mb']:.1f} MB) exceeds limit ({self.max_size_mb} MB)")
                # Could implement LRU eviction here
            
            # Vacuum database to reclaim space
            with self._get_connection() as conn:
                conn.execute('VACUUM')
                conn.commit()
            
            logger.info(f"Cache optimized: removed {removed_count} expired entries")
            return True
            
        except Exception as e:
            logger.error(f"Error optimizing cache: {e}")
            return False


# Global cache instance
_cache_instance: Optional[DriveCache] = None


def get_cache() -> DriveCache:
    """Get the global cache instance.
    
    Returns:
        Global DriveCache instance
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = DriveCache()
    return _cache_instance