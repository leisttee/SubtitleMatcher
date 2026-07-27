# ui.py (päivitetty)
import customtkinter as ctk
from tkinter import filedialog, messagebox
from pathlib import Path
import threading

from scanner import scan_videos, scan_subtitles
from matcher import find_matches
from copier import copy_matches
from smart_match import SmartMatcher
from config import Config


class SubtitleMatcherUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SubtitleMatcher")
        self.geometry("900x800")

        self.video_folder = ""
        self.subtitle_folder = ""
        self.matches = []

        # Smart Match variables
        self.smart_video_folder = ""
        self.smart_matcher = SmartMatcher()
        self.smart_results = {}

        # Check API keys
        missing_keys = Config.validate()
        if missing_keys:
            self.show_api_warning(missing_keys)

        # Resources
        base_dir = Path(__file__).resolve().parent.parent
        icon_path = base_dir / "resources" / "icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        # Main title
        self.title_label = ctk.CTkLabel(
            self,
            text="SubtitleMatcher",
            font=("Segoe UI", 28, "bold")
        )
        self.title_label.pack(pady=(20, 10))

        # Main container
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(pady=10, padx=20, fill="both", expand=True)

        # === MANUAL MATCH (left side) ===
        self.manual_frame = ctk.CTkFrame(self.main_frame)
        self.manual_frame.pack(side="left", padx=10, pady=10, fill="both", expand=True)

        manual_title = ctk.CTkLabel(
            self.manual_frame,
            text="Manual Match",
            font=("Segoe UI", 18, "bold")
        )
        manual_title.pack(pady=(0, 15))

        # Video folder
        self.video_button = ctk.CTkButton(
            self.manual_frame,
            text="Select Video Folder",
            command=self.select_video_folder
        )
        self.video_button.pack(pady=5)

        self.video_label = ctk.CTkLabel(
            self.manual_frame,
            text="No video folder selected",
            wraplength=350
        )
        self.video_label.pack(pady=5)

        # Subtitle folder
        self.subtitle_button = ctk.CTkButton(
            self.manual_frame,
            text="Select Subtitle Folder",
            command=self.select_subtitle_folder
        )
        self.subtitle_button.pack(pady=5)

        self.subtitle_label = ctk.CTkLabel(
            self.manual_frame,
            text="No subtitle folder selected",
            wraplength=350
        )
        self.subtitle_label.pack(pady=5)

        # Scan button
        self.scan_button = ctk.CTkButton(
            self.manual_frame,
            text="Scan Files",
            command=self.scan_files
        )
        self.scan_button.pack(pady=10)

        # Match & Copy button
        self.copy_button = ctk.CTkButton(
            self.manual_frame,
            text="Match & Copy",
            command=self.match_and_copy
        )
        self.copy_button.pack(pady=5)

        # === SMART MATCH (right side) ===
        self.smart_frame = ctk.CTkFrame(self.main_frame)
        self.smart_frame.pack(side="right", padx=10, pady=10, fill="both", expand=True)

        smart_title = ctk.CTkLabel(
            self.smart_frame,
            text="Smart Match",
            font=("Segoe UI", 18, "bold")
        )
        smart_title.pack(pady=(0, 15))

        # Language selection
        language_frame = ctk.CTkFrame(self.smart_frame)
        language_frame.pack(pady=5, fill="x")

        language_label = ctk.CTkLabel(
            language_frame,
            text="Language:",
            font=("Segoe UI", 12)
        )
        language_label.pack(side="left", padx=5)

        self.language_var = ctk.StringVar(value="en")
        self.language_menu = ctk.CTkOptionMenu(
            language_frame,
            values=["en", "fi", "sv", "no", "da"],
            variable=self.language_var
        )
        self.language_menu.pack(side="left", padx=5)

        # Video library
        self.smart_video_button = ctk.CTkButton(
            self.smart_frame,
            text="Select Video Library",
            command=self.select_smart_video_folder
        )
        self.smart_video_button.pack(pady=5)

        self.smart_video_label = ctk.CTkLabel(
            self.smart_frame,
            text="No video library selected",
            wraplength=350
        )
        self.smart_video_label.pack(pady=5)

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(self.smart_frame)
        self.progress_bar.pack(pady=10, padx=20, fill="x")
        self.progress_bar.set(0)

        # Action buttons
        self.smart_scan_button = ctk.CTkButton(
            self.smart_frame,
            text="Scan Video Library",
            command=self.smart_scan
        )
        self.smart_scan_button.pack(pady=5)

        self.smart_download_button = ctk.CTkButton(
            self.smart_frame,
            text="Download Subtitles",
            command=self.smart_download
        )
        self.smart_download_button.pack(pady=5)

        self.smart_match_button = ctk.CTkButton(
            self.smart_frame,
            text="Auto Match & Copy",
            command=self.smart_match_and_copy
        )
        self.smart_match_button.pack(pady=5)

        # Info label
        self.smart_info_label = ctk.CTkLabel(
            self.smart_frame,
            text="Ready",
            wraplength=350
        )
        self.smart_info_label.pack(pady=5)

        # === LOG WINDOW (bottom) ===
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.pack(pady=10, padx=20, fill="both", expand=True)

        log_title = ctk.CTkLabel(
            self.log_frame,
            text="Log",
            font=("Segoe UI", 14, "bold")
        )
        log_title.pack(anchor="w", padx=10, pady=(5, 0))

        self.result_box = ctk.CTkTextbox(
            self.log_frame,
            width=700,
            height=200
        )
        self.result_box.pack(pady=10, padx=10, fill="both", expand=True)

    def show_api_warning(self, missing_keys):
        """Näyttää varoituksen puuttuvista API-avaimista"""
        warning = "Missing API keys:\n"
        for key in missing_keys:
            warning += f"  - {key}\n"
        warning += "\nPlease set these as environment variables or in config.py"
        
        messagebox.showwarning("API Keys Required", warning)

    # === MANUAL MATCH METHODS ===

    def select_video_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.video_folder = folder
            self.video_label.configure(text=folder)
            self.log_message("Selected video folder: " + folder)

    def select_subtitle_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.subtitle_folder = folder
            self.subtitle_label.configure(text=folder)
            self.log_message("Selected subtitle folder: " + folder)

    def scan_files(self):
        self.clear_log()

        if not self.video_folder:
            self.log_message("Select video folder first")
            return

        if not self.subtitle_folder:
            self.log_message("Select subtitle folder first")
            return

        videos = scan_videos(self.video_folder)
        subtitles = scan_subtitles(self.subtitle_folder)

        self.matches = find_matches(videos, subtitles)

        self.log_message("Found " + str(len(videos)) + " video files")
        self.log_message("Found " + str(len(subtitles)) + " subtitle files")
        self.log_message("")
        self.log_message("VIDEOS:")
        self.log_message("-" * 50)
        for video in videos[:20]:
            self.log_message("  " + video.name)
        if len(videos) > 20:
            self.log_message("  ... and " + str(len(videos) - 20) + " more")

        self.log_message("")
        self.log_message("SUBTITLES:")
        self.log_message("-" * 50)
        for subtitle in subtitles[:20]:
            self.log_message("  " + subtitle.name)
        if len(subtitles) > 20:
            self.log_message("  ... and " + str(len(subtitles) - 20) + " more")

        self.log_message("")
        self.log_message("MATCHES (" + str(len(self.matches)) + "):")
        self.log_message("-" * 50)
        for video, subtitle in self.matches[:20]:
            self.log_message("  " + video.name)
            self.log_message("    -> " + subtitle.name)
        if len(self.matches) > 20:
            self.log_message("  ... and " + str(len(self.matches) - 20) + " more")

    def match_and_copy(self):
        self.clear_log()

        if not self.matches:
            self.log_message("No matches found. Run Scan Files first.")
            return

        copied, skipped = copy_matches(self.matches)

        self.log_message("Copied: " + str(copied))
        self.log_message("Skipped (already exists): " + str(skipped))
        self.log_message("")
        self.log_message("Finished successfully.")

    # === SMART MATCH METHODS ===

    def select_smart_video_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.smart_video_folder = folder
            self.smart_video_label.configure(text=folder)
            self.log_message("Selected video library: " + folder)

    def smart_scan(self):
        self.clear_log()
        if not self.smart_video_folder:
            self.log_message("Select video library first")
            return

        self.log_message("Scanning video library...")
        self.log_message("Library: " + self.smart_video_folder)
        self.log_message("")

        # Run in background thread
        thread = threading.Thread(target=self._run_smart_scan)
        thread.start()

    def _run_smart_scan(self):
        try:
            episodes = self.smart_matcher.scan_video_library(self.smart_video_folder)
            
            self.after(0, lambda: self.log_message("Found " + str(len(episodes)) + " video files"))
            
            if episodes:
                show_name = episodes[0].show_name
                season = episodes[0].season
                self.after(0, lambda: self.log_message("Show: " + show_name))
                self.after(0, lambda: self.log_message("Season: " + str(season)))
                self.after(0, lambda: self.log_message("Episodes: " + str(len([e for e in episodes if e.season == season]))))
                
                self.after(0, lambda: self.smart_info_label.configure(text="Scan complete: " + str(len(episodes)) + " episodes found"))
            else:
                self.after(0, lambda: self.smart_info_label.configure(text="No episodes found"))
                
            self.after(0, lambda: self.progress_bar.set(0.5))
            
        except Exception as e:
            self.after(0, lambda: self.log_message("Error: " + str(e)))
            self.after(0, lambda: self.smart_info_label.configure(text="Error scanning"))

    def smart_download(self):
        self.clear_log()
        if not self.smart_video_folder:
            self.log_message("Select video library first")
            return

        language = self.language_var.get()
        self.log_message("Downloading subtitles in: " + language)
        self.log_message("Starting download process...")

        # Run in background thread
        thread = threading.Thread(target=self._run_smart_download, args=(language,))
        thread.start()

    def _run_smart_download(self, language):
        try:
            episodes = self.smart_matcher.scan_video_library(self.smart_video_folder)
            
            if not episodes:
                self.after(0, lambda: self.log_message("No episodes found"))
                return
            
            show_name = episodes[0].show_name
            self.after(0, lambda: self.log_message("Searching for: " + show_name))
            
            show_id = self.smart_matcher.find_show_id(show_name)
            if not show_id:
                self.after(0, lambda: self.log_message("Could not find show: " + show_name))
                return
            
            imdb_id = self.smart_matcher.get_imdb_id(show_id)
            if not imdb_id:
                self.after(0, lambda: self.log_message("Could not get IMDB ID"))
                return
            
            self.after(0, lambda: self.log_message("IMDB ID: " + imdb_id))
            
            total = len(episodes)
            downloaded = 0
            
            for i, episode in enumerate(episodes):
                progress = (i + 1) / total
                self.after(0, lambda p=progress: self.progress_bar.set(p))
                
                self.after(0, lambda e=episode: self.log_message("Episode " + str(e.episode) + "..."))
                
                subtitle_file = self.smart_matcher.download_subtitles_for_episode(episode, imdb_id)
                if subtitle_file:
                    downloaded += 1
                    self.after(0, lambda: self.log_message("  Downloaded: " + subtitle_file.name))
            
            self.after(0, lambda: self.log_message(""))
            self.after(0, lambda: self.log_message("Downloaded: " + str(downloaded) + " of " + str(total)))
            self.after(0, lambda: self.smart_info_label.configure(text="Download complete: " + str(downloaded) + " subtitles"))
            self.after(0, lambda: self.progress_bar.set(1.0))
            
        except Exception as e:
            self.after(0, lambda: self.log_message("Error: " + str(e)))
            self.after(0, lambda: self.smart_info_label.configure(text="Error downloading"))

    def smart_match_and_copy(self):
        self.clear_log()
        if not self.smart_video_folder:
            self.log_message("Select video library first")
            return

        language = self.language_var.get()
        self.log_message("Starting auto match in: " + language)
        
        # Run in background thread
        thread = threading.Thread(target=self._run_smart_match_and_copy, args=(language,))
        thread.start()

    def _run_smart_match_and_copy(self, language):
        try:
            results = self.smart_matcher.match_all_episodes(self.smart_video_folder, language)
            
            self.after(0, lambda: self.log_message(""))
            self.after(0, lambda: self.log_message("Results:"))
            self.after(0, lambda: self.log_message("-" * 50))
            
            for video, subtitle in results.items():
                self.after(0, lambda v=video, s=subtitle: self.log_message(v.name + " -> " + s.name))
            
            self.after(0, lambda: self.log_message(""))
            self.after(0, lambda: self.log_message("Completed: " + str(len(results)) + " files matched"))
            self.after(0, lambda: self.smart_info_label.configure(text="Match complete: " + str(len(results)) + " files"))
            
        except Exception as e:
            self.after(0, lambda: self.log_message("Error: " + str(e)))
            self.after(0, lambda: self.smart_info_label.configure(text="Error matching"))

    # === HELPER METHODS ===

    def log_message(self, message):
        """Add message to log window"""
        self.result_box.insert("end", message + "\n")
        self.result_box.see("end")

    def clear_log(self):
        """Clear log window"""
        self.result_box.delete("1.0", "end")


def main():
    app = SubtitleMatcherUI()
    app.mainloop()


if __name__ == "__main__":
    main()