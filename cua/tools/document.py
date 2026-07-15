"""Document tools using Kimi Files API: upload, extract, list, cleanup."""

import hashlib
import time
from pathlib import Path

# Track uploaded file IDs for lifecycle management
_uploaded_files: dict[str, str] = {}  # sha8 -> file_id


# --- Schemas ---

READ_DOCUMENT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ReadDocument",
        "description": "Upload a file to Kimi and extract its text content. Supports PDF, DOCX, TXT, images (OCR), and more. Returns a doc reference you can pass to DraftContent for reference-based writing. Use this instead of file_read for non-text files or when you need structured extraction.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to upload and extract",
                },
                "purpose": {
                    "type": "string",
                    "enum": ["file-extract", "image"],
                    "description": "file-extract for documents (text extraction), image for images",
                },
            },
            "required": ["path"],
        },
    },
}


LIST_DOCUMENTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ListDocuments",
        "description": "List all files uploaded to Kimi. Use to see what documents are available for reference.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


DELETE_DOCUMENT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "DeleteDocument",
        "description": "Delete a file from Kimi by its file ID or doc reference. Use to clean up after you're done with a document.",
        "parameters": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "File ID or doc reference (doc:<sha8>) to delete",
                },
            },
            "required": ["ref"],
        },
    },
}


CLEANUP_DOCUMENTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "CleanupDocuments",
        "description": "Delete ALL uploaded files from Kimi. Use periodically to free up your 1000-file quota.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


# --- Executors ---

def _get_client():
    import os
    from openai import OpenAI
    from cua.config import load_config
    config = load_config()
    api_key = config.get("moonshot_api_key", "") or os.environ.get("MOONSHOT_API_KEY", "")
    base_url = config.get("base_url", "https://api.moonshot.cn/v1")
    return OpenAI(api_key=api_key, base_url=base_url)


def execute_read_document(path: str, purpose: str = "file-extract") -> dict:
    """Upload and extract document content."""
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        return {
            "content": [{"type": "text", "text": f"File not found: {path}"}],
            "mouse_pos": None, "last_screenshot": None,
        }

    try:
        client = _get_client()
        # Upload
        with open(file_path, "rb") as f:
            file_obj = client.files.create(file=f, purpose=purpose)
        file_id = file_obj.id
        filename = file_obj.filename

        # Track for lifecycle
        sha = hashlib.sha256(str(file_path).encode()).hexdigest()[:8]
        _uploaded_files[sha] = file_id

        # Extract content
        content = client.files.content(file_id=file_id).text

        if len(content) > 3000:
            preview = content[:3000] + f"\n...(truncated, {len(content)} chars total)"
        else:
            preview = content

        return {
            "content": [{"type": "text", "text": (
                f"Document: {filename}\n"
                f"Reference: doc:{sha}\n"
                f"Size: {file_path.stat().st_size:,} bytes\n"
                f"Content:\n{preview}"
            )}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"ReadDocument failed: {e}"}],
            "mouse_pos": None, "last_screenshot": None,
        }


def execute_list_documents() -> dict:
    """List uploaded files."""
    try:
        client = _get_client()
        files = client.files.list()
        if not files.data:
            return {
                "content": [{"type": "text", "text": "No files uploaded."}],
                "mouse_pos": None, "last_screenshot": None,
            }

        lines = [f"{len(files.data)} file(s) uploaded:"]
        for f in files.data:
            lines.append(f"  {f.id} — {f.filename} ({f.bytes} bytes, {f.purpose})")
        return {
            "content": [{"type": "text", "text": "\n".join(lines)}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"ListDocuments failed: {e}"}],
            "mouse_pos": None, "last_screenshot": None,
        }


def execute_delete_document(ref: str) -> dict:
    """Delete a single uploaded file."""
    try:
        client = _get_client()
        file_id = ref

        # If it's a doc:sha8 reference, resolve it
        if ref.startswith("doc:"):
            sha = ref[4:].strip()[:8]
            file_id = _uploaded_files.get(sha, ref)

        client.files.delete(file_id=file_id)
        return {
            "content": [{"type": "text", "text": f"Deleted: {file_id}"}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"DeleteDocument failed: {e}"}],
            "mouse_pos": None, "last_screenshot": None,
        }


def execute_cleanup_documents() -> dict:
    """Delete all uploaded files."""
    try:
        client = _get_client()
        files = client.files.list()
        count = len(files.data)
        for f in files.data:
            try:
                client.files.delete(file_id=f.id)
            except Exception:
                pass
        _uploaded_files.clear()
        return {
            "content": [{"type": "text", "text": f"Cleaned up {count} file(s)."}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"CleanupDocuments failed: {e}"}],
            "mouse_pos": None, "last_screenshot": None,
        }
