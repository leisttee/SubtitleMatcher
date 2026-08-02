# copier.py
from pathlib import Path
import shutil
import os


def copy_matches(matches, overwrite=False):
    """
    Copy subtitle files to match video files.
    
    Args:
        matches: List of (video_path, subtitle_path) tuples
        overwrite: If True, overwrite existing files
        
    Returns:
        Tuple of (copied_count, skipped_count)
    """
    copied_count = 0
    skipped_count = 0
    error_count = 0

    total = len(matches)
    
    for idx, (video, subtitle) in enumerate(matches):
        # Status update
        progress = (idx + 1) / total * 100
        print(f"\r📊 Kopioidaan: {progress:.1f}% ({idx + 1}/{total})", end="")
        
        destination = video.parent / f"{video.stem}{subtitle.suffix}"

        # Tarkista onko jo olemassa
        if destination.exists() and not overwrite:
            skipped_count += 1
            print(f"\n  ⏭️ Ohitetaan (on jo): {destination.name}")
            continue

        try:
            # Varmista että kohdekansio on olemassa
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            # Kopioi tiedosto
            shutil.copy2(subtitle, destination)
            
            # Varmista että kopio onnistui
            if destination.exists():
                copied_count += 1
                if overwrite and destination.exists():
                    print(f"\n  ✅ Korvattiin: {destination.name}")
                else:
                    print(f"\n  ✅ Kopioitiin: {destination.name}")
            else:
                error_count += 1
                print(f"\n  ❌ Kopiointi epäonnistui: {destination.name}")
                
        except PermissionError as e:
            error_count += 1
            print(f"\n  ❌ Lupa evätty: {destination.name} - {e}")
            
        except OSError as e:
            error_count += 1
            print(f"\n  ❌ Tiedostovirhe: {destination.name} - {e}")
            
        except Exception as e:
            error_count += 1
            print(f"\n  ❌ Tuntematon virhe: {destination.name} - {e}")

    print(f"\n\n✅ Kopiointi valmis!")
    print(f"  📁 Kopioitu: {copied_count}")
    print(f"  ⏭️ Ohitettu: {skipped_count}")
    if error_count > 0:
        print(f"  ❌ Virheitä: {error_count}")

    return copied_count, skipped_count


def copy_single_subtitle(video_path: Path, subtitle_path: Path, overwrite: bool = False) -> bool:
    """
    Copy a single subtitle file.
    
    Args:
        video_path: Video file path
        subtitle_path: Subtitle file path
        overwrite: If True, overwrite existing file
        
    Returns:
        True if successful, False otherwise
    """
    destination = video_path.parent / f"{video_path.stem}{subtitle_path.suffix}"
    
    # Tarkista onko jo olemassa
    if destination.exists() and not overwrite:
        print(f"  ⏭️ Ohitetaan: {destination.name} (on jo)")
        return False
    
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(subtitle_path, destination)
        
        if destination.exists():
            print(f"  ✅ Kopioitiin: {destination.name}")
            return True
        else:
            print(f"  ❌ Kopiointi epäonnistui: {destination.name}")
            return False
            
    except Exception as e:
        print(f"  ❌ Virhe kopioinnissa: {e}")
        return False


def get_subtitle_destination(video_path: Path, subtitle_path: Path) -> Path:
    """
    Get the destination path for a subtitle file.
    
    Args:
        video_path: Video file path
        subtitle_path: Subtitle file path
        
    Returns:
        Destination path
    """
    return video_path.parent / f"{video_path.stem}{subtitle_path.suffix}"