# -*- coding: utf-8 -*-
"""
Logger Manager Module for MyServer Desktop (Beta)
Menyediakan sistem logging diagnostik terpusat dengan rotasi otomatis (5 MB per berkas).
Mencatat seluruh aktivitas aplikasi, rute koneksi, proses SMB mounting,
serta menangkap unhandled exception ke <Folder_Aplikasi>/logs/myserver.log
atau folder kustom pilihan pengguna.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
from logging.handlers import RotatingFileHandler

_logger_instance = None
_log_file_path = None
_log_dir_path = None
_log_lock = threading.Lock()


def get_base_app_dir():
    """Mengembalikan direktori dasar instalasi aplikasi."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_default_log_dir():
    """Mengembalikan direktori log default (<app_dir>/logs)."""
    return os.path.join(get_base_app_dir(), "logs")


def get_configured_log_dir():
    """Membaca folder log yang dikonfigurasi pengguna dari config.json."""
    base_dir = get_base_app_dir()
    cfg_path = os.path.join(base_dir, "config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                custom_dir = data.get("log_directory", "").strip()
                if custom_dir and os.path.exists(custom_dir):
                    return custom_dir
        except Exception:
            pass
    return get_default_log_dir()


def setup_application_logging(custom_dir=None, force_reconfigure=False):
    """
    Menginisialisasi sistem pencatatan log aplikasi dengan file handler rotasi.
    Mendukung rekonfigurasi dinamis ke folder baru tanpa restart aplikasi.
    """
    global _logger_instance, _log_file_path, _log_dir_path

    with _log_lock:
        target_dir = custom_dir or get_configured_log_dir()
        if _logger_instance is not None and not force_reconfigure and _log_dir_path == target_dir:
            return _logger_instance

        try:
            os.makedirs(target_dir, exist_ok=True)
        except Exception:
            target_dir = os.path.join(os.environ.get("LOCALAPPDATA", get_base_app_dir()), "MyServer", "logs")
            os.makedirs(target_dir, exist_ok=True)

        _log_dir_path = target_dir
        _log_file_path = os.path.join(target_dir, "myserver.log")

        logger = logging.getLogger("MyServer")
        logger.setLevel(logging.DEBUG)

        # Tutup dan bersihkan handler lama jika force_reconfigure
        if force_reconfigure and logger.handlers:
            for old_h in list(logger.handlers):
                try:
                    old_h.flush()
                    old_h.close()
                except Exception:
                    pass
                logger.removeHandler(old_h)

        if not logger.handlers:
            try:
                handler = RotatingFileHandler(
                    _log_file_path,
                    maxBytes=5 * 1024 * 1024,  # 5 MB
                    backupCount=3,
                    encoding="utf-8",
                    delay=False
                )
                formatter = logging.Formatter(
                    fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S"
                )
                handler.setFormatter(formatter)
                handler.setLevel(logging.INFO)
                logger.addHandler(handler)
            except Exception:
                pass

        _logger_instance = logger
        return logger


def set_configured_log_dir(new_dir):
    """
    Mengubah folder penyimpanan file log secara permanen:
    1. Menyimpan ke config.json
    2. Menyalin log aktif saat ini ke folder baru agar riwayat tetap utuh
    3. Mengalihkan handler logging ke folder baru secara langsung.
    """
    clean_dir = os.path.abspath(new_dir.strip()) if new_dir else ""
    if not clean_dir or not os.path.exists(clean_dir):
        return {"success": False, "error": f"Direktori '{clean_dir}' tidak ditemukan"}

    base_dir = get_base_app_dir()
    cfg_path = os.path.join(base_dir, "config.json")
    try:
        cfg = {}
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        cfg["log_directory"] = clean_dir
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        return {"success": False, "error": f"Gagal menyimpan config: {e}"}

    # Salin berkas log lama ke folder baru jika belum ada
    old_log = get_log_file_path()
    new_log = os.path.join(clean_dir, "myserver.log")
    if os.path.exists(old_log) and os.path.abspath(old_log) != os.path.abspath(new_log):
        try:
            if not os.path.exists(new_log):
                shutil.copy2(old_log, new_log)
        except Exception:
            pass

    # Rekonfigurasi handler aktif
    setup_application_logging(custom_dir=clean_dir, force_reconfigure=True)
    log_info(f"[LoggerManager] Direktori log resmi dialihkan ke: {clean_dir}")
    return {"success": True, "logDirectory": clean_dir}


def reset_log_dir_to_default():
    """Mengembalikan folder penyimpanan log ke bawaan (<app_dir>/logs)."""
    base_dir = get_base_app_dir()
    cfg_path = os.path.join(base_dir, "config.json")
    try:
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg.pop("log_directory", None)
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        return {"success": False, "error": f"Gagal menyimpan config: {e}"}

    default_dir = get_default_log_dir()
    setup_application_logging(custom_dir=default_dir, force_reconfigure=True)
    log_info(f"[LoggerManager] Direktori log dikembalikan ke default: {default_dir}")
    return {"success": True, "logDirectory": default_dir}


def get_log_status():
    """Mengembalikan status konfigurasi direktori log."""
    cur_dir = os.path.abspath(get_log_dir_path())
    def_dir = os.path.abspath(get_default_log_dir())
    return {
        "logDirectory": cur_dir,
        "defaultDirectory": def_dir,
        "isCustom": cur_dir.lower() != def_dir.lower()
    }


def get_logger(module_name="MyServer"):
    """Mengembalikan logger spesifik modul."""
    if _logger_instance is None:
        setup_application_logging()
    return logging.getLogger(f"MyServer.{module_name}")


def log_info(message, module="App"):
    """Mencatat catatan informasi standar dan segera mem-flush buffer berkas."""
    try:
        lg = get_logger(module)
        lg.info(message)
        for h in lg.handlers or (_logger_instance.handlers if _logger_instance else []):
            try:
                h.flush()
            except Exception:
                pass
    except Exception:
        pass


def log_error(message, module="App"):
    """Mencatat galat kritis atau kegagalan sistem."""
    try:
        lg = get_logger(module)
        lg.error(message)
        for h in lg.handlers or (_logger_instance.handlers if _logger_instance else []):
            try:
                h.flush()
            except Exception:
                pass
    except Exception:
        pass


def log_warning(message, module="App"):
    """Mencatat peringatan kondisi tak terduga yang dapat ditoleransi."""
    try:
        lg = get_logger(module)
        lg.warning(message)
        for h in lg.handlers or (_logger_instance.handlers if _logger_instance else []):
            try:
                h.flush()
            except Exception:
                pass
    except Exception:
        pass


def log_debug(message, module="App"):
    """Mencatat informasi diagnostik mendalam."""
    try:
        lg = get_logger(module)
        lg.debug(message)
    except Exception:
        pass


def install_global_excepthook():
    """Menangkap unhandled exception global untuk dicatat ke myserver.log."""
    def _unhandled_hook(exc_type, exc_value, exc_traceback):
        import traceback
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        log_error(f"UNHANDLED FATAL EXCEPTION:\n{tb_str}", module="CrashHandler")
        try:
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
        except Exception:
            pass
    sys.excepthook = _unhandled_hook


def get_log_file_path():
    """Mengembalikan path lengkap berkas log."""
    if _log_file_path is None:
        setup_application_logging()
    return _log_file_path


def get_log_dir_path():
    """Mengembalikan path folder direktori log."""
    if _log_dir_path is None:
        setup_application_logging()
    return _log_dir_path


def open_log_in_editor():
    """Membuka berkas log aplikasi langsung menggunakan Notepad dengan flush handler sebelumnya."""
    path = get_log_file_path()
    if _logger_instance:
        for h in _logger_instance.handlers:
            try:
                h.flush()
            except Exception:
                pass

    if not os.path.exists(path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("[MyServer Diagnostic Log Initialized]\n")
        except Exception:
            pass

    try:
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["notepad.exe", path])
        return True
    except Exception:
        return False


def open_log_folder_in_explorer():
    """Membuka folder tempat berkas log tersimpan di Windows File Explorer."""
    dir_path = get_log_dir_path()
    try:
        if sys.platform == "win32":
            os.startfile(dir_path)
        else:
            subprocess.Popen(["explorer.exe", dir_path])
        return True
    except Exception:
        return False


def get_recent_log_summary(max_lines=50):
    """Mengambil n baris log terakhir untuk kemudahan pelaporan galat."""
    path = get_log_file_path()
    if not os.path.exists(path):
        return "Belum ada catatan log yang dibuat."

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            recent = lines[-max_lines:] if len(lines) > max_lines else lines
            return "".join(recent)
    except Exception as e:
        return f"Gagal membaca berkas log: {e}"
