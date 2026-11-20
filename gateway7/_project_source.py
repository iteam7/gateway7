"""Read selected development-project Python source without consulting bytecode.

This import hook exists only while the disposable dev child owns its project.
Installed Gateway7 and dependency modules keep their normal import semantics.
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from importlib.abc import MetaPathFinder
from importlib.machinery import PathFinder, SourceFileLoader, SourcelessFileLoader
from importlib.machinery import ModuleSpec
from pathlib import Path
import sys
from types import CodeType, ModuleType


class _ProjectSourceLoader(SourceFileLoader):
    def get_code(self, fullname: str) -> CodeType:
        # -B prevents writing caches, but Python still reads a valid-looking pyc.
        # Compile the actual source bytes even when mtime and size match a cache.
        source = self.get_data(self.path)
        return self.source_to_code(source, self.path)


class _ProjectSourceFinder(MetaPathFinder):
    def __init__(self, root: Path) -> None:
        self.root = root

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        spec = PathFinder.find_spec(fullname, path, target)
        if spec is None or spec.origin is None:
            return None
        try:
            origin = Path(spec.origin).resolve(strict=True)
        except (OSError, RuntimeError):
            return None
        if not origin.is_relative_to(self.root):
            return None
        if isinstance(spec.loader, SourceFileLoader):
            spec.loader = _ProjectSourceLoader(fullname, str(origin))
            return spec
        if isinstance(spec.loader, SourcelessFileLoader):
            raise ImportError("Development project modules require Python source")
        return None


@contextmanager
def project_source_imports(root: Path) -> Iterator[None]:
    """Keep relative and lazily imported project helpers fresh for the whole run."""
    selected = root.resolve(strict=True)
    finder = _ProjectSourceFinder(selected)
    previous_path = sys.path[:]
    sys.path.insert(0, str(selected))
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)
        sys.path[:] = previous_path
