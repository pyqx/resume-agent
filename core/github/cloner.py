"""RepoCloner — shallow clone with sandbox isolation.

Security posture:
- Strict URL validation (github/gitlab/gitee, no embedded credentials).
- Git runs with credential helpers and terminal prompts disabled, so a
  private-repo URL fails fast instead of hanging or using local credentials.
- Blob-size filter + post-clone size check bound disk usage.
- Sensitive files (keys, .env, credentials) are flagged via is_sensitive_path()
  so analysis layers can exclude them from LLM prompts.
"""

import asyncio
import fnmatch
import logging
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Files/directories to exclude from analysis for safety
BLOCKED_PATTERNS = [
    ".env", ".env.*", "credentials.*", "*.pem", "*.key",
    "id_rsa*", "*.pfx", "secrets.*", ".git/config",
]

_URL_RE = re.compile(
    r"^https://(github\.com|gitlab\.com|gitee\.com)/"
    r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)
_SSH_RE = re.compile(
    r"^git@(github\.com|gitlab\.com|gitee\.com):"
    r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?$"
)

_MAX_BLOB_MB = 10


def is_sensitive_path(rel_path: str) -> bool:
    """True if a repo-relative path matches a blocked (secret-bearing) pattern."""
    parts = rel_path.replace("\\", "/").split("/")
    name = parts[-1] if parts else rel_path
    joined = "/".join(parts)
    for pattern in BLOCKED_PATTERNS:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(joined, pattern):
            return True
    return False


def _rmtree_force(path: Path):
    """rmtree that clears read-only bits (git object files on Windows)."""

    def _on_error(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    shutil.rmtree(path, onerror=_on_error)


class RepoCloner:
    """Shallow clone a git repo to a temp directory with safety restrictions."""

    def __init__(self, max_size_mb: int = 200, timeout_seconds: int = 60):
        self.max_size_mb = max_size_mb
        self.timeout_seconds = timeout_seconds
        self._temp_dirs: list[Path] = []

    async def shallow_clone(self, url: str) -> Path:
        """Clone repo with --depth 1 to a temp directory (async, non-blocking).

        Raises:
            ValueError: If URL is unsafe/unsupported or repo exceeds size limit
            RuntimeError: If the clone fails or times out
        """
        clone_url = self._normalize_url(url)
        if clone_url is None:
            raise ValueError(f"Not a valid git repository URL: {url}")

        temp_dir = Path(tempfile.mkdtemp(prefix="repo_analysis_"))
        self._temp_dirs.append(temp_dir)
        logger.info("Cloning %s", clone_url)

        env = {
            **os.environ,
            # Never prompt, never touch local credential stores.
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        }
        argv = [
            "git",
            "-c", "credential.helper=",
            "clone",
            "--depth", "1",
            "--single-branch",
            f"--filter=blob:limit={_MAX_BLOB_MB}m",
            "--",
            clone_url,
            str(temp_dir),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            try:
                _, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout_seconds
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise RuntimeError(
                    f"Clone timed out after {self.timeout_seconds}s"
                )

            if proc.returncode != 0:
                stderr_text = (stderr or b"").decode("utf-8", errors="replace")
                logger.warning("Clone failed: %s", stderr_text[:500])
                # Don't leak local paths/credential hints to callers.
                raise RuntimeError(
                    "Clone failed (repository may be private, missing, or unreachable)"
                )

            total_size = await asyncio.to_thread(self._dir_size, temp_dir)
            if total_size > self.max_size_mb * 1024 * 1024:
                raise ValueError(
                    f"Repository too large ({total_size / 1024 / 1024:.0f}MB "
                    f"> {self.max_size_mb}MB limit)"
                )
            return temp_dir
        except BaseException:
            await self.remove(temp_dir)
            raise

    @staticmethod
    def _dir_size(path: Path) -> int:
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())

    async def remove(self, path: Path | None):
        """Remove a cloned repo (async wrapper around blocking rmtree)."""
        if path and path.exists():
            await asyncio.to_thread(_rmtree_force, path)
        if path in self._temp_dirs:
            self._temp_dirs.remove(path)

    def cleanup(self, path: Path | None = None):
        """Synchronous removal (for shutdown hooks / non-async contexts)."""
        if path and path.exists():
            _rmtree_force(path)
        if path in self._temp_dirs:
            self._temp_dirs.remove(path)

    def cleanup_all(self):
        """Clean up all remaining temp directories."""
        for d in list(self._temp_dirs):
            self.cleanup(d)

    @staticmethod
    def _normalize_url(url: str) -> str | None:
        """Validate and normalize to a canonical https URL, or None if invalid."""
        url = url.strip()
        m = _URL_RE.match(url)
        if m:
            host, owner, repo = m.groups()
            return f"https://{host}/{owner}/{repo}"
        m = _SSH_RE.match(url)
        if m:
            host, owner, repo = m.groups()
            return f"https://{host}/{owner}/{repo}"
        return None

    @staticmethod
    def _is_valid_git_url(url: str) -> bool:
        return RepoCloner._normalize_url(url) is not None
