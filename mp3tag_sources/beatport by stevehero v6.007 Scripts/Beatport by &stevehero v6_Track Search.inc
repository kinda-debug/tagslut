#    _                   _                        _
#   | |                 | |                      | |
#   | |__    ___   __ _ | |_  _ __    ___   _ __ | |_     ___  ___   _ __ ___
#   | '_ \  / _ \ / _` || __|| '_ \  / _ \ | '__|| __|   / __|/ _ \ | '_ ` _ \
#   | |_) ||  __/| (_| || |_ | |_) || (_) || |   | |_  _| (__| (_) || | | | | |
#   |_.__/  \___| \__,_| \__|| .__/  \___/ |_|    \__|(_)\___|\___/ |_| |_| |_| _
#                    (_)     | | |   | |                 | |                   | |
#    ___   ___  _ __  _  _ __|_| |_  | |__   _   _   ___ | |_  ___ __   __ ___ | |__    ___  _ __  ___ TM
#   / __| / __|| '__|| || '_ \ | __| | '_ \ | | | | / __|| __|/ _ \\ \ / // _ \| '_ \  / _ \| '__|/ _ \
#   \__ \| (__ | |   | || |_) || |_  | |_) || |_| | \__ \| |_|  __/ \ V /|  __/| | | ||  __/| |  | (_) |
#   |___/ \___||_|   |_|| .__/  \__| |_.__/  \__, | |___/ \__|\___|  \_/  \___||_| |_| \___||_|   \___/
#                       | |                   __/ |
#                       |_|                  |___/
#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::#
#                             .::  [v6.007 by stevehero™] [2024.10.08] ::.                                #
#  https://community.mp3tag.de/t/ws-beatport-com-by-stevehero-release-single-track-artwork-tagging/12568  #
#                          .:: Please read the 'Version History + Readme' file ::.                        #
#                    .:: DO NOT COPY/MODIFY OR REDISTRIBUTE THIS WITHOUT PERMISSION ::.                   #
#                .:: This file should be stored in your tag sources, sources directory ::.                #
#                                      %APPDATA%\Mp3tag\data\sources                                      #
#                          and requires Mp3tag v3.26 [Win] / 1.8.4 [Mac] or above                         #
#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::#
#       .:: You can buy me a 🍺's, 🍔's or an EP on beatport as a thank you (See link below) ::.         #
#                                    https://revolut.me/stephen147                                        #
#                                    https://revolut.me/stephen147                                        #
#                                    https://revolut.me/stephen147                                        #
#                                    https://revolut.me/stephen147                                        #
#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::#

# TO DO: NA
# WSF Help: https://help.mp3tag.de/main_online.html

[Name]=beatport.com  [v6.007 by stevehero™] (◣_◢)
[MinAppVersionMac]=1.8.4
[MinAppVersionWin]=3.26
[Settings]=Beatport by &stevehero v6#USER SETTIN&GS.settings
[BasedOn]=https://www.beatport.com
[IndexUrl]=https://www.beatport.com/search/tracks?q=
[AlbumUrl]=
[WordSeparator]=+
[IndexFormat]=%_coverurl%|% ↓ EXCLUSIVE%|% ↓ LENGTH%|% ↓ ISRC%|% ↓ TRACK ID (◣_◢)™%|% ↓ RECORD LABEL%|% ↓ RELEASED%|% ↓ CATALOG%|% ↓ TRACK NAME%|% ↓ RELEASE NAME%|% ↓ ARTIST/S%|% ↓ REMIXER/S%|% ↓ GENRE/S%|%_URL%
[Encoding]=url-utf-8

#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::#

[ParserScriptIndex]=...

# debug "on"  "W:\Apps (Portable)\Music Apps\Mp3tag\data\sources\BEATPORT TRACK ParserScriptIndex.html" # Place before headings to want to debug
# debug "off" "W:\Apps (Portable)\Music Apps\Mp3tag\data\sources\BEATPORT TRACK ParserScriptIndex.html" # Place after headings to want to debug (OPTIONAL)

# Remove non JSON from HTML, leaving only valid JSON (Must be first section of code below [ParserScriptIndex] or [ParserScriptAlbum]
JoinUntil "</html>"
RegexpReplace "<!DOCTYPE\s+.+?json\">" ""          # Remove before JSON
RegexpReplace "</script><noscript>.+?</html>" ""   # Remove after JSON

RegexpReplace "(\")artist_name(\":\s*\"[^\"]*\",\s*\"artist_type_name\":\s*\"Artist\")" "$1actual_artist_name$2" # Gives the a new property for the Artist "actual_artist_name"
RegexpReplace "(\")artist_name(\":\s*\"[^\"]*\",\s*\"artist_type_name\":\s*\"Remixer\")" "$1remixer_artist_name$2" # Gives the a new property for the Remixer "remixer_artist_name"
Replace "Deadmau5" "deadmau5"
Replace "|" "$verticalBar()"

# Turn on JSON for the remainder of the script
json "ON" "current"

# Set it up to go into the data object
json_select_object "props"
json_select_object "pageProps"
json_select_object "dehydratedState"
json_select_array "queries" 1 # Select "queries" 1 array (Album info)
json_select_object "state"
json_select_object "data"

# Loop through the data array
json_foreach "data"

json_select_object "release" # _COVERURL
json_select "release_image_uri"
SayRest
Json_unselect_object
Say "|"

json_select "exclusive_period" # EXCLUSIVE
If "5"
Say "✅"
Else
Say "❎"
Endif
Say "|"

json_select "length" # LENGTH
# SayRest
SayDuration "ms"
Say "|"

json_select "isrc" # ISRC
If ""
Say "❎"
Else
SayRest
Endif
Say "|"

json_select "track_id" # ID
SayRest
Say "|"

json_select_object "label" # RECORD LABEL
json_select "label_name"
SayRest
json_unselect_object
Say "|"

json_select "release_date" # RELEASED
RegexpReplace "T\d+:\d+:\d+" ""
SayRest
Say "|"

json_select "catalog_number" # CATALOG
SayRest
Say "|"

json_select "track_name" # TRACK NAME
SayRest
json_select "mix_name"
RegexpReplace "\(+(.+?)\)+" "$1" # Removes any brackets for the mix_name property as the code below will add them. NOTE: Some mix_names don't have any, so this is needed.
IfNot ""
Say " ("
SayRest
Say ")"
Endif
Say "|"

json_select_object "release" # RELEASE NAME
json_select "release_name"
SayRest
json_unselect_object
Say "|"

json_select_many_count "artists" "actual_artist_name" # ARTIST/S
IfGreater 3
json_select_many "artists" "actual_artist_name" " ● " " ● " 3
SayRest
Say " & more..."
Else
json_select_many "artists" "actual_artist_name" " ● " " ● "
SayRest
Endif
Say "|"

json_select_many_count "artists" "remixer_artist_name" # REMIXER/S
If "0"
Say "-"
Endif
IfGreater 3
json_select_many "artists" "remixer_artist_name" " ● " " ● " 3
SayRest
Say " & more..."
Else
json_select_many "artists" "remixer_artist_name" " ● " " ● "
SayRest
Endif
Say "|"

json_select_many_count "genre" "genre_name" # GENRE/S
IfGreater 3
json_select_many "genre" "genre_name" " ● " " ● " 3
SayRest
Say " & more..."
Else
json_select_many "genre" "genre_name" " ● " " ● "
SayRest
Endif
Say "|"

Say "https://www.beatport.com/track/tracks/" # _URL (REQUIRED FOR PREVIEW BUTTON TO WORK)
json_select "track_id"
SayRest

SayNewline
json_foreach_end

#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::#

[ParserScriptAlbum]=...

# debug "on"  "W:\Apps (Portable)\Music Apps\Mp3tag\data\sources\BEATPORT TRACK ParserScriptAlbum.html" # Place before headings to want to debug
# debug "off" "W:\Apps (Portable)\Music Apps\Mp3tag\data\sources\BEATPORT TRACK ParserScriptAlbum.html" # Place after headings to want to debug (OPTIONAL)

# Remove non JSON from HTML, leaving only valid JSON (Must be first section of code below [ParserScriptIndex] or [ParserScriptAlbum]
JoinUntil "</html>"
RegexpReplace "<!DOCTYPE\s+.+?json\">" ""          # Remove before JSON
RegexpReplace "</script><noscript>.+?</html>" ""   # Remove after JSON
Replace "|" "$verticalBar()"

#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::#
#                                      .:: U S E R   O P T I O N S ::.                                    #
#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::#

# You can replace "" to your liking. But change the SettingOriginalMixRemove keys title and description in the Beatport by &stevehero v6#SETTIN&GS file to reflect this.
IfVar "SettingOriginalMixRemove" "true"
RegexpReplace "\(*Original Mix\)*" ""
Endif

# You can replace the RegexpReplace replaces to your liking. But change the SettingFeaturingString choices in the Beatport by &stevehero v6#SETTIN&GS file to reflect this.
IfVar "SettingFeaturingString" "ft."
RegexpReplace "(?i)\s+f(ea)?t\.*\s+" " ft. "       # 'ft. => feat.' 'Ft. => ft.' 'Feat. => ft.'
Endif
IfVar "SettingFeaturingString" "feat."
RegexpReplace "(?i)\s+f(ea)?t\.*\s+" " feat. "     # 'ft. => feat.' 'Ft. => feat.' 'Feat. => feat.'
Endif
IfVar "SettingFeaturingString" "featuring"
RegexpReplace "(?i)\s+f(ea)?t\.*\s+" " featuring " # 'ft. => feat.' 'Ft. => featuring' 'Feat. => featuring'
Endif

# Part of the Beatport by &stevehero v6#SETTIN&GS settings file.
IfVar "SettingFeaturingRemoveBrackets" "true"
RegexpReplace "(?i)(\(|\[)(feat\.\s.+?)(\]|\))" "$2" # Title (feat. artist) => Title feat. artist
Endif

#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::#
#                                   .:: J S O N    P A R S I N G ::.                                      #
#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::#

# Fix the artist URL from the API one to the normal beatport URL
RegexpReplace "(\"name\":\s*\"[^\"]+\"\s*,\s*\"slug\":\s*\")([^\"]+)(\"\s*,\s*\"url\":\s*\")[^\"]+?(\d+)(/*\"\s*)" "$1$2$3https://www.beatport.com/artist/$2/$4$5"

RegexpReplace "(?i)\bep\b" "EP"                               # Fix Ep to EP
RegexpReplace "\s+Remix\)\s+\(Original\s+Mix\)" " Remix)"     # Fix ' Remix (Original Mix)'
Replace "\u2018" "'"                                          # Fix left quote to apostrophe
Replace "\u2019" "'"                                          # Fix right quote to apostrophe
Replace "Deadmau5" "deadmau5"

# Turn on JSON for the remainder of the script
json "ON" "current"

# Set it up to go into the data object
json_select_object "props"
json_select_object "pageProps"
json_select_object "dehydratedState"
json_select_array "queries" 1 # Select "queries" 1 array (Album info)
json_select_object "state"
json_select_object "data"

OutputTo "_TIME_CHECK"  # Shows track length when only a single track is available, , convenient to check time comparison
json_select "length" # All that to get this little blighter
SayRest

OutputTo "ALBUM"
json_select_object "release"
json_select "name"
SayRest
json_unselect_object

OutputTo "ARTIST"
json_select_many "artists" "name" ", " " & "
SayRest

OutputTo "BPM"
json_select "bpm"
SayRest

OutputTo "COVERURL"
json_select_object "release"
json_select_object "image"
json_select "uri"
SayRest
json_unselect_object
json_unselect_object

OutputTo "DATE"
IfVar "SettingDateFormat" "MMDD"
json_select "new_release_date"
RegexpReplace "\d\d\d\d-(\d\d)-(\d\d)" "$1$2"     # DATE in MMDD format
SayRest
Endif
IfVar "SettingDateFormat" "DDMM"
json_select "new_release_date"
RegexpReplace "\d\d\d\d-(\d\d)-(\d\d)" "$2$1"     # DATE in DDMM format
SayRest
Endif
IfVar "SettingDateFormat" "YYYY-MM-DD"
json_select "new_release_date"
SayRest
Endif

OutputTo "BEATPORT_ARTIST_URL"
json_select_many "artists" "url" "\\u005c\\u005c" # There's a fix for this at the top of the code to convert the API URL to a normal one

SayRest

OutputTo "BEATPORT_LABEL_URL"
Say "https://www.beatport.com/label/"
json_select_object "release"
json_select_object "label"
json_select "slug"
SayRest
Say "/"
json_select "id"
SayRest
json_unselect_object
json_unselect_object

OutputTo "BEATPORT_RELEASE_ID"
json_select_object "release"
json_select "id"
SayRest
json_unselect_object

OutputTo "BEATPORT_TRACK_ID"
json_select "id"
SayRest

OutputTo "BEATPORT_TRACK_URL"
Say "https://www.beatport.com/track/"
json_select "slug"
SayRest
Say "/"
json_select "id"
SayRest

OutputTo "GENRE"
json_select_object "genre"
json_select "name"
IfVar "SettingGenreRename" "true"
RegexpReplace "\s*(Dee|Ele|Min|Pro|Tec)(.+?)\s+(House)\s*" "$3 $1$2"  # 'Progressive House' => 'House Progressive', 'Electro House' => 'House Electro', etc.
Endif
SayRest
json_unselect_object
# If there's a subgenre
json_select_object "sub_genre"
IfNot ""
json_select "name"
Say " / "
SayRest
json_unselect_object
Endif
Say "|"

OutputTo "INITIALKEY"
json_select_object "key"
# Camelot Notation here if option chosen
IfVar "SettingInitialkeyFormat" "Camelot"
json_select "camelot_number"
IfVar "SettingInitialkeyAddPadding" "true"
RegexpReplace "^\s*(\d)\s*$" "0$1" # 8A => 08A, 7B => 07B, etc.
Endif
SayRest
json_select "camelot_letter"
SayRest
Endif
# Musical Key here if option chosen
IfVar "SettingInitialkeyFormat" "Musical"
json_select "name"
Replace "b" "♭"
SayRest
Endif
json_unselect_object
Say "|"

OutputTo "ISRC" # International Standard Recording Code
json_select "isrc"
SayRest

OutputTo "MIXARTIST"
json_select_many "remixers" "name" ", " " & "
SayRest

OutputTo "PUBLISHER"
json_select_object "release"
json_select_object "label"
json_select "name"
SayRest
json_unselect_object
json_unselect_object

OutputTo "TITLE"
json_select "name"
SayRest
json_select "mix_name"
RegexpReplace "\(+(.+?)\)+" "$1" # Removes any brackets for the mix_name property as the code below will add them. NOTE: Some mix_names don't have any, so this is needed.
IfNot ""
Say " ("
SayRest
Say ")"
Endif

OutputTo "UNSYNCEDLYRICS"
Say "Release type:\\u0009\\u0009"
Say "Beatport Single Track"
json_select_object "data"
Say "\\u000d\\u000a----------------------------------------------\\u000d\\u000a"
Say "Exclusive to beatport:\\u0009"
json_select "exclusive"
Replace "0" "❎"
Replace "1" "✅"
SayRest
Say "\\u000d\\u000a----------------------------------------------\\u000d\\u000a"
json_select "desc"
If ""
Say "No Description Available on Beatport"
Else
SayRest
Endif
Say "\\u000d\\u000a----------------------------------------------\\u000d\\u000a"
Say "Tagged by:\\u0009\\u0009Mp3Tag w/ beatport.com scripts [v6.007 by stevehero™] (◣_◢) (http://bit.ly/2EmyidV)"

OutputTo "WWW"
Say "https://www.beatport.com/release/"
json_select_object "release"
json_select "slug"
sayrest
Say "/"
json_select "id"
sayrest
json_unselect_object
sayrest

OutputTo "YEAR"
json_select "new_release_date"
IfVar "SettingYearFormat" "DD-MM-YYYY"
json_select "new_release_date"
RegexpReplace "(\d\d\d\d)-(\d\d)-(\d\d)" "$3-$2-$1"   # YEAR in DD-MM-YYYY format
SayRest
Endif
IfVar "SettingYearFormat" "YYYY"
json_select "new_release_date"
RegexpReplace "(\d\d\d\d)-\d\d-\d\d" "$1"             # YEAR in YYYY format
SayRest
Endif
IfVar "SettingYearFormat" "YYYY-MM-DD"
json_select "new_release_date"
SayRest
Endif

# #:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::#
# #                            .:: T A G    C U S T O M I Z A T I O N ::.                                   #
# # • Add your own web source scripting here                                                                #
# # • ALBUM [CATALOG #] is part of the external setting file, DO NOT EDIT THIS!                             #
# # • To disable place a "#" in front of each line of code between the headings. e.g.                       #
# # OutputTo "ALBUMARTIST"                                                                                  #
# # SayOutput "ARTIST"                                                                                      #
# #:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::#

# ALBUMARTIST
OutputTo "ALBUMARTIST"
SayOutput "ARTIST"
# ALBUM ARTIST
OutputTo "ALBUM ARTIST"
SayOutput "ARTIST"
# ALBUM [BP SINGLE TRACK #]
IfVar "SettingCatIDNoAlbumAppend" "true"
OutputTo "ALBUM"
Say " [BP SINGLE TRACK #"
SayOutput "BEATPORT_TRACK_ID"
Say "]"
Endif
# CATALOG #
OutputTo "CATALOG #"
Say "BP SINGLE TRACK #"
SayOutput "BEATPORT_TRACK_ID"
# COMMENT
OutputTo "COMMENT"
SayOutput "INITIALKEY"
# MEDIATYPE
OutputTo "MEDIATYPE"
Say "BEATPORT STORE"
# RELEASETIME
OutputTo "RELEASETIME"
SayOutput "YEAR"
Say "T00:00:00Z"
# MEDIATYPE_ORIGINAL
OutputTo "MEDIATYPE_ORIGINAL"
Say "WEB"
# STYLE
OutputTo "STYLE"
Say "Electronic"
# DISCNUMBER
OutputTo "DISCNUMBER"
Say "1"
# DISCTOTAL
OutputTo "DISCTOTAL"
Say "1"
# TOTAL TRACKS
OutputTo "TOTALTRACKS"
IfVar "SettingTotaltracksAddPadding" "true"
Say "01"
Else
Say "1"
Endif
# TRACK
OutputTo "TRACK"
IfVar "SettingTrackAddPadding" "true"
Say "01"
Else
Say "1"
Endif
IfVar "SettingTrackTotaltracksAppend" "true"
Say "/"
SayOutput "TOTALTRACKS"
Endif

#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::#
#                                .:: R E M O V E    F I E L D S ::.                                       #
# • DO NOT EDIT THIS!                                                                                     #
# • This is controlled by an external settings file.                                                      #
#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::#

IfVar "SettingSet_LENGTH" "true"
Set "_LENGTH"
EndIf
IfVar "SettingSet_TIME_CHECK" "true"
Set "_TIME_CHECK" # Shows track length when only a single track is available, , convenient to check time comparison
EndIf
IfVar "SettingSetALBUM" "true"
Set "ALBUM"
EndIf
IfVar "SettingSetALBUMARTIST" "true"
Set "ALBUMARTIST" # ITUNES USES
EndIf
IfVar "SettingSetALBUM ARTIST" "true"
Set "ALBUM ARTIST" # EXTRA FIELD, ALBUM ARTIST USED IN VLC, FOOBAR 2000 AND OTHERS PLEASE CHECK YOUR MUSIC PLAYER FIRST
EndIf
IfVar "SettingSetARTIST" "true"
Set "ARTIST"
EndIf
IfVar "SettingSetBEATPORT_ARTIST_URL" "true"
Set "BEATPORT_ARTIST_URL"
EndIf
IfVar "SettingSetBEATPORT_LABEL_URL" "true"
Set "BEATPORT_LABEL_URL"
EndIf
IfVar "SettingSetBEATPORT_RELEASE_ID" "true"
Set "BEATPORT_RELEASE_ID"
EndIf
IfVar "SettingSetBEATPORT_TRACK_ID" "true"
Set "BEATPORT_TRACK_ID"
EndIf
IfVar "SettingSetBEATPORT_TRACK_URL" "true"
Set "BEATPORT_TRACK_URL"
EndIf
IfVar "SettingSetBPM" "true"
Set "BPM"
EndIf
IfVar "SettingSetCATALOG#" "true"
Set "CATALOG #"
EndIf
IfVar "SettingSetCOMMENT" "true"
Set "COMMENT" # EXTRA FIELD
EndIf
IfVar "SettingSetCOMPILATION" "true"
Set "COMPILATION"
EndIf
IfVar "SettingSetCOVERURL" "true"
Set "COVERURL"
EndIf
IfVar "SettingSetDATE" "true"
Set "DATE"
EndIf
IfVar "SettingSetDISCNUMBER" "true"
Set "DISCNUMBER" # EXTRA FIELD
EndIf
IfVar "SettingSetDISCTOTAL" "true"
Set "DISCTOTAL" # EXTRA FIELD
EndIf
IfVar "SettingSetGENRE" "true"
Set "GENRE"
EndIf
IfVar "SettingSetINITIALKEY" "true"
Set "INITIALKEY"
EndIf
IfVar "SettingSetISRC" "true"
Set "ISRC" # International Standard Recording Code
EndIf
IfVar "SettingSetMEDIATYPE" "true"
Set "MEDIATYPE" # EXTRA FIELD
EndIf
IfVar "SettingSetMEDIATYPE_ORIGINAL" "true"
Set "MEDIATYPE_ORIGINAL" # EXTRA FIELD
EndIf
IfVar "SettingSetMIXARTIST" "true"
Set "MIXARTIST"
EndIf
IfVar "SettingSetPUBLISHER" "true"
Set "PUBLISHER" # RECORD LABEL
EndIf
IfVar "SettingSetRELEASETIME" "true"
Set "RELEASETIME"
EndIf
IfVar "SettingSetSTYLE" "true"
Set "STYLE"
EndIf
IfVar "SettingSetTITLE" "true"
Set "TITLE"
EndIf
IfVar "SettingSetTOTALTRACKS" "true"
Set "TOTALTRACKS" # EXTRA FIELD
EndIf
IfVar "SettingSetUNSYNCEDLYRICS" "true"
Set "UNSYNCEDLYRICS" # DESCRIPTION ON BEATPORT
EndIf
IfVar "SettingSetUPC" "true"
Set "UPC" # Universal Product Code
EndIf
IfVar "SettingSetWWW" "true"
Set "WWW"
EndIf
IfVar "SettingSetYEAR" "true"
Set "YEAR"
EndIf

#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::#
#                                       .:: T H E E    E N D ::.                                          #
#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::#
#    _                   _                        _
#   | |                 | |                      | |
#   | |__    ___   __ _ | |_  _ __    ___   _ __ | |_     ___  ___   _ __ ___
#   | '_ \  / _ \ / _` || __|| '_ \  / _ \ | '__|| __|   / __|/ _ \ | '_ ` _ \
#   | |_) ||  __/| (_| || |_ | |_) || (_) || |   | |_  _| (__| (_) || | | | | |
#   |_.__/  \___| \__,_| \__|| .__/  \___/ |_|    \__|(_)\___|\___/ |_| |_| |_| _
#                    (_)     | | |   | |                 | |                   | |
#    ___   ___  _ __  _  _ __|_| |_  | |__   _   _   ___ | |_  ___ __   __ ___ | |__    ___  _ __  ___ TM
#   / __| / __|| '__|| || '_ \ | __| | '_ \ | | | | / __|| __|/ _ \\ \ / // _ \| '_ \  / _ \| '__|/ _ \
#   \__ \| (__ | |   | || |_) || |_  | |_) || |_| | \__ \| |_|  __/ \ V /|  __/| | | ||  __/| |  | (_) |
#   |___/ \___||_|   |_|| .__/  \__| |_.__/  \__, | |___/ \__|\___|  \_/  \___||_| |_| \___||_|   \___/
#                       | |                   __/ |
#                       |_|                  |___/