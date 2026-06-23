"""
workspace.py — the agent's persistent, traversal-safe filesystem.

This is the "codebase" the agent works on: a real directory on disk (so it survives
across `run()` calls and process restarts), but every path the agent gives is confined
to that directory. The confinement is the security boundary for the FILE tools — even
when code runs without an OS jail (LocalSandbox), the agent cannot read/write outside
its workspace through `read_file`/`write_file`/`list_files`.

HOW THE JAIL WORKS (and why `resolve()` is the right primitive)
--------------------------------------------------------------
`resolve(path)` joins the request onto the root and then calls `Path.resolve()`, which
(a) makes it absolute and (b) FOLLOWS SYMLINKS. We then assert the result is the root or
underneath it. That single check rejects all three escape vectors at once:
  - `..` segments (`ws/../secret` resolves above the root),
  - absolute paths (`ws / "/etc"` == `/etc`, pathlib anchors on an absolute right-hand
    side), and
  - symlinks that point outside (resolve() follows the link to its real target).
"""

from __future__ import annotations

from pathlib import Path


class Workspace:
    """A directory the agent can read/write, with all paths confined inside it."""

    def __init__(self, root: str | Path) -> None:
        # Resolve + create the root once. Storing the RESOLVED root is what makes the
        # containment check below reliable (we compare real paths to real paths).
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, path: str) -> Path:
        """Map a user/agent-supplied relative path to a real path INSIDE the root.

        Raises ``ValueError`` if the path escapes the workspace (``..``, absolute, or a
        symlink pointing outside). This is the single choke point every file op goes
        through.
        """
        candidate = (self._root / path).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            raise ValueError(f"path outside workspace: {path!r}")
        return candidate

    def read_file(self, path: str) -> str:
        """Read a UTF-8 text file. ``FileNotFoundError`` if absent (the tool layer turns
        that into a message the model can act on)."""
        return self.resolve(path).read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> int:
        """Create/overwrite a UTF-8 text file (parent dirs auto-created). Returns the
        number of bytes written."""
        target = self.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode("utf-8")
        target.write_bytes(data)
        return len(data)

    def list_files(self, subdir: str = ".") -> list[str]:
        """List files (not dirs) under ``subdir`` as root-relative POSIX paths, sorted.

        POSIX form (forward slashes) keeps output stable across OSes — important because
        the agent reasons over these strings and re-passes them to the file tools.
        """
        base = self.resolve(subdir)
        if not base.is_dir():
            return []
        files = [p for p in base.rglob("*") if p.is_file()]
        return sorted(p.relative_to(self._root).as_posix() for p in files)
