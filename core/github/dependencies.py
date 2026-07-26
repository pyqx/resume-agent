"""DependencyAnalyzer — inventory dependencies declared in manifest files.

Counts are read from real manifest parsing (tomllib for TOML). This module
does NOT check whether dependencies are outdated — it only inventories them
and flags structural patterns (local/git deps, unpinned requirements).
"""

import json
import logging
import re
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

_REQ_SPEC_RE = re.compile(r"(==|>=|<=|~=|!=|===|<|>|@)")


class DependencyAnalyzer:
    """Inventory project dependencies from manifest files."""

    def analyze(self, repo_path: Path) -> dict:
        """Analyze project dependencies."""
        results = {
            "package_files": [],
            "total_dependencies": 0,
            "potential_issues": [],
        }

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
                    logger.warning("Failed to parse %s: %s", filename, e)
                    results["potential_issues"].append(f"Could not parse {filename}")

        return results

    def _parse_package_json(self, path: Path) -> dict:
        data = json.loads(path.read_text(encoding="utf-8"))
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        issues = []

        for name, version in deps.items():
            if isinstance(version, str) and version.startswith("file:"):
                issues.append(f"Local dependency: {name} ({version})")
            if isinstance(version, str) and "github:" in version:
                issues.append(f"GitHub dependency: {name} ({version})")

        return {"count": len(deps), "issues": issues}

    def _parse_requirements(self, path: Path) -> dict:
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        count = 0
        issues = []
        for line in lines:
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            count += 1
            # Strip environment markers before judging pinnedness
            spec = line.split(";", 1)[0]
            if not _REQ_SPEC_RE.search(spec):
                issues.append(f"Unpinned dependency: {spec.strip()}")
        return {"count": count, "issues": issues}

    def _parse_pyproject(self, path: Path) -> dict:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        count = 0
        project = data.get("project", {})
        count += len(project.get("dependencies", []))
        for extra_deps in project.get("optional-dependencies", {}).values():
            count += len(extra_deps)
        # Poetry layout
        poetry = data.get("tool", {}).get("poetry", {})
        poetry_deps = poetry.get("dependencies", {})
        count += sum(1 for name in poetry_deps if name.lower() != "python")
        for group in poetry.get("group", {}).values():
            count += len(group.get("dependencies", {}))
        return {"count": count, "issues": []}

    def _parse_cargo(self, path: Path) -> dict:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        count = 0
        for section in ("dependencies", "dev-dependencies", "build-dependencies"):
            count += len(data.get(section, {}))
        # workspace dependencies
        count += len(data.get("workspace", {}).get("dependencies", {}))
        return {"count": count, "issues": []}

    def _parse_gomod(self, path: Path) -> dict:
        lines = path.read_text(encoding="utf-8").split("\n")
        count = 0
        in_require = False
        for raw in lines:
            line = raw.split("//", 1)[0].strip()
            if not line:
                continue
            if line.startswith("require ("):
                in_require = True
                continue
            if in_require:
                if line == ")":
                    in_require = False
                    continue
                count += 1
            elif line.startswith("require "):
                count += 1
        return {"count": count, "issues": []}
