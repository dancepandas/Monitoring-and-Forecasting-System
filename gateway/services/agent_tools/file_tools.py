import re
from pathlib import Path

from pydantic import BaseModel, Field

# 5. 文件检索（2 个）
# ---------------------------------------------------------------------------

class GlobArgs(BaseModel):
    pattern: str = Field(..., description="glob 模式，如 **/*.py")
    path: str = Field(default=".", description="搜索根目录")

def glob_search(**kwargs) -> dict:
    args = GlobArgs(**kwargs)
    root = Path(args.path)
    matches = sorted(root.glob(args.pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "matches": [str(p) for p in matches],
        "count": len(matches),
    }

class GrepArgs(BaseModel):
    pattern: str = Field(..., description="正则表达式")
    path: str = Field(default=".", description="搜索根目录")
    glob: str = Field(default="*", description="文件过滤模式")

def grep_search(**kwargs) -> dict:
    args = GrepArgs(**kwargs)
    root = Path(args.path)
    regex = re.compile(args.pattern)
    matches = []
    for file_path in root.rglob(args.glob):
        if not file_path.is_file():
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                matches.append({"file": str(file_path), "line": i, "text": line})
    return {"matches": matches, "count": len(matches)}

# ---------------------------------------------------------------------------