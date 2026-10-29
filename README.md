# ezBooru

ezBooru is a cross-platform desktop client for browsing and downloading posts
from Danbooru, Gelbooru, Safebooru, and Moebooru-compatible sites.

## Run

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m ezbooru.main
```

On Linux, activate the environment with `source .venv/bin/activate` instead.

## Build a standalone Windows executable

From PowerShell in the project directory, run:

```powershell
.\build_exe.cmd
```

The script installs the optional PyInstaller build dependency into the active
project environment, converts the source icon in `assets\ezBooru.png` to a
Windows icon, and creates `dist\ezBooru.exe` with that icon. The one-file executable
bundles the Python runtime and application dependencies; Python does not need
to be installed on the target Windows computer. The first launch may take a
little longer while the bundled files are extracted. Build on Windows for a
Windows executable; PyInstaller does not cross-compile executables for other
operating systems.

The application uses qasync to run its Qt interface and asynchronous HTTP
requests on one event loop. Image bytes are cached in memory and on disk in the
platform's user cache directory. Danbooru and Moebooru requests use their
public JSON APIs; Gelbooru and Safebooru use their DAPI JSON endpoints.

## Search

Choose a site, enter space-separated tags, and select **Search**. Use `J` or
the down arrow and `K` or the up arrow to change the selected post. Press `S`
to save the selected post. In the viewer, use the mouse wheel to zoom and drag
to pan. **Download loaded posts** saves the current results using the editable
filename template; supported fields are `{id}`, `{artist}`, `{character}`,
`{rating}`, `{ext}`, and `{booru}`.

Batch downloads are bounded to four concurrent transfers. The GUI's `S` shortcut
and viewer Save action remain available for individual posts.

## Notes

Public API availability, rate limits, and post fields vary by site. The client
reports network, HTTP, and malformed-response errors in the status bar rather
than treating them as empty search results. Some API hosts can require an
account or API key; credentials are not currently configurable in the UI.
