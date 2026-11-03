import unittest
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parents[2] / "src" / "ps"
WEB_DIR = RUNTIME_DIR / "ui" / "web"


class UINavigationTests(unittest.TestCase):
    def test_pages_link_to_each_other(self):
        auth = (WEB_DIR / "auth.html").read_text(encoding="utf-8")
        register = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn('class="recognition-button secondary" href="index.html"', auth)
        self.assertIn('href="/auth.html"', register)
        self.assertIn('href="/users.html"', register)
        users = (WEB_DIR / "users.html").read_text(encoding="utf-8")
        self.assertIn('href="/index.html"', users)
        self.assertIn('href="/auth.html"', users)

    def test_web_buttons_call_control_backend(self):
        auth = (WEB_DIR / "auth.html").read_text(encoding="utf-8")
        auth_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
        register_js = (WEB_DIR / "register.js").read_text(encoding="utf-8")
        self.assertIn('fetch("/api/recognition/start"', auth_js)
        self.assertNotIn('id="result-chip-text"', auth)
        self.assertIn('id="voiceprint-banner"', auth)
        self.assertIn('fetch("/api/enrollment/start"', register_js)
        self.assertIn("renderCommand(phase, command, state.headline)", auth_js)
        self.assertNotIn('id="command-status"', auth)
        self.assertIn("声音采集完毕", (RUNTIME_DIR / "board_runtime.py").read_text(encoding="utf-8"))
        users_js = (WEB_DIR / "users.js").read_text(encoding="utf-8")
        self.assertIn('fetch("/api/users"', users_js)
        self.assertIn('fetch("/api/users/delete"', users_js)
        self.assertNotIn("localStorage", users_js)


if __name__ == "__main__":
    unittest.main()
