"""Size calculation engine for Google Drive Explorer."""

import logging
import time
from typing import Dict, List, Optional, Set, Callable
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from googleapiclient.errors import HttpError

from .client import DriveClient
from .models import DriveItem, DriveStructure, ItemType
from .cache import get_cache
from .config import get_config
from .utils import RichProgressManager, format_file_size


logger = logging.getLogger(__name__)


class SizeCalculationError(Exception):
    """Exception raised when size calculation fails."""
    pass


class PermissionError(SizeCalculationError):
    """Exception raised when access is denied to a folder or file."""
    pass


class RateLimitError(SizeCalculationError):
    """Exception raised when API rate limit is exceeded."""
    pass


class DriveCalculator:
    """Handles recursive size calculation for Google Drive folder structures."""
    
    def __init__(self, client: Optional[DriveClient] = None):
        """Initialize the calculator.
        
        Args:
            client: DriveClient instance. If None, will create a new one.
        """
        self.client = client or DriveClient()
        self.config = get_config()
        self.cache = get_cache()
        
        # Statistics
        self._processed_items = 0
        self._total_size_calculated = 0
        self._errors_encountered = 0
        self._permission_errors = 0
        self._rate_limit_errors = 0
        self._cache_hits = 0
        self._api_calls = 0
        
        # Internal tracking
        self._calculated_folders: Dict[str, int] = {}
        self._processing_folders: Set[str] = set()
    
    def calculate_full_drive_sizes(self, 
                                   structure: DriveStructure,
                                   force_recalculate: bool = False,
                                   progress_callback: Optional[Callable[[str, int, int], None]] = None) -> DriveStructure:
        """Calculate sizes for all folders in the Drive structure.
        
        Args:
            structure: DriveStructure to calculate sizes for
            force_recalculate: If True, ignore cached calculations
            progress_callback: Optional callback for progress updates (message, current, total)
            
        Returns:
            Updated DriveStructure with calculated folder sizes
        """
        logger.info("Starting full Drive size calculation...")
        start_time = time.time()
        
        try:
            # Reset statistics
            self._reset_stats()
            
            # Get all folders that need calculation
            folders_to_calculate = [
                item for item in structure.all_items.values() 
                if item.is_folder and (force_recalculate or item.calculated_size is None)
            ]
            
            total_folders = len(folders_to_calculate)
            logger.info(f"Found {total_folders} folders to calculate")
            
            if progress_callback:
                progress_callback("Analyzing folders...", 0, total_folders)
            
            # Calculate sizes for all folders
            processed = 0
            for folder in folders_to_calculate:
                try:
                    self._calculate_folder_size_recursive(folder, structure)
                    processed += 1
                    
                    if progress_callback:
                        progress_callback(
                            f"Calculated: {folder.name}", 
                            processed, 
                            total_folders
                        )
                    
                    # Log progress periodically
                    if processed % 50 == 0:
                        logger.info(f"Calculated sizes for {processed}/{total_folders} folders")
                        
                except PermissionError as e:
                    logger.warning(f"Permission denied for folder '{folder.name}': {e}")
                    self._permission_errors += 1
                    self._errors_encountered += 1
                    # Mark folder as scanned but with error
                    folder.scan_complete = True
                    folder.calculated_size = 0
                    folder.last_scanned = datetime.now()
                    continue
                    
                except RateLimitError as e:
                    logger.error(f"Rate limit exceeded while processing '{folder.name}': {e}")
                    self._rate_limit_errors += 1
                    self._errors_encountered += 1
                    # Wait and retry once
                    time.sleep(2)
                    try:
                        self._calculate_folder_size_recursive(folder, structure)
                        processed += 1
                    except Exception:
                        logger.error(f"Retry failed for folder '{folder.name}'")
                        continue
                        
                except Exception as e:
                    logger.warning(f"Unexpected error calculating size for folder '{folder.name}': {e}")
                    self._errors_encountered += 1
                    continue
            
            # Update structure statistics
            self._update_structure_stats(structure)
            
            # Cache the complete structure
            if self.config.cache.enabled:
                self.cache.cache_structure(structure)
                logger.info("Cached complete structure")
            
            elapsed = time.time() - start_time
            logger.info(f"Size calculation completed in {elapsed:.2f} seconds")
            self._log_statistics()
            
            return structure
            
        except Exception as e:
            logger.error(f"Error during size calculation: {e}")
            raise SizeCalculationError(f"Failed to calculate Drive sizes: {e}")
    
    def _calculate_folder_size_recursive(self, folder: DriveItem, structure: DriveStructure) -> int:
        """Recursively calculate the size of a folder.
        
        Args:
            folder: Folder to calculate size for
            structure: Complete Drive structure
            
        Returns:
            Total size of folder in bytes
        """
        # Avoid circular references and double processing
        if folder.id in self._processing_folders:
            logger.warning(f"Circular reference detected for folder: {folder.name}")
            return 0
        
        # Check if already calculated
        if folder.id in self._calculated_folders:
            self._cache_hits += 1
            return self._calculated_folders[folder.id]
        
        # Check cache for folder sizes
        cached_folder = self.cache.get_item(folder.id)
        if cached_folder and cached_folder.calculated_size is not None and not self._should_recalculate(cached_folder):
            # Use cached data
            folder.calculated_size = cached_folder.calculated_size
            folder.file_count = cached_folder.file_count
            folder.folder_count = cached_folder.folder_count
            folder.last_scanned = cached_folder.last_scanned
            folder.scan_complete = True
            
            self._calculated_folders[folder.id] = cached_folder.calculated_size
            self._cache_hits += 1
            return cached_folder.calculated_size
        
        # Check in-memory cache
        if not folder.calculated_size is None and not self._should_recalculate(folder):
            self._calculated_folders[folder.id] = folder.calculated_size
            self._cache_hits += 1
            return folder.calculated_size
        
        # Mark as being processed
        self._processing_folders.add(folder.id)
        
        try:
            total_size = 0
            file_count = 0
            folder_count = 0
            
            # Process all children
            for child in folder.children:
                if child.is_folder:
                    # Recursively calculate subfolder size
                    child_size = self._calculate_folder_size_recursive(child, structure)
                    total_size += child_size
                    folder_count += 1
                    # Don't double-count nested folders - they're already included in child.folder_count
                    # This was causing exponential performance issues
                else:
                    # Add file size directly
                    # Note: Google Workspace files have size=0, but we still count them
                    total_size += child.size
                    file_count += 1
                    
                    # Log Google Workspace files for debugging
                    if child.is_google_workspace_file and child.size == 0:
                        logger.debug(f"Google Workspace file found: {child.name} ({child.type})")
            
            # Add nested counts from all subfolders
            for child in folder.children:
                if child.is_folder:
                    folder_count += child.folder_count  # Add nested folder counts
                    file_count += child.file_count      # Add nested file counts
            
            # Update folder metadata
            folder.calculated_size = total_size
            folder.file_count = file_count
            folder.folder_count = folder_count
            folder.last_scanned = datetime.now()
            folder.scan_complete = True
            
            # Cache the result in memory and persistent cache
            self._calculated_folders[folder.id] = total_size
            self._processed_items += 1
            self._total_size_calculated += total_size
            
            # Cache individual folder for future use
            if self.config.cache.enabled:
                self.cache.cache_item(folder)
            
            logger.debug(f"Calculated size for '{folder.name}': {format_file_size(total_size)} "
                        f"({file_count} files, {folder_count} folders)")
            
            return total_size
            
        finally:
            # Remove from processing set
            self._processing_folders.discard(folder.id)
    
    def _handle_api_error(self, error: Exception, item_name: str) -> None:
        """Handle API errors and convert to appropriate exceptions.
        
        Args:
            error: Exception from API call
            item_name: Name of item being processed
            
        Raises:
            PermissionError: For 403 Forbidden errors
            RateLimitError: For 429 Too Many Requests errors
            SizeCalculationError: For other API errors
        """
        if isinstance(error, HttpError):
            if error.resp.status == 403:
                raise PermissionError(f"Access denied to {item_name}")
            elif error.resp.status == 429:
                raise RateLimitError(f"Rate limit exceeded for {item_name}")
            elif error.resp.status >= 500:
                raise SizeCalculationError(f"Server error while accessing {item_name}: {error}")
            else:
                raise SizeCalculationError(f"API error for {item_name}: {error}")
        else:
            raise SizeCalculationError(f"Unexpected error for {item_name}: {error}")
    
    def calculate_folder_tree_sizes(self, root_folder: DriveItem) -> DriveItem:
        """Calculate sizes for a specific folder tree.
        
        Args:
            root_folder: Root folder to start calculation from
            
        Returns:
            Updated folder with calculated sizes
        """
        logger.info(f"Calculating sizes for folder tree: {root_folder.name}")
        start_time = time.time()
        
        try:
            self._reset_stats()
            
            # Create a minimal structure for this tree
            structure = DriveStructure()
            self._add_folder_tree_to_structure(root_folder, structure)
            
            # Calculate sizes
            total_size = self._calculate_folder_size_recursive(root_folder, structure)
            
            elapsed = time.time() - start_time
            logger.info(f"Tree calculation completed in {elapsed:.2f} seconds")
            logger.info(f"Total size: {format_file_size(total_size)}")
            
            return root_folder
            
        except Exception as e:
            logger.error(f"Error calculating folder tree sizes: {e}")
            raise SizeCalculationError(f"Failed to calculate folder tree: {e}")
    
    def calculate_incremental_sizes(self, 
                                   structure: DriveStructure,
                                   progress_callback: Optional[Callable[[str, int, int], None]] = None) -> DriveStructure:
        """Calculate sizes only for folders that need updating (incremental calculation).
        
        Args:
            structure: DriveStructure to update
            progress_callback: Optional callback for progress updates
            
        Returns:
            Updated DriveStructure with recalculated sizes
        """
        logger.info("Starting incremental Drive size calculation...")
        start_time = time.time()
        
        try:
            # Reset statistics
            self._reset_stats()
            
            # Find folders that need recalculation
            folders_to_update = []
            for item in structure.all_items.values():
                if item.is_folder and self._should_recalculate(item):
                    folders_to_update.append(item)
            
            total_folders = len(folders_to_update)
            logger.info(f"Found {total_folders} folders that need updating")
            
            if total_folders == 0:
                logger.info("No folders need updating - using cached data")
                return structure
            
            if progress_callback:
                progress_callback("Analyzing modified folders...", 0, total_folders)
            
            # Calculate sizes for modified folders only
            processed = 0
            for folder in folders_to_update:
                try:
                    # Invalidate cache for this folder first
                    self.cache.invalidate_item(folder.id)
                    
                    # Recalculate size
                    self._calculate_folder_size_recursive(folder, structure)
                    processed += 1
                    
                    if progress_callback:
                        progress_callback(
                            f"Updated: {folder.name}", 
                            processed, 
                            total_folders
                        )
                    
                    # Log progress periodically
                    if processed % 20 == 0:
                        logger.info(f"Updated sizes for {processed}/{total_folders} folders")
                        
                except Exception as e:
                    logger.warning(f"Error updating size for folder '{folder.name}': {e}")
                    self._errors_encountered += 1
                    continue
            
            # Update structure statistics
            self._update_structure_stats(structure)
            
            # Cache the updated structure
            if self.config.cache.enabled:
                self.cache.cache_structure(structure)
                logger.info("Cached updated structure")
            
            elapsed = time.time() - start_time
            logger.info(f"Incremental calculation completed in {elapsed:.2f} seconds")
            self._log_statistics()
            
            return structure
            
        except Exception as e:
            logger.error(f"Error during incremental calculation: {e}")
            raise SizeCalculationError(f"Failed to perform incremental calculation: {e}")
    
    def _add_folder_tree_to_structure(self, folder: DriveItem, structure: DriveStructure) -> None:
        """Recursively add folder tree to structure."""
        structure.add_item(folder)
        
        for child in folder.children:
            if child.is_folder:
                self._add_folder_tree_to_structure(child, structure)
            else:
                structure.add_item(child)
    
    def _should_recalculate(self, folder: DriveItem) -> bool:
        """Determine if a folder should be recalculated.
        
        Args:
            folder: Folder to check
            
        Returns:
            True if folder should be recalculated
        """
        # Always recalculate if no size is set
        if folder.calculated_size is None:
            return True
        
        # Check if folder was scanned recently
        if folder.last_scanned:
            hours_since_scan = (datetime.now() - folder.last_scanned).total_seconds() / 3600
            if hours_since_scan < self.config.cache.ttl_hours:
                return False
        
        # Check if any children have been modified since last scan
        if folder.last_scanned:
            for child in folder.children:
                if child.modified_time and child.modified_time > folder.last_scanned:
                    logger.debug(f"Recalculating '{folder.name}' - child '{child.name}' was modified")
                    return True
        
        return False
    
    def _update_structure_stats(self, structure: DriveStructure) -> None:
        """Update overall structure statistics."""
        total_calculated_size = 0
        total_files = 0
        total_folders = 0
        
        for item in structure.all_items.values():
            if item.is_folder:
                total_folders += 1
                if item.calculated_size:
                    total_calculated_size += item.calculated_size
            else:
                total_files += 1
                total_calculated_size += item.size
        
        structure.total_files = total_files
        structure.total_folders = total_folders
        structure.total_size = total_calculated_size
        structure.scan_timestamp = datetime.now()
        structure.scan_complete = True
    
    def _reset_stats(self) -> None:
        """Reset calculation statistics."""
        self._processed_items = 0
        self._total_size_calculated = 0
        self._errors_encountered = 0
        self._permission_errors = 0
        self._rate_limit_errors = 0
        self._cache_hits = 0
        self._api_calls = 0
        self._calculated_folders.clear()
        self._processing_folders.clear()
    
    def _log_statistics(self) -> None:
        """Log calculation statistics."""
        logger.info("=== Size Calculation Statistics ===")
        logger.info(f"Folders processed: {self._processed_items}")
        logger.info(f"Total size calculated: {format_file_size(self._total_size_calculated)}")
        logger.info(f"Cache hits: {self._cache_hits}")
        logger.info(f"API calls made: {self._api_calls}")
        logger.info(f"Errors encountered: {self._errors_encountered}")
        if self._permission_errors > 0:
            logger.info(f"Permission errors: {self._permission_errors}")
        if self._rate_limit_errors > 0:
            logger.info(f"Rate limit errors: {self._rate_limit_errors}")
    
    def get_calculation_stats(self) -> Dict[str, any]:
        """Get current calculation statistics.
        
        Returns:
            Dictionary with calculation statistics
        """
        return {
            'processed_items': self._processed_items,
            'total_size_calculated': self._total_size_calculated,
            'cache_hits': self._cache_hits,
            'api_calls': self._api_calls,
            'errors_encountered': self._errors_encountered,
            'permission_errors': self._permission_errors,
            'rate_limit_errors': self._rate_limit_errors
        }
    
    def find_largest_folders(self, structure: DriveStructure, limit: int = 50) -> List[DriveItem]:
        """Find the largest folders by calculated size.
        
        Args:
            structure: DriveStructure to search
            limit: Maximum number of folders to return
            
        Returns:
            List of largest folders sorted by size
        """
        folders_with_size = [
            item for item in structure.all_items.values()
            if item.is_folder and item.calculated_size and item.calculated_size > 0
        ]
        
        folders_with_size.sort(key=lambda x: x.calculated_size, reverse=True)
        return folders_with_size[:limit]
    
    def find_empty_folders(self, structure: DriveStructure) -> List[DriveItem]:
        """Find empty folders (no files or subfolders).
        
        Args:
            structure: DriveStructure to search
            
        Returns:
            List of empty folders
        """
        empty_folders = []
        
        for item in structure.all_items.values():
            if (item.is_folder and 
                item.scan_complete and 
                item.file_count == 0 and 
                item.folder_count == 0):
                empty_folders.append(item)
        
        return empty_folders
    
    def analyze_folder_distribution(self, structure: DriveStructure) -> Dict[str, any]:
        """Analyze the distribution of folder sizes.
        
        Args:
            structure: DriveStructure to analyze
            
        Returns:
            Dictionary with folder size distribution analysis
        """
        folders_with_size = [
            item for item in structure.all_items.values()
            if item.is_folder and item.calculated_size and item.calculated_size > 0
        ]
        
        if not folders_with_size:
            return {'total_folders': 0, 'analysis': 'No folders with calculated sizes'}
        
        sizes = [folder.calculated_size for folder in folders_with_size]
        sizes.sort(reverse=True)
        
        total_size = sum(sizes)
        folder_count = len(sizes)
        
        # Calculate percentiles
        def percentile(data, p):
            index = int(len(data) * p / 100)
            return data[min(index, len(data) - 1)]
        
        analysis = {
            'total_folders': folder_count,
            'total_size': total_size,
            'largest_folder_size': sizes[0],
            'median_folder_size': percentile(sizes, 50),
            'p90_folder_size': percentile(sizes, 90),
            'p95_folder_size': percentile(sizes, 95),
            'smallest_folder_size': sizes[-1],
            'empty_folders': len(self.find_empty_folders(structure))
        }
        
        # Size distribution buckets
        buckets = {
            'tiny': 0,      # < 1MB
            'small': 0,     # 1MB - 10MB
            'medium': 0,    # 10MB - 100MB
            'large': 0,     # 100MB - 1GB
            'huge': 0       # > 1GB
        }
        
        for size in sizes:
            if size < 1024**2:  # < 1MB
                buckets['tiny'] += 1
            elif size < 10 * 1024**2:  # < 10MB
                buckets['small'] += 1
            elif size < 100 * 1024**2:  # < 100MB
                buckets['medium'] += 1
            elif size < 1024**3:  # < 1GB
                buckets['large'] += 1
            else:  # >= 1GB
                buckets['huge'] += 1
        
        analysis['size_distribution'] = buckets
        
        return analysis
    
    def analyze_google_workspace_files(self, structure: DriveStructure) -> Dict[str, any]:
        """Analyze Google Workspace files in the Drive structure.
        
        Args:
            structure: DriveStructure to analyze
            
        Returns:
            Dictionary with Google Workspace file analysis
        """
        workspace_files = []
        workspace_types = {}
        
        for item in structure.all_items.values():
            if item.is_google_workspace_file:
                workspace_files.append(item)
                
                if item.type not in workspace_types:
                    workspace_types[item.type] = {
                        'count': 0,
                        'examples': []
                    }
                
                workspace_types[item.type]['count'] += 1
                if len(workspace_types[item.type]['examples']) < 5:
                    workspace_types[item.type]['examples'].append(item.name)
        
        # Calculate workspace file distribution by folder
        folders_with_workspace = 0
        for folder in structure.all_items.values():
            if folder.is_folder:
                has_workspace = any(child.is_google_workspace_file for child in folder.children)
                if has_workspace:
                    folders_with_workspace += 1
        
        analysis = {
            'total_workspace_files': len(workspace_files),
            'workspace_types': workspace_types,
            'folders_containing_workspace': folders_with_workspace,
            'percentage_of_total_files': (len(workspace_files) / max(structure.total_files, 1)) * 100,
            'most_common_type': max(workspace_types.keys(), key=lambda k: workspace_types[k]['count']) if workspace_types else None
        }
        
        return analysis