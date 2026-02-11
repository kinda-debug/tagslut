```

#    _                   _                        _
#   | |                 | |                      | |
#   | |__    ___   __ _ | |_  _ __    ___   _ __ | |_     ___  ___   _ __ ___
#   | '_ \  / _ \ / _` || __|| '_ \  / _ \ | '__|| __|   / __|/ _ \ | '_ ` _ \
#   | |_) ||  __/| (_| || |_ | |_) || (_) || |   | |_  _| (__| (_) || | | | | |
#   |_.__/  \___| \__,_| \__|| .__/  \___/ |_|    \__|(_)\___|\___/ |_| |_| |_|      _
#                    (_)     | | |        | |                 | |                   | |
#    ___   ___  _ __  _  _ __|_| |_  ___  | |__   _   _   ___ | |_  ___ __   __ ___ | |__    ___  _ __  ___ TM
#   / __| / __|| '__|| || '_ \ | __|/ __| | '_ \ | | | | / __|| __|/ _ \\ \ / // _ \| '_ \  / _ \| '__|/ _ \
#   \__ \| (__ | |   | || |_) || |_ \__ \ | |_) || |_| | \__ \| |_|  __/ \ V /|  __/| | | ||  __/| |  | (_) |
#   |___/ \___||_|   |_|| .__/  \__||___/ |_.__/  \__, | |___/ \__|\___|  \_/  \___||_| |_| \___||_|   \___/
#                       | |                        __/ |
#                       |_|                       |___/
```
# You can buy me a 🍺's, 🍔's or an EP on beatport as a thank you (See link below)
```
https://revolut.me/stephen147
https://revolut.me/stephen147
https://revolut.me/stephen147
https://revolut.me/stephen147
https://revolut.me/stephen147
https://revolut.me/stephen147
https://revolut.me/stephen147
```

# SCRIPTS HOMEPAGE & BUG REPORTING ZONE
https://community.mp3tag.de/t/ws-beatport-com-by-stevehero-release-single-track-artwork-tagging/12568.

## HOW TO INSTALL
- Place files in the zip folder in the `%appdata%\mp3tag\data\sources` directory. This includes the .inc and .scr files along with the .settings file.

## UPDATE HISTORY
---

#### **v6.007** 2024.10.08
- **ADDED:**        `sub_genre` now parsed and added to the genre tag like so: Main Genre / Sub Genre

#### **v6.006** 2024.05.24
- **ADDED:**        Added support for cover thumbnails in list of Tag Sources query results. v3.26 of Mp3tag is required for PC.

  ![2024.05.24 (22-12-01)|409x326](upload://gPlEhMHcL1bs8Vs7kJoCjdgDQNz.gif)

#### **v6.005** 2024.01.01
- **FIX:**          Wrong release date was grabbed. Now using `new_release_date` that uses the correct date.

#### **v6.004** 2023.08.29
- **ADDED:**        Web Source scripts have now a UI settings dialog. Thanks @Florian. This can now be accessed by going to the menu item > Tag Sources > Beatport by stevehero v6 > USER SETTINGS.
- **ADDED:**        `[MinAppVersionMac]=1.8.4` and `[MinAppVersionWin]=3.26` added to check the version of Mp3tag so a message will appear if you're using the wrong version of Mp3tag.
- **CHG:**          Removed GENRE tag-only scripts.

#### **v6.003** 2023.08.03
- **FIX:**          `+%s` needed to be `%s` in DIRECT .src files.

#### **v6.002** 2023.08.02
- **ADDED:**        Option to for formatting how Title (feat. Artist) is done so you can do this (The default) Title (feat. artist) => Title feat. artist. See RegexpReplace in options.
- **FIX:**          `%s` needed to be `+%s` in some .src files.
- **FIX:**          Beatport source code now has multiple lines. `JoinUntil "</html>"` added.
- **FIX:**          `JoinUntil "</html>"` and RegexpReplace functions are now positioned just below `[ParserScriptAlbum]=...` to enable RegexpReplace functions below to work.

#### **V6.001** 2023.07.23
- **ADDED:**        Option to get the Musical key of the tracks along with the Camelot key. New user option `OPTION:INITIALKEY_CAMELOT_KEY_OR_MUSICAL_KEY` inside .inc scripts.
- **CHG:**          Deleted "Beatport by &stevehero v6#RELEASE Search by (Album)Artist + Release (150 Results).src" as `&per_page=150` switch is no longer working plus searches are much faster so no need really for them.
- **CHG:**          Deleted "Beatport by &stevehero v6#RELEASE Search by Release (150 Results).src" as `&per_page=150` switch is no longer working plus searches are much faster so no need really for them.
- **CHG:**          Deleted the date-sorted RELEASE search scripts as Beatport no longer allow sorting Releases by DATE. You can always click the RELEASED header in the search results dialog.
- **CHG:**          Spring cleaned the search by ID scripts to not show the full URL in the Search by input box.
- **FIX:**          With the TRACK scripts, the release name of the album wasn't the true name of the release.

#### **v6.0**   2023.07.19
- **NEW_RELEASE:**  Complete rewrite. Requires Mp3tag v3.21b or later. Scripts no longer use the old slow site. As a result, the scripts should be much faster 😛!

#### OLDER RELEASES
No longer applicable.