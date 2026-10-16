#!/bin/bash
# start_mac.command - double-click to run the website on a Mac.
# If macOS blocks it: right-click the file -> Open -> Open.
cd "$(dirname "$0")" || exit 1
echo "=== Blinkit Sales Portal - starting up ==="
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 not found. Install it from python.org, then try again."; read -r -p "Press Enter to close"; exit 1
fi
python3 --version
[ -x venv/bin/python ] || { echo "Creating the project environment - first run only..."; python3 -m venv venv || exit 1; }
echo "Checking libraries - the first run takes 1 to 2 minutes..."
venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt || { read -r -p "Install failed. Screenshot this window. Press Enter"; exit 1; }
[ -f .env ] || cp .env.example .env
echo "Checking the database..."
venv/bin/python seed.py --ensure || { read -r -p "Database setup failed. Screenshot this window. Press Enter"; exit 1; }
echo
echo "Website: http://127.0.0.1:5000   Staff: http://127.0.0.1:5000/admin/login"
echo "KEEP THIS WINDOW OPEN. Press Ctrl+C to stop."
( sleep 4; open "http://127.0.0.1:5000" 2>/dev/null ) &
venv/bin/python app.py
