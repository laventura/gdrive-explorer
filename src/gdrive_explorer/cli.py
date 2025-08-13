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
@click.option('--limit', '-l', default=50, help='Number of items to scan (for testing)')
@click.option('--cache/--no-cache', default=True, help='Use cached data if available')
def scan(limit, cache):
    """Scan Google Drive and analyze folder sizes (Phase 2 preview)."""
    try:
        rprint("[blue]Starting Google Drive scan (Phase 2)...[/blue]")
        
        # Initialize explorer
        explorer = DriveExplorer()
        
        # Check cache first if enabled
        cached_structure = None
        if cache:
            cached_structure = get_cache().get_structure()
            if cached_structure:
                rprint("[green]✓ Found cached drive structure[/green]")
        
        if cached_structure:
            structure = cached_structure
        else:
            rprint("[blue]Fetching drive data from Google API...[/blue]")
            # For Phase 2 preview, we'll just test with a limited scan
            rprint(f"[yellow]Note: Limited to {limit} items for testing[/yellow]")
            
            # Get basic files list for testing
            client = DriveClient()
            result = client.list_files(page_size=limit)
            files = result.get('files', [])
            
            rprint(f"[green]✓ Fetched {len(files)} items[/green]")
            
            # Show sample analysis
            folders = [f for f in files if client.is_folder(f)]
            regular_files = [f for f in files if not client.is_folder(f)]
            
            total_size = sum(client.get_file_size(f) for f in regular_files)
            
            # Create summary table
            table = Table(title="Google Drive Scan Results (Preview)")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green", justify="right")
            
            table.add_row("Total Items", str(len(files)))
            table.add_row("Folders", str(len(folders)))
            table.add_row("Files", str(len(regular_files)))
            table.add_row("Total Size", format_file_size(total_size))
            
            console.print(table)
            
            # Show largest files
            if regular_files:
                regular_files.sort(key=lambda x: client.get_file_size(x), reverse=True)
                
                files_table = Table(title=f"Largest Files (Top {min(10, len(regular_files))})")
                files_table.add_column("Name", style="cyan", no_wrap=False)
                files_table.add_column("Size", style="green", justify="right")
                files_table.add_column("Type", style="magenta")
                
                for file in regular_files[:10]:
                    name = file.get('name', 'Unknown')
                    size = format_file_size(client.get_file_size(file))
                    file_type = "Google Doc" if 'google-apps' in file.get('mimeType', '') else "File"
                    
                    files_table.add_row(name, size, file_type)
                
                console.print(files_table)
            
            return  # Early return for Phase 2 preview
        
        # Full scan functionality will be implemented later
        rprint("[yellow]Full recursive scan will be available in final Phase 2[/yellow]")
        
    except Exception as e:
        rprint(f"[red]Error during scan: {e}[/red]")


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


if __name__ == '__main__':
    main()