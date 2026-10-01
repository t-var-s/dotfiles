"""Exercise the actual piped installer through a controlling terminal.

Uses only Python's standard library. HOME changes only in child processes.
"""
import errno
import os
from pathlib import Path
import pty
import select
import shlex
import shutil
import signal
import subprocess
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def run_terminal(command, home, answers=(), env_extra=None, before_answer=None):
    """stdin carries the script; /dev/tty carries the scripted user answers."""
    pid, terminal = pty.fork()
    if pid == 0:
        env = dict(os.environ, HOME=str(home), TERM="xterm-256color")
        env.update(env_extra or {})
        os.execve("/bin/bash", ["/bin/bash", "-c", command], env)
    output = b""
    answered = 0
    deadline = time.monotonic() + 20
    status = None
    try:
        while time.monotonic() < deadline:
            if select.select([terminal], [], [], 0.1)[0]:
                try:
                    chunk = os.read(terminal, 65536)
                except OSError as error:
                    if error.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                output += chunk
                if output.count(b"[y/N]: ") > answered:
                    if answered >= len(answers):
                        raise AssertionError("Unexpected prompt:\n" + output.decode(errors="replace"))
                    if before_answer:
                        before_answer(answered)
                    os.write(terminal, answers[answered].encode() + b"\n")
                    answered += 1
            finished, status_value = os.waitpid(pid, os.WNOHANG)
            if finished:
                status = status_value
                # Drain PTY output after child exit.
                while select.select([terminal], [], [], 0)[0]:
                    try:
                        chunk = os.read(terminal, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    output += chunk
                break
        else:
            raise AssertionError("Installer timed out:\n" + output.decode(errors="replace"))
        if status is None:
            _, status = os.waitpid(pid, 0)
    finally:
        if status is None:
            try:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
            except ProcessLookupError:
                pass
        os.close(terminal)
    return os.waitstatus_to_exitcode(status), output.decode(errors="replace")


class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp_base = Path(os.environ.get("TMPDIR", "/tmp")).resolve()
        cls.temp_base = temp_base
        cls.run_tmp = Path(subprocess.check_output(
            ["mktemp", "-d", str(temp_base / "codex-dotfiles-tests.XXXXXX")], text=True
        ).strip()).resolve()
        (cls.run_tmp / ".codex-task-temp").touch()
        cls.project = cls.run_tmp / "project"
        cls.project.mkdir()
        for filename in (".vimrc", ".tmux.conf", ".gitignore"):
            shutil.copy2(ROOT / filename, cls.project / filename)
        for directory in ("installer", "scripts"):
            shutil.copytree(ROOT / directory, cls.project / directory)
        subprocess.run(["git", "init", "-q", str(cls.project)], check=True)
        subprocess.run(["git", "add", ".gitignore", ".vimrc", ".tmux.conf", "installer", "scripts"],
                       cwd=cls.project, check=True)
        subprocess.run(["git", "-c", "user.name=Installer Test", "-c", "user.email=installer-test@example.invalid",
                        "-c", "commit.gpgsign=false", "commit", "-qm", "Fixture sources"],
                       cwd=cls.project, check=True)
        cls.build()

    @classmethod
    def tearDownClass(cls):
        # Validate the dedicated generated test directory before recursive removal.
        target = cls.run_tmp.resolve()
        forbidden = {Path("/"), Path.home().resolve(), ROOT, cls.temp_base}
        for key in ("CODEX_HOME", "TMPDIR"):
            if os.environ.get(key):
                forbidden.add(Path(os.environ[key]).resolve())
        if (target in forbidden or target.parent != cls.temp_base
                or not target.name.startswith("codex-dotfiles-tests.")
                or not (target / ".codex-task-temp").is_file()):
            raise RuntimeError(f"Refusing cleanup; test files remain at {target}")
        subprocess.run(["/bin/rm", "-rf", str(target)], check=True)

    @classmethod
    def build(cls, expected=0):
        result = subprocess.run(["/bin/bash", "scripts/build.sh"], cwd=cls.project,
                                capture_output=True, text=True)
        if result.returncode != expected:
            raise AssertionError(result.stdout + result.stderr)
        return result

    def setUp(self):
        self.home = self.run_tmp / self._testMethodName / "home with spaces"
        self.home.mkdir(parents=True)

    def install(self, answers=(), **kwargs):
        path = shlex.quote(str(self.project / "dist/install.sh"))
        return run_terminal(f"cat {path} | /bin/bash", self.home, answers, **kwargs)

    def backups(self):
        return list((self.home / ".dotfiles-backups").glob("run-*"))

    def assert_installed(self, name):
        self.assertEqual((self.home / name).read_bytes(), (self.project / name).read_bytes())

    def test_fresh_install_repeat_and_restore(self):
        status, output = self.install(["y", "y", "y"])
        self.assertEqual(status, 0, output)
        self.assert_installed(".vimrc")
        self.assert_installed(".tmux.conf")
        self.assertEqual((self.home / ".vimrc").stat().st_mode & 0o777, 0o600)
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        status, output = self.install()
        self.assertEqual(status, 0, output)
        self.assertEqual(output.count("Already up to date."), 2)
        self.assertEqual(self.backups(), backups)
        command = "/bin/bash " + shlex.quote(str(backups[0] / "restore.sh"))
        status, output = run_terminal(command, self.home, ["y"])
        self.assertEqual(status, 0, output)
        self.assertFalse((self.home / ".vimrc").exists())
        self.assertFalse((self.home / ".tmux.conf").exists())
        status, output = run_terminal(command, self.home)
        self.assertEqual(status, 0, output)
        self.assertIn("Nothing to restore", output)

    def test_existing_files_diff_backup_restore_and_permissions(self):
        original = b'" local configuration\nset number\n'
        (self.home / ".vimrc").write_bytes(original)
        (self.home / ".vimrc").chmod(0o640)
        status, output = self.install(["y", "y", "n", "y"])
        self.assertEqual(status, 0, output)
        self.assertIn('-" local configuration', output)
        self.assert_installed(".vimrc")
        self.assertFalse((self.home / ".tmux.conf").exists())
        self.assertEqual((self.home / ".vimrc").stat().st_mode & 0o777, 0o640)
        backup = self.backups()[0]
        self.assertEqual((backup / "originals/vim").read_bytes(), original)
        status, output = run_terminal("/bin/bash " + shlex.quote(str(backup / "restore.sh")), self.home, ["y"])
        self.assertEqual(status, 0, output)
        self.assertEqual((self.home / ".vimrc").read_bytes(), original)
        self.assertEqual((self.home / ".vimrc").stat().st_mode & 0o777, 0o640)

    def test_cancel_and_default_no(self):
        status, output = self.install(["y", "y", ""])
        self.assertEqual(status, 0, output)
        self.assertEqual(list(self.home.iterdir()), [])
        status, output = self.install(["", ""])
        self.assertEqual(status, 0, output)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_no_terminal_and_truncated_download(self):
        installer = (self.project / "dist/install.sh").read_bytes()
        for script in (installer, installer.rsplit(b'main "$@"', 1)[0]):
            result = subprocess.run(["/bin/bash"], input=script, capture_output=True,
                                    start_new_session=True, env=dict(os.environ, HOME=str(self.home)))
            self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(result.returncode, 0)  # Definitions only: no entry point.
        result = subprocess.run(["/bin/bash"], input=installer, capture_output=True,
                                start_new_session=True, env=dict(os.environ, HOME=str(self.home)))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"interactive terminal", result.stderr)

    def test_symlink_and_directory_destinations_are_skipped(self):
        outside = self.home.parent / "outside"
        outside.write_text("keep me\n")
        (self.home / ".vimrc").symlink_to(outside)
        (self.home / ".tmux.conf").mkdir()
        status, output = self.install()
        self.assertEqual(status, 0, output)
        self.assertEqual(output.count("symlink or non-file"), 2)
        self.assertEqual(outside.read_text(), "keep me\n")
        self.assertEqual(self.backups(), [])

    def test_edit_during_review_aborts(self):
        original = self.home / ".vimrc"
        original.write_text('" initial\n')
        def edit(index):
            if index == 3:
                original.write_text('" edited during review\n')
        status, output = self.install(["n", "y", "n", "y"], before_answer=edit)
        self.assertNotEqual(status, 0, output)
        self.assertIn("changed during review", output)
        self.assertEqual(original.read_text(), '" edited during review\n')
        self.assertEqual(self.backups(), [])

    def test_restore_refuses_later_local_edits(self):
        status, output = self.install(["y", "y", "y"])
        self.assertEqual(status, 0, output)
        (self.home / ".vimrc").write_text('" new local edit\n')
        backup = self.backups()[0]
        status, output = run_terminal("/bin/bash " + shlex.quote(str(backup / "restore.sh")), self.home)
        self.assertNotEqual(status, 0, output)
        self.assertIn("changed since installation", output)
        self.assert_installed(".tmux.conf")

    def test_old_application_version_skips_only_that_file(self):
        fake_bin = self.home.parent / "bin"
        fake_bin.mkdir()
        fake_vim = fake_bin / "vim"
        fake_vim.write_text('#!/bin/sh\nprintf "VIM - Vi IMproved 7.3\\n"\n')
        fake_vim.chmod(0o755)
        status, output = self.install(["y", "y"], env_extra={"PATH": str(fake_bin) + ":" + os.environ["PATH"]})
        self.assertEqual(status, 0, output)
        self.assertIn("requires 7.4", output)
        self.assertFalse((self.home / ".vimrc").exists())
        self.assert_installed(".tmux.conf")

    def test_missing_application_skips_only_that_file(self):
        fake_bin = self.home.parent / "bin"
        fake_bin.mkdir()
        for name in ("vim", "uname", "mktemp", "touch", "cat", "sed", "cp", "cmp",
                     "diff", "mkdir", "date", "mv", "rm", "rmdir", "dirname"):
            (fake_bin / name).symlink_to(shutil.which(name))
        status, output = self.install(["y", "y"], env_extra={"PATH": str(fake_bin)})
        self.assertEqual(status, 0, output)
        self.assertIn("tmux is not installed", output)
        self.assert_installed(".vimrc")
        self.assertFalse((self.home / ".tmux.conf").exists())

    def test_tmux_minimum_version_boundary(self):
        # Fake the installer's initial version check; validation and the config's
        # version-dependent commands use the real binary's version afterward.
        real_tmux = shutil.which("tmux")
        original_home = self.home
        try:
            for version in ("1.7", "1.8"):
                with self.subTest(version=version):
                    self.home = original_home / version
                    self.home.mkdir()
                    fake_bin = self.home.parent / ("bin-" + version)
                    fake_bin.mkdir()
                    fake_tmux = fake_bin / "tmux"
                    banner_read = shlex.quote(str(fake_bin / "banner-read"))
                    fake_tmux.write_text(
                        f'#!/bin/sh\nif [ "$1" = "-V" ] && [ ! -e {banner_read} ]; then\n'
                        f'  : > {banner_read}\n'
                        f'  printf "tmux {version}\\n"\nelse\n'
                        f'  exec {shlex.quote(real_tmux)} "$@"\nfi\n'
                    )
                    fake_tmux.chmod(0o755)
                    answers = ["y", "y"] if version == "1.7" else ["n", "y", "y"]
                    status, output = self.install(answers, env_extra={
                        "PATH": str(fake_bin) + ":" + os.environ["PATH"]
                    })
                    self.assertEqual(status, 0, output)
                    if version == "1.7":
                        self.assertIn("requires 1.8 or newer", output)
                        self.assert_installed(".vimrc")
                        self.assertFalse((self.home / ".tmux.conf").exists())
                    else:
                        self.assertIn("tmux 1.8 (minimum 1.8)", output)
                        self.assert_installed(".tmux.conf")
        finally:
            self.home = original_home

    def test_partial_replacement_failure_can_be_restored(self):
        original = b'" original local file\n'
        (self.home / ".vimrc").write_bytes(original)
        fake_bin = self.home.parent / "bin"
        fake_bin.mkdir()
        fake_mv = fake_bin / "mv"
        fake_mv.write_text(
            '#!/bin/bash\nfor argument do destination=$argument; done\n'
            'case "$destination" in */.tmux.conf) echo "Simulated rename failure" >&2; exit 1 ;; esac\n'
            f'exec {shlex.quote(shutil.which("mv"))} "$@"\n'
        )
        fake_mv.chmod(0o755)
        status, output = self.install(["n", "y", "y", "y"],
                                      env_extra={"PATH": str(fake_bin) + ":" + os.environ["PATH"]})
        self.assertNotEqual(status, 0, output)
        self.assertIn("Restore completed replacements", output)
        self.assert_installed(".vimrc")
        self.assertFalse((self.home / ".tmux.conf").exists())
        backup = self.backups()[0]
        status, output = run_terminal("/bin/bash " + shlex.quote(str(backup / "restore.sh")), self.home, ["y"])
        self.assertEqual(status, 0, output)
        self.assertEqual((self.home / ".vimrc").read_bytes(), original)
        self.assertFalse((self.home / ".tmux.conf").exists())

    def test_symlink_backup_directory_aborts_before_replacement(self):
        outside = self.home.parent / "outside"
        outside.mkdir()
        (self.home / ".dotfiles-backups").symlink_to(outside)
        status, output = self.install(["y", "y", "y"])
        self.assertNotEqual(status, 0, output)
        self.assertIn("Backup directory must not be a symlink", output)
        self.assertFalse((self.home / ".vimrc").exists())
        self.assertFalse((self.home / ".tmux.conf").exists())
        self.assertEqual(list(outside.iterdir()), [])

    def test_invalid_config_skipped(self):
        source = self.project / ".vimrc"
        original = source.read_bytes()
        try:
            source.write_text("ThisIsNotAVimCommand\n")
            self.build()
            status, output = self.install(["y", "y"])
            self.assertEqual(status, 0, output)
            self.assertIn("could not validate", output)
            self.assertFalse((self.home / ".vimrc").exists())
            self.assert_installed(".tmux.conf")
        finally:
            source.write_bytes(original)
            self.build()

    def test_manifest_extension_and_web_namespace(self):
        manifest = self.project / "installer/manifest.tsv"
        original = manifest.read_bytes()
        (self.project / "extra.conf").write_text("literal $HOME `command` \\ text\n")
        web = self.project / "web"
        web.mkdir(exist_ok=True)
        (web / "toolbox.js").write_text("window.exampleToolbox = {};\n")
        subprocess.run(["git", "add", "web/toolbox.js"], cwd=self.project, check=True)
        try:
            with manifest.open("a") as output:
                output.write("extra\textra.conf\t.config/example/config\tnone\t-\n")
            self.build()
            self.assertEqual((self.project / "dist/web/toolbox.js").read_bytes(), (web / "toolbox.js").read_bytes())
            self.assertNotIn(b"window.exampleToolbox", (self.project / "dist/install.sh").read_bytes())
            status, output = self.install(["n", "n", "y", "y"])
            self.assertEqual(status, 0, output)
            self.assertEqual((self.home / ".config/example/config").read_bytes(), (self.project / "extra.conf").read_bytes())
        finally:
            manifest.write_bytes(original)
            subprocess.run(["git", "update-index", "--force-remove", "web/toolbox.js"], cwd=self.project, check=True)
            self.build()
        self.assertFalse((self.project / "dist/web/toolbox.js").exists())

    def test_generic_dotfile_skips_symlink_parent(self):
        manifest = self.project / "installer/manifest.tsv"
        original = manifest.read_bytes()
        outside = self.home.parent / "outside"
        outside.mkdir()
        (self.home / ".config").symlink_to(outside)
        try:
            manifest.write_bytes(original + b"extra\t.vimrc\t.config/example/config\tnone\t-\n")
            self.build()
            status, output = self.install(["n", "n"])
            self.assertEqual(status, 0, output)
            self.assertIn("symlink or non-file", output)
            self.assertEqual(list(outside.iterdir()), [])
        finally:
            manifest.write_bytes(original)
            self.build()

    def test_build_rejects_binary_and_unterminated_payloads(self):
        source = self.project / ".vimrc"
        original = source.read_bytes()
        try:
            for data in (b"no final newline", b"embedded\x00nul\n"):
                source.write_bytes(data)
                result = self.build(expected=1)
                self.assertIn("Build error", result.stderr)
        finally:
            source.write_bytes(original)
            self.build()

    def test_build_preserves_unrecognized_output_directory(self):
        sentinel = self.project / "dist/.dotfiles-generated"
        saved = self.project / "saved-sentinel"
        sentinel.rename(saved)
        original = (self.project / "dist/install.sh").read_bytes()
        try:
            result = self.build(expected=1)
            self.assertIn("not a recognized generated directory", result.stderr)
            self.assertEqual((self.project / "dist/install.sh").read_bytes(), original)
        finally:
            saved.rename(sentinel)

    def test_build_revision_tracks_only_installer_inputs(self):
        generated = self.project / ".netlify"
        generated.mkdir(exist_ok=True)
        (generated / "generated-state.json").write_text("{}\n")
        source = self.project / ".vimrc"
        original = source.read_bytes()
        try:
            self.build()
            revision = (self.project / "dist/install.sh").read_text().splitlines()[2]
            self.assertNotIn("-dirty", revision)
            source.write_bytes(original + b'" local change\n')
            self.build()
            revision = (self.project / "dist/install.sh").read_text().splitlines()[2]
            self.assertTrue(revision.endswith("-dirty"), revision)
        finally:
            source.write_bytes(original)
            self.build()

    def test_manifest_rejects_traversal_duplicates_and_overlap(self):
        manifest = self.project / "installer/manifest.tsv"
        original = manifest.read_bytes()
        try:
            for entry in (
                "bad\t.vimrc\t../outside\tnone\t-\n",
                "vim\t.vimrc\t.other\tnone\t-\n",
                "bad\t.vimrc\t.vimrc/child\tnone\t-\n",
                "bad\t.vimrc\t.dotfiles-backups/config\tnone\t-\n",
            ):
                manifest.write_bytes(original + entry.encode())
                result = self.build(expected=1)
                self.assertIn("Build error", result.stderr)
        finally:
            manifest.write_bytes(original)
            self.build()


if __name__ == "__main__":
    unittest.main(verbosity=2)
