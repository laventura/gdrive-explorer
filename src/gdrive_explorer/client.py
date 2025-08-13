"""Google Drive API client wrapper."""

import time
import random
import logging
from typing import Dict, List, Optional, Any, Callable
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from .auth import get_authenticated_credentials
from .config import get_config


logger = logging.getLogger(__name__)


class DriveClient:
    """Wrapper for Google Drive API with enhanced rate limiting and error handling."""
    
    def __init__(self, credentials: Optional[Credentials] = None):
        """Initialize Drive API client.
        
        Args:
            credentials: Google API credentials. If None, will authenticate automatically.
        """
        if credentials is None:
            credentials = get_authenticated_credentials()
        
        self.service = build('drive', 'v3', credentials=credentials)
        self.config = get_config()
        self.request_delay = self.config.api.request_delay
        self.max_retries = self.config.api.max_retries
        self._last_request_time = 0.0
        self._request_count = 0
    
    def _make_request_with_retry(self, request_func: Callable, *args, **kwargs) -> Any:
        """Make API request with exponential backoff retry logic.
        
        Args:
            request_func: Function to call that makes the API request
            *args, **kwargs: Arguments to pass to request_func
            
        Returns:
            Result from successful API request
            
        Raises:
            HttpError: If all retries are exhausted
        """
        # Rate limiting - ensure minimum delay between requests
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self.request_delay:
            sleep_time = self.request_delay - time_since_last
            time.sleep(sleep_time)
        
        for attempt in range(self.max_retries + 1):
            try:
                self._last_request_time = time.time()
                self._request_count += 1
                
                if attempt > 0:
                    logger.debug(f"API request attempt {attempt + 1}/{self.max_retries + 1}")
                
                result = request_func(*args, **kwargs)
                
                if attempt > 0:
                    logger.info(f"API request succeeded on attempt {attempt + 1}")
                
                return result
                
            except HttpError as error:
                status_code = error.resp.status
                
                # Handle different types of errors
                if status_code == 429:  # Rate limit exceeded
                    if attempt < self.max_retries:
                        # Exponential backoff with jitter
                        base_delay = min(60, 2 ** attempt)
                        jitter = random.uniform(0.1, 0.3) * base_delay
                        delay = base_delay + jitter
                        
                        logger.warning(f"Rate limit exceeded. Retrying in {delay:.1f} seconds...")
                        time.sleep(delay)
                        continue
                    else:
                        logger.error("Rate limit exceeded. Max retries exhausted.")
                        raise
                        
                elif status_code in [500, 502, 503, 504]:  # Server errors
                    if attempt < self.max_retries:
                        # Shorter delay for server errors
                        delay = min(10, 2 ** attempt) + random.uniform(0.1, 0.5)
                        logger.warning(f"Server error {status_code}. Retrying in {delay:.1f} seconds...")
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(f"Server error {status_code}. Max retries exhausted.")
                        raise
                        
                elif status_code == 403:  # Forbidden - might be quota
                    if "quota" in str(error).lower() and attempt < self.max_retries:
                        delay = 60 + random.uniform(10, 30)  # Longer delay for quota issues
                        logger.warning(f"Quota exceeded. Retrying in {delay:.1f} seconds...")
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(f"Access forbidden: {error}")
                        raise
                        
                else:
                    # For other errors, don't retry
                    logger.error(f"API error {status_code}: {error}")
                    raise
                    
            except Exception as e:
                # For non-HTTP errors, retry with exponential backoff
                if attempt < self.max_retries:
                    delay = min(30, 2 ** attempt) + random.uniform(0.1, 1.0)
                    logger.warning(f"Unexpected error: {e}. Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"Unexpected error. Max retries exhausted: {e}")
                    raise
        
        # This should never be reached, but just in case
        raise Exception("Max retries exhausted")
    
    def list_files(self, page_size: int = 1000, page_token: Optional[str] = None,
                   query: Optional[str] = None, fields: Optional[str] = None) -> Dict[str, Any]:
        """List files from Google Drive.
        
        Args:
            page_size: Number of files to return per page (max 1000)
            page_token: Token for next page of results
            query: Search query to filter files
            fields: Specific fields to return (default includes all metadata)
            
        Returns:
            Dictionary containing files list and nextPageToken if more results exist
            
        Raises:
            HttpError: If API request fails
        """
        if fields is None:
            # Request comprehensive file metadata
            fields = (
                "nextPageToken, files("
                "id, name, mimeType, size, parents, createdTime, modifiedTime, "
                "webViewLink, ownedByMe, shared, trashed, starred"
                ")"
            )
        
        def _list_request():
            return self.service.files().list(
                pageSize=page_size,
                pageToken=page_token,
                q=query,
                fields=fields
            ).execute()
        
        return self._make_request_with_retry(_list_request)
    
    def get_file_metadata(self, file_id: str, fields: Optional[str] = None) -> Dict[str, Any]:
        """Get metadata for a specific file.
        
        Args:
            file_id: Google Drive file ID
            fields: Specific fields to return
            
        Returns:
            File metadata dictionary
            
        Raises:
            HttpError: If API request fails
        """
        if fields is None:
            fields = (
                "id, name, mimeType, size, parents, createdTime, modifiedTime, "
                "webViewLink, ownedByMe, shared, trashed, starred"
            )
        
        def _get_request():
            return self.service.files().get(
                fileId=file_id,
                fields=fields
            ).execute()
        
        return self._make_request_with_retry(_get_request)
    
    def get_request_stats(self) -> Dict[str, Any]:
        """Get statistics about API requests made.
        
        Returns:
            Dictionary with request statistics
        """
        return {
            'total_requests': self._request_count,
            'request_delay': self.request_delay,
            'max_retries': self.max_retries,
            'last_request_time': self._last_request_time
        }
    
    def list_all_files(self, query: Optional[str] = None, 
                       show_progress: bool = True) -> List[Dict[str, Any]]:
        """List all files from Google Drive, handling pagination automatically.
        
        Args:
            query: Search query to filter files
            show_progress: Whether to show progress information
            
        Returns:
            List of all files matching the query
            
        Raises:
            HttpError: If API request fails
        """
        all_files = []
        page_token = None
        page_count = 0
        
        while True:
            result = self.list_files(page_token=page_token, query=query)
            files = result.get('files', [])
            all_files.extend(files)
            
            page_count += 1
            if show_progress:
                print(f"Fetched page {page_count}, total files: {len(all_files)}")
            
            page_token = result.get('nextPageToken')
            if not page_token:
                break
        
        if show_progress:
            print(f"Completed: fetched {len(all_files)} files total")
        
        return all_files
    
    def get_folder_children(self, folder_id: str) -> List[Dict[str, Any]]:
        """Get all files and folders within a specific folder.
        
        Args:
            folder_id: Google Drive folder ID
            
        Returns:
            List of files/folders in the specified folder
        """
        query = f"'{folder_id}' in parents and trashed=false"
        return self.list_all_files(query=query, show_progress=False)
    
    def is_folder(self, file_metadata: Dict[str, Any]) -> bool:
        """Check if a file is actually a folder.
        
        Args:
            file_metadata: File metadata from Drive API
            
        Returns:
            True if the file is a folder
        """
        return file_metadata.get('mimeType') == 'application/vnd.google-apps.folder'
    
    def get_file_size(self, file_metadata: Dict[str, Any]) -> int:
        """Get file size in bytes, handling Google Workspace files.
        
        Args:
            file_metadata: File metadata from Drive API
            
        Returns:
            File size in bytes (0 for Google Workspace files)
        """
        # Google Workspace files (Docs, Sheets, etc.) don't have size
        size_str = file_metadata.get('size')
        if size_str is None:
            return 0
        
        try:
            return int(size_str)
        except (ValueError, TypeError):
            return 0
    
    def test_connection(self) -> bool:
        """Test the connection to Google Drive API.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Try to get basic info about the user's Drive
            result = self.service.about().get(fields="user").execute()
            return 'user' in result
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False