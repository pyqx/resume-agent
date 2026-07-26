"""StructureAnalyzer — directory layout and module relationship analysis."""

import logging
from collections import defaultdict
from pathlib import Path

from core.github.cloner import is_sensitive_path

logger = logging.getLogger(__name__)

_SOURCE_EXTS = (".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".cpp", ".c", ".rb")
_DOC_EXTS = (".md", ".rst", ".txt")
_CONFIG_EXTS = (".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".lock")
_TEST_DIR_NAMES = {"test", "tests", "spec", "specs", "__tests__"}


class StructureAnalyzer:
    """Analyze repo directory structure and detect architectural patterns."""

    # Vendored/generated directories: excluded from the tree AND all statistics.
    IGNORE_DIRS = {
        ".git", "__pycache__", "node_modules", ".next", "dist", "build",
        "target", ".idea", ".vscode", "vendor", ".venv", "venv",
    }
    IGNORE_FILES = {
        ".gitignore", ".gitattributes", ".DS_Store", "Thumbs.db",
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
        "Cargo.lock", "poetry.lock", "Pipfile.lock",
    }

    def analyze(self, repo_path: Path) -> dict:
        """Analyze repository structure and return module overview."""
        files = list(self._iter_files(repo_path))
        tree = self._build_tree(repo_path)
        tech_stack = self._detect_tech_stack(repo_path, files)
        modules = self._detect_modules(tree)
        file_stats = self._count_file_types(repo_path, files)

        return {
            "root_name": repo_path.name,
            "tech_stack": tech_stack,
            "directory_tree": self._render_tree_simple(tree, max_depth=3),
            "modules": modules,
            "file_stats": file_stats,
            "has_tests": file_stats.get("test_files", 0) > 0,
            "has_ci": self._detect_ci(repo_path),
            "has_docs": self._detect_docs(repo_path),
        }

    def _iter_files(self, repo_path: Path):
        """Single filtered walk: skips vendored dirs and sensitive files."""
        stack = [repo_path]
        while stack:
            current = stack.pop()
            try:
                entries = list(current.iterdir())
            except (PermissionError, OSError):
                continue
            for entry in entries:
                if entry.is_dir():
                    if entry.name not in self.IGNORE_DIRS:
                        stack.append(entry)
                elif entry.is_file():
                    if entry.name in self.IGNORE_FILES:
                        continue
                    rel = str(entry.relative_to(repo_path))
                    if is_sensitive_path(rel):
                        continue
                    yield entry

    def _build_tree(self, path: Path, depth: int = 0, root: Path | None = None) -> dict:
        """Build a nested directory tree dict (sensitive files excluded)."""
        if root is None:
            root = path
        result: dict = {"name": path.name, "type": "directory", "children": []}

        try:
            entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except (PermissionError, OSError):
            return result

        for entry in entries:
            if entry.name in self.IGNORE_DIRS or entry.name in self.IGNORE_FILES:
                continue
            if entry.is_dir():
                if depth >= 4:
                    result["children"].append(
                        {"name": f"{entry.name}/…", "type": "directory", "children": []}
                    )
                    continue
                result["children"].append(self._build_tree(entry, depth + 1, root))
            else:
                rel = str(entry.relative_to(root))
                if is_sensitive_path(rel):
                    continue
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                result["children"].append({
                    "name": entry.name,
                    "type": "file",
                    "size": size,
                })

        return result

    def _detect_tech_stack(self, repo_path: Path, files: list[Path]) -> dict:
        """Detect primary language, frameworks, and build tools."""
        file_map = {
            "package.json": "Node.js",
            "tsconfig.json": "TypeScript",
            "setup.py": "Python",
            "pyproject.toml": "Python",
            "Cargo.toml": "Rust",
            "go.mod": "Go",
            "pom.xml": "Java/Maven",
            "build.gradle": "Java/Gradle",
            "Gemfile": "Ruby",
            "CMakeLists.txt": "C/C++/CMake",
            "Makefile": "C/Make",
            "Dockerfile": "Docker",
        }

        detected = {}
        for filename, label in file_map.items():
            if (repo_path / filename).exists():
                detected[label] = True

        # Count source file extensions (vendored dirs already excluded)
        ext_counts = defaultdict(int)
        for f in files:
            if f.suffix:
                ext_counts[f.suffix] += 1

        top_extensions = sorted(ext_counts.items(), key=lambda x: -x[1])[:5]

        return {
            "detected_tools": list(detected.keys()),
            "top_file_extensions": dict(top_extensions),
        }

    def _detect_modules(self, tree: dict) -> list[dict]:
        """Identify top-level modules based on directory structure."""
        modules = []
        for child in tree.get("children", []):
            if child.get("type") == "directory":
                children = child.get("children", [])
                modules.append({
                    "name": child["name"],
                    "subdirs": sum(1 for c in children if c.get("type") == "directory"),
                    "files": sum(1 for c in children if c.get("type") == "file"),
                })
        return modules

    @staticmethod
    def _is_test_file(repo_path: Path, f: Path) -> bool:
        rel = f.relative_to(repo_path)
        if any(part.lower() in _TEST_DIR_NAMES for part in rel.parts[:-1]):
            return True
        name = f.name.lower()
        stem = f.stem.lower()
        return (
            name.startswith("test_")
            or stem.endswith("_test")
            or ".test." in name
            or ".spec." in name
        )

    def _count_file_types(self, repo_path: Path, files: list[Path]) -> dict:
        """Count files by type category (vendored dirs excluded)."""
        counts = {"source_files": 0, "test_files": 0, "config_files": 0, "doc_files": 0, "other": 0}
        for f in files:
            if self._is_test_file(repo_path, f):
                counts["test_files"] += 1
            elif f.suffix in _DOC_EXTS:
                counts["doc_files"] += 1
            elif f.suffix in _CONFIG_EXTS:
                counts["config_files"] += 1
            elif f.suffix in _SOURCE_EXTS:
                counts["source_files"] += 1
            else:
                counts["other"] += 1
        return counts

    def _detect_ci(self, repo_path: Path) -> bool:
        """Check if CI configuration exists."""
        ci_patterns = [
            ".github/workflows", ".gitlab-ci.yml", "Jenkinsfile",
            ".travis.yml", "circle.yml", ".circleci/config.yml",
        ]
        return any((repo_path / p).exists() for p in ci_patterns)

    def _detect_docs(self, repo_path: Path) -> bool:
        """Check for documentation files."""
        doc_files = [
            "README.md", "README.rst", "CONTRIBUTING.md", "CHANGELOG.md",
            "LICENSE", "LICENSE.md", "LICENSE.txt", "docs",
        ]
        return any((repo_path / f).exists() for f in doc_files)

    def _render_tree_simple(self, tree: dict, depth: int = 0, max_depth: int = 3) -> str:
        """Render a simple text tree representation with truncation markers."""
        if depth > max_depth:
            return ""

        lines = [f"{'  ' * depth}{tree['name']}{'/' if tree['type'] == 'directory' else ''}"]
        children = tree.get("children", [])
        for child in children[:10]:
            if isinstance(child, dict):
                rendered = self._render_tree_simple(child, depth + 1, max_depth)
                if rendered:
                    lines.append(rendered)
        if len(children) > 10:
            lines.append(f"{'  ' * (depth + 1)}… (+{len(children) - 10} more)")

        return "\n".join(l for l in lines if l)
