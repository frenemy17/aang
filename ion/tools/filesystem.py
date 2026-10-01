import ast
import json
import re
from typing import Dict, Any, Optional
from .base import BaseTool
from ion.sandbox.base import SandboxEnvironment

def validate_syntax_before_write(sandbox: SandboxEnvironment, path: str, content: str) -> Optional[str]:
    """
    Validate syntax for code files before writing to disk.
    Returns error string if invalid syntax detected, or None if valid/unsupported format.
    Prevents corrupting the repository with truncated LLM outputs.
    """
    try:
        # 1. Python validation via AST
        if path.endswith(".py"):
            try:
                ast.parse(content)
            except SyntaxError as se:
                return f"Python SyntaxError at line {se.lineno}, col {se.offset}: {se.msg}\n  {se.text or ''}"

        # 2. JSON validation
        elif path.endswith(".json"):
            try:
                json.loads(content)
            except json.JSONDecodeError as jde:
                return f"JSONDecodeError at line {jde.lineno}, col {jde.colno}: {jde.msg}"

        # 3. JavaScript / TypeScript validation via node -c
        elif path.endswith(".js") or path.endswith(".mjs") or path.endswith(".cjs"):
            tmp_probe = f".ion_syntax_{abs(hash(content)) % 1000000}.js"
            try:
                sandbox.write_file(tmp_probe, content)
                code, stdout, stderr = sandbox.run_command(f"node -c {tmp_probe} 2>&1", timeout=5)
                sandbox.run_command(f"rm -f {tmp_probe}", timeout=5)
                output_str = (stderr or stdout or "")
                if code != 0 and any(err_kw in output_str for err_kw in ["SyntaxError:", "ReferenceError:", "TypeError:"]):
                    err_clean = output_str.replace(tmp_probe, path).strip()
                    err_lines = [l for l in err_clean.splitlines() if not l.startswith("Node.js v")]
                    return "\n".join(err_lines)
            except Exception:
                pass
    except Exception:
        pass
    return None


class ListFilesTool(BaseTool):
    name = "list_files"
    description = "List all files in a directory."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the directory (use '.' for root)"
            }
        },
        "required": ["path"]
    }
    category = "OBSERVE"
    
    def __init__(self, sandbox: SandboxEnvironment):
        self.sandbox = sandbox
        
    def execute(self, path: str, **kwargs) -> str:
        try:
            return self.sandbox.list_files(path)
        except Exception as e:
            return f"Error listing files: {str(e)}"

class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the contents of a file. Supports optional line ranges."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file"
            },
            "line_start": {
                "type": "integer",
                "description": "Optional starting line number (1-indexed)"
            },
            "line_end": {
                "type": "integer",
                "description": "Optional ending line number (1-indexed)"
            }
        },
        "required": ["path"]
    }
    category = "OBSERVE"
    
    def __init__(self, sandbox: SandboxEnvironment):
        self.sandbox = sandbox
        
    def execute(self, path: str, line_start: int = None, line_end: int = None, **kwargs) -> str:
        try:
            # Handle possible argument aliases from different LLM families
            start = line_start if line_start is not None else kwargs.get("start_line") or kwargs.get("offset")
            end = line_end if line_end is not None else kwargs.get("end_line") or kwargs.get("limit")

            content = self.sandbox.read_file(path)
            if start is not None or end is not None:
                lines = content.splitlines(keepends=True)
                s = max(0, int(start) - 1) if start is not None else 0
                e = int(end) if end is not None else len(lines)
                return "".join(lines[s:e])
            return content
        except Exception as e:
            return f"Error reading file: {str(e)}"

class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write entire content to a file, overwriting it."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file"
            },
            "content": {
                "type": "string",
                "description": "The full content to write"
            }
        },
        "required": ["path", "content"]
    }
    category = "MODIFY"
    
    def __init__(self, sandbox: SandboxEnvironment):
        self.sandbox = sandbox
        
    def execute(self, path: str, content: str = None, **kwargs) -> str:
        try:
            if content is None:
                content = kwargs.get("content:") or kwargs.get("contents") or kwargs.get("text") or kwargs.get("code") or ""
            syntax_err = validate_syntax_before_write(self.sandbox, path, content)
            if syntax_err:
                return (
                    f"Error: Syntax validation failed before saving to '{path}'.\n"
                    f"{syntax_err}\n"
                    f"Notice: The file was NOT modified on disk to protect repository integrity. "
                    f"Please ensure all statements and code blocks are complete before saving."
                )
            self.sandbox.write_file(path, content)
            return f"Successfully wrote to {path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

class ReplaceInFileTool(BaseTool):
    name = "replace_in_file"
    description = "Replace a specific text block with a new text block in a file. Whitespace-tolerant."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file"
            },
            "old_text": {
                "type": "string",
                "description": "The existing text to replace"
            },
            "new_text": {
                "type": "string",
                "description": "The new text to insert"
            }
        },
        "required": ["path", "old_text", "new_text"]
    }
    category = "MODIFY"
    
    def __init__(self, sandbox: SandboxEnvironment):
        self.sandbox = sandbox
        
    def execute(self, path: str, old_text: str = None, new_text: str = None, **kwargs) -> str:
        try:
            if old_text is None:
                old_text = kwargs.get("target") or kwargs.get("search") or kwargs.get("find") or ""
            if new_text is None:
                new_text = kwargs.get("replacement") or kwargs.get("replace") or ""
            content = self.sandbox.read_file(path)
            
            def apply_and_save(target_content: str, label: str = "") -> str:
                syntax_err = validate_syntax_before_write(self.sandbox, path, target_content)
                if syntax_err:
                    return (
                        f"Error: Syntax validation failed after applying replacement to '{path}'.\n"
                        f"{syntax_err}\n"
                        f"Notice: The replacement was NOT applied to disk to protect repository integrity. "
                        f"Please ensure the replacement produces complete, valid syntax."
                    )
                self.sandbox.write_file(path, target_content)
                suffix = f" ({label})" if label else ""
                return f"Successfully replaced text in {path}{suffix}"

            # Tier 1: Direct exact match
            if old_text in content:
                new_content = content.replace(old_text, new_text, 1)
                return apply_and_save(new_content)
                
            # Tier 2: Newline-normalized match (CRLF / LF)
            content_norm = content.replace('\r\n', '\n')
            old_norm = old_text.replace('\r\n', '\n')
            if old_norm in content_norm:
                new_content = content_norm.replace(old_norm, new_text.replace('\r\n', '\n'), 1)
                return apply_and_save(new_content, "newline-normalized")

            # Tier 3: Whitespace-tolerant line-level matching
            content_lines = content_norm.split('\n')
            target_lines = [l.strip() for l in old_norm.split('\n') if l.strip()]
            
            if target_lines:
                match_indices = []
                for i in range(len(content_lines) - len(target_lines) + 1):
                    window = [content_lines[i + j].strip() for j in range(len(target_lines))]
                    if window == target_lines:
                        match_indices.append(i)
                        
                if len(match_indices) == 1:
                    start_idx = match_indices[0]
                    end_idx = start_idx + len(target_lines)
                    before = content_lines[:start_idx]
                    after = content_lines[end_idx:]
                    replacement_lines = new_text.replace('\r\n', '\n').split('\n')
                    final_lines = before + replacement_lines + after
                    return apply_and_save('\n'.join(final_lines), "whitespace-tolerant block match")
                elif len(match_indices) > 1:
                    return f"Error: Found multiple ({len(match_indices)}) matching blocks in {path}. Provide more surrounding context."

            file_len = len(content_lines)
            snippet = ""
            if file_len <= 120:
                snippet = f"\n\n[Current contents of {path} ({file_len} lines)]:\n{content_norm}"
            else:
                snippet = f"\n\n[File {path} has {file_len} lines. Use read_file to view current lines or write_file to overwrite cleanly.]"
            return (
                f"Error: The target old_text could not be found in {path}. "
                f"The file content may have changed from earlier edits.\n"
                f"Actionable Hint: Call read_file('{path}') to inspect current lines, or use write_file('{path}', ...) to rewrite the file cleanly.{snippet}"
            )
        except Exception as e:
            return f"Error replacing text: {str(e)}"

class ApplyPatchTool(BaseTool):
    name = "apply_patch"
    description = "Apply a unified diff or patch to a file."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the target file"
            },
            "patch": {
                "type": "string",
                "description": "The unified diff or patch text"
            }
        },
        "required": ["path", "patch"]
    }
    category = "MODIFY"

    def __init__(self, sandbox: SandboxEnvironment):
        self.sandbox = sandbox

    def execute(self, path: str = "", patch: str = "", **kwargs) -> str:
        try:
            patch = patch or kwargs.get("diff") or kwargs.get("patch_text") or kwargs.get("content") or kwargs.get("text") or ""
            path = path or kwargs.get("file") or kwargs.get("target_file") or kwargs.get("filepath") or kwargs.get("filename") or ""
            
            if not path:
                return "Error applying patch: missing required parameter 'path'."
            if not patch:
                return "Error applying patch: missing required parameter 'patch' (diff content)."

            if not patch.endswith('\n'):
                patch += '\n'
            patch_file = f".tmp_patch_{abs(hash(patch)) % 100000}.patch"
            self.sandbox.write_file(patch_file, patch)
            
            # Try git apply with recount and whitespace fix
            code, stdout, stderr = self.sandbox.run_command(f"git apply --recount --whitespace=fix {patch_file} 2>&1")
            if code != 0:
                # Try patch command fallback
                code, stdout, stderr = self.sandbox.run_command(f"patch -p0 < {patch_file} 2>&1 || patch -p1 < {patch_file} 2>&1")
                
            self.sandbox.run_command(f"rm -f {patch_file}")
            if code == 0:
                return f"Successfully applied patch to {path}"
            return f"Error applying patch to {path}: {stdout or stderr or 'Patch could not be applied cleanly. Use replace_in_file instead.'}"
        except Exception as e:
            return f"Error applying patch: {str(e)}"
