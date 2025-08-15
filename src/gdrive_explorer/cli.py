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
@click.option('--full', is_flag=True, help='Perform complete Drive scan with size calculation (Phase 3)')
def scan(limit, format, sort, min_size, max_size, item_type, cache, path, full):
    """Scan and analyze Google Drive with rich visualization."""
    try:
        if full:
            rprint("[blue]🔍 Performing complete Google Drive scan with size calculation...[/blue]")
        else:
            rprint("[blue]🔍 Scanning Google Drive (quick preview)...[/blue]")
        
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
        
        if full:
            # Phase 3: Complete Drive scan with size calculation
            from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
            
            explorer = DriveExplorer()
            structure = None
            
            def progress_callback(message, current, total):
                # This will be handled by the progress display below
                pass
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                
                task = progress.add_task("Scanning Drive...", total=100)
                
                def update_progress(message, current, total):
                    if total > 0:
                        percentage = (current / total) * 100
                        progress.update(task, completed=percentage, description=message)
                
                # Perform complete scan
                structure = explorer.scan_drive_complete(
                    calculate_sizes=True,
                    use_cache=cache,
                    progress_callback=update_progress
                )
            
            rprint(f"[green]✅ Complete scan finished![/green]")
            rprint(f"[blue]Total: {structure.total_files:,} files, {structure.total_folders:,} folders[/blue]")
            rprint(f"[blue]Total size: {format_file_size(structure.total_size)}[/blue]")
            
            # Get items from structure
            items = list(structure.all_items.values())
            
        else:
            # Quick preview mode
            client = DriveClient()
            
            # Check cache first
            if cache:
                cached_structure = get_cache().get_structure()
                if cached_structure and cached_structure.scan_complete:
                    rprint("[green]✓ Using cached complete drive structure[/green]")
                    items = list(cached_structure.all_items.values())
                else:
                    # Fall back to quick scan
                    rprint("[blue]Fetching sample data from Google Drive API...[/blue]")
                    rprint(f"[yellow]Note: Limited preview with {limit * 2} items. Use --full for complete scan.[/yellow]")
                    
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
            else:
                rprint("[blue]Fetching sample data from Google Drive API...[/blue]")
                rprint(f"[yellow]Note: Limited preview with {limit * 2} items. Use --full for complete scan.[/yellow]")
                
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
            if full and 'structure' in locals():
                # Use complete structure from full scan
                display.display_tree(structure, max_depth=3, min_size=filters.min_size or 0)
            else:
                # Create structure from available items
                folders = [item for item in filtered_items if item.is_folder]
                if folders or len(filtered_items) > 0:
                    if not full:
                        rprint("[yellow]Tree view with sample folder structure (use --full for complete tree):[/yellow]")
                    # Create structure for demo
                    from .models import DriveStructure
                    temp_structure = DriveStructure()
                    for item in items:
                        temp_structure.add_item(item)
                    temp_structure.build_hierarchy()
                    display.display_tree(temp_structure, max_depth=3, min_size=filters.min_size or 0)
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
        table.add_row("Complete Scans", str(stats.get('complete_scans', 0)))
        table.add_row("Max Files Scanned", f"{stats.get('max_files_scanned', 0):,}")
        table.add_row("Max Folders Scanned", f"{stats.get('max_folders_scanned', 0):,}")
        table.add_row("Total Scan Errors", str(stats.get('total_scan_errors', 0)))
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


@main.command('full-scan')
@click.option('--cache/--no-cache', default=True, help='Use cached data if available')
@click.option('--force', '-f', is_flag=True, help='Force complete rescan even if cache exists')
def full_scan(cache, force):
    """Perform a complete Google Drive scan with size calculation (Phase 3)."""
    try:
        rprint("[blue]🚀 Starting complete Google Drive analysis...[/blue]")
        
        if force:
            cache = False
            rprint("[yellow]⚡ Forcing complete rescan (ignoring cache)[/yellow]")
        
        # Initialize components
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
        explorer = DriveExplorer()
        display = DriveDisplayManager(console)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            
            task = progress.add_task("Initializing scan...", total=100)
            
            def update_progress(message, current, total):
                if total > 0:
                    percentage = (current / total) * 100
                    progress.update(task, completed=percentage, description=message)
            
            # Perform complete scan with size calculation
            structure = explorer.scan_drive_complete(
                calculate_sizes=True,
                use_cache=cache,
                progress_callback=update_progress
            )
        
        rprint(f"[green]✅ Complete analysis finished![/green]")
        
        # Display comprehensive summary
        display.display_summary(structure)
        
        # Analyze Google Workspace files
        workspace_analysis = explorer.calculator.analyze_google_workspace_files(structure)
        if workspace_analysis['total_workspace_files'] > 0:
            rprint(f"\n[bold cyan]📄 Google Workspace Files Analysis:[/bold cyan]")
            rprint(f"[green]Total Workspace Files:[/green] {workspace_analysis['total_workspace_files']:,}")
            rprint(f"[green]Percentage of Files:[/green] {workspace_analysis['percentage_of_total_files']:.1f}%")
            rprint(f"[green]Most Common Type:[/green] {workspace_analysis['most_common_type'] or 'N/A'}")
            
            if workspace_analysis['workspace_types']:
                rprint("[dim]Types breakdown:[/dim]")
                for file_type, data in workspace_analysis['workspace_types'].items():
                    rprint(f"  • {file_type.replace('google_', '').title()}: {data['count']:,} files")
        
        # Show largest folders with calculated sizes
        if structure.total_folders > 0:
            rprint("\n[bold cyan]📁 Largest Folders (by calculated size):[/bold cyan]")
            largest_folders = explorer.find_largest_folders(structure, limit=10)
            if largest_folders:
                display.display_table(
                    largest_folders,
                    title="🔥 Top 10 Largest Folders",
                    sort_by=SortBy.SIZE,
                    limit=10
                )
            else:
                rprint("[yellow]No folders with calculated sizes found[/yellow]")
        
        # Show largest files
        rprint("\n[bold cyan]📄 Largest Files:[/bold cyan]")
        largest_files = explorer.find_largest_files(structure, limit=10)
        if largest_files:
            display.display_table(
                largest_files,
                title="🔥 Top 10 Largest Files",
                sort_by=SortBy.SIZE,
                limit=10
            )
        
        rprint(f"\n[green]✨ Analysis complete! Use other commands to explore your {structure.total_files:,} files and {structure.total_folders:,} folders.[/green]")
        rprint("[dim]💡 Try: gdrive-explorer scan --full --format tree[/dim]")
        
    except PermissionError as e:
        rprint(f"[red]Permission Error: {e}[/red]")
        rprint("[yellow]💡 This might be due to:[/yellow]")
        rprint("   • Insufficient Google Drive API permissions")
        rprint("   • Files shared from other accounts that you can't access")
        rprint("   • Try re-authenticating: gdrive-explorer auth --force")
    except Exception as e:
        rprint(f"[red]Error during full scan: {e}[/red]")
        
        # Provide helpful suggestions based on error type
        error_str = str(e).lower()
        if "quota" in error_str or "rate" in error_str:
            rprint("[yellow]💡 Google Drive API quota exceeded. Try again later.[/yellow]")
        elif "permission" in error_str or "insufficient" in error_str:
            rprint("[yellow]💡 Try re-authenticating: gdrive-explorer auth --force[/yellow]")
        elif "network" in error_str or "connection" in error_str:
            rprint("[yellow]💡 Network issues detected. Check your internet connection.[/yellow]")
        
        import traceback
        if click.get_current_context().find_root().params.get('verbose'):
            rprint(f"[red]{traceback.format_exc()}[/red]")


@main.command()
@click.option('--limit', '-l', default=20, help='Number of largest items to show')
@click.option('--type', 'item_type', type=click.Choice(['files', 'folders', 'both']), default='both', help='Show files, folders, or both')
def largest(limit, item_type):
    """Show the largest files and folders in your Drive."""
    try:
        rprint("[blue]🔍 Finding largest items...[/blue]")
        
        display = DriveDisplayManager(console)
        
        # Check for complete cached structure first
        cached_structure = get_cache().get_structure()
        if cached_structure and cached_structure.scan_complete:
            rprint("[green]✓ Using complete cached Drive structure[/green]")
            
            explorer = DriveExplorer()
            
            # Show files
            if item_type in ['files', 'both']:
                large_files = explorer.find_largest_files(cached_structure, limit=limit)
                if large_files:
                    display.display_table(
                        large_files,
                        title=f"🔥 Largest Files (Top {len(large_files)})",
                        sort_by=SortBy.SIZE
                    )
                else:
                    rprint("[yellow]No large files found[/yellow]")
            
            # Show folders with calculated sizes
            if item_type in ['folders', 'both']:
                if item_type == 'both':
                    rprint()
                
                large_folders = explorer.find_largest_folders(cached_structure, limit=limit)
                if large_folders:
                    rprint("[green]📁 Folders with calculated sizes:[/green]")
                    display.display_table(
                        large_folders,
                        title=f"🔥 Largest Folders (Top {len(large_folders)})",
                        sort_by=SortBy.SIZE
                    )
                else:
                    rprint("[yellow]No folders with calculated sizes found[/yellow]")
            
            return
        
        # Fall back to sample data
        rprint("[yellow]No complete scan available. Showing sample data.[/yellow]")
        rprint("[dim]💡 Run 'gdrive-explorer full-scan' for complete analysis with folder sizes.[/dim]")
        
        client = DriveClient()
        
        # Get sample data
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
                title=f"🔥 Largest Files (Top {min(limit, len(large_files))} - Sample)",
                sort_by=SortBy.SIZE
            )
        
        # Show folders (note: without full scan, folder sizes aren't calculated)
        if item_type in ['folders', 'both'] and large_folders:
            if item_type == 'both':
                rprint()
            
            rprint("[yellow]📁 Folders (sizes not calculated - sample data):[/yellow]")
            display.display_table(
                large_folders[:limit],
                title=f"📁 Recent Folders (Top {min(limit, len(large_folders))} - Sample)",
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
        
        display = DriveDisplayManager(console)
        
        # Check for complete cached structure first
        cached_structure = get_cache().get_structure()
        if cached_structure and cached_structure.scan_complete:
            rprint("[green]✓ Using complete cached Drive structure[/green]")
            display.display_summary(cached_structure)
            return
        elif cached_structure:
            rprint("[green]✓ Using partial cached data[/green]")
            display.display_summary(cached_structure)
            return
        
        # Fall back to sample data
        rprint("[yellow]No cached data available. Generating sample summary.[/yellow]")
        rprint("[dim]💡 Run 'gdrive-explorer full-scan' for complete analysis.[/dim]")
        
        client = DriveClient()
        
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

[bold]Total Items:[/bold] {total_items:,} (sample of your Drive)
[bold]Files:[/bold] {len(regular_files):,}
[bold]Folders:[/bold] {len(folders):,}
[bold]Total Size:[/bold] {format_file_size(total_size)} (files only)
[bold]Google Workspace Files:[/bold] {len(workspace_files):,}

[bold yellow]Note:[/bold yellow] This is a sample analysis from recent files. 
For complete Drive analysis with folder sizes, run: [bold]gdrive-explorer full-scan[/bold]
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