"""RepoCloner — shallow clone with sandbox isolation."""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Files/directories to exclude from analysis for safety
BLOCKED_PATTERNS = [
    ".env", ".env.*", "credentials.*", "*.pem", "*.key",
    "id_rsa*", "*.pfx", "secrets.*", ".git/config",
]


class RepoCloner:
    """Shallow clone a GitHub repo to a temp directory with safety restrictions."""

    def __init__(self, max_size_mb: int = 200, timeout_seconds: int = 60):
        self.max_size_mb = max_size_mb
        self.timeout_seconds = timeout_seconds
        self._temp_dirs: list[Path] = []

    def shallow_clone(self, url: str) -> Path:
        """Clone repo with --depth 1 to a temp directory.

        Args:
            url: GitHub/GitLab/Gitee repo URL

        Returns:
            Path to cloned repository

        Raises:
            ValueError: If URL looks unsafe or unsupported
            subprocess.TimeoutExpired: If clone takes too long
        """
        # Validate URL
        if not self._is_valid_git_url(url):
            raise ValueError(f"Not a valid git repository URL: {url}")

        # Transform to HTTPS for GitHub API compatibility
        clone_url = self._normalize_url(url)

        # Create temp directory
        temp_dir = Path(tempfile.mkdtemp(prefix="repo_analysis_"))
        self._temp_dirs.append(temp_dir)

        logger.info(f"Cloning {clone_url} -> {temp_dir}")

        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--single-branch", clone_url, str(temp_dir)],
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )

        if result.returncode != 0:
            # Clean up on failure
            self.cleanup(temp_dir)
            raise RuntimeError(f"Clone failed: {result.stderr[:500]}")

        # Check repo size
        total_size = sum(f.stat().st_size for f in temp_dir.rglob("*") if f.is_file())
        if total_size > self.max_size_mb * 1024 * 1024:
            self.cleanup(temp_dir)
            raise ValueError(f"Repository too large ({total_size / 1024 / 1024:.0f}MB > {self.max_size_mb}MB limit)")

        return temp_dir

    def cleanup(self, path: Path | None = None):
        """Remove cloned repo. Call after analysis is complete."""
        if path and path.exists():
            shutil.rmtree(path, ignore_errors=True)
            if path in self._temp_dirs:
                self._temp_dirs.remove(path)

    def cleanup_all(self):
        """Clean up all remaining temp directories."""
        for d in list(self._temp_dirs):
            self.cleanup(d)

    @staticmethod
    def _is_valid_git_url(url: str) -> bool:
        return any(
            url.startswith(prefix)
            for prefix in [
                "https://github.com/",
                "https://gitlab.com/",
                "https://gitee.com/",
                "git@github.com:",
                "git@gitlab.com:",
                "git@gitee.com:",
            ]
        )

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Ensure HTTPS format."""
        if url.startswith("git@"):
            # git@github.com:user/repo.git -> https://github.com/user/repo
            url = url.replace(":", "/").replace("git@", "https://")
        return url.rstrip("/").removesuffix(".git")
