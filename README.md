# qobuz-strawberry-sync
This is a small CLI tool for syncing playlists from your Qobuz account into Strawberry. It uses the credentials you've already provided in Strawberry to do this, so no additional setup is needed.

This script only works on the Linux version of Strawberry, users on other platforms should just use the official app.

# Usage
```bash
uv sync
uv run sync.py
```

That's it, the script will attempt to autodetect both your Strawberry configurationa and the database.
