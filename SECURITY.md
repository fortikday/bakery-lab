# Security

Bakery Lab is a local prototype. `serve.py` listens on `127.0.0.1` so the daily
log is accessible from the same computer. It has no user accounts or separation
between different people's data. Do not expose this server directly to the
internet or use it as a shared hosted service.

Daily records are stored in `local/waste-log.sqlite3`. Access to that file gives
access to the records. Keep the database, backups, exports, and credentials out
of public repositories and reports. Stop the app before copying the database
for a complete backup.

## Report a vulnerability privately

If the public repository has **Security → Report a vulnerability** enabled, use
that private reporting option. Include the affected version, the steps needed
to reproduce the issue, and its likely impact. Use fictional data and remove
credentials and personal information.

If private reporting is unavailable, open an issue asking the maintainers how
to contact them privately. Do not include the vulnerability's technical details,
an exploit, private bakery records, or secrets in that public request.

Ordinary bugs that do not expose data or create a security risk can use the
public bug-report form.
