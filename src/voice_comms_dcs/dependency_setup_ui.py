from __future__ import annotations

import argparse
import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from .dependency_manager import DependencyManager, DependencyPlan, validate_languages
from .model_manifest import build_model_manifest, write_model_manifest


class DependencySetupUi(tk.Tk):
    """Small post-install UI for downloading local AI models with progress."""

    def __init__(self, languages: tuple[str, ...], ollama_model: str, whisper_quality: str) -> None:
        super().__init__()
        self.title("Voice-Comms-DCS Model Setup")
        self.geometry("640x260")
        self.resizable(False, False)
        self.languages = languages
        self.ollama_model = ollama_model
        self.whisper_quality = whisper_quality
        self.events: queue.Queue[tuple[str, float | None, str]] = queue.Queue()
        self.failed = False

        root = ttk.Frame(self, padding=18)
        root.pack(fill=tk.BOTH, expand=True)

        ttk.Label(root, text="Voice-Comms-DCS Local Model Setup", font=("Segoe UI", 16, "bold")).pack(anchor=tk.W)
        ttk.Label(
            root,
            text="Downloading selected Ollama, Whisper.cpp and Piper models. This may take several minutes.",
        ).pack(anchor=tk.W, pady=(6, 14))

        self.status = tk.StringVar(value="Preparing...")
        self.detail = tk.StringVar(value=f"Languages: {', '.join(languages)}")
        ttk.Label(root, textvariable=self.status).pack(anchor=tk.W)
        ttk.Label(root, textvariable=self.detail).pack(anchor=tk.W, pady=(4, 8))

        self.progress = ttk.Progressbar(root, orient="horizontal", length=580, mode="determinate")
        self.progress.pack(anchor=tk.W, fill=tk.X)

        self.close_button = ttk.Button(root, text="Close", state=tk.DISABLED, command=self.destroy)
        self.close_button.pack(anchor=tk.E, pady=(18, 0))

        self.after(100, self._poll_events)
        threading.Thread(target=self._run_install, daemon=True).start()

    def _run_install(self) -> None:
        try:
            manager = DependencyManager(progress=lambda kind, percent, message: self.events.put((kind, percent, message)))
            manager.install(
                DependencyPlan(
                    languages=self.languages,
                    ollama_model=self.ollama_model,
                    whisper_quality=self.whisper_quality,
                )
            )
            self.events.put(("manifest", None, "Writing model checksum manifest..."))
            manifest = build_model_manifest(root=Path("."))
            write_model_manifest(manifest, Path("build_output/model_manifest.json"))
            self.events.put(("manifest", 100.0, "Model checksum manifest written."))
            self.events.put(("done", 100.0, "Setup complete."))
        except Exception as exc:
            self.failed = True
            self.events.put(("error", None, str(exc)))

    def _poll_events(self) -> None:
        while not self.events.empty():
            kind, percent, message = self.events.get_nowait()
            self.status.set(message)
            self.detail.set(kind)
            if percent is None:
                self.progress.configure(mode="indeterminate")
                self.progress.start(10)
            else:
                self.progress.stop()
                self.progress.configure(mode="determinate", value=max(0.0, min(100.0, percent)))
            if kind == "done":
                self.close_button.configure(state=tk.NORMAL)
                messagebox.showinfo("Voice-Comms-DCS", "Local model setup complete. Model checksum manifest written to build_output/model_manifest.json.")
            if kind == "error":
                self.close_button.configure(state=tk.NORMAL)
                messagebox.showerror("Voice-Comms-DCS", message)
        if self.close_button["state"] == tk.DISABLED:
            self.after(100, self._poll_events)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch the Voice-Comms-DCS model setup UI.")
    parser.add_argument("--languages", nargs="+", default=["en"], choices=["en", "zh", "ko", "fr", "ru", "es"])
    parser.add_argument("--ollama-model", default="qwen2.5:0.5b")
    parser.add_argument("--whisper-quality", choices=["tiny", "base"], default="base")
    args = parser.parse_args(argv)

    app = DependencySetupUi(
        languages=validate_languages(args.languages),
        ollama_model=args.ollama_model,
        whisper_quality=args.whisper_quality,
    )
    app.mainloop()
    return 1 if app.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
