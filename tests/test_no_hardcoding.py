import os
import tarfile
import unittest
import zipfile

BETA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FORBIDDEN_STRINGS = (
    "algitha.my.id",
    "stimi.",
    "Disk_Gibran",
    "Disk_Aldhy",
    "D:\\Projek",
    "D:\\Softwares",
    "D:\\Logs",
    "C:\\Users\\gibran",
    "C:\\Users\\gibra",
    "Algitha-Server",
    "myserver_algitha_secret",
    "192.168.1.11",
    "192.168.1.6",
    "192.168.1.10",
    "192.168.1.50",
    "192.168.1.100",
    "172.24.0.",
    "10.147.20.",
    "\"algitha\"",
)

SKIP_DIR_NAMES = {
    "node_modules",
    ".git",
    "target",
    "__pycache__",
    "dist",
    "bin",
    "logs",
    ".planning",
    "tests",
    "__tests__",
    ".pytest_cache",
    "ui",
}

SKIP_REL_FILES = {
    "CHANGELOG.md",
    "CHANGELOG.txt",
    "changelog_manager.py",
}

TEXT_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".rs",
    ".toml",
    ".json",
    ".iss",
    ".spec",
    ".yml",
    ".yaml",
    ".ps1",
    ".bat",
    ".sh",
    ".html",
}


class TestNoHardcoding(unittest.TestCase):
    def test_production_sources_contain_no_personal_or_env_hardcodings(self):
        hits = []
        for root, dirs, files in os.walk(BETA_DIR):
            dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES]
            rel_root = os.path.relpath(root, BETA_DIR).replace("\\", "/")
            if rel_root.startswith("resources/deps"):
                continue

            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if ext not in TEXT_EXTENSIONS:
                    continue
                full_path = os.path.join(root, fn)
                rel_path = os.path.relpath(full_path, BETA_DIR).replace("\\", "/")
                if rel_path in SKIP_REL_FILES:
                    continue
                # Intentional brand string in HeaderLogo comment and settings mock is checked by domain/secret rules,
                # skip empty test quote '"algitha"' only outside auth rules — still disallow every personal IP/domain/path.
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                for token in FORBIDDEN_STRINGS:
                    if token == "\"algitha\"" and ext in (".ts", ".tsx"):
                        continue
                    if token in content:
                        hits.append(f"{rel_path}: contains {token!r}")

        self.assertEqual(hits, [], "Found hardcoded personal/env literals:\n" + "\n".join(hits))

    def test_bundled_backend_archives_contain_no_hardcodings(self):
        res_dir = os.path.join(BETA_DIR, "resources")
        zip_path = os.path.join(res_dir, "MyServer-Backend-ZimaOS.zip")
        tar_path = os.path.join(res_dir, "MyServer-Backend-ZimaOS.tar.gz")
        self.assertTrue(os.path.isfile(zip_path))
        self.assertTrue(os.path.isfile(tar_path))

        hits = []
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                if os.path.splitext(member)[1].lower() not in TEXT_EXTENSIONS:
                    continue
                text = zf.read(member).decode("utf-8", errors="ignore")
                for token in FORBIDDEN_STRINGS:
                    if token in text:
                        hits.append(f"zip:{member}: contains {token!r}")

        with tarfile.open(tar_path, "r:gz") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                if os.path.splitext(member.name)[1].lower() not in TEXT_EXTENSIONS:
                    continue
                f = tf.extractfile(member)
                if f is None:
                    continue
                text = f.read().decode("utf-8", errors="ignore")
                for token in FORBIDDEN_STRINGS:
                    if token in text:
                        hits.append(f"tar:{member.name}: contains {token!r}")

        self.assertEqual(hits, [], "Found hardcoded literals inside backend archives:\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
