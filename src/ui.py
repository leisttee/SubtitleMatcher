import os
import sys
import threading
from pathlib import Path

if getattr(sys, 'frozen', False):
    base_dir = Path(sys.executable).resolve().parent
else:
    base_dir = Path(__file__).resolve().parent.parent

src_dir = base_dir / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(base_dir))

import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import requests
from io import BytesIO
from typing import List, Dict, Optional, Tuple, Any


from scanner import scan_videos, scan_subtitles
from matcher import find_matches
from copier import copy_matches
from smart_match import SmartMatcher
from config import Config


class SubtitleSelectionDialog(ctk.CTkToplevel):
    """Ikkuna, jossa käyttäjä voi valita tekstitysversion hakutuloksista."""
    
    def __init__(self, parent, results, video_filename=None):
        super().__init__(parent)
        self.title("Valitse tekstitysversio")
        self.geometry("700x450")
        self.results = results
        self.selected = None
        
        # Aseta modaalinen
        self.transient(parent)
        self.grab_set()
        
        # UI
        self.build_ui(results, video_filename)
        
    def build_ui(self, results, video_filename):
        # Ohjeteksti
        info_text = "Valitse haluamasi tekstitysversio. Suositeltu versio on merkitty tähdellä (*)."
        if video_filename:
            info_text += f"\nVideon julkaisuryhmä: {self._extract_release_group(video_filename) or 'Ei tunnistettu'}"
        
        info_label = ctk.CTkLabel(
            self,
            text=info_text,
            wraplength=650,
            justify="left"
        )
        info_label.pack(pady=(10, 5), padx=10)
        
        # Lista tuloksista
        self.list_frame = ctk.CTkFrame(self)
        self.list_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.list_widget = ctk.CTkScrollableFrame(self.list_frame)
        self.list_widget.pack(fill="both", expand=True)
        
        # Lisää tulokset listaan
        self.result_items = []
        for idx, result in enumerate(results):
            # Luo kehys jokaiselle riville
            item_frame = ctk.CTkFrame(self.list_widget)
            item_frame.pack(fill="x", padx=5, pady=2)
            
            # Valintanappi
            radio_var = ctk.StringVar(value="")
            radio = ctk.CTkRadioButton(
                item_frame,
                text="",
                variable=radio_var,
                value=str(idx),
                command=lambda i=idx: self.select_item(i)
            )
            radio.pack(side="left", padx=5)
            
            # Tiedostonimi (tärkein tieto)
            filename = result.get("filename", "Tuntematon")
            is_recommended = idx == 0  # Ensimmäinen on suositeltu
            
            # Tunnista julkaisuryhmä
            group = self._extract_release_group(filename)
            group_text = f" [{group}]" if group else ""
            
            name_label = ctk.CTkLabel(
                item_frame,
                text=f"{'⭐ ' if is_recommended else ''}{filename}{group_text}",
                font=("Segoe UI", 11, "bold" if is_recommended else "normal"),
                wraplength=400,
                justify="left"
            )
            name_label.pack(side="left", padx=5)
            
            # Lisätiedot: kieli, lataukset, uploader
            details = []
            if result.get("language"):
                details.append(result.get("language"))
            if result.get("download_count"):
                details.append(f"⬇️ {result.get('download_count')}")
            if result.get("uploader"):
                details.append(f"👤 {result.get('uploader')}")
            if result.get("hearing_impaired"):
                details.append("🔊 SDH")
            
            if details:
                detail_label = ctk.CTkLabel(
                    item_frame,
                    text=" | ".join(details),
                    font=("Segoe UI", 9),
                    text_color="gray"
                )
                detail_label.pack(side="right", padx=5)
            
            # Tallenna viite
            self.result_items.append({
                'frame': item_frame,
                'radio': radio,
                'radio_var': radio_var,
                'data': result
            })
        
        # Valitse ensimmäinen oletuksena
        if self.result_items:
            self.select_item(0)
            self.result_items[0]['radio_var'].set("0")
        
        # Painikkeet
        button_frame = ctk.CTkFrame(self)
        button_frame.pack(pady=10)
        
        select_btn = ctk.CTkButton(
            button_frame,
            text="Valitse ja lataa",
            command=self.confirm_selection,
            width=150
        )
        select_btn.pack(side="left", padx=5)
        
        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Peruuta",
            command=self.cancel_selection,
            width=150
        )
        cancel_btn.pack(side="left", padx=5)
    
    def _extract_release_group(self, filename: str) -> Optional[str]:
        """Tunnista julkaisuryhmä tiedostonimestä."""
        if not filename:
            return None
        
        groups = [
            'KILLERS', 'DIMENSION', 'EVO', 'NTb', 'FUM', 'TOKiG', 
            'mSD', 'BATV', 'SYS', 'XVID', 'DIVX', 'YIFY', 'YTS',
            'RARBG', 'EZTV', 'TBS', 'BSG', 'WEB', 'AMZN', 'NF'
        ]
        
        filename_upper = filename.upper()
        for group in groups:
            if group in filename_upper:
                return group
        return None
    
    def select_item(self, index):
        """Valitse listan kohta."""
        for i, item in enumerate(self.result_items):
            if i == index:
                item['radio'].select()
                item['frame'].configure(fg_color=("gray75", "gray25"))
            else:
                item['frame'].configure(fg_color=("gray94", "gray13"))
    
    def confirm_selection(self):
        """Vahvista valinta ja sulje ikkuna."""
        for item in self.result_items:
            if item['radio_var'].get():
                self.selected = item['data']
                break
        self.destroy()
    
    def cancel_selection(self):
        """Peruuta valinta ja sulje ikkuna."""
        self.selected = None
        self.destroy()


class SubtitleMatcherUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SubtitleMatcher")
        self.geometry("1100x900")

        self.video_folder = ""
        self.subtitle_folder = ""
        self.matches = []

        self.smart_video_folder = ""
        self.smart_matcher = SmartMatcher()
        self.smart_results = {}
        self.current_movie_info = None
        self.current_poster = None

        # Peruutustila
        self.download_thread = None
        self.is_downloading = False

        self.base_dir = self.get_base_dir()
        self.env_path = self.base_dir / ".env"

        # User .env path (for installed version)
        self.user_env_path = Path.home() / ".subtitlematcher" / ".env"

        self.setup_window_icon()
        self.build_ui()
        self.load_settings()

        # Set default appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

    def get_base_dir(self):
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
        # Main container with two columns
        self.main_container = ctk.CTkFrame(self)
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Left column - Info panel
        self.info_panel = ctk.CTkFrame(self.main_container, width=300)
        self.info_panel.pack(side="left", fill="y", padx=(0, 10))
        self.info_panel.pack_propagate(False)

        # Right column - Main content
        self.content_panel = ctk.CTkFrame(self.main_container)
        self.content_panel.pack(side="right", fill="both", expand=True)

        # Build info panel
        self.build_info_panel()

        # Build main content
        self.build_main_content()

    def build_info_panel(self):
        # Title
        title_label = ctk.CTkLabel(
            self.info_panel,
            text="Movie Info",
            font=("Segoe UI", 18, "bold")
        )
        title_label.pack(pady=(10, 5))

        # Poster frame
        self.poster_frame = ctk.CTkFrame(self.info_panel, width=250, height=375)
        self.poster_frame.pack(pady=10, padx=10)
        self.poster_frame.pack_propagate(False)

        # Poster placeholder
        self.poster_label = ctk.CTkLabel(
            self.poster_frame,
            text="No poster",
            font=("Segoe UI", 24),
            width=250,
            height=375
        )
        self.poster_label.pack(fill="both", expand=True)

        # Movie title
        self.movie_title_label = ctk.CTkLabel(
            self.info_panel,
            text="No movie selected",
            font=("Segoe UI", 16, "bold"),
            wraplength=280
        )
        self.movie_title_label.pack(pady=(5, 0))

        # Movie year
        self.movie_year_label = ctk.CTkLabel(
            self.info_panel,
            text="",
            font=("Segoe UI", 12)
        )
        self.movie_year_label.pack()

        # IMDb Rating
        self.rating_frame = ctk.CTkFrame(self.info_panel)
        self.rating_frame.pack(pady=5)

        self.rating_label = ctk.CTkLabel(
            self.rating_frame,
            text="N/A",
            font=("Segoe UI", 14, "bold")
        )
        self.rating_label.pack(side="left", padx=5)

        self.vote_count_label = ctk.CTkLabel(
            self.rating_frame,
            text="(0 votes)",
            font=("Segoe UI", 10)
        )
        self.vote_count_label.pack(side="left", padx=5)

        # Genres
        self.genres_label = ctk.CTkLabel(
            self.info_panel,
            text="",
            font=("Segoe UI", 11),
            wraplength=280
        )
        self.genres_label.pack(pady=5)

        # Runtime
        self.runtime_label = ctk.CTkLabel(
            self.info_panel,
            text="",
            font=("Segoe UI", 11)
        )
        self.runtime_label.pack()

        # Overview
        overview_label = ctk.CTkLabel(
            self.info_panel,
            text="Overview:",
            font=("Segoe UI", 12, "bold")
        )
        overview_label.pack(pady=(10, 0))

        self.overview_text = ctk.CTkTextbox(
            self.info_panel,
            height=150,
            width=280,
            wrap="word"
        )
        self.overview_text.pack(pady=5, padx=10, fill="both")
        self.overview_text.configure(state="disabled")

        # Status bar
        self.status_label = ctk.CTkLabel(
            self.info_panel,
            text="Ready",
            font=("Segoe UI", 10),
            text_color="gray"
        )
        self.status_label.pack(pady=5)

    def build_main_content(self):
        # Tab view
        self.tabview = ctk.CTkTabview(self.content_panel)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_manual = self.tabview.add("Manual Match")
        self.tab_smart = self.tabview.add("Smart Match")
        self.tab_settings = self.tabview.add("Settings")
        self.tab_help = self.tabview.add("Help")

        self.build_manual_tab()
        self.build_smart_tab()
        self.build_settings_tab()
        self.build_help_tab()
        self.build_log_window()

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
            text="Smart Match automatically detects movies and TV series from filenames.",
            wraplength=700
        )
        smart_description.pack(pady=(0, 15))

        # Mode selection (Movie / TV Series)
        mode_frame = ctk.CTkFrame(self.smart_frame)
        mode_frame.pack(pady=5, padx=20, fill="x")

        mode_label = ctk.CTkLabel(
            mode_frame,
            text="Mode:",
            font=("Segoe UI", 12)
        )
        mode_label.pack(side="left", padx=5)

        self.smart_mode_var = ctk.StringVar(value="Movie")
        self.smart_mode_menu = ctk.CTkOptionMenu(
            mode_frame,
            values=["Movie", "TV Series"],
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

        # Buttons row 1
        button_frame1 = ctk.CTkFrame(self.smart_frame)
        button_frame1.pack(pady=5)

        self.smart_scan_button = ctk.CTkButton(
            button_frame1,
            text="Scan Library",
            command=self.smart_scan,
            width=150
        )
        self.smart_scan_button.pack(side="left", padx=5)

        self.smart_download_button = ctk.CTkButton(
            button_frame1,
            text="Download Subtitles",
            command=self.smart_download,
            width=150
        )
        self.smart_download_button.pack(side="left", padx=5)

        # Stop-nappi
        self.smart_stop_button = ctk.CTkButton(
            button_frame1,
            text="⏹️ Stop",
            command=self.stop_download,
            width=150,
            fg_color="#8B0000",
            hover_color="#CC0000",
            state="disabled"
        )
        self.smart_stop_button.pack(side="left", padx=5)

        self.smart_match_button = ctk.CTkButton(
            button_frame1,
            text="Auto Match & Copy",
            command=self.smart_match_and_copy,
            width=150
        )
        self.smart_match_button.pack(side="left", padx=5)

        # Browse subtitle file button
        button_frame2 = ctk.CTkFrame(self.smart_frame)
        button_frame2.pack(pady=5)

        self.browse_subtitle_button = ctk.CTkButton(
            button_frame2,
            text="📁 Browse subtitle file...",
            command=self.browse_subtitle_file,
            width=200,
            fg_color="#2B5B2B",
            hover_color="#3A7A3A"
        )
        self.browse_subtitle_button.pack(side="left", padx=5)

        self.browse_subtitle_label = ctk.CTkLabel(
            button_frame2,
            text="",
            wraplength=300,
            font=("Segoe UI", 10)
        )
        self.browse_subtitle_label.pack(side="left", padx=10)

        # Progress bar with percentage label
        progress_frame = ctk.CTkFrame(self.smart_frame)
        progress_frame.pack(pady=15, padx=20, fill="x")

        self.progress_bar = ctk.CTkProgressBar(progress_frame)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(
            progress_frame,
            text="0%",
            font=("Segoe UI", 12, "bold"),
            width=40
        )
        self.progress_label.pack(side="right")

        # Status label for current operation
        self.progress_status_label = ctk.CTkLabel(
            self.smart_frame,
            text="Ready",
            font=("Segoe UI", 11),
            wraplength=700
        )
        self.progress_status_label.pack(pady=(0, 5))

        self.smart_info_label = ctk.CTkLabel(
            self.smart_frame,
            text="Ready",
            wraplength=700
        )
        self.smart_info_label.pack(pady=10)

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

        # === SubDL API Key (Recommended - PRIMARY) ===
        ctk.CTkLabel(
            self.settings_frame,
            text="SubDL API Key (Recommended - PRIMARY)",
            font=("Segoe UI", 12, "bold")
        ).pack(pady=(10, 5))

        self.subdl_entry = ctk.CTkEntry(
            self.settings_frame,
            width=600,
            show="*"
        )
        self.subdl_entry.pack(pady=5)

        subdl_help = ctk.CTkLabel(
            self.settings_frame,
            text="Get your API key at: https://subdl.com",
            font=("Segoe UI", 10),
            text_color="gray"
        )
        subdl_help.pack(pady=(0, 10))

        # === OpenSubtitles API Key (POISTETTU KÄYTÖSTÄ) ===
        # Jätetty pois käytöstä - näytetään vain info
        ctk.CTkLabel(
            self.settings_frame,
            text="OpenSubtitles API Key (POISTETTU KÄYTÖSTÄ)",
            font=("Segoe UI", 10),
            text_color="gray"
        ).pack(pady=(5, 0))
        
        ctk.CTkLabel(
            self.settings_frame,
            text="Ohjelma käyttää vain SubDL API:a. OpenSubtitles on poistettu.",
            font=("Segoe UI", 9),
            text_color="gray"
        ).pack(pady=(0, 10))

        # === TMDB API Key ===
        ctk.CTkLabel(
            self.settings_frame,
            text="TMDB API Key (for IMDb ID lookup & posters)"
        ).pack(pady=(20, 5))

        self.tmdb_entry = ctk.CTkEntry(
            self.settings_frame,
            width=600,
            show="*"
        )
        self.tmdb_entry.pack(pady=5)

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
        if self.show_keys_var.get():
            self.subdl_entry.configure(show="")
            self.tmdb_entry.configure(show="")
        else:
            self.subdl_entry.configure(show="*")
            self.tmdb_entry.configure(show="*")

    def load_settings(self):
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

        if values.get("SUBDL_API_KEY"):
            self.subdl_entry.delete(0, "end")
            self.subdl_entry.insert(0, values["SUBDL_API_KEY"])

        if values.get("TMDB_API_KEY"):
            self.tmdb_entry.delete(0, "end")
            self.tmdb_entry.insert(0, values["TMDB_API_KEY"])

    def save_settings(self):
        subdl_key = self.subdl_entry.get().strip()
        tmdb_key = self.tmdb_entry.get().strip()

        try:
            self.user_env_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.user_env_path, "w", encoding="utf-8") as file:
                file.write(f"SUBDL_API_KEY={subdl_key}\n")
                file.write(f"TMDB_API_KEY={tmdb_key}\n")

            with open(self.env_path, "w", encoding="utf-8") as file:
                file.write(f"SUBDL_API_KEY={subdl_key}\n")
                file.write(f"TMDB_API_KEY={tmdb_key}\n")

            Config.load()
            Config.print_status()
            self.smart_matcher = SmartMatcher()

            self.settings_status_label.configure(
                text="Settings saved successfully."
            )
            self.log_message(f"Settings saved to: {self.user_env_path}")

        except Exception as e:
            self.settings_status_label.configure(
                text="Error saving settings: " + str(e)
            )
            messagebox.showerror("Settings Error", str(e))

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
2. Enter your API keys:
   - SubDL API Key (Recommended - get at subdl.com)
   - TMDB API Key (for IMDb ID lookup & posters)
3. Save settings.
4. Open the Smart Match tab.
5. Select the video library.
6. Select language.
7. Select mode (TV Series or Movie).
8. Click Scan Library to find videos.
9. Click Download Subtitles to fetch subtitles.
10. Click Auto Match & Copy to rename and copy.

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

SubDL (Recommended - PRIMARY):
  Create an account at subdl.com and generate an API key.
  Most reliable service with excellent availability.

TMDB:
  Create an account at themoviedb.org and create an API key.
  Used to automatically fetch IMDb IDs, movie posters and ratings.

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

    def build_log_window(self):
        self.log_frame = ctk.CTkFrame(self.content_panel)
        self.log_frame.pack(pady=(0, 10), padx=10, fill="both", expand=False)

        log_title = ctk.CTkLabel(
            self.log_frame,
            text="Log",
            font=("Segoe UI", 14, "bold")
        )
        log_title.pack(anchor="w", padx=10, pady=(5, 0))

        self.result_box = ctk.CTkTextbox(
            self.log_frame,
            height=150
        )
        self.result_box.pack(pady=5, padx=10, fill="both", expand=True)

    # === STOP ===

    def stop_download(self):
        """Stop the current download process gracefully"""
        try:
            if self.is_downloading:
                # Aseta ensin napit disabled, jotta käyttäjä ei voi painaa uudelleen
                self.smart_stop_button.configure(state="disabled", text="Stopping...")
                self.progress_status_label.configure(text="Stopping...")
                self.log_message("⏹️ Stopping download...")
                
                # Kutsu stop-metodia
                self.smart_matcher.stop("User requested stop")
                
                # Aseta is_downloading False, jotta UI tietää että lataus on pysäytetty
                self.is_downloading = False
                
                # Päivitä UI
                self._set_buttons_enabled(True)
                self.smart_info_label.configure(text="Stopped by user")
                self.progress_status_label.configure(text="Stopped")
                self.log_message("⏹️ Download stopped successfully")
        except Exception as e:
            self.log_message(f"⚠️ Error stopping: {e}")
            # Pakota napit päälle virheen sattuessa
            self._set_buttons_enabled(True)
            self.smart_stop_button.configure(state="disabled", text="⏹️ Stop")

    def _update_progress_ui(self, progress: float, status: str):
        """Paivita progress UI"""
        percent = int(progress)
        self.progress_bar.set(progress / 100)
        self.progress_label.configure(text=f"{percent}%")
        if status:
            self.progress_status_label.configure(text=status)

    def _update_status_ui(self, message: str):
        """Paivita status UI"""
        self.progress_status_label.configure(text=message)

    def _set_buttons_enabled(self, enabled: bool):
        """Ota kayttoon/poista kaytosta napit"""
        state = "normal" if enabled else "disabled"
        self.smart_scan_button.configure(state=state)
        self.smart_download_button.configure(state=state)
        self.smart_match_button.configure(state=state)
        self.smart_mode_menu.configure(state=state)
        self.language_menu.configure(state=state)
        self.smart_video_button.configure(state=state)
        self.browse_subtitle_button.configure(state=state)

        if enabled:
            self.smart_stop_button.configure(state="disabled", text="⏹️ Stop")
            self.is_downloading = False
        else:
            self.smart_stop_button.configure(state="normal", text="⏹️ Stop")
            self.is_downloading = True

    # === API VALIDATION ===

    def validate_api_keys_for_smart_match(self):
        Config.load()

        subdl_key = Config.SUBDL_API_KEY
        tmdb_key = Config.TMDB_API_KEY

        if not subdl_key or not tmdb_key:
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
                                if key == "SUBDL_API_KEY":
                                    subdl_key = value
                                elif key == "TMDB_API_KEY":
                                    tmdb_key = value
                except Exception as e:
                    print(f"Error reading .env: {e}")

        missing_keys = []

        if not subdl_key:
            missing_keys.append("SUBDL_API_KEY (Recommended - PRIMARY)")
        if not tmdb_key:
            missing_keys.append("TMDB_API_KEY")

        if missing_keys:
            self.show_api_warning(missing_keys)
            self.tabview.set("Settings")
            return False

        Config.SUBDL_API_KEY = subdl_key
        Config.TMDB_API_KEY = tmdb_key

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

    # === UUSI: Selaa tekstitystiedosto ===

    def browse_subtitle_file(self):
        """Avaa tiedostonvalintadialogi .srt-tiedoston valintaan"""
        # Tarkista että video on valittu
        if not self.smart_video_folder:
            messagebox.showwarning("Virhe", "Valitse ensin videokirjasto (Smart Match -välilehti).")
            return

        # Valitse tiedosto
        file_path = filedialog.askopenfilename(
            title="Valitse tekstitystiedosto",
            filetypes=[("Tekstitystiedostot", "*.srt"), ("Kaikki tiedostot", "*.*")]
        )
        
        if not file_path:
            return

        # Tarkista että tiedosto on .srt
        if not file_path.lower().endswith('.srt'):
            messagebox.showwarning("Virhe", "Valitse .srt-tiedosto.")
            return

        self.log_message(f"📂 Valittu tekstitystiedosto: {file_path}")
        self.browse_subtitle_label.configure(text=Path(file_path).name)

        # Kysy käyttäjältä, mihin videoon tämä liitetään
        self.show_video_selection_for_subtitle(file_path)

    def show_video_selection_for_subtitle(self, subtitle_path):
        """Näytä lista videoista, joihin tekstitys voidaan liittää."""
        # Skannaa videot
        mode = self.smart_mode_var.get()
        
        if mode == "Movie":
            videos = self.smart_matcher.scan_movie_library(self.smart_video_folder)
            if not videos:
                messagebox.showinfo("Ei videoita", "Ei löytynyt elokuvia kirjastosta.")
                return
            
            # Jos vain yksi video, kopioi suoraan
            if len(videos) == 1:
                self.copy_subtitle_to_video(subtitle_path, videos[0].file_path)
                return
            
            # Muuten näytä valintaikkuna
            self.show_video_selection_dialog(subtitle_path, videos)
        else:
            # TV Series - etsi oikea jakso
            episodes = self.smart_matcher.scan_video_library(self.smart_video_folder)
            if not episodes:
                messagebox.showinfo("Ei videoita", "Ei löytynyt jaksoja kirjastosta.")
                return
            
            # Yritä tunnistaa jakso tekstityksen nimestä
            sub_name = Path(subtitle_path).stem
            matched_episodes = []
            
            for ep in episodes:
                if ep.show_name.lower() in sub_name.lower():
                    matched_episodes.append(ep)
            
            if len(matched_episodes) == 1:
                self.copy_subtitle_to_video(subtitle_path, matched_episodes[0].file_path)
                return
            elif len(matched_episodes) > 1:
                self.show_episode_selection_dialog(subtitle_path, matched_episodes)
            else:
                self.show_episode_selection_dialog(subtitle_path, episodes)

    def show_video_selection_dialog(self, subtitle_path, videos):
        """Näytä valintaikkuna elokuville."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Valitse video")
        dialog.geometry("500x400")
        dialog.transient(self)
        dialog.grab_set()

        label = ctk.CTkLabel(
            dialog,
            text="Valitse video, johon tekstitys liitetään:",
            font=("Segoe UI", 12)
        )
        label.pack(pady=10)

        # Lista
        list_frame = ctk.CTkFrame(dialog)
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        list_widget = ctk.CTkScrollableFrame(list_frame)
        list_widget.pack(fill="both", expand=True)

        selected_video = [None]

        for video in videos:
            btn = ctk.CTkButton(
                list_widget,
                text=f"{video.title} ({video.year or 'N/A'}) - {video.file_path.name}",
                command=lambda v=video: [selected_video.__setitem__(0, v), dialog.destroy()],
                width=450,
                anchor="w"
            )
            btn.pack(pady=2, padx=5, fill="x")

        cancel_btn = ctk.CTkButton(
            dialog,
            text="Peruuta",
            command=dialog.destroy,
            width=100
        )
        cancel_btn.pack(pady=10)

        dialog.wait_window()

        if selected_video[0]:
            self.copy_subtitle_to_video(subtitle_path, selected_video[0].file_path)

    def show_episode_selection_dialog(self, subtitle_path, episodes):
        """Näytä valintaikkuna TV-jaksoille."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Valitse jakso")
        dialog.geometry("500x400")
        dialog.transient(self)
        dialog.grab_set()

        label = ctk.CTkLabel(
            dialog,
            text="Valitse jakso, johon tekstitys liitetään:",
            font=("Segoe UI", 12)
        )
        label.pack(pady=10)

        list_frame = ctk.CTkFrame(dialog)
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        list_widget = ctk.CTkScrollableFrame(list_frame)
        list_widget.pack(fill="both", expand=True)

        selected_episode = [None]

        for ep in episodes[:50]:
            btn = ctk.CTkButton(
                list_widget,
                text=f"{ep.show_name} S{ep.season:02d}E{ep.episode:02d} - {ep.file_path.name}",
                command=lambda e=ep: [selected_episode.__setitem__(0, e), dialog.destroy()],
                width=450,
                anchor="w"
            )
            btn.pack(pady=2, padx=5, fill="x")

        if len(episodes) > 50:
            info = ctk.CTkLabel(
                list_widget,
                text=f"... ja {len(episodes) - 50} muuta jaksoa",
                text_color="gray"
            )
            info.pack(pady=5)

        cancel_btn = ctk.CTkButton(
            dialog,
            text="Peruuta",
            command=dialog.destroy,
            width=100
        )
        cancel_btn.pack(pady=10)

        dialog.wait_window()

        if selected_episode[0]:
            self.copy_subtitle_to_video(subtitle_path, selected_episode[0].file_path)

    def copy_subtitle_to_video(self, subtitle_path, video_path):
        """Kopioi tekstitystiedoston videon viereen oikealla nimellä."""
        try:
            video_dir = Path(video_path).parent
            video_stem = Path(video_path).stem
            subtitle_stem = Path(subtitle_path).stem
            
            # Tarkista onko jo olemassa
            dest_path = video_dir / f"{video_stem}.srt"
            
            if dest_path.exists():
                # Kysy ylikirjoitetaanko
                overwrite = messagebox.askyesno(
                    "Tiedosto on olemassa",
                    f"Tiedosto {dest_path.name} on jo olemassa.\n\nHaluatko korvata sen?"
                )
                if not overwrite:
                    self.log_message(f"⏭️ Ohitettiin: {dest_path.name}")
                    self.browse_subtitle_label.configure(text="Ohitettu")
                    return
            
            # Kopioi tiedosto
            import shutil
            shutil.copy2(subtitle_path, dest_path)
            
            self.log_message(f"✅ Kopioitu: {subtitle_path} -> {dest_path}")
            self.browse_subtitle_label.configure(text=f"Kopioitu: {dest_path.name}")
            
            # Päivitä info
            self.smart_info_label.configure(text=f"Tekstitys kopioitu: {dest_path.name}")
            
            # Kysy haluaako käyttäjä lisätä toisen
            another = messagebox.askyesno(
                "Valmis",
                f"Tekstitys kopioitu onnistuneesti!\n\n{dest_path.name}\n\nHaluatko lisätä toisen tekstityksen?"
            )
            if another:
                self.browse_subtitle_file()
                
        except Exception as e:
            self.log_message(f"❌ Virhe kopioinnissa: {e}")
            messagebox.showerror("Virhe", f"Kopiointi epäonnistui:\n{str(e)}")

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

        self._set_buttons_enabled(False)

        thread = threading.Thread(target=self._run_smart_scan)
        thread.daemon = True
        thread.start()

    def _run_smart_scan(self):
        try:
            # Reset progress
            self.after(0, lambda: self.progress_bar.set(0))
            self.after(0, lambda: self.progress_label.configure(text="0%"))
            self.after(0, lambda: self.progress_status_label.configure(text="Scanning..."))

            mode = self.smart_mode_var.get()

            if mode == "Movie":
                movies = self.smart_matcher.scan_movie_library(self.smart_video_folder)

                self.after(0, lambda: self.log_message("Found " + str(len(movies)) + " movie files"))

                if movies:
                    if movies:
                        self.after(0, lambda: self.update_movie_info(movies[0]))

                    for movie in movies[:10]:
                        year_str = f" ({movie.year})" if movie.year else ""
                        self.after(0, lambda m=movie: self.log_message(f"  {m.title}{year_str}"))

                    self.after(0, lambda: self.smart_info_label.configure(
                        text="Scan complete: " + str(len(movies)) + " movies found"
                    ))
                else:
                    self.after(0, lambda: self.smart_info_label.configure(text="No movies found"))
            else:
                # TV Series mode
                episodes = self.smart_matcher.scan_video_library(self.smart_video_folder)

                self.after(0, lambda: self.log_message("Found " + str(len(episodes)) + " video files"))

                if episodes:
                    show_name = episodes[0].show_name
                    season = episodes[0].season
                    season_count = len([e for e in episodes if e.season == season])

                    self.after(0, lambda: self.log_message("Show: " + show_name))
                    self.after(0, lambda: self.log_message("Season: " + str(season)))
                    self.after(0, lambda: self.log_message("Episodes: " + str(season_count)))

                    # Update info panel for TV show
                    self.after(0, lambda: self.update_show_info(show_name))

                    self.after(0, lambda: self.smart_info_label.configure(
                        text="Scan complete: " + str(len(episodes)) + " episodes found"
                    ))
                else:
                    self.after(0, lambda: self.smart_info_label.configure(text="No episodes found"))

            self.after(0, lambda: self.progress_bar.set(1.0))
            self.after(0, lambda: self.progress_label.configure(text="100%"))
            self.after(0, lambda: self.progress_status_label.configure(text="Scan complete!"))
            self.after(0, lambda: self._set_buttons_enabled(True))

        except Exception as e:
            self.after(0, lambda: self.log_message("Error: " + str(e)))
            self.after(0, lambda: self.smart_info_label.configure(text="Error scanning"))
            self.after(0, lambda: self.progress_status_label.configure(text="Error!"))
            self.after(0, lambda: self._set_buttons_enabled(True))

    def update_show_info(self, show_name: str):
        """Update info panel with TV show details."""
        try:
            # Find show ID
            show_id = self.smart_matcher.find_show_id(show_name)
            if not show_id:
                self.movie_title_label.configure(text=show_name)
                self.movie_year_label.configure(text="")
                self.rating_label.configure(text="N/A")
                self.vote_count_label.configure(text="")
                self.genres_label.configure(text="")
                self.runtime_label.configure(text="TV Series")
                self.overview_text.configure(state="normal")
                self.overview_text.delete("1.0", "end")
                self.overview_text.insert("1.0", "No overview available.")
                self.overview_text.configure(state="disabled")
                self.poster_label.configure(text="No poster", image="")
                return

            # Get show details
            details = self.smart_matcher.get_show_details(show_id)
            if not details:
                return

            # Update labels
            self.movie_title_label.configure(text=details.get("title", show_name))
            year = details.get("year", "")
            self.movie_year_label.configure(text=str(year) if year else "")
            
            # Rating
            rating = details.get("rating", 0)
            votes = details.get("vote_count", 0)
            self.rating_label.configure(text=f"⭐ {rating:.1f}" if rating > 0 else "⭐ N/A")
            self.vote_count_label.configure(text=f"({votes:,} votes)" if votes > 0 else "")
            
            # Genres
            genres = details.get("genres", [])
            self.genres_label.configure(text=", ".join(genres[:3]) if genres else "")
            
            # Runtime
            self.runtime_label.configure(text="TV Series")
            
            # Overview
            overview = details.get("overview", "")
            self.overview_text.configure(state="normal")
            self.overview_text.delete("1.0", "end")
            self.overview_text.insert("1.0", overview if overview else "No overview available.")
            self.overview_text.configure(state="disabled")
            
            # Poster
            poster_path = details.get("poster_path")
            if poster_path:
                self.load_poster(poster_path)
            else:
                self.poster_label.configure(text="No poster", image="")
            
            self.status_label.configure(text=f"Loaded: {details.get('title', show_name)}")
            
        except Exception as e:
            self.log_message(f"Error updating show info: {e}")

    def update_movie_info(self, movie):
        """Update info panel with movie details."""
        try:
            # Get TMDB ID
            tmdb_id = self.smart_matcher.find_movie_id(movie.title, movie.year)
            if not tmdb_id:
                return
            
            # Get movie details from TMDB
            details = self.smart_matcher.get_movie_details(tmdb_id)
            if not details:
                return
            
            # Update labels
            self.movie_title_label.configure(text=details.get("title", movie.title))
            self.movie_year_label.configure(text=str(details.get("year", "")))
            
            # Rating
            rating = details.get("rating", 0)
            votes = details.get("vote_count", 0)
            self.rating_label.configure(text=f"⭐ {rating:.1f}" if rating > 0 else "⭐ N/A")
            self.vote_count_label.configure(text=f"({votes:,} votes)" if votes > 0 else "")
            
            # Genres
            genres = details.get("genres", [])
            self.genres_label.configure(text=", ".join(genres[:3]) if genres else "")
            
            # Runtime
            runtime = details.get("runtime", 0)
            if runtime > 0:
                hours = runtime // 60
                minutes = runtime % 60
                self.runtime_label.configure(text=f"{hours}h {minutes}min" if hours > 0 else f"{minutes}min")
            else:
                self.runtime_label.configure(text="")
            
            # Overview
            overview = details.get("overview", "")
            self.overview_text.configure(state="normal")
            self.overview_text.delete("1.0", "end")
            self.overview_text.insert("1.0", overview if overview else "No overview available.")
            self.overview_text.configure(state="disabled")
            
            # Poster
            poster_path = details.get("poster_path")
            if poster_path:
                self.load_poster(poster_path)
            
            self.status_label.configure(text=f"Loaded: {details.get('title', movie.title)}")
            
        except Exception as e:
            self.log_message(f"Error updating movie info: {e}")

    def load_poster(self, poster_path):
        """Load and display movie poster using CTkImage."""
        try:
            # TMDB poster URL
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
            
            # Download poster
            response = requests.get(poster_url, timeout=10)
            if response.status_code == 200:
                image_data = response.content
                image = Image.open(BytesIO(image_data))
                
                # Resize to fit poster frame
                image = image.resize((250, 375), Image.Resampling.LANCZOS)
                
                # Convert to CTkImage (not PhotoImage)
                ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=(250, 375))
                
                # Update label
                self.poster_label.configure(image=ctk_image, text="")
                self.poster_label.image = ctk_image  # Keep reference
        except Exception as e:
            print(f"Error loading poster: {e}")

    def smart_download(self):
        self.clear_log()

        if not self.validate_api_keys_for_smart_match():
            return

        if not self.smart_video_folder:
            self.log_message("Select video library first")
            return

        language_code = self._get_language_code()
        mode = self.smart_mode_var.get()

        self.log_message("Mode: " + mode)
        self.log_message("Downloading subtitles in: " + language_code)
        self.log_message("Starting download process...")

        self._set_buttons_enabled(False)
        
        # Aseta progress callbackit
        self.smart_matcher.set_callbacks(
            progress_callback=self._update_progress_ui,
            status_callback=self._update_status_ui
        )
        self.smart_matcher.reset_stop()

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
            # Tarkista onko peruutus
            if self.smart_matcher.is_stopped():
                self.after(0, lambda: self.log_message("⏹️ Download stopped by user"))
                self.after(0, lambda: self.smart_info_label.configure(text="Stopped"))
            else:
                self.after(0, lambda: self.log_message(f"❌ Error: {str(e)}"))
                self.after(0, lambda: self.smart_info_label.configure(text=f"Error: {str(e)}"))
        finally:
            # Tämä ajetaan aina, mutta jos sovellus on kaatunut, tämä voi aiheuttaa ongelmia
            try:
                self.after(0, lambda: self._set_buttons_enabled(True))
                self.after(0, lambda: self.smart_stop_button.configure(state="disabled", text="⏹️ Stop"))
                self.after(0, lambda: self.progress_status_label.configure(text="Ready"))
            except:
                pass  # Estä kaatuminen

    def _run_tv_download(self, language_code):
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
        self.smart_matcher.total_episodes = total
        self.smart_matcher.processed_episodes = 0
        self.smart_matcher.failed_episodes = []
        downloaded = 0
    
        for i, episode in enumerate(episodes):
            # Tarkista peruutus
            if self.smart_matcher.is_stopped():
                self.after(0, lambda: self.log_message("Download stopped by user"))
                break
                
            progress = ((i + 1) / total) * 100
            
            # Update progress bar and percentage
            self.after(0, lambda p=progress: self._update_progress_ui(p, f"Processing: S{episode.season:02d}E{episode.episode:02d}"))
    
            subtitle_file = self.smart_matcher.download_subtitles_for_episode(
                episode,
                imdb_id,
                language_code
            )
    
            self.smart_matcher.processed_episodes = i + 1
            
            if subtitle_file:
                downloaded += 1
                self.after(
                    0,
                    lambda f=subtitle_file: self.log_message(f"  Downloaded: {f.name}")
                )
            else:
                self.after(
                    0,
                    lambda e=episode: self.log_message(f"  No subtitle found for S{e.season:02d}E{e.episode:02d}")
                )
    
        self.after(0, lambda: self.log_message(""))
        self.after(
            0,
            lambda: self.log_message("Download Summary:")
        )
        self.after(
            0,
            lambda: self.log_message(f"  Successful: {downloaded}/{total} episodes")
        )
        if downloaded < total:
            self.after(
                0,
                lambda: self.log_message(f"  Failed: {total - downloaded} episodes")
            )
        if self.smart_matcher.is_stopped():
            self.after(
                0,
                lambda: self.log_message("Stopped by user")
            )
            self.after(
                0,
                lambda: self.smart_info_label.configure(
                    text=f"Stopped: {downloaded}/{total} subtitles downloaded"
                )
            )
        else:
            self.after(
                0,
                lambda: self.smart_info_label.configure(
                    text=f"Download complete: {downloaded}/{total} subtitles"
                )
            )
        self.after(0, lambda: self.progress_bar.set(1.0))
        self.after(0, lambda: self.progress_label.configure(text="100%"))
        self.after(0, lambda: self.progress_status_label.configure(text="Complete!"))

    def _run_movie_download(self, language_code):
        movies = self.smart_matcher.scan_movie_library(self.smart_video_folder)

        if not movies:
            self.after(0, lambda: self.log_message("No movies found"))
            return

        total = len(movies)
        downloaded = 0
        failed = []

        for i, movie in enumerate(movies):
            # Tarkista peruutus
            if self.smart_matcher.is_stopped():
                self.after(0, lambda: self.log_message("Download stopped by user"))
                break
                
            progress = ((i + 1) / total) * 100

            # Update progress bar and percentage
            self.after(0, lambda p=progress: self._update_progress_ui(p, f"Processing: {movie.title}"))

            # Update info panel with current movie
            self.after(0, lambda m=movie: self.update_movie_info(m))

            try:
                subtitle_file = self.smart_matcher.download_subtitles_for_movie(
                    movie,
                    language_code
                )

                if subtitle_file:
                    downloaded += 1
                    self.after(
                        0,
                        lambda f=subtitle_file: self.log_message(f"  Downloaded: {f.name}")
                    )
                else:
                    failed.append(movie.title)
                    self.after(
                        0,
                        lambda m=movie: self.log_message(f"  No subtitle found for: {m.title}")
                    )
            except Exception as e:
                failed.append(movie.title)
                self.after(
                    0,
                    lambda m=movie, e=e: self.log_message(f"  Error for {m.title}: {str(e)}")
                )

        self.after(0, lambda: self.log_message(""))
        self.after(
            0,
            lambda: self.log_message("Download Summary:")
        )
        self.after(
            0,
            lambda: self.log_message(f"  Successful: {downloaded}/{total} movies")
        )
        if failed:
            self.after(
                0,
                lambda: self.log_message(f"  Failed ({len(failed)}): {', '.join(failed[:5])}")
            )
            if len(failed) > 5:
                self.after(0, lambda: self.log_message(f"     ... and {len(failed) - 5} more"))
        if self.smart_matcher.is_stopped():
            self.after(
                0,
                lambda: self.log_message("Stopped by user")
            )
            self.after(
                0,
                lambda: self.smart_info_label.configure(
                    text=f"Stopped: {downloaded}/{total} subtitles downloaded"
                )
            )
        else:
            self.after(
                0,
                lambda: self.smart_info_label.configure(
                    text=f"Download complete: {downloaded}/{total} subtitles"
                )
            )

        self.after(0, lambda: self.progress_bar.set(1.0))
        self.after(0, lambda: self.progress_label.configure(text="100%"))
        self.after(0, lambda: self.progress_status_label.configure(text="Complete!"))

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

        self._set_buttons_enabled(False)
        self.smart_matcher.set_callbacks(
            progress_callback=self._update_progress_ui,
            status_callback=self._update_status_ui
        )
        self.smart_matcher.reset_stop()

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
                    lambda v=video, s=subtitle: self.log_message(f"  {v.name} -> {s.name}")
                )

            self.after(0, lambda: self.log_message(""))
            self.after(
                0,
                lambda: self.log_message(f"Completed: {len(results)} files matched")
            )
            self.after(
                0,
                lambda: self.smart_info_label.configure(
                    text=f"Match complete: {len(results)} files"
                )
            )
            self.after(0, lambda: self.progress_bar.set(1.0))
            self.after(0, lambda: self.progress_label.configure(text="100%"))
            self.after(0, lambda: self.progress_status_label.configure(text="Match complete!"))

        except Exception as e:
            self.after(0, lambda: self.log_message(f"Error matching: {str(e)}"))
            self.after(0, lambda: self.smart_info_label.configure(text="Error matching"))
        finally:
            self.after(0, lambda: self._set_buttons_enabled(True))
            self.after(0, lambda: self.smart_stop_button.configure(state="disabled", text="⏹️ Stop"))

    # === HELPER METHODS ===

    def log_message(self, message):
        self.result_box.insert("end", message + "\n")
        self.result_box.see("end")

    def clear_log(self):
        self.result_box.delete("1.0", "end")


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = SubtitleMatcherUI()
    app.mainloop()


if __name__ == "__main__":
    main()