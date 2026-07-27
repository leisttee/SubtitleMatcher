import customtkinter as ctk
from tkinter import filedialog
from pathlib import Path

from scanner import scan_videos, scan_subtitles
from matcher import find_matches
from copier import copy_matches


class SubtitleMatcherUI(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("SubtitleMatcher")
        self.geometry("800x600")

        self.video_folder = ""
        self.subtitle_folder = ""
        self.matches = []

        # Resources
        base_dir = Path(__file__).resolve().parent.parent

        icon_path = base_dir / "resources" / "icon.ico"

        if icon_path.exists():
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        # Title
        self.title_label = ctk.CTkLabel(
            self,
            text="SubtitleMatcher",
            font=("Segoe UI", 24, "bold")
        )
        self.title_label.pack(pady=20)

        # Video folder
        self.video_button = ctk.CTkButton(
            self,
            text="Select Video Folder",
            command=self.select_video_folder
        )
        self.video_button.pack(pady=10)

        self.video_label = ctk.CTkLabel(
            self,
            text="No video folder selected"
        )
        self.video_label.pack()

        # Subtitle folder
        self.subtitle_button = ctk.CTkButton(
            self,
            text="Select Subtitle Folder",
            command=self.select_subtitle_folder
        )
        self.subtitle_button.pack(pady=10)

        self.subtitle_label = ctk.CTkLabel(
            self,
            text="No subtitle folder selected"
        )
        self.subtitle_label.pack()

        # Scan button
        self.scan_button = ctk.CTkButton(
            self,
            text="Scan Files",
            command=self.scan_files
        )
        self.scan_button.pack(pady=20)

        # Match & Copy button
        self.copy_button = ctk.CTkButton(
            self,
            text="Match & Copy",
            command=self.match_and_copy
        )
        self.copy_button.pack(pady=5)

        # Results
        self.result_box = ctk.CTkTextbox(
            self,
            width=700,
            height=300
        )
        self.result_box.pack(
            pady=10,
            padx=20,
            fill="both",
            expand=True
        )

    def select_video_folder(self):
        folder = filedialog.askdirectory()

        if folder:
            self.video_folder = folder
            self.video_label.configure(text=folder)

    def select_subtitle_folder(self):
        folder = filedialog.askdirectory()

        if folder:
            self.subtitle_folder = folder
            self.subtitle_label.configure(text=folder)

    def scan_files(self):

        self.result_box.delete("1.0", "end")

        if not self.video_folder:
            self.result_box.insert(
                "end",
                "Select video folder first\n"
            )
            return

        if not self.subtitle_folder:
            self.result_box.insert(
                "end",
                "Select subtitle folder first\n"
            )
            return

        videos = scan_videos(self.video_folder)
        subtitles = scan_subtitles(self.subtitle_folder)

        self.matches = find_matches(
            videos,
            subtitles
        )

        self.result_box.insert(
            "end",
            f"Found {len(videos)} video files\n"
        )

        self.result_box.insert(
            "end",
            f"Found {len(subtitles)} subtitle files\n\n"
        )

        self.result_box.insert(
            "end",
            "VIDEOS\n"
        )

        self.result_box.insert(
            "end",
            "-" * 50 + "\n"
        )

        for video in videos[:20]:
            self.result_box.insert(
                "end",
                f"{video.name}\n"
            )

        self.result_box.insert(
            "end",
            "\nSUBTITLES\n"
        )

        self.result_box.insert(
            "end",
            "-" * 50 + "\n"
        )

        for subtitle in subtitles[:20]:
            self.result_box.insert(
                "end",
                f"{subtitle.name}\n"
            )

        self.result_box.insert(
            "end",
            f"\nMATCHES ({len(self.matches)})\n"
        )

        self.result_box.insert(
            "end",
            "-" * 50 + "\n"
        )

        for video, subtitle in self.matches[:20]:

            self.result_box.insert(
                "end",
                f"{video.name}\n"
            )

            self.result_box.insert(
                "end",
                f"  -> {subtitle.name}\n\n"
            )

    def match_and_copy(self):

        self.result_box.delete("1.0", "end")

        if not self.matches:

            self.result_box.insert(
                "end",
                "No matches found. Run Scan Files first.\n"
            )

            return

        copied, skipped = copy_matches(
            self.matches
        )

        self.result_box.insert(
            "end",
            f"Copied: {copied}\n"
        )

        self.result_box.insert(
            "end",
            f"Skipped (already exists): {skipped}\n"
        )

        self.result_box.insert(
            "end",
            "\nFinished successfully.\n"
        )