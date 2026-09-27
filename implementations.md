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

The runtime targets Bash 3.2, Vim 7.4 and tmux 2.1. Vim settings guard clipboard
features and declare UTF-8 encoding. Version checks precede candidate validation.
Vim loads the candidate without user plugins, swap or viminfo; validation also
triggers Markdown settings. Tmux validation sources the candidate in its own
uniquely named server, then shuts down that server. Application validation is a
smoke test, not a proof of every interactive mapping or installed runtime build.

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
