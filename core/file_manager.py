import os
import shutil
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Union, Set, Tuple
import hashlib
import json
from ..config.settings import settings

logger = logging.getLogger(__name__)

class FileManager:
    """Manages file operations within a predefined workspace"""
    
    def __init__(self, workspace_path: Optional[str] = None):
        self.workspace_path = workspace_path or settings.filesystem.workspace_path
        self.allowed_extensions = set(settings.filesystem.allowed_extensions)
        self.max_file_size = settings.filesystem.max_file_size_mb * 1024 * 1024  # Convert to bytes
        self.backup_enabled = settings.filesystem.backup_enabled
        self.backup_path = settings.filesystem.backup_path or os.path.join(self.workspace_path, "_backups")
        self.file_checksums = {}  # Track file checksums to detect changes
        
        # Initialize the workspace
        self._initialize_workspace()
    
    def _initialize_workspace(self) -> None:
        """Create workspace directory if it doesn't exist"""
        try:
            os.makedirs(self.workspace_path, exist_ok=True)
            logger.info(f"Workspace initialized at: {self.workspace_path}")
            
            if self.backup_enabled:
                os.makedirs(self.backup_path, exist_ok=True)
                logger.info(f"Backup directory initialized at: {self.backup_path}")
                
            # Load file checksums if present
            checksum_file = os.path.join(self.workspace_path, ".checksums.json")
            if os.path.exists(checksum_file):
                with open(checksum_file, 'r') as f:
                    self.file_checksums = json.load(f)
                    
        except Exception as e:
            logger.error(f"Failed to initialize workspace: {e}")
            raise
    
    def _update_checksums(self) -> None:
        """Update checksums for all files in workspace"""
        self.file_checksums = {}
        
        for root, _, files in os.walk(self.workspace_path):
            for file in files:
                filepath = os.path.join(root, file)
                
                # Skip backup directory and checksum file
                if self.backup_path in filepath or ".checksums.json" in filepath:
                    continue
                
                rel_path = os.path.relpath(filepath, self.workspace_path)
                try:
                    self.file_checksums[rel_path] = self._get_file_checksum(filepath)
                except:
                    pass
        
        # Save checksums
        checksum_file = os.path.join(self.workspace_path, ".checksums.json")
        with open(checksum_file, 'w') as f:
            json.dump(self.file_checksums, f)
    
    def _get_file_checksum(self, filepath: str) -> str:
        """Calculate file checksum using SHA256"""
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256.update(byte_block)
        return sha256.hexdigest()
    
    def _is_file_allowed(self, filepath: str) -> bool:
        """Check if the file is allowed based on extension and size"""
        _, ext = os.path.splitext(filepath)
        
        # Special case: allow directories
        if os.path.isdir(filepath):
            return True
            
        # Check extension is allowed
        if ext not in self.allowed_extensions and ext != "":
            logger.warning(f"File extension not allowed: {ext}")
            return False
            
        # Check file size
        if os.path.exists(filepath) and os.path.getsize(filepath) > self.max_file_size:
            logger.warning(f"File exceeds maximum allowed size: {filepath}")
            return False
            
        return True
    
    def _backup_file(self, filepath: str) -> Optional[str]:
        """Create a backup of the file if it exists"""
        if not self.backup_enabled or not os.path.exists(filepath):
            return None
            
        rel_path = os.path.relpath(filepath, self.workspace_path)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_dir = os.path.join(self.backup_path, timestamp)
        backup_file = os.path.join(backup_dir, rel_path)
        
        try:
            os.makedirs(os.path.dirname(backup_file), exist_ok=True)
            shutil.copy2(filepath, backup_file)
            logger.debug(f"Backup created: {backup_file}")
            return backup_file
        except Exception as e:
            logger.error(f"Failed to create backup for {filepath}: {e}")
            return None
    
    def list_files(self, relative_path: str = "") -> List[Dict[str, Union[str, int, bool]]]:
        """List all files in the workspace or a subdirectory"""
        target_path = os.path.join(self.workspace_path, relative_path)
        
        if not os.path.exists(target_path):
            logger.warning(f"Path does not exist: {target_path}")
            return []
            
        result = []
        
        for root, dirs, files in os.walk(target_path):
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                rel_path = os.path.relpath(dir_path, self.workspace_path)
                
                result.append({
                    'name': dir_name,
                    'path': rel_path,
                    'is_dir': True,
                    'size': 0,
                    'modified': datetime.fromtimestamp(os.path.getmtime(dir_path)).isoformat(),
                })
                
            for file_name in files:
                file_path = os.path.join(root, file_name)
                rel_path = os.path.relpath(file_path, self.workspace_path)
                
                # Skip backup directory and hidden files
                if self.backup_path in file_path or file_name.startswith('.'):
                    continue
                    
                try:
                    stats = os.stat(file_path)
                    result.append({
                        'name': file_name,
                        'path': rel_path,
                        'is_dir': False,
                        'size': stats.st_size,
                        'modified': datetime.fromtimestamp(stats.st_mtime).isoformat(),
                        'extension': os.path.splitext(file_name)[1]
                    })
                except Exception as e:
                    logger.error(f"Error getting stats for {file_path}: {e}")
        
        return result
    
    def read_file(self, filepath: str) -> str:
        """Read file content"""
        full_path = os.path.join(self.workspace_path, filepath)
        
        if not os.path.exists(full_path):
            logger.warning(f"File does not exist: {full_path}")
            return f"Error: File '{filepath}' does not exist"
            
        if not os.path.isfile(full_path):
            logger.warning(f"Not a file: {full_path}")
            return f"Error: '{filepath}' is not a file"
            
        if not self._is_file_allowed(full_path):
            logger.warning(f"File type or size not allowed: {full_path}")
            return f"Error: File '{filepath}' type or size not allowed"
            
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content
        except Exception as e:
            logger.error(f"Failed to read file {full_path}: {e}")
            return f"Error reading file: {e}"
    
    def write_file(self, filepath: str, content: str) -> bool:
        """Write content to a file"""
        full_path = os.path.join(self.workspace_path, filepath)
        
        # Create directories if they don't exist
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        if not self._is_file_allowed(full_path):
            logger.warning(f"File type or size not allowed: {full_path}")
            return False
            
        try:
            # Backup existing file
            if os.path.exists(full_path):
                self._backup_file(full_path)
                
            # Write new content
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
            # Update checksum
            rel_path = os.path.relpath(full_path, self.workspace_path)
            self.file_checksums[rel_path] = self._get_file_checksum(full_path)
            logger.info(f"File written: {full_path}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to write file {full_path}: {e}")
            return False
    
    def delete_file(self, filepath: str) -> bool:
        """Delete a file or directory"""
        full_path = os.path.join(self.workspace_path, filepath)
        
        if not os.path.exists(full_path):
            logger.warning(f"Path does not exist: {full_path}")
            return False
            
        try:
            # Backup existing file
            if os.path.isfile(full_path):
                self._backup_file(full_path)
                os.remove(full_path)
            else:
                # For directories, backup all files inside
                for root, _, files in os.walk(full_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        self._backup_file(file_path)
                        
                shutil.rmtree(full_path)
                
            # Update checksums
            self._update_checksums()
            logger.info(f"Deleted: {full_path}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to delete {full_path}: {e}")
            return False
    
    def create_directory(self, dirpath: str) -> bool:
        """Create a directory"""
        full_path = os.path.join(self.workspace_path, dirpath)
        
        try:
            os.makedirs(full_path, exist_ok=True)
            logger.info(f"Directory created: {full_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to create directory {full_path}: {e}")
            return False
    
    def get_file_history(self, filepath: str) -> List[Dict[str, str]]:
        """Get the history of changes for a file"""
        if not self.backup_enabled:
            return []
            
        rel_path = filepath
        history = []
        
        for root, dirs, _ in os.walk(self.backup_path):
            for backup_dir in dirs:
                backup_timestamp = backup_dir
                backup_file = os.path.join(root, backup_dir, rel_path)
                
                if os.path.exists(backup_file):
                    timestamp = datetime.strptime(backup_timestamp, "%Y%m%d%H%M%S")
                    history.append({
                        'timestamp': timestamp.isoformat(),
                        'path': os.path.relpath(backup_file, self.backup_path)
                    })
        
        # Sort by timestamp descending
        history.sort(key=lambda x: x['timestamp'], reverse=True)
        return history
    
    def get_changed_files(self) -> List[str]:
        """Get list of files that have changed since last checksum update"""
        changed_files = []
        
        for root, _, files in os.walk(self.workspace_path):
            for file in files:
                filepath = os.path.join(root, file)
                
                # Skip backup directory and checksum file
                if self.backup_path in filepath or ".checksums.json" in filepath:
                    continue
                    
                rel_path = os.path.relpath(filepath, self.workspace_path)
                
                # Skip if file type not allowed
                _, ext = os.path.splitext(filepath)
                if ext not in self.allowed_extensions and ext != "":
                    continue
                
                current_checksum = self._get_file_checksum(filepath)
                
                if rel_path not in self.file_checksums:
                    # New file
                    changed_files.append(rel_path)
                elif self.file_checksums[rel_path] != current_checksum:
                    # Modified file
                    changed_files.append(rel_path)
        
        return changed_files
