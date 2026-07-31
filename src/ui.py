# ui.py
import os
import sys
import threading
import customtkinter as ctk

from tkinter import filedialog, messagebox
from pathlib import Path

from scanner import scan_videos, scan_subtitles
from matcher import find_matches
from copier import copy_matches
from smart_match import SmartMatcher
from config import Config


class SubtitleMatcherUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SubtitleMatcher")
        self.geometry("950x850")

        self.video_folder = ""
        self.subtitle_folder = ""
        self.matches = []

        self.smart_video_folder = ""
        self.smart_matcher = SmartMatcher()
        self.smart_results = {}

        self.base_dir = self.get_base_dir()
        self.env_path = self.base_dir / ".env"
        
        # User .env path (for installed version)
        self.user_env_path = Path.home() / ".subtitlematcher" / ".env"

        self.setup_window_icon()
        self.build_ui()
        self.load_settings()

    def get_base_dir(self):
        """
        Development:
            project root

        PyInstaller exe:
            folder where exe is located
        """
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent

        return Path(__file__).resolve().parent.parent

    def setup_window_icon(self):
        icon_path = self.base_dir / "resources" / "icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

    def build_ui(self):
        self.title_label = ctk.CTkLabel(
            self,
            text="SubtitleMatcher",
            font=("Segoe UI", 28, "bold")
        )
        self.title_label.pack(pady=(20, 10))

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=20, pady=10)

        self.tab_manual = self.tabview.add("Manual Match")
        self.tab_smart = self.tabview.add("Smart Match")
        self.tab_settings = self.tabview.add("Settings")
        self.tab_help = self.tabview.add("Help")

        self.build_manual_tab()
        self.build_smart_tab()
        self.build_settings_tab()
        self.build_help_tab()
        self.build_log_window()

    # === MANUAL MATCH TAB ===

    def build_manual_tab(self):
        self.manual_frame = ctk.CTkFrame(self.tab_manual)
        self.manual_frame.pack(padx=20, pady=20, fill="both", expand=True)

        manual_title = ctk.CTkLabel(
            self.manual_frame,
            text="Manual Match",
            font=("Segoe UI", 20, "bold")
        )
        manual_title.pack(pady=(10, 20))

        manual_description = ctk.CTkLabel(
            self.manual_frame,
            text="Use Manual Match when you already have subtitle files and want to match them with video files.",
            wraplength=700
        )
        manual_description.pack(pady=(0, 15))

        self.video_button = ctk.CTkButton(
            self.manual_frame,
            text="Select Video Folder",
            command=self.select_video_folder
        )
        self.video_button.pack(pady=5)

        self.video_label = ctk.CTkLabel(
            self.manual_frame,
            text="No video folder selected",
            wraplength=700
        )
        self.video_label.pack(pady=5)

        self.subtitle_button = ctk.CTkButton(
            self.manual_frame,
            text="Select Subtitle Folder",
            command=self.select_subtitle_folder
        )
        self.subtitle_button.pack(pady=5)

        self.subtitle_label = ctk.CTkLabel(
            self.manual_frame,
            text="No subtitle folder selected",
            wraplength=700
        )
        self.subtitle_label.pack(pady=5)

        self.scan_button = ctk.CTkButton(
            self.manual_frame,
            text="Scan Files",
            command=self.scan_files
        )
        self.scan_button.pack(pady=(20, 5))

        self.copy_button = ctk.CTkButton(
            self.manual_frame,
            text="Match & Copy",
            command=self.match_and_copy
        )
        self.copy_button.pack(pady=5)

    # === SMART MATCH TAB ===

    def build_smart_tab(self):
        self.smart_frame = ctk.CTkFrame(self.tab_smart)
        self.smart_frame.pack(padx=20, pady=20, fill="both", expand=True)

        smart_title = ctk.CTkLabel(
            self.smart_frame,
            text="Smart Match",
            font=("Segoe UI", 20, "bold")
        )
        smart_title.pack(pady=(10, 10))

        smart_description = ctk.CTkLabel(
            self.smart_frame,
            text="Smart Match uses OpenSubtitles, SubDL and TMDB API keys. Manual Match works without API keys.",
            wraplength=700
        )
        smart_description.pack(pady=(0, 15))

        # === INFO FRAME ===
        self.info_frame = ctk.CTkFrame(self.smart_frame)
        self.info_frame.pack(pady=10, padx=20, fill="x")
        
        # Poster placeholder
        self.poster_label = ctk.CTkLabel(
            self.info_frame,
            text="🎬",
            font=("Segoe UI", 48),
            width=100,
            height=150
        )
        self.poster_label.pack(side="left", padx=10, pady=10)
        
        # Info text frame
        self.info_text_frame = ctk.CTkFrame(self.info_frame, fg_color="transparent")
        self.info_text_frame.pack(side="left", padx=10, pady=10, fill="both", expand=True)
        
        self.info_title_label = ctk.CTkLabel(
            self.info_text_frame,
            text="No media selected",
            font=("Segoe UI", 18, "bold"),
            anchor="w"
        )
        self.info_title_label.pack(anchor="w")
        
        self.info_year_label = ctk.CTkLabel(
            self.info_text_frame,
            text="",
            font=("Segoe UI", 12),
            anchor="w"
        )
        self.info_year_label.pack(anchor="w")
        
        self.info_rating_label = ctk.CTkLabel(
            self.info_text_frame,
            text="",
            font=("Segoe UI", 12),
            anchor="w"
        )
        self.info_rating_label.pack(anchor="w")
        
        self.info_genres_label = ctk.CTkLabel(
            self.info_text_frame,
            text="",
            font=("Segoe UI", 12),
            anchor="w",
            wraplength=400
        )
        self.info_genres_label.pack(anchor="w")
        
        self.info_overview_label = ctk.CTkLabel(
            self.info_text_frame,
            text="",
            font=("Segoe UI", 11),
            anchor="w",
            wraplength=500,
            justify="left"
        )
        self.info_overview_label.pack(anchor="w", pady=(5, 0))

        # Mode selection
        mode_frame = ctk.CTkFrame(self.smart_frame)
        mode_frame.pack(pady=5, padx=20, fill="x")

        mode_label = ctk.CTkLabel(
            mode_frame,
            text="Mode:",
            font=("Segoe UI", 12)
        )
        mode_label.pack(side="left", padx=5)

        self.smart_mode_var = ctk.StringVar(value="TV Series")
        self.smart_mode_menu = ctk.CTkOptionMenu(
            mode_frame,
            values=["TV Series", "Movie"],
            variable=self.smart_mode_var
        )
        self.smart_mode_menu.pack(side="left", padx=5)

        # Language selection
        language_frame = ctk.CTkFrame(self.smart_frame)
        language_frame.pack(pady=5, padx=20, fill="x")

        language_label = ctk.CTkLabel(
            language_frame,
            text="Language:",
            font=("Segoe UI", 12)
        )
        language_label.pack(side="left", padx=5)

        self.language_var = ctk.StringVar(value="English (en)")
        self.language_menu = ctk.CTkOptionMenu(
            language_frame,
            values=[
                "English (en)",
                "Finnish (fi)",
                "Swedish (sv)",
                "Norwegian (no)",
                "Danish (da)",
                "Estonian (et)",
                "Latvian (lv)",
                "Lithuanian (lt)",
                "German (de)",
                "French (fr)",
                "Spanish (es)",
                "Italian (it)",
                "Polish (pl)",
                "Czech (cs)",
                "Dutch (nl)",
                "Portuguese (pt)",
                "Russian (ru)"
            ],
            variable=self.language_var
        )
        self.language_menu.pack(side="left", padx=5)

        self.smart_video_button = ctk.CTkButton(
            self.smart_frame,
            text="Select Video Library",
            command=self.select_smart_video_folder
        )
        self.smart_video_button.pack(pady=(20, 5))

        self.smart_video_label = ctk.CTkLabel(
            self.smart_frame,
            text="No video library selected",
            wraplength=700
        )
        self.smart_video_label.pack(pady=5)

        self.progress_bar = ctk.CTkProgressBar(self.smart_frame)
        self.progress_bar.pack(pady=15, padx=20, fill="x")
        self.progress_bar.set(0)

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

        self.smart_info_label = ctk.CTkLabel(
            self.smart_frame,
            text="Ready",
            wraplength=700
        )
        self.smart_info_label.pack(pady=10)

    # === SETTINGS TAB ===

    def build_settings_tab(self):
        self.settings_frame = ctk.CTkFrame(self.tab_settings)
        self.settings_frame.pack(padx=20, pady=20, fill="both", expand=True)

        settings_title = ctk.CTkLabel(
            self.settings_frame,
            text="Settings",
            font=("Segoe UI", 20, "bold")
        )
        settings_title.pack(pady=(10, 20))

        settings_description = ctk.CTkLabel(
            self.settings_frame,
            text="API keys are saved locally to a .env file. They are not needed for Manual Match.",
            wraplength=700
        )
        settings_description.pack(pady=(0, 20))

        # OpenSubtitles API Key
        ctk.CTkLabel(
            self.settings_frame,
            text="OpenSubtitles API Key"
        ).pack(pady=(10, 5))

        self.opensub_entry = ctk.CTkEntry(
            self.settings_frame,
            width=600,
            show="*"
        )
        self.opensub_entry.pack(pady=5)

        # TMDB API Key
        ctk.CTkLabel(
            self.settings_frame,
            text="TMDB API Key"
        ).pack(pady=(20, 5))

        self.tmdb_entry = ctk.CTkEntry(
            self.settings_frame,
            width=600,
            show="*"
        )
        self.tmdb_entry.pack(pady=5)

        # SubDL API Key
        ctk.CTkLabel(
            self.settings_frame,
            text="SubDL API Key"
        ).pack(pady=(20, 5))

        self.subdl_entry = ctk.CTkEntry(
            self.settings_frame,
            width=600,
            show="*"
        )
        self.subdl_entry.pack(pady=5)

        # Show API Keys checkbox
        self.show_keys_var = ctk.BooleanVar(value=False)
        self.show_keys_checkbox = ctk.CTkCheckBox(
            self.settings_frame,
            text="Show API Keys",
            variable=self.show_keys_var,
            command=self.toggle_key_visibility
        )
        self.show_keys_checkbox.pack(pady=10)

        # Settings file location
        self.env_location_label = ctk.CTkLabel(
            self.settings_frame,
            text="Settings file: " + str(self.user_env_path),
            wraplength=700
        )
        self.env_location_label.pack(pady=(20, 5))

        self.save_settings_button = ctk.CTkButton(
            self.settings_frame,
            text="Save Settings",
            command=self.save_settings
        )
        self.save_settings_button.pack(pady=(20, 5))

        self.settings_status_label = ctk.CTkLabel(
            self.settings_frame,
            text="",
            wraplength=700
        )
        self.settings_status_label.pack(pady=10)

    def toggle_key_visibility(self):
        """Toggle visibility of API keys."""
        if self.show_keys_var.get():
            self.opensub_entry.configure(show="")
            self.tmdb_entry.configure(show="")
            self.subdl_entry.configure(show="")
        else:
            self.opensub_entry.configure(show="*")
            self.tmdb_entry.configure(show="*")
            self.subdl_entry.configure(show="*")

    def load_settings(self):
        """Load settings from .env file."""
        env_to_load = None
        
        if self.user_env_path.exists():
            env_to_load = self.user_env_path
        elif self.env_path.exists():
            env_to_load = self.env_path
        else:
            return

        values = {}

        try:
            with open(env_to_load, "r", encoding="utf-8") as file:
                for line in file:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip()
        except Exception as e:
            self.settings_status_label.configure(
                text="Could not read .env file: " + str(e)
            )
            return

        if values.get("OPENSUBTITLES_API_KEY"):
            self.opensub_entry.delete(0, "end")
            self.opensub_entry.insert(0, values["OPENSUBTITLES_API_KEY"])

        if values.get("TMDB_API_KEY"):
            self.tmdb_entry.delete(0, "end")
            self.tmdb_entry.insert(0, values["TMDB_API_KEY"])

        if values.get("SUBDL_API_KEY"):
            self.subdl_entry.delete(0, "end")
            self.subdl_entry.insert(0, values["SUBDL_API_KEY"])

    def save_settings(self):
        """Save API keys to .env file and update Config."""
        opensub_key = self.opensub_entry.get().strip()
        tmdb_key = self.tmdb_entry.get().strip()
        subdl_key = self.subdl_entry.get().strip()

        try:
            self.user_env_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.user_env_path, "w", encoding="utf-8") as file:
                file.write(f"OPENSUBTITLES_API_KEY={opensub_key}\n")
                file.write(f"TMDB_API_KEY={tmdb_key}\n")
                file.write(f"SUBDL_API_KEY={subdl_key}\n")
            
            with open(self.env_path, "w", encoding="utf-8") as file:
                file.write(f"OPENSUBTITLES_API_KEY={opensub_key}\n")
                file.write(f"TMDB_API_KEY={tmdb_key}\n")
                file.write(f"SUBDL_API_KEY={subdl_key}\n")
            
            Config.load()
            Config.print_status()
            self.smart_matcher = SmartMatcher()
            
            self.settings_status_label.configure(text="Settings saved successfully.")
            self.log_message(f"✅ Settings saved to: {self.user_env_path}")
            self.log_message("✅ SmartMatcher updated with new API keys!")

        except Exception as e:
            self.settings_status_label.configure(text="Error saving settings: " + str(e))
            messagebox.showerror("Settings Error", str(e))

    # === HELP TAB ===

    def build_help_tab(self):
        self.help_frame = ctk.CTkFrame(self.tab_help)
        self.help_frame.pack(padx=20, pady=20, fill="both", expand=True)

        help_title = ctk.CTkLabel(
            self.help_frame,
            text="Help",
            font=("Segoe UI", 20, "bold")
        )
        help_title.pack(pady=(10, 15))

        help_text = """Manual Match

Manual Match works without API keys.

Steps:
1. Select the video folder.
2. Select the subtitle folder.
3. Click Scan Files.
4. Click Match & Copy.

Use this mode when you already have subtitle files locally.


Smart Match

Smart Match can search and download subtitles automatically.

Steps:
1. Open the Settings tab.
2. Enter your OpenSubtitles API key.
3. Enter your TMDB API key.
4. Enter your SubDL API key (optional, but recommended).
5. Save settings.
6. Open the Smart Match tab.
7. Select the video library.
8. Select language.
9. Select mode (TV Series or Movie).
10. Scan, download and match subtitles.

TV Series filename examples:
  Show.Name.S01E01.mkv
  Show Name - S01E01.mp4
  Show.Name.1x01.avi

Movie filename examples:
  Movie Name 2023.mkv
  Movie.Name.2023.mp4
  Avatar (2009).mkv
  The.Dark.Knight.2008.1080p.BluRay.mkv


API Keys

OpenSubtitles:
  Create an account at opensubtitles.com and create an API key.

TMDB:
  Create an account at themoviedb.org and create an API key.

SubDL:
  Create an account at subdl.com and get your API key from the API dashboard.

The keys are saved locally into a .env file next to the application or project folder.

If automatic detection fails, use Manual Match.
"""

        self.help_textbox = ctk.CTkTextbox(
            self.help_frame,
            width=800,
            height=500
        )
        self.help_textbox.pack(fill="both", expand=True, padx=10, pady=10)
        self.help_textbox.insert("1.0", help_text)
        self.help_textbox.configure(state="disabled")

    # === LOG WINDOW ===

    def build_log_window(self):
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.pack(pady=(0, 20), padx=20, fill="both", expand=False)

        log_title = ctk.CTkLabel(
            self.log_frame,
            text="Log",
            font=("Segoe UI", 14, "bold")
        )
        log_title.pack(anchor="w", padx=10, pady=(5, 0))

        self.result_box = ctk.CTkTextbox(
            self.log_frame,
            width=800,
            height=180
        )
        self.result_box.pack(pady=10, padx=10, fill="both", expand=True)

    # === API VALIDATION ===

    def validate_api_keys_for_smart_match(self):
        """Validate API keys and update Config."""
        Config.load()
        
        opensub_key = Config.OPENSUBTITLES_API_KEY
        tmdb_key = Config.TMDB_API_KEY
        subdl_key = Config.SUBDL_API_KEY
        
        if not opensub_key or not tmdb_key:
            env_to_load = None
            if self.user_env_path.exists():
                env_to_load = self.user_env_path
            elif self.env_path.exists():
                env_to_load = self.env_path
            
            if env_to_load:
                try:
                    with open(env_to_load, "r", encoding="utf-8") as file:
                        for line in file:
                            if "=" in line:
                                key, value = line.strip().split("=", 1)
                                if key == "OPENSUBTITLES_API_KEY":
                                    opensub_key = value
                                elif key == "TMDB_API_KEY":
                                    tmdb_key = value
                                elif key == "SUBDL_API_KEY":
                                    subdl_key = value
                except Exception as e:
                    print(f"Error reading .env: {e}")
        
        missing_keys = []

        if not opensub_key and not subdl_key:
            missing_keys.append("OPENSUBTITLES_API_KEY or SUBDL_API_KEY")
        if not tmdb_key:
            missing_keys.append("TMDB_API_KEY")

        if missing_keys:
            self.show_api_warning(missing_keys)
            self.tabview.set("Settings")
            return False

        self.smart_matcher = SmartMatcher()
        return True

    def show_api_warning(self, missing_keys):
        warning = "Missing API keys:\n"
        for key in missing_keys:
            warning += "  - " + key + "\n"
        warning += "\nPlease add the keys in the Settings tab."
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

    def _get_language_code(self):
        display = self.language_var.get()
        start = display.find("(") + 1
        end = display.find(")")
        return display[start:end] if start > 0 and end > start else "en"

    def smart_scan(self):
        self.clear_log()

        mode = self.smart_mode_var.get()

        if not self.smart_video_folder:
            self.log_message("Select video library first")
            return

        self.log_message("Scanning video library...")
        self.log_message("Mode: " + mode)
        self.log_message("Library: " + self.smart_video_folder)
        self.log_message("")

        thread = threading.Thread(target=self._run_smart_scan)
        thread.daemon = True
        thread.start()

    def _run_smart_scan(self):
        try:
            mode = self.smart_mode_var.get()

            if mode == "Movie":
                movies = self.smart_matcher.scan_movie_library(self.smart_video_folder)

                self.after(0, lambda: self.log_message("Found " + str(len(movies)) + " movie files"))

                if movies:
                    movie = movies[0]
                    self.after(0, lambda: self._show_movie_info(movie))
                    
                    for movie in movies[:10]:
                        year_str = f" ({movie.year})" if movie.year else ""
                        self.after(0, lambda m=movie: self.log_message(f"  {m.title}{year_str}"))

                    self.after(0, lambda: self.smart_info_label.configure(
                        text="Scan complete: " + str(len(movies)) + " movies found"
                    ))
                else:
                    self.after(0, lambda: self.smart_info_label.configure(text="No movies found"))
            else:
                episodes = self.smart_matcher.scan_video_library(self.smart_video_folder)

                self.after(0, lambda: self.log_message("Found " + str(len(episodes)) + " video files"))

                if episodes:
                    show_name = episodes[0].show_name
                    season = episodes[0].season
                    season_count = len([e for e in episodes if e.season == season])

                    self.after(0, lambda: self._show_show_info(show_name))
                    self.after(0, lambda: self.log_message("Show: " + show_name))
                    self.after(0, lambda: self.log_message("Season: " + str(season)))
                    self.after(0, lambda: self.log_message("Episodes: " + str(season_count)))
                    self.after(0, lambda: self.smart_info_label.configure(
                        text="Scan complete: " + str(len(episodes)) + " episodes found"
                    ))
                else:
                    self.after(0, lambda: self.smart_info_label.configure(text="No episodes found"))

            self.after(0, lambda: self.progress_bar.set(0.5))

        except Exception as e:
            self.after(0, lambda: self.log_message("Error: " + str(e)))
            self.after(0, lambda: self.smart_info_label.configure(text="Error scanning"))

    def _show_movie_info(self, movie_info):
        """Show movie details in info frame."""
        try:
            movie_id = self.smart_matcher.find_movie_id(movie_info.title, movie_info.year)
            if movie_id:
                details = self.smart_matcher.get_movie_details(movie_id)
                if details:
                    self.info_title_label.configure(text=details.get("title", "Unknown"))
                    self.info_year_label.configure(text=f"📅 {details.get('year', 'N/A')}")
                    
                    rating = details.get("rating", 0)
                    stars = "⭐" * int(rating / 2) if rating else ""
                    self.info_rating_label.configure(
                        text=f"{stars} {rating:.1f}/10 ({details.get('rating_count', 0)} votes)"
                    )
                    
                    genres = ", ".join(details.get("genres", []))
                    self.info_genres_label.configure(text=f"🎭 {genres}" if genres else "")
                    
                    overview = details.get("overview", "No description available")
                    if len(overview) > 300:
                        overview = overview[:300] + "..."
                    self.info_overview_label.configure(text=f"📝 {overview}")
                    
                    # Load poster
                    poster_url = details.get("poster_url")
                    if poster_url:
                        self._load_poster(poster_url)
                    else:
                        self.poster_label.configure(text="🎬")
                    
        except Exception as e:
            print(f"Error showing movie info: {e}")

    def _show_show_info(self, show_name):
        """Show TV show details in info frame."""
        try:
            show_id = self.smart_matcher.find_show_id(show_name)
            if show_id:
                details = self.smart_matcher.get_show_details(show_id)
                if details:
                    self.info_title_label.configure(text=details.get("title", "Unknown"))
                    self.info_year_label.configure(text=f"📅 {details.get('year', 'N/A')}")
                    
                    rating = details.get("rating", 0)
                    stars = "⭐" * int(rating / 2) if rating else ""
                    self.info_rating_label.configure(
                        text=f"{stars} {rating:.1f}/10 ({details.get('rating_count', 0)} votes)"
                    )
                    
                    genres = ", ".join(details.get("genres", []))
                    seasons = details.get("seasons", 0)
                    self.info_genres_label.configure(
                        text=f"🎭 {genres} | 📺 {seasons} seasons" if genres else f"📺 {seasons} seasons"
                    )
                    
                    overview = details.get("overview", "No description available")
                    if len(overview) > 300:
                        overview = overview[:300] + "..."
                    self.info_overview_label.configure(text=f"📝 {overview}")
                    
                    # Load poster
                    poster_url = details.get("poster_url")
                    if poster_url:
                        self._load_poster(poster_url)
                    else:
                        self.poster_label.configure(text="📺")
                    
        except Exception as e:
            print(f"Error showing show info: {e}")

    def _load_poster(self, poster_url: str):
        """Load poster image from URL."""
        try:
            import requests
            from PIL import Image
            from io import BytesIO
            
            # Download image
            response = requests.get(poster_url, timeout=10)
            if response.status_code == 200:
                # Convert to CTkImage
                image = Image.open(BytesIO(response.content))
                
                # Resize to fit
                image = image.resize((100, 150), Image.Resampling.LANCZOS)
                
                # Create CTkImage
                ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=(100, 150))
                
                # Update poster_label
                self.poster_label.configure(image=ctk_image, text="")
            else:
                self.poster_label.configure(text="🎬")
        except Exception as e:
            print(f"Error loading poster: {e}")
            self.poster_label.configure(text="🎬")

    def smart_download(self):
        self.clear_log()

        if not self.validate_api_keys_for_smart_match():
            return

        if not self.smart_video_folder:
            self.log_message("Select video library first")
            return

        language_code = self._get_language_code()
        mode = self.smart_mode_var.get()

        self.log_message("=" * 60)
        self.log_message(f"🎯 Mode: {mode}")
        self.log_message(f"🌐 Language: {language_code}")
        self.log_message("=" * 60)
        self.log_message("Starting download process...")

        thread = threading.Thread(target=self._run_smart_download, args=(language_code, mode))
        thread.daemon = True
        thread.start()

    def _run_smart_download(self, language_code, mode):
        try:
            if mode == "Movie":
                self._run_movie_download(language_code)
            else:
                self._run_tv_download(language_code)

        except Exception as e:
            self.after(0, lambda: self.log_message(f"❌ Error: {str(e)}"))
            self.after(0, lambda: self.smart_info_label.configure(text="Error downloading"))

    def _run_tv_download(self, language_code):
        episodes = self.smart_matcher.scan_video_library(self.smart_video_folder)

        if not episodes:
            self.after(0, lambda: self.log_message("❌ No episodes found"))
            return

        show_name = episodes[0].show_name
        self.after(0, lambda: self.log_message(f"📺 Series: {show_name}"))
        self.after(0, lambda: self.log_message("🔍 Searching for subtitles..."))

        show_id = self.smart_matcher.find_show_id(show_name)
        if not show_id:
            self.after(0, lambda: self.log_message(f"❌ Could not find show: {show_name}"))
            return

        imdb_id = self.smart_matcher.get_imdb_id(show_id)
        if not imdb_id:
            self.after(0, lambda: self.log_message("❌ Could not get IMDB ID"))
            return

        self.after(0, lambda: self.log_message(f"📌 IMDB ID: {imdb_id}"))

        total = len(episodes)
        downloaded = 0
        failed_episodes = []

        self.after(0, lambda: self.log_message(""))
        self.after(0, lambda: self.log_message("=" * 60))
        self.after(0, lambda: self.log_message(f"📥 Downloading {total} episodes..."))
        self.after(0, lambda: self.log_message("=" * 60))

        for i, episode in enumerate(episodes):
            progress = (i + 1) / total
            
            # Päivitä progress bar (prosentti näkyy tässä)
            self.after(0, lambda p=progress: self.progress_bar.set(p))
            
            # Näytä prosentti info-labelissa
            percent = int(progress * 100)
            self.after(0, lambda p=percent: self.smart_info_label.configure(
                text=f"Downloading: {p}% ({i+1}/{total})"
            ))
            
            # Selkeä jakso-ilmoitus (ilman prosenttia)
            self.after(0, lambda e=episode: self.log_message(
                f"Episode {e.episode:02d}..."
            ))
            
            subtitle_file = self.smart_matcher.download_subtitles_for_episode(
                episode,
                imdb_id,
                language_code
            )

            if subtitle_file:
                downloaded += 1
                self.after(0, lambda f=subtitle_file: self.log_message(
                    f"  ✅ {f.name}"
                ))
            else:
                failed_episodes.append(episode.episode)
                self.after(0, lambda e=episode: self.log_message(
                    f"  ❌ Episode {e.episode:02d} failed"
                ))

               # LOPPUTULOS
        self.after(0, lambda: self.log_message(""))
        self.after(0, lambda: self.log_message("=" * 60))
        self.after(0, lambda: self.log_message("📊 SUMMARY"))
        self.after(0, lambda: self.log_message("=" * 60))
        
        success_percent = int((downloaded / total) * 100) if total > 0 else 0
        self.after(0, lambda: self.log_message(f"✅ Successful: {downloaded}/{total} ({success_percent}%)"))
        
        if failed_episodes:
            self.after(0, lambda: self.log_message(f"❌ Failed: {len(failed_episodes)} episodes"))
            self.after(0, lambda: self.log_message(f"   Episodes: {', '.join(map(str, failed_episodes))}"))
        else:
            self.after(0, lambda: self.log_message("🎉 All episodes downloaded successfully!"))

        self.after(0, lambda: self.log_message("=" * 60))
        self.after(0, lambda: self.smart_info_label.configure(
            text=f"✅ Complete: {downloaded}/{total} subtitles"
        ))
        self.after(0, lambda: self.progress_bar.set(1.0))

    def _run_movie_download(self, language_code):
        movies = self.smart_matcher.scan_movie_library(self.smart_video_folder)

        if not movies:
            self.after(0, lambda: self.log_message("❌ No movies found"))
            return

        total = len(movies)
        downloaded = 0
        failed_movies = []

        self.after(0, lambda: self.log_message(""))
        self.after(0, lambda: self.log_message("=" * 60))
        self.after(0, lambda: self.log_message(f"📥 Downloading {total} movies..."))
        self.after(0, lambda: self.log_message("=" * 60))

        for i, movie in enumerate(movies):
            progress = (i + 1) / total
            
            # Päivitä progress bar
            self.after(0, lambda p=progress: self.progress_bar.set(p))
            
            # Näytä prosentti info-labelissa
            percent = int(progress * 100)
            self.after(0, lambda p=percent: self.smart_info_label.configure(
                text=f"Downloading: {p}% ({i+1}/{total})"
            ))
            
            self.after(0, lambda m=movie: self.log_message(
                f"🎬 {m.title}..."
            ))

            subtitle_file = self.smart_matcher.download_subtitles_for_movie(
                movie,
                language_code
            )

            if subtitle_file:
                downloaded += 1
                self.after(0, lambda f=subtitle_file: self.log_message(
                    f"  ✅ {f.name}"
                ))
            else:
                failed_movies.append(movie.title)
                self.after(0, lambda m=movie: self.log_message(
                    f"  ❌ {m.title} failed"
                ))

        # LOPPUTULOS
        self.after(0, lambda: self.log_message(""))
        self.after(0, lambda: self.log_message("=" * 60))
        self.after(0, lambda: self.log_message("📊 SUMMARY"))
        self.after(0, lambda: self.log_message("=" * 60))
        
        success_percent = int((downloaded / total) * 100) if total > 0 else 0
        self.after(0, lambda: self.log_message(f"✅ Successful: {downloaded}/{total} ({success_percent}%)"))
        
        if failed_movies:
            self.after(0, lambda: self.log_message(f"❌ Failed: {len(failed_movies)} movies"))
            for title in failed_movies[:5]:
                self.after(0, lambda t=title: self.log_message(f"   - {t}"))
            if len(failed_movies) > 5:
                self.after(0, lambda: self.log_message(f"   ... and {len(failed_movies) - 5} more"))
        else:
            self.after(0, lambda: self.log_message("🎉 All movies downloaded successfully!"))

        self.after(0, lambda: self.log_message("=" * 60))
        self.after(0, lambda: self.smart_info_label.configure(
            text=f"✅ Complete: {downloaded}/{total} subtitles"
        ))
        self.after(0, lambda: self.progress_bar.set(1.0))

    def smart_match_and_copy(self):
        self.clear_log()

        if not self.validate_api_keys_for_smart_match():
            return

        if not self.smart_video_folder:
            self.log_message("Select video library first")
            return

        language_code = self._get_language_code()
        mode = self.smart_mode_var.get()

        self.log_message("Mode: " + mode)
        self.log_message("Starting auto match in: " + language_code)

        thread = threading.Thread(
            target=self._run_smart_match_and_copy,
            args=(language_code, mode)
        )
        thread.daemon = True
        thread.start()

    def _run_smart_match_and_copy(self, language_code, mode):
        try:
            if mode == "Movie":
                results = self.smart_matcher.match_all_movies(
                    self.smart_video_folder,
                    language_code
                )
            else:
                results = self.smart_matcher.match_all_episodes(
                    self.smart_video_folder,
                    language_code
                )

            self.after(0, lambda: self.log_message(""))
            self.after(0, lambda: self.log_message("Results:"))
            self.after(0, lambda: self.log_message("-" * 50))

            for video, subtitle in results.items():
                self.after(
                    0,
                    lambda v=video, s=subtitle: self.log_message(v.name + " -> " + s.name)
                )

            self.after(0, lambda: self.log_message(""))
            self.after(
                0,
                lambda: self.log_message("Completed: " + str(len(results)) + " files matched")
            )
            self.after(
                0,
                lambda: self.smart_info_label.configure(
                    text="Match complete: " + str(len(results)) + " files"
                )
            )

        except Exception as e:
            self.after(0, lambda: self.log_message("Error: " + str(e)))
            self.after(0, lambda: self.smart_info_label.configure(text="Error matching"))

    # === HELPER METHODS ===

    def log_message(self, message):
        self.result_box.insert("end", message + "\n")
        self.result_box.see("end")

    def clear_log(self):
        self.result_box.delete("1.0", "end")


def main():
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    app = SubtitleMatcherUI()
    app.mainloop()


if __name__ == "__main__":
    main()