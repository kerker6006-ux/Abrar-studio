# Publish Abrar Studio to GitHub

Target: `kerker6006-ux/Abrar-studio`

The connected GitHub app can see the repository but currently receives HTTP 403 for repository-content writes. In GitHub, open the installed ChatGPT/OpenAI GitHub app settings, grant this repository access, and ensure **Contents: Read and write** and **Actions: Read and write** are permitted.

The repository contains the complete, directly browsable source tree, including:

- `.github/workflows/windows-release.yml`
- `abrar_studio/`, `assets/`, `templates/`, `tests/`, and `scripts/`
- `VERIFICATION_REPORT.md`
- `README.md` and `gpt.md`

A push to `main` builds directly from the checked-out source, verifies `AbrarStudio-Setup.exe`, publishes a GitHub Release, and activates the app’s default update channel.
