"""Command-line interface for Google Drive Explorer."""

import click
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from .auth import DriveAuthenticator
from .client import DriveClient
from .config import get_config
from .utils import setup_logging, format_file_size
from .explorer import DriveExplorer
from .cache import get_cache
from .display import DriveDisplayManager, SortBy, DisplayFormat, FilterOptions, parse_size_string


console = Console()


@click.group()
@click.option('--config', '-c', help='Path to configuration file')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.pass_context
def main(ctx, config, verbose):
    """Google Drive Explorer - Analyze your Google Drive storage usage."""
    # Ensure context object exists
    ctx.ensure_object(dict)
    
    # Set up configuration
    if config:
        ctx.obj['config_file'] = config
    
    # Set up logging
    app_config = get_config()
    log_level = "DEBUG" if verbose else app_config.logging.level
    setup_logging(level=log_level, log_file=app_config.logging.file)


@main.command()
@click.option('--force', '-f', is_flag=True, help='Force re-authentication')
def auth(force):
    """Authenticate with Google Drive API."""
    try:
        authenticator = DriveAuthenticator()
        
        if force:
            authenticator.clear_credentials()
            rprint("[yellow]Forcing re-authentication...[/yellow]")
        
        if authenticator.is_authenticated() and not force:
            rprint("[green]✓ Already authenticated with Google Drive[/green]")
            return
        
        rprint("[blue]Starting OAuth authentication...[/blue]")
        credentials = authenticator.authenticate()
        
        if credentials and credentials.valid:
            rprint("[green]✓ Successfully authenticated with Google Drive![/green]")
        else:
            rprint("[red]✗ Authentication failed[/red]")
            
    except Exception as e:
        rprint(f"[red]Authentication error: {e}[/red]")


@main.command()
@click.option('--limit', '-l', default=20, help='Number of files to display')
def test(limit):
    """Test connection and list some files from Google Drive."""
    try:
        rprint("[blue]Testing Google Drive connection...[/blue]")
        
        # Initialize client
        client = DriveClient()
        
        # Test connection
        if not client.test_connection():
            rprint("[red]✗ Failed to connect to Google Drive[/red]")
            rprint("[yellow]Try running: gdrive-explorer auth[/yellow]")
            return
        
        rprint("[green]✓ Successfully connected to Google Drive[/green]")
        
        # Fetch some files to test
        rprint(f"[blue]Fetching first {limit} files...[/blue]")
        result = client.list_files(page_size=limit)
        files = result.get('files', [])
        
        if not files:
            rprint("[yellow]No files found in your Google Drive[/yellow]")
            return
        
        # Display results in a table
        table = Table(title=f"Google Drive Files (showing first {len(files)})")
        table.add_column("Name", style="cyan", no_wrap=False)
        table.add_column("Type", style="magenta")
        table.add_column("Size", style="green", justify="right")
        table.add_column("Modified", style="blue")
        
        for file in files:
            name = file.get('name', 'Unknown')
            mime_type = file.get('mimeType', '')
            
            # Determine file type
            if client.is_folder(file):
                file_type = "Folder"
            elif 'google-apps' in mime_type:
                file_type = "Google Doc"
            else:
                file_type = "File"
            
            # Format size
            size = client.get_file_size(file)
            size_str = format_file_size(size) if size > 0 else "-"
            
            # Format date
            modified = file.get('modifiedTime', '')
            if modified:
                # Simple date formatting (just take the date part)
                modified = modified.split('T')[0]
            
            table.add_row(name, file_type, size_str, modified)
        
        console.print(table)
        rprint(f"[green]✓ Successfully listed {len(files)} items[/green]")
        
    except Exception as e:
        rprint(f"[red]Error testing connection: {e}[/red]")


@main.command()
def info():
    """Show application information and configuration."""
    config = get_config()
    
    # Create info table
    table = Table(title="Google Drive Explorer - Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    
    # Add configuration info
    table.add_row("Credentials File", config.auth.credentials_file)
    table.add_row("Token File", config.auth.token_file)
    table.add_row("Cache Enabled", str(config.cache.enabled))
    table.add_row("Cache TTL", f"{config.cache.ttl_hours} hours")
    table.add_row("Log Level", config.logging.level)
    table.add_row("Default Format", config.display.default_format)
    table.add_row("Show Progress", str(config.display.show_progress))
    
    console.print(table)


@main.command()
def clear_auth():
    """Clear stored authentication credentials."""
    try:
        authenticator = DriveAuthenticator()
        authenticator.clear_credentials()
        rprint("[green]✓ Authentication credentials cleared[/green]")
        rprint("[yellow]You'll need to re-authenticate next time[/yellow]")
    except Exception as e:
        rprint(f"[red]Error clearing credentials: {e}[/red]")


@main.command()
@click.option('--limit', '-l', default=100, help='Number of items to display')
@click.option('--format', '-f', type=click.Choice(['table', 'tree', 'compact']), default='table', help='Display format')
@click.option('--sort', '-s', type=click.Choice(['size', 'name', 'modified', 'type']), default='size', help='Sort by')
@click.option('--min-size', help='Minimum size filter (e.g., 10MB)')
@click.option('--max-size', help='Maximum size filter (e.g., 1GB)')
@click.option('--type', 'item_type', type=click.Choice(['files', 'folders', 'both']), default='both', help='Item type to show')
@click.option('--cache/--no-cache', default=True, help='Use cached data if available')
@click.option('--path/--no-path', default=False, help='Show full path in table view')
def scan(limit, format, sort, min_size, max_size, item_type, cache, path):
    """Scan and analyze Google Drive with rich visualization."""
    try:
        rprint("[blue]🔍 Scanning Google Drive...[/blue]")
        
        # Initialize display manager
        display = DriveDisplayManager(console)
        
        # Create filters
        filters = FilterOptions()
        if min_size:
            filters.min_size = parse_size_string(min_size)
        if max_size:
            filters.max_size = parse_size_string(max_size)
        
        filters.include_files = item_type in ['files', 'both']
        filters.include_folders = item_type in ['folders', 'both']
        
        # Get data (for now, use basic API call - full scan will be Phase 3)
        client = DriveClient()
        
        # Check cache first
        if cache:
            cached_structure = get_cache().get_structure()
            if cached_structure:
                rprint("[green]✓ Using cached drive structure[/green]")
                display.display_summary(cached_structure)
                return
        
        rprint("[blue]Fetching data from Google Drive API...[/blue]")
        rprint(f"[yellow]Note: Limited preview with {limit * 2} items[/yellow]")
        
        # Get sample data
        result = client.list_files(page_size=min(limit * 2, 1000))
        files = result.get('files', [])
        
        # Convert to DriveItem objects
        from .models import DriveItem
        items = []
        for file_data in files:
            try:
                item = DriveItem.from_drive_api(file_data)
                items.append(item)
            except Exception as e:
                continue
        
        rprint(f"[green]✓ Loaded {len(items)} items[/green]")
        
        # Apply filters
        filtered_items = display.filter_items(items, filters)
        
        if not filtered_items:
            rprint("[yellow]No items match the specified criteria[/yellow]")
            return
        
        # Display based on format
        sort_by = SortBy(sort)
        
        if format == 'table':
            display.display_table(
                filtered_items, 
                title=f"Google Drive Analysis - {item_type.title()}",
                sort_by=sort_by,
                limit=limit,
                show_path=path
            )
        elif format == 'compact':
            display.display_compact_list(
                filtered_items,
                title=f"Google Drive - {item_type.title()} (sorted by {sort})",
                limit=limit
            )
        elif format == 'tree':
            # For tree view, we need folder structure
            folders = [item for item in filtered_items if item.is_folder]
            if folders:
                rprint("[yellow]Tree view with sample folder structure:[/yellow]")
                # Create a mock structure for demo
                from .models import DriveStructure
                structure = DriveStructure()
                for item in items:
                    structure.add_item(item)
                structure.build_hierarchy()
                display.display_tree(structure, max_depth=3, min_size=filters.min_size or 0)
            else:
                rprint("[yellow]No folders found for tree view[/yellow]")
        
        # Show summary stats
        total_size = sum(item.display_size for item in filtered_items)
        rprint(f"\n[dim]Showing {len(filtered_items)} items, total size: {format_file_size(total_size)}[/dim]")
        
    except Exception as e:
        rprint(f"[red]Error during scan: {e}[/red]")
        import traceback
        if click.get_current_context().find_root().params.get('verbose'):
            rprint(f"[red]{traceback.format_exc()}[/red]")


@main.command()
def cache():
    """Show cache information and statistics."""
    try:
        cache_instance = get_cache()
        stats = cache_instance.get_cache_stats()
        
        if not stats.get('enabled', False):
            rprint("[yellow]Cache is disabled[/yellow]")
            return
        
        # Create cache stats table
        table = Table(title="Cache Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")
        
        table.add_row("Cached Items", str(stats.get('items_count', 0)))
        table.add_row("Cached Structures", str(stats.get('structures_count', 0)))
        table.add_row("Total Size", f"{stats.get('total_size_mb', 0):.2f} MB")
        table.add_row("Database Size", f"{stats.get('database_size_mb', 0):.2f} MB")
        table.add_row("Expired Entries", str(stats.get('expired_count', 0)))
        
        console.print(table)
        
        if stats.get('expired_count', 0) > 0:
            rprint("[yellow]Run 'gdrive-explorer cache --clear-expired' to clean up[/yellow]")
        
    except Exception as e:
        rprint(f"[red]Error getting cache stats: {e}[/red]")


@main.command('cache-clear')
@click.option('--expired-only', is_flag=True, help='Only clear expired entries')
def cache_clear(expired_only):
    """Clear cache data."""
    try:
        cache_instance = get_cache()
        
        if expired_only:
            removed = cache_instance.clear_expired()
            rprint(f"[green]✓ Removed {removed} expired cache entries[/green]")
        else:
            if click.confirm("This will clear all cached data. Continue?"):
                cache_instance.clear_all()
                rprint("[green]✓ Cache cleared successfully[/green]")
            else:
                rprint("[yellow]Operation cancelled[/yellow]")
                
    except Exception as e:
        rprint(f"[red]Error clearing cache: {e}[/red]")


@main.command()
@click.option('--limit', '-l', default=20, help='Number of largest items to show')
@click.option('--type', 'item_type', type=click.Choice(['files', 'folders', 'both']), default='both', help='Show files, folders, or both')
def largest(limit, item_type):
    """Show the largest files and folders in your Drive."""
    try:
        rprint("[blue]🔍 Finding largest items...[/blue]")
        
        client = DriveClient()
        display = DriveDisplayManager(console)
        
        # Get data
        result = client.list_files(page_size=1000)
        files = result.get('files', [])
        
        # Convert to DriveItem objects
        from .models import DriveItem
        items = []
        for file_data in files:
            try:
                item = DriveItem.from_drive_api(file_data)
                items.append(item)
            except Exception:
                continue
        
        # Separate files and folders
        large_files = [item for item in items if not item.is_folder and item.size > 0]
        large_folders = [item for item in items if item.is_folder]
        
        # Show files
        if item_type in ['files', 'both'] and large_files:
            large_files.sort(key=lambda x: x.size, reverse=True)
            display.display_table(
                large_files[:limit],
                title=f"🔥 Largest Files (Top {min(limit, len(large_files))})",
                sort_by=SortBy.SIZE
            )
        
        # Show folders (note: without full scan, folder sizes aren't calculated)
        if item_type in ['folders', 'both'] and large_folders:
            if item_type == 'both':
                rprint()
            
            rprint("[yellow]📁 Folders (sizes not calculated without full scan):[/yellow]")
            display.display_table(
                large_folders[:limit],
                title=f"📁 Recent Folders (Top {min(limit, len(large_folders))})",
                sort_by=SortBy.MODIFIED
            )
        
    except Exception as e:
        rprint(f"[red]Error finding largest items: {e}[/red]")


@main.command()
@click.option('--depth', '-d', default=3, help='Tree depth to display')
@click.option('--min-size', help='Minimum size to show (e.g., 10MB)')
def tree(depth, min_size):
    """Display your Google Drive as a folder tree."""
    try:
        rprint("[blue]🌳 Building folder tree...[/blue]")
        
        client = DriveClient()
        display = DriveDisplayManager(console)
        
        # Get data
        result = client.list_files(page_size=1000)
        files = result.get('files', [])
        
        # Convert to DriveItem objects and build structure
        from .models import DriveItem, DriveStructure
        structure = DriveStructure()
        
        for file_data in files:
            try:
                item = DriveItem.from_drive_api(file_data)
                structure.add_item(item)
            except Exception:
                continue
        
        structure.build_hierarchy()
        
        # Parse min size
        min_size_bytes = 0
        if min_size:
            min_size_bytes = parse_size_string(min_size)
        
        # Display tree
        display.display_tree(structure, max_depth=depth, min_size=min_size_bytes)
        
        # Show summary
        stats = structure.get_folder_stats()
        rprint(f"\n[dim]Showing structure with {stats['total_folders']} folders and {stats['total_files']} files[/dim]")
        
    except Exception as e:
        rprint(f"[red]Error building tree: {e}[/red]")


@main.command()
def summary():
    """Show summary statistics of your Google Drive."""
    try:
        rprint("[blue]📊 Analyzing Google Drive...[/blue]")
        
        client = DriveClient()
        display = DriveDisplayManager(console)
        
        # Check for cached structure first
        cached_structure = get_cache().get_structure()
        if cached_structure:
            rprint("[green]✓ Using cached data[/green]")
            display.display_summary(cached_structure)
            return
        
        # Get sample data for basic summary
        result = client.list_files(page_size=1000)
        files = result.get('files', [])
        
        # Basic analysis
        total_items = len(files)
        folders = [f for f in files if client.is_folder(f)]
        regular_files = [f for f in files if not client.is_folder(f)]
        total_size = sum(client.get_file_size(f) for f in regular_files)
        
        # Google Workspace files
        workspace_files = [f for f in regular_files if 'google-apps' in f.get('mimeType', '')]
        
        # Create summary
        summary_text = f"""
[bold cyan]📊 Google Drive Summary (Sample)[/bold cyan]

[bold]Total Items:[/bold] {total_items:,} (sample)
[bold]Files:[/bold] {len(regular_files):,}
[bold]Folders:[/bold] {len(folders):,}
[bold]Total Size:[/bold] {format_file_size(total_size)}
[bold]Google Workspace Files:[/bold] {len(workspace_files):,}

[bold yellow]Note:[/bold yellow] This is a sample analysis. For complete analysis, 
run full scan after setting up authentication.
        """
        
        from rich.panel import Panel
        panel = Panel(summary_text.strip(), title="Google Drive Statistics", border_style="blue")
        console.print(panel)
        
    except Exception as e:
        rprint(f"[red]Error generating summary: {e}[/red]")


@main.command()
@click.option('--pattern', '-p', help='Search pattern (regex supported)')
@click.option('--type', 'item_type', type=click.Choice(['files', 'folders', 'both']), default='both', help='Item type to search')
@click.option('--min-size', help='Minimum size filter (e.g., 10MB)')
@click.option('--limit', '-l', default=50, help='Maximum results to show')
def search(pattern, item_type, min_size, limit):
    """Search for files and folders in your Google Drive."""
    try:
        if not pattern:
            rprint("[red]Please provide a search pattern with --pattern[/red]")
            return
        
        rprint(f"[blue]🔍 Searching for: '{pattern}'...[/blue]")
        
        client = DriveClient()
        display = DriveDisplayManager(console)
        
        # Get data
        result = client.list_files(page_size=1000)
        files = result.get('files', [])
        
        # Convert to DriveItem objects
        from .models import DriveItem
        items = []
        for file_data in files:
            try:
                item = DriveItem.from_drive_api(file_data)
                items.append(item)
            except Exception:
                continue
        
        # Create filters
        filters = FilterOptions()
        filters.name_pattern = pattern
        filters.include_files = item_type in ['files', 'both']
        filters.include_folders = item_type in ['folders', 'both']
        
        if min_size:
            filters.min_size = parse_size_string(min_size)
        
        # Apply filters
        filtered_items = display.filter_items(items, filters)
        
        if not filtered_items:
            rprint(f"[yellow]No items found matching '{pattern}'[/yellow]")
            return
        
        # Display results
        display.display_table(
            filtered_items,
            title=f"🔍 Search Results for '{pattern}'",
            sort_by=SortBy.SIZE,
            limit=limit,
            show_path=True
        )
        
        rprint(f"\n[dim]Found {len(filtered_items)} items matching '{pattern}'[/dim]")
        
    except Exception as e:
        rprint(f"[red]Error searching: {e}[/red]")


if __name__ == '__main__':
    main()