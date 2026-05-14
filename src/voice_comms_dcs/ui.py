from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .app import VoiceCommsService
from .config import AppConfig
from .stt import SttRuntimeError, VoskListener


class VoiceCommsUi(tk.Tk):
    """Simple Windows-friendly Tkinter UI for the voice bridge."""

    def __init__(self, config: AppConfig, config_path: str) -> None:
        super().__init__()
        self.title("Voice-Comms-DCS")
        self.geometry("760x480")
        self.minsize(680, 420)

        self.config_model = config
        self.config_path = config_path
        self.service = VoiceCommsService(config)
        self.listener: VoskListener | None = None

        self.status_var = tk.StringVar(value="Ready")
        self.connection_var = tk.StringVar(value=f"UDP target: {config.dcs_host}:{config.dcs_port}")
        self.last_transcript_var = tk.StringVar(value="-")
        self.last_match_var = tk.StringVar(value="-")
        self.listen_button_var = tk.StringVar(value="Start Listening")

        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(root, text="Voice-Comms-DCS", font=("Segoe UI", 18, "bold"))
        title.pack(anchor=tk.W)

        subtitle = ttk.Label(
            root,
            text="Speak configured phrases and dispatch deterministic UDP commands to DCS mission logic.",
        )
        subtitle.pack(anchor=tk.W, pady=(0, 12))

        status_frame = ttk.LabelFrame(root, text="Status", padding=12)
        status_frame.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(status_frame, textvariable=self.connection_var).pack(anchor=tk.W)
        ttk.Label(status_frame, text=f"Config: {self.config_path}").pack(anchor=tk.W)
        ttk.Label(status_frame, textvariable=self.status_var).pack(anchor=tk.W)

        controls = ttk.Frame(root)
        controls.pack(fill=tk.X, pady=(0, 12))

        ttk.Button(controls, textvariable=self.listen_button_var, command=self._toggle_listening).pack(
            side=tk.LEFT
        )
        ttk.Button(controls, text="Show Commands", command=self._show_commands).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        manual = ttk.LabelFrame(root, text="Manual Phrase Test", padding=12)
        manual.pack(fill=tk.X, pady=(0, 12))

        self.manual_entry = ttk.Entry(manual)
        self.manual_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.manual_entry.bind("<Return>", lambda _event: self._manual_dispatch())
        ttk.Button(manual, text="Send Test", command=self._manual_dispatch).pack(side=tk.LEFT, padx=(8, 0))

        recent = ttk.LabelFrame(root, text="Last Recognition", padding=12)
        recent.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(recent, text="Transcript:").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(recent, textvariable=self.last_transcript_var).grid(
            row=0, column=1, sticky=tk.W, padx=(8, 0)
        )
        ttk.Label(recent, text="Match:").grid(row=1, column=0, sticky=tk.W)
        ttk.Label(recent, textvariable=self.last_match_var).grid(
            row=1, column=1, sticky=tk.W, padx=(8, 0)
        )
        recent.columnconfigure(1, weight=1)

        log_frame = ttk.LabelFrame(root, text="Log", padding=12)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log = tk.Text(log_frame, height=8, wrap=tk.WORD, state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True)

    def _toggle_listening(self) -> None:
        if self.listener and self.listener.is_running:
            self.listener.stop()
            self.listen_button_var.set("Start Listening")
            self._set_status("Stopped")
            return

        if self.config_model.stt.engine != "vosk":
            messagebox.showerror("Unsupported STT Engine", "Only the Vosk backend is implemented in v0.1.")
            return

        def on_transcript(text: str) -> None:
            self.after(0, self._handle_transcript, text)

        def on_status(message: str) -> None:
            self.after(0, self._set_status, message)

        self.listener = VoskListener(
            self.config_model.stt,
            on_transcript=on_transcript,
            on_status=on_status,
        )
        try:
            self.listener.start()
        except SttRuntimeError as exc:
            messagebox.showerror("Speech Recognition Error", str(exc))
            self._append_log(str(exc))
            return

        self.listen_button_var.set("Stop Listening")
        self._set_status("Starting listener...")

    def _manual_dispatch(self) -> None:
        phrase = self.manual_entry.get().strip()
        if not phrase:
            return
        self._handle_transcript(phrase)
        self.manual_entry.delete(0, tk.END)

    def _handle_transcript(self, transcript: str) -> None:
        result = self.service.handle_transcript(transcript)
        self.last_transcript_var.set(result.transcript)

        if result.matched and result.match:
            match_text = (
                f"{result.match.command.id} via '{result.match.phrase}' "
                f"({result.match.confidence:.2f})"
            )
            self.last_match_var.set(match_text)
            self._append_log(f"MATCH {match_text} -> {result.payload}")
        else:
            self.last_match_var.set("No match")
            self._append_log(f"NO MATCH '{transcript}': {result.reason}")

    def _show_commands(self) -> None:
        lines: list[str] = []
        for command in self.config_model.commands:
            lines.append(f"{command.id}: {', '.join(command.phrases)}")
        messagebox.showinfo("Configured Commands", "\n\n".join(lines))

    def _set_status(self, message: str) -> None:
        self.status_var.set(f"Status: {message}")
        self._append_log(f"STATUS {message}")

    def _append_log(self, message: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, message + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _on_close(self) -> None:
        if self.listener and self.listener.is_running:
            self.listener.stop()
        self.service.close()
        self.destroy()
