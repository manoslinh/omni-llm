"""
Git Repository Manager.

Handles git operations with AI attribution and safety features.
Based on Aider's repo.py patterns.
"""

import asyncio
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CommitInfo:
    """Information about a commit."""
    hash: str
    author: str
    date: datetime
    message: str
    files: List[str]


@dataclass
class BranchInfo:
    """Information about a git branch."""
    name: str
    is_current: bool
    commit_hash: str
    commit_message: str


class GitRepository:
    """
    Manages git operations for AI coding.
    
    Key features:
    - Dirty commits: Auto-commit uncommitted changes before editing
    - AI attribution: Mark AI-generated commits with proper attribution
    - Undo mechanism: Save commit hash before each message for easy rollback
    - Branch isolation: Work on feature branches
    - Worktree support: For parallel agent execution (future)
    """
    
    def __init__(
        self,
        path: Optional[str] = None,
        auto_commit: bool = True,
        ai_author_name: str = "AI Assistant",
        ai_author_email: str = "ai@omni-llm.dev",
        user_author_name: str = "User",
        user_author_email: str = "user@example.com",
    ):
        """
        Initialize git repository manager.
        
        Args:
            path: Path to git repository (defaults to current directory)
            auto_commit: Whether to auto-commit dirty changes before edits
            ai_author_name: Name to use for AI-authored commits
            ai_author_email: Email to use for AI-authored commits
            user_author_name: Name to use for user-authored commits
            user_author_email: Email to use for user-authored commits
        """
        self.path = Path(path or os.getcwd()).resolve()
        self.auto_commit = auto_commit
        self.ai_author_name = ai_author_name
        self.ai_author_email = ai_author_email
        self.user_author_name = user_author_name
        self.user_author_email = user_author_email
        
        # State tracking
        self._last_commit_before_edit: Optional[str] = None
        self._is_initialized = False
        
        # Initialize
        self._ensure_git_repo()
        logger.info(f"GitRepository initialized at {self.path}")
    
    async def has_dirty_changes(self) -> bool:
        """
        Check if there are uncommitted changes.
        
        Uses `git status --porcelain` for reliable detection.
        
        Returns:
            True if there are uncommitted changes, False otherwise
        """
        status = await self._run_git(["status", "--porcelain"])
        return bool(status.strip())
    
    async def commit_dirty_changes(self, message: Optional[str] = None) -> Optional[str]:
        """
        Commit any dirty (uncommitted) changes.
        
        This is called before AI edits to ensure we have a clean state
        to roll back to if needed.
        
        Args:
            message: Optional custom commit message. If not provided,
                    generates one with timestamp and summary of changes.
        
        Returns:
            Commit hash if a commit was made, None if no dirty changes
        """
        if not self.auto_commit:
            return None
        
        # Always save current commit for undo, even if no dirty changes
        self._last_commit_before_edit = await self.get_current_commit()
        logger.debug(f"Saved commit for undo: {self._last_commit_before_edit[:8] if self._last_commit_before_edit else 'None'}")
        
        # Check for dirty changes
        if not await self.has_dirty_changes():
            logger.debug("No dirty changes to commit")
            return None
        
        # Generate commit message if not provided
        if not message:
            # Get summary of changes
            status = await self._run_git(["status", "--porcelain"])
            changed_files = []
            for line in status.strip().split('\n'):
                if line:
                    filename = line[3:].strip()
                    changed_files.append(filename)
            
            # Limit to first few files for summary
            if len(changed_files) == 1:
                summary = f"Update {changed_files[0]}"
            elif len(changed_files) <= 3:
                summary = f"Update {', '.join(changed_files)}"
            else:
                summary = f"Update {len(changed_files)} files"
            
            # Add timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"Auto-commit: {timestamp} - {summary}"
        
        # Stage all changes (including new files)
        await self._run_git(["add", "--all"])
        
        # Create commit
        await self._run_git([
            "commit",
            "--message", message,
            "--author", f"{self.user_author_name} <{self.user_author_email}>",
            "--quiet",  # Suppress output
        ])
        
        # Get the commit hash
        commit_hash = await self.get_current_commit()
        logger.info(f"Created dirty commit: {commit_hash[:8] if commit_hash else 'None'}")
        return commit_hash
    
    # Backward compatibility alias
    async def dirty_commit(self) -> Optional[str]:
        """Alias for commit_dirty_changes for backward compatibility."""
        return await self.commit_dirty_changes()
    
    async def commit(
        self,
        files: List[str],
        message: str,
        ai_attributed: bool = True,
        co_authors: Optional[List[str]] = None,
    ) -> str:
        """
        Commit changes with AI attribution.
        
        Args:
            files: List of files to commit
            message: Commit message
            ai_attributed: Whether to attribute to AI
            co_authors: List of co-author emails for trailer
            
        Returns:
            Commit hash
        """
        if not files:
            raise ValueError("No files to commit")
        
        # Stage files
        await self._run_git(["add"] + files)
        
        # Build commit command
        cmd = ["commit"]
        
        # Add author if AI-attributed
        if ai_attributed:
            cmd.extend(["--author", f"{self.ai_author_name} <{self.ai_author_email}>"])
        
        # Add message
        cmd.extend(["--message", message])
        
        # Add co-authors as trailers
        if co_authors:
            for email in co_authors:
                cmd.extend(["--trailer", f"Co-authored-by: {email}"])
        
        # Always add AI attribution trailer
        if ai_attributed:
            cmd.extend(["--trailer", f"AI-generated-by: Omni-LLM"])
        
        # Execute commit
        result = await self._run_git(cmd)
        commit_hash = result.strip()
        
        logger.info(f"Committed {len(files)} files: {commit_hash[:8]}")
        return commit_hash
    
    async def undo_last_edit(self) -> bool:
        """
        Undo the last AI edit by resetting to the commit before it.
        
        Returns:
            True if undo was successful, False otherwise
        """
        if not self._last_commit_before_edit:
            logger.warning("No last commit saved for undo")
            return False
        
        try:
            await self._run_git(["reset", "--hard", self._last_commit_before_edit])
            logger.info(f"Undo successful: reset to {self._last_commit_before_edit[:8]}")
            self._last_commit_before_edit = None
            return True
        except Exception as e:
            logger.error(f"Undo failed: {e}")
            return False
    
    async def create_branch(self, name: str, checkout: bool = True) -> bool:
        """
        Create a new branch.
        
        Args:
            name: Branch name
            checkout: Whether to checkout the new branch
            
        Returns:
            True if successful
        """
        try:
            await self._run_git(["branch", name])
            
            if checkout:
                await self._run_git(["checkout", name])
            
            logger.info(f"Created branch: {name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create branch {name}: {e}")
            return False
    
    async def checkout_branch(self, name: str) -> bool:
        """Checkout an existing branch."""
        try:
            await self._run_git(["checkout", name])
            logger.info(f"Checked out branch: {name}")
            return True
        except Exception as e:
            logger.error(f"Failed to checkout branch {name}: {e}")
            return False
    
    async def get_current_branch(self) -> str:
        """Get the current branch name."""
        result = await self._run_git(["branch", "--show-current"])
        return result.strip()
    
    async def get_current_commit(self) -> Optional[str]:
        """Get the current commit hash."""
        try:
            result = await self._run_git(["rev-parse", "HEAD"])
            return result.strip()
        except RuntimeError as e:
            # Handle empty repository (no commits yet)
            if "ambiguous argument 'HEAD'" in str(e) or "unknown revision" in str(e):
                logger.debug("No commits yet in repository")
                return None
            raise
    
    async def list_branches(self) -> List[BranchInfo]:
        """List all branches."""
        result = await self._run_git(["branch", "--list", "--format=%(refname:short) %(objectname) %(contents:subject)"])
        
        branches = []
        current_branch = await self.get_current_branch()
        
        for line in result.strip().split('\n'):
            if not line:
                continue
            
            parts = line.split(' ', 2)
            if len(parts) >= 3:
                name, hash_, message = parts
            elif len(parts) == 2:
                name, hash_ = parts
                message = ""
            else:
                continue
            
            branches.append(BranchInfo(
                name=name,
                is_current=(name == current_branch),
                commit_hash=hash_,
                commit_message=message,
            ))
        
        return branches
    
    async def get_status(self) -> Dict[str, List[str]]:
        """
        Get git status.
        
        Returns:
            Dict with keys: staged, unstaged, untracked
        """
        result = await self._run_git(["status", "--porcelain"])
        
        staged = []
        unstaged = []
        untracked = []
        
        for line in result.strip().split('\n'):
            if not line:
                continue
            
            status = line[:2]
            filename = line[3:].strip()
            
            if status[0] != ' ' and status[0] != '?':
                staged.append(filename)
            if status[1] != ' ':
                unstaged.append(filename)
            if status == '??':
                untracked.append(filename)
        
        return {
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
        }
    
    async def create_worktree(self, path: str, branch: Optional[str] = None) -> bool:
        """
        Create a git worktree.
        
        Worktrees allow multiple branches to be checked out simultaneously.
        Useful for parallel agent execution.
        
        Args:
            path: Path for the new worktree
            branch: Branch to checkout (creates new branch if None)
            
        Returns:
            True if successful
        """
        cmd = ["worktree", "add", path]
        if branch:
            cmd.append(branch)
        else:
            # Create new branch with unique name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            branch_name = f"omni-worktree-{timestamp}"
            cmd.extend(["-b", branch_name])
        
        try:
            await self._run_git(cmd)
            logger.info(f"Created worktree at {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to create worktree at {path}: {e}")
            return False
    
    async def merge_branch(self, source_branch: str, target_branch: Optional[str] = None) -> bool:
        """
        Merge a branch into current or target branch.
        
        Args:
            source_branch: Branch to merge from
            target_branch: Branch to merge into (defaults to current)
            
        Returns:
            True if successful
        """
        # Save current branch
        original_branch = await self.get_current_branch()
        
        try:
            # Checkout target branch if specified
            if target_branch and target_branch != original_branch:
                await self.checkout_branch(target_branch)
            
            # Merge
            await self._run_git(["merge", "--no-ff", source_branch])
            
            logger.info(f"Merged {source_branch} into {target_branch or original_branch}")
            return True
            
        except Exception as e:
            logger.error(f"Merge failed: {e}")
            return False
            
        finally:
            # Restore original branch if we changed it
            if target_branch and target_branch != original_branch:
                await self.checkout_branch(original_branch)
    
    async def get_diff(self, file_path: Optional[str] = None) -> str:
        """
        Get diff of changes.
        
        Args:
            file_path: Optional specific file to diff
            
        Returns:
            Diff text
        """
        cmd = ["diff", "--no-color"]
        if file_path:
            cmd.append(file_path)
        
        return await self._run_git(cmd)
    
    async def get_log(self, limit: int = 10) -> List[CommitInfo]:
        """
        Get commit log.
        
        Args:
            limit: Maximum number of commits to return
            
        Returns:
            List of CommitInfo objects
        """
        format_str = "%H|%an|%ad|%s"
        result = await self._run_git([
            "log",
            f"--max-count={limit}",
            f"--format={format_str}",
            "--date=iso",
        ])
        
        commits = []
        for line in result.strip().split('\n'):
            if not line:
                continue
            
            hash_, author, date_str, message = line.split('|', 3)
            
            try:
                date = datetime.fromisoformat(date_str.replace(' ', 'T'))
            except ValueError:
                date = datetime.now()
            
            # Get files changed in this commit
            files_result = await self._run_git([
                "show", "--name-only", "--format=", hash_
            ])
            files = [f.strip() for f in files_result.strip().split('\n') if f.strip()]
            
            commits.append(CommitInfo(
                hash=hash_,
                author=author,
                date=date,
                message=message,
                files=files,
            ))
        
        return commits
    
    def _ensure_git_repo(self) -> None:
        """Ensure we're in a git repository, initialize if not."""
        try:
            # Check if git repo exists
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.path,
                capture_output=True,
                text=True,
            )
            
            if result.returncode != 0:
                logger.info(f"Initializing git repository at {self.path}")
                subprocess.run(
                    ["git", "init"],
                    cwd=self.path,
                    check=True,
                )
                
                # Set initial config
                subprocess.run(
                    ["git", "config", "user.name", self.user_author_name],
                    cwd=self.path,
                    check=True,
                )
                subprocess.run(
                    ["git", "config", "user.email", self.user_author_email],
                    cwd=self.path,
                    check=True,
                )
            
            self._is_initialized = True
            
        except Exception as e:
            logger.error(f"Failed to ensure git repository: {e}")
            raise
    
    async def _run_git(self, args: List[str]) -> str:
        """
        Run git command asynchronously.
        
        Args:
            args: Git command arguments
            
        Returns:
            Command output
        """
        cmd = ["git"] + args
        
        logger.debug(f"Running git: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode('utf-8', errors='replace').strip()
            raise RuntimeError(f"Git command failed: {' '.join(cmd)}\n{error_msg}")
        
        return stdout.decode('utf-8', errors='replace')
    
    async def close(self) -> None:
        """Clean up resources."""
        logger.info("GitRepository closed")
    
    # Context manager support
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()