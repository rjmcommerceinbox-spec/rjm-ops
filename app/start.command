#!/bin/bash
# Double-click to start the RJM Amazon app. Close this window to stop it.
cd "$(dirname "$0")" || exit 1
if ! /usr/bin/python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
  echo "Python 3 is needed. macOS will now offer to install Apple's Command Line Tools - click Install,"
  echo "wait for it to finish, then double-click start.command again."
  xcode-select --install 2>/dev/null
  read -r -p "Press Return to close."
  exit 1
fi
(sleep 1.5; open "http://127.0.0.1:8765") &
/usr/bin/python3 server.py
