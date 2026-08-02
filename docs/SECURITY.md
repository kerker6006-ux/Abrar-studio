# Security model

The application never embeds a Gemini API key in source code, project JSON, logs, or rendered files.

On Windows, the key is encrypted using Windows Data Protection API (DPAPI). The encrypted blob is tied to the current Windows account. A key pasted into chat or another public location must be revoked and replaced before use.

Voice files are cached using a SHA-256 key derived from the locked character profile, model, voice name, dialogue, and direction. The API key is not part of the hash.

Updates are accepted only when the GitHub release contains both `AbrarStudio-Setup.exe` and `AbrarStudio-Setup.exe.sha256`, and the SHA-256 digest matches before execution. Code signing is strongly recommended for public distribution.
