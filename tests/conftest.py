"""Shared fixtures. Nothing here touches the network or a live model — see
pyproject.toml's `live` marker for tests that do (skipped by default)."""
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _no_real_desktop_backend():
    """Assistant.ask()/confirmation calls platforms.current().notify(...) on
    every turn now (the notification system) -- without this, the FIRST test
    in the whole suite to hit either path would lazily create and cache a
    REAL backend, firing actual OS notifications (notify-send, etc.) for the
    rest of the run on a real Linux/macOS/Windows machine. Defaults every
    test to an inert backend; a test that wants real backend behavior (e.g.
    app_dirs) already calls platforms.set_backend(...) itself, which simply
    overrides this for its own duration."""
    from raven import platforms
    platforms.set_backend(platforms.Backend())
    yield
    platforms.set_backend(None)


@pytest.fixture(autouse=True)
def _no_real_sudo_password_provider():
    """tools._run_sudo consults a module-level provider (raven/cli.py's own
    interactive registration) -- without resetting it, a test that sets one
    (to exercise the password-prompt path) would leak it into every test that
    runs afterward in the same process."""
    from raven import tools
    tools.set_sudo_password_provider(None)
    yield
    tools.set_sudo_password_provider(None)


@pytest.fixture
def store(tmp_path):
    """A Store backed by a throwaway SQLite file, never the real ~/.raven one."""
    from raven.store import Store
    return Store(tmp_path / "history.db")


@pytest.fixture
def settings_path(tmp_path, monkeypatch):
    """Point config.SETTINGS_PATH at a throwaway file for the duration of a test."""
    from raven import config
    path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_PATH", path)
    return path


@pytest.fixture
def app_dirs(tmp_path, monkeypatch):
    """Point the Linux backend's APP_DIRS at one throwaway directory of
    fabricated .desktop files, so app-matching tests don't depend on what's
    actually installed on whatever machine runs the suite. Also forces the
    Linux backend, so these tests mean the same thing on any OS."""
    from raven import platforms
    from raven.platforms import linux
    apps_dir = tmp_path / "applications"
    apps_dir.mkdir()

    def write(app_id: str, name: str, exec_line: str, no_display: bool = False):
        content = f"[Desktop Entry]\nName={name}\nExec={exec_line}\n"
        if no_display:
            content += "NoDisplay=true\n"
        (apps_dir / f"{app_id}.desktop").write_text(content)

    write("org.gnome.TextEditor", "Text Editor", "gnome-text-editor %U")
    write("codeblocks", "Code::Blocks Ide", "codeblocks %F")
    write("code", "Visual Studio Code", "/usr/share/code/code %F")
    write("org.mozilla.firefox", "Firefox",
          "/usr/bin/flatpak run --branch=stable --command=firefox --file-forwarding "
          "org.mozilla.firefox @@u %u @@")
    write("r-base", "R", "R")  # the one-letter-name regression case
    write("hidden-app", "Hidden Thing", "hidden-thing", no_display=True)

    monkeypatch.setattr(linux, "APP_DIRS", [apps_dir])
    platforms.set_backend(linux.LinuxBackend())
    yield apps_dir
    platforms.set_backend(None)


@pytest.fixture(scope="session")
def browser_page():
    """The real (headless) browser, loaded once with the local test fixture
    page and reset before every test that uses it. No network — file:// only."""
    from raven import browser
    url = (FIXTURES / "test_form.html").resolve().as_uri()
    browser.navigate(url)
    yield browser
    browser.close()


@pytest.fixture
def fresh_page(browser_page):
    """Reload the fixture page so each test starts from the same clean state
    (the form untouched, the hidden div still hidden)."""
    url = (FIXTURES / "test_form.html").resolve().as_uri()
    browser_page.navigate(url)
    return browser_page
