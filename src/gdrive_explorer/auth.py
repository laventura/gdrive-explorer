"""OAuth 2.0 authentication for Google Drive API."""

import os
import pickle
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials


class DriveAuthenticator:
    """Handles OAuth 2.0 authentication for Google Drive API."""
    
    # Read-only scope for Drive metadata
    SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']
    
    def __init__(self, credentials_file: str = "config/credentials.json", 
                 token_file: str = "config/token.pickle"):
        """Initialize authenticator with file paths.
        
        Args:
            credentials_file: Path to OAuth 2.0 credentials JSON file
            token_file: Path to store/load authentication tokens
        """
        self.credentials_file = Path(credentials_file)
        self.token_file = Path(token_file)
        self._credentials: Optional[Credentials] = None
    
    def authenticate(self) -> Credentials:
        """Authenticate with Google Drive API using OAuth 2.0.
        
        Returns:
            Valid Google API credentials
            
        Raises:
            FileNotFoundError: If credentials file is missing
            Exception: If authentication fails
        """
        # Try to load existing token
        if self.token_file.exists():
            with open(self.token_file, 'rb') as token:
                self._credentials = pickle.load(token)
        
        # If there are no (valid) credentials available, let the user log in
        if not self._credentials or not self._credentials.valid:
            if self._credentials and self._credentials.expired and self._credentials.refresh_token:
                # Try to refresh expired credentials
                try:
                    self._credentials.refresh(Request())
                except Exception as e:
                    print(f"Failed to refresh token: {e}")
                    self._credentials = None
            
            if not self._credentials:
                # Run OAuth flow for new credentials
                self._credentials = self._run_oauth_flow()
            
            # Save credentials for next run
            self._save_credentials()
        
        return self._credentials
    
    def _run_oauth_flow(self) -> Credentials:
        """Run the OAuth 2.0 authorization flow.
        
        Returns:
            Fresh credentials from OAuth flow
            
        Raises:
            FileNotFoundError: If credentials file doesn't exist
            Exception: If OAuth flow fails
        """
        if not self.credentials_file.exists():
            raise FileNotFoundError(
                f"Credentials file not found: {self.credentials_file}\n"
                "Please download it from Google Cloud Console:\n"
                "1. Go to https://console.cloud.google.com/\n"
                "2. Enable Google Drive API\n"
                "3. Create OAuth 2.0 credentials\n"
                "4. Download and save as 'config/credentials.json'"
            )
        
        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.credentials_file), self.SCOPES
        )
        credentials = flow.run_local_server(port=0)
        return credentials
    
    def _save_credentials(self) -> None:
        """Save credentials to token file for future use."""
        # Ensure config directory exists
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.token_file, 'wb') as token:
            pickle.dump(self._credentials, token)
        
        print(f"Credentials saved to: {self.token_file}")
    
    def is_authenticated(self) -> bool:
        """Check if we have valid credentials.
        
        Returns:
            True if authenticated with valid credentials
        """
        return (self._credentials is not None and 
                self._credentials.valid and 
                not self._credentials.expired)
    
    def clear_credentials(self) -> None:
        """Clear stored credentials and force re-authentication."""
        if self.token_file.exists():
            os.remove(self.token_file)
        self._credentials = None
        print("Credentials cleared. You'll need to re-authenticate next time.")


def get_authenticated_credentials(credentials_file: str = "config/credentials.json") -> Credentials:
    """Convenience function to get authenticated credentials.
    
    Args:
        credentials_file: Path to OAuth credentials JSON file
        
    Returns:
        Valid Google API credentials
    """
    authenticator = DriveAuthenticator(credentials_file)
    return authenticator.authenticate()