import pandas as pd
import re
from pathlib import Path

# Read the input file
with open('/Users/georgeskhawam/Projects/dedupe/uh.txt', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Parse each line
data = []
for line in lines:
    line = line.strip()
    if not line:
        continue
    
    # Extract filename from path
    filepath = Path(line)
    filename = filepath.name
    parent_dir = filepath.parent.name
    
    # Try to parse artist - (year) album - track.ext format
    match = re.match(r'^(.+?) - \((\d{4})\) (.+?) - (\d+)\. (.+)\.flac$', filename)
    
    if match:
        artist = match.group(1)
        year = match.group(2)
        album = match.group(3)
        track_num = match.group(4)
        track_name = match.group(5)
    else:
        # Fallback parsing
        artist = parent_dir
        year = ""
        album = ""
        track_num = ""
        track_name = filename.replace('.flac', '')
    
    data.append({
        'Full Path': line,
        'Artist': artist,
        'Year': year,
        'Album': album,
        'Track Number': track_num,
        'Track Name': track_name,
        'Filename': filename
    })

# Create DataFrame
df = pd.DataFrame(data)

# Export to Excel
output_file = '/Users/georgeskhawam/Projects/dedupe/file_list.xlsx'
df.to_excel(output_file, index=False, engine='openpyxl')

print(f"Excel file created: {output_file}")
print(f"Total files: {len(df)}")
