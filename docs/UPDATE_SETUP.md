# Update publishing

1. Build on a Windows x64 computer with Python 3.11+, PyInstaller, and Inno Setup 6 by running `scripts\build_windows.ps1`.
2. Create a public or private GitHub repository and publish a non-draft, non-prerelease release tagged with a semantic version such as `v0.2.0`.
3. Upload both files from `release`:
   - `AbrarStudio-Setup.exe`
   - `AbrarStudio-Setup.exe.sha256`
4. Enter the GitHub owner and repository names in the application's Settings page.
5. Future versions will be detected through GitHub's latest-release endpoint. The installer is downloaded, SHA-256 verified, and then launched silently.

The framework is implemented, but automatic updates cannot operate until a real release repository is configured and installers are published there.
