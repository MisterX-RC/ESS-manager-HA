#!/bin/bash
#
# ESS Manager - sync & push
# ---------------------------------------------------------------------
# Double-click this file in Finder to:
#   1. Look in your Downloads folder for the newest
#      "ess-manager-ha-repo*.zip" (whatever Claude most recently sent you)
#   2. Copy its contents over this folder (leaving this script, this
#      folder's own git history, and its GitHub remote untouched)
#   3. Commit whatever changed
#   4. Push to GitHub
#
# This script must live INSIDE your ess-manager-ha folder (the one with
# the .git folder in it) - it finds everything else relative to itself.
# If that folder's GitHub remote is missing (e.g. a freshly unzipped
# folder that's never been pointed at GitHub before), this script adds it
# automatically rather than failing with "no configured push destination".
#
# First run: git will ask for your GitHub username and a personal access
# token once, in this Terminal window. After that, macOS Keychain
# remembers it and every future run is silent - no prompts.
# ---------------------------------------------------------------------

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
DOWNLOADS_DIR="$HOME/Downloads"
ZIP_PATTERN="ess-manager-ha-repo*.zip"
MARKER_FILE="$REPO_DIR/.last_synced_zip"

echo "== ESS Manager: sync & push =="
echo "Repo folder: $REPO_DIR"
cd "$REPO_DIR" || { echo "Could not find the repo folder - aborting."; read -r -p "Press Return to close..."; exit 1; }

if [ ! -d ".git" ]; then
  echo "This doesn't look like the ess-manager-ha git repo (no .git folder here)."
  echo "Move this script inside the ess-manager-ha folder and try again."
  read -r -p "Press Return to close..."
  exit 1
fi

# Once a push succeeds interactively, remember the credential in the Mac's
# own Keychain so future runs never have to ask again.
git config credential.helper osxkeychain

# Every zip is built from a repo with its GitHub remote deliberately
# removed (so an access token never ends up embedded in a shipped file),
# and rsync below never touches .git - so a folder that was never
# manually pointed at GitHub (or somehow lost that setting) would fail
# every single run with "No configured push destination" until someone
# ran `git remote add origin ...` by hand. Do that automatically instead.
REPO_URL="https://github.com/MisterX-RC/ESS-manager-HA.git"
if ! git remote get-url origin >/dev/null 2>&1; then
  echo "No 'origin' remote configured in this folder yet - adding it now ($REPO_URL)."
  git remote add origin "$REPO_URL"
fi

# --- find the newest matching zip in Downloads ----------------------------
LATEST_ZIP=""
LATEST_MTIME=0
while IFS= read -r -d '' f; do
  mtime=$(stat -f "%m" "$f")
  if [ "$mtime" -gt "$LATEST_MTIME" ]; then
    LATEST_MTIME="$mtime"
    LATEST_ZIP="$f"
  fi
done < <(find "$DOWNLOADS_DIR" -maxdepth 1 -iname "$ZIP_PATTERN" -print0 2>/dev/null)

if [ -n "$LATEST_ZIP" ]; then
  THIS_ZIP_ID="$LATEST_ZIP|$LATEST_MTIME"
  LAST_SYNCED=""
  [ -f "$MARKER_FILE" ] && LAST_SYNCED=$(cat "$MARKER_FILE")

  if [ "$THIS_ZIP_ID" != "$LAST_SYNCED" ]; then
    echo "Found update: $(basename "$LATEST_ZIP")"
    TMP_DIR=$(mktemp -d)
    if ! unzip -q "$LATEST_ZIP" -d "$TMP_DIR"; then
      echo "Could not unzip $LATEST_ZIP - aborting."
      rm -rf "$TMP_DIR"
      read -r -p "Press Return to close..."
      exit 1
    fi

    # The zip contains one top-level folder - copy ITS contents over this
    # repo, whatever it's named, skipping .git (keep this folder's own
    # history/remote) and this script itself.
    SRC_DIR=$(find "$TMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)
    if [ -z "$SRC_DIR" ]; then
      echo "Could not find a repo folder inside the zip - aborting."
      rm -rf "$TMP_DIR"
      read -r -p "Press Return to close..."
      exit 1
    fi

    rsync -a --delete \
      --exclude ".git" \
      --exclude "$SCRIPT_NAME" \
      --exclude ".last_synced_zip" \
      "$SRC_DIR"/ "$REPO_DIR"/

    rm -rf "$TMP_DIR"
    echo "$THIS_ZIP_ID" > "$MARKER_FILE"
    echo "Copied the update into this folder."
  else
    echo "Newest zip in Downloads was already synced - nothing new to copy in."
  fi
else
  echo "No ess-manager-ha-repo*.zip found in Downloads - just checking for anything to push."
fi

# --- commit whatever changed ----------------------------------------------
if [ -n "$(git status --porcelain)" ]; then
  git add -A
  git commit -m "Sync update $(date '+%Y-%m-%d %H:%M')"
  echo "Committed local changes."
else
  echo "Nothing changed to commit."
fi

# --- push -------------------------------------------------------------
# -u (re)sets the upstream tracking branch every time - harmless once it's
# already set, but required the first time origin gets added (whether
# that was done manually before, or automatically just above), otherwise
# a plain `git push` fails with an unrelated "no upstream branch" error.
echo "Pushing to GitHub..."
CURRENT_BRANCH="$(git branch --show-current)"
if git push -u origin "$CURRENT_BRANCH"; then
  echo "Done - pushed successfully."
else
  echo
  echo "Push failed - see the error above."
  echo "(If this is the very first run, git may have needed a username/token"
  echo "and none was entered in time - just run this script again.)"
fi

echo
read -r -p "Press Return to close this window..."
