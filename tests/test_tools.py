"""raven/tools.py — file/shell primitives, app matching, and the tool registry.

App-matching tests use the `app_dirs` fixture (a fabricated .desktop
directory), never the real machine's installed apps — otherwise this suite
would only pass on whichever machine wrote it.
"""
import subprocess
from unittest.mock import patch

import pytest

from raven import tools
from raven.platforms import linux


# ---------------------------------------------------------------------------
# Tool registry: every function has a spec and vice versa, every spec has a
# working callable — the class of bug that would silently break one tool.
# ---------------------------------------------------------------------------

def test_every_tool_function_has_a_spec():
    spec_names = {t["function"]["name"] for t in tools.TOOL_SPECS}
    assert set(tools.TOOL_FUNCTIONS) == spec_names


def test_tool_specs_are_valid_shapes():
    for spec in tools.TOOL_SPECS:
        fn = spec["function"]
        assert fn["name"] and fn["description"]
        assert fn["parameters"]["type"] == "object"


# ---------------------------------------------------------------------------
# App-name matching (Step 3.19's word-boundary fix + the "R" false-positive
# regression it introduced, both re-verified here)
# ---------------------------------------------------------------------------

def test_exact_and_generic_phrasing_both_resolve(app_dirs):
    assert tools._match_app("text editor") == ("text editor", "org.gnome.TextEditor")
    assert tools._match_app("the text editor app") == ("text editor", "org.gnome.TextEditor")
    assert tools._match_app("editor") == ("text editor", "org.gnome.TextEditor")


def test_trailing_punctuation_does_not_break_matching(app_dirs):
    assert tools._match_app("text editor.") == ("text editor", "org.gnome.TextEditor")


def test_one_letter_app_name_does_not_false_positive(app_dirs):
    """Regression: a naive substring match makes 'R' match almost any query
    (the letter appears inside 'editor'). Word-boundary matching must not."""
    result = tools._match_app("text editor")
    assert result == ("text editor", "org.gnome.TextEditor")  # not ambiguous with "R"


def test_ambiguous_name_lists_candidates_not_a_guess(app_dirs):
    result = tools._match_app("code")
    assert isinstance(result, str)
    assert "Code::Blocks Ide" in result and "Visual Studio Code" in result


def test_unknown_name_offers_closest_matches(app_dirs):
    result = tools._match_app("text editr")  # typo, close to "text editor"
    assert isinstance(result, str)
    assert "text editor" in result.lower()


def test_completely_unknown_name_has_no_crash(app_dirs):
    result = tools._match_app("zzz_nonexistent_zzz")
    assert isinstance(result, str) and "No installed app matches" in result


def test_hidden_app_is_not_matched(app_dirs):
    result = tools._match_app("hidden thing")
    assert isinstance(result, str)  # NoDisplay=true entries are excluded


def test_list_apps_excludes_hidden(app_dirs):
    listing = tools.list_apps()
    assert "Text Editor" in listing
    assert "Hidden Thing" not in listing


# ---------------------------------------------------------------------------
# _binary_name: the Flatpak fix (Step 3.21) — this is a correctness/safety
# bug, not cosmetic: close_app's pkill target came from this.
# ---------------------------------------------------------------------------

def test_binary_name_flatpak_extracts_the_real_command_not_flatpak_itself(app_dirs):
    """Before this fix, EVERY flatpak app resolved to the literal string
    'flatpak', so close_app('firefox') would have run `pkill -f flatpak` —
    matching and killing every running flatpak app, not just Firefox."""
    assert linux._binary_name("org.mozilla.firefox") == "firefox"


def test_binary_name_non_flatpak_app(app_dirs):
    assert linux._binary_name("org.gnome.TextEditor") == "gnome-text-editor"


def test_binary_name_unknown_app_id(app_dirs):
    assert linux._binary_name("no-such-app") is None


# ---------------------------------------------------------------------------
# LinuxBackend.notify: the notification system (confirm/finished-task alerts)
# ---------------------------------------------------------------------------

def test_linux_notify_calls_notify_send(monkeypatch):
    calls = []
    monkeypatch.setattr(linux.shutil, "which", lambda name: "/usr/bin/notify-send")
    monkeypatch.setattr(linux.subprocess, "run", lambda cmd, **k: calls.append(cmd))
    linux.LinuxBackend().notify("R.A.V.E.N", "hello")
    assert calls == [["notify-send", "--app-name=R.A.V.E.N", "R.A.V.E.N", "hello"]]


def test_linux_notify_is_a_silent_no_op_without_notify_send(monkeypatch):
    monkeypatch.setattr(linux.shutil, "which", lambda name: None)

    def boom(*a, **k):
        raise AssertionError("should never call subprocess.run without notify-send")

    monkeypatch.setattr(linux.subprocess, "run", boom)
    linux.LinuxBackend().notify("title", "body")  # must not raise


def test_linux_notify_swallows_a_subprocess_failure(monkeypatch):
    monkeypatch.setattr(linux.shutil, "which", lambda name: "/usr/bin/notify-send")

    def boom(*a, **k):
        raise OSError("no dbus session")

    monkeypatch.setattr(linux.subprocess, "run", boom)
    linux.LinuxBackend().notify("title", "body")  # must not raise -- best-effort


# ---------------------------------------------------------------------------
# open_file / open_url with an app=: REUSE_WINDOW_ARGS wiring (Step 3.24)
# ---------------------------------------------------------------------------

def test_open_file_injects_reuse_window_flag_for_vs_code(app_dirs, tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("x")
    with patch.object(linux, "shutil") as mock_shutil, patch.object(linux, "subprocess") as mock_subprocess:
        mock_shutil.which.return_value = "/usr/bin/code"
        result = tools.open_file(str(target), app="visual studio code")
    args = mock_subprocess.Popen.call_args[0][0]
    assert args == ["code", "-r", str(target)]
    assert "Opened" in result and "Visual Studio Code" in result


def test_open_file_other_apps_go_through_gtk_launch_unmodified(app_dirs, tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("x")
    with patch.object(linux, "shutil") as mock_shutil, patch.object(linux, "subprocess") as mock_subprocess:
        mock_shutil.which.return_value = "/usr/bin/gtk-launch"
        tools.open_file(str(target), app="code::blocks")
    args = mock_subprocess.Popen.call_args[0][0]
    assert args == ["gtk-launch", "codeblocks", str(target)]


def test_open_file_missing_target(app_dirs, tmp_path):
    result = tools.open_file(str(tmp_path / "nope.txt"))
    assert "No such file" in result


# ---------------------------------------------------------------------------
# Shared helpers used by open_url/fetch_url/web_search
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("example.com", "https://example.com"),
    ("http://example.com", "http://example.com"),
    ("https://example.com", "https://example.com"),
])
def test_normalize_url(raw, expected):
    assert tools._normalize_url(raw) == expected


def test_strip_html_removes_tags_scripts_and_collapses_whitespace():
    raw = "<html><script>evil()</script><body>  Hello   <b>world</b>  </body></html>"
    assert tools._strip_html(raw) == "Hello world"


def test_strip_html_truncates():
    raw = "<p>" + ("x" * 5000) + "</p>"
    assert len(tools._strip_html(raw, max_chars=100)) == 100


def test_unwrap_ddg_link_extracts_the_real_url():
    wrapped = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage&rut=abc"
    assert tools._unwrap_ddg_link(wrapped) == "https://example.com/page"


def test_unwrap_ddg_link_passthrough_when_not_wrapped():
    assert tools._unwrap_ddg_link("https://example.com") == "https://example.com"


# ---------------------------------------------------------------------------
# File primitives — the boring but load-bearing ones
# ---------------------------------------------------------------------------

def test_write_then_read_round_trip(tmp_path):
    p = tmp_path / "f.txt"
    tools.write_file(str(p), "hello")
    assert tools.read_file(str(p)) == "hello"


def test_make_dir_is_idempotent(tmp_path):
    p = tmp_path / "a" / "b"
    tools.make_dir(str(p))
    tools.make_dir(str(p))  # must not raise on the second call
    assert p.is_dir()


# ---------------------------------------------------------------------------
# save_note (B3): durable cross-session memory, bounded on the write path.
# ---------------------------------------------------------------------------

def test_save_note_writes_a_bullet_line(tmp_path, monkeypatch):
    notes_path = tmp_path / "memory" / "notes.md"
    monkeypatch.setattr(tools, "NOTES_PATH", notes_path)
    result = tools.save_note("the user prefers Rust")
    assert "Saved note" in result
    assert notes_path.read_text() == "- the user prefers Rust\n"


def test_save_note_creates_missing_parent_directories(tmp_path, monkeypatch):
    notes_path = tmp_path / "does" / "not" / "exist" / "notes.md"
    monkeypatch.setattr(tools, "NOTES_PATH", notes_path)
    tools.save_note("x")
    assert notes_path.is_file()


def test_save_note_appends_rather_than_overwrites(tmp_path, monkeypatch):
    notes_path = tmp_path / "notes.md"
    monkeypatch.setattr(tools, "NOTES_PATH", notes_path)
    tools.save_note("first fact")
    tools.save_note("second fact")
    content = notes_path.read_text()
    assert "- first fact\n" in content
    assert "- second fact\n" in content


def test_save_note_rejects_empty_note(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "NOTES_PATH", tmp_path / "notes.md")
    assert "Error" in tools.save_note("   ")


def test_save_note_collapses_embedded_newlines_to_one_line(tmp_path, monkeypatch):
    notes_path = tmp_path / "notes.md"
    monkeypatch.setattr(tools, "NOTES_PATH", notes_path)
    tools.save_note("line one\nline two\r\nline three")
    assert notes_path.read_text().count("\n") == 1  # one note, one line


def test_save_note_rejects_an_overlong_note_rather_than_truncating(tmp_path, monkeypatch):
    notes_path = tmp_path / "notes.md"
    monkeypatch.setattr(tools, "NOTES_PATH", notes_path)
    result = tools.save_note("x" * (tools.MAX_NOTE_CHARS + 1))
    assert "too long" in result
    assert not notes_path.exists()  # refused outright, nothing partially written


def test_save_note_refuses_once_the_file_cap_is_reached(tmp_path, monkeypatch):
    notes_path = tmp_path / "notes.md"
    monkeypatch.setattr(tools, "NOTES_PATH", notes_path)
    notes_path.write_text("x" * (tools.MAX_NOTES_FILE_CHARS - 10))
    result = tools.save_note("one more fact that won't fit")
    assert "memory is full" in result
    assert notes_path.read_text() == "x" * (tools.MAX_NOTES_FILE_CHARS - 10)  # untouched, not evicted


# ---------------------------------------------------------------------------
# edit_file (C1): exact-string replace, must match uniquely
# ---------------------------------------------------------------------------

def test_edit_file_replaces_a_unique_match(tmp_path):
    p = tmp_path / "f.py"
    p.write_text("def foo():\n    return 1\n")
    result = tools.edit_file(str(p), "return 1", "return 2")
    assert "Edited" in result
    assert p.read_text() == "def foo():\n    return 2\n"


def test_edit_file_refuses_when_old_string_not_found(tmp_path):
    p = tmp_path / "f.py"
    p.write_text("original content")
    result = tools.edit_file(str(p), "nonexistent", "x")
    assert "not found" in result
    assert p.read_text() == "original content"  # untouched


def test_edit_file_refuses_an_ambiguous_match_rather_than_guessing(tmp_path):
    p = tmp_path / "f.py"
    p.write_text("x = 1\nx = 1\n")
    result = tools.edit_file(str(p), "x = 1", "x = 2")
    assert "matches 2 times" in result
    assert p.read_text() == "x = 1\nx = 1\n"  # untouched -- no guessing which one


def test_edit_file_rejects_empty_old_string(tmp_path):
    p = tmp_path / "f.py"
    p.write_text("content")
    result = tools.edit_file(str(p), "", "x")
    assert "Error" in result
    assert p.read_text() == "content"


def test_edit_file_only_replaces_the_one_match_not_every_occurrence_elsewhere(tmp_path):
    """Regression guard: str.replace(..., 1) must be used, not a global
    replace -- even though uniqueness is already enforced above this, a
    global replace on a since-duplicated string elsewhere in a bigger file
    would silently touch text it was never asked to."""
    p = tmp_path / "f.py"
    p.write_text("UNIQUE_MARKER\nsome other line\n")
    tools.edit_file(str(p), "UNIQUE_MARKER", "REPLACED")
    assert p.read_text() == "REPLACED\nsome other line\n"


# ---------------------------------------------------------------------------
# glob_files (C1)
# ---------------------------------------------------------------------------

def test_glob_files_finds_matching_files(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.txt").write_text("")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.py").write_text("")
    result = tools.glob_files("**/*.py", str(tmp_path))
    assert "a.py" in result
    assert "c.py" in result
    assert "b.txt" not in result


def test_glob_files_no_matches(tmp_path):
    assert "No files matching" in tools.glob_files("*.nonexistent", str(tmp_path))


def test_glob_files_skips_heavy_directories(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("")
    (tmp_path / "real.py").write_text("")
    result = tools.glob_files("**/*", str(tmp_path))
    assert "real.py" in result
    assert ".git" not in result


def test_glob_files_not_a_directory(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x")
    assert "Not a directory" in tools.glob_files("*", str(f))


# ---------------------------------------------------------------------------
# tree (C1)
# ---------------------------------------------------------------------------

def test_tree_shows_files_and_directories(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("")
    result = tools.tree(str(tmp_path))
    assert "- a.py" in result
    assert "d sub" in result
    assert "- b.py" in result


def test_tree_respects_max_depth(tmp_path):
    deep = tmp_path / "l1" / "l2" / "l3"
    deep.mkdir(parents=True)
    (deep / "buried.py").write_text("")
    result = tools.tree(str(tmp_path), max_depth=1)
    assert "l1" in result
    assert "buried.py" not in result  # beyond max_depth


def test_tree_skips_heavy_directories(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("")
    (tmp_path / "real.py").write_text("")
    result = tools.tree(str(tmp_path))
    assert "real.py" in result
    assert "node_modules" not in result


def test_tree_not_a_directory(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x")
    assert "Not a directory" in tools.tree(str(f))


def test_list_dir_marks_files_and_directories(tmp_path):
    (tmp_path / "file.txt").write_text("x")
    (tmp_path / "sub").mkdir()
    listing = tools.list_dir(str(tmp_path))
    assert "- file.txt" in listing
    assert "d sub" in listing


def test_list_dir_empty(tmp_path):
    assert tools.list_dir(str(tmp_path)) == "(empty)"


# ---------------------------------------------------------------------------
# _is_existing_file (A3's write_file confirmation decides on this)
# ---------------------------------------------------------------------------

def test_is_existing_file_true_for_a_real_file(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("x")
    assert tools._is_existing_file(str(p)) is True


def test_is_existing_file_false_for_a_new_path(tmp_path):
    assert tools._is_existing_file(str(tmp_path / "new.txt")) is False


def test_is_existing_file_false_for_a_directory(tmp_path):
    assert tools._is_existing_file(str(tmp_path)) is False


def test_is_existing_file_false_for_empty_path():
    assert tools._is_existing_file("") is False


# ---------------------------------------------------------------------------
# grep (A3): read-only text search, no shell involved
# ---------------------------------------------------------------------------

@pytest.fixture
def search_tree(tmp_path):
    (tmp_path / "a.py").write_text("def hello():\n    return 'world'\n")
    (tmp_path / "b.py").write_text("class Hello:\n    pass\n")
    (tmp_path / "notes.txt").write_text("nothing relevant here\n")
    (tmp_path / "data.bin").write_bytes(b"\x00\x01hello\x02\x03")
    skip_dir = tmp_path / "venv" / "lib"
    skip_dir.mkdir(parents=True)
    (skip_dir / "c.py").write_text("def hello(): pass\n")
    return tmp_path


def test_grep_finds_matches_with_file_and_line_number(search_tree):
    result = tools.grep("hello", str(search_tree))
    assert "a.py:1: def hello():" in result
    assert "b.py:1: class Hello:" in result  # case-insensitive


def test_grep_is_case_insensitive_by_design(search_tree):
    assert "b.py" in tools.grep("HELLO", str(search_tree))


def test_grep_skips_common_heavy_directories(search_tree):
    result = tools.grep("hello", str(search_tree))
    assert "venv" not in result


def test_grep_skips_binary_files(search_tree):
    result = tools.grep("hello", str(search_tree))
    assert "data.bin" not in result


def test_grep_narrowed_by_glob(search_tree):
    result = tools.grep("hello", str(search_tree), glob="**/notes.txt")
    assert "No matches" in result


def test_grep_no_matches_is_a_clear_message_not_empty_string(search_tree):
    result = tools.grep("zzz_nomatch_zzz", str(search_tree))
    assert "No matches" in result


def test_grep_invalid_regex_does_not_crash(search_tree):
    result = tools.grep("(unclosed[", str(search_tree))
    assert "Invalid pattern" in result


def test_grep_target_not_a_directory(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    assert "Not a directory" in tools.grep("x", str(f))


def test_grep_caps_the_number_of_matches(tmp_path):
    big = tmp_path / "big.txt"
    big.write_text("hit\n" * (tools.MAX_GREP_MATCHES + 20))
    result = tools.grep("hit", str(tmp_path))
    match_lines = [line for line in result.splitlines() if line.startswith("big.txt:")]
    assert len(match_lines) == tools.MAX_GREP_MATCHES
    assert "narrow the pattern" in result


def test_looks_binary_true_for_nul_byte(tmp_path):
    p = tmp_path / "b.bin"
    p.write_bytes(b"abc\x00def")
    assert tools._looks_binary(p) is True


def test_looks_binary_false_for_text(tmp_path):
    p = tmp_path / "t.txt"
    p.write_text("just text")
    assert tools._looks_binary(p) is False


def test_delete_file(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("x")
    tools.delete_file(str(p))
    assert not p.exists()


def test_run_command_captures_stdout():
    assert tools.run_command("echo hello").strip() == "hello"


def test_run_command_no_output_reports_exit_code():
    assert tools.run_command("true") == "(exited 0, no output)"


# ---------------------------------------------------------------------------
# run_tests (C3): same execution shape as run_command, longer timeout
# ---------------------------------------------------------------------------

def test_run_tests_captures_stdout():
    assert tools.run_tests("echo hello").strip() == "hello"


def test_run_tests_defaults_to_pytest(monkeypatch):
    captured = {}

    def fake_run(command, shell, capture_output, text, timeout, stdin):
        captured["command"] = command
        captured["timeout"] = timeout
        captured["stdin"] = stdin
        class R: stdout, stderr, returncode = "", "", 0
        return R()

    monkeypatch.setattr(tools.subprocess, "run", fake_run)
    tools.run_tests()
    assert captured["command"] == "pytest"
    assert captured["timeout"] == tools.RUN_TESTS_TIMEOUT
    assert tools.RUN_TESTS_TIMEOUT > tools.RUN_COMMAND_TIMEOUT  # the whole point of a separate tool
    assert captured["stdin"] == tools.subprocess.DEVNULL


# ---------------------------------------------------------------------------
# _run_shell stdin=DEVNULL (real bug, found live 2026-09-24): without it, a
# command that reads stdin (python3, ssh, sudo, git commit with no -m, ...)
# inherits R.A.V.E.N's own stdin -- the user's real terminal in interactive
# mode -- and blocks forever, in a way even Ctrl+C couldn't recover from
# (prompt_toolkit already owns the terminal in its own raw input mode).
# The actual hang-and-fix was reproduced live with a real pty before this
# fix was written (see DEV_LOG) -- that reproduction isn't repeated here as
# a routine test, since it requires reassigning the TEST PROCESS's own stdin
# fd to prove anything, which is too invasive/risky to do routinely inside
# the main suite (real risk of corrupting pytest's own I/O if anything goes
# wrong). What's safe and still meaningful to assert on every run: the
# actual subprocess.run call unconditionally includes stdin=DEVNULL, for
# every one of _run_shell's callers, not just one.
# ---------------------------------------------------------------------------

def test_run_command_and_run_tests_and_git_all_pass_stdin_devnull(monkeypatch):
    calls = []

    def fake_run(command, shell, capture_output, text, timeout, stdin):
        calls.append(stdin)
        class R: stdout, stderr, returncode = "", "", 0
        return R()

    monkeypatch.setattr(tools.subprocess, "run", fake_run)
    tools.run_command("echo hi")
    tools.run_tests()
    tools.git("status")
    assert calls == [tools.subprocess.DEVNULL] * 3


# ---------------------------------------------------------------------------
# sudo: the one deliberate exception to the stdin=DEVNULL rule above. A real
# fix for a real gap -- sudo could never authenticate before this (DEVNULL
# means it can never read a password), so an interactive CLI user approving a
# sudo call via confirm_run just watched it fail afterward with no way to
# actually supply the password it needed.
# ---------------------------------------------------------------------------

class _FakeProc:
    """Stands in for a subprocess.Popen handle -- _run_capturing_group only
    ever calls .communicate()/.returncode/.pid on what Popen(...) gives it."""
    def __init__(self, stdout="", stderr="", returncode=0, hangs=False):
        self._stdout, self._stderr, self.returncode = stdout, stderr, returncode
        self._hangs = hangs
        self.pid = 4242
        self.killed = False

    def communicate(self, input=None, timeout=None):
        if self._hangs and not self.killed:
            raise subprocess.TimeoutExpired(cmd="x", timeout=timeout)
        return self._stdout, self._stderr


def _fake_popen(procs):
    """Returns a stand-in for subprocess.Popen that hands back `procs` in
    order, recording each call's (command, kwargs)."""
    calls = []
    queue = list(procs)

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return queue.pop(0)

    popen.calls = calls
    return popen


def test_sudo_with_a_cached_credential_never_asks_for_a_password(monkeypatch):
    """sudo -n succeeds immediately when sudo's own ~15 min ticket is still
    valid -- the password provider must never even be consulted in that case."""
    fake = _fake_popen([_FakeProc(stdout="ok\n", returncode=0)])
    monkeypatch.setattr(tools.subprocess, "Popen", fake)
    provider_calls = []
    tools.set_sudo_password_provider(lambda: provider_calls.append(1) or "hunter2")

    assert tools.run_command("sudo apt update").strip() == "ok"
    assert len(fake.calls) == 1
    command, kwargs = fake.calls[0]
    assert command == "sudo -n apt update"
    assert kwargs["stdin"] == tools.subprocess.DEVNULL
    assert kwargs["start_new_session"] is True
    assert provider_calls == []  # never asked


def test_sudo_without_a_cached_credential_asks_for_and_uses_the_password(monkeypatch):
    fake = _fake_popen([
        _FakeProc(stderr="sudo: a password is required", returncode=1),
        _FakeProc(stdout="updated\n", returncode=0),
    ])
    monkeypatch.setattr(tools.subprocess, "Popen", fake)
    tools.set_sudo_password_provider(lambda: "hunter2")

    assert tools.run_command("sudo apt update").strip() == "updated"
    assert len(fake.calls) == 2
    probe_cmd, probe_kwargs = fake.calls[0]
    auth_cmd, auth_kwargs = fake.calls[1]
    assert probe_cmd == "sudo -n apt update"
    assert auth_cmd == "sudo -S -p '' apt update"
    # The password reaches the real process ONLY via communicate()'s input,
    # never the command string (where it'd show up in a process list / this
    # tool's own returned output) and never a plain stdin=DEVNULL (which
    # would just repeat the original bug).
    assert auth_kwargs["stdin"] == tools.subprocess.PIPE
    assert "hunter2" not in auth_cmd
    assert auth_kwargs["start_new_session"] is True


def test_sudo_uses_a_generous_timeout_for_the_real_authenticated_command(monkeypatch):
    """RUN_COMMAND_TIMEOUT (30s) is fine for the instant -n probe, but a real
    privileged command (a package install, say) can easily run past it --
    the REAL authenticated call gets its own, much longer cap."""
    timeouts = []
    real_communicate = _FakeProc.communicate

    def spying_communicate(self, input=None, timeout=None):
        timeouts.append(timeout)
        return real_communicate(self, input=input, timeout=timeout)

    monkeypatch.setattr(_FakeProc, "communicate", spying_communicate, raising=False)
    fake = _fake_popen([
        _FakeProc(stderr="sudo: a password is required", returncode=1),
        _FakeProc(returncode=0),
    ])
    monkeypatch.setattr(tools.subprocess, "Popen", fake)
    tools.set_sudo_password_provider(lambda: "hunter2")

    tools.run_command("sudo apt update")  # RUN_COMMAND_TIMEOUT=30 passed in
    assert timeouts == [tools.RUN_COMMAND_TIMEOUT, tools.RUN_SUDO_TIMEOUT]
    assert tools.RUN_SUDO_TIMEOUT > tools.RUN_COMMAND_TIMEOUT


def test_sudo_kills_the_whole_process_group_on_a_timeout_not_just_the_shell(monkeypatch):
    """The real bug this guards against: subprocess.run's own timeout only
    kills the `/bin/sh -c "..."` wrapper, leaving a real child (sudo itself,
    or whatever it's running) orphaned but still attached to the real
    terminal -- which is how an orphaned sudo ended up nattively prompting on
    a live user's terminal, completely outside R.A.V.E.N's control."""
    killed_pgids = []
    hanging = _FakeProc(hangs=True)

    def fake_killpg(pgid, sig):
        killed_pgids.append((pgid, sig))
        hanging.killed = True  # real os.killpg would let the drained communicate() return

    monkeypatch.setattr(tools.os, "killpg", fake_killpg)
    monkeypatch.setattr(tools.os, "getpgid", lambda pid: pid)
    fake = _fake_popen([hanging])
    monkeypatch.setattr(tools.subprocess, "Popen", fake)

    result = tools.run_command("sudo apt update")
    assert "Timed out" in result
    assert killed_pgids == [(hanging.pid, tools.signal.SIGKILL)]


def test_sudo_declining_the_password_prompt_never_runs_the_command(monkeypatch):
    fake = _fake_popen([_FakeProc(stderr="sudo: a password is required", returncode=1)])
    monkeypatch.setattr(tools.subprocess, "Popen", fake)
    tools.set_sudo_password_provider(lambda: None)  # Enter with no input -- declined

    assert tools.run_command("sudo apt update") == "Cancelled: no sudo password entered."
    assert len(fake.calls) == 1  # only the probe -- never the real command
    assert fake.calls[0][0] == "sudo -n apt update"


def test_sudo_with_no_registered_provider_fails_exactly_like_before(monkeypatch):
    """The desktop server never registers a provider (see
    set_sudo_password_provider's docstring) -- a sudo call there must keep
    failing cleanly, not hang or newly start prompting for anything."""
    fake = _fake_popen([_FakeProc(stderr="sudo: a password is required", returncode=1)])
    monkeypatch.setattr(tools.subprocess, "Popen", fake)
    assert tools.run_command("sudo apt update") == "sudo: a password is required"
    assert len(fake.calls) == 1  # never even tries the password path


def test_a_command_that_merely_mentions_sudo_is_not_treated_as_one(monkeypatch):
    """`_SUDO_RE` only matches sudo as the command's own first word -- a
    command that merely contains the word (in a pipeline, as an argument,
    inside a string) must go through the ordinary DEVNULL path unchanged."""
    def boom(*a, **k):
        raise AssertionError("should never take the sudo path")

    monkeypatch.setattr(tools, "_run_sudo", boom)
    assert tools.run_command("echo 'ask for sudo later'").strip() == "ask for sudo later"


# ---------------------------------------------------------------------------
# SKILLS / core_tool_names (D2)
# ---------------------------------------------------------------------------

def test_every_skill_tool_is_a_real_registered_tool():
    """A typo'd tool name in SKILLS would silently vanish from BOTH core and
    every skill -- unreachable by the model no matter what it calls."""
    all_skill_tools = {name for names in tools.SKILLS.values() for name in names}
    assert all_skill_tools <= set(tools.TOOL_FUNCTIONS)


def test_every_skill_has_a_description():
    assert set(tools.SKILLS) == set(tools.SKILL_DESCRIPTIONS)


def test_core_tool_names_excludes_skill_tools():
    core = tools.core_tool_names()
    all_skill_tools = {name for names in tools.SKILLS.values() for name in names}
    assert core.isdisjoint(all_skill_tools)


def test_core_tool_names_includes_everything_else():
    """core + skills together must cover every registered tool -- nothing
    silently falls through the cracks and becomes permanently unreachable."""
    all_skill_tools = {name for names in tools.SKILLS.values() for name in names}
    assert tools.core_tool_names() | all_skill_tools == set(tools.TOOL_FUNCTIONS)


def test_core_includes_the_coding_essentials():
    core = tools.core_tool_names()
    for name in ("read_file", "write_file", "edit_file", "grep", "glob_files",
                 "tree", "run_command", "run_tests", "git", "save_note"):
        assert name in core


# ---------------------------------------------------------------------------
# analyze_image / browser_screenshot (V2): analyze_image is registered as a
# placeholder only -- Assistant._run_tool intercepts it before it ever runs.
# ---------------------------------------------------------------------------

def test_analyze_image_placeholder_never_actually_runs():
    """If this DOES run, the interception in Assistant._run_tool was
    skipped somehow -- it should fail loudly and clearly, not silently."""
    with pytest.raises(RuntimeError, match="must be handled by Assistant"):
        tools.analyze_image("x.png", "what is this?")


def test_vision_skill_contains_analyze_image():
    assert "analyze_image" in tools.SKILLS["vision"]


def test_browser_skill_contains_screenshot():
    assert "browser_screenshot" in tools.SKILLS["browser"]


# ---------------------------------------------------------------------------
# Text encoding (2026-10-01). Path.read_text()/write_text() with no `encoding`
# use the LOCALE encoding, which is cp1252 on a French Windows install, not
# UTF-8. Found live: write_file produced an HTML page declaring
# <meta charset="UTF-8"> that was actually cp1252 on disk, so every accented
# character rendered as a replacement glyph in the browser.
#
# These tests assert on the BYTES on disk, not on what a round trip through
# the same functions returns — a read and a write that are wrong in the same
# way round-trip perfectly and hide the bug entirely.
# ---------------------------------------------------------------------------

ACCENTS = "Fréquence des vagues — 30 % d'amplitude « test »"


def test_write_file_writes_utf8_regardless_of_the_platform_locale(tmp_path):
    target = tmp_path / "page.html"
    tools.write_file(str(target), ACCENTS)
    assert target.read_bytes().decode("utf-8") == ACCENTS


def test_write_file_handles_characters_absent_from_cp1252(tmp_path):
    """The crash case, not just the mojibake case: a narrow no-break space
    (U+202F) has no cp1252 equivalent at all, so the old code raised
    UnicodeEncodeError and lost the write outright."""
    target = tmp_path / "note.txt"
    texte = "espace fine insécable et emoji \U0001F30A"
    tools.write_file(str(target), texte)
    assert target.read_bytes().decode("utf-8") == texte


def test_read_file_reads_utf8(tmp_path):
    source = tmp_path / "in.txt"
    source.write_bytes(ACCENTS.encode("utf-8"))
    assert tools.read_file(str(source)) == ACCENTS


def test_read_file_still_reads_a_legacy_non_utf8_file(tmp_path):
    """Strict UTF-8 on read would turn a previously-working read_file into a
    hard error for any pre-existing cp1252 file, so there's a fallback."""
    source = tmp_path / "legacy.txt"
    source.write_bytes("café".encode("cp1252"))
    assert "caf" in tools.read_file(str(source))  # decoded, not raised


def test_edit_file_keeps_the_file_utf8(tmp_path):
    target = tmp_path / "page.html"
    target.write_bytes("<p>ancien</p>".encode("utf-8"))
    tools.edit_file(str(target), "ancien", "nouveau — révisé")
    assert target.read_bytes().decode("utf-8") == "<p>nouveau — révisé</p>"


def test_save_note_writes_utf8(tmp_path):
    notes = tmp_path / "notes.md"
    with patch.object(tools, "NOTES_PATH", notes):
        tools.save_note("préférence : accents conservés")
    assert "préférence" in notes.read_bytes().decode("utf-8")
