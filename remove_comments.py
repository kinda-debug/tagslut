#!/usr/bin/env python3
import re
from pathlib import Path

# XML: remove entire line <key>Comments</key><string>...</string>
xml_pattern = re.compile(r'\t*<key>Comments</key><string>[^<]*</string>\r?\n')

# JSON flat: remove ', Comments <any value>' up to the next comma
json_pattern = re.compile(r',\s*Comments\s+[^,]+(?=,)')

XML_FILES = [
    '/Volumes/MUSIC/Libraryimp.xml',
]

JSON_FILES = [
    '/Users/georgeskhawam/Projects/tagslut/original_rxb.json',
    '/Users/georgeskhawam/Projects/tagslut/edited_rxb.json',
    '/Users/georgeskhawam/Projects/tagslut/editedexpitunes.json',
    '/Users/georgeskhawam/Projects/tagslut/setB.json',
    '/Users/georgeskhawam/Projects/tagslut/setA.json',
    '/Users/georgeskhawam/Projects/tagslut/playlist.json',
    '/Users/georgeskhawam/Projects/tagslut/iTunes-Library.json',
    '/Users/georgeskhawam/Projects/tagslut/Libraryimp.json',
]

def process(path, pattern):
    p = Path(path)
    if not p.exists():
        print(f'SKIP   {p.name}')
        return
    text = p.read_text(encoding='utf-8')
    new_text, count = pattern.subn('', text)
    if count:
        p.write_text(new_text, encoding='utf-8')
    status = 'OK   ' if count else 'CLEAN'
    print(f'{status}  {p.name}  -- {count} removed')

print('-- XML --')
for f in XML_FILES:
    process(f, xml_pattern)

print('-- JSON --')
for f in JSON_FILES:
    process(f, json_pattern)
