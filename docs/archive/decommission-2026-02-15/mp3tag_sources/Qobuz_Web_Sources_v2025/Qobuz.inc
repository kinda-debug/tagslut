# Qobuz Tag Source for Mp3tag
#
# Initial release by GMK.

[MinAppVersionWin]=3.22
[MinAppVersionMac]=1.8.6
[Settings]=&Qobuz#Qobuz Settings.settings
[BasedOn]=qobuz.com
[AlbumUrl]=https://www.qobuz.com
[WordSeparator]=%20
#[SearchBy]=$if($eql(%albumartist%,'Various Artists'),$regexp(%album%,'\s+\[.+\]$',,1),$regexp(%albumartist%,'\s+\[.+\]$',,1))
[SearchBy]=%albumartist% %album%
[Encoding]=url-utf-8
[IndexFormat]=%type%|%_url%|%Album%|%Artist%|%Date%
[Version]=25.10.12

[ParserScriptIndex]=...
# ###################################################################
#					I  N  D  E  X
# ###################################################################

#DebugWriteInput "%userprofile%\Desktop\Logs\MP3Tag-debug_Qobuz_INDEX_input.log"
#Debug "on" "%userprofile%\Desktop\Logs\MP3Tag-debug_Qobuz_INDEX.log"

FindLine "<ul class=\"product__wrapper\">"
FindLine "<li>"

Do
	JoinUntil "</li>"
	Unspace
	RegexpReplace "(\s)+" "$1"
	RegexpReplace "(>)\s+" "$1"
	RegexpReplace "\s+(<)" "$1"

	# Type
	Say "Album|"

	# URL
	FindInLine "<a class=\"ReleaseCardInfosTitle\" href=\""
	SayUntil "\""
	Say "|"
	JoinUntil "</a>"
	Unspace
	RegexpReplace "(\s)+" "$1"
	RegexpReplace "(>)\s+" "$1"
	RegexpReplace "\s+(<)" "$1"

	# Album
	FindInLine "data-title=\""
	SayUntil "\""
	Say "|"
	KillTag "a"
	KillTag "/a"

	# Artist
	FindInLine "<p class=\"ReleaseCardInfosSubtitle\">"
	SayUntil "<"
	Say "|"

	# Date
	FindInLine "<p class=\"ReleaseCardInfosData\">"
	
	# Dutch
	RegexpReplace "(\d{1,2}) januari (\d{4})" "$2-01-$1"
	RegexpReplace "(\d{1,2}) februari (\d{4})" "$2-02-$1"
	RegexpReplace "(\d{1,2}) maart (\d{4})" "$2-03-$1"
	RegexpReplace "(\d{1,2}) april (\d{4})" "$2-04-$1"
	RegexpReplace "(\d{1,2}) mei (\d{4})" "$2-05-$1"
	RegexpReplace "(\d{1,2}) juni (\d{4})" "$2-06-$1"
	RegexpReplace "(\d{1,2}) juli (\d{4})" "$2-07-$1"
	RegexpReplace "(\d{1,2}) augustus (\d{4})" "$2-08-$1"
	RegexpReplace "(\d{1,2}) september (\d{4})" "$2-09-$1"
	RegexpReplace "(\d{1,2}) oktober (\d{4})" "$2-10-$1"
	RegexpReplace "(\d{1,2}) november (\d{4})" "$2-11-$1"
	RegexpReplace "(\d{1,2}) december (\d{4})" "$2-12-$1"

	# English (US)
	RegexpReplace "January (\d{1,2}), (\d{4})" "$2-01-$1"
	RegexpReplace "February (\d{1,2}), (\d{4})" "$2-02-$1"
	RegexpReplace "March (\d{1,2}), (\d{4})" "$2-03-$1"
	RegexpReplace "April (\d{1,2}), (\d{4})" "$2-04-$1"
	RegexpReplace "May (\d{1,2}), (\d{4})" "$2-05-$1"
	RegexpReplace "June (\d{1,2}), (\d{4})" "$2-06-$1"
	RegexpReplace "July (\d{1,2}), (\d{4})" "$2-07-$1"
	RegexpReplace "August (\d{1,2}), (\d{4})" "$2-08-$1"
	RegexpReplace "September (\d{1,2}), (\d{4})" "$2-09-$1"
	RegexpReplace "October (\d{1,2}), (\d{4})" "$2-10-$1"
	RegexpReplace "November (\d{1,2}), (\d{4})" "$2-11-$1"
	RegexpReplace "December (\d{1,2}), (\d{4})" "$2-12-$1"

	# English (Australia)
	RegexpReplace "(\d{1,2}) January (\d{4})" "$2-01-$1"
	RegexpReplace "(\d{1,2}) February (\d{4})" "$2-02-$1"
	RegexpReplace "(\d{1,2}) March (\d{4})" "$2-03-$1"
	RegexpReplace "(\d{1,2}) April (\d{4})" "$2-04-$1"
	RegexpReplace "(\d{1,2}) May (\d{4})" "$2-05-$1"
	RegexpReplace "(\d{1,2}) June (\d{4})" "$2-06-$1"
	RegexpReplace "(\d{1,2}) July (\d{4})" "$2-07-$1"
	RegexpReplace "(\d{1,2}) August (\d{4})" "$2-08-$1"
	RegexpReplace "(\d{1,2}) September (\d{4})" "$2-09-$1"
	RegexpReplace "(\d{1,2}) October (\d{4})" "$2-10-$1"
	RegexpReplace "(\d{1,2}) November (\d{4})" "$2-11-$1"
	RegexpReplace "(\d{1,2}) December (\d{4})" "$2-12-$1"

	# French
	RegexpReplace "(\d+) janvier (\d+)" "$2-01-$1"
	RegexpReplace "(\d+) février (\d+)" "$2-02-$1"
	RegexpReplace "(\d+) mars (\d+)" "$2-03-$1"
	RegexpReplace "(\d+) avril (\d+)" "$2-04-$1"
	RegexpReplace "(\d+) mai (\d+)" "$2-05-$1"
	RegexpReplace "(\d+) juin (\d+)" "$2-06-$1"
	RegexpReplace "(\d+) juillet (\d+)" "$2-07-$1"
	RegexpReplace "(\d+) août (\d+)" "$2-08-$1"
	RegexpReplace "(\d+) septembre (\d+)" "$2-09-$1"
	RegexpReplace "(\d+) octobre (\d+)" "$2-10-$1"
	RegexpReplace "(\d+) novembre (\d+)" "$2-11-$1"
	RegexpReplace "(\d+) décembre (\d+)" "$2-12-$1"

	# German
	RegexpReplace "(\d+)\. Jänner (\d+)" "$2-01-$1"
	RegexpReplace "(\d+)\. Januar (\d+)" "$2-01-$1"
	RegexpReplace "(\d+)\. Februar (\d+)" "$2-02-$1"
	RegexpReplace "(\d+)\. März (\d+)" "$2-03-$1"
	RegexpReplace "(\d+)\. April (\d+)" "$2-04-$1"
	RegexpReplace "(\d+)\. Mai (\d+)" "$2-05-$1"
	RegexpReplace "(\d+)\. Juni (\d+)" "$2-06-$1"
	RegexpReplace "(\d+)\. Juli (\d+)" "$2-07-$1"
	RegexpReplace "(\d+)\. August (\d+)" "$2-08-$1"
	RegexpReplace "(\d+)\. September (\d+)" "$2-09-$1"
	RegexpReplace "(\d+)\. Oktober (\d+)" "$2-10-$1"
	RegexpReplace "(\d+)\. November (\d+)" "$2-11-$1"
	RegexpReplace "(\d+)\. Dezember (\d+)" "$2-12-$1"

	# Italian
	RegexpReplace "(\d+) gennaio (\d+)" "$2-01-$1"
	RegexpReplace "(\d+) febbraio (\d+)" "$2-02-$1"
	RegexpReplace "(\d+) marzo (\d+)" "$2-03-$1"
	RegexpReplace "(\d+) aprile (\d+)" "$2-04-$1"
	RegexpReplace "(\d+) maggio (\d+)" "$2-05-$1"
	RegexpReplace "(\d+) giugno (\d+)" "$2-06-$1"
	RegexpReplace "(\d+) luglio (\d+)" "$2-07-$1"
	RegexpReplace "(\d+) agosto (\d+)" "$2-08-$1"
	RegexpReplace "(\d+) settembre (\d+)" "$2-09-$1"
	RegexpReplace "(\d+) ottobre (\d+)" "$2-10-$1"
	RegexpReplace "(\d+) novembre (\d+)" "$2-11-$1"
	RegexpReplace "(\d+) dicembre (\d+)" "$2-12-$1"

	# Portuguese
	RegexpReplace "(\d+) de janeiro de (\d+)" "$2-01-$1"
	RegexpReplace "(\d+) de fevereiro de (\d+)" "$2-02-$1"
	RegexpReplace "(\d+) de março de (\d+)" "$2-03-$1"
	RegexpReplace "(\d+) de abril de (\d+)" "$2-04-$1"
	RegexpReplace "(\d+) de maio de (\d+)" "$2-05-$1"
	RegexpReplace "(\d+) de junho de (\d+)" "$2-06-$1"
	RegexpReplace "(\d+) de julho de (\d+)" "$2-07-$1"
	RegexpReplace "(\d+) de agosto de (\d+)" "$2-08-$1"
	RegexpReplace "(\d+) de setembro de (\d+)" "$2-09-$1"
	RegexpReplace "(\d+) de outubro de (\d+)" "$2-10-$1"
	RegexpReplace "(\d+) de novembro de (\d+)" "$2-11-$1"
	RegexpReplace "(\d+) de dezembro de (\d+)" "$2-12-$1"

	# Spanish
	RegexpReplace "(\d+) de enero de (\d+)" "$2-01-$1"
	RegexpReplace "(\d+) de febrero de (\d+)" "$2-02-$1"
	RegexpReplace "(\d+) de marzo de (\d+)" "$2-03-$1"
	RegexpReplace "(\d+) de abril de (\d+)" "$2-04-$1"
	RegexpReplace "(\d+) de mayo de (\d+)" "$2-05-$1"
	RegexpReplace "(\d+) de junio de (\d+)" "$2-06-$1"
	RegexpReplace "(\d+) de julio de (\d+)" "$2-07-$1"
	RegexpReplace "(\d+) de agosto de (\d+)" "$2-08-$1"
	RegexpReplace "(\d+) de septiembre de (\d+)" "$2-09-$1"
	RegexpReplace "(\d+) de octubre de (\d+)" "$2-10-$1"
	RegexpReplace "(\d+) de noviembre de (\d+)" "$2-11-$1"
	RegexpReplace "(\d+) de diciembre de (\d+)" "$2-12-$1"

	RegexpReplace "(\d{4})-(\d{2})-(\d{0,1})\s" "$1-$2-0$3 "
	FindInLine "• "
	SayUntil " •"

	SayNewLine
	MoveLine 1

	# Loop
	FindLine "<li>" 1 1
	Unspace
While "<li>" 200


[ParserScriptAlbum]=...
# ###################################################################
#					A  L  B  U  M
# ###################################################################

#DebugWriteInput "%userprofile%\Desktop\Logs\MP3Tag-debug_Qobuz_ALBUM_input.log"
#Debug "on" "%userprofile%\Desktop\Logs\MP3Tag-debug_Qobuz_ALBUM.log"

# QOBUZ_URL
OutputTo "QOBUZ_URL"
SayOutput "currentURL"

FindLine "<script type=\"application/ld+json\">"
JoinUntil "</script>"
KillTag "script"
KillTag "/script"
Replace "\\/" "/"
Unspace

json "on" "current"

# Album Artist
json_select_object "brand"
	OutputTo "ALBUMARTIST"
	json_select "name"
	If "Various Artists"
		Set "COMPILATION" "1"
	EndIf
	SayRest
json_unselect_object

# Cover Art
OutputTo "COVERURL"
json_select_array "image" 3
SayRest

# Release Date
OutputTo "YEAR"
json_select "releaseDate"
RegexpReplace "(\d{4})-01-01" "$1"
IfVar "yearFormat" "YYYY"
	RegexpReplace "(\d{4})-\d{2}-\d{2}" "$1"
EndIf
Unspace
SayRest

json "off"

GotoLine 1

# Album
FindLine "<span class=\"album-title\">"
Unspace
FindInLine "<span class=\"album-title\">"
OutputTo "ALBUM"
SayUntil "<"

# Genre
FindLine "<li class=\"album-meta__item\">" 3
JoinUntil "</li>"
Unspace
FindInLine "<a class"
FindInLine ">"
OutputTo "GENRE"
SayUntil "<"
GotoLine 1

# Total Discs & Total Tracks
FindLine "<section class=\"album-about\" id=\"about\">"
JoinUntil "</section>"
Unspace
Replace "組み枚数 : " ""
FindInLine "<li class=\"album-about__item\">"
IfGreater 1
	OutputTo "TEMP_TotalDiscs"
	Say "/"
	SayRegexp "\d+\s?(?=[Dd]isco?|disque|ディスク.*)"
	Set "TEMP_TotalTracks"
Else
	OutputTo "TEMP_TotalDiscs"
	Say "/"
	SayRegexp "\d+\s?(?=[Dd]isco?|disque|ディスク.*)"
	OutputTo "TEMP_TotalTracks"
	Say "/"
	SayRegexp "\d+ (?=faixa|[Tt]rack|pist[ae]|traccia)"
EndIf

# Copyright
FindInLine "<p class=\"album-about__copyright\">"
Replace "(C)" "©"
Replace "(P)" "℗"
OutputTo "TEMP_AlbumPublisher"
RegexpReplace "(©\s+)?(\d{4})\s+(.*?)\s+(℗\s+)?\2\s+\3" "© & ℗ $2 $3"
RegexpReplace "(?<=>)(\d{4})" "© $1"
SayRegexp "(?<=℗\s\d{4}\s).*?(?=<)"
RegexpReplace "((?:\w+)(?: \w+)+?)(?: \1)+" "© & ℗ $1"
FindInLine "<p class=\"album-about__copyright\">"
OutputTo "COPYRIGHT"
SayUntil "<"
GotoLine 1

# Tracklist
FindLine "<div class=\"player__item\">"
Unspace

Do
	OutputTo "TRACKS"
	Say "|"

	JoinUntil "</div>"
	Unspace
	KillTag "div"
	KillTag "/div"
	Unspace
	RegexpReplace ".*(?:Disc|DISC|DISCO|DISQUE)\s+(\d+).*" "$1"
	KillTag "p"
	KillTag "/p"
	If ""
		IfNotOutput "TEMP_DiscNumber"
			Set "TEMP_DiscNumber" "1"
		EndIf
	Else
		Set "TEMP_DiscNumber"
		OutputTo "TEMP_DiscNumber"
		SayRest
	EndIf
	MoveLine -1

	# Track
	FindLine "<div class=\"track__item track__item--number\">"
	JoinUntil "</div>"
	OutputTo "TRACK"
	SayRegexp "(?<=span>)\d+"
	IfOutput "TEMP_TotalTracks"
		SayOutput "TEMP_TotalTracks"
	EndIf
	Say "|"
	MoveLine -6

	FindLine "data-track-v2"
	RegexpReplace ".*data-track-v2=\"([^\"]+)\".*" "$1"
	Replace "&quot;" "\""
	json "on" "current"

	# Artist
	OutputTo "TEMP_Artist"
	json_select "item_brand"
	SayRest

	# Label
	OutputTo "LABEL"
	json_select "item_category2"
	SayRest
	Say "|"
	json "off"

	# Featuring
	FindLine "<div class=\"track__items\""
	OutputTo "TEMP_Featured"
	Replace "[" "("
	Replace "]" ")"
	SayRegexp "(?<=\([Ff]eat\. )[^\)]+"
	
	#Title
	OutputTo "TITLE"
	IfOutput "TEMP_Featured"
		Replace "[" "("
		Replace "]" ")"
		RegexpReplace "(.*?)(\s\([Ff]eat.[^\)]+\))" "$1"
	EndIf
	RegexpReplace "(\s)+" "$1"
	RegexpReplace "([\(\)])+" "$1"
	SayRegexp "(?<=title=\")[^\"]+"
	Say "|"

	# Length
	FindLine "<span class=\"track__item track__item--duration\">"
	JoinUntil "</span>"
	OutputTo "_LENGTH"
	SayRegexp "(?<=<span class=\"track__item track__item--duration\">)[^<]+"
	Say "|"

	# DiscNumber
	OutputTo "DISCNUMBER"
	SayOutput "TEMP_DiscNumber"
	SayOutput "TEMP_TotalDiscs"
	Say "|"

	# Credits
	MoveLine 2
	Unspace
	If "<div class=\"track__infos\">"
		FindLine "<p class=\"track__info\">" 1
		JoinUntil "</p>"
		RegexpReplace "Not Applicable[^-]+\s-\s" ""
		RegexpReplace "Unknown[^-]+\s-\s" ""
		RegexpReplace "Various Artists[^-]+\s-\s" ""
		OutputTo "CREDITS"
		SayRegexp "(?<=p class=\"track__info\">)[^<]+" "" "</p>"
		Say "|"

		UnSpace
		Replace "Performer" "MainArtist"
		KillTag "p"
		KillTag "/p"
		Replace " - " " | "
		RegexpReplace ", (?!MainArtist)[^,|]+" ""
		OutputTo "TEMP_MainArtist"
		SayRegExp "[^\|]+(?=, MainArtist)" ", "

		OutputTo "ARTIST"
		IfOutput "TEMP_MainArtist"
			SayOutput "TEMP_MainArtist"
		Else
			IfNotOutput "COMPILATION"
				SayOutput "TEMP_Artist"
			EndIf
		EndIf
		
		# Featured
		IfNotOutput "TEMP_Featured"
			MoveLine -1
			MoveLine 1
			UnSpace
			RegexpReplace "Not Applicable[^-]+\s-\s" ""
			RegexpReplace "Unknown[^-]+\s-\s" ""
			RegexpReplace "Various Artists[^-]+\s-\s" ""
			KillTag "p"
			KillTag "/p"
			Replace " - " " | "
			RegexpReplace ", (?!FeaturedArtist)[^,|]+" ""
			OutputTo "TEMP_Featured"
			SayRegexp "[^\|]+(?=, FeaturedArtist)" ", "
		EndIf
		OutputTo "ARTIST"
		IfOutput "TEMP_Featured"
			# Add parentheses and change spelling/abbrev as desired
			IfOutput "TEMP_MainArtist"
				Say " (feat. "
			EndIf
			SayOutput "TEMP_Featured"
			IfOutput "TEMP_MainArtist"
				Say ")"
			EndIf
		EndIf
		Say "|"

		Set "TEMP_MainArtist"
		Set "TEMP_Artist"
		Set "TEMP_Featured"

		# Composer
		MoveLine -1
		MoveLine 1
		UnSpace
		RegexpReplace "Not Applicable[^-]+\s-\s" ""
		RegexpReplace "Unknown[^-]+\s-\s" ""
		RegexpReplace "Various Artists[^-]+\s-\s" ""
		KillTag "p"
		KillTag "/p"
		Replace " - " " | "
		
		# Trying to remove spaces from all credit roles
		Replace "12-String Acoustic Guitar" "12-StringAcousticGuitar"
		RegexpReplace "(\s[^,]+)\s(Guitar)" "$1$2"
		Replace "Additional Vocals" "AdditionalVocals"
		Replace "Associated Performer" "AssociatedPerformer"
		Replace "Background Vocalist" "BackgroundVocalist"
		Replace "Drum Programmer" "DrumProgrammer"
		Replace "Drum Programming" "DrumProgramming"
		Replace "Executive Producer" "ExecutiveProducer"
		Replace "Lead Vocals" "LeadVocals"
		Replace "Main Artist" "MainArtist"
		Replace "Recording Producer" "RecordingProducer"
		Replace "Recording Engineer" "RecordingEngineer"
		Replace "Sound Effects" "SoundEffects"
		Replace "Wind Controller" "WindController"
		Replace "Work Arranger" "WorkArranger"
		RegexpReplace "Author|Songwriter|Writer" "Composer"
		Replace "ComposerLyricist" "Composer"
		RegexpReplace ", (?!Composer|\w+\s\w+)[^,|]+" "" # Remove all but Composer credits
		RegexpReplace "(, Composer)+" "$1" # Remove duplicate Composer credits
		OutputTo "COMPOSER"
		SayRegexp "[^\|]+(?=, Composer)" ", "
		Say "|"
	
		# Lyricist
		MoveLine -1
		MoveLine 1
		UnSpace
		RegexpReplace "Not Applicable[^-]+\s-\s" ""
		RegexpReplace "Unknown[^-]+\s-\s" ""
		RegexpReplace "Various Artists[^-]+\s-\s" ""
		RegexpReplace "<p class=\"track__info\">([^<]+)</p>" "$1"
		Replace " - " " | "
		Replace "ComposerLyricist" "Lyricist"
		RegexpReplace ", (?!Lyricist)[^,|]+" "" # Remove all but Lyricist credits
		RegexpReplace "(, Lyricist)+" "$1" # Remove duplicate Lyricist credits
		OutputTo "LYRICIST"
		SayRegexp "[^\|]+(?=, Lyricist)" ", "
		Say "|"
		
		# Publisher
		MoveLine -1
		MoveLine 1
		UnSpace
		RegexpReplace "Not Applicable[^-]+\s-\s" ""
		RegexpReplace "Unknown[^-]+\s-\s" ""
		RegexpReplace "Various Artists[^-]+\s-\s" ""
		KillTag "p"
		KillTag "/p"
		Replace " - " " | "
		RegexpReplace ", (?!MusicPublisher)[^,|]+" ""
		RegexpReplace "(, MusicPublisher)+" "$1"
		OutputTo "TEMP_Publisher"
		SayRegexp "[^\|]+(?=, MusicPublisher)" " / "
		OutputTo "PUBLISHER"
		IfOutput "TEMP_Publisher"
			SayOutput "TEMP_Publisher"
			Set "TEMP_Publisher"
		Else
			SayOutput "TEMP_AlbumPublisher"
		EndIf
		Say "|"
		Set "TEMP_Publisher"
	Else
		# Credits
		OutputTo "CREDITS"
		Say "|"
		
		# Artist
		OutputTo "ARTIST"
		SayOutput "TEMP_Artist"
		IfOutput "TEMP_Featured"
			# Add parentheses and change spelling/abbrev as desired
			Say " (feat. "
			SayOutput "TEMP_Featured"
			Say ")"
		EndIf
		Say "|"
		Set "TEMP_Artist"
		Set "TEMP_Featured"
		
		# Composer
		OutputTo "COMPOSER"
		Say "|"
		
		# Lyricist
		OutputTo "LYRICIST"
		Say "|"
		
		# Publisher
		OutputTo "PUBLISHER"
		SayOutput "TEMP_AlbumPublisher"
		Say "|"
	EndIf
	
	# Loop
	FindLine "<div class=\"player__item\">" 1 1
	Unspace

While "<div class=\"player__item\">" 200

Set "TEMP_DiscNumber"
Set "TEMP_TotalDiscs"
Set "TEMP_TotalTracks"
Set "TEMP_AlbumPublisher"
Set "TEMP_Artist"
