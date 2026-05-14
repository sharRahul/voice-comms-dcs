# Model integrity

Voice-Comms-DCS downloads local AI assets for Whisper.cpp and Piper, but it must not silently trust model binaries.

## SHA256 verification

Model specs can carry SHA256 values:

- `WhisperModelSpec.sha256`
- `PiperVoiceSpec.model_sha256`
- `PiperVoiceSpec.config_sha256`

When a SHA256 is configured, the dependency manager verifies the downloaded `.part` file before promoting it to the final model path. A mismatch deletes the partial file and raises an error.

## Missing hashes

Some upstream model URLs do not publish a stable checksum in this repository yet. Those specs intentionally use `None` rather than fake hashes. The downloader emits a visible warning when a model is downloaded without a configured SHA256.

Use `config/model_hashes.example.json` as the review template for collecting trusted hashes. A release engineer should generate a model manifest from a trusted download, review the source, and then pin the expected hashes in code or a reviewed manifest file.

## HTTP resume safety

Interrupted downloads use `.part` files and HTTP Range requests. If the server returns HTTP 416:

- a `.part` file is promoted only when a configured SHA256 matches;
- without a SHA256, the partial file is discarded and the download restarts from byte 0;
- with a mismatched SHA256, the partial file is discarded and the download restarts safely.

## Ownership manifest

Successful Voice-Comms-DCS model downloads are recorded in:

```text
models/.voice-comms-dcs-installed.json
```

Uninstall only removes files listed in that manifest. Custom or manually downloaded `models/whisper/ggml-*.bin` files are not deleted.
