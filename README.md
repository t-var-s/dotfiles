# Dotfiles

Personal configuration oriented towards:
- portable backward-compatible vim and tmux
- keyboard layout in PT-PT with ç leader key
- yazi-inspired netrw file browsing
- decent markdown UX with tmux centered layout

Compatibility targets: **Vim 7.4+**, **tmux 2.1+**, and **Bash 3.2+**.
The installer checks the applications actually installed, rather than assuming
capabilities from an OS name. It installs configuration only, without sudo,
package installation, or changes to running Vim/tmux sessions. Use a UTF-8
terminal for the PT-PT mappings.

## Install or update

Once the build has been deployed to Netlify:

```sh
curl -fsSL https://dotfiles.viewfromtheweb.com/install.sh | bash
```

The script contains the dotfiles themselves; it makes no further downloads.
It reports its source revision, checks compatibility, offers a diff for changed
files, asks which files to include, and confirms the final selection before
writing configurations. Every yes/no prompt defaults to no.

Run the same command again to update to the latest successful deployment of
`main`. Identical files are skipped without another backup. Updates replace
whole files, including local edits, after confirmation; they do not merge.
Files removed from the repository are not automatically removed from your home.

Piped execution needs a controlling terminal because prompts read `/dev/tty`.
For a remote command, allocate a terminal with `ssh -t`. Without a terminal, the
installer stops before changing anything.

You may instead download the script to a file, inspect it, and run `bash` on that
file after the download succeeds, or transfer it to an offline machine. A saved
copy always installs its embedded revision. HTTPS errors should be fixed rather
than bypassed with curl's `-k` option. In `-fsSL`, `-f` fails on HTTP errors, `-s`
hides progress, `-S` retains error messages, and `-L` follows redirects.

## Backups and restoration

Each installation that changes files creates a private run directory under
`~/.dotfiles-backups/`, containing original files, installed snapshots, the source
revision, and a standalone `restore.sh`. The installer prints its exact command:

```sh
bash /path/printed/by/the/installer/restore.sh
```

Restoration is interactive. It refuses to overwrite files edited since that
installation; reconcile or preserve those edits first. To undo several updates,
restore them in reverse order. Newly installed files are moved into the backup
directory on restoration. Backups and newly created parent directories remain.

Symlinks, including symlinks in destination parents, are skipped. Directories and
other non-file destinations are skipped too. The installer preserves permissions
on existing writable files and creates new files with mode `0600`. Each file is
replaced by a rename in its own directory. A failure can leave earlier files
installed; the printed restore command handles those completed replacements.

## Build and extend

```sh
bash scripts/build.sh
```

The build needs Git, Bash 3.2+, `realpath`, and standard macOS/Linux utilities.
Destination machines need Bash and standard utilities, plus the application
whose configuration they install; they do not need Git or build tools.

```text
.vimrc, .tmux.conf        Editable dotfiles
installer/manifest.tsv   Explicit list of installable files
installer/install.sh     Installer source template
installer/restore.sh     Standalone restore source template
scripts/build.sh         Builds the self-contained installer and copies web assets
web/                     Browser assets, published under /web/
dist/                    Generated publish directory, ignored by Git
```

Add another newline-terminated text file and a tab-separated manifest row:

```text
# id    source         home-relative destination   validator   minimum version
extra   extra.conf     .config/example/config      none        -
```

Use actual tabs between the five fields. Paths are relative, contain only
letters, digits, `.`, `_`, `-`, and `/`, and cannot traverse parents or overlap
another destination. IDs are unique letters/digits/underscores/hyphens. Sources
must be regular text files without NUL bytes. `none` installs a generic file;
`vim` and `tmux` check minimum versions and load the candidate configuration in
an isolated process. Additional applications can get their own validator in
`installer/install.sh` and the corresponding build manifest check.

The build embeds only manifest-listed dotfiles. Git-tracked files under `web/`
are copied separately to `dist/web/`; add new web assets to Git before building.
They never enter the installer unless explicitly added to its manifest.
Rebuilding replaces the generated `dist/` directory, including removing stale
web assets. Do not edit or keep source files in `dist/`.

## Netlify

Connect this repository with `main` as the production branch and leave the base
directory blank. The committed `netlify.toml` sets:

- Build command: `bash scripts/build.sh`
- Publish directory: `dist`

A push to `main` builds a complete installer from that revision and publishes it
at `/install.sh`. Browser assets are served at `/web/<filename>`. `dist/` is
generated during the build, so it is not committed. No homepage is generated;
the root URL may return 404 while `/install.sh` works correctly.

## Validation

```sh
bash scripts/build.sh
shellcheck -s bash scripts/build.sh installer/install.sh installer/restore.sh dist/install.sh
python3 tests/test_installer.py
```

The integration tests use Python's standard library and real Vim/tmux binaries,
with temporary homes and a pseudo-terminal to exercise `cat install.sh | bash`.
They also simulate older/missing applications and installation failures. Tests
must not run against your real home directory. Minimum-version execution on
Vim 7.4 and tmux 2.1 remains a target-machine validation step; a version check
alone is not evidence that those old binaries were tested.
