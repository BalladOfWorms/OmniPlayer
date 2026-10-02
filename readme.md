# OmniPlayer

A small, dark-themed music player for **FINAL FANTASY XI**'s soundtrack files (`.bgw`), by **BalladOfWorms**.

OmniPlayer plays the music straight from your own FFXI installation, looping each track exactly the way the game does. It recognises the tracks and names them for you, and can export them to MP3, FLAC or WAV.

> **No music is included with or distributed by OmniPlayer.** It only plays and converts the `.bgw` files already on your PC from your own installation of FINAL FANTASY XI. See the [disclaimer](#disclaimer).

---

## Features

- **Plays FFXI's music as the game does.** Each track plays its intro, then loops its loop section seamlessly, forever. One click switches to playing each track once, then moving on to the next.
- **Tracks are recognised and named automatically.** A built-in catalogue of over 200 tracks, from the original game through The Voracious Resurgence, fills in each track's name, composer, expansion and where it's heard in game. It works on the game's own folders and on copies you've moved elsewhere.
- **One library from many folders.** Import your whole FINAL FANTASY XI folder, or any folders of `.bgw` files. Each import adds to the list.
- **A library you can arrange:**
  - sort by any column, with numbers sorted as numbers;
  - drag columns to reorder them, resize them, or hide them from the settings menu;
  - search as you type, across names, files, expansions and composers.
- **Favourites and playlists.** Click a heart to favourite a track. Build playlists from the right-click menu, and switch between them from the settings menu.
- **Track info.** See each track's file, path, length, format and loop points. Edit its name, expansion and composer; your edits always take priority over the catalogue.
- **Export to MP3, FLAC or WAV.** Each track is saved as it plays once through and tagged with title, album, track number and composer.
- **Mini player.** Fold the window down to just the now-playing panel, which stays on top of other windows.
- **Look and feel.** Dark (true black) and light themes, a live waveform line that moves with the music, rounded panels, and a borderless window.

---

## Download and run

1. Download `OmniPlayer.exe` from the Releases page.
2. Run it. Windows may show a SmartScreen "unknown publisher" warning because the exe isn't code-signed; choose **More info → Run anyway**.
3. Click the **OmniPlayer icon** at the top left, then **Import folder…**, and pick your FFXI folder, for example:

   ```
   C:\Program Files (x86)\PlayOnline\SquareEnix\FINAL FANTASY XI
   ```

   The exact path depends on where FFXI is installed. The music lives in its `sound`, `sound2`, `sound3` … `\win\music\data` folders. Importing the top-level `FINAL FANTASY XI` folder picks them all up at once.

That's all: everything OmniPlayer needs is inside the exe.

---

## Using OmniPlayer

| To… | Do this |
|---|---|
| Play a track | Double-click it, or select it and press **Enter** |
| Play / pause | The round button, or **Space** |
| Seek | Click or drag anywhere on the progress line |
| Loop forever / play once | The repeat button (red = loops forever, as in game) |
| Shuffle | The shuffle button (red = on) |
| Favourite a track | Click the ♡ in its row, or right-click → Add to favourites |
| Sort | Click a column heading: once A→Z, twice Z→A, three times back to library order |
| Move or resize a column | Drag its heading, or drag the divider between headings |
| Show or hide columns | Settings menu → Columns |
| Edit a track's name, expansion or composer | Right-click → **Track info…** (or **F2**) |
| Add tracks to a playlist | Right-click → Add to playlist |
| Switch playlist | Settings menu → Playlists |
| Remove tracks from the list | Right-click → Remove from list (or **Del**). Files on disk are never touched; importing the folder again brings them back |
| Select several tracks | Ctrl+click, Shift+click, drag down the rows, or **Ctrl+A** |
| Export | Right-click → Export…, or Settings menu → Export selected… |
| Mini player | The square button at the bottom right of the player; drag an empty part of the panel to move it |
| Move the window | Drag the title strip |
| Resize the window | Drag the ◢ in the bottom-right corner |
| Settings menu | Click the OmniPlayer icon at the top left |

---

## How tracks are recognised

The same `musicNNN.bgw` number can appear in more than one of the game's sound folders, so OmniPlayer never goes by the number alone:

1. **By sound folder.** Files under `sound\`, `sound2\`, `sound3\` and so on are matched against that folder's own part of the catalogue.
2. **By what's in the folder.** For a copied folder, or one the catalogue isn't tied to yet, OmniPlayer looks at which track numbers the folder holds. If one expansion accounts for enough of them to rule out chance, the folder's tracks are named from that expansion. A single matching number on its own is never trusted.
3. **By fingerprint.** Once a track has been recognised, OmniPlayer remembers its file's fingerprint, so a copy is still recognised wherever you move it.

Track info's **Catalogue** line shows how each track was recognised, or that it wasn't. Short jingles and fanfares that aren't in the community song lists stay under their file names; rename them yourself in Track info.

---

## Exporting

**Export…** saves the selected tracks as MP3 (128–320 kbps), FLAC (lossless) or WAV. Each file contains the track as it plays once through: intro and loop section once, with no repeats and no fade. MP3 and FLAC files are tagged with title, album, track number and composer.

The MP3 and FLAC encoders are built into the exe. When running from source, OmniPlayer offers to download either one the first time you use it.

---

## Where OmniPlayer keeps things

- **Your names, expansions, composers and favourites:** `bgw_names.json` inside each imported folder, so they travel with the folder. For folders that can't be written to (such as the game's own install under Program Files), they go in the settings folder instead.
- **Everything else:** `%APPDATA%\OmniPlayer\`
  - `settings.json`: window size and position, theme, columns, sort, imported folders and so on
  - `playlists.json`: your playlists
  - `fingerprints.json`: recognised tracks, so copies are still recognised later
  - `info_*.json`: cached track lengths, to keep big libraries quick to open

Deleting `%APPDATA%\OmniPlayer` resets OmniPlayer. Your music files are never modified.

---

## Running from source and building the exe

**Requirements:** Windows 10 or 11 and Python 3.10 or newer.

```
py -m pip install pygame-ce pillow lameenc
py OmniPlayer.py
```

Running from source, OmniPlayer offers to download [vgmstream](https://github.com/vgmstream/vgmstream) (the decoder) on first run.

**To build `OmniPlayer.exe`,** put `OmniPlayer.py`, `OmniPlayerBuild.bat` and `OmniPlayer.ico` in one folder and run `OmniPlayerBuild.bat`. It:

1. installs or updates the build requirements (PyInstaller, pygame-ce, lameenc, Pillow);
2. downloads vgmstream and the FLAC encoder (once; they're kept for later builds);
3. builds a single `OmniPlayer.exe` with all of them packed inside, and moves it next to the source.

---

## Credits

OmniPlayer is written by **BalladOfWorms**. It is built on:

- **[vgmstream](https://github.com/vgmstream/vgmstream)**: decodes the `.bgw` files (ISC-style licence)
- **[FLAC](https://xiph.org/flac/)** by Xiph.Org: FLAC export (`flac.exe`, distributed under its own licences, included alongside it)
- **[LAME](https://lame.sourceforge.io/)** via **[lameenc](https://pypi.org/project/lameenc/)**: MP3 export (LGPL)
- **[pygame-ce](https://pyga.me/)**: audio playback (LGPL)
- **[Pillow](https://python-pillow.org/)**: smooth-edged drawing (HPND licence)

Track names, composers and locations were compiled from community-maintained FFXI music listings.

---

## License

OmniPlayer is released under the [MIT License](LICENSE): © 2026 BalladOfWorms. The components listed under [Credits](#credits) keep their own licences. The MIT License covers OmniPlayer's own code only. It grants no rights to FINAL FANTASY XI's music, which belongs to Square Enix.

---

## Disclaimer

**No music is included with or distributed by OmniPlayer.** OmniPlayer plays and converts the `.bgw` files from your own installation of FINAL FANTASY XI. Please don't share exported music.

FINAL FANTASY XI and its music are © SQUARE ENIX CO., LTD. All rights reserved. OmniPlayer is a free, fan-made tool. It is not affiliated with, endorsed by, or supported by Square Enix. It does not read or modify the game client or its data beyond playing the music files.