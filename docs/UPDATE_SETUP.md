# Update publishing

1. Build on Windows x64 with Python 3.11+, PyInstaller, and Inno Setup 6 by running `scripts\build_windows.ps1`.
2. Publish a non-draft, non-prerelease GitHub Release tagged with a newer semantic version such as `v3.0.2`.
3. Upload the four files created in `release`:
   - `AbrarStudio-Setup.exe` and `AbrarStudio-Setup.exe.sha256` for first-time installation and compatibility with version 3.0.0;
   - `AbrarStudio-Update.zip` and `AbrarStudio-Update.zip.sha256` for in-place updates.
4. Abrar Studio checks `kerker6006-ux/Abrar-studio` automatically at startup. The repository can still be changed in Settings.
5. When a newer version exists, the app downloads the update ZIP, verifies its SHA-256 checksum and ZIP paths, closes, replaces its program files, and reopens.

Settings, encrypted credentials, projects, renders and cached voices live outside the installation directory and are preserved. Users install once; releases after 3.0.1 use the in-place updater.
