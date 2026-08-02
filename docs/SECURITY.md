# Security model

The application never embeds a Gemini API key in source code, project JSON, logs, or rendered files.

On Windows, the key is encrypted using Windows Data Protection API (DPAPI). The encrypted blob is tied to the current Windows account. A key pasted into chat or another public location must be revoked and replaced before use.

Voice files are cached using a SHA-256 key derived from the locked character profile, model, voice name, dialogue, and direction. The API key is not part of the hash.

Updates are accepted only when the GitHub release contains both `AbrarStudio-Update.zip` and `AbrarStudio-Update.zip.sha256`. The app verifies the SHA-256 digest, rejects unsafe ZIP paths, waits for the running app to close, replaces only installed program files, and restarts. Code signing is strongly recommended for public distribution.
