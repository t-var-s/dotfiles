# Source template: scripts/build.sh appends the manifest, payloads and main call.
# Bash 3.2 compatible. Prompts use fd 3, never the pipe carrying the script.

say() { printf '%s\n' "$*"; }
die() { say "Error: $*" >&2; exit 1; }
ask() {
  local answer
  while :; do
    printf '%s [y/N]: ' "$1" >&3
    IFS= read -r answer <&3 || return 1
    case "$answer" in y|Y|yes|YES) return 0 ;; ''|n|N|no|NO) return 1 ;; esac
    printf 'Please enter y or n.\n' >&3
  done
}

# Reject symlinks in the destination and all parents below the canonical HOME.
safe_destination() {
  local relative=$1 current=$target_home part
  while [ -n "$relative" ]; do
    part=${relative%%/*}
    if [ "$relative" = "$part" ]; then relative=''; else relative=${relative#*/}; fi
    current="$current/$part"
    [ ! -L "$current" ] || return 1
    if [ -n "$relative" ]; then
      [ ! -e "$current" ] || [ -d "$current" ] || return 1
    else
      [ ! -e "$current" ] || [ -f "$current" ] || return 1
    fi
  done
}

version_at_least() {
  local actual=$1 minimum=$2 major minor required_major required_minor
  [[ "$actual" =~ ^([0-9]+)\.([0-9]+) ]] || return 1
  major=$((10#${BASH_REMATCH[1]})); minor=$((10#${BASH_REMATCH[2]}))
  required_major=${minimum%%.*}; required_minor=${minimum#*.}
  [ "$major" -gt "$required_major" ] ||
    { [ "$major" -eq "$required_major" ] && [ "$minor" -ge "$required_minor" ]; }
}

check_application() {
  local validator=$1 minimum=$2 output version
  [ "$validator" != none ] || return 0
  if ! command -v "$validator" >/dev/null 2>&1; then say "  Skipped: $validator is not installed."; return 1; fi
  case "$validator" in
    vim) output=$(vim --version) || return 1
         version=$(printf '%s\n' "$output" | sed -n '1s/.*IMproved \([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p') ;;
    tmux) output=$(tmux -V) || return 1; version=${output#tmux } ;;
  esac
  if ! version_at_least "$version" "$minimum"; then
    say "  Skipped: $validator ${version:-unknown} found; requires $minimum or newer."
    return 1
  fi
  say "  $validator $version (minimum $minimum)"
}

validate_config() {
  local validator=$1 candidate=$2 log=$3 result=0
  case "$validator" in
    none) return 0 ;;
    vim)
      # No user plugins, swap, viminfo or interaction with an existing editor.
      # shellcheck disable=SC2016 # Vim expands its own $VIMRUNTIME.
      vim -N -n -i NONE --noplugin -es -V1 -u "$candidate" \
        --cmd 'set runtimepath=$VIMRUNTIME' \
        -c 'setfiletype markdown' -c 'qa!' >"$log" 2>&1 || result=$?
      ;;
    tmux)
      # Start empty, then explicitly source: startup errors alone may exit zero.
      # -L avoids Unix socket path length limits on macOS temporary directories.
      tmux_socket="dotfiles-check-$$-${RANDOM}-${RANDOM}"
      TMUX='' tmux -L "$tmux_socket" -f /dev/null new-session -d -s dotfiles-check \
        'exec sleep 30' >"$log" 2>&1 || result=$?
      if [ "$result" -eq 0 ]; then
        TMUX='' tmux -L "$tmux_socket" source-file "$candidate" >>"$log" 2>&1 || result=$?
      fi
      TMUX='' tmux -L "$tmux_socket" kill-server >/dev/null 2>&1 || :
      tmux_socket=''
      ;;
  esac
  if [ "$result" -ne 0 ]; then
    say "  Skipped: $validator could not validate this configuration."
    cat "$log"
    return 1
  fi
}

cleanup() {
  local status=$?
  trap - EXIT
  if [ -n "$tmux_socket" ]; then TMUX='' tmux -L "$tmux_socket" kill-server >/dev/null 2>&1 || :; fi
  # These are known generated files, not recursive deletion targets.
  if [ -n "$pending_file" ]; then rm -f "$pending_file"; fi
  if [ -n "$run_tmp" ] && [ -f "$run_tmp/.codex-task-temp" ]; then
    local id _source destination validator minimum
    if [ -f "$run_tmp/manifest.tsv" ]; then
      while IFS=$'\t' read -r id _source destination validator minimum; do
        rm -f "$run_tmp/$id.payload" "$run_tmp/$id.before" "$run_tmp/$id.log"
      done < "$run_tmp/manifest.tsv"
    fi
    rm -f "$run_tmp/manifest.tsv" "$run_tmp/selected.tsv" "$run_tmp/.codex-task-temp"
    rmdir "$run_tmp" || say "Temporary files remain at: $run_tmp" >&2
  fi
  if [ "$status" -ne 0 ] && [ -n "$backup_run" ]; then
    printf 'Installation stopped. Restore completed replacements with:\n  bash %q\n' "$backup_run/restore.sh" >&2
  fi
  exit "$status"
}

main() {
  set -eu
  set -o pipefail
  umask 077
  run_tmp=''; pending_file=''; backup_run=''; tmux_socket=''
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM HUP
  [ "$#" -eq 0 ] || die 'Run without arguments; installation is interactive.'
  if ! { exec 3<>/dev/tty; } 2>/dev/null; then
    die 'An interactive terminal is required. Over SSH, allocate one with ssh -t.'
  fi
  [ -n "${HOME:-}" ] && [ -d "$HOME" ] || die 'HOME must be an existing directory.'
  target_home=$(cd "$HOME" && pwd -P)
  [ "$target_home" != / ] && [ -w "$target_home" ] || die 'HOME must be writable and must not be /.'
  export LC_ALL=C
  say "Dotfiles revision: $DOTFILES_REVISION"
  say "System: $(uname -s) $(uname -r)"
  say "Destination: $target_home"
  say 'Installs configuration only. Existing files are backed up; local edits are replaced only with confirmation.'
  say 'The Vim leader key is ç; use a UTF-8 terminal for the mappings.'

  local temp_base=${TMPDIR:-/tmp}
  run_tmp=$(mktemp -d "${temp_base%/}/codex-dotfiles-install.XXXXXX")
  touch "$run_tmp/.codex-task-temp"
  write_manifest > "$run_tmp/manifest.tsv"
  : > "$run_tmp/selected.tsv"
  local id _source destination validator minimum candidate target had_original count=0 diff_status
  while IFS=$'\t' read -r id _source destination validator minimum; do
    say ""
    say "$id -> ~/$destination"
    if ! safe_destination "$destination"; then say '  Skipped: symlink or non-file in destination path.'; continue; fi
    if ! check_application "$validator" "$minimum"; then continue; fi
    candidate="$run_tmp/$id.payload"
    target="$target_home/$destination"
    write_payload "$id" > "$candidate"
    if [ -f "$target" ] && cmp -s "$target" "$candidate"; then say '  Already up to date.'; continue; fi
    if ! validate_config "$validator" "$candidate" "$run_tmp/$id.log"; then continue; fi
    had_original=no
    if [ -f "$target" ]; then
      if [ ! -r "$target" ] || [ ! -w "$target" ]; then
        say '  Skipped: existing file is unreadable or read-only.'
        continue
      fi
      cp -p "$target" "$run_tmp/$id.before"
      had_original=yes
      say '  Existing file differs.'
      if ask 'Show differences?'; then
        diff_status=0
        diff -u "$run_tmp/$id.before" "$candidate" || diff_status=$?
        [ "$diff_status" -le 1 ] || die 'Could not compare files.'
      fi
    else
      say '  File is missing.'
    fi
    if ask "Include $id in this installation?"; then
      printf '%s\t%s\t%s\n' "$id" "$destination" "$had_original" >> "$run_tmp/selected.tsv"
      count=$((count + 1))
    fi
  done < "$run_tmp/manifest.tsv"
  if [ "$count" -eq 0 ]; then say 'Nothing selected; no configuration changes.'; return; fi
  say ""
  say "Ready to install $count file(s):"
  while IFS=$'\t' read -r id destination had_original; do say "  ~/$destination"; done < "$run_tmp/selected.tsv"
  if ! ask 'Back up existing files and install the selection?'; then say 'Cancelled; no configuration changes.'; return; fi

  # Recheck every destination after interactive review and before any backups.
  while IFS=$'\t' read -r id destination had_original; do
    safe_destination "$destination" || die "Destination changed: $destination"
    target="$target_home/$destination"
    if [ "$had_original" = yes ]; then
      cmp -s "$target" "$run_tmp/$id.before" || die "File changed during review: $destination. Run again."
    else
      [ ! -e "$target" ] || die "File appeared during review: $destination. Run again."
    fi
  done < "$run_tmp/selected.tsv"
  [ ! -L "$target_home/.dotfiles-backups" ] || die 'Backup directory must not be a symlink.'
  mkdir -p "$target_home/.dotfiles-backups"
  backup_run=$(mktemp -d "$target_home/.dotfiles-backups/run-$(date -u +%Y%m%dT%H%M%SZ).XXXXXX")
  mkdir "$backup_run/originals" "$backup_run/installed" "$backup_run/completed" "$backup_run/restored" "$backup_run/removed"
  cp "$run_tmp/selected.tsv" "$backup_run/manifest.tsv"
  printf '%s\n' "$DOTFILES_REVISION" > "$backup_run/revision"
  {
    printf '#!/bin/bash\ntarget_home=%q\n' "$target_home"
    write_restore
  } > "$backup_run/restore.sh"

  # Finish preparing all backups before replacing the first configuration.
  while IFS=$'\t' read -r id destination had_original; do
    if [ "$had_original" = yes ]; then cp -p "$run_tmp/$id.before" "$backup_run/originals/$id"; fi
    cp "$run_tmp/$id.payload" "$backup_run/installed/$id"
  done < "$run_tmp/selected.tsv"
  while IFS=$'\t' read -r id destination had_original; do
    safe_destination "$destination" || die "Destination changed: $destination"
    target="$target_home/$destination"
    if [ "$had_original" = yes ]; then
      cmp -s "$target" "$run_tmp/$id.before" || die "File changed before replacement: $destination"
    else
      [ ! -e "$target" ] || die "File appeared before replacement: $destination"
    fi
    mkdir -p "$(dirname "$target")"
    pending_file=$(mktemp "$(dirname "$target")/.dotfiles-install.XXXXXX")
    # Retain existing permissions; new dotfiles are private (0600).
    if [ "$had_original" = yes ]; then cp -p "$run_tmp/$id.before" "$pending_file"; fi
    cat "$run_tmp/$id.payload" > "$pending_file"
    # A completion marker before rename makes interruption recoverable; restore
    # also checks the bytes and safely skips a rename that never happened.
    touch "$backup_run/completed/$id"
    mv -f "$pending_file" "$target"
    pending_file=''
    say "Installed ~/$destination"
  done < "$run_tmp/selected.tsv"
  say ""
  printf 'Restore this installation with:\n  bash %q\n' "$backup_run/restore.sh"
  say 'Fetch and run the installer again to update. Existing Vim/tmux sessions were not reloaded.'
}
