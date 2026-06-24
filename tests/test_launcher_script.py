import stat
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "script.sh"


def read_script():
    if not SCRIPT.exists():
        raise AssertionError("script.sh should exist at the project root")
    return SCRIPT.read_text()


class LauncherScriptTests(unittest.TestCase):
    def test_script_exists_is_executable_and_has_valid_bash_syntax(self):
        self.assertTrue(SCRIPT.exists(), "script.sh should exist at the project root")
        mode = SCRIPT.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR, "script.sh should be executable by the owner")

        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_script_uses_project_ports_and_expected_commands(self):
        text = read_script()

        self.assertIn('BACKEND_PORT="${BACKEND_PORT:-8765}"', text)
        self.assertIn('FRONTEND_PORT="${FRONTEND_PORT:-8766}"', text)
        self.assertIn('VITE_API_BASE_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"', text)
        self.assertIn("python3 app/backend/server.py", text)
        self.assertIn("npm run dev -- --port", text)
        self.assertIn("--strictPort", text)

        for default_port in ("3000", "5000", "8000", "5173"):
            self.assertNotIn(default_port, text)

    def test_script_clears_ports_and_cleans_up_started_processes(self):
        text = read_script()

        self.assertIn("kill_port", text)
        self.assertIn("lsof", text)
        self.assertIn("kill", text)
        self.assertIn("trap cleanup INT TERM EXIT", text)
        self.assertIn("BACKEND_PID=", text)
        self.assertIn("FRONTEND_PID=", text)


if __name__ == "__main__":
    unittest.main()
