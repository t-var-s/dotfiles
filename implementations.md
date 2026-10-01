# Installer and distribution decisions

The repository publishes a self-contained Bash installer and independent web
assets through Netlify. `main` supplies the latest successful deployment; there
is no release pin. The generated installer reports a Git revision, with a
`-dirty` suffix for changes to the installer templates, manifest, build script,
or manifest-listed payloads. Unrelated generated build-service files do not
affect the installer revision label.

`installer/manifest.tsv` is the explicit installation boundary. It maps IDs and
repository sources to paths below the current user's canonical home directory,
with an application validator and minimum version. Builds reject unsafe paths,
duplicate IDs, overlapping destinations, reserved backup paths, non-text files,
and heredoc delimiter collisions. Payloads use quoted heredocs and must end in
a newline; empty files are permitted.

The build publishes only its generated `dist/`. It stages output before replacing
the previous generated directory, validates canonical cleanup targets and
sentinels, and copies Git-tracked `web/` assets into a separate `/web/` namespace.
Remote installation needs no Git checkout or subsequent network request.

Netlify's ignore command compares `CACHED_COMMIT_REF` with `COMMIT_REF`, excluding
only the root `README.md`. A README-only change (or no effective change) skips
the build. Any other change, including new paths, triggers it. Missing references
or Git comparison failures explicitly return 1 so deployment can proceed.

The runtime targets Bash 3.2, Vim 7.4 and tmux 1.8. Vim settings guard clipboard
features and declare UTF-8 encoding. Version checks precede candidate validation.
Vim loads the candidate without user plugins, swap or viminfo; validation also
triggers Markdown settings. Tmux validation sources the candidate in its own
uniquely named server, then shuts down that server. Application validation is a
smoke test, not a proof of every interactive mapping or installed runtime build.

Netrw navigation uses `<Plug>NetrwLocalBrowseCheck` when available. Older netrw
releases, including v149, lack that action, so the Vim configuration copies the
buffer's native Enter mapping onto `l` before replacing Enter with search. The
copy resolves `<SID>` against netrw's original script ID so its private browsing
functions remain callable from the vimrc mapping.

Tmux checks its binary version with `tmux -V`, which does not connect to a server
still loading its startup configuration. It selects the unified 2.1+ mouse
setting or the four legacy mouse settings, and selects 1.8's empty `-c` argument
or 1.9+'s `pane_current_path` format. The centered
workspace uses a shell test of `window_panes`, percentage splits and pane swapping
instead of newer format comparisons, `if-shell -F` or `split-window -b`. It keeps
the original shell active in the middle, starts both margins in its directory,
and leaves existing multi-pane layouts alone. Proportions are approximate because
pane borders and integer cell widths affect rounding.

Each `if-shell` branch starts with `run-shell true`. The original 1.8 release
can free its conditional callback data before the job's cleanup accesses it
when a branch finishes synchronously. Yielding the branch through a shell job
avoids that lifetime bug without changing the resulting settings or layout.

Local validation on macOS exercised startup, reload, mouse options, pane
navigation, zoom, the single-pane guard and directory inheritance using both
tmux 3.7c and an uninstalled build of the original 1.8 release. The 1.8 build
used the bundled vis compatibility implementation and an explicit ARM Darwin
build target with the existing compiler and libraries. Target-machine checks
remain separate from this local runtime validation.

The installer is interactive, with prompts on `/dev/tty` and explicit opt-in for
each changed file followed by one final confirmation. No terminal means no
installation. The entry point appears after all generated functions/payloads,
reducing premature execution on interrupted piped downloads. Downloading to a
file and checking curl's exit status before execution is still stronger.

Symlink destinations/ancestors and non-file destinations are skipped. Existing
files are compared again after review and immediately before replacement to
catch intervening edits. This is not a filesystem transaction or protection
against a concurrently hostile process changing paths between checks.

All selected originals and installed snapshots are saved before replacement.
Files are individually replaced by same-directory renames. Existing permissions
are preserved; new dotfiles are private. Whole installations are not atomic:
if a later replacement fails, earlier replacements remain and can be restored.

Each backup run includes its own restore script and completion markers. Restore
compares current bytes with that run's installed snapshot and refuses to discard
later edits. It restores originals, moves newly created files into the backup,
and can resume partial restoration. It retains backup history and empty parent
directories. Subsequent updates should be undone newest first.

Stage one is local implementation and validation. Stage two is publishing through
the existing Git-connected Netlify project and exercising the served installer
on target machines, including actual minimum-version binaries. Browser toolbox
behavior can be developed independently under `web/`.
