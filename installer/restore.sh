# Embedded in each backup run; target_home is written by the installer.
# shellcheck disable=SC2154
set -eu
set -o pipefail
umask 077
backup_run=$(cd "$(dirname "$0")" && pwd -P)
pending_file=''
trap 'if [ -n "$pending_file" ]; then rm -f "$pending_file"; fi' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
fail() { printf 'Restore error: %s\n' "$*" >&2; exit 1; }
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
if ! { exec 3<>/dev/tty; } 2>/dev/null; then fail 'An interactive terminal is required.'; fi
[ -d "$target_home" ] && [ ! -L "$target_home" ] || fail 'Original home directory is unavailable or has become a symlink.'

# Assess all paths before changing any. A later local edit stops restoration.
count=0
while IFS=$'\t' read -r id destination had_original; do
  [ -f "$backup_run/completed/$id" ] && [ ! -f "$backup_run/restored/$id" ] || continue
  safe_destination "$destination" || fail "Unsafe destination: $destination"
  target="$target_home/$destination"
  if [ "$had_original" = yes ] && cmp -s "$target" "$backup_run/originals/$id"; then continue; fi
  if [ "$had_original" = no ] && [ ! -e "$target" ]; then continue; fi
  cmp -s "$target" "$backup_run/installed/$id" || fail "$destination changed since installation. Preserve or reconcile your edits before restoring."
  printf 'Restore ~/%s\n' "$destination"
  count=$((count + 1))
done < "$backup_run/manifest.tsv"
if [ "$count" -eq 0 ]; then printf 'Nothing to restore.\n'; exit 0; fi
printf 'Restore %s file(s)? [y/N]: ' "$count" >&3
IFS= read -r answer <&3 || exit 0
case "$answer" in y|Y|yes|YES) ;; *) printf 'Cancelled.\n'; exit 0 ;; esac

while IFS=$'\t' read -r id destination had_original; do
  [ -f "$backup_run/completed/$id" ] && [ ! -f "$backup_run/restored/$id" ] || continue
  safe_destination "$destination" || fail "Unsafe destination: $destination"
  target="$target_home/$destination"
  if [ "$had_original" = yes ] && cmp -s "$target" "$backup_run/originals/$id"; then continue; fi
  if [ "$had_original" = no ] && [ ! -e "$target" ]; then continue; fi
  cmp -s "$target" "$backup_run/installed/$id" || fail "$destination changed during review."
  if [ "$had_original" = yes ]; then
    pending_file=$(mktemp "$(dirname "$target")/.dotfiles-restore.XXXXXX")
    cp -p "$backup_run/originals/$id" "$pending_file"
    mv -f "$pending_file" "$target"
    pending_file=''
  else
    # Move newly installed files into the backup instead of deleting them.
    mv "$target" "$backup_run/removed/$id"
  fi
  touch "$backup_run/restored/$id"
  printf 'Restored ~/%s\n' "$destination"
done < "$backup_run/manifest.tsv"
printf 'Restoration complete. Backups remain at %s\n' "$backup_run"
