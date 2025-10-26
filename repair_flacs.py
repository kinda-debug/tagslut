
import subprocess
import os


# Use the unrepaired playlist as input
playlist = "/Volumes/dotad/MUSIC/broken_files.m3u"
output_dir = "/Volumes/dotad/MUSIC/REPAIRED"
updated_playlist = playlist  # Overwrite the unrepaired M3U file

os.makedirs(output_dir, exist_ok=True)

with open(playlist, "r") as f:
    files = [line.strip() for line in f if line.strip() and os.path.isfile(line.strip())]

total = len(files)
unrepaired = []

for idx, src in enumerate(files, 1):
    rel_path = os.path.relpath(src, "/Volumes/dotad/MUSIC")
    dst = os.path.join(output_dir, rel_path)
    if os.path.isfile(dst):
        print(f"[{idx}/{total}] Already repaired: {dst}")
        continue
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    print(f"[{idx}/{total}] Repairing: {src} -> {dst}")
    result = subprocess.run([
        "ffmpeg", "-y", "-i", src, "-c:a", "flac", dst
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not (result.returncode == 0 and os.path.isfile(dst)):
        unrepaired.append(src)

# Update the playlist to only include unrepaired files
with open(updated_playlist, "w") as fout:
    for path in unrepaired:
        fout.write(path + "\n")

print(f"Repair complete. {total - len(unrepaired)} files repaired, {len(unrepaired)} remain in {updated_playlist}.")