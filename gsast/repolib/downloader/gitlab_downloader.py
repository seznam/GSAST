import os
import tempfile
import shutil
import subprocess
from typing import Optional, Tuple
from pathlib import Path, PurePath

import configs.default_values as default_values
from utils.safe_logging import log
from urllib.parse import urlparse
from .base_downloader import BaseRepositoryDownloader


def get_project_path_with_namespace(project_ssh_url) -> PurePath:
    # Handle both string URLs and Path objects
    if isinstance(project_ssh_url, (Path, PurePath)):
        # If it's already a Path object, convert to string first
        url_str = str(project_ssh_url)
    else:
        url_str = project_ssh_url
    
    return PurePath(url_str.split(':')[1].split('.git')[0])


class GitLabProjectDownloader(BaseRepositoryDownloader):
    def __init__(self, gitlab_url, GITLAB_API_TOKEN):
        self.gitlab_scheme, self.gitlab_host = urlparse(gitlab_url)[:2]
        self.GITLAB_API_TOKEN = GITLAB_API_TOKEN
        self.temp_dir = tempfile.mkdtemp()
        # ignore git-lfs
        os.environ["GIT_LFS_SKIP_SMUDGE"] = "1"

    def __del__(self):
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def get_project_path(self, project_url: str) -> PurePath:
        """Extract project path from SSH URL (e.g., 'owner/repo')."""
        return get_project_path_with_namespace(project_url)

    def _prepare_project_dir(self, project_parent_dir_name: str, project_path: PurePath) -> (Path, Path):
        project_parent = Path(self.temp_dir) / project_parent_dir_name
        project_dir = project_parent / project_path
        if project_dir.exists():
            log.warning(f"Project directory {project_dir} already exists, removing")
            shutil.rmtree(project_dir)
        project_dir.mkdir(parents=True)
        return project_dir, project_parent

    def download_project(self, project_url: str, project_parent_dir_name: str, use_shallow_clone: bool = True) -> Optional[Tuple[Path, Path]]:
        path_with_namespace = self.get_project_path(project_url)
        project_dir, project_parent_dir = self._prepare_project_dir(project_parent_dir_name, path_with_namespace)

        # since git clone will create a directory with the project name, it must be removed from the path
        path_to_clone_to = project_dir.parent
        project_dir.rmdir()

        log.info(f"Downloading project {path_with_namespace} to {project_dir}{' (slow git clone is used)' if not use_shallow_clone else ''}")
        try:
            self._download_project(path_with_namespace, path_to_clone_to, use_shallow_clone)
        except Exception as e:
            log.error(f"Error while downloading project {path_with_namespace}: {e}")
            return None
        return project_dir, project_parent_dir

    def _download_project(self, path_with_namespace: PurePath, path_to_clone_to: PurePath, use_shallow_clone: bool):
        os.chdir(path_to_clone_to)
        download_url = f"{self.gitlab_scheme}://oauth2:{self.GITLAB_API_TOKEN}@{self.gitlab_host}/{path_with_namespace}.git"
        args = ["git", "clone"]
        if use_shallow_clone:
            args.extend(["--depth=1", "--single-branch"])
        args.append(download_url)
        try:
            result = subprocess.run(args, timeout=default_values.PROJECT_DOWNLOAD_TIMEOUT, check=True,
                                    capture_output=True, text=True)
            log.debug(f"Git clone output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            log.error(f"Git clone failed with exit code: {e.returncode}")
            log.error(f"Git clone stdout: {e.stdout}")
            log.error(f"Git clone stderr: {e.stderr}")
            raise e
    
    def download_to_permanent_location(self, project_url: str, destination_dir: Path, use_shallow_clone: bool = True, flat_structure: bool = False) -> Optional[Path]:
        """Download project directly to a permanent location"""
        try:
            path_with_namespace = self.get_project_path(project_url)
            
            # Make destination_dir absolute to avoid path issues
            destination_dir = destination_dir.resolve()
            
            if flat_structure:
                # Just use the repo name (e.g., "my-repo" instead of "group/my-repo")
                repo_name = path_with_namespace.name
                final_project_dir = destination_dir / repo_name
            else:
                # Use full group/repo structure
                final_project_dir = destination_dir / path_with_namespace
            
            # Remove existing directory if it exists
            if final_project_dir.exists():
                log.warning(f"Destination directory {final_project_dir} already exists, removing")
                shutil.rmtree(final_project_dir)
            
            # Create parent directories
            final_project_dir.parent.mkdir(parents=True, exist_ok=True)
            
            log.info(f"Downloading project {path_with_namespace} to {final_project_dir}")
            
            # Store original working directory
            original_cwd = os.getcwd()
            
            try:
                # Change to the exact parent directory where we want the repo
                os.chdir(final_project_dir.parent)
                
                download_url = f"{self.gitlab_scheme}://oauth2:{self.GITLAB_API_TOKEN}@{self.gitlab_host}/{path_with_namespace}.git"
                args = ["git", "clone"]
                if use_shallow_clone:
                    args.extend(["--depth=1", "--single-branch"])
                
                args.extend([download_url, final_project_dir.name])
                
                result = subprocess.run(
                    args,
                    timeout=default_values.PROJECT_DOWNLOAD_TIMEOUT,
                    check=True,
                    capture_output=True,
                    text=True
                )
                
                log.info(f"Successfully downloaded {path_with_namespace}")
                return final_project_dir
                
            finally:
                # Always restore original working directory
                os.chdir(original_cwd)
            
        except Exception as e:
            log.error(f"Error downloading project from {project_url} to {destination_dir}: {e}")
            return None
