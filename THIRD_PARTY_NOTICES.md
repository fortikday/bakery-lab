# Third-party notices

Bakery Lab's original code and documentation are covered by the root
[MIT licence](LICENSE). The following upstream material retains its own notice.

## Reduce Foodwaste Dataset

- Source: [Green AI Hub Mittelstand / Reduce-Foodwaste-Dataset](https://github.com/Green-AI-Hub-Mittelstand/Reduce-Foodwaste-Dataset).
- Snapshot: commit `3bde2d0f9b256ffc800932ac8574a695909f59a5`.
- Included files: `data/train.csv`, `data/README.md`, and `data/LICENSE`.
- Upstream copyright: 2025 Green-AI Hub Mittelstand.
- Licence: MIT; the complete upstream notice is preserved in [data/LICENSE](data/LICENSE).
- Retrieval details and file checksums: [data/source.json](data/source.json).

Generated forecast results, notebook charts, and the sales dashboard use this
bundled dataset. Keep the upstream licence and attribution when redistributing
the dataset or these derived results.

Optional Python dependencies are installed separately from their package
registries. Their licences remain with those packages; Bakery Lab's licence
does not replace them. No third-party JavaScript, font files, or downloaded
image assets are bundled with the app.

## Portable Windows preview

The separately built Windows package includes CPython 3.12.14, SQLite 3.53.1,
OpenSSL 3.5.8, and their Windows runtime support files. These components keep
their upstream licences; the project MIT licence covers Bakery Lab's own code.
The package includes the Python notice and the OpenSSL Apache 2.0 licence in
its `licenses/` folder. Copies for this build are kept in
`packaging/licenses/` in the source project.

Python: <https://www.python.org/>. OpenSSL licence source:
<https://github.com/openssl/openssl/blob/openssl-3.5.8/LICENSE.txt>.
SQLite: <https://sqlite.org/copyright.html>. Microsoft runtime support files
retain their Microsoft notices and are not relicensed by Bakery Lab.

The executable is built with unmodified PyInstaller 6.22.3. Its distribution
exception permits application bundles under their own applicable licences:
<https://pyinstaller.org/en/stable/license.html>. Tk is excluded from this
portable build; the optional source desktop window can use a locally installed Tk.
