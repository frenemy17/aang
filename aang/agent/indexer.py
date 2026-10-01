import os
import re
from typing import Dict, List, Any

class SymbolIndexer:
    """Lightweight AST/Regex symbol indexer for JS/TS and Python codebases."""
    def __init__(self, sandbox):
        self.sandbox = sandbox
        self.symbols: Dict[str, Dict[str, Any]] = {}

    def build_index(self, repo_files: Any) -> Dict[str, Dict[str, Any]]:
        self.symbols.clear()
        
        if isinstance(repo_files, str):
            repo_files = [f.strip() for f in repo_files.splitlines() if f.strip()]

        # Regex patterns for Python and JavaScript / TypeScript
        py_pattern = re.compile(r'^\s*(def|class)\s+([a-zA-Z_][a-zA-Z0-9_]*)', re.MULTILINE)
        js_pattern = re.compile(r'(?:function\s+([a-zA-Z_][a-zA-Z0-9_]*)|(?:const|let|var)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:function|\([^)]*\)\s*=>)|class\s+([a-zA-Z_][a-zA-Z0-9_]*)|exports\.([a-zA-Z_][a-zA-Z0-9_]*)\s*=)', re.MULTILINE)

        for f in repo_files:
            if not (f.endswith('.py') or f.endswith('.js') or f.endswith('.ts')):
                continue
            if any(p in f for p in ['.git', 'node_modules', 'venv', '__pycache__', 'dist']):
                continue

            try:
                content = self.sandbox.read_file(f)
                if f.endswith('.py'):
                    for match in py_pattern.finditer(content):
                        kind, name = match.group(1), match.group(2)
                        line_num = content[:match.start()].count('\n') + 1
                        self.symbols[name] = {"file": f, "kind": kind, "line": line_num}
                else:
                    for match in js_pattern.finditer(content):
                        name = match.group(1) or match.group(2) or match.group(3) or match.group(4)
                        if name:
                            line_num = content[:match.start()].count('\n') + 1
                            self.symbols[name] = {"file": f, "kind": "function/class", "line": line_num}
            except Exception:
                pass

        return self.symbols

    def find_relevant_symbols(self, query: str) -> List[Dict[str, Any]]:
        results = []
        q_tokens = set(re.findall(r'[a-zA-Z0-9_]+', query.lower()))
        for sym, meta in self.symbols.items():
            sym_lower = sym.lower()
            if sym_lower in q_tokens or any(tok in sym_lower for tok in q_tokens if len(tok) >= 4):
                results.append({"name": sym, **meta})
        return results
