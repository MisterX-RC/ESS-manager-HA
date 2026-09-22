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
#   5. Publish a matching GitHub Release (tag vX.Y.Z, from manifest.json)
#      if one doesn't already exist - HACS's own docs are explicit that a
#      plain git tag alone isn't enough for it to notice an update, it
#      needs an actual Release, so this is what makes the version bump
#      above actually show up as an update in HACS
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
PUSH_OK=true
if git push -u origin "$CURRENT_BRANCH"; then
  echo "Pushed successfully."
else
  PUSH_OK=false
  echo
  echo "Push failed - see the error above."
  echo "(If this is the very first run, git may have needed a username/token"
  echo "and none was entered in time - just run this script again.)"
fi

# --- cut a GitHub Release for this version, if there isn't one yet -------
# A bare git tag is NOT enough for HACS to detect an update - its own docs
# say so directly ("Just publishing tags is not enough, you need to
# publish releases"). So instead of `git tag` + `git push --tags`, this
# calls the GitHub REST API to create an actual Release, which brings its
# own tag along automatically. It reuses the same personal access token
# macOS Keychain already saved for the git push above (read via `git
# credential fill`, the same mechanism git itself uses), so there's
# nothing new to type in.
if [ "$PUSH_OK" = true ]; then
  VERSION=$(grep -m1 '"version"' custom_components/ess_manager/manifest.json | sed -E 's/.*"version": *"([^"]+)".*/\1/')
  if [ -z "$VERSION" ]; then
    echo "Could not read a version out of manifest.json - skipping the release."
  else
    TAG="v$VERSION"
    echo "Checking GitHub for a $TAG release..."
    CRED_OUTPUT=$(printf 'protocol=https\nhost=github.com\n' | git credential fill 2>/dev/null)
    GH_TOKEN_FOR_API=$(printf '%s\n' "$CRED_OUTPUT" | sed -n 's/^password=//p')

    if [ -z "$GH_TOKEN_FOR_API" ]; then
      echo "Could not retrieve a saved GitHub token from Keychain to cut a release - skipping."
      echo "(Code was still pushed above; you can draft the $TAG release by hand on GitHub if you want HACS to see it sooner.)"
    else
      EXISTING_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $GH_TOKEN_FOR_API" \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/MisterX-RC/ESS-manager-HA/releases/tags/$TAG")

      if [ "$EXISTING_STATUS" = "200" ]; then
        echo "Release $TAG already exists on GitHub - nothing to do."
      else
        RELEASE_RESPONSE="$(mktemp)"
        CREATE_STATUS=$(curl -s -o "$RELEASE_RESPONSE" -w "%{http_code}" \
          -X POST \
          -H "Authorization: Bearer $GH_TOKEN_FOR_API" \
          -H "Accept: application/vnd.github+json" \
          "https://api.github.com/repos/MisterX-RC/ESS-manager-HA/releases" \
          -d "{\"tag_name\":\"$TAG\",\"name\":\"$TAG\",\"target_commitish\":\"$CURRENT_BRANCH\",\"body\":\"See CHANGELOG.md for details on this release.\",\"draft\":false,\"prerelease\":false}")

        if [ "$CREATE_STATUS" = "201" ]; then
          echo "Published GitHub release $TAG."
          echo "HACS checks custom repos roughly every 6h and at HA startup - or use HACS's own 'Redownload'/'Update information' to see it right now."
        else
          echo "Could not create release $TAG (HTTP $CREATE_STATUS):"
          cat "$RELEASE_RESPONSE"
          echo
          echo "(Code was still pushed above. A common cause is a saved token"
          echo "that's missing the 'repo' scope needed to create releases -"
          echo "you can draft the $TAG release by hand on GitHub instead.)"
        fi
        rm -f "$RELEASE_RESPONSE"
      fi
    fi
  fi
fi

echo
read -r -p "Press Return to close this window..."
