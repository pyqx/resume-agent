"""DependencyAnalyzer — detect outdated dependencies and potential issues."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DependencyAnalyzer:
    """Analyze project dependencies for outdated packages and known patterns."""

    def analyze(self, repo_path: Path) -> dict:
        """Analyze project dependencies."""
        results = {
            "package_files": [],
            "total_dependencies": 0,
            "potential_issues": [],
        }

        # Check common dependency files
        dep_files = {
            "package.json": self._parse_package_json,
            "requirements.txt": self._parse_requirements,
            "pyproject.toml": self._parse_pyproject,
            "Cargo.toml": self._parse_cargo,
            "go.mod": self._parse_gomod,
        }

        for filename, parser in dep_files.items():
            file_path = repo_path / filename
            if file_path.exists():
                try:
                    parsed = parser(file_path)
                    results["package_files"].append(filename)
                    results["total_dependencies"] += parsed.get("count", 0)
                    if parsed.get("issues"):
                        results["potential_issues"].extend(parsed["issues"])
                except Exception as e:
                    logger.debug(f"Failed to parse {filename}: {e}")

        return results

    def _parse_package_json(self, path: Path) -> dict:
        data = json.loads(path.read_text(encoding="utf-8"))
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        issues = []
        count = len(deps)

        # Flag common patterns
        for name, version in deps.items():
            if isinstance(version, str) and version.startswith("file:"):
                issues.append(f"Local dependency: {name} ({version})")
            if isinstance(version, str) and "github:" in version:
                issues.append(f"GitHub dependency: {name} ({version})")

        return {"count": count, "issues": issues}

    def _parse_requirements(self, path: Path) -> dict:
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        count = 0
        issues = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                count += 1
                if "==" not in line and ">=" not in line:
                    issues.append(f"Unpinned dependency: {line}")
        return {"count": count, "issues": issues}

    def _parse_pyproject(self, path: Path) -> dict:
        # Simple TOML parsing — just look for dependency sections
        content = path.read_text(encoding="utf-8")
        count = content.count('"') // 2  # rough estimate
        return {"count": max(0, count // 3), "issues": []}

    def _parse_cargo(self, path: Path) -> dict:
        content = path.read_text(encoding="utf-8")
        count = content.count('"') // 2
        return {"count": max(0, count // 4), "issues": []}

    def _parse_gomod(self, path: Path) -> dict:
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        count = sum(1 for l in lines if l.strip() and not l.startswith("module ") and not l.startswith("go "))
        return {"count": count, "issues": []}
