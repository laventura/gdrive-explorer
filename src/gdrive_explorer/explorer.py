"""Core exploration logic for Google Drive folder traversal."""

import time
from typing import Dict, List, Optional, Set, Callable
from datetime import datetime
import logging

from .client import DriveClient
from .models import DriveItem, DriveStructure, ItemType
from .utils import ProgressTracker
from .config import get_config


logger = logging.getLogger(__name__)


class DriveExplorer:
    """Handles recursive exploration and analysis of Google Drive structure."""
    
    def __init__(self, client: Optional[DriveClient] = None):
        """Initialize the explorer.
        
        Args:
            client: DriveClient instance. If None, will create a new one.
        """
        self.client = client or DriveClient()
        self.config = get_config()
        self._scanned_folders: Set[str] = set()
        self._total_items_found = 0
        
    def scan_drive(self, 
                   progress_callback: Optional[Callable[[int, int], None]] = None,
                   max_depth: Optional[int] = None) -> DriveStructure:
        """Scan the entire Google Drive and build hierarchical structure.
        
        Args:
            progress_callback: Optional callback function(current, total) for progress updates
            max_depth: Maximum folder depth to scan (None for unlimited)
            
        Returns:
            Complete DriveStructure with all files and folders
        """
        logger.info("Starting Google Drive scan...")
        start_time = time.time()
        
        structure = DriveStructure()
        
        try:
            # Step 1: Get all files from Drive
            all_files = self._fetch_all_files(progress_callback)
            logger.info(f"Found {len(all_files)} total items in Drive")
            
            # Step 2: Convert to DriveItem objects and build structure
            self._build_structure(all_files, structure, progress_callback)
            
            # Step 3: Build hierarchy and calculate sizes
            logger.info("Building folder hierarchy...")
            structure.build_hierarchy()
            
            # Step 4: Mark scan as complete
            structure.scan_complete = True
            structure.scan_timestamp = datetime.now()
            
            elapsed = time.time() - start_time
            logger.info(f"Drive scan completed in {elapsed:.2f} seconds")
            logger.info(f"Total: {structure.total_files} files, {structure.total_folders} folders")
            logger.info(f"Total size: {structure.total_size:,} bytes")
            
            return structure
            
        except Exception as e:
            logger.error(f"Error during drive scan: {e}")
            raise
    
    def scan_folder(self, folder_id: str, 
                    max_depth: Optional[int] = None,
                    progress_callback: Optional[Callable[[int, int], None]] = None) -> DriveItem:
        """Scan a specific folder and its contents recursively.
        
        Args:
            folder_id: Google Drive folder ID to scan
            max_depth: Maximum depth to scan (None for unlimited)
            progress_callback: Optional progress callback
            
        Returns:
            DriveItem representing the folder with all children populated
        """
        logger.info(f"Starting folder scan for: {folder_id}")
        
        try:
            # Get folder metadata
            folder_data = self.client.get_file_metadata(folder_id)
            folder = DriveItem.from_drive_api(folder_data)
            
            if not folder.is_folder:
                raise ValueError(f"Item {folder_id} is not a folder")
            
            # Recursively scan contents
            self._scan_folder_recursive(folder, max_depth, 0, progress_callback)
            
            # Calculate final sizes
            folder.calculate_folder_size()
            folder.scan_complete = True
            
            logger.info(f"Folder scan complete: {folder.file_count} files, {folder.folder_count} folders")
            
            return folder
            
        except Exception as e:
            logger.error(f"Error scanning folder {folder_id}: {e}")
            raise
    
    def _fetch_all_files(self, progress_callback: Optional[Callable[[int, int], None]] = None) -> List[Dict]:
        """Fetch all files from Google Drive using pagination.
        
        Args:
            progress_callback: Optional progress callback
            
        Returns:
            List of all file metadata dictionaries
        """
        all_files = []
        page_token = None
        page_count = 0
        
        # Query to exclude trashed files
        query = "trashed=false"
        
        logger.info("Fetching all files from Google Drive...")
        
        while True:
            try:
                result = self.client.list_files(
                    page_size=self.config.api.page_size,
                    page_token=page_token,
                    query=query
                )
                
                files = result.get('files', [])
                all_files.extend(files)
                page_count += 1
                
                if progress_callback:
                    progress_callback(len(all_files), len(all_files))
                
                logger.debug(f"Fetched page {page_count}, total files: {len(all_files)}")
                
                page_token = result.get('nextPageToken')
                if not page_token:
                    break
                    
                # Rate limiting
                time.sleep(self.config.api.request_delay)
                
            except Exception as e:
                logger.error(f"Error fetching files on page {page_count}: {e}")
                raise
        
        logger.info(f"Fetched {len(all_files)} files in {page_count} API calls")
        return all_files
    
    def _build_structure(self, 
                        all_files: List[Dict], 
                        structure: DriveStructure,
                        progress_callback: Optional[Callable[[int, int], None]] = None) -> None:
        """Build DriveStructure from raw file data.
        
        Args:
            all_files: List of file metadata from API
            structure: DriveStructure to populate
            progress_callback: Optional progress callback
        """
        logger.info("Converting API data to DriveItem objects...")
        
        if self.config.display.show_progress:
            progress = ProgressTracker(len(all_files), "Converting files")
        
        for i, file_data in enumerate(all_files):
            try:
                item = DriveItem.from_drive_api(file_data)
                structure.add_item(item)
                
                if self.config.display.show_progress:
                    progress.update()
                
                if progress_callback:
                    progress_callback(i + 1, len(all_files))
                    
            except Exception as e:
                logger.warning(f"Error processing file {file_data.get('id', 'unknown')}: {e}")
                continue
        
        if self.config.display.show_progress:
            progress.complete()
    
    def _scan_folder_recursive(self, 
                              folder: DriveItem, 
                              max_depth: Optional[int],
                              current_depth: int,
                              progress_callback: Optional[Callable[[int, int], None]] = None) -> None:
        """Recursively scan folder contents.
        
        Args:
            folder: Folder to scan
            max_depth: Maximum depth to scan
            current_depth: Current depth level
            progress_callback: Optional progress callback
        """
        if folder.id in self._scanned_folders:
            return  # Already scanned
        
        if max_depth is not None and current_depth >= max_depth:
            return  # Reached maximum depth
        
        logger.debug(f"Scanning folder: {folder.name} (depth {current_depth})")
        
        try:
            # Get children of this folder
            children_data = self.client.get_folder_children(folder.id)
            
            for child_data in children_data:
                try:
                    child = DriveItem.from_drive_api(child_data)
                    folder.add_child(child)
                    
                    # If child is a folder, scan it recursively
                    if child.is_folder:
                        self._scan_folder_recursive(
                            child, 
                            max_depth, 
                            current_depth + 1, 
                            progress_callback
                        )
                    
                    self._total_items_found += 1
                    
                    if progress_callback:
                        progress_callback(self._total_items_found, self._total_items_found)
                        
                except Exception as e:
                    logger.warning(f"Error processing child item: {e}")
                    continue
            
            self._scanned_folders.add(folder.id)
            
        except Exception as e:
            logger.error(f"Error scanning folder {folder.name}: {e}")
            raise
    
    def get_folder_tree(self, folder: DriveItem, max_depth: int = 3) -> Dict:
        """Get folder tree structure for display.
        
        Args:
            folder: Root folder
            max_depth: Maximum depth to display
            
        Returns:
            Dictionary representing tree structure
        """
        def build_tree(item: DriveItem, depth: int) -> Dict:
            tree = {
                'name': item.name,
                'type': item.type,
                'size': item.display_size,
                'file_count': item.file_count,
                'folder_count': item.folder_count,
                'children': []
            }
            
            if depth < max_depth and item.is_folder:
                for child in sorted(item.children, key=lambda x: x.display_size, reverse=True):
                    tree['children'].append(build_tree(child, depth + 1))
            
            return tree
        
        return build_tree(folder, 0)
    
    def find_largest_files(self, structure: DriveStructure, limit: int = 50) -> List[DriveItem]:
        """Find the largest files in the drive.
        
        Args:
            structure: DriveStructure to search
            limit: Maximum number of files to return
            
        Returns:
            List of largest files sorted by size
        """
        files = [item for item in structure.all_items.values() 
                if not item.is_folder and item.size > 0]
        
        files.sort(key=lambda x: x.size, reverse=True)
        return files[:limit]
    
    def find_largest_folders(self, structure: DriveStructure, limit: int = 50) -> List[DriveItem]:
        """Find the largest folders in the drive.
        
        Args:
            structure: DriveStructure to search
            limit: Maximum number of folders to return
            
        Returns:
            List of largest folders sorted by calculated size
        """
        folders = [item for item in structure.all_items.values() 
                  if item.is_folder and item.calculated_size and item.calculated_size > 0]
        
        folders.sort(key=lambda x: x.calculated_size, reverse=True)
        return folders[:limit]
    
    def find_empty_folders(self, structure: DriveStructure) -> List[DriveItem]:
        """Find empty folders in the drive.
        
        Args:
            structure: DriveStructure to search
            
        Returns:
            List of empty folders
        """
        empty_folders = []
        
        for item in structure.all_items.values():
            if item.is_folder and len(item.children) == 0:
                empty_folders.append(item)
        
        return empty_folders
    
    def analyze_file_types(self, structure: DriveStructure) -> Dict[str, Dict]:
        """Analyze file types and their storage usage.
        
        Args:
            structure: DriveStructure to analyze
            
        Returns:
            Dictionary with file type statistics
        """
        type_stats = {}
        
        for item in structure.all_items.values():
            if not item.is_folder:
                mime_type = item.mime_type
                file_type = item.type
                
                if file_type not in type_stats:
                    type_stats[file_type] = {
                        'count': 0,
                        'total_size': 0,
                        'mime_types': set()
                    }
                
                type_stats[file_type]['count'] += 1
                type_stats[file_type]['total_size'] += item.size
                type_stats[file_type]['mime_types'].add(mime_type)
        
        # Convert sets to lists for JSON serialization
        for stats in type_stats.values():
            stats['mime_types'] = list(stats['mime_types'])
        
        return type_stats