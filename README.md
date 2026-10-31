# ezBooru

ezBooru is a cross-platform desktop client for browsing and downloading posts
from Danbooru, Gelbooru, Safebooru, and Moebooru-compatible sites!!!!!!! >.<

![stupid ahh icon </3](assets/ezBooru.png)


## Run
You can download the executable file from releases!! mwahhh <3
OR do this!

Python 3.11 or newer is required!!!

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m ezbooru.main
```


On macOS or Linux, activate the environment with `source .venv/bin/activate`
instead!!!!!!!

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
operating systems!

The application uses qasync to run its Qt interface and asynchronous HTTP
requests on one event loop. Image bytes are cached in memory and on disk in the
platform's user cache directory. Danbooru and Moebooru requests use their
public JSON APIs; Gelbooru and Safebooru use their DAPI JSON endpoints!

## Build a macOS app

On a Mac, run:

```bash
python3 -m venv .venv
source .venv/bin/activate
bash build_macos.sh
```

The script uses macOS `sips` and `iconutil` to make the app icon and PyInstaller
to create `dist/ezBooru.app`. Build the bundle on macOS; Windows and macOS
artifacts must each be built on their target operating system.

The application uses qasync to run its Qt interface and asynchronous HTTP
requests on one event loop. Image bytes are cached in memory and on disk in the
platform's user cache directory. Danbooru and Moebooru requests use their
public JSON APIs; Gelbooru and Safebooru use their DAPI JSON endpoints!

## Search

Choose a site, enter space-separated tags, and select **Search**. The sidebar
also provides artist-tag search, persistent saved searches, favorites,
blacklisted tags, and a configurable download folder. Posts matching any
blacklisted tag are filtered from search results and bulk downloads. **Download
all matching** fetches every page for the current search and asks for
confirmation first. Use `J` or
the down arrow and `K` or the up arrow to change the selected post. Press `S`
to save the selected post. In the viewer, use the mouse wheel to zoom and drag
to pan. **Download loaded posts** saves the current results using the editable
filename template; supported fields are `{id}`, `{artist}`, `{character}`,
`{rating}`, `{ext}`, and `{booru}`!

Batch downloads are bounded to four concurrent transfers. The GUI's `S` shortcut
and viewer Save action remain available for individual posts!

## Notes

Public API availability, rate limits, and post fields vary by site. The client
reports network, HTTP, and malformed-response errors in the status bar rather
than treating them as empty search results. Some API hosts can require an
account or API key; credentials are not currently configurable in the UI!
    