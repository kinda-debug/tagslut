# Picard Scripts — FINAL_LIBRARY naming

These scripts are **library-only** and aim to match the repo's canonical layout:

```
<Album Artist>/
  (<Release Year>) <Album Title>/
    <Artist-or-AlbumArtist> – (<Release Year>) <Album Title> – <Disc><Track> <Track Title>.<ext>
```

Notes:
- This does **not** set Picard's **Destination directory**. It only returns the **relative** subpath.
- Uses **en dash** `–` (U+2013) as the separator.
- Multi-disc numbering uses `101`, `202`, etc.
- Various Artists detection includes a heuristic for pathological `albumartist` values that are long comma-lists (to avoid `path too long` situations).

## File naming script (Options → File naming → Script)

```picard
$set(_year,$if2($left(%date%,4),$left(%originaldate%,4),%year%,0000))
$set(_is_va,$or($eq($lower(%albumartist%),various artists),$eq($lower(%albumartist%),va),$eq(%compilation%,1),$eq(%itunescompilation%,1),$rsearch(%albumartist%,\,.*\,.*\,)))
$set(_folder_artist,$if(%_is_va%,Various Artists,%albumartist%))
$set(_file_artist,$if(%_is_va%,%artist%,%albumartist%))
$set(_disc_track,$if($or($gt(%totaldiscs%,1),$gt(%discnumber%,1)),$num($add($mul(%discnumber%,100),%tracknumber%),3),$num(%tracknumber%,2)))
%_folder_artist%/(%_year%) %album%/%_file_artist% – (%_year%) %album% – %_disc_track% %title%.%_extension%
```

## Optional tagger script (Script → Tagger Script)

If you want the **metadata itself** to be normalized (so the filenames are *purely* derived from tags), run this before saving:

```picard
$if($rsearch(%albumartist%,\,.*\,.*\,),$set(albumartist,Various Artists))
```
