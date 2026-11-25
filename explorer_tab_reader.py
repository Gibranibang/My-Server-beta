"""
explorer_tab_reader.py
Pembaca tab aktif Windows 10/11 File Explorer via STA COM ber-timeout 1500 ms.

Aturan ketat (T-13-10 / Win11 22H2+):
- DILARANG menggunakan IsWindowVisible() untuk menentukan tab aktif (selalu True di Win11).
- Wajib mencocokkan IOleWindow::GetWindow() terhadap top_tab_hwnd (Z-order ShellTabWindowClass)
  dan short-circuit `continue` SEBELUM mengakses `.Document` atau `.SelectedItems()`.
- Wajib membuat thread `ApartmentState.STA` sekali pakai per request dengan batas keras
  `_MAX_HUNG_STA_THREADS = 3` sebelum mengembalikan `error="COM_BUSY"`.
- Menggunakan `pythonnet` (`clr`) dengan fallback PowerShell STA tersembunyi (`0x08000000`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from typing import Any, Callable, Dict, List, Optional

_IN_FLIGHT_LOCK = threading.Lock()
_in_flight_com_threads = 0
_MAX_HUNG_STA_THREADS = 3

CREATE_NO_WINDOW = 0x08000000

_CSHARP_COM_HELPER = r"""
using System;
using System.Runtime.InteropServices;

public static class ExplorerTabComHelper
{
    private static readonly Guid SID_STopLevelBrowser = new Guid("4C96BE40-915C-11CF-99D3-00AA004AE837");
    private static readonly Guid IID_IShellBrowser = new Guid("000214E2-0000-0000-C000-000000000046");

    [ComImport, Guid("6D5140C1-7436-11CE-8034-00AA006009FA"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IComServiceProvider
    {
        [PreserveSig]
        int QueryService(ref Guid guidService, ref Guid riid, [MarshalAs(UnmanagedType.IUnknown)] out object ppvObject);
    }

    [ComImport, Guid("00000114-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IOleWindow
    {
        [PreserveSig]
        int GetWindow(out IntPtr phwnd);
        [PreserveSig]
        int ContextSensitiveHelp(int fEnterMode);
    }

    public static long GetShellBrowserTabHwnd(object comShellWindow)
    {
        if (comShellWindow == null) return 0;
        try
        {
            IComServiceProvider sp = comShellWindow as IComServiceProvider;
            if (sp == null) return 0;
            Guid sid = SID_STopLevelBrowser;
            Guid iid = IID_IShellBrowser;
            object browserObj = null;
            int hr = sp.QueryService(ref sid, ref iid, out browserObj);
            if (hr != 0 || browserObj == null) return 0;
            try
            {
                IOleWindow oleWin = browserObj as IOleWindow;
                if (oleWin == null) return 0;
                IntPtr tabHwnd = IntPtr.Zero;
                int hrWin = oleWin.GetWindow(out tabHwnd);
                if (hrWin != 0) return 0;
                return tabHwnd.ToInt64();
            }
            finally
            {
                if (browserObj != null && Marshal.IsComObject(browserObj))
                {
                    Marshal.ReleaseComObject(browserObj);
                }
            }
        }
        catch
        {
            return 0;
        }
    }
}
"""

_COMPILED_HELPER_LOCK = threading.Lock()
_compiled_helper_type = None


def _get_compiled_com_helper():
    """Kompilasi helper C# IServiceProvider/IOleWindow sekali per proses saat pythonnet aktif."""
    global _compiled_helper_type
    with _COMPILED_HELPER_LOCK:
        if _compiled_helper_type is not None:
            return _compiled_helper_type
        import Microsoft.CSharp  # type: ignore
        import System.CodeDom.Compiler  # type: ignore

        provider = Microsoft.CSharp.CSharpCodeProvider()
        params = System.CodeDom.Compiler.CompilerParameters()
        params.GenerateInMemory = True
        params.GenerateExecutable = False
        params.ReferencedAssemblies.Add("System.dll")
        results = provider.CompileAssemblyFromSource(params, _CSHARP_COM_HELPER)
        if results.Errors.HasErrors:
            msgs = "; ".join(str(err) for err in results.Errors)
            raise RuntimeError(f"CSharp COM helper compile error: {msgs}")
        _compiled_helper_type = results.CompiledAssembly.GetType("ExplorerTabComHelper")
        return _compiled_helper_type


def _extract_active_tab_from_shell_windows(
    windows: Any,
    fg_hwnd: int,
    top_tab_hwnd: int,
    get_tab_hwnd_fn: Callable[[Any], int],
) -> Dict[str, Any]:
    """
    Iterasi jendela COM Shell.Application dengan short-circuit sebelum membaca `.Document`.
    Dipisahkan agar dapat diuji unit secara deterministik lintas OS.
    """
    fg_int = int(fg_hwnd or 0)
    top_int = int(top_tab_hwnd or 0)

    for win in windows:
        try:
            full_name = str(getattr(win, "FullName", "") or "")
            if not full_name.lower().endswith("explorer.exe"):
                continue
            win_hwnd = int(getattr(win, "HWND", 0) or 0)
            if fg_int != 0 and win_hwnd != fg_int:
                continue

            tab_hwnd = int(get_tab_hwnd_fn(win) or 0)
            # Short-circuit wajib sebelum menyentuh .Document/.SelectedItems() pada tab non-aktif
            if top_int != 0 and tab_hwnd != top_int:
                continue

            doc = getattr(win, "Document", None)
            if doc is None:
                continue

            folder_path = ""
            try:
                folder_obj = getattr(doc, "Folder", None)
                self_obj = getattr(folder_obj, "Self", None) if folder_obj is not None else None
                folder_path = str(getattr(self_obj, "Path", "") or "") if self_obj is not None else ""
            except Exception:
                folder_path = ""

            selected_items: List[str] = []
            try:
                sel_fn = getattr(doc, "SelectedItems", None)
                sel_coll = sel_fn() if callable(sel_fn) else sel_fn
                if sel_coll is not None:
                    for item in sel_coll:
                        p = str(getattr(item, "Path", "") or "")
                        if p:
                            selected_items.append(p)
            except Exception:
                selected_items = []

            return {
                "ok": True,
                "timed_out": False,
                "folder_path": folder_path,
                "selected_items": selected_items,
                "tab_hwnd": tab_hwnd,
                "error": "",
            }
        except Exception:
            continue

    return {
        "ok": False,
        "timed_out": False,
        "folder_path": "",
        "selected_items": [],
        "tab_hwnd": 0,
        "error": "TAB_NOT_FOUND",
    }


def _run_pythonnet_sta_worker(
    fg_hwnd: int,
    top_tab_hwnd: int,
    result_box: Dict[str, Any],
    done_event: threading.Event,
    on_finish: Callable[[], None],
) -> None:
    """Jalankan pembacaan COM di thread .NET ApartmentState.STA sekali pakai."""
    import clr  # type: ignore  # noqa: F401
    import System  # type: ignore
    import System.Threading  # type: ignore

    def _sta_entry():
        try:
            helper_cls = _get_compiled_com_helper()
            shell_type = System.Type.GetTypeFromProgID("Shell.Application")
            shell_app = System.Activator.CreateInstance(shell_type)
            windows = shell_app.Windows()
            res = _extract_active_tab_from_shell_windows(
                windows,
                fg_hwnd=fg_hwnd,
                top_tab_hwnd=top_tab_hwnd,
                get_tab_hwnd_fn=lambda w: int(helper_cls.GetShellBrowserTabHwnd(w)),
            )
            result_box.update(res)
        except Exception as exc:
            result_box.update({
                "ok": False,
                "timed_out": False,
                "folder_path": "",
                "selected_items": [],
                "tab_hwnd": 0,
                "error": f"COM_ERROR:{exc}",
            })
        finally:
            on_finish()
            done_event.set()

    sta_thread = System.Threading.Thread(System.Threading.ThreadStart(_sta_entry))
    sta_thread.SetApartmentState(System.Threading.ApartmentState.STA)
    sta_thread.IsBackground = True
    sta_thread.Start()


_PS_LOCK = threading.Lock()
_ps_persistent_proc = None
_ps_cold_started = False


def _ensure_persistent_ps_proc():
    """Start or return a persistent hidden PowerShell -STA process with precompiled COM helper."""
    global _ps_persistent_proc, _ps_cold_started
    if _ps_persistent_proc is not None and _ps_persistent_proc.poll() is None:
        return _ps_persistent_proc
    ps_loop = f"""
$ErrorActionPreference = 'SilentlyContinue'
$cs = @'
{_CSHARP_COM_HELPER}
'@
if (-not ('ExplorerTabComHelper' -as [type])) {{
    Add-Type -TypeDefinition $cs -Language CSharp | Out-Null
}}
$shell = New-Object -ComObject Shell.Application
[Console]::Out.WriteLine("READY")
[Console]::Out.Flush()
while ($null -ne ($line = [Console]::In.ReadLine())) {{
    $parts = $line.Split(',')
    $fInt = [long]$parts[0]
    $tInt = [long]$parts[1]
    $wins = $shell.Windows()
    $out = @{{ ok = $false; timed_out = $false; folder_path = ""; selected_items = @(); tab_hwnd = 0; error = "TAB_NOT_FOUND" }}
    foreach ($w in $wins) {{
        try {{
            if ([string]$w.FullName -notlike "*explorer.exe") {{ continue }}
            if ($fInt -ne 0 -and [long]$w.HWND -ne $fInt) {{ continue }}
            $th = [ExplorerTabComHelper]::GetShellBrowserTabHwnd($w)
            if ($tInt -ne 0 -and $th -ne $tInt) {{ continue }}
            $doc = $w.Document
            if ($null -eq $doc) {{ continue }}
            $fp = ""
            try {{ $fp = [string]$doc.Folder.Self.Path }} catch {{}}
            $sel = @()
            try {{
                $items = $doc.SelectedItems()
                if ($null -ne $items) {{
                    foreach ($it in $items) {{
                        $p = [string]$it.Path
                        if ($p) {{ $sel += $p }}
                    }}
                }}
            }} catch {{}}
            $out = @{{ ok = $true; timed_out = $false; folder_path = $fp; selected_items = $sel; tab_hwnd = $th; error = "" }}
            break
        }} catch {{}}
    }}
    [Console]::Out.WriteLine(($out | ConvertTo-Json -Compress -Depth 4))
    [Console]::Out.Flush()
}}
"""
    _ps_persistent_proc = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-STA", "-Command", ps_loop],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=CREATE_NO_WINDOW,
    )
    ready_line = _ps_persistent_proc.stdout.readline().strip() if _ps_persistent_proc.stdout else ""
    if ready_line != "READY":
        try:
            _ps_persistent_proc.kill()
        except Exception:
            pass
        _ps_persistent_proc = None
        raise RuntimeError(f"POWERSHELL_DAEMON_NOT_READY:{ready_line}")
    _ps_cold_started = True
    return _ps_persistent_proc


def _run_powershell_sta_worker(
    fg_hwnd: int,
    top_tab_hwnd: int,
    timeout_ms: int,
    result_box: Dict[str, Any],
    done_event: threading.Event,
    on_finish: Callable[[], None],
) -> None:
    """Fallback PowerShell STA tersembunyi (CREATE_NO_WINDOW=0x08000000) bila pythonnet tidak tersedia."""
    def _ps_runner():
        global _ps_persistent_proc
        try:
            with _PS_LOCK:
                proc = _ensure_persistent_ps_proc()
                assert proc.stdin is not None and proc.stdout is not None
                proc.stdin.write(f"{int(fg_hwnd or 0)},{int(top_tab_hwnd or 0)}\n")
                proc.stdin.flush()
                raw = proc.stdout.readline().strip()
            if raw:
                parsed = json.loads(raw)
                sel = parsed.get("selected_items")
                if isinstance(sel, str):
                    sel = [sel] if sel else []
                elif not isinstance(sel, list):
                    sel = []
                result_box.update({
                    "ok": bool(parsed.get("ok", False)),
                    "timed_out": False,
                    "folder_path": str(parsed.get("folder_path") or ""),
                    "selected_items": [str(x) for x in sel if x],
                    "tab_hwnd": int(parsed.get("tab_hwnd") or 0),
                    "error": str(parsed.get("error") or ""),
                })
            else:
                result_box.update({
                    "ok": False,
                    "timed_out": False,
                    "folder_path": "",
                    "selected_items": [],
                    "tab_hwnd": 0,
                    "error": "POWERSHELL_EMPTY_OUTPUT",
                })
        except Exception as exc:
            with _PS_LOCK:
                if _ps_persistent_proc is not None:
                    try:
                        _ps_persistent_proc.kill()
                    except Exception:
                        pass
                    _ps_persistent_proc = None
            result_box.update({
                "ok": False,
                "timed_out": False,
                "folder_path": "",
                "selected_items": [],
                "tab_hwnd": 0,
                "error": f"POWERSHELL_ERROR:{exc}",
            })
        finally:
            on_finish()
            done_event.set()

    t = threading.Thread(target=_ps_runner, daemon=True)
    t.start()


def warmup() -> bool:
    """Pra-inisialisasi PowerShell STA persisten di background agar hotkey pertama < 20 ms."""
    if sys.platform != "win32":
        return False
    try:
        with _PS_LOCK:
            _ensure_persistent_ps_proc()
        return True
    except Exception:
        return False


def _spawn_sta_com_worker(
    fg_hwnd: int,
    top_tab_hwnd: int,
    timeout_ms: int,
    result_box: Dict[str, Any],
    done_event: threading.Event,
    on_finish: Callable[[], None],
) -> None:
    """Jalankan pembacaan COM Explorer melalui PowerShell -STA persisten (proven Spike 001/002)."""
    _run_powershell_sta_worker(fg_hwnd, top_tab_hwnd, timeout_ms, result_box, done_event, on_finish)


def read_active_explorer_tab(fg_hwnd: int, top_tab_hwnd: int = 0, timeout_ms: int = 1500) -> Dict[str, Any]:
    """
    Membaca folder aktif dan item terpilih pada tab Explorer aktif secara aman.
    Mengembalikan dict standar dengan batas maksimum 3 thread COM menggantung (`COM_BUSY`).
    """
    if sys.platform != "win32":
        return {
            "ok": False,
            "timed_out": False,
            "folder_path": "",
            "selected_items": [],
            "tab_hwnd": 0,
            "error": "NON_WINDOWS",
        }

    global _in_flight_com_threads
    with _IN_FLIGHT_LOCK:
        if _in_flight_com_threads >= _MAX_HUNG_STA_THREADS:
            return {
                "ok": False,
                "timed_out": False,
                "folder_path": "",
                "selected_items": [],
                "tab_hwnd": 0,
                "error": "COM_BUSY",
            }
        _in_flight_com_threads += 1

    done_event = threading.Event()
    result_box: Dict[str, Any] = {
        "ok": False,
        "timed_out": False,
        "folder_path": "",
        "selected_items": [],
        "tab_hwnd": 0,
        "error": "",
    }
    released = threading.Event()

    def _on_finish() -> None:
        global _in_flight_com_threads
        if not released.is_set():
            released.set()
            with _IN_FLIGHT_LOCK:
                _in_flight_com_threads = max(0, _in_flight_com_threads - 1)

    try:
        _spawn_sta_com_worker(
            fg_hwnd=int(fg_hwnd or 0),
            top_tab_hwnd=int(top_tab_hwnd or 0),
            timeout_ms=int(timeout_ms or 1500),
            result_box=result_box,
            done_event=done_event,
            on_finish=_on_finish,
        )
    except Exception as exc:
        _on_finish()
        return {
            "ok": False,
            "timed_out": False,
            "folder_path": "",
            "selected_items": [],
            "tab_hwnd": 0,
            "error": f"WORKER_SPAWN_FAILED:{exc}",
        }

    wait_sec = max(0.01, float(timeout_ms) / 1000.0)
    if timeout_ms >= 500 and not _ps_cold_started:
        wait_sec = max(wait_sec, 6.0)
    if not done_event.wait(wait_sec):
        with _PS_LOCK:
            global _ps_persistent_proc
            if _ps_persistent_proc is not None:
                try:
                    _ps_persistent_proc.kill()
                except Exception:
                    pass
                _ps_persistent_proc = None
        return {
            "ok": False,
            "timed_out": True,
            "folder_path": "",
            "selected_items": [],
            "tab_hwnd": 0,
            "error": "TIMEOUT",
        }

    return dict(result_box)
