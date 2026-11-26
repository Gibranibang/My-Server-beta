"""
http_transfer_manager.py
Mesin RAM clipboard, Hybrid Paste Dispatcher, antrian HTTP transfer rekursif berbatas 3 worker,
download streaming ber-verifikasi commonpath(), dan state machine konflik ala Windows Explorer.
"""

from __future__ import annotations

import concurrent.futures
import copy
import http.client
import json
import os
import posixpath
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import smb_mount_manager

DEFAULT_MAX_WORKERS = 3
DEFAULT_CHUNK_SIZE = 262144  # 256 KB
DEFAULT_CHUNK_THRESHOLD = 524288  # 512 KB
DEFAULT_MAX_CHUNK_RETRIES = 3
WRITABLE_ROLES = ("system_admin", "owner", "administrator", "editor")


def _sanitize_rel_component(name: str) -> str:
    """Validasi satu segmen nama berkas/folder agar bebas path traversal dan NUL byte."""
    if not isinstance(name, str) or "\x00" in name:
        raise ValueError("INVALID_PATH_COMPONENT")
    raw = name.strip()
    if not raw or raw in (".", "..") or "/" in raw or "\\" in raw:
        raise ValueError(f"INVALID_PATH_COMPONENT:{raw!r}")
    clean = os.path.basename(raw)
    if not clean or clean in (".", "..") or "\x00" in clean:
        raise ValueError(f"INVALID_PATH_COMPONENT:{raw!r}")
    return clean


def _split_and_validate_rel_path(rel_path: str) -> List[str]:
    """Memecah rel_path server dan menolak segmen traversal ('.', '..', '\\x00')."""
    if not isinstance(rel_path, str) or "\x00" in rel_path:
        raise ValueError("INVALID_PATH_TRAVERSAL")
    norm = rel_path.replace("\\", "/").strip("/")
    if not norm:
        return []
    parts: List[str] = []
    for seg in norm.split("/"):
        if not seg:
            continue
        parts.append(_sanitize_rel_component(seg))
    return parts


def _safe_local_join(dest_dir: str, *rel_parts: str) -> str:
    """
    Menggabungkan dest_dir dengan komponen relatif yang telah disanitasi
    dan memverifikasi os.path.commonpath([dest_real, target_real]) == dest_real.
    """
    dest_real = os.path.realpath(os.path.abspath(dest_dir))
    clean_parts = [_sanitize_rel_component(p) for p in rel_parts]
    target_abs = os.path.abspath(os.path.join(dest_real, *clean_parts))
    target_real = os.path.realpath(target_abs)
    if os.path.commonpath([dest_real, target_real]) != dest_real:
        raise ValueError("PATH_TRAVERSAL_BLOCKED")
    return target_abs


def _pick_non_colliding_name(existing_names: Set[str], desired: str, is_dir: bool) -> str:
    """Menghasilkan nama unik ala Windows Explorer: 'stem (1).ext' atau 'folder (1)'."""
    if desired not in existing_names:
        return desired
    stem, ext = ("", "") if is_dir else os.path.splitext(desired)
    if not stem:
        stem = desired
    idx = 1
    while True:
        cand = f"{stem} ({idx}){ext}"
        if cand not in existing_names:
            return cand
        idx += 1


def _pick_non_colliding_local_path(dest_dir: str, desired: str, is_dir: bool) -> Tuple[str, str]:
    """Menghasilkan (nama_aman, path_absolut) yang belum ada di disk lokal."""
    cand_abs = _safe_local_join(dest_dir, desired)
    if not os.path.exists(cand_abs):
        return desired, cand_abs
    stem, ext = ("", "") if is_dir else os.path.splitext(desired)
    if not stem:
        stem = desired
    idx = 1
    while True:
        cand_name = f"{stem} ({idx}){ext}"
        cand_abs = _safe_local_join(dest_dir, cand_name)
        if not os.path.exists(cand_abs):
            return cand_name, cand_abs
        idx += 1


def _build_multipart_payload(
    fields: Dict[str, str],
    file_field: Tuple[str, str, bytes],
) -> Tuple[bytes, str]:
    boundary = f"----MyServerXferBoundary{uuid.uuid4().hex[:12]}"
    chunks: List[bytes] = []
    for k, v in fields.items():
        chunks.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{k}"\r\n\r\n'
            f"{v}\r\n".encode("utf-8")
        )
    f_name, filename, content_bytes = file_field
    chunks.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{f_name}"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n".encode("utf-8")
    )
    chunks.append(content_bytes)
    chunks.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


@dataclass
class TransferJobState:
    job_id: str
    direction: str  # "upload" | "download" | "server_copy"
    status: str = "running"  # "running" | "paused" | "awaiting_conflict" | "completed" | "cancelled" | "failed"
    server_id: str = ""
    server_name: str = ""
    dest_display: str = ""
    total_files: int = 0
    completed_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    bytes_total: int = 0
    bytes_done: int = 0
    active_workers: int = 0
    speed_bps: float = 0.0
    eta_seconds: Optional[float] = None
    active_item: str = ""
    error: str = ""
    conflict: Optional[Dict[str, Any]] = None
    items: List[Dict[str, Any]] = field(default_factory=list)
    started_monotonic: float = field(default_factory=time.monotonic)
    finished_monotonic: Optional[float] = None
    pause_gate: threading.Event = field(default_factory=threading.Event)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    conflict_event: threading.Event = field(default_factory=threading.Event)
    conflict_decision: str = "rename"
    apply_to_all_action: Optional[str] = None
    active_part_paths: Set[str] = field(default_factory=set)
    local_dest_dir: str = ""
    clipboard_copied_at: float = 0.0

    def __post_init__(self) -> None:
        self.pause_gate.set()


class HttpTransferManager:
    """
    Pengelola clipboard in-memory dan antrian transfer HTTP Explorer <-> MyServer Backend.
    """

    def __init__(
        self,
        resolve_smb_target_fn: Optional[Callable[[str], Tuple[bool, Dict[str, Any]]]] = None,
        backend_json_request_fn: Optional[
            Callable[[str, str, Dict[str, str], Optional[bytes], float], Tuple[int, Any]]
        ] = None,
        get_backend_session_fn: Optional[Callable[[str], Tuple[str, str, str, str]]] = None,
        notify_local_dir_fn: Optional[Callable[[str], bool]] = None,
        on_toast_fn: Optional[Callable[[str, str, str], None]] = None,
        max_workers: int = DEFAULT_MAX_WORKERS,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_threshold: int = DEFAULT_CHUNK_THRESHOLD,
        max_chunk_retries: int = DEFAULT_MAX_CHUNK_RETRIES,
    ) -> None:
        self.resolve_smb_target_fn = resolve_smb_target_fn
        self.backend_json_request_fn = backend_json_request_fn
        self.get_backend_session_fn = get_backend_session_fn
        self.notify_local_dir_fn = notify_local_dir_fn or smb_mount_manager.notify_local_folder_updated
        self.on_toast_fn = on_toast_fn

        self.max_workers = max(1, min(4, int(max_workers)))
        self.chunk_size = int(chunk_size)
        self.chunk_threshold = int(chunk_threshold)
        self.max_chunk_retries = max(1, int(max_chunk_retries))

        self._clipboard_lock = threading.Lock()
        self._EXPLORER_CLIPBOARD: Dict[str, Any] = {
            "mode": "",
            "server_id": "",
            "server_name": "",
            "source_origin": "",
            "items": [],
            "copied_at": 0.0,
        }

        self._jobs_lock = threading.Lock()
        self._jobs: Dict[str, TransferJobState] = {}
        self._latest_job_id: str = ""
        self._job_threads: Dict[str, threading.Thread] = {}

    # ------------------------------------------------------------------
    # RAM Clipboard In-Memory (tanpa menyentuh SQLite Backend)
    # ------------------------------------------------------------------
    def set_clipboard_local(self, items: List[Any]) -> Dict[str, Any]:
        normalized: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for raw in items or []:
            if isinstance(raw, dict):
                p = str(raw.get("path") or raw.get("local_path") or "").strip()
                is_dir = raw.get("is_dir")
            else:
                p = str(raw or "").strip()
                is_dir = None
            if not p:
                continue
            key = os.path.normcase(os.path.abspath(p)) if os.path.exists(p) else p
            if key in seen:
                continue
            seen.add(key)
            if is_dir is None:
                is_dir = os.path.isdir(p)
            normalized.append({
                "path": p,
                "name": os.path.basename(p.rstrip("\\/")) or p,
                "is_dir": bool(is_dir),
            })

        snapshot = {
            "mode": "local" if normalized else "",
            "server_id": "",
            "server_name": "",
            "source_origin": "explorer",
            "items": normalized,
            "copied_at": time.time(),
        }
        with self._clipboard_lock:
            self._EXPLORER_CLIPBOARD = snapshot
            return copy.deepcopy(self._EXPLORER_CLIPBOARD)

    def set_clipboard_server(
        self,
        server_id: str,
        server_name: str,
        items: List[Any],
        source_origin: str = "explorer",
    ) -> Dict[str, Any]:
        normalized: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for raw in items or []:
            if isinstance(raw, dict):
                rel = str(raw.get("rel_path") or raw.get("path") or "").strip().strip("/")
                name = str(raw.get("name") or (rel.split("/")[-1] if rel else "")).strip()
                is_dir = raw.get("is_dir")
                size = int(raw.get("size") or 0)
            else:
                rel = str(raw or "").strip().strip("/")
                name = rel.split("/")[-1] if rel else ""
                is_dir = None
                size = 0
            if not rel or rel in seen:
                continue
            seen.add(rel)
            normalized.append({
                "rel_path": rel,
                "name": name,
                "is_dir": is_dir if isinstance(is_dir, bool) else None,
                "size": size,
            })

        snapshot = {
            "mode": "server" if normalized else "",
            "server_id": str(server_id or ""),
            "server_name": str(server_name or ""),
            "source_origin": str(source_origin or "explorer"),
            "items": normalized,
            "copied_at": time.time(),
        }
        with self._clipboard_lock:
            self._EXPLORER_CLIPBOARD = snapshot
            return copy.deepcopy(self._EXPLORER_CLIPBOARD)

    def get_clipboard(self) -> Dict[str, Any]:
        with self._clipboard_lock:
            snap = copy.deepcopy(self._EXPLORER_CLIPBOARD)
        mode = snap.get("mode")
        snap["kind"] = mode if mode in ("local", "server") else "empty"
        return snap

    def _clear_clipboard_if_unchanged(self, expected_copied_at: float) -> bool:
        if not expected_copied_at:
            return False
        with self._clipboard_lock:
            if float(self._EXPLORER_CLIPBOARD.get("copied_at") or 0.0) == float(expected_copied_at):
                self._EXPLORER_CLIPBOARD = {
                    "mode": "",
                    "server_id": "",
                    "server_name": "",
                    "source_origin": "",
                    "items": [],
                    "copied_at": 0.0,
                }
                return True
        return False

    def clear_clipboard(self) -> None:
        with self._clipboard_lock:
            self._EXPLORER_CLIPBOARD = {
                "mode": "",
                "server_id": "",
                "server_name": "",
                "source_origin": "",
                "items": [],
                "copied_at": 0.0,
            }

    # ------------------------------------------------------------------
    # HTTP Transport Helpers (http.client / urllib.request streaming)
    # ------------------------------------------------------------------
    def _resolve_session(self, server_id: str = "") -> Tuple[str, str, str, str]:
        if self.get_backend_session_fn is None:
            raise RuntimeError("BACKEND_SESSION_UNAVAILABLE")
        sid, sname, base_url, token = self.get_backend_session_fn(server_id or "")
        if not base_url or not token:
            raise RuntimeError("BACKEND_SESSION_UNAUTHENTICATED")
        return str(sid or ""), str(sname or ""), str(base_url).rstrip("/"), str(token)

    def _http_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        body_bytes: Optional[bytes] = None,
        timeout: float = 20.0,
    ) -> Tuple[int, Any]:
        req_headers = dict(headers or {})
        if self.backend_json_request_fn is not None:
            return self.backend_json_request_fn(method, url, req_headers, body_bytes, timeout)

        parsed = urllib.parse.urlsplit(url)
        conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        conn = conn_cls(parsed.hostname, parsed.port, timeout=timeout)
        path_q = parsed.path or "/"
        if parsed.query:
            path_q = f"{path_q}?{parsed.query}"
        try:
            conn.request(method, path_q, body=body_bytes, headers=req_headers)
            resp = conn.getresponse()
            raw = resp.read()
            status = int(resp.status)
            ctype = str(resp.getheader("Content-Type") or "")
            if "application/json" in ctype or raw.lstrip().startswith((b"{", b"[")):
                try:
                    return status, json.loads(raw.decode("utf-8"))
                except Exception:
                    return status, raw.decode("utf-8", errors="replace")
            return status, raw
        finally:
            conn.close()

    def _api_json(
        self,
        base_url: str,
        token: str,
        method: str,
        api_path: str,
        payload: Optional[Dict[str, Any]] = None,
        timeout: float = 20.0,
    ) -> Tuple[int, Any]:
        headers = {"Authorization": f"Bearer {token}"}
        body: Optional[bytes] = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        return self._http_request(method, f"{base_url}{api_path}", headers=headers, body_bytes=body, timeout=timeout)

    def _browse_dir(self, base_url: str, token: str, rel_path: str) -> Tuple[int, Dict[str, Any]]:
        q = urllib.parse.urlencode({"path": rel_path})
        st, data = self._http_request(
            "GET",
            f"{base_url}/api/v1/storage/browse-files?{q}",
            headers={"Authorization": f"Bearer {token}"},
        )
        return st, data if isinstance(data, dict) else {"detail": str(data)}

    def _mkdir(self, base_url: str, token: str, rel_path: str) -> Dict[str, Any]:
        st, data = self._api_json(base_url, token, "POST", "/api/v1/storage/mkdir", {"path": rel_path})
        if st >= 400 or not isinstance(data, dict):
            raise RuntimeError(f"HTTP {st} on mkdir({rel_path}): {data}")
        return data

    # ------------------------------------------------------------------
    # Quick Picker Browse API
    # ------------------------------------------------------------------
    def browse_directory(
        self,
        server_id: Optional[str] = None,
        path: str = "",
        source: str = "disks",
    ) -> Dict[str, Any]:
        sid, sname, base_url, token = self._resolve_session(server_id or "")
        src = str(source or "disks").strip().lower()
        clean_path = str(path or "").strip().strip("/")

        if src == "shared" and not clean_path:
            st, data = self._http_request(
                "GET",
                f"{base_url}/api/v1/storage/shared-with-me",
                headers={"Authorization": f"Bearer {token}"},
            )
            if st >= 400 or not isinstance(data, dict):
                return {"ok": False, "status": st, "detail": str(data), "items": [], "writable": False}
            raw_items = data.get("shares") or data.get("items") or []
            out_items: List[Dict[str, Any]] = []
            any_writable = False
            for it in raw_items:
                if not isinstance(it, dict):
                    continue
                role = str(it.get("role") or it.get("effective_role") or "viewer").strip().lower()
                is_w = role in ("editor", "administrator", "owner", "system_admin")
                if is_w:
                    any_writable = True
                row = dict(it)
                row["role"] = role
                row["effective_role"] = role
                row["writable"] = is_w
                row["is_dir"] = bool(it.get("is_dir", True)) if str(it.get("type") or "").lower() != "file" else False
                if not row.get("relative_path"):
                    row["relative_path"] = str(it.get("created_path") or it.get("share_path") or it.get("path") or "").strip("/")
                out_items.append(row)
            return {
                "ok": True,
                "server_id": sid,
                "server_name": sname,
                "source": "shared",
                "path": "",
                "effective_role": "shared_list",
                "writable": any_writable,
                "items": out_items,
            }

        if not clean_path and src == "disks":
            st, data = self._http_request(
                "GET",
                f"{base_url}/api/v1/storage/disks",
                headers={"Authorization": f"Bearer {token}"},
            )
            if st >= 400 or not isinstance(data, dict):
                return {"ok": False, "status": st, "detail": str(data), "items": [], "writable": False}
            is_admin = bool(data.get("is_admin", False))
            disks = data.get("disks") or []
            norm_disks: List[Dict[str, Any]] = []
            for d in disks:
                if not isinstance(d, dict):
                    continue
                d_name = str(d.get("name") or d.get("id") or d.get("path") or "").strip("/")
                if not d_name:
                    continue
                norm_disks.append({
                    **d,
                    "name": d_name,
                    "relative_path": d_name,
                    "is_dir": True,
                })
            return {
                "ok": True,
                "server_id": sid,
                "server_name": sname,
                "source": "disks",
                "path": "",
                "effective_role": "system_admin" if is_admin else "editor",
                "writable": False,
                "items": norm_disks,
            }

        st, data = self._browse_dir(base_url, token, clean_path)
        if st >= 400 or not isinstance(data, dict):
            return {"ok": False, "status": st, "detail": str(data), "items": [], "writable": False}
        eff_role = str(data.get("effective_role") or "").strip().lower()
        writable = eff_role in WRITABLE_ROLES
        raw_dir_items = data.get("items") or []
        norm_items: List[Dict[str, Any]] = []
        for it in raw_dir_items:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name") or "").strip()
            rel = str(it.get("relative_path") or "").strip("/")
            if not rel and name:
                rel = f"{clean_path}/{name}".strip("/")
            is_dir = bool(it.get("is_dir")) or str(it.get("type") or "").lower() in ("dir", "folder", "directory")
            norm_items.append({
                **it,
                "name": name or rel.rsplit("/", 1)[-1],
                "relative_path": rel,
                "is_dir": is_dir,
            })
        return {
            "ok": True,
            "server_id": sid,
            "server_name": sname,
            "source": src,
            "path": clean_path,
            "effective_role": eff_role,
            "writable": writable,
            "items": norm_items,
        }

    # ------------------------------------------------------------------
    # Conflict State Machine + Pause/Resume/Cancel
    # ------------------------------------------------------------------
    def _resolve_conflict_decision(
        self,
        job: TransferJobState,
        item_name: str,
        dest_path: str,
        is_dir: bool,
        remaining_hint: int = 0,
    ) -> str:
        if job.cancel_event.is_set():
            return "skip"
        if job.apply_to_all_action is not None:
            return job.apply_to_all_action

        job.conflict_event.clear()
        with self._jobs_lock:
            job.status = "awaiting_conflict"
            job.conflict = {
                "job_id": job.job_id,
                "item_name": item_name,
                "dest_path": dest_path,
                "is_dir": bool(is_dir),
                "remaining_conflicts_hint": int(remaining_hint),
            }

        job.conflict_event.wait()
        if job.cancel_event.is_set():
            return "skip"
        return job.conflict_decision

    def resolve_conflict(
        self,
        job_id: str,
        action: str,
        apply_to_all: bool = False,
    ) -> Dict[str, Any]:
        clean_action = str(action or "").strip().lower()
        if clean_action not in ("overwrite", "rename", "skip"):
            return {"success": False, "code": "INVALID_CONFLICT_ACTION"}

        with self._jobs_lock:
            job = self._jobs.get(job_id) or self._jobs.get(self._latest_job_id)
            if job is None:
                return {"success": False, "code": "JOB_NOT_FOUND"}
            job.conflict_decision = clean_action
            if apply_to_all:
                job.apply_to_all_action = clean_action
            job.conflict = None
            if not job.cancel_event.is_set():
                job.status = "paused" if not job.pause_gate.is_set() else "running"
            job.conflict_event.set()
            return {"success": True, "job_id": job.job_id, "action": clean_action, "apply_to_all": bool(apply_to_all)}

    def _get_target_job(self, job_id: Optional[str] = None) -> Optional[TransferJobState]:
        with self._jobs_lock:
            if job_id:
                return self._jobs.get(job_id)
            return self._jobs.get(self._latest_job_id)

    def pause_job(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        job = self._get_target_job(job_id)
        if job is None:
            return {"success": False, "code": "JOB_NOT_FOUND"}
        job.pause_gate.clear()
        with self._jobs_lock:
            if job.status == "running":
                job.status = "paused"
        return {"success": True, "job_id": job.job_id, "status": job.status}

    def resume_job(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        job = self._get_target_job(job_id)
        if job is None:
            return {"success": False, "code": "JOB_NOT_FOUND"}
        with self._jobs_lock:
            if job.status == "paused":
                job.status = "running"
        job.pause_gate.set()
        return {"success": True, "job_id": job.job_id, "status": job.status}

    def _cleanup_part_files(self, job: TransferJobState) -> int:
        removed = 0
        with self._jobs_lock:
            part_paths = list(job.active_part_paths)
            job.active_part_paths.clear()
            dest_root = job.local_dest_dir
        for p in part_paths:
            try:
                if os.path.exists(p):
                    os.remove(p)
                    removed += 1
            except OSError:
                pass
        if dest_root and os.path.isdir(dest_root):
            for r_dir, _, files in os.walk(dest_root):
                for fn in files:
                    if ".myserver-part." in fn:
                        try:
                            os.remove(os.path.join(r_dir, fn))
                            removed += 1
                        except OSError:
                            pass
        return removed

    def cancel_job(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        job = self._get_target_job(job_id)
        if job is None:
            return {"success": False, "code": "JOB_NOT_FOUND"}
        job.cancel_event.set()
        job.pause_gate.set()
        job.conflict_event.set()
        with self._jobs_lock:
            job.conflict = None
            job.status = "cancelled"
            job.finished_monotonic = time.monotonic()
        self._cleanup_part_files(job)
        return {"success": True, "job_id": job.job_id, "status": "cancelled"}

    def clear_finished(self) -> Dict[str, Any]:
        with self._jobs_lock:
            to_del = [
                jid for jid, j in self._jobs.items()
                if j.status in ("completed", "cancelled", "failed")
            ]
            for jid in to_del:
                self._jobs.pop(jid, None)
            if self._latest_job_id in to_del:
                self._latest_job_id = next(reversed(self._jobs), "")
        return {"success": True, "cleared": len(to_del)}

    def wait_for_job(self, job_id: Optional[str] = None, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """Helper sinkron (terutama untuk test/CLI) menunggu thread job selesai."""
        target_id = job_id or self._latest_job_id
        with self._jobs_lock:
            t = self._job_threads.get(target_id)
        if t is not None:
            t.join(timeout=timeout)
        return self.get_status(target_id)

    def get_status(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        job = self._get_target_job(job_id)
        if job is None:
            return {
                "has_job": False,
                "job_id": "",
                "status": "idle",
                "direction": "",
                "speed_bps": 0.0,
                "eta_seconds": None,
                "active_workers": 0,
                "bytes_done": 0,
                "bytes_total": 0,
                "total_files": 0,
                "completed_files": 0,
                "skipped_files": 0,
                "failed_files": 0,
                "conflict": None,
                "items": [],
                "clipboard": self.get_clipboard(),
            }
        with self._jobs_lock:
            end_ts = job.finished_monotonic or time.monotonic()
            elapsed = max(0.001, end_ts - job.started_monotonic)
            speed_bps = round(job.bytes_done / elapsed, 2) if job.bytes_done > 0 else 0.0
            remaining_bytes = max(0, job.bytes_total - job.bytes_done)
            eta = round(remaining_bytes / speed_bps, 1) if speed_bps > 0 and remaining_bytes > 0 else 0.0
            return {
                "has_job": True,
                "job_id": job.job_id,
                "status": job.status,
                "direction": job.direction,
                "server_id": job.server_id,
                "server_name": job.server_name,
                "dest_display": job.dest_display,
                "dest_label": job.dest_display,
                "speed_bps": speed_bps,
                "eta_seconds": eta if job.status in ("running", "paused", "awaiting_conflict") else 0.0,
                "active_workers": job.active_workers,
                "bytes_done": job.bytes_done,
                "bytes_total": job.bytes_total,
                "total_files": job.total_files,
                "completed_files": job.completed_files,
                "skipped_files": job.skipped_files,
                "failed_files": job.failed_files,
                "active_item": job.active_item,
                "conflict": copy.deepcopy(job.conflict),
                "items": copy.deepcopy(job.items),
                "clipboard": self.get_clipboard(),
                "error": job.error,
            }

    # ------------------------------------------------------------------
    # Upload Engine (<= 512 KB direct, > 512 KB chunked 256 KB + 3x retry)
    # ------------------------------------------------------------------
    def _upload_file_direct(
        self,
        base_url: str,
        token: str,
        server_dir_rel: str,
        filename: str,
        local_path: str,
        job: TransferJobState,
        item_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        job.pause_gate.wait()
        if job.cancel_event.is_set():
            raise InterruptedError("CANCELLED")
        with open(local_path, "rb") as f:
            raw_bytes = f.read()
        payload, ctype = _build_multipart_payload(
            {"path": server_dir_rel, "filename": filename},
            ("file", filename, raw_bytes),
        )
        st, resp = self._http_request(
            "POST",
            f"{base_url}/api/v1/storage/upload",
            headers={"Authorization": f"Bearer {token}", "Content-Type": ctype},
            body_bytes=payload,
            timeout=30.0,
        )
        if st >= 400:
            raise RuntimeError(f"HTTP {st} on upload({filename}): {resp}")
        with self._jobs_lock:
            job.bytes_done += len(raw_bytes)
            job.completed_files += 1
            if item_state is not None:
                item_state["bytes_done"] = len(raw_bytes)
                item_state["bytes_total"] = max(int(item_state.get("bytes_total") or 0), len(raw_bytes))
                item_state["status"] = "done"

    def _upload_file_chunked(
        self,
        base_url: str,
        token: str,
        server_dir_rel: str,
        filename: str,
        local_path: str,
        job: TransferJobState,
        item_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        file_size = os.path.getsize(local_path)
        total_chunks = max(1, (file_size + self.chunk_size - 1) // self.chunk_size)
        upload_id = uuid.uuid4().hex[:16]

        with open(local_path, "rb") as f:
            for chunk_index in range(total_chunks):
                job.pause_gate.wait()
                if job.cancel_event.is_set():
                    raise InterruptedError("CANCELLED")
                chunk_bytes = f.read(self.chunk_size)
                payload, ctype = _build_multipart_payload(
                    {
                        "upload_id": upload_id,
                        "chunk_index": str(chunk_index),
                        "total_chunks": str(total_chunks),
                    },
                    ("file", f"part_{chunk_index:06d}.tmp", chunk_bytes),
                )
                last_err: Optional[Exception] = None
                for attempt in range(self.max_chunk_retries):
                    job.pause_gate.wait()
                    if job.cancel_event.is_set():
                        raise InterruptedError("CANCELLED")
                    try:
                        st, resp = self._http_request(
                            "POST",
                            f"{base_url}/api/v1/storage/upload-chunk",
                            headers={"Authorization": f"Bearer {token}", "Content-Type": ctype},
                            body_bytes=payload,
                            timeout=30.0,
                        )
                        if st >= 500 or st == 0:
                            raise RuntimeError(f"Transient HTTP {st}: {resp}")
                        if st >= 400:
                            raise ValueError(f"HTTP {st} on upload-chunk: {resp}")
                        last_err = None
                        break
                    except ValueError:
                        raise
                    except Exception as exc:
                        last_err = exc
                        if attempt + 1 < self.max_chunk_retries:
                            time.sleep(0.05)
                if last_err is not None:
                    raise last_err
                with self._jobs_lock:
                    job.bytes_done += len(chunk_bytes)
                    if item_state is not None:
                        item_state["bytes_done"] = int(item_state.get("bytes_done") or 0) + len(chunk_bytes)

        job.pause_gate.wait()
        if job.cancel_event.is_set():
            raise InterruptedError("CANCELLED")

        q = urllib.parse.urlencode({
            "upload_id": upload_id,
            "path": server_dir_rel,
            "filename": filename,
            "total_chunks": total_chunks,
        })
        st, resp = self._http_request(
            "POST",
            f"{base_url}/api/v1/storage/upload-commit?{q}",
            headers={"Authorization": f"Bearer {token}"},
            body_bytes=b"",
            timeout=60.0,
        )
        if st >= 400:
            raise RuntimeError(f"HTTP {st} on upload-commit({filename}): {resp}")
        with self._jobs_lock:
            job.completed_files += 1
            if item_state is not None:
                item_state["bytes_done"] = max(
                    int(item_state.get("bytes_done") or 0),
                    int(item_state.get("bytes_total") or 0),
                    file_size,
                )
                item_state["bytes_total"] = max(int(item_state.get("bytes_total") or 0), file_size)
                item_state["status"] = "done"

    def _run_upload_job(
        self,
        job: TransferJobState,
        local_sources: List[str],
        server_dest_rel: str,
    ) -> None:
        try:
            _, _, base_url, token = self._resolve_session(job.server_id)
            dir_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}

            def _get_existing_map(rel_dir: str) -> Dict[str, Dict[str, Any]]:
                if rel_dir not in dir_cache:
                    st, data = self._browse_dir(base_url, token, rel_dir)
                    if st >= 400:
                        raise RuntimeError(f"HTTP {st} on browse-files({rel_dir}): {data}")
                    dir_cache[rel_dir] = {
                        str(itm.get("name") or ""): itm
                        for itm in (data.get("items") or [])
                        if isinstance(itm, dict)
                    }
                return dir_cache[rel_dir]

            file_jobs: List[Tuple[str, str, str, int, Dict[str, Any]]] = []

            def _stage_tree(local_path: str, target_parent_rel: str) -> None:
                if job.cancel_event.is_set():
                    return
                abs_lp = os.path.abspath(local_path)
                base_name = os.path.basename(abs_lp)
                is_dir = os.path.isdir(abs_lp)
                existing = _get_existing_map(target_parent_rel)
                chosen_name = base_name

                if base_name in existing:
                    action = self._resolve_conflict_decision(
                        job,
                        item_name=base_name,
                        dest_path=posixpath.join(target_parent_rel, base_name) if target_parent_rel else base_name,
                        is_dir=is_dir,
                    )
                    if action == "skip":
                        with self._jobs_lock:
                            job.skipped_files += 1
                        return
                    if action == "rename":
                        chosen_name = _pick_non_colliding_name(set(existing.keys()), base_name, is_dir)

                if is_dir:
                    cand_rel = posixpath.join(target_parent_rel, chosen_name) if target_parent_rel else chosen_name
                    mk_res = self._mkdir(base_url, token, cand_rel)
                    # Wajib hormati `created_path` hasil /mkdir (khususnya role 'editor')
                    actual_dir_rel = str(mk_res.get("created_path") or cand_rel).strip("/")
                    dir_cache.pop(target_parent_rel, None)
                    if mk_res.get("renamed"):
                        dir_cache[actual_dir_rel] = {}
                    for child_name in sorted(os.listdir(abs_lp)):
                        _stage_tree(os.path.join(abs_lp, child_name), actual_dir_rel)
                else:
                    sz = os.path.getsize(abs_lp)
                    item_id = f"up_{len(file_jobs)}_{chosen_name}"
                    item_dict: Dict[str, Any] = {
                        "id": item_id,
                        "name": chosen_name,
                        "size": sz,
                        "bytes_done": 0,
                        "bytes_total": sz,
                        "status": "pending",
                    }
                    file_jobs.append((abs_lp, target_parent_rel, chosen_name, sz, item_dict))
                    existing[chosen_name] = {"name": chosen_name, "is_dir": False}
                    with self._jobs_lock:
                        job.total_files += 1
                        job.bytes_total += sz
                        job.items.append(item_dict)

            clean_dest = server_dest_rel.strip("/")
            for src in local_sources:
                _stage_tree(src, clean_dest)

            def _worker(item_job: Tuple[str, str, str, int, Dict[str, Any]]) -> None:
                local_path, srv_dir_rel, target_name, sz, item_dict = item_job
                with self._jobs_lock:
                    job.active_workers += 1
                    job.active_item = f"{srv_dir_rel}/{target_name}".strip("/")
                    item_dict["status"] = "active"
                try:
                    if sz > self.chunk_threshold:
                        self._upload_file_chunked(
                            base_url, token, srv_dir_rel, target_name, local_path, job, item_state=item_dict
                        )
                    else:
                        self._upload_file_direct(
                            base_url, token, srv_dir_rel, target_name, local_path, job, item_state=item_dict
                        )
                except BaseException:
                    with self._jobs_lock:
                        item_dict["status"] = "cancelled" if job.cancel_event.is_set() else "error"
                    raise
                finally:
                    with self._jobs_lock:
                        job.active_workers = max(0, job.active_workers - 1)

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                futs = [pool.submit(_worker, fj) for fj in file_jobs]
                for fut in concurrent.futures.as_completed(futs):
                    try:
                        fut.result()
                    except InterruptedError:
                        pass
                    except Exception as exc:
                        with self._jobs_lock:
                            job.failed_files += 1
                            if not job.error:
                                job.error = str(exc)

            with self._jobs_lock:
                if job.cancel_event.is_set():
                    job.status = "cancelled"
                elif job.failed_files > 0:
                    job.status = "failed"
                else:
                    job.status = "completed"
                job.finished_monotonic = time.monotonic()
                final_status = job.status
            if final_status == "completed":
                self._clear_clipboard_if_unchanged(job.clipboard_copied_at)
        except Exception as exc:
            with self._jobs_lock:
                job.status = "cancelled" if job.cancel_event.is_set() else "failed"
                job.error = str(exc)
                job.finished_monotonic = time.monotonic()

    # ------------------------------------------------------------------
    # Download Engine (streaming 256 KB -> .myserver-part.<uuid8> + commonpath)
    # ------------------------------------------------------------------
    def _stream_download_file(
        self,
        base_url: str,
        token: str,
        srv_rel: str,
        local_target: str,
        job: TransferJobState,
        item_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        job.pause_gate.wait()
        if job.cancel_event.is_set():
            raise InterruptedError("CANCELLED")

        os.makedirs(os.path.dirname(local_target), exist_ok=True)
        part_path = f"{local_target}.myserver-part.{uuid.uuid4().hex[:8]}"
        with self._jobs_lock:
            job.active_part_paths.add(part_path)

        q = urllib.parse.urlencode({"path": srv_rel})
        req = urllib.request.Request(
            f"{base_url}/api/v1/storage/download?{q}",
            method="GET",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp, open(part_path, "wb") as f_out:
                if item_state is not None and int(item_state.get("bytes_total") or 0) <= 0:
                    try:
                        cl = int(resp.headers.get("Content-Length") or 0)
                    except (TypeError, ValueError):
                        cl = 0
                    if cl > 0:
                        with self._jobs_lock:
                            if int(item_state.get("bytes_total") or 0) <= 0:
                                item_state["bytes_total"] = cl
                                item_state["size"] = cl
                                job.bytes_total += cl
                while True:
                    job.pause_gate.wait()
                    if job.cancel_event.is_set():
                        raise InterruptedError("CANCELLED")
                    chunk = resp.read(self.chunk_size)
                    if not chunk:
                        break
                    f_out.write(chunk)
                    with self._jobs_lock:
                        job.bytes_done += len(chunk)
                        if item_state is not None:
                            item_state["bytes_done"] = int(item_state.get("bytes_done") or 0) + len(chunk)
            if job.cancel_event.is_set():
                raise InterruptedError("CANCELLED")
            os.replace(part_path, local_target)
            with self._jobs_lock:
                job.completed_files += 1
                if item_state is not None:
                    done_b = int(item_state.get("bytes_done") or 0)
                    tot_b = int(item_state.get("bytes_total") or 0)
                    if tot_b < done_b:
                        diff = done_b - tot_b
                        item_state["bytes_total"] = done_b
                        item_state["size"] = done_b
                        job.bytes_total += diff
                    item_state["status"] = "done"
        except Exception:
            if os.path.exists(part_path):
                try:
                    os.remove(part_path)
                except OSError:
                    pass
            raise
        finally:
            with self._jobs_lock:
                job.active_part_paths.discard(part_path)

    def _run_download_job(
        self,
        job: TransferJobState,
        server_items: List[Dict[str, Any]],
        local_dest_dir: str,
    ) -> None:
        try:
            _, _, base_url, token = self._resolve_session(job.server_id)
            dest_real = os.path.realpath(os.path.abspath(local_dest_dir))
            os.makedirs(dest_real, exist_ok=True)

            download_jobs: List[Tuple[str, str, int, Dict[str, Any]]] = []

            def _collect_server_tree(
                rel_path: str,
                target_parent_dir: str,
                hint_is_dir: Optional[bool],
                hint_size: int = 0,
            ) -> None:
                if job.cancel_event.is_set():
                    return
                parts = _split_and_validate_rel_path(rel_path)
                if not parts:
                    raise ValueError("INVALID_EMPTY_SERVER_PATH")
                clean_rel = "/".join(parts)
                base_name = parts[-1]

                resolved_is_dir = hint_is_dir
                prefetched_children: Optional[List[Dict[str, Any]]] = None

                # Fallback probe langsung ke /browse-files tanpa me-list parent (mendukung root Shared with Me)
                if resolved_is_dir is None:
                    st, probe_data = self._browse_dir(base_url, token, clean_rel)
                    if st == 200:
                        resolved_is_dir = True
                        prefetched_children = probe_data.get("items") or []
                    elif st == 400:
                        resolved_is_dir = False
                    else:
                        raise RuntimeError(f"HTTP {st} on browse-files({clean_rel}): {probe_data}")

                target_local = _safe_local_join(target_parent_dir, base_name)
                if os.path.exists(target_local):
                    action = self._resolve_conflict_decision(
                        job,
                        item_name=base_name,
                        dest_path=target_local,
                        is_dir=bool(resolved_is_dir),
                    )
                    if action == "skip":
                        with self._jobs_lock:
                            job.skipped_files += 1
                        return
                    if action == "rename":
                        _, target_local = _pick_non_colliding_local_path(
                            target_parent_dir, base_name, bool(resolved_is_dir)
                        )

                if resolved_is_dir:
                    os.makedirs(target_local, exist_ok=True)
                    if prefetched_children is None:
                        st, dir_data = self._browse_dir(base_url, token, clean_rel)
                        if st >= 400:
                            raise RuntimeError(f"HTTP {st} on browse-files({clean_rel}): {dir_data}")
                        prefetched_children = dir_data.get("items") or []
                    for child in prefetched_children:
                        if not isinstance(child, dict):
                            continue
                        child_name = _sanitize_rel_component(str(child.get("name") or ""))
                        child_rel = f"{clean_rel}/{child_name}"
                        _collect_server_tree(
                            child_rel,
                            target_local,
                            bool(child.get("is_dir", False)),
                            int(child.get("size") or 0),
                        )
                else:
                    sz_hint = int(hint_size or 0)
                    item_id = f"dl_{len(download_jobs)}_{base_name}"
                    item_dict: Dict[str, Any] = {
                        "id": item_id,
                        "name": os.path.basename(target_local),
                        "size": sz_hint,
                        "bytes_done": 0,
                        "bytes_total": sz_hint,
                        "status": "pending",
                    }
                    download_jobs.append((clean_rel, target_local, sz_hint, item_dict))
                    with self._jobs_lock:
                        job.total_files += 1
                        job.bytes_total += sz_hint
                        job.items.append(item_dict)

            for itm in server_items:
                _collect_server_tree(
                    str(itm.get("rel_path") or ""),
                    dest_real,
                    itm.get("is_dir"),
                    int(itm.get("size") or 0),
                )

            def _worker(dl_job: Tuple[str, str, int, Dict[str, Any]]) -> None:
                srv_rel, target_local, _, item_dict = dl_job
                with self._jobs_lock:
                    job.active_workers += 1
                    job.active_item = srv_rel
                    item_dict["status"] = "active"
                try:
                    self._stream_download_file(base_url, token, srv_rel, target_local, job, item_state=item_dict)
                except BaseException:
                    with self._jobs_lock:
                        item_dict["status"] = "cancelled" if job.cancel_event.is_set() else "error"
                    raise
                finally:
                    with self._jobs_lock:
                        job.active_workers = max(0, job.active_workers - 1)

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                futs = [pool.submit(_worker, dj) for dj in download_jobs]
                for fut in concurrent.futures.as_completed(futs):
                    try:
                        fut.result()
                    except InterruptedError:
                        pass
                    except Exception as exc:
                        with self._jobs_lock:
                            job.failed_files += 1
                            if not job.error:
                                job.error = str(exc)

            if job.cancel_event.is_set():
                self._cleanup_part_files(job)

            with self._jobs_lock:
                if job.cancel_event.is_set():
                    job.status = "cancelled"
                elif job.failed_files > 0:
                    job.status = "failed"
                else:
                    job.status = "completed"
                job.finished_monotonic = time.monotonic()
                final_status = job.status

            if not job.cancel_event.is_set() and job.completed_files > 0:
                try:
                    self.notify_local_dir_fn(dest_real)
                except Exception:
                    pass
            if final_status == "completed":
                self._clear_clipboard_if_unchanged(job.clipboard_copied_at)
        except Exception as exc:
            self._cleanup_part_files(job)
            with self._jobs_lock:
                job.status = "cancelled" if job.cancel_event.is_set() else "failed"
                job.error = str(exc)
                job.finished_monotonic = time.monotonic()

    # ------------------------------------------------------------------
    # Server-to-Server Copy (/api/v1/storage/copy)
    # ------------------------------------------------------------------
    def _run_server_copy_job(
        self,
        job: TransferJobState,
        src_paths: List[str],
        dest_dir_rel: str,
    ) -> None:
        try:
            _, _, base_url, token = self._resolve_session(job.server_id)
            st_b, b_data = self._browse_dir(base_url, token, dest_dir_rel)
            existing_names: Set[str] = set()
            if st_b == 200 and isinstance(b_data, dict):
                existing_names = {
                    str(it.get("name") or "")
                    for it in (b_data.get("items") or [])
                    if isinstance(it, dict)
                }

            conflict_mode = "rename"
            for sp in src_paths:
                bn = sp.strip("/").split("/")[-1]
                if bn in existing_names:
                    conflict_mode = self._resolve_conflict_decision(
                        job,
                        item_name=bn,
                        dest_path=f"{dest_dir_rel}/{bn}".strip("/"),
                        is_dir=False,
                    )
                    break

            if job.cancel_event.is_set():
                with self._jobs_lock:
                    job.status = "cancelled"
                    job.finished_monotonic = time.monotonic()
                return

            st, resp = self._api_json(
                base_url,
                token,
                "POST",
                "/api/v1/storage/copy",
                {
                    "src_paths": src_paths,
                    "dest_dir": dest_dir_rel,
                    "conflict_mode": conflict_mode,
                },
                timeout=60.0,
            )
            if st >= 400 or not isinstance(resp, dict):
                raise RuntimeError(f"HTTP {st} on copy: {resp}")
            copied = resp.get("copied") or []
            skipped = resp.get("skipped") or []
            with self._jobs_lock:
                job.total_files = len(src_paths)
                job.completed_files = len(copied)
                job.skipped_files = len(skipped)
                job.status = "completed"
                job.finished_monotonic = time.monotonic()
            self._clear_clipboard_if_unchanged(job.clipboard_copied_at)
        except Exception as exc:
            with self._jobs_lock:
                job.status = "cancelled" if job.cancel_event.is_set() else "failed"
                job.error = str(exc)
                job.finished_monotonic = time.monotonic()

    # ------------------------------------------------------------------
    # Hybrid Paste Dispatcher
    # ------------------------------------------------------------------
    def _spawn_job(self, job: TransferJobState, target_fn: Callable[..., None], *args: Any) -> str:
        with self._jobs_lock:
            self._jobs[job.job_id] = job
            self._latest_job_id = job.job_id
            t = threading.Thread(target=target_fn, args=(job, *args), daemon=True)
            self._job_threads[job.job_id] = t
        t.start()
        return job.job_id

    def _try_resolve_smb(self, dest_path: str) -> Tuple[bool, Dict[str, Any]]:
        if not dest_path or self.resolve_smb_target_fn is None:
            return (False, {})
        try:
            ok, info = self.resolve_smb_target_fn(dest_path)
            return (bool(ok), info if isinstance(info, dict) else {})
        except Exception:
            return (False, {})

    def dispatch_paste(
        self,
        dest_path: str = "",
        server_id: str = "",
        dest_rel: str = "",
        force_quick_picker: bool = False,
    ) -> Dict[str, Any]:
        clip = self.get_clipboard()
        mode = clip.get("mode")
        items = clip.get("items") or []
        clip_ts = float(clip.get("copied_at") or 0.0)
        if not mode or not items:
            return {"success": False, "code": "CLIPBOARD_EMPTY"}

        if mode == "local":
            local_paths = [str(it.get("path") or "") for it in items if it.get("path")]
            if dest_rel and not force_quick_picker:
                sid, sname, _, _ = self._resolve_session(server_id or "")
                job = TransferJobState(
                    job_id=f"xfer_{uuid.uuid4().hex[:10]}",
                    direction="upload",
                    server_id=sid,
                    server_name=sname,
                    dest_display=dest_rel,
                    clipboard_copied_at=clip_ts,
                )
                self._spawn_job(job, self._run_upload_job, local_paths, dest_rel.strip("/"))
                return {
                    "success": True,
                    "ui_action": "open_transfer_window",
                    "mode": "progress",
                    "direction": "upload",
                    "job_id": job.job_id,
                }

            if not force_quick_picker and dest_path:
                smb_ok, smb_info = self._try_resolve_smb(dest_path)
                if smb_ok:
                    target_rel = str(smb_info.get("canonical_rel") or "").strip("/")
                    target_sid = str(smb_info.get("server_id") or server_id or "")
                    target_sname = str(smb_info.get("server_name") or target_sid)
                    job = TransferJobState(
                        job_id=f"xfer_{uuid.uuid4().hex[:10]}",
                        direction="upload",
                        server_id=target_sid,
                        server_name=target_sname,
                        dest_display=target_rel,
                        clipboard_copied_at=clip_ts,
                    )
                    self._spawn_job(job, self._run_upload_job, local_paths, target_rel)
                    return {
                        "success": True,
                        "ui_action": "open_transfer_window",
                        "mode": "progress",
                        "direction": "upload",
                        "job_id": job.job_id,
                    }

            # Fallback ke Quick Picker tanpa pernah memanggil os.path.exists pada path SMB
            return {
                "success": True,
                "ui_action": "open_transfer_window",
                "mode": "quick_picker",
                "direction": "upload",
            }

        if mode == "server":
            clip_sid = str(clip.get("server_id") or "")
            clip_sname = str(clip.get("server_name") or clip_sid)
            src_rels = [str(it.get("rel_path") or "") for it in items if it.get("rel_path")]

            if dest_rel and (not server_id or server_id == clip_sid) and not force_quick_picker:
                job = TransferJobState(
                    job_id=f"xfer_{uuid.uuid4().hex[:10]}",
                    direction="server_copy",
                    server_id=clip_sid,
                    server_name=clip_sname,
                    dest_display=dest_rel.strip("/"),
                    clipboard_copied_at=clip_ts,
                )
                self._spawn_job(job, self._run_server_copy_job, src_rels, dest_rel.strip("/"))
                return {
                    "success": True,
                    "ui_action": "open_transfer_window",
                    "mode": "progress",
                    "direction": "server_copy",
                    "job_id": job.job_id,
                }

            if dest_path and not force_quick_picker:
                smb_ok, smb_info = self._try_resolve_smb(dest_path)
                if smb_ok and str(smb_info.get("server_id") or "") == clip_sid:
                    target_rel = str(smb_info.get("canonical_rel") or "").strip("/")
                    job = TransferJobState(
                        job_id=f"xfer_{uuid.uuid4().hex[:10]}",
                        direction="server_copy",
                        server_id=clip_sid,
                        server_name=clip_sname,
                        dest_display=target_rel,
                        clipboard_copied_at=clip_ts,
                    )
                    self._spawn_job(job, self._run_server_copy_job, src_rels, target_rel)
                    return {
                        "success": True,
                        "ui_action": "open_transfer_window",
                        "mode": "progress",
                        "direction": "server_copy",
                        "job_id": job.job_id,
                    }

                if not smb_ok and os.path.isdir(dest_path):
                    job = TransferJobState(
                        job_id=f"xfer_{uuid.uuid4().hex[:10]}",
                        direction="download",
                        server_id=clip_sid,
                        server_name=clip_sname,
                        dest_display=os.path.abspath(dest_path),
                        local_dest_dir=os.path.abspath(dest_path),
                        clipboard_copied_at=clip_ts,
                    )
                    self._spawn_job(job, self._run_download_job, items, dest_path)
                    return {
                        "success": True,
                        "ui_action": "open_transfer_window",
                        "mode": "progress",
                        "direction": "download",
                        "job_id": job.job_id,
                    }

            return {
                "success": True,
                "ui_action": "open_transfer_window",
                "mode": "quick_picker",
                "direction": "download",
            }

        return {"success": False, "code": "UNSUPPORTED_CLIPBOARD_MODE"}
