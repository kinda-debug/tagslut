def extract_metadata_from_path(flac_path):
    """
    Extract artist, album, and track info from the new folder/filename pattern.
    Example path:
    /root/Artist/(2020) Album [Type]/01. Artist - Title.flac
    """
    # Remove extension
    path_no_ext = os.path.splitext(flac_path)[0]
    # Split path
    parts = path_no_ext.split(os.sep)
    if len(parts) < 3:
        return {'artist': '', 'album': '', 'track': ''}
    # Album folder: e.g. (2020) Album [Type]
    album_folder = parts[-2]
    # Artist folder: e.g. Artist or Various Artists
    artist_folder = parts[-3]
    # Filename: e.g. 01. Artist - Title
    filename = os.path.basename(path_no_ext)
    # Remove track number prefix
    match = re.match(r'^(\d{2})\.\s*(.*)', filename)
    if match:
        filename = match.group(2)
    # If compilation, filename is "Artist - Title", else could be just "Title"
    if ' - ' in filename:
        artist, title = filename.split(' - ', 1)
    else:
        artist = artist_folder
        title = filename
    # Clean up album name (remove year and type in brackets)
    album = re.sub(r'^\(\d{4}\)\s*', '', album_folder)
    album = re.sub(r'\s*\[.*?\]', '', album).strip()
    return {'artist': artist.strip(), 'album': album.strip(), 'track': title.strip()}
import json
import os
import sys
import asyncio
import aiofiles
import glob
import logging
import re
import unicodedata
import csv
from datetime import datetime
from difflib import SequenceMatcher
from logging.handlers import RotatingFileHandler

import pandas as pd
from fuzzywuzzy import fuzz
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm, Prompt
from rich.align import Align

class Config:
    def __init__(self):
        self.SEARCH_DIRECTORY = "/Volumes/DJSSD/DRPBX"
        self.SAVE_DIRECTORY = "/Volumes/DJSSD/DRPBX/"
        self.SUPPORTED_ENCODINGS = ['utf-8', 'iso-8859-1', 'windows-1252']
        self.MIN_MATCH_RATIO = 55
        self.MANUAL_MATCH_THRESHOLD = 40


        # Ensure save directory exists
        os.makedirs(self.SAVE_DIRECTORY, exist_ok=True)

class PlaylistUI:
    def __init__(self, console):
        self.console = console

    def display_header(self):
        """Display the colorful magic box header"""
        title = "♫ GEORGIE'S PLAYLIST MAGIC BOX ♫"
        # Create a cute colorful version of the title
        colorful_title = (
            "[bold pink1]♫[/bold pink1] "
            "[bold bright_magenta]G[/bold bright_magenta]"
            "[bold bright_cyan]E[/bold bright_cyan]"
            "[bold bright_green]O[/bold bright_green]"
            "[bold bright_yellow]R[/bold bright_yellow]"
            "[bold bright_red]G[/bold bright_red]"
            "[bold bright_blue]I[/bold bright_blue]"
            "[bold bright_magenta]E[/bold bright_magenta]"
            "[bold white]'[/bold white]"
            "[bold bright_cyan]S[/bold bright_cyan] "
            "[bold bright_green]P[/bold bright_green]"
            "[bold bright_yellow]L[/bold bright_yellow]"
            "[bold bright_red]A[/bold bright_red]"
            "[bold bright_blue]Y[/bold bright_blue]"
            "[bold bright_magenta]L[/bold bright_magenta]"
            "[bold bright_cyan]I[/bold bright_cyan]"
            "[bold bright_green]S[/bold bright_green]"
            "[bold bright_yellow]T[/bold bright_yellow] "
            "[bold bright_red]M[/bold bright_red]"
            "[bold bright_blue]A[/bold bright_blue]"
            "[bold bright_magenta]G[/bold bright_magenta]"
            "[bold bright_cyan]I[/bold bright_cyan]"
            "[bold bright_green]C[/bold bright_green] "
            "[bold bright_yellow]B[/bold bright_yellow]"
            "[bold bright_red]O[/bold bright_red]"
            "[bold bright_blue]X[/bold bright_blue] "
            "[bold pink1]♫[/bold pink1]"
        )
        
        panel = Panel(
            Align.center(colorful_title),
            border_style="bright_magenta",
            padding=(1, 2),
            title="[bold white]Welcome![/bold white]",
            subtitle="[italic bright_cyan]Making your playlists sparkle[/italic bright_cyan]"
        )
        self.console.print("\n")
        self.console.print(panel)
        self.console.print("\n")

    def display_directory_status(self, search_directory: str):
        """Display directory access status in a table"""
        table = Table(title="[bold magenta]Directory Access Check[/bold magenta]")
        table.add_column("Directory", style="cyan")
        table.add_column("Status", style="magenta")
        table.add_column("Contents", style="green")

        if os.path.exists(search_directory):
            try:
                contents = [f for f in os.listdir(search_directory) if not f.startswith('.')]
                status = "[bold green]Accessible[/bold green]"
                contents_str = ", ".join(contents[:2]) + ("..." if len(contents) > 2 else "")
            except PermissionError:
                status = "[bold red]Not accessible (Permission denied)[/bold red]"
                contents_str = ""
        else:
            status = "[bold yellow]Does not exist[/bold yellow]"
            contents_str = ""

        table.add_row(search_directory, status, contents_str)
        self.console.print(table)

# Global instances
console = Console()
config = Config()
ui = PlaylistUI(console)

# Logging setup
file_handler = RotatingFileHandler("script.log", maxBytes=1024 * 1024, backupCount=5)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(file_handler)

def normalize_string(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', s.lower()) if unicodedata.category(c) != 'Mn')
    s = re.sub(r'[^\w\s]', '', s)
    return re.sub(r'\s+', ' ', s).strip()

def similarity_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_string(a), normalize_string(b)).ratio()

def find_flac_files(search_dir):
    return glob.glob(os.path.join(search_dir, '**', '*.flac'), recursive=True)

async def parse_json_file(file_path):
    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as json_file:
            content = await json_file.read()
            data = json.loads(content)
            if isinstance(data, list):
                data = data[0]
            playlist_name = data.get('name', os.path.splitext(os.path.basename(file_path))[0])
            tracks = data.get('tracks', [])
            parsed_tracks = []
            for track_info in tracks:
                if isinstance(track_info, dict):
                    track = {
                        'track': track_info.get('track', ''),
                        'artist': track_info.get('artist', ''),
                        'album': track_info.get('album', '')
                    }
                    if any(track.values()):
                        parsed_tracks.append(track)
            console.print(f"[cyan]DEBUG: Parsed {len(parsed_tracks)} tracks from JSON[/cyan]")
            return playlist_name, parsed_tracks
    except json.JSONDecodeError as e:
        console.print(f"Error decoding JSON in file {file_path}: {e}", style="bold red")
    except Exception as e:
        console.print(f"An error occurred while processing {file_path}: {e}", style="bold red")
    return None, []

async def parse_csv_file(file_path):
    try:
        tracks = []
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as csv_file:
            content = await csv_file.read()
            csv_reader = csv.DictReader(content.splitlines())
            for row in csv_reader:
                track = {
                    'track': row.get('track', row.get('title', '')),
                    'artist': row.get('artist', ''),
                    'album': row.get('album', '')
                }
                if any(track.values()):
                    tracks.append(track)
        console.print(f"[cyan]DEBUG: Parsed {len(tracks)} tracks from CSV[/cyan]")
        return os.path.splitext(os.path.basename(file_path))[0], tracks
    except Exception as e:
        console.print(f"[red]Error parsing CSV file {file_path}: {e}[/red]")
        return None, []

async def parse_m3u_file(file_path):
    tracks = []
    for encoding in config.SUPPORTED_ENCODINGS:
        try:
            async with aiofiles.open(file_path, 'r', encoding=encoding) as m3u_file:
                lines = await m3u_file.readlines()
                current_track = {}
                for line in lines:
                    line = line.strip()
                    if line.startswith('#EXTINF:'):
                        try:
                            _, info = line.split(',', 1)
                            parts = info.split(' - ', 1)
                            if len(parts) > 1:
                                current_track['artist'] = parts[0].strip()
                                current_track['track'] = parts[1].strip()
                            else:
                                current_track['track'] = info.strip()
                        except ValueError:
                            console.print(f"[yellow]Warning: Malformed #EXTINF line: {line}[/yellow]")
                    elif line and not line.startswith('#'):
                        current_track['path'] = line.strip()
                        album = os.path.basename(os.path.dirname(line))
                        current_track['album'] = album if album else "Unknown Album"
                        tracks.append(current_track)
                        current_track = {}
                console.print(f"[cyan]DEBUG: Parsed {len(tracks)} tracks from M3U[/cyan]")
                return os.path.basename(file_path), tracks
        except UnicodeDecodeError:
            continue
        except Exception as e:
            console.print(f"[red]Error parsing M3U file {file_path}: {e}[/red]")
            return None, []
    return None, []

async def parse_xlsx_file(file_path):
    try:
        df = pd.read_excel(file_path)
        tracks = []
        for _, row in df.iterrows():
            track = {
                'track': row.get('track', row.get('title', '')),
                'artist': row.get('artist', ''),
                'album': row.get('album', '')
            }
            if any(track.values()):
                tracks.append(track)
        console.print(f"[cyan]DEBUG: Parsed {len(tracks)} tracks from XLSX[/cyan]")
        return os.path.splitext(os.path.basename(file_path))[0], tracks
    except Exception as e:
        console.print(f"[red]Error parsing XLSX file {file_path}: {e}[/red]")
        return None, []

async def process_track(track, flac_files, progress=None, task=None, total_tracks=0, current_track=0):
    search_string = f"{track.get('artist', '')} {track.get('track', '')} {track.get('album', '')}"
    search_string_normalized = normalize_string(search_string)
    console.print(f"[cyan]Searching for: {search_string_normalized}[/cyan]")
    best_matches = []
    for flac_file in flac_files:
        # Extract metadata from path
        meta = extract_metadata_from_path(flac_file)
        meta_string = f"{meta['artist']} {meta['track']} {meta['album']}"
        meta_string_normalized = normalize_string(meta_string)
        # Fuzzy match against normalized search string
        ratio = fuzz.ratio(search_string_normalized.lower(), meta_string_normalized.lower())
        partial_ratio = fuzz.partial_ratio(search_string_normalized.lower(), meta_string_normalized.lower())
        token_sort_ratio = fuzz.token_sort_ratio(search_string_normalized.lower(), meta_string_normalized.lower())
        best_score = max(ratio, partial_ratio, token_sort_ratio)
        if best_score >= config.MIN_MATCH_RATIO:
            best_matches.append((flac_file, best_score))
    if best_matches:
        best_matches.sort(key=lambda x: x[1], reverse=True)
        best_match = best_matches[0]
        console.print(Panel(
            f"[green]Auto Match found:[/green]\n"
            f"[blue]Track:[/blue] {track.get('track', 'Unknown')}\n"
            f"[blue]Artist:[/blue] {track.get('artist', 'Unknown')}\n"
            f"[blue]Path:[/blue] {best_match[0]}\n"
            f"[blue]Match ratio:[/blue] {best_match[1]}%"
        ))
        return best_match[0]
    console.print("[yellow]No suitable auto-match found.[/yellow]")
    return None

async def process_playlist(file_path: str, search_dir: str):
    if file_path.lower().endswith('.json'):
        playlist_name, tracks = await parse_json_file(file_path)
    elif file_path.lower().endswith('.m3u'):
        playlist_name, tracks = await parse_m3u_file(file_path)
    elif file_path.lower().endswith('.csv'):
        playlist_name, tracks = await parse_csv_file(file_path)
    elif file_path.lower().endswith('.xlsx'):
        playlist_name, tracks = await parse_xlsx_file(file_path)
    else:
        console.print("[bold red]Unsupported file format[/bold red]")
        return []

    if not tracks:
        console.print("[bold yellow]No tracks found in the playlist.[/bold yellow]")
        return []

    for track in tracks:
        track['playlist'] = playlist_name
        track['source_file'] = file_path

    console.print(Panel(f"[bold cyan]Processing:[/bold cyan] {file_path}\n"
                        f"[bold green]Playlist:[/bold green] {playlist_name}\n"
                        f"[bold yellow]Loaded tracks:[/bold yellow] {len(tracks)}"))

    flac_files = find_flac_files(search_dir)
    for track in tracks:
        match = await process_track(track, flac_files, None, None, len(tracks), 0)
        if match:
            track['matched_path'] = match
    return tracks

async def create_m3u_file(file_path: str, tracks: list):
    """
    Create an M3U file with extended info and relative paths for BluOS compatibility.
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        async with aiofiles.open(file_path, 'w', encoding='utf-8', newline='') as m3u_file:
            await m3u_file.write('#EXTM3U\r\n')
            for track in tracks:
                path = track.get('matched_path')
                if not path:
                    continue
                
                # Use relative path if possible for better portability
                try:
                    # Calculate path relative to the M3U file's directory
                    display_path = os.path.relpath(path, os.path.dirname(file_path))
                except (ValueError, OSError):
                    display_path = path
                
                artist = track.get('artist', 'Unknown Artist')
                title = track.get('track', 'Unknown Track')
                
                # Extended M3U format: #EXTINF:duration,Artist - Title
                # Using -1 for duration as we don't parse FLAC metadata here
                await m3u_file.write(f'#EXTINF:-1,{artist} - {title}\r\n')
                await m3u_file.write(display_path + '\r\n')
                
        console.print(f"[green]M3U playlist created successfully at: {file_path}[/green]")
    except Exception as e:
        console.print(f"[red]An error occurred while creating the M3U file: {e}[/red]")

async def create_unmatched_log(file_path: str, unmatched_tracks: list):
    try:
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as log_file:
            for track in unmatched_tracks:
                await log_file.write(
                    f"Track: {track.get('track', 'Unknown')}, Artist: {track.get('artist', 'Unknown')}, Album: {track.get('album', 'Unknown')}\n")
        console.print(f"[bold green]Unmatched tracks log created successfully at: {file_path}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]An error occurred while creating the unmatched tracks log: {e}[/bold red]")

async def handle_unmatched_tracks(all_unmatched_tracks, search_dir):
    if not all_unmatched_tracks:
        console.print("[bold green]No unmatched tracks to process.[/bold green]")
        return

    console.print(f"[bold yellow]Total unmatched tracks across all playlists: {len(all_unmatched_tracks)}[/bold yellow]")

    if Confirm.ask("[bold yellow]Do you want to review and manually match unmatched tracks?[/bold yellow]"):
        flac_files = find_flac_files(search_dir)
        for track in all_unmatched_tracks:
            console.print(Panel(f"[yellow]Unmatched track details:[/yellow]\n"
                                f"[blue]Playlist:[/blue] {track.get('playlist', 'Unknown')}\n"
                                f"[blue]Track:[/blue] {track.get('track', 'Unknown')}\n"
                                f"[blue]Artist:[/blue] {track.get('artist', 'Unknown')}\n"
                                f"[blue]Album:[/blue] {track.get('album', 'Unknown')}\n"
                                f"[blue]Original Path:[/blue] {track.get('path', 'N/A')}"))

            search_string = f"{track.get('artist', '')} {track.get('track', '')} {track.get('album', '')}"
            best_matches = []
            for flac_file in flac_files:
                file_name = re.sub(r'[^\w\s]', '', os.path.basename(flac_file).lower())
                ratio = fuzz.ratio(search_string.lower(), file_name)
                partial = fuzz.partial_ratio(search_string.lower(), file_name)
                token_sort = fuzz.token_sort_ratio(search_string.lower(), file_name)
                best_ratio = max(ratio, partial, token_sort)
                if best_ratio > config.MANUAL_MATCH_THRESHOLD:
                    best_matches.append((flac_file, best_ratio))

            best_matches.sort(key=lambda x: x[1], reverse=True)
            best_matches = best_matches[:5]

            if best_matches:
                console.print("[cyan]Potential matches:[/cyan]")
                for i, (match, ratio) in enumerate(best_matches, 1):
                    console.print(f"{i}. {os.path.basename(match)} (Match ratio: {ratio}%)")
                console.print("0. Skip this track")
                console.print("M. Enter path manually")

                choice = Prompt.ask("Select an option", choices=[str(i) for i in range(len(best_matches) + 1)] + ['M', 'm'])
                if choice == '0':
                    continue
                elif choice.upper() == 'M':
                    manual_path = Prompt.ask("Enter the full path to the FLAC file").strip().strip("'\"")
                    if manual_path:
                        manual_path = os.path.abspath(os.path.expanduser(manual_path))
                        if os.path.isfile(manual_path) and manual_path.lower().endswith('.flac'):
                            track['matched_path'] = manual_path
                        else:
                            console.print("[bold red]Invalid path or not a FLAC file. Skipping this track.[/bold red]")
                else:
                    track['matched_path'] = best_matches[int(choice) - 1][0]
            else:
                console.print("[yellow]No potential matches found.[/yellow]")
                if Confirm.ask("Do you want to enter the path manually?"):
                    manual_path = Prompt.ask("Enter the full path to the FLAC file").strip().strip("'\"")
                    if manual_path:
                        manual_path = os.path.abspath(os.path.expanduser(manual_path))
                        if os.path.isfile(manual_path) and manual_path.lower().endswith('.flac'):
                            track['matched_path'] = manual_path
                        else:
                            console.print("[bold red]Invalid path or not a FLAC file. Skipping this track.[/bold red]")

    if Confirm.ask("[bold yellow]Do you want to create a log of remaining unmatched tracks?[/bold yellow]"):
        unmatched_log_file = os.path.join(config.SAVE_DIRECTORY, "unmatched_tracks.txt")
        await create_unmatched_log(unmatched_log_file, [track for track in all_unmatched_tracks if "matched_path" not in track])

async def main():
    ui.display_header()
    ui.display_directory_status(config.SEARCH_DIRECTORY)
    
    all_tracks = []
    while True:
        input_files = []
        path = console.input("[bold yellow]Enter the path to a playlist file or directory (or press Enter to quit): [/bold yellow]").strip().strip("'\"")
        if not path:
            break

        path = os.path.expanduser(path)
        path = os.path.abspath(path)

        if os.path.isdir(path):
            for file in os.listdir(path):
                if file.lower().endswith(('.m3u', '.json', '.xlsx', '.csv')):
                    input_files.append(os.path.join(path, file))
            if not input_files:
                console.print("[bold red]No supported files found in directory.[/bold red]")
        elif os.path.isfile(path):
            if path.lower().endswith(('.m3u', '.json', '.xlsx', '.csv')):
                input_files.append(path)
            else:
                console.print("[bold red]Unsupported file format. Please use M3U, JSON, CSV, or XLSX files.[/bold red]")
        else:
            console.print("[bold red]Invalid path.[/bold red]")

        if input_files:
            for file_path in input_files:
                tracks = await process_playlist(file_path, config.SEARCH_DIRECTORY)
                all_tracks.extend(tracks)
            break

    if all_tracks:
        unmatched_tracks = [t for t in all_tracks if 'matched_path' not in t]
        if unmatched_tracks:
            await handle_unmatched_tracks(unmatched_tracks, config.SEARCH_DIRECTORY)
        
        # Check if we have any matches to save
        any_matches = any('matched_path' in t for t in all_tracks)
        if any_matches:
            if Confirm.ask("[bold yellow]Do you want to save the fixed M3U playlists?[/bold yellow]"):
                # Group tracks by source_file to save individual playlists
                playlists = {}
                for track in all_tracks:
                    sf = track['source_file']
                    if sf not in playlists:
                        playlists[sf] = []
                    if 'matched_path' in track:
                        playlists[sf].append(track)
                
                for sf, playlist_tracks in playlists.items():
                    if playlist_tracks:
                        base_name = os.path.splitext(os.path.basename(sf))[0]
                        output_name = f"{base_name}_f.m3u"
                        output_path = os.path.join(config.SAVE_DIRECTORY, output_name)
                        await create_m3u_file(output_path, playlist_tracks)
            else:
                console.print("[yellow]Save cancelled by user.[/yellow]")
        else:
            console.print("[yellow]No tracks were matched. Nothing to save.[/yellow]")

    console.print("[bold green]All playlists processed. Exiting...[/bold green]")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold red]Interrupted by user. Exiting...[/bold red]")
