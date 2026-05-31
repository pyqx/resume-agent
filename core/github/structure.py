"""StructureAnalyzer — directory layout and module relationship analysis."""

import logging
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class StructureAnalyzer:
    """Analyze repo directory structure and detect architectural patterns."""

    IGNORE_DIRS = {
        ".git", "__pycache__", "node_modules", ".next", "dist", "build",
        "target", ".idea", ".vscode", "vendor", ".venv", "venv",
        "test", "tests", "spec", "__tests__",
    }
    IGNORE_FILES = {
        ".gitignore", ".gitattributes", ".DS_Store", "Thumbs.db",
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
        "Cargo.lock", "poetry.lock", "Pipfile.lock",
    }

    def analyze(self, repo_path: Path) -> dict:
        """Analyze repository structure and return module overview."""
        tree = self._build_tree(repo_path)
        tech_stack = self._detect_tech_stack(repo_path)
        modules = self._detect_modules(tree, tech_stack)
        file_stats = self._count_file_types(repo_path)

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

    def _build_tree(self, path: Path, depth: int = 0) -> dict:
        """Build a nested directory tree dict."""
        result: dict = {"name": path.name, "type": "directory", "children": []}

        try:
            entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return result

        for entry in entries:
            if entry.name in self.IGNORE_DIRS:
                continue
            if entry.name in self.IGNORE_FILES:
                continue
            if depth >= 4 and entry.is_dir():
                result["children"].append({"name": f"{entry.name}/", "type": "directory", "children": "..."})
                continue
            if entry.is_dir():
                result["children"].append(self._build_tree(entry, depth + 1))
            else:
                result["children"].append({
                    "name": entry.name,
                    "type": "file",
                    "size": entry.stat().st_size,
                })

        return result

    def _detect_tech_stack(self, repo_path: Path) -> dict:
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

        # Count source file extensions
        ext_counts = defaultdict(int)
        for f in repo_path.rglob("*"):
            if f.is_file() and f.suffix:
                ext_counts[f.suffix] += 1

        top_extensions = sorted(ext_counts.items(), key=lambda x: -x[1])[:5]

        return {
            "detected_tools": list(detected.keys()),
            "top_file_extensions": dict(top_extensions),
        }

    def _detect_modules(self, tree: dict, tech_stack: dict) -> list[dict]:
        """Identify top-level modules based on directory structure."""
        modules = []
        for child in tree.get("children", []):
            if child.get("type") == "directory":
                modules.append({
                    "name": child["name"],
                    "subdirs": sum(1 for c in child.get("children", []) if c.get("type") == "directory"),
                    "files": sum(1 for c in child.get("children", []) if c.get("type") == "file"),
                })
        return modules

    def _count_file_types(self, repo_path: Path) -> dict:
        """Count files by type category."""
        counts = {"source_files": 0, "test_files": 0, "config_files": 0, "doc_files": 0, "other": 0}
        test_patterns = ["test", "spec", "__tests__"]

        for f in repo_path.rglob("*"):
            if not f.is_file():
                continue
            if any(p in str(f).lower() for p in test_patterns):
                counts["test_files"] += 1
            elif f.suffix in (".md", ".rst", ".txt"):
                counts["doc_files"] += 1
            elif f.suffix in (".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".lock"):
                counts["config_files"] += 1
            elif f.suffix in (".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".cpp", ".c", ".rb"):
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
        doc_files = ["README.md", "CONTRIBUTING.md", "CHANGELOG.md", "LICENSE", "docs/"]
        return any((repo_path / f).exists() for f in doc_files)

    def _render_tree_simple(self, tree: dict, depth: int = 0, max_depth: int = 3) -> str:
        """Render a simple text tree representation."""
        if depth > max_depth:
            return ""

        lines = [f"{'  ' * depth}{tree['name']}{'/' if tree['type'] == 'directory' else ''}"]
        for child in tree.get("children", [])[:10]:
            if isinstance(child, dict):
                lines.append(self._render_tree_simple(child, depth + 1, max_depth))

        return "\n".join(l for l in lines if l)
