# Build the portable Windows app

The portable app includes Python, SQLite, and the two browser pages.
It does not bundle the optional ML packages. Build it on Windows using
Python 3.11 or newer; building on another operating system does not create a
Windows executable.

From the project root:

```powershell
python -m venv .build-venv
.\.build-venv\Scripts\python -m pip install -r packaging/requirements-build.txt
.\.build-venv\Scripts\python -m PyInstaller --distpath dist --workpath build packaging/BakeryLab.spec
```

The complete app is `dist/BakeryLab/`. Keep `BakeryLab.exe` and its `_internal/`
support folder together. Add the project licence, third-party notices, bakery
guide, and applicable bundled Python/Tcl/Tk licence notices before distributing
a ZIP. Do not include any database, recovery copy, local configuration, or
test data in that ZIP.

The portable build uses a simple running window and opens the browser. Tk is
excluded so the build does not depend on the build machine's desktop toolkit.
Keep the running window open while using Bakery Lab; close it when finished.
The optional source desktop window still uses Tk when it is installed correctly.

The packaged app keeps data in
`%LOCALAPPDATA%\BakeryLab\local\waste-log.sqlite3`. Replacing the portable
application folder does not replace this database. Source mode keeps its data
in the project `local/` folder instead. Upgrading from source to the portable
app does not automatically migrate those records; recover a full backup using
the bakery guide.

Run the packaged backend smoke check with explicitly isolated paths:

```powershell
dist\BakeryLab\BakeryLab.exe --check --db C:\path\to\test.sqlite3 --check-output C:\path\to\check.json
```

Use real absolute paths in a test folder. This mode opens no desktop window or
browser, and it checks the bundled pages, local configuration, and SQLite
backup download. Review the JSON result and process exit code. It does not
verify the visual layout or interactive behaviour of the desktop window.

Portable builds made with these instructions are unsigned unless a distributor
adds their own signing process. Do not describe them as code-signed, reviewed
by Microsoft, or tested on operating systems that have not been checked.
