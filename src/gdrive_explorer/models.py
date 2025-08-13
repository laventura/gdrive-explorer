"""Data models for Google Drive Explorer."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, validator


class ItemType(str, Enum):
    """File/folder type enumeration."""
    FILE = "file"
    FOLDER = "folder"
    GOOGLE_DOC = "google_doc"
    GOOGLE_SHEET = "google_sheet"
    GOOGLE_SLIDE = "google_slide"
    GOOGLE_FORM = "google_form"
    GOOGLE_DRAWING = "google_drawing"
    UNKNOWN = "unknown"


class DriveItem(BaseModel):
    """Represents a file or folder in Google Drive."""
    
    id: str = Field(..., description="Google Drive file ID")
    name: str = Field(..., description="File/folder name")
    type: ItemType = Field(..., description="Item type")
    mime_type: str = Field(..., description="MIME type from Google Drive")
    size: int = Field(default=0, description="Size in bytes (0 for Google Workspace files)")
    parent_ids: List[str] = Field(default_factory=list, description="Parent folder IDs")
    created_time: Optional[datetime] = Field(None, description="Creation timestamp")
    modified_time: Optional[datetime] = Field(None, description="Last modification timestamp")
    path: str = Field(default="", description="Full path from root")
    is_owned_by_me: bool = Field(default=True, description="Whether I own this file")
    is_shared: bool = Field(default=False, description="Whether file is shared")
    is_starred: bool = Field(default=False, description="Whether file is starred")
    is_trashed: bool = Field(default=False, description="Whether file is in trash")
    web_view_link: Optional[str] = Field(None, description="Link to view in browser")
    
    # Calculated fields for folder analysis
    children: List['DriveItem'] = Field(default_factory=list, description="Child items (for folders)")
    calculated_size: Optional[int] = Field(None, description="Calculated folder size including children")
    file_count: int = Field(default=0, description="Total files in folder (recursive)")
    folder_count: int = Field(default=0, description="Total subfolders in folder (recursive)")
    
    # Metadata for caching and processing
    last_scanned: Optional[datetime] = Field(None, description="When this item was last scanned")
    scan_complete: bool = Field(default=False, description="Whether folder scan is complete")
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        arbitrary_types_allowed = True
    
    @validator('type', pre=True)
    def determine_type(cls, v, values):
        """Determine item type from MIME type if not explicitly set."""
        if isinstance(v, str) and v in ItemType.__members__.values():
            return v
        
        mime_type = values.get('mime_type', '')
        
        if mime_type == 'application/vnd.google-apps.folder':
            return ItemType.FOLDER
        elif mime_type == 'application/vnd.google-apps.document':
            return ItemType.GOOGLE_DOC
        elif mime_type == 'application/vnd.google-apps.spreadsheet':
            return ItemType.GOOGLE_SHEET
        elif mime_type == 'application/vnd.google-apps.presentation':
            return ItemType.GOOGLE_SLIDE
        elif mime_type == 'application/vnd.google-apps.form':
            return ItemType.GOOGLE_FORM
        elif mime_type == 'application/vnd.google-apps.drawing':
            return ItemType.GOOGLE_DRAWING
        elif 'google-apps' in mime_type:
            return ItemType.UNKNOWN
        else:
            return ItemType.FILE
    
    @property
    def is_folder(self) -> bool:
        """Check if this item is a folder."""
        return self.type == ItemType.FOLDER
    
    @property
    def is_google_workspace_file(self) -> bool:
        """Check if this is a Google Workspace file (Docs, Sheets, etc.)."""
        return self.type in [
            ItemType.GOOGLE_DOC,
            ItemType.GOOGLE_SHEET, 
            ItemType.GOOGLE_SLIDE,
            ItemType.GOOGLE_FORM,
            ItemType.GOOGLE_DRAWING
        ]
    
    @property
    def display_size(self) -> int:
        """Get the size to display (calculated size for folders, actual size for files)."""
        if self.is_folder and self.calculated_size is not None:
            return self.calculated_size
        return self.size
    
    @property
    def has_size(self) -> bool:
        """Check if this item contributes to storage usage."""
        return self.size > 0 or (self.is_folder and self.calculated_size and self.calculated_size > 0)
    
    def add_child(self, child: 'DriveItem') -> None:
        """Add a child item to this folder."""
        if not self.is_folder:
            raise ValueError("Cannot add children to non-folder items")
        
        # Avoid duplicates
        if child.id not in [c.id for c in self.children]:
            self.children.append(child)
            child.path = f"{self.path}/{child.name}".lstrip("/")
    
    def calculate_folder_size(self) -> int:
        """Calculate total size of folder including all children recursively."""
        if not self.is_folder:
            return self.size
        
        total_size = 0
        files = 0
        folders = 0
        
        for child in self.children:
            if child.is_folder:
                folders += 1
                if child.calculated_size is not None:
                    total_size += child.calculated_size
                else:
                    total_size += child.calculate_folder_size()
                folders += child.folder_count
                files += child.file_count
            else:
                files += 1
                total_size += child.size
        
        self.calculated_size = total_size
        self.file_count = files
        self.folder_count = folders
        
        return total_size
    
    def get_all_children(self, include_folders: bool = True) -> List['DriveItem']:
        """Get all children recursively."""
        all_children = []
        
        for child in self.children:
            if child.is_folder:
                if include_folders:
                    all_children.append(child)
                all_children.extend(child.get_all_children(include_folders))
            else:
                all_children.append(child)
        
        return all_children
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for export."""
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'size': self.size,
            'calculated_size': self.calculated_size,
            'file_count': self.file_count,
            'folder_count': self.folder_count,
            'path': self.path,
            'created_time': self.created_time.isoformat() if self.created_time else None,
            'modified_time': self.modified_time.isoformat() if self.modified_time else None,
            'is_owned_by_me': self.is_owned_by_me,
            'is_shared': self.is_shared,
            'is_starred': self.is_starred,
            'web_view_link': self.web_view_link
        }
    
    @classmethod
    def from_drive_api(cls, api_data: Dict[str, Any]) -> 'DriveItem':
        """Create DriveItem from Google Drive API response."""
        # Parse timestamps
        created_time = None
        modified_time = None
        
        if 'createdTime' in api_data:
            try:
                created_time = datetime.fromisoformat(api_data['createdTime'].replace('Z', '+00:00'))
            except ValueError:
                pass
        
        if 'modifiedTime' in api_data:
            try:
                modified_time = datetime.fromisoformat(api_data['modifiedTime'].replace('Z', '+00:00'))
            except ValueError:
                pass
        
        # Parse size
        size = 0
        if 'size' in api_data:
            try:
                size = int(api_data['size'])
            except (ValueError, TypeError):
                size = 0
        
        return cls(
            id=api_data['id'],
            name=api_data.get('name', 'Unknown'),
            mime_type=api_data.get('mimeType', ''),
            size=size,
            parent_ids=api_data.get('parents', []),
            created_time=created_time,
            modified_time=modified_time,
            is_owned_by_me=api_data.get('ownedByMe', True),
            is_shared=api_data.get('shared', False),
            is_starred=api_data.get('starred', False),
            is_trashed=api_data.get('trashed', False),
            web_view_link=api_data.get('webViewLink'),
            last_scanned=datetime.now()
        )


class DriveStructure(BaseModel):
    """Represents the complete Google Drive structure."""
    
    root_folders: List[DriveItem] = Field(default_factory=list, description="Top-level folders")
    root_files: List[DriveItem] = Field(default_factory=list, description="Top-level files")
    all_items: Dict[str, DriveItem] = Field(default_factory=dict, description="All items by ID")
    total_files: int = Field(default=0, description="Total number of files")
    total_folders: int = Field(default=0, description="Total number of folders")
    total_size: int = Field(default=0, description="Total size in bytes")
    scan_timestamp: Optional[datetime] = Field(None, description="When scan was completed")
    scan_complete: bool = Field(default=False, description="Whether scan is complete")
    
    def add_item(self, item: DriveItem) -> None:
        """Add an item to the structure."""
        self.all_items[item.id] = item
        
        if item.is_folder:
            self.total_folders += 1
        else:
            self.total_files += 1
            self.total_size += item.size
    
    def get_item(self, item_id: str) -> Optional[DriveItem]:
        """Get item by ID."""
        return self.all_items.get(item_id)
    
    def build_hierarchy(self) -> None:
        """Build the hierarchical structure from flat item list."""
        # First pass: identify root items and build parent-child relationships
        for item in self.all_items.values():
            if not item.parent_ids:
                # Root item
                if item.is_folder:
                    self.root_folders.append(item)
                else:
                    self.root_files.append(item)
                item.path = item.name
            else:
                # Find parents and add as child
                for parent_id in item.parent_ids:
                    parent = self.all_items.get(parent_id)
                    if parent and parent.is_folder:
                        parent.add_child(item)
                        break
        
        # Second pass: calculate folder sizes
        for folder in self.root_folders:
            folder.calculate_folder_size()
    
    def get_largest_items(self, limit: int = 100, folders_only: bool = False) -> List[DriveItem]:
        """Get largest items sorted by size."""
        items = []
        
        for item in self.all_items.values():
            if folders_only and not item.is_folder:
                continue
            if item.has_size:
                items.append(item)
        
        # Sort by display size (calculated size for folders, actual size for files)
        items.sort(key=lambda x: x.display_size, reverse=True)
        
        return items[:limit]
    
    def get_folder_stats(self) -> Dict[str, Any]:
        """Get statistics about the folder structure."""
        return {
            'total_items': len(self.all_items),
            'total_files': self.total_files,
            'total_folders': self.total_folders,
            'total_size': self.total_size,
            'root_folders': len(self.root_folders),
            'root_files': len(self.root_files),
            'scan_complete': self.scan_complete,
            'scan_timestamp': self.scan_timestamp.isoformat() if self.scan_timestamp else None
        }


# Update forward references
DriveItem.model_rebuild()