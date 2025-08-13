"""Utility functions and helpers for Google Drive Explorer."""

import logging
import sys
import time
from pathlib import Path
from typing import Union


def setup_logging(level: str = "INFO", log_file: str = "gdrive-explorer.log") -> None:
    """Set up application logging.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Path to log file
    """
    # Ensure log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )


def format_file_size(size_bytes: int, human_readable: bool = True) -> str:
    """Format file size in human-readable format.
    
    Args:
        size_bytes: File size in bytes
        human_readable: If True, format as KB/MB/GB, otherwise raw bytes
        
    Returns:
        Formatted file size string
    """
    if not human_readable:
        return f"{size_bytes:,} bytes"
    
    if size_bytes == 0:
        return "0 B"
    
    # Convert to appropriate unit
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    unit_index = 0
    size = float(size_bytes)
    
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    
    # Format with appropriate precision
    if unit_index == 0:  # Bytes
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.1f} {units[unit_index]}"


def validate_file_path(file_path: Union[str, Path], must_exist: bool = True) -> Path:
    """Validate and normalize file path.
    
    Args:
        file_path: Path to validate
        must_exist: If True, file must exist
        
    Returns:
        Validated Path object
        
    Raises:
        FileNotFoundError: If file doesn't exist and must_exist is True
        ValueError: If path is invalid
    """
    try:
        path = Path(file_path).resolve()
        
        if must_exist and not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        return path
        
    except Exception as e:
        raise ValueError(f"Invalid file path '{file_path}': {e}")


def ensure_directory_exists(directory: Union[str, Path]) -> Path:
    """Ensure directory exists, creating it if necessary.
    
    Args:
        directory: Directory path
        
    Returns:
        Path object for the directory
    """
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def truncate_string(text: str, max_length: int = 50, suffix: str = "...") -> str:
    """Truncate string to maximum length.
    
    Args:
        text: String to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add when truncating
        
    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def safe_get_nested_dict(data: dict, keys: list, default=None):
    """Safely get value from nested dictionary.
    
    Args:
        data: Dictionary to search
        keys: List of keys representing nested path
        default: Default value if key path doesn't exist
        
    Returns:
        Value at nested path or default
    """
    try:
        result = data
        for key in keys:
            result = result[key]
        return result
    except (KeyError, TypeError):
        return default


class ProgressTracker:
    """Enhanced progress tracking utility with rich output support."""
    
    def __init__(self, total: int, description: str = "Processing", use_rich: bool = True):
        """Initialize progress tracker.
        
        Args:
            total: Total number of items to process
            description: Description of the operation
            use_rich: Whether to use rich progress bars
        """
        self.total = total
        self.current = 0
        self.description = description
        self.last_percent = -1
        self.use_rich = use_rich
        self.start_time = time.time()
        
        if use_rich:
            try:
                from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn, TimeRemainingColumn
                self._rich_progress = Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    TimeElapsedColumn(),
                    TimeRemainingColumn(),
                )
                self._task_id = self._rich_progress.add_task(description, total=total)
                self._rich_progress.start()
            except ImportError:
                self.use_rich = False
    
    def update(self, increment: int = 1) -> None:
        """Update progress.
        
        Args:
            increment: Number of items processed
        """
        self.current += increment
        
        if self.use_rich and hasattr(self, '_rich_progress'):
            self._rich_progress.update(self._task_id, completed=self.current)
        else:
            # Fallback to simple text progress
            percent = int((self.current / self.total) * 100) if self.total > 0 else 100
            
            # Only print when percent changes to avoid spam
            if percent != self.last_percent:
                elapsed = time.time() - self.start_time
                rate = self.current / elapsed if elapsed > 0 else 0
                eta = (self.total - self.current) / rate if rate > 0 else 0
                
                print(f"\r{self.description}: {percent}% ({self.current}/{self.total}) "
                      f"[{rate:.1f} items/s, ETA: {eta:.0f}s]", end="")
                self.last_percent = percent
                
                if self.current >= self.total:
                    print()  # New line when complete
    
    def complete(self) -> None:
        """Mark progress as complete."""
        self.current = self.total
        
        if self.use_rich and hasattr(self, '_rich_progress'):
            self._rich_progress.update(self._task_id, completed=self.total)
            self._rich_progress.stop()
        else:
            self.update(0)
            
        elapsed = time.time() - self.start_time
        print(f"{self.description} completed in {elapsed:.2f} seconds")
    
    def set_description(self, description: str) -> None:
        """Update the progress description.
        
        Args:
            description: New description
        """
        self.description = description
        
        if self.use_rich and hasattr(self, '_rich_progress'):
            self._rich_progress.update(self._task_id, description=description)


class RichProgressManager:
    """Manager for multiple concurrent progress bars using rich."""
    
    def __init__(self):
        """Initialize the progress manager."""
        self.tasks = {}
        self._progress = None
        
        try:
            from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
            )
        except ImportError:
            pass
    
    def start(self) -> None:
        """Start the progress display."""
        if self._progress:
            self._progress.start()
    
    def stop(self) -> None:
        """Stop the progress display."""
        if self._progress:
            self._progress.stop()
    
    def add_task(self, name: str, description: str, total: int) -> str:
        """Add a new progress task.
        
        Args:
            name: Unique name for the task
            description: Description to display
            total: Total number of items
            
        Returns:
            Task ID for updates
        """
        if self._progress:
            task_id = self._progress.add_task(description, total=total)
            self.tasks[name] = task_id
            return task_id
        return name
    
    def update_task(self, name: str, increment: int = 1) -> None:
        """Update a task's progress.
        
        Args:
            name: Task name
            increment: Number of items processed
        """
        if self._progress and name in self.tasks:
            self._progress.update(self.tasks[name], advance=increment)
    
    def complete_task(self, name: str) -> None:
        """Mark a task as complete.
        
        Args:
            name: Task name
        """
        if self._progress and name in self.tasks:
            task_id = self.tasks[name]
            task = self._progress.tasks[task_id]
            self._progress.update(task_id, completed=task.total)