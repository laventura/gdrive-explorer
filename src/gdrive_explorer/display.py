"""Rich CLI output formatting and display utilities."""

import math
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from enum import Enum

from rich.console import Console
from rich.table import Table
from rich.tree import Tree
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.text import Text
from rich.align import Align
from rich import print as rprint

from .models import DriveItem, DriveStructure, ItemType
from .utils import format_file_size
from .config import get_config


class SortBy(str, Enum):
    """Sorting options for display."""
    SIZE = "size"
    NAME = "name"
    MODIFIED = "modified"
    TYPE = "type"
    COUNT = "count"  # For folders, sort by file count


class DisplayFormat(str, Enum):
    """Display format options."""
    TABLE = "table"
    TREE = "tree"
    JSON = "json"
    COMPACT = "compact"


class FilterOptions:
    """Options for filtering displayed items."""
    
    def __init__(self):
        self.min_size: Optional[int] = None
        self.max_size: Optional[int] = None
        self.item_types: Optional[List[ItemType]] = None
        self.include_folders: bool = True
        self.include_files: bool = True
        self.modified_after: Optional[datetime] = None
        self.modified_before: Optional[datetime] = None
        self.name_pattern: Optional[str] = None
        self.show_zero_size: bool = True


class DriveDisplayManager:
    """Manages rich CLI display and formatting for Google Drive data."""
    
    def __init__(self, console: Optional[Console] = None):
        """Initialize display manager.
        
        Args:
            console: Rich console instance. If None, creates a new one.
        """
        self.console = console or Console()
        self.config = get_config()
    
    def sort_items(self, items: List[DriveItem], 
                   sort_by: SortBy = SortBy.SIZE, 
                   reverse: bool = True) -> List[DriveItem]:
        """Sort items by specified criteria.
        
        Args:
            items: List of DriveItem objects to sort
            sort_by: Sorting criteria
            reverse: If True, sort in descending order
            
        Returns:
            Sorted list of items
        """
        if sort_by == SortBy.SIZE:
            return sorted(items, key=lambda x: x.display_size, reverse=reverse)
        elif sort_by == SortBy.NAME:
            return sorted(items, key=lambda x: x.name.lower(), reverse=reverse)
        elif sort_by == SortBy.MODIFIED:
            return sorted(items, key=lambda x: x.modified_time or datetime.min, reverse=reverse)
        elif sort_by == SortBy.TYPE:
            return sorted(items, key=lambda x: (x.type, x.display_size), reverse=reverse)
        elif sort_by == SortBy.COUNT:
            return sorted(items, key=lambda x: x.file_count if x.is_folder else 0, reverse=reverse)
        else:
            return items
    
    def filter_items(self, items: List[DriveItem], 
                     filters: Optional[FilterOptions] = None) -> List[DriveItem]:
        """Filter items based on criteria.
        
        Args:
            items: List of items to filter
            filters: Filter criteria
            
        Returns:
            Filtered list of items
        """
        if not filters:
            return items
        
        filtered = []
        
        for item in items:
            # Type filtering
            if not filters.include_folders and item.is_folder:
                continue
            if not filters.include_files and not item.is_folder:
                continue
            
            # Item type filtering
            if filters.item_types and item.type not in filters.item_types:
                continue
            
            # Size filtering
            if filters.min_size is not None and item.display_size < filters.min_size:
                continue
            if filters.max_size is not None and item.display_size > filters.max_size:
                continue
            
            # Zero size filtering
            if not filters.show_zero_size and item.display_size == 0:
                continue
            
            # Date filtering
            if item.modified_time:
                if filters.modified_after and item.modified_time < filters.modified_after:
                    continue
                if filters.modified_before and item.modified_time > filters.modified_before:
                    continue
            
            # Name pattern filtering
            if filters.name_pattern:
                import re
                if not re.search(filters.name_pattern, item.name, re.IGNORECASE):
                    continue
            
            filtered.append(item)
        
        return filtered
    
    def display_table(self, items: List[DriveItem], 
                      title: str = "Google Drive Items",
                      sort_by: SortBy = SortBy.SIZE,
                      limit: Optional[int] = None,
                      show_path: bool = False) -> None:
        """Display items in a rich table format.
        
        Args:
            items: Items to display
            title: Table title
            sort_by: How to sort the items
            limit: Maximum number of items to show
            show_path: Whether to show full path
        """
        # Sort items
        sorted_items = self.sort_items(items, sort_by, reverse=True)
        
        # Apply limit
        if limit:
            sorted_items = sorted_items[:limit]
        
        # Create table
        table = Table(title=title, show_header=True, header_style="bold cyan")
        
        # Add columns
        table.add_column("Name", style="cyan", no_wrap=False, min_width=20)
        table.add_column("Type", style="magenta", width=12)
        table.add_column("Size", style="green", justify="right", width=10)
        
        if show_path:
            table.add_column("Path", style="blue", no_wrap=False)
        
        table.add_column("Modified", style="yellow", width=12)
        table.add_column("Details", style="dim", width=15)
        
        # Add rows
        for item in sorted_items:
            # Name with icon
            name_text = self._get_item_icon(item) + " " + item.name
            
            # Type
            type_text = self._format_item_type(item)
            
            # Size
            if item.display_size > 0:
                size_text = format_file_size(item.display_size)
            elif item.is_google_workspace_file:
                size_text = "G-Workspace"
            else:
                size_text = "-"
            
            # Path (if requested)
            path_text = item.path if show_path else None
            
            # Modified date
            modified_text = self._format_date(item.modified_time)
            
            # Details (file count for folders, etc.)
            details_text = self._get_item_details(item)
            
            # Add row
            row = [name_text, type_text, size_text]
            if show_path:
                row.append(path_text or "")
            row.extend([modified_text, details_text])
            
            table.add_row(*row)
        
        # Display table
        self.console.print(table)
        
        # Show summary
        if len(sorted_items) < len(items):
            self.console.print(f"\n[dim]Showing {len(sorted_items)} of {len(items)} items[/dim]")
    
    def display_tree(self, structure: DriveStructure, 
                     max_depth: int = 3,
                     min_size: int = 0,
                     show_size: bool = True) -> None:
        """Display folder structure as a tree.
        
        Args:
            structure: Drive structure to display
            max_depth: Maximum depth to show
            min_size: Minimum size threshold for display
            show_size: Whether to show sizes in tree
        """
        tree = Tree("📁 Google Drive", style="bold blue")
        
        # Add root folders
        for folder in structure.root_folders:
            if folder.calculated_size and folder.calculated_size >= min_size:
                self._add_tree_node(tree, folder, max_depth, min_size, show_size)
        
        # Add root files if any
        if structure.root_files:
            files_node = tree.add("📄 Root Files", style="dim")
            for file in structure.root_files[:10]:  # Limit root files display
                if file.size >= min_size:
                    size_text = f" ({format_file_size(file.size)})" if show_size else ""
                    files_node.add(f"{self._get_item_icon(file)} {file.name}{size_text}")
        
        self.console.print(tree)
    
    def _add_tree_node(self, parent_node, item: DriveItem, 
                       max_depth: int, min_size: int, 
                       show_size: bool, current_depth: int = 0) -> None:
        """Recursively add tree nodes."""
        if current_depth >= max_depth:
            return
        
        # Format node label
        size_text = ""
        if show_size and item.display_size > 0:
            size_text = f" ({format_file_size(item.display_size)})"
        
        details = ""
        if item.is_folder and (item.file_count > 0 or item.folder_count > 0):
            details = f" [{item.file_count} files, {item.folder_count} folders]"
        
        node_label = f"{self._get_item_icon(item)} {item.name}{size_text}{details}"
        node = parent_node.add(node_label)
        
        # Add children if it's a folder
        if item.is_folder and current_depth < max_depth - 1:
            # Sort children by size
            sorted_children = self.sort_items(item.children, SortBy.SIZE)
            
            # Add folders first
            folders = [child for child in sorted_children if child.is_folder]
            for child in folders[:10]:  # Limit display
                if child.calculated_size and child.calculated_size >= min_size:
                    self._add_tree_node(node, child, max_depth, min_size, show_size, current_depth + 1)
            
            # Add some files
            files = [child for child in sorted_children if not child.is_folder]
            if files:
                files_shown = 0
                for child in files:
                    if child.size >= min_size and files_shown < 5:
                        file_size = f" ({format_file_size(child.size)})" if show_size else ""
                        node.add(f"{self._get_item_icon(child)} {child.name}{file_size}")
                        files_shown += 1
                
                if len(files) > 5:
                    node.add(f"[dim]... and {len(files) - 5} more files[/dim]")
    
    def display_summary(self, structure: DriveStructure) -> None:
        """Display summary statistics.
        
        Args:
            structure: Drive structure to summarize
        """
        stats = structure.get_folder_stats()
        
        # Create summary panel
        summary_text = f"""
[bold cyan]📊 Drive Summary[/bold cyan]

[bold]Total Items:[/bold] {stats['total_items']:,}
[bold]Files:[/bold] {stats['total_files']:,}
[bold]Folders:[/bold] {stats['total_folders']:,}
[bold]Total Size:[/bold] {format_file_size(stats['total_size'])}
[bold]Root Folders:[/bold] {stats['root_folders']}
[bold]Root Files:[/bold] {stats['root_files']}

[bold]Scan Status:[/bold] {'✅ Complete' if stats['scan_complete'] else '⏳ In Progress'}
[bold]Last Scan:[/bold] {stats['scan_timestamp'] or 'Never'}
        """
        
        panel = Panel(summary_text.strip(), title="Google Drive Statistics", border_style="blue")
        self.console.print(panel)
    
    def display_largest_items(self, structure: DriveStructure, 
                             item_type: str = "both",
                             limit: int = 20) -> None:
        """Display largest files or folders.
        
        Args:
            structure: Drive structure
            item_type: "files", "folders", or "both"
            limit: Number of items to show
        """
        if item_type in ["files", "both"]:
            files = [item for item in structure.all_items.values() 
                    if not item.is_folder and item.size > 0]
            files.sort(key=lambda x: x.size, reverse=True)
            
            if files:
                self.display_table(
                    files[:limit], 
                    f"🔥 Largest Files (Top {min(limit, len(files))})",
                    sort_by=SortBy.SIZE
                )
        
        if item_type in ["folders", "both"]:
            folders = [item for item in structure.all_items.values() 
                      if item.is_folder and item.calculated_size and item.calculated_size > 0]
            folders.sort(key=lambda x: x.calculated_size, reverse=True)
            
            if folders:
                if item_type == "both":
                    self.console.print()  # Add spacing
                
                self.display_table(
                    folders[:limit], 
                    f"📁 Largest Folders (Top {min(limit, len(folders))})",
                    sort_by=SortBy.SIZE
                )
    
    def display_compact_list(self, items: List[DriveItem], 
                           title: str = "Items",
                           limit: Optional[int] = None) -> None:
        """Display items in a compact list format.
        
        Args:
            items: Items to display
            title: List title  
            limit: Maximum items to show
        """
        sorted_items = self.sort_items(items, SortBy.SIZE, reverse=True)
        if limit:
            sorted_items = sorted_items[:limit]
        
        self.console.print(f"\n[bold cyan]{title}[/bold cyan]")
        self.console.print("─" * 60)
        
        for i, item in enumerate(sorted_items, 1):
            icon = self._get_item_icon(item)
            size = format_file_size(item.display_size) if item.display_size > 0 else "-"
            
            # Color code by size
            if item.display_size > 1024**3:  # > 1GB
                size_style = "red bold"
            elif item.display_size > 1024**2:  # > 1MB  
                size_style = "yellow"
            else:
                size_style = "green"
            
            self.console.print(f"{i:2d}. {icon} {item.name:<40} [{size_style}]{size:>10}[/{size_style}]")
        
        if len(sorted_items) < len(items):
            self.console.print(f"\n[dim]... and {len(items) - len(sorted_items)} more items[/dim]")
    
    def _get_item_icon(self, item: DriveItem) -> str:
        """Get emoji icon for item type."""
        if item.is_folder:
            return "📁"
        elif item.type == ItemType.GOOGLE_DOC:
            return "📄"
        elif item.type == ItemType.GOOGLE_SHEET:
            return "📊"
        elif item.type == ItemType.GOOGLE_SLIDE:
            return "📋"
        elif item.type == ItemType.GOOGLE_FORM:
            return "📝"
        elif item.type == ItemType.GOOGLE_DRAWING:
            return "🎨"
        elif "image" in item.mime_type:
            return "🖼️"
        elif "video" in item.mime_type:
            return "🎥"
        elif "audio" in item.mime_type:
            return "🎵"
        elif "pdf" in item.mime_type:
            return "📕"
        else:
            return "📄"
    
    def _format_item_type(self, item: DriveItem) -> str:
        """Format item type for display."""
        if item.is_folder:
            return "Folder"
        elif item.is_google_workspace_file:
            return f"Google {item.type.replace('google_', '').title()}"
        else:
            return "File"
    
    def _format_date(self, date: Optional[datetime]) -> str:
        """Format date for display."""
        if not date:
            return "-"
        
        now = datetime.now(date.tzinfo)
        diff = now - date
        
        if diff.days == 0:
            return "Today"
        elif diff.days == 1:
            return "Yesterday"
        elif diff.days < 7:
            return f"{diff.days}d ago"
        elif diff.days < 30:
            return f"{diff.days // 7}w ago"
        elif diff.days < 365:
            return f"{diff.days // 30}mo ago"
        else:
            return f"{diff.days // 365}y ago"
    
    def _get_item_details(self, item: DriveItem) -> str:
        """Get additional details for display."""
        if item.is_folder:
            if item.file_count > 0 or item.folder_count > 0:
                return f"{item.file_count}f, {item.folder_count}d"
            else:
                return "Empty"
        elif item.is_shared:
            return "Shared"
        elif item.is_starred:
            return "Starred"
        else:
            return ""


def parse_size_string(size_str: str) -> int:
    """Parse human-readable size string to bytes.
    
    Args:
        size_str: Size string like "10MB", "1.5GB", etc.
        
    Returns:
        Size in bytes
    """
    size_str = size_str.upper().strip()
    
    # Extract number and unit
    import re
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([KMGT]?B?)$', size_str)
    if not match:
        raise ValueError(f"Invalid size format: {size_str}")
    
    number = float(match.group(1))
    unit = match.group(2) or 'B'
    
    # Convert to bytes
    multipliers = {
        'B': 1,
        'KB': 1024,
        'MB': 1024**2,
        'GB': 1024**3,
        'TB': 1024**4
    }
    
    return int(number * multipliers.get(unit, 1))