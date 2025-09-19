import os
import tempfile
import shutil
import subprocess
from typing import Optional, Tuple
from pathlib import Path, PurePath
from urllib.parse import urlparse

import configs.default_values as default_values
from utils.safe_logging import log
from .base_downloader import BaseRepositoryDownloader


def get_github_project_path(clone_url: str) -> PurePath:
    """Extract project path from GitHub clone URL"""
    # Handle both HTTPS and SSH URLs
    if clone_url.startswith('https://github.com/'):
        # https://github.com/owner/repo.git -> owner/repo
        path = clone_url.replace('https://github.com/', '').replace('.git', '')
    elif clone_url.startswith('git@github.com:'):
        # git@github.com:owner/repo.git -> owner/repo
        path = clone_url.split(':')[1].replace('.git', '')
    else:
        raise ValueError(f"Unsupported GitHub URL format: {clone_url}")
    
    return PurePath(path)


class GitHubProjectDownloader(BaseRepositoryDownloader):
    def __init__(self, GITHUB_API_TOKEN: Optional[str] = None):
        self.GITHUB_API_TOKEN = GITHUB_API_TOKEN
        self.temp_dir = tempfile.mkdtemp()
        # Ignore git-lfs to speed up downloads
        os.environ["GIT_LFS_SKIP_SMUDGE"] = "1"
    
    def get_project_path(self, project_url: str) -> PurePath:
        """Extract project path from URL (e.g., 'owner/repo')."""
        return get_github_project_path(project_url)

    def __del__(self):
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _prepare_project_dir(self, project_parent_dir_name: str, project_path: PurePath) -> Tuple[Path, Path]:
        """Prepare directory structure for downloading project"""
        project_parent = Path(self.temp_dir) / project_parent_dir_name
        project_dir = project_parent / project_path
        
        if project_dir.exists():
            log.warning(f"Project directory {project_dir} already exists, removing")
            shutil.rmtree(project_dir)
        
        project_dir.mkdir(parents=True)
        return project_dir, project_parent

    def download_project(self, clone_url: str, project_parent_dir_name: str, use_shallow_clone: bool = True) -> Optional[Tuple[Path, Path]]:
        """Download a GitHub project using git clone"""
        try:
            project_path = get_github_project_path(clone_url)
            project_dir, project_parent_dir = self._prepare_project_dir(project_parent_dir_name, project_path)

            # Remove the created directory since git clone will create it
            project_dir.rmdir()
            path_to_clone_to = project_dir.parent

            log.info(f"Downloading project {project_path} to {project_dir}{' (shallow clone)' if use_shallow_clone else ' (full clone)'}")
            
            self._download_project(clone_url, path_to_clone_to, use_shallow_clone)
            
            return project_dir, project_parent_dir
            
        except Exception as e:
            log.error(f"Error while downloading project from {clone_url}: {e}")
            return None

    def _download_project(self, clone_url: str, path_to_clone_to: Path, use_shallow_clone: bool):
        """Execute git clone command"""
        os.chdir(path_to_clone_to)
        
        # Prepare git clone command
        args = ["git", "clone"]
        
        if use_shallow_clone:
            args.extend(["--depth=1", "--single-branch"])
        
        # Convert SSH URLs to HTTPS if token is available for better authentication
        if self.GITHUB_API_TOKEN and clone_url.startswith('git@github.com:'):
            # Convert SSH URL to HTTPS with token authentication
            # git@github.com:owner/repo.git -> https://token@github.com/owner/repo.git
            repo_path = clone_url.split(':')[1]  # Extract owner/repo.git part
            auth_url = f'https://{self.GITHUB_API_TOKEN}@github.com/{repo_path}'
            args.append(auth_url)
            log.info(f"Converting SSH URL to HTTPS with token authentication")
        elif self.GITHUB_API_TOKEN and clone_url.startswith('https://github.com/'):
            # Insert token into existing HTTPS URL
            auth_url = clone_url.replace('https://github.com/', f'https://{self.GITHUB_API_TOKEN}@github.com/')
            args.append(auth_url)
        else:
            args.append(clone_url)
            if clone_url.startswith('git@github.com:') and not self.GITHUB_API_TOKEN:
                log.warning(f"SSH URL detected but no GitHub token available. This may fail if SSH keys are not configured: {clone_url}")
        
        try:
            result = subprocess.run(
                args, 
                timeout=default_values.PROJECT_DOWNLOAD_TIMEOUT, 
                check=True,
                capture_output=True, 
                text=True
            )
            log.debug(f"Git clone output: {result.stdout}")
            
        except subprocess.CalledProcessError as e:
            log.error(f"Git clone failed with exit code: {e.returncode}")
            log.error(f"Git clone stdout: {e.stdout}")
            log.error(f"Git clone stderr: {e.stderr}")
            raise e
        except subprocess.TimeoutExpired:
            log.error(f"Git clone timed out after {default_values.PROJECT_DOWNLOAD_TIMEOUT} seconds")
            raise

    def download_to_permanent_location(self, clone_url: str, destination_dir: Path, use_shallow_clone: bool = True, flat_structure: bool = False) -> Optional[Path]:
        """Download project directly to a permanent location"""
        try:
            project_path = get_github_project_path(clone_url)
            
            # Make destination_dir absolute to avoid path issues
            destination_dir = destination_dir.resolve()
            
            if flat_structure:
                # Just use the repo name (e.g., "truth" instead of "google/truth")
                repo_name = project_path.name
                final_project_dir = destination_dir / repo_name
            else:
                # Use full owner/repo structure
                final_project_dir = destination_dir / project_path
            
            # Remove existing directory if it exists
            if final_project_dir.exists():
                log.warning(f"Destination directory {final_project_dir} already exists, removing")
                shutil.rmtree(final_project_dir)
            
            # Create parent directories
            final_project_dir.parent.mkdir(parents=True, exist_ok=True)
            
            log.info(f"Downloading project {project_path} to {final_project_dir}")
            
            # Store original working directory
            original_cwd = os.getcwd()
            
            try:
                # Change to the exact parent directory where we want the repo
                os.chdir(final_project_dir.parent)
                
                args = ["git", "clone"]
                if use_shallow_clone:
                    args.extend(["--depth=1", "--single-branch"])
                
                # Convert SSH URLs to HTTPS if token is available for better authentication
                if self.GITHUB_API_TOKEN and clone_url.startswith('git@github.com:'):
                    # Convert SSH URL to HTTPS with token authentication
                    repo_path = clone_url.split(':')[1]  # Extract owner/repo.git part
                    auth_url = f'https://{self.GITHUB_API_TOKEN}@github.com/{repo_path}'
                    args.extend([auth_url, final_project_dir.name])
                    log.info(f"Converting SSH URL to HTTPS with token authentication")
                elif self.GITHUB_API_TOKEN and clone_url.startswith('https://github.com/'):
                    # Insert token into existing HTTPS URL
                    auth_url = clone_url.replace('https://github.com/', f'https://{self.GITHUB_API_TOKEN}@github.com/')
                    args.extend([auth_url, final_project_dir.name])
                else:
                    args.extend([clone_url, final_project_dir.name])
                    if clone_url.startswith('git@github.com:') and not self.GITHUB_API_TOKEN:
                        log.warning(f"SSH URL detected but no GitHub token available. This may fail if SSH keys are not configured: {clone_url}")
                
                result = subprocess.run(
                    args,
                    timeout=default_values.PROJECT_DOWNLOAD_TIMEOUT,
                    check=True,
                    capture_output=True,
                    text=True
                )
                
                log.info(f"Successfully downloaded {project_path}")
                return final_project_dir
                
            finally:
                # Always restore original working directory
                os.chdir(original_cwd)
            
        except Exception as e:
            log.error(f"Error downloading project from {clone_url} to {destination_dir}: {e}")
            return None