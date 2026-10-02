# -*- coding: utf-8 -*-
"""
OmniPlayer -- listen to Final Fantasy XI's soundtrack straight from the
game's own .bgw files, looping exactly the way the game loops them.

Author: BalladOfWorms

WHAT YOU NEED
  * vgmstream's command-line decoder. OmniPlayerBuild.bat packs it into
    the exe, so a built exe needs nothing else. Run as a script (or from
    an exe built without it), OmniPlayer offers to download vgmstream's
    official Windows build from GitHub the first time it runs without it. To do it by hand instead, extract everything in
    vgmstream-win64.zip (vgmstream-cli.exe and its .dll files) next to
    this script or its exe, or into any folder directly beside it.
  * pip install pygame-ce          (audio playback)
  * pip install lameenc            (optional -- only for MP3 export)
  * FLAC export uses Xiph's flac.exe -- packed in by OmniPlayerBuild.bat,
    or fetched by OmniPlayer the first time FLAC export is used.
  * pip install pillow             (smooth edges on the player controls;
                                    without it they are drawn plainer)

BUILDING THE EXE
  OmniPlayerBuild.bat (or: pyinstaller --onefile --windowed OmniPlayer.py),
  then put the vgmstream files beside OmniPlayer.exe.

HOW IT WORKS
  vgmstream decodes a track to plain audio in a fraction of a second and
  reports the game's loop points. The player plays the intro once, then
  repeats the loop section with no gap at the seam -- the same thing the
  game does. Track names are kept in bgw_names.json inside the folder you
  open (falling back to the settings folder if that one is read-only), so
  the .bgw files keep their original names and the names travel with the
  folder when you copy it.
"""

import io
import json
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave

APP_NAME = "OmniPlayer"
APP_VERSION = "1.0.1"

DEFAULT_ALBUM = "Final Fantasy XI"
NAMES_FILE = "bgw_names.json"
INFO_CACHE_FILE = "bgw_info_cache.json"

EXPANSIONS = ("Original", "Rise of the Zilart", "Chains of Promathia",
              "Treasures of Aht Urhgan", "Wings of the Goddess",
              "A Crystalline Prophecy", "A Moogle Kupo d'Etat", "A Shantotto Ascension",
              "Vision of Abyssea", "Scars of Abyssea", "Heroes of Abyssea",
              "Seekers of Adoulin", "Rhapsodies of Vana'diel",
              "The Voracious Resurgence", "Abyssea", "Add-on Scenarios & Battle Areas",
              "Other")

# ── Track catalogue ──────────────────────────────────────────────────────
# Known tracks, so they're named the moment they're loaded. A file number
# alone is not enough -- the same musicNNN can turn up in more than one of
# the game's sound folders -- so tracks are keyed by WHICH sound folder
# they live in (sound, sound2, sound3 ...) plus their number. A track found
# this way also has its header fingerprint remembered (fingerprints.json in
# the settings folder), so the same file is still recognised after it has
# been copied somewhere with no "soundN" in its path. Anything you set on
# a track yourself always wins over the catalogue.
#   folder: (expansion, {number: (title, composer, where it's heard)})
CATALOG = {
    "sound": ("Original", {
        101: ("Battle Theme", "Naoshi Mizuta", "Field area battle theme (solo)"),
        102: ("Battle in the Dungeon #2", "Naoshi Mizuta", "Dungeon area battle theme (party)"),
        103: ("Battle Theme #2", "Naoshi Mizuta", "Field area battle theme (party)"),
        104: ("Ghelsba / A Road Once Traveled", "Naoshi Mizuta", "Mission/quest scenes (formerly Fort Ghelsba's and Yughott Grotto's theme in the FFXI beta)"),
        105: ("Mhaura", "Naoshi Mizuta", "Mhaura"),
        106: ("Voyager", "Naoshi Mizuta", "Ferry - Mhaura/Selbina"),
        107: ("The Kingdom of San d'Oria", "Naoshi Mizuta", "Kingdom of San d'Oria"),
        108: ("Vana'diel March", "Naoshi Mizuta", "Title screen"),
        109: ("Ronfaure", "Nobuo Uematsu", "Ronfaure"),
        110: ("The Grand Duchy of Jeuno", "Naoshi Mizuta", "Jeuno"),
        111: ("Blackout", "Naoshi Mizuta", "K.O."),
        112: ("Selbina", "Naoshi Mizuta", "Selbina"),
        113: ("Sarutabaruta", "Naoshi Mizuta", "Sarutabaruta"),
        114: ("Batallia Downs", "Naoshi Mizuta", "Batallia Downs"),
        115: ("Battle in the Dungeon", "Naoshi Mizuta", "Dungeon area battle theme (solo)"),
        116: ("Gustaberg", "Kumi Tanioka", "Gustaberg"),
        117: ("Ru'Lude Gardens", "Kumi Tanioka", "Ru'Lude Gardens"),
        118: ("Rolanberry Fields", "Naoshi Mizuta", "Rolanberry Fields"),
        119: ("Awakening", "Kumi Tanioka", "The Rank 5 mission"),
        120: ("Vana'diel March #2", "Naoshi Mizuta", "Mission/quest scenes"),
        121: ("Shadow Lord", "Kumi Tanioka", "Mission/quest scenes"),
        122: ("One Last Time / Just Once More", "Nobuo Uematsu", "Mission/quest scenes"),
        123: ("Hopelessness", "Nobuo Uematsu", "Mission/quest scenes"),
        124: ("Recollection", "Nobuo Uematsu", "Mission/quest scenes"),
        125: ("Tough Battle", "Naoshi Mizuta", "Battlefields"),
        126: ("Mog House", "Naoshi Mizuta", "Mog House"),
        127: ("Anxiety", "Nobuo Uematsu", "Mission/quest scenes"),
        128: ("Airship", "Nobuo Uematsu", "Airship"),
        130: ("Tarutaru Female", "Kumi Tanioka", "Character creation"),
        131: ("Elvaan Female", "Kumi Tanioka", "Character creation"),
        132: ("Elvaan Male", "Naoshi Mizuta", "Character creation"),
        133: ("Hume Male", "Naoshi Mizuta", "Character creation"),
        151: ("The Federation of Windurst", "Naoshi Mizuta", "Windurst"),
        152: ("The Republic of Bastok", "Kumi Tanioka", "Bastok"),
        153: ("Prelude", "Nobuo Uematsu", "Login, updating, quest scenes"),
        154: ("Metalworks", "Kumi Tanioka", "Bastok"),
        155: ("Castle Zvahl", "Naoshi Mizuta", "Castle Zvahl"),
        156: ("Chateau d'Oraguille", "Naoshi Mizuta", "Chateau d'Oraguille"),
        157: ("Fury", "Kumi Tanioka", "Mission/quest scenes"),
        158: ("Sauromugue Champaign", "Naoshi Mizuta", "Sauromugue Champaign"),
        159: ("Sorrow", "Nobuo Uematsu", "Mission/quest scenes"),
        160: ("Repression (Memoro de la Ŝtono)", "Nobuo Uematsu", "Mission/quest scenes"),
        161: ("Despair (Memoro de la Ŝtono)", "Nobuo Uematsu", "Mission/quest scenes"),
        162: ("Heavens Tower", "Naoshi Mizuta", "Heavens Tower"),
        163: ("Sometime, Somewhere", "Nobuo Uematsu", "Mission/quest scenes"),
        164: ("Xarcabard", "Naoshi Mizuta", "Xarcabard"),
        165: ("Galka", "Naoshi Mizuta", "Character creation"),
        166: ("Mithra", "Kumi Tanioka", "Character creation"),
        167: ("Tarutaru Male", "Naoshi Mizuta", "Character creation"),
        168: ("Hume Female", "Kumi Tanioka", "Character creation"),
        169: ("Regeneracy", "Kumi Tanioka", "Job Change Land (removed in a 2002 update)"),
        170: ("Buccaneers", "Naoshi Mizuta", "Ferry - Mhaura/Selbina (pirate attack)"),
        214: ("Eternal Oath / Wedding March", "Naoshi Mizuta", "Wedding Support - wedding ceremony"),
    }),
    "sound2": ("Rise of the Zilart", {
        134: ("Yuhtunga Jungle", "Naoshi Mizuta", "Elshimo Lowlands"),
        135: ("Kazham", "Naoshi Mizuta", "Kazham"),
        171: ("Altepa Desert", "Naoshi Mizuta", "Kuzotz"),
        190: ("The Sanctuary of Zi'Tah", "Naoshi Mizuta", "The Sanctuary of Zi'Tah"),
        191: ("Battle Theme #3", "Naoshi Mizuta", "Zilart field area battle theme"),
        192: ("Battle In the Dungeon #3", "Naoshi Mizuta", "Zilart dungeon area battle theme"),
        193: ("Tough Battle #2", "Naoshi Mizuta", "Zilart BF"),
        194: ("Bloody Promises", "Naoshi Mizuta",
              "Mission/quest scenes (Raogrimm's theme)"),
        195: ("Belief", "Naoshi Mizuta", "Rise of the Zilart final boss theme (phase 2)"),
        196: ("Fighters of the Crystal", "Naoshi Mizuta", "Zilart Missions (Ark Angels)"),
        197: ("To The Heavens / Kamlanaut#2", "Naoshi Mizuta", "Zilart Missions"),
        198: ("Eald'narche", "Naoshi Mizuta", "Rise of the Zilart final boss theme (phase 1)"),
        199: ("Grav'iton", "Naoshi Mizuta", "Zilart Missions"),
        200: ("Hidden Truths / Kamlanaut#1", "Nobuo Uematsu", "Zilart Missions"),
        201: ("End Theme", "Naoshi Mizuta", "Rise of the Zilart ending theme"),
        202: ("Moongate (Memoro de la Ŝtono): Ancient Verse of Ro'Maeve / "
              "Ancient Verse of Altepa / Ancient Verse of Uggalepih",
              "Naoshi Mizuta", "Mission scenes"),
        206: ("Revenant Maiden / The Zilart", "Naoshi Mizuta", "Zilart Missions (Yve'noile)"),
        207: ("Ve'Lugannon Palace", "Naoshi Mizuta", "Ve'Lugannon Palace"),
        208: ("Rabao", "Naoshi Mizuta", "Rabao"),
        209: ("Norg", "Naoshi Mizuta", "Norg"),
        210: ("Tu'Lia", "Naoshi Mizuta", "Tu'Lia"),
        211: ("Ro'Maeve", "Naoshi Mizuta", "Ro'Maeve"),
        212: ("Dash de Chocobo", "Naoshi Mizuta", "Riding a chocobo"),
        213: ("Hall of the Gods", "Naoshi Mizuta", "Hall of the Gods"),
        227: ("Sunbreeze Shuffle", "Naoshi Mizuta", "Sunbreeze Festival, Legion"),
    }),
    # sound3 by the game's install pattern (ROM2 = Zilart, ROM3 = Promathia);
    # unconfirmed until a file shows up named.
    "sound3": ("Chains of Promathia", {
        129: ("Hook, Line, and Sinker", "Naoshi Mizuta", "Fishing (small fish)"),
        136: ("The Big One", "Naoshi Mizuta", "Fishing (large fish)"),
        137: ("A Realm of Emptiness", "Naoshi Mizuta",
              "Chains of Promathia final boss theme (2nd phase), Apocalypse Nigh boss theme"),
        218: ("Depths Of The Soul", "Naoshi Mizuta", "Promathia dungeon battle theme"),
        219: ("Onslaught", "Naoshi Mizuta", "Promathia field battle theme"),
        220: ("Turmoil", "Naoshi Mizuta", "Promathia Mission BF"),
        221: ("Moblin Menagerie - Movalpolos", "Naoshi Mizuta", "Movalpolos"),
        222: ("Faded Memories - Promyvion", "Naoshi Mizuta", "Promyvion"),
        223: ("Conflict: March of the Hero", "Naoshi Mizuta", "Conflict (team is winning)"),
        224: ("Dusk and Dawn", "Naoshi Mizuta", "Promathia Missions"),
        225: ("Words Unspoken - Pso'Xja", "Naoshi Mizuta", "Pso'Xja"),
        226: ("Conflict: You Want To Live Forever?", "Naoshi Mizuta",
              "Conflict (team is losing or tied)"),
        228: ("Gates Of Paradise - The Garden of Ru'Hmet", "Naoshi Mizuta",
              "The Garden of Ru'Hmet"),
        229: ("The Currents of Time", "Naoshi Mizuta", "Manaclipper"),
        230: ("A New Horizon - Tavnazian Archipelago", "Naoshi Mizuta",
              "Tavnazian Archipelago"),
        231: ("Celestial Thunder / Trembling Sky", "Naoshi Mizuta",
              "Promathia Missions (Nag'molada's theme)"),
        232: ("Ruler of the Skies", "Naoshi Mizuta", "Promathia Missions"),
        233: ("The Celestial Capital - Al'Taieu", "Naoshi Mizuta", "Promathia Missions"),
        234: ("Happily Ever After", "Naoshi Mizuta", "Promathia Missions"),
        235: ("First Ode: Nocturne Of The Gods", "Nobuo Uematsu", "Promathia Missions"),
        236: ("Fourth Ode: Clouded Dawn", "Naoshi Mizuta", "Promathia Missions"),
        237: ("Third Ode: Memoria de la Ŝtono", "Nobuo Uematsu", "Promathia Missions"),
        238: ("A New Morning", "Naoshi Mizuta", "Promathia Missions"),
        239: ("Jeuno ~Starlight Celebration~", "Naoshi Mizuta",
              "Starlight Celebration, Dynamis - Tavnazia"),
        240: ("Second Ode: Distant Promises", "Nobuo Uematsu", "Promathia Missions"),
        241: ("Fifth Ode: A Time for Prayer", "Naoshi Mizuta", "Promathia Missions"),
        242: ("Unity", "Naoshi Mizuta", "Title screen"),
        243: ("Grav'iton", "Naoshi Mizuta",
              "Promathia Missions (Grav'iton's theme) -- same music as Zilart's music199"),
        244: ("Revenant Maiden / The Zilart", "Naoshi Mizuta",
              "Promathia Missions (Yve'noile's theme) -- same music as Zilart's music206"),
        245: ("The Forgotten City - Tavnazian Safehold", "Naoshi Mizuta",
              "Tavnazian Safehold"),
        900: ("Distant Worlds", "Nobuo Uematsu", "Promathia Missions ending theme"),
    }),    # sound4 by the install pattern (ROM4 = Aht Urhgan); a wrong guess is
    # still caught by what the folder holds (see assign_catalog).
    "sound4": ("Treasures of Aht Urhgan", {
        138: ("Mercenaries' Delight", "Naoshi Mizuta", "Aht Urhgan field area battle theme"),
        139: ("Delve", "Naoshi Mizuta", "Aht Urhgan dungeon area battle theme"),
        142: ("Fated Strife -Besieged-", "Naoshi Mizuta", "Besieged"),
        143: ("Hellriders", "Naoshi Mizuta", "Aht Urhgan Mission BF"),
        144: ("Rapid Onslaught -Assault-", "Naoshi Mizuta", "Assault"),
        146: ("The Colosseum", "Naoshi Mizuta", "Pankration"),
        147: ("Eastward Bound...", "Naoshi Mizuta", "Ferry - Mhaura/Al Zahbi, Ferry - Nashmau/Al Zahbi"),
        148: ("Forbidden Seal", "Naoshi Mizuta", "Nyzul Isle"),
        149: ("Jeweled Boughs", "Naoshi Mizuta", "Bhaflau Thickets, Wajaom Woodlands"),
        150: ("Ululations from Beyond", "Naoshi Mizuta", "Arrapago Reef"),
        172: ("Black Coffin", "Naoshi Mizuta", "The Ashu Talif"),
        173: ("Illusions in the Mist", "Naoshi Mizuta", "Caedarva Mire"),
        174: ("Whispers of the Gods", "Naoshi Mizuta", "Aydeewa Subterrane"),
        175: ("Bandits' Market", "Naoshi Mizuta", "Nashmau"),
        176: ("Circuit de Chocobo", "Naoshi Mizuta", "Chocobo Circuit"),
        177: ("Run Chocobo Run!", "Naoshi Mizuta", "Chocobo Circuit"),
        178: ("The Bustle of the Capital", "Naoshi Mizuta", "Aht Urhgan Whitegate, Al Zahbi"),
        179: ("Vana'diel March #4", "Naoshi Mizuta", "Title screen"),
        183: ("A Puppet's Slumber", "Naoshi Mizuta", "Aht Urhgan Missions"),
        184: ("Eternal Gravestone", "Naoshi Mizuta", "Aht Urhgan Missions, Besieged (defeated)"),
        185: ("Ever-Turning Wheels", "Naoshi Mizuta", "Aht Urhgan Missions"),
        186: ("Iron Colossus", "Naoshi Mizuta", "Aht Urhgan Missions, Einherjar"),
        187: ("Ragnarok", "Naoshi Mizuta", "Aht Urhgan final boss theme"),
        188: ("Choc-A-Bye-Baby", "Nobuo Uematsu", "Chocobo Raising"),
        189: ("An Invisible Crown", "Naoshi Mizuta", "Treasures of Aht Urhgan ending theme"),
    }),    "sound5": ("Wings of the Goddess", {
        40: ("Cloister of Time and Souls", "Naoshi Mizuta", "The Threshold, Walk of Echoes"),
        41: ("Royal Wanderlust", "Naoshi Mizuta", "Wings of the Goddess Missions (Cait Sith's theme)"),
        42: ("Snowdrift Waltz", "Naoshi Mizuta", "Xarcabard (S)"),
        43: ("Troubled Shadows", "Naoshi Mizuta", "Castle Zvahl Baileys (S), Castle Zvahl Keep (S)"),
        44: ("Where Lords Rule Not", "Naoshi Mizuta", "La Vaule (S), Beadeaux (S), Castle Oztroja (S)"),
        45: ("Summers Lost", "Naoshi Mizuta", "Wings of the Goddess Missions (Lilisette's theme)"),
        46: ("Goddess Divine", "Naoshi Mizuta", "Wings of the Goddess final boss theme"),
        54: ("Everlasting Bonds", "Naoshi Mizuta", "Wings of the Goddess ending theme"),
        140: ("Wings of the Goddess", "Naoshi Mizuta", "Title screen"),
        141: ("The Cosmic Wheel", "Naoshi Mizuta", "West Sarutabaruta (S)"),
        145: ("Encampment Dreams", "Naoshi Mizuta", "Wings of the Goddess Missions"),
        180: ("Thunder of the March", "Naoshi Mizuta", "Bastok Markets (S)"),
        182: ("Stargazing", "Naoshi Mizuta", "Windurst Waters (S)"),
        215: ("Clash of Standards", "Naoshi Mizuta", "Wings of the Goddess field battle theme"),
        216: ("On this Blade", "Naoshi Mizuta", "Wings of the Goddess dungeon battle theme"),
        217: ("Kindred Cry", "Naoshi Mizuta", "Wings of the Goddess Mission BF, Odyssey"),
        246: ("March of the Allied Forces", "Naoshi Mizuta", "Wings of the Goddess quests"),
        247: ("Roar of the Battle Drums", "Naoshi Mizuta", "Campaign Battle theme"),
        248: ("Young Griffons in Flight", "Naoshi Mizuta", "Wings of the Goddess quests (The Young Griffons' theme)"),
        249: ("Run Maggot, Run!", "Naoshi Mizuta", "Wings of the Goddess quest BF, Moblin Maze Mongers"),
        250: ("Under a Clouded Moon", "Naoshi Mizuta", "Wings of the Goddess quest BF"),
        251: ("Autumn Footfalls", "Naoshi Mizuta", "East Ronfaure (S)"),
        252: ("Flowers on the Battlefield", "Naoshi Mizuta", "Batallia Downs (S), Rolanberry Fields (S), Sauromugue Champaign (S)"),
        253: ("Echoes of a Zephyr", "Naoshi Mizuta", "North Gustaberg (S)"),
        254: ("Griffons Never Die", "Naoshi Mizuta", "Southern San d'Oria (S)"),
    }),    # Folder not known yet for these three: keyed by name, not by a
    # soundN folder, and recognised from the numbers a folder holds
    # (see assign_catalog). Give them their soundN key once known.
    "soa": ("Seekers of Adoulin", {
        57: ("Steel Sings, Blades Dance", "Naoshi Mizuta", "Seekers of Adoulin battle theme"),
        58: ("A New Direction", "Naoshi Mizuta", "Title screen"),
        59: ("The Pioneers", "Naoshi Mizuta", "Western Adoulin"),
        60: ("Into Lands Primeval - Ulbuka", "Naoshi Mizuta", "East Ulbuka Territory"),
        61: ("Water's Umbral Knell", "Naoshi Mizuta", "Rala Waterways, Yorcia Weald"),
        62: ("Keepers of the Wild", "Naoshi Mizuta", "Wildskeeper Reive, Skirmish, Delve"),
        63: ("The Sacred City of Adoulin", "Naoshi Mizuta", "Eastern Adoulin"),
        64: ("Breaking Ground", "Naoshi Mizuta", "Reive battle theme"),
        65: ("Hades", "Naoshi Mizuta", "Seekers of Adoulin final boss theme (phase 1)"),
        66: ("Arciela", "Naoshi Mizuta", "Seekers of Adoulin Missions (Arciela's theme)"),
        67: ("Mog Resort", "Naoshi Mizuta", "Mog Garden"),
        68: ("Worlds Away", "Naoshi Mizuta", "Seekers of Adoulin Missions"),
        72: ("The Serpentine Labyrinth", "Naoshi Mizuta", "Outer Ra'Kaznar, Ra'Kaznar Inner Court"),
        73: ("The Divine", "Naoshi Mizuta", "Mount Kamihr"),
        74: ("Clouds Over Ulbuka", "Naoshi Mizuta", "Seekers of Adoulin BF"),
        75: ("The Price", "Naoshi Mizuta", "Seekers of Adoulin final boss theme (phase 2)"),
        76: ("Forever Today", "Naoshi Mizuta", "Seekers of Adoulin ending theme"),
        78: ("Forever Today (instrumental version)", "Naoshi Mizuta", "Seekers of Adoulin epilogue quests"),
    }),
    "rov": ("Rhapsodies of Vana'diel", {
        79: ("Iroha", "Naoshi Mizuta", "Reisenjima, Rhapsodies of Vana'diel Missions"),
        80: ("The Boundless Black", "Naoshi Mizuta", "Escha"),
        81: ("Isle of the Gods", "Naoshi Mizuta", "Rhapsodies of Vana'diel Missions"),
        82: ("Wail of the Void", "Naoshi Mizuta", "Rhapsodies of Vana'diel final boss theme"),
        83: ("Rhapsodies of Vana'diel", "Naoshi Mizuta", "Rhapsodies of Vana'diel ending theme"),
    }),
    "tvr": ("The Voracious Resurgence", {
        25: ("The Voracious Resurgence", "Naoshi Mizuta", "The Voracious Resurgence Missions"),
        26: ("The Devoured", "Naoshi Mizuta", "The Voracious Resurgence battle theme"),
        27: ("Encroaching Perils", "Naoshi Mizuta", "The Voracious Resurgence Missions"),
        28: ("The Destiny Destroyers", "Naoshi Mizuta", "The Voracious Resurgence Missions"),
        31: ("Black Stars Rise", "Naoshi Mizuta", "The Voracious Resurgence Missions"),
        32: ("All Smiles", "Naoshi Mizuta", "The Voracious Resurgence Missions"),
        33: ("Valhalla", "Naoshi Mizuta", "The Voracious Resurgence final boss theme (phase 1)"),
        34: ("We Are Vana'diel", "Naoshi Mizuta", "Title screen"),
        37: ("All-Consuming Chaos", "Naoshi Mizuta", "The Voracious Resurgence final boss theme (phase 2)"),
        38: ("Your Choice", "Naoshi Mizuta", "The Voracious Resurgence ending theme"),
    }),    # Add-on scenarios and battle areas: several titles in one table, so
    # tracks can carry their own expansion (a 4th value) over the section's.
    "addon": ("Add-on Scenarios & Battle Areas", {
        47: ("Echoes of Creation", "Naoshi Mizuta", "A Crystalline Prophecy final boss theme, Rhapsodies of Vana'diel Missions", "A Crystalline Prophecy"),
        48: ("Main Theme -FINAL FANTASY XI Version-", "Naoshi Mizuta", "A Crystalline Prophecy ending theme, Abyssea ending theme", "A Crystalline Prophecy"),
        49: ("Luck of the Mog", "Naoshi Mizuta", "A Moogle Kupo d'Etat final boss theme", "A Moogle Kupo d'Etat"),
        50: ("Feast of the Ladies", "Naoshi Mizuta", "A Shantotto Ascension final boss theme", "A Shantotto Ascension"),
        51: ("Abyssea - Scarlet Skies, Shadowed Plains", "Naoshi Mizuta", "Abyssea", "Abyssea"),
        52: ("Melodies Errant", "Naoshi Mizuta", "Abyssea battle theme", "Abyssea"),
        53: ("Shinryu", "Naoshi Mizuta", "Abyssea final boss theme", "Abyssea"),
        55: ("Provenance Watcher", "Naoshi Mizuta", "Voidwatch final boss theme"),
        56: ("Where it All Begins", "Naoshi Mizuta", "Provenance"),
    }),
    # Later content (Sortie, Odyssey, Omen, mounts ...). music028 is also a
    # Voracious Resurgence number -- a different file in a different folder;
    # which one applies is decided by the rest of the folder's contents.
    "other": ("Other", {
        28: ("Devils' Delight", "Naoshi Mizuta", "Harvest Festival"),
        30: ("Sojourner", "Naoshi Mizuta", "Odyssey (Bumba's battle theme)"),
        35: ("Goddesspeed", "Naoshi Mizuta", "Sortie - ground level"),
        36: ("Good Fortune", "Naoshi Mizuta", "Sortie - basement"),
        70: ("Monstrosity", "Naoshi Mizuta", "Monstrosity"),
        84: ("Full Speed Ahead!", "Naoshi Mizuta", "Mounts"),
        85: ("Times Grow Tense", "Naoshi Mizuta", "Ambuscade"),
        87: ("For a Friend", "Naoshi Mizuta", "Omen"),
        88: ("Between Dreams and Reality", "Naoshi Mizuta", "Dynamis - Divergence wave 1 / wave 2"),
        89: ("Disjoined One", "Naoshi Mizuta", "Dynamis - Divergence wave 3"),
        90: ("Winds of Change", "Naoshi Mizuta", "Heroines' Combat II"),
        # From the "unused music" table -- the ones that have a file:
        69: ("Distant Worlds -Nanaa Mihgo's Version-", "Naoshi Mizuta",
             "Nanaa Mihgo Statue (Orchestrion)"),
        71: ("The Pioneers -Nanaa Mihgo's Version-", "Naoshi Mizuta",
             "Nanaa Mihgo Statue II (Orchestrion)"),
        77: ("Distant Worlds (instrumental version)", "Naoshi Mizuta",
             "Sheet of Promathia tunes (Orchestrion)"),
        86: ("The Shadow Lord Battle (Final Fantasy Record Keeper version)",
             "Naoshi Mizuta", "Sheet of Shadow Lord tunes (Orchestrion)"),
    }),
}

_FINGERPRINTS = None
_FP_DIRTY = False


def _fp_path():
    return os.path.join(settings_dir(), "fingerprints.json")


def _fingerprints():
    global _FINGERPRINTS
    if _FINGERPRINTS is None:
        try:
            with open(_fp_path(), encoding="utf-8") as f:
                _FINGERPRINTS = json.load(f)
        except (OSError, ValueError):
            _FINGERPRINTS = {}
    return _FINGERPRINTS


def save_fingerprints():
    global _FP_DIRTY
    if _FP_DIRTY:
        try:
            with open(_fp_path(), "w", encoding="utf-8") as f:
                json.dump(_FINGERPRINTS, f)
            _FP_DIRTY = False
        except OSError:
            pass


def track_fingerprint(path):
    """The header's size, id, length and loop fields -- the same for every
    copy of a file and different between files."""
    try:
        with open(path, "rb") as f:
            head = f.read(0x28)
    except OSError:
        return None
    if len(head) < 0x28 or not head.startswith(b"BGMStream"):
        return None
    return head[0x10:0x28].hex()


def _sound_folder(path):
    """"sound3" for ...\\sound3\\win\\music\\data\\music218.bgw, or None."""
    segs = [p.lower() for p in re.split(r"[\\/]+", path)]
    return next((p for p in reversed(segs) if re.fullmatch(r"sound\d*", p)), None)


def _entry(section, number):
    exp, tracks = CATALOG[section]
    row = tracks[number]
    title, composer, heard = row[:3]
    if len(row) > 3 and row[3]:
        exp = row[3]                    # this track's own expansion
    return (exp, title, composer, heard)


def _learn(path, section, number):
    global _FP_DIRTY
    fp = track_fingerprint(path)
    if fp and _fingerprints().get(fp) != [section, number]:
        _fingerprints()[fp] = [section, number]
        _FP_DIRTY = True


def assign_catalog(tracks):
    """Give each track its catalogue entry (track.cat), folder by folder.

    1. A folder with "soundN" in its path is that sound folder: known
       numbers in that section are certain.
    2. A copied folder without it is judged by what's IN it: the catalogue
       section that accounts for most of its file numbers wins (if it
       accounts for enough to be more than chance), and its numbers are
       named from that section. A number only one section has is also
       taken. So a copy of Promathia's music, wherever it lives and
       whatever it's called, is recognised from its own contents.
    3. Otherwise the file's fingerprint, remembered from an earlier time
       it was seen in its game folder.
    Matches by 1 and 2 are remembered as fingerprints for next time."""
    from collections import Counter, defaultdict
    by_dir = defaultdict(list)
    for t in tracks:
        t.cat = None
        by_dir[os.path.dirname(t.path)].append(t)
    for d, group in by_dir.items():
        sec = _sound_folder(group[0].path)
        if sec is not None and not (sec in CATALOG and any(
                t.number in CATALOG[sec][1] for t in group)):
            # "soundN" that this catalogue has nothing for: an expansion we
            # filed under a different folder, or one not catalogued yet.
            # Let the files speak for themselves, as for a copied folder.
            sec = None
        winner = None
        # Sections keyed by name rather than a soundN folder, and how many of
        # each one's numbers this folder holds.
        # How many of each section's numbers this folder holds -- every
        # section but the folder's own (WotG's low numbers, say, could sit in
        # the base folder alongside its own tracks).
        loose = {k: sum(1 for t in group if t.number in tr)
                 for k, (_, tr) in CATALOG.items() if k != sec}
        if sec is None:
            nums = [t.number for t in group if t.number is not None]
            hits = Counter(s_ for n in nums for s_, (_, tr) in CATALOG.items() if n in tr)
            if hits:
                w, cnt = hits.most_common(1)[0]
                if cnt >= 5 or cnt >= 0.4 * max(1, len(nums)):
                    winner = w
        for t in group:
            n = t.number
            pick = None
            how = None
            if sec is not None:
                if sec in CATALOG and n in CATALOG[sec][1]:
                    pick = sec
                else:
                    # Not this folder's own: one of the expansions whose folder
                    # isn't known yet, if this folder holds at least two of its
                    # numbers (one alone could be coincidence).
                    owners = sorted((loose[k], k) for k in loose
                                    if n in CATALOG[k][1] and loose[k] >= 2)
                    # Shared number (e.g. music028): the section with more of
                    # its numbers in this folder wins; a tie decides nothing.
                    if owners and (len(owners) == 1 or owners[-1][0] > owners[-2][0]):
                        pick = owners[-1][1]
                        how = "by its number -- folder not confirmed"
            elif winner is not None:
                if n in CATALOG[winner][1]:
                    pick = winner
                else:
                    owners = sorted((loose.get(s_, 0), s_) for s_, (_, tr) in CATALOG.items()
                                    if n in tr)
                    if owners and (len(owners) == 1 or owners[-1][0] > owners[-2][0]):
                        pick = owners[-1][1]
            if pick is not None:
                t.cat = _entry(pick, n) + ("%s, music%03d (%s)" % (
                    CATALOG[pick][0], n,
                    how or ("its sound folder" if sec else "what's in its folder")),)
                _learn(t.path, pick, n)
                continue
            fp = track_fingerprint(t.path)
            hit = _fingerprints().get(fp) if fp else None
            if hit and hit[0] in CATALOG and int(hit[1]) in CATALOG[hit[0]][1]:
                t.cat = _entry(hit[0], int(hit[1])) + ("%s, music%03d (its fingerprint)" % (
                    CATALOG[hit[0]][0], int(hit[1])),)
    save_fingerprints()


# The mini player is just the rounded panel: everything outside the
# panel's rounded corners is painted this colour and made see-through.
MINI_KEY = "#010203"

LOOP_FOREVER = "Loop forever (in-game)"
PLAY_ONCE = "Play once, then next"
REPEAT_MODES = (LOOP_FOREVER, PLAY_ONCE)


# ── Paths ────────────────────────────────────────────────────────────────

# The app icon (64 px, rounded), embedded so the window and the title strip
# have it with no extra files. The exe's own icon is OmniPlayer.ico.
APP_ICON_PNG = (
    "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"
    "QmCC"
)


def app_dir():
    """Folder of the exe (frozen) or of this script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def settings_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "OmniPlayer")
    os.makedirs(d, exist_ok=True)
    return d


VGMSTREAM_URL = ("https://github.com/vgmstream/vgmstream-releases/"
                 "releases/download/nightly/vgmstream-win64.zip")


def find_vgmstream():
    """vgmstream-cli beside the exe/script, in any folder directly inside
    that one (wherever the zip got extracted to), in the settings folder
    (where OmniPlayer downloads it), in a bundled PyInstaller folder, or
    on PATH. None if it is nowhere."""
    names = ("vgmstream-cli.exe", "vgmstream-cli")
    roots = [app_dir(), os.path.join(settings_dir(), "vgmstream")]
    try:
        roots += [e.path for e in os.scandir(app_dir()) if e.is_dir()]
    except OSError:
        pass
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots += [meipass, os.path.join(meipass, "vgmstream")]
    for root in roots:
        for n in names:
            p = os.path.join(root, n)
            if os.path.isfile(p):
                return p
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


FLAC_URL = ("https://github.com/xiph/flac/releases/download/1.5.0/"
            "flac-1.5.0-win.zip")


def find_flac():
    """flac.exe (the official Xiph encoder) beside the exe/script, in a
    folder directly beside it, in the settings folder, bundled, or on PATH."""
    names = ("flac.exe", "flac")
    roots = [app_dir(), os.path.join(app_dir(), "flac"),
             os.path.join(settings_dir(), "flac")]
    try:
        roots += [e.path for e in os.scandir(app_dir()) if e.is_dir()]
    except OSError:
        pass
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots += [meipass, os.path.join(meipass, "flac")]
    for r in roots:
        for n in names:
            p = os.path.join(r, n)
            if os.path.isfile(p):
                return p
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def download_flac():
    """Fetch Xiph's official Windows build and keep its 64-bit flac.exe (and
    the DLL and licence files it comes with) in the settings folder."""
    import urllib.request
    import zipfile
    fd, tmp = tempfile.mkstemp(suffix=".zip", prefix="flac_")
    os.close(fd)
    dest = os.path.join(settings_dir(), "flac")
    try:
        req = urllib.request.Request(FLAC_URL, headers={"User-Agent": APP_NAME})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        os.makedirs(dest, exist_ok=True)
        with zipfile.ZipFile(tmp) as z:
            for n in z.namelist():
                base = n.rsplit("/", 1)[-1]
                if not base:
                    continue
                if "/Win64/" in n or base.startswith("COPYING"):
                    with z.open(n) as src, open(os.path.join(dest, base), "wb") as out:
                        shutil.copyfileobj(src, out)
        exe = os.path.join(dest, "flac.exe")
        if not os.path.isfile(exe):
            raise VgmError("downloaded, but flac.exe was not in it")
        return exe
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def download_vgmstream(progress=None):
    """Fetch vgmstream's official Windows build and unpack it next to
    OmniPlayer (or into the settings folder if that one is read-only).
    Returns the path to vgmstream-cli.exe."""
    import urllib.request
    import zipfile
    fd, tmp = tempfile.mkstemp(suffix=".zip", prefix="vgm_")
    os.close(fd)
    try:
        req = urllib.request.Request(VGMSTREAM_URL,
                                     headers={"User-Agent": APP_NAME})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if progress:
                    progress(got, total)
        for dest in (os.path.join(app_dir(), "vgmstream"),
                     os.path.join(settings_dir(), "vgmstream")):
            try:
                os.makedirs(dest, exist_ok=True)
                with zipfile.ZipFile(tmp) as z:
                    z.extractall(dest)
                exe = os.path.join(dest, "vgmstream-cli.exe")
                if os.path.isfile(exe):
                    return exe
            except OSError:
                continue
        raise VgmError("downloaded, but vgmstream-cli.exe was not in it")
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


# Hide the console window vgmstream would otherwise flash on Windows.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


# ── vgmstream ────────────────────────────────────────────────────────────

class VgmError(Exception):
    pass


def _run_vgm(args, timeout=120):
    exe = find_vgmstream()
    if not exe:
        raise VgmError("vgmstream-cli was not found.")
    try:
        r = subprocess.run([exe] + args, capture_output=True,
                           timeout=timeout, creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise VgmError("vgmstream took too long")
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip()
        raise VgmError(msg or "vgmstream failed (code %d)" % r.returncode)
    return r.stdout


def vgm_info(path):
    """Sample rate, channels, total samples and loop points of a file.

    Returns {"rate", "channels", "samples", "loop_start", "loop_end"};
    the loop values are None for a track that does not loop.
    """
    out = _run_vgm(["-I", "-m", path], timeout=30)
    text = out.decode("utf-8", "replace")
    # -I prints one JSON object; be tolerant of anything around it.
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise VgmError("no info from vgmstream")
    j = json.loads(m.group(0))
    loop = j.get("loopingInfo") or {}
    samples = int(j.get("numberOfSamples") or 0)
    ls, le = loop.get("start"), loop.get("end")
    if ls is None or le is None or not (0 <= ls < le <= samples):
        ls = le = None
    return {"rate": int(j.get("sampleRate") or 44100),
            "channels": int(j.get("channels") or 2),
            "samples": samples,
            "loop_start": ls, "loop_end": le,
            "encoding": j.get("encoding") or "",
            "bitrate": int(j.get("bitrate") or 0)}


def vgm_decode(path, out_wav, loops=None, fade=None, whole=False):
    """Decode to a 16-bit WAV. whole=True: the stream once, ignoring the
    loop (what the player uses -- it does its own looping). Otherwise
    `loops` passes through the loop section and `fade` seconds of fade."""
    args = ["-o", out_wav]
    if whole:
        args.append("-i")
    else:
        if loops is not None:
            args += ["-l", "%.1f" % float(loops)]
        if fade is not None:
            args += ["-f", "%.1f" % float(fade)]
    _run_vgm(args + [path])


def read_wav(path):
    with wave.open(path, "rb") as w:
        return (w.getframerate(), w.getnchannels(), w.getsampwidth(),
                w.readframes(w.getnframes()))


# ── Library ──────────────────────────────────────────────────────────────

def track_number(path):
    """music023.bgw -> 23 (None if the name carries no number)."""
    # The file name only -- split on either slash, so a "(x86)" earlier in
    # the path can never be mistaken for the track number.
    name = re.split(r"[\\/]", path)[-1]
    m = re.search(r"(\d+)", os.path.splitext(name)[0])
    return int(m.group(1)) if m else None


class Track:
    __slots__ = ("path", "rel", "number", "info", "folder", "cat")

    def __init__(self, path, folder):
        self.path = path
        self.folder = folder
        self.rel = os.path.relpath(path, folder.root).replace("\\", "/")
        self.number = track_number(path)
        self.info = None
        self.cat = None            # set by assign_catalog when its folder is scanned

    def default_name(self):
        return os.path.splitext(os.path.basename(self.path))[0]

    def length_seconds(self):
        if not self.info or not self.info["rate"]:
            return None
        end = self.info["loop_end"] or self.info["samples"]
        return end / float(self.info["rate"])


def _path_tag(root):
    return re.sub(r"[^A-Za-z0-9]+", "_", root).strip("_")[-80:]


class Folder:
    """One imported folder: its tracks, what you've set on them, and cached
    info.

    What you set -- a track's name, its expansion, whether it's a
    favourite -- lives in bgw_names.json INSIDE the folder, keyed by each
    file's path relative to it, so it travels with the folder when it is
    copied. A folder that can't be written to (the game's own install
    under Program Files) keeps it in the settings folder instead, in
    names_<folder path>.json. Older files that held just a name per track
    are read as they are."""

    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.tracks = []
        self.names = {}
        self._names_path = os.path.join(self.root, NAMES_FILE)
        self._cache = {}

    def scan(self):
        found = []
        for dirpath, _dirs, files in os.walk(self.root):
            for f in files:
                if f.lower().endswith(".bgw"):
                    found.append(Track(os.path.join(dirpath, f), self))
        found.sort(key=lambda t: (os.path.dirname(t.rel).lower(),
                                  t.number if t.number is not None else 1e9,
                                  t.rel.lower()))
        self.tracks = found
        assign_catalog(found)
        self._load_names()
        self._load_cache()
        for t in self.tracks:
            t.info = self._cached_info(t)

    def _fallback_names_path(self):
        return os.path.join(settings_dir(), "names_%s.json" % _path_tag(self.root))

    def _load_names(self):
        self.names = {}
        self._names_path = os.path.join(self.root, NAMES_FILE)
        for p in (self._names_path, self._fallback_names_path()):
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, dict):
                            self.names[str(k)] = {kk: vv for kk, vv in v.items() if vv}
                        elif v:
                            self.names[str(k)] = {"name": str(v)}
                    if p != self._names_path and not os.path.exists(self._names_path):
                        self._names_path = p
            except (OSError, ValueError):
                pass

    def save_names(self):
        clean = {k: v for k, v in self.names.items() if v}
        data = json.dumps(clean, indent=2, ensure_ascii=False, sort_keys=True)
        for p in (self._names_path, os.path.join(self.root, NAMES_FILE),
                  self._fallback_names_path()):
            try:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(data)
                self._names_path = p
                return p
            except OSError:
                continue
        return None

    # Track length needs vgmstream's info; caching it keeps a big folder
    # from being re-read every time it is opened.
    def _cache_path(self):
        return os.path.join(settings_dir(), "info_%s.json" % _path_tag(self.root))

    def _load_cache(self):
        try:
            with open(self._cache_path(), encoding="utf-8") as f:
                self._cache = json.load(f)
        except (OSError, ValueError):
            self._cache = {}

    def save_cache(self):
        try:
            with open(self._cache_path(), "w", encoding="utf-8") as f:
                json.dump(self._cache, f)
        except OSError:
            pass

    @staticmethod
    def _stamp(track):
        try:
            st = os.stat(track.path)
            return "%d:%d" % (st.st_size, int(st.st_mtime))
        except OSError:
            return ""

    def _cached_info(self, track):
        c = self._cache.get(track.rel)
        if c and c.get("stamp") == self._stamp(track):
            return c.get("info")
        return None

    def fill_info(self, track):
        if track.info is None:
            track.info = vgm_info(track.path)
            self._cache[track.rel] = {"stamp": self._stamp(track),
                                      "info": track.info}
        return track.info


class Library:
    """Every imported folder, in the order they were imported; `tracks` is
    all of their tracks, one folder after another."""

    def __init__(self):
        self.folders = []
        self.tracks = []
        # Tracks taken off the list (by full path). The files are untouched;
        # importing their folder again brings them back.
        self.removed = set()

    @property
    def roots(self):
        return [f.root for f in self.folders]

    def add(self, root, restore=False):
        """Import a folder (or rescan it if it's already in). Returns how
        many of its tracks are on the list. restore=True (an explicit
        import) brings back any of its tracks that had been removed."""
        root = os.path.abspath(root)
        if restore:
            pre = os.path.normcase(root.rstrip("\\/") + os.sep)
            self.removed = {p for p in self.removed if not p.startswith(pre)}
        folder = next((f for f in self.folders if f.root.lower() == root.lower()), None)
        if folder is None:
            folder = Folder(root)
            self.folders.append(folder)
        folder.scan()
        self._rebuild()
        return sum(1 for t in self.tracks if t.folder is folder)

    def remove(self, root):
        self.folders = [f for f in self.folders if f.root != root]
        self._rebuild()

    def _rebuild(self):
        rm = self.removed
        self.tracks = [t for f in self.folders for t in f.tracks
                       if os.path.normcase(t.path) not in rm]

    def remove_tracks(self, tracks):
        """Take tracks off the list. A folder left with nothing on the list
        is dropped from the library too."""
        for t in tracks:
            self.removed.add(os.path.normcase(t.path))
        self._rebuild()
        keep = {id(t.folder) for t in self.tracks}
        gone = [f for f in self.folders if id(f) not in keep]
        if gone:
            self.folders = [f for f in self.folders if id(f) in keep]
            for f in gone:
                pre = os.path.normcase(f.root.rstrip("\\/") + os.sep)
                self.removed = {p for p in self.removed if not p.startswith(pre)}
        return gone

    def meta(self, track):
        return track.folder.names.get(track.rel) or {}

    # What you set wins; then the catalogue; then the file itself.
    def name_of(self, track):
        return (self.meta(track).get("name") or (track.cat and track.cat[1])
                or track.default_name())

    def expansion_of(self, track):
        return self.meta(track).get("expansion") or (track.cat and track.cat[0]) or ""

    def composer_of(self, track):
        return self.meta(track).get("composer") or (track.cat and track.cat[2]) or ""

    def heard_in(self, track):
        return (track.cat and track.cat[3]) or ""

    def is_fav(self, track):
        return bool(self.meta(track).get("fav"))

    def set_meta(self, track, key, value, save=True):
        """Set (or, with an empty value, clear) one thing on a track."""
        m = dict(self.meta(track))
        if value:
            m[key] = value
        else:
            m.pop(key, None)
        if m:
            track.folder.names[track.rel] = m
        else:
            track.folder.names.pop(track.rel, None)
        return track.folder.save_names() if save else True

    def rename(self, track, new_name):
        new_name = (new_name or "").strip()
        if new_name in (track.default_name(), track.cat and track.cat[1]):
            new_name = ""          # same as it would show anyway: store nothing
        return self.set_meta(track, "name", new_name)

    def track_by_path(self, path):
        if not hasattr(self, "_by_path") or self._by_path_n != len(self.tracks):
            self._by_path = {os.path.normcase(t.path): t for t in self.tracks}
            self._by_path_n = len(self.tracks)
        return self._by_path.get(os.path.normcase(path))

    def fill_info(self, track):
        return track.folder.fill_info(track)

    def save_cache(self):
        for f in self.folders:
            f.save_cache()


# ── Playback ─────────────────────────────────────────────────────────────

class Engine:
    """Plays one decoded track, looping it the game's way.

    The intro plays once, then the loop section repeats. The repeat is
    QUEUED on the mixer channel before the current section ends, so the
    mixer moves straight on to it inside its own audio callback -- no gap
    and no click at the seam. tick() re-queues it each time it starts.
    """

    def __init__(self):
        self._pg = None
        self.mixer_fmt = None
        self.track = None
        self.rate = 44100
        self.channels = 2
        self.frame_bytes = 4
        self.pcm = b""
        self.total = 0
        self.loop_start = None
        self.loop_end = None
        self.looping = True
        self.volume = 0.8
        self._chan = None
        self._body = None
        self._t0 = 0.0
        self._base = 0
        self._paused_at = None
        self._paused_total = 0.0
        self.playing = False

    def _mixer(self, rate, channels):
        if self._pg is None:
            import pygame
            self._pg = pygame
        pg = self._pg
        if self.mixer_fmt != (rate, channels):
            if pg.mixer.get_init():
                pg.mixer.quit()
            pg.mixer.init(frequency=rate, size=-16, channels=channels,
                          buffer=2048)
            pg.mixer.set_num_channels(2)
            self.mixer_fmt = (rate, channels)
        return pg

    def load(self, track, info):
        """Decode `track` and get it ready to play from the start."""
        self.stop()
        fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="bgw_")
        os.close(fd)
        try:
            vgm_decode(track.path, tmp, whole=True)
            rate, ch, width, pcm = read_wav(tmp)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        if width != 2:
            raise VgmError("unexpected sample width %d" % width)
        self.track = track
        self.rate, self.channels = rate, ch
        self.frame_bytes = 2 * ch
        self.pcm = pcm
        self.total = len(pcm) // self.frame_bytes
        ls, le = info.get("loop_start"), info.get("loop_end")
        if ls is not None and le is not None and le <= self.total:
            self.loop_start, self.loop_end = ls, le
        else:
            self.loop_start = self.loop_end = None
        pg = self._mixer(rate, ch)
        self._body = None
        if self.loop_start is not None:
            self._body = pg.mixer.Sound(buffer=self._slice(self.loop_start,
                                                           self.loop_end))

    def _slice(self, a, b):
        return self.pcm[a * self.frame_bytes:b * self.frame_bytes]

    def has_loop(self):
        return self.loop_start is not None

    def end_frame(self):
        """Where one pass through the track ends."""
        return self.loop_end if self.has_loop() else self.total

    def play(self, frame=0):
        if not self.pcm:
            return
        pg = self._mixer(self.rate, self.channels)
        was_paused = self._paused_at is not None
        self.stop()
        loop = self.looping and self.has_loop()
        frame = max(0, min(int(frame), self.end_frame() - 1))
        end = self.loop_end if loop else self.end_frame()
        first = pg.mixer.Sound(buffer=self._slice(frame, end))
        self._chan = first.play()
        if self._chan is None:
            return
        self._chan.set_volume(self.volume)
        if loop:
            self._chan.queue(self._body)
        self._t0 = time.monotonic()
        self._base = frame
        self._paused_total = 0.0
        self._paused_at = None
        self.playing = True
        if was_paused:
            self.pause()

    def tick(self):
        """Keep the loop section queued. Call a few times a second."""
        if (self.playing and self._chan is not None and self._body is not None
                and self.looping and self._paused_at is None
                and self._chan.get_busy() and self._chan.get_queue() is None):
            self._chan.queue(self._body)

    def finished(self):
        """True once a play-once pass has run out."""
        return (self.playing and self._paused_at is None
                and self._chan is not None and not self._chan.get_busy())

    def pause(self):
        if self._chan is not None and self._paused_at is None and self.playing:
            self._chan.pause()
            self._paused_at = time.monotonic()

    def resume(self):
        if self._chan is not None and self._paused_at is not None:
            self._paused_total += time.monotonic() - self._paused_at
            self._paused_at = None
            self._chan.unpause()

    def is_paused(self):
        return self._paused_at is not None

    def stop(self):
        """Stop for real. pygame-ce starts a channel's QUEUED sound the
        moment the channel is halted, so stopping a looping track used to
        just start the loop section again -- and a new track then played
        on top of it. So the queue is first swapped for a few frames of
        silence: the halt starts that instead, and it is over at once."""
        self.playing = False
        chan, self._chan = self._chan, None
        if chan is not None:
            try:
                if self._pg is not None and chan.get_queue() is not None:
                    chan.queue(self._pg.mixer.Sound(
                        buffer=b"\x00" * (self.frame_bytes * 16)))
                chan.stop()
            except Exception:
                pass
        self._paused_at = None

    def set_volume(self, v):
        self.volume = max(0.0, min(1.0, v))
        if self._chan is not None:
            self._chan.set_volume(self.volume)

    def set_looping(self, on):
        """Switch mode on the fly, continuing from where it is."""
        on = bool(on)
        if on == self.looping:
            return
        self.looping = on
        if self.playing:
            self.play(self.position())

    def position(self):
        """Current frame, folded back into the loop once it has wrapped."""
        if not self.playing:
            return 0
        now = self._paused_at or time.monotonic()
        pos = self._base + (now - self._t0 - self._paused_total) * self.rate
        if self.looping and self.has_loop() and pos >= self.loop_end:
            span = self.loop_end - self.loop_start
            pos = self.loop_start + (pos - self.loop_start) % span
        return int(min(pos, self.end_frame()))


# ── Smooth drawing ───────────────────────────────────────────────────────
# Tk's canvas draws without anti-aliasing on Windows, so round shapes come
# out jagged. When Pillow is present the panel's icons, knobs and rounded
# card are drawn at four times their size and scaled down, which smooths
# every edge; without it the canvas's own shapes are used.
try:
    from PIL import Image, ImageDraw, ImageTk
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False


def _rgb(hexcol):
    h = hexcol.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,)


def render_icon(name, color, box, playing=False, mini=False, scale=4):
    """One control icon, `box` pixels square, in `color`. Drawn on a
    24-unit grid at 4x and scaled down for smooth edges."""
    S = box * scale
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    k = S / 24.0
    col = _rgb(color)

    def P(*pts):
        return [(x * k, y * k) for x, y in pts]

    lw = max(1, int(round(2.0 * k)))
    if name == "prev":
        d.rectangle(P((6, 6), (8.4, 18)), fill=col)
        d.polygon(P((18, 6), (18, 18), (9.2, 12)), fill=col)
    elif name == "next":
        d.rectangle(P((15.6, 6), (18, 18)), fill=col)
        d.polygon(P((6, 6), (6, 18), (14.8, 12)), fill=col)
    elif name == "play":
        d.ellipse(P((1.2, 1.2), (22.8, 22.8)), outline=col, width=max(1, int(1.3 * k)))
        if playing:
            d.rounded_rectangle(P((8.4, 7.4), (10.8, 16.6)), radius=0.8 * k, fill=col)
            d.rounded_rectangle(P((13.2, 7.4), (15.6, 16.6)), radius=0.8 * k, fill=col)
        else:
            d.polygon(P((9.6, 7.2), (9.6, 16.8), (17.2, 12)), fill=col)
    elif name == "repeat":
        d.line(P((5, 14), (5, 8.5), (16.5, 8.5)), fill=col, width=lw, joint="curve")
        d.polygon(P((15.5, 5.2), (20, 8.5), (15.5, 11.8)), fill=col)
        d.line(P((19, 10), (19, 15.5), (7.5, 15.5)), fill=col, width=lw, joint="curve")
        d.polygon(P((8.5, 12.2), (4, 15.5), (8.5, 18.8)), fill=col)
    elif name == "shuffle":
        d.line(P((3.5, 7.5), (8, 7.5), (14.5, 16.5), (17.5, 16.5)), fill=col, width=lw,
               joint="curve")
        d.polygon(P((16.5, 13.3), (21, 16.5), (16.5, 19.7)), fill=col)
        d.line(P((3.5, 16.5), (8, 16.5), (14.5, 7.5), (17.5, 7.5)), fill=col, width=lw,
               joint="curve")
        d.polygon(P((16.5, 4.3), (21, 7.5), (16.5, 10.7)), fill=col)
    elif name == "mini":
        d.rounded_rectangle(P((3, 5), (21, 19)), radius=1.6 * k, outline=col, width=lw)
        if mini:
            d.rounded_rectangle(P((6, 8), (12.5, 12.5)), radius=0.8 * k, fill=col)
        else:
            d.rounded_rectangle(P((11.5, 11.5), (18, 16)), radius=0.8 * k, fill=col)
    elif name == "speaker":
        d.polygon(P((3.5, 9.5), (7.5, 9.5), (12.5, 5), (12.5, 19), (7.5, 14.5), (3.5, 14.5)),
                  fill=col)
        d.arc(P((9, 7.5), (18, 16.5)), -55, 55, fill=col, width=lw)
    elif name == "search":
        d.ellipse(P((3.5, 3.5), (15, 15)), outline=col, width=lw)
        d.line(P((14, 14), (20.5, 20.5)), fill=col, width=int(lw * 1.2))
    elif name == "knob":
        d.ellipse(P((0.5, 0.5), (23.5, 23.5)), fill=col)
    return im.resize((box, box), Image.LANCZOS)


def render_pill(w, h, fill, scale=4):
    """A solid capsule (fully rounded ends), drawn as two circles and a bar
    at 4x and scaled down -- no seams, smooth ends."""
    W, H = w * scale, h * scale
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    col = _rgb(fill)
    if H >= W:                                   # vertical
        d.ellipse((0, 0, W - 1, W - 1), fill=col)
        d.ellipse((0, H - W, W - 1, H - 1), fill=col)
        d.rectangle((0, W // 2, W - 1, H - W // 2), fill=col)
    else:
        d.ellipse((0, 0, H - 1, H - 1), fill=col)
        d.ellipse((W - H, 0, W - 1, H - 1), fill=col)
        d.rectangle((H // 2, 0, W - H // 2, H - 1), fill=col)
    return im.resize((w, h), Image.LANCZOS)


def render_card(w, h, r, fill, outline, scale=3):
    """A rounded rectangle with a 1px outline, smooth at the corners."""
    im = Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w * scale - 1, h * scale - 1), radius=r * scale,
                        fill=_rgb(fill), outline=_rgb(outline), width=scale)
    return im.resize((w, h), Image.LANCZOS)


def scope_points(pcm, frame, channels, points=72, span=4096):
    """`points` values, -1..1, for the live line: the audio around `frame`
    across `span` frames (about 93 ms at 44.1 kHz). Each point is the
    AVERAGE of its slice rather than one raw sample, which filters out the
    fine high-frequency detail -- the line follows the music's swell and
    pulse instead of thrashing."""
    if not pcm:
        return [0.0] * points
    mv = memoryview(pcm).cast("h")
    total = len(mv) // channels
    base = max(0, min(int(frame), total - span - 1))
    seg = span // points
    sub = max(1, seg // 8)                      # 8 samples per point
    out = []
    for i in range(points):
        a = (base + i * seg) * channels
        vals = mv[a:a + seg * channels:sub * channels]
        out.append(sum(vals) / (32768.0 * max(1, len(vals))))
    return out


# ── Export ───────────────────────────────────────────────────────────────

def _id3_frame(fid, text):
    data = b"\x01" + text.encode("utf-16")      # UTF-16 with BOM
    return fid.encode("ascii") + struct.pack(">I", len(data)) + b"\x00\x00" + data


def id3v2_tag(title=None, album=None, artist=None, track=None):
    """A minimal ID3v2.3 tag -- enough for any player to show the name."""
    frames = b""
    for fid, val in (("TIT2", title), ("TALB", album),
                     ("TPE1", artist), ("TRCK", track)):
        if val:
            frames += _id3_frame(fid, str(val))
    n = len(frames)
    size = bytes(((n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F))
    return b"ID3\x03\x00\x00" + size + frames


def safe_filename(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name or "track"


LAMEENC_JSON = "https://pypi.org/pypi/lameenc/json"


def mp3_lib_dir():
    """Where OmniPlayer keeps the MP3 encoder it fetches -- per Python
    version, since the encoder is compiled for one."""
    return os.path.join(settings_dir(), "lib",
                        "py%d%d" % sys.version_info[:2])


def _use_mp3_lib_dir():
    d = mp3_lib_dir()
    if os.path.isdir(d) and d not in sys.path:
        sys.path.insert(0, d)


def have_mp3():
    try:
        _use_mp3_lib_dir()
        import importlib.util
        return importlib.util.find_spec("lameenc") is not None
    except Exception:
        return False


def _wheel_fits(filename):
    """Is this lameenc build the one for this Python and this machine?"""
    import platform
    v = "cp%d%d" % sys.version_info[:2]
    if ("-%s-%s-" % (v, v)) not in filename:
        return False
    if sys.platform == "win32":
        tag = "win_amd64" if struct.calcsize("P") == 8 else "win32"
        if platform.machine().lower() in ("arm64", "aarch64"):
            tag = "win_arm64"
        return filename.endswith(tag + ".whl")
    if sys.platform.startswith("linux"):
        return "manylinux" in filename and platform.machine() in filename
    return False


def ensure_mp3():
    """Make MP3 export available: fetch the lameenc encoder from PyPI if it
    isn't installed. A wheel is just a zip, so this unpacks the one built
    for this Python into the settings folder and imports it from there --
    which works in the built exe too, where pip can't run."""
    if have_mp3():
        return True
    import urllib.request
    import zipfile
    import importlib
    hdr = {"User-Agent": APP_NAME}
    with urllib.request.urlopen(urllib.request.Request(LAMEENC_JSON, headers=hdr),
                                timeout=30) as r:
        meta = json.load(r)
    wheel = next((u for u in meta.get("urls", []) if _wheel_fits(u["filename"])), None)
    if wheel is None:
        raise VgmError("no MP3 encoder build for Python %d.%d on this machine"
                       % sys.version_info[:2])
    fd, tmp = tempfile.mkstemp(suffix=".whl", prefix="lame_")
    os.close(fd)
    try:
        with urllib.request.urlopen(urllib.request.Request(wheel["url"], headers=hdr),
                                    timeout=60) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        d = mp3_lib_dir()
        os.makedirs(d, exist_ok=True)
        with zipfile.ZipFile(tmp) as z:
            z.extractall(d)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    importlib.invalidate_caches()
    _use_mp3_lib_dir()
    importlib.import_module("lameenc")   # proves it loads
    return True


def export_track(track, title, out_dir, fmt="mp3", bitrate=256,
                 album=DEFAULT_ALBUM, artist=""):
    """Write one track as MP3, FLAC or WAV, as the file plays once through
    -- intro and loop section once, no repeats, no fade. MP3 and FLAC are
    tagged with title, album, track number and artist (the composer).
    Returns the path written."""
    num = track.number
    base = safe_filename(("%03d " % num if num is not None else "") + title)
    fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="bgw_x_")
    os.close(fd)
    try:
        vgm_decode(track.path, tmp, whole=True)
        if fmt == "wav":
            dest = os.path.join(out_dir, base + ".wav")
            shutil.copyfile(tmp, dest)
            return dest
        if fmt == "flac":
            exe = find_flac()
            if not exe:
                raise VgmError("the FLAC encoder isn't here")
            dest = os.path.join(out_dir, base + ".flac")
            args = [exe, "--best", "--silent", "--force", "-o", dest]
            for k, v in (("TITLE", title), ("ALBUM", album), ("ARTIST", artist),
                         ("COMPOSER", artist),
                         ("TRACKNUMBER", str(num) if num is not None else "")):
                if v:
                    args += ["-T", "%s=%s" % (k, v)]
            r = subprocess.run(args + [tmp], capture_output=True,
                               creationflags=_NO_WINDOW)
            if r.returncode != 0 or not os.path.isfile(dest):
                raise VgmError((r.stderr or b"").decode("utf-8", "replace").strip()
                               or "flac failed")
            return dest
        import lameenc
        rate, ch, width, pcm = read_wav(tmp)
        if width != 2:
            raise VgmError("unexpected sample width %d" % width)
        enc = lameenc.Encoder()
        enc.set_bit_rate(int(bitrate))
        enc.set_in_sample_rate(rate)
        enc.set_channels(ch)
        enc.set_quality(2)
        mp3 = enc.encode(pcm) + enc.flush()
        dest = os.path.join(out_dir, base + ".mp3")
        with open(dest, "wb") as f:
            f.write(id3v2_tag(title=title, album=album, artist=artist,
                              track=num))
            f.write(mp3)
        return dest
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


# ── Settings ─────────────────────────────────────────────────────────────

def load_settings():
    try:
        with open(os.path.join(settings_dir(), "settings.json"),
                  encoding="utf-8") as f:
            s = json.load(f)
            return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(s):
    try:
        with open(os.path.join(settings_dir(), "settings.json"), "w",
                  encoding="utf-8") as f:
            json.dump(s, f, indent=2)
    except OSError:
        pass


THEMES = {
    # Dark: charcoal with a red accent.
    # Dark: true black, with a red accent.
    "dark": {"bg": "#000000", "panel": "#000000", "field": "#000000",
             "stripe": "#0b0b0c", "fg": "#e8e8ec", "dim": "#85888f",
             "accent": "#e53935", "accent_hi": "#ff5a52", "sel_fg": "#ffffff",
             "sel_bg": "#2c1214", "border": "#26272b", "trough": "#2e2f34",
             "heading": "#0b0b0c", "warn": "#ff8a80", "card": "#0c0c0e"},
    "light": {"bg": "#eceef1", "panel": "#f4f5f7", "field": "#ffffff",
              "stripe": "#f6f7f9", "fg": "#1f2328", "dim": "#6b7079",
              "accent": "#d32f2f", "accent_hi": "#e53935", "sel_fg": "#ffffff",
              "sel_bg": "#f9dede", "border": "#d3d6db", "trough": "#d9dce1",
              "heading": "#e8eaee", "warn": "#aa3333", "card": "#ffffff"},
}


def apply_theme(root, style, name):
    """Colour every ttk widget, plus the few plain-tk pieces (the window
    background, menus, the combobox drop-down list) that ttk cannot."""
    c = THEMES[name]
    style.theme_use("clam")
    base_font = ("Segoe UI", 10) if sys.platform == "win32" else ("TkDefaultFont", 10)
    style.configure(".", font=base_font)
    style.configure(".", background=c["panel"], foreground=c["fg"],
                    fieldbackground=c["field"], bordercolor=c["border"],
                    darkcolor=c["panel"], lightcolor=c["panel"],
                    troughcolor=c["trough"], selectbackground=c["accent"],
                    selectforeground=c["sel_fg"], insertcolor=c["fg"],
                    arrowcolor=c["fg"], focuscolor=c["accent"])
    style.map(".", background=[("active", c["heading"])],
              foreground=[("disabled", c["dim"])])
    # Text buttons (Open folder, Export, the dialog's buttons): flat fills,
    # no outline, lighter on hover, gold text while pressed.
    style.configure("TButton", background=c["heading"], padding=(10, 4),
                    bordercolor=c["heading"], lightcolor=c["heading"],
                    darkcolor=c["heading"], relief="flat", focusthickness=0)
    style.map("TButton", background=[("pressed", c["border"]), ("active", c["border"])],
              foreground=[("pressed", c["accent"]), ("active", c["accent_hi"])],
              bordercolor=[("active", c["border"])],
              lightcolor=[("active", c["border"])], darkcolor=[("active", c["border"])])
    style.configure("Dim.TLabel", foreground=c["dim"])
    style.configure("Warn.TLabel", foreground=c["warn"])
    style.configure("Now.TLabel", font=("Segoe UI", 10, "bold"))
    for w in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(w, fieldbackground=c["field"], foreground=c["fg"],
                        background=c["heading"])
        style.map(w, fieldbackground=[("readonly", c["field"])],
                  foreground=[("readonly", c["fg"])],
                  selectbackground=[("readonly", c["field"])],
                  selectforeground=[("readonly", c["fg"])])
    # No border of its own: the frame around the list draws the outline.
    style.configure("Treeview", background=c["field"], foreground=c["fg"],
                    fieldbackground=c["field"], rowheight=26,
                    bordercolor=c["field"], lightcolor=c["field"],
                    darkcolor=c["field"], borderwidth=0)
    style.map("Treeview", background=[("selected", c["sel_bg"])],
              foreground=[("selected", c["fg"])],
              # clam draws a blue ring around a focused list; none here
              bordercolor=[("focus", c["field"])], lightcolor=[("focus", c["field"])],
              darkcolor=[("focus", c["field"])])
    # Drop the list's own field border entirely (the frame around it draws
    # the red outline), so no theme colour can show through as a second line.
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    # Headings with a visible divider between columns -- the divider is
    # what you drag to resize, so it has to be findable.
    style.configure("Treeview.Heading", background=c["heading"],
                    foreground=c["dim"], relief="flat", padding=(6, 4),
                    font=(base_font[0], 9, "bold"), borderwidth=1,
                    bordercolor=c["border"], lightcolor=c["heading"],
                    darkcolor=c["border"])
    style.map("Treeview.Heading", background=[("active", c["border"])])
    style.configure("TCheckbutton", background=c["panel"])
    style.configure("TRadiobutton", background=c["panel"])
    for w in ("TCheckbutton", "TRadiobutton"):
        style.configure(w, indicatorbackground=c["field"],
                        indicatorforeground=c["fg"], upperbordercolor=c["border"],
                        lowerbordercolor=c["border"])
        style.map(w, background=[("active", c["panel"])],
                  indicatorbackground=[("selected", c["accent"]),
                                       ("!selected", c["field"])],
                  indicatorforeground=[("selected", c["sel_fg"])])
    style.configure("Tool.TButton", padding=(4, 2))

    def icon_button(name, bg, size, fg=c["fg"], hover_fg=c["accent_hi"], hover_bg=None):
        """Borderless glyph button: no fill, no outline -- just the icon,
        brightening to gold under the pointer."""
        hb = hover_bg or bg
        style.configure(name, background=bg, foreground=fg, bordercolor=bg,
                        lightcolor=bg, darkcolor=bg, relief="flat",
                        focusthickness=0, padding=(4, 0),
                        font=(base_font[0], size))
        style.map(name, background=[("pressed", hb), ("active", hb)],
                  bordercolor=[("active", hb)], lightcolor=[("active", hb)],
                  darkcolor=[("active", hb)],
                  foreground=[("pressed", c["accent"]), ("active", hover_fg)])

    icon_button("Icon.TButton", c["panel"], 15)
    icon_button("Play.TButton", c["panel"], 22, fg=c["accent"], hover_fg=c["accent_hi"])
    icon_button("Bar.TButton", c["heading"], 10)
    icon_button("BarClose.TButton", c["heading"], 10, hover_fg="#ffffff",
                hover_bg="#c42b1c")
    style.configure("Bar.TButton", padding=(3, 0))
    style.configure("BarClose.TButton", padding=(3, 0))
    style.configure("Bar.TFrame", background=c["heading"])
    style.configure("BarTitle.TLabel", background=c["heading"], foreground=c["fg"],
                    font=(base_font[0], 9, "bold"))
    style.configure("BarDim.TLabel", background=c["heading"], foreground=c["dim"])
    # Sliders: an accent-coloured thumb on a slim trough.
    style.configure("Horizontal.TScale", background=c["accent"],
                    troughcolor=c["trough"], bordercolor=c["trough"],
                    lightcolor=c["accent_hi"], darkcolor=c["accent"],
                    sliderthickness=12, gripcount=0)
    style.map("Horizontal.TScale", background=[("active", c["accent_hi"])])
    # The big play button, and the now-playing card.
    style.configure("Accent.TButton", background=c["accent"], foreground=c["sel_fg"],
                    bordercolor=c["accent"], lightcolor=c["accent_hi"],
                    darkcolor=c["accent"], font=(base_font[0], 12, "bold"),
                    padding=(6, 0))
    style.map("Accent.TButton", background=[("pressed", c["accent"]),
                                            ("active", c["accent_hi"])],
              foreground=[("active", c["sel_fg"])])
    style.configure("Card.TFrame", background=c["card"], bordercolor=c["border"],
                    relief="solid", borderwidth=1)
    style.configure("CardTitle.TLabel", background=c["card"], foreground=c["fg"],
                    font=(base_font[0], 14, "bold"))
    style.configure("CardSub.TLabel", background=c["card"], foreground=c["dim"])
    style.configure("CardTime.TLabel", background=c["card"], foreground=c["dim"],
                    font=(base_font[0], 9))
    style.configure("BarIcon.TLabel", background=c["heading"], foreground=c["accent"],
                    font=(base_font[0], 10, "bold"))
    # Scrollbars: a red slider on the list's own background, brighter
    # under the pointer or while dragged; the end arrows stay quiet.
    for sbs in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(sbs, background=c["accent"], troughcolor=c["field"],
                        arrowcolor=c["dim"], bordercolor=c["field"],
                        lightcolor=c["accent"], darkcolor=c["accent"],
                        gripcount=0, arrowsize=11)
        style.map(sbs, background=[("pressed", c["accent_hi"]), ("active", c["accent_hi"])],
                  lightcolor=[("pressed", c["accent_hi"]), ("active", c["accent_hi"])],
                  darkcolor=[("pressed", c["accent_hi"]), ("active", c["accent_hi"])],
                  arrowcolor=[("active", c["accent_hi"])])
    # No end arrows: just the trough and the slider, so the red is only
    # ever the slider itself.
    style.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {
        "sticky": "ns", "children": [
            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    style.layout("Horizontal.TScrollbar", [("Horizontal.Scrollbar.trough", {
        "sticky": "we", "children": [
            ("Horizontal.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    root.configure(background=c["panel"])
    root.option_add("*TCombobox*Listbox.background", c["field"])
    root.option_add("*TCombobox*Listbox.foreground", c["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", c["sel_fg"])
    # Plain tk widgets -- the rename box (simpledialog) is built from these.
    for cls, key, val in (("Toplevel", "background", c["panel"]),
                          ("Frame", "background", c["panel"]),
                          ("Label", "background", c["panel"]),
                          ("Label", "foreground", c["fg"]),
                          ("Entry", "background", c["field"]),
                          ("Entry", "foreground", c["fg"]),
                          ("Entry", "insertBackground", c["fg"]),
                          ("Entry", "selectBackground", c["accent"]),
                          ("Button", "background", c["heading"]),
                          ("Button", "foreground", c["fg"]),
                          ("Button", "activeBackground", c["border"]),
                          ("Button", "activeForeground", c["fg"])):
        root.option_add("*%s.%s" % (cls, key), val)
    root.option_add("*Menu.background", c["field"])
    root.option_add("*Menu.foreground", c["fg"])
    root.option_add("*Menu.activeBackground", c["accent"])
    root.option_add("*Menu.activeForeground", c["sel_fg"])
    _rounded_widgets(root, style, name, c)
    return c


def _rounded_widgets(root, style, theme, c):
    """Rounded text buttons and entry fields. ttk can't round a corner by
    itself, so each state is a small rounded image (drawn smooth with
    Pillow) used as a stretchable 9-slice element. Without Pillow the
    flat square ones stay."""
    if not HAVE_PIL:
        return
    keep = root.__dict__.setdefault("_omni_round_imgs", {})

    def img(fill, outline, w=28, h=22, r=7):
        key = (fill, outline, w, h, r)
        if key not in keep:
            keep[key] = ImageTk.PhotoImage(render_card(w, h, r, fill, outline),
                                           master=root)
        return keep[key]

    b_el, e_el = "omni_rbtn_%s" % theme, "omni_rent_%s" % theme
    try:
        style.element_create(
            b_el, "image", img(c["heading"], c["border"]),
            ("pressed", img(c["border"], c["accent"])),
            ("active", img(c["border"], c["border"])),
            border=8, sticky="nsew")
        style.element_create(
            e_el, "image", img(c["field"], c["border"]),
            ("focus", img(c["field"], c["accent"])),
            border=8, sticky="nsew")
    except Exception:
        pass        # already created for this theme
    style.layout("Round.TButton", [(b_el, {"sticky": "nsew", "children": [
        ("Button.padding", {"sticky": "nsew", "children": [
            ("Button.label", {"sticky": "nsew"})]})]})])
    style.configure("Round.TButton", padding=(12, 1), foreground=c["fg"],
                    background=c["heading"])
    style.map("Round.TButton", foreground=[("pressed", c["accent"]),
                                           ("active", c["accent_hi"])],
              background=[("active", c["border"]), ("pressed", c["border"])])
    style.layout("Round.TEntry", [(e_el, {"sticky": "nsew", "children": [
        ("Entry.padding", {"sticky": "nsew", "children": [
            ("Entry.textarea", {"sticky": "nsew"})]})]})])
    style.configure("Round.TEntry", padding=(8, 1), foreground=c["fg"],
                    fieldbackground=c["field"], insertcolor=c["fg"])

    # Scrollbar sliders as rounded pills: a small rounded image that
    # stretches along its length, red, brighter under the pointer/dragged.
    def pill(fill, w, h):
        key = ("pill", fill, w, h)
        if key not in keep:
            keep[key] = ImageTk.PhotoImage(render_pill(w, h, fill), master=root)
        return keep[key]

    # The names must end in ".thumb": that is how a ttk scrollbar finds the
    # part it sizes and moves. Any other name and the slider is drawn
    # across the whole length of the bar.
    vt = "Omni%sV.Scrollbar.thumb" % theme.capitalize()
    ht = "Omni%sH.Scrollbar.thumb" % theme.capitalize()
    try:
        style.element_create(vt, "image", pill(c["accent"], 9, 24),
                             ("pressed", pill(c["accent_hi"], 9, 24)),
                             ("active", pill(c["accent_hi"], 9, 24)),
                             border=(4, 5, 4, 5), sticky="ns")
        style.element_create(ht, "image", pill(c["accent"], 24, 9),
                             ("pressed", pill(c["accent_hi"], 24, 9)),
                             ("active", pill(c["accent_hi"], 24, 9)),
                             border=(5, 4, 5, 4), sticky="we")
    except Exception:
        pass
    style.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {
        "sticky": "ns", "children": [(vt, {"expand": "1", "sticky": "ns"})]})])
    style.layout("Horizontal.TScrollbar", [("Horizontal.Scrollbar.trough", {
        "sticky": "we", "children": [(ht, {"expand": "1", "sticky": "we"})]})])


def playlists_path():
    return os.path.join(settings_dir(), "playlists.json")


def load_playlists():
    """{name: [file paths, in order]} -- by full path, so a playlist can mix
    tracks from any of the imported folders."""
    try:
        with open(playlists_path(), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): [str(p) for p in v] for k, v in data.items()
                    if isinstance(v, list)}
    except (OSError, ValueError):
        pass
    return {}


def save_playlists(pls):
    try:
        with open(playlists_path(), "w", encoding="utf-8") as f:
            json.dump(pls, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def fmt_time(seconds):
    if seconds is None:
        return ""
    seconds = max(0, int(seconds))
    return "%d:%02d" % (seconds // 60, seconds % 60)


# ── Window ───────────────────────────────────────────────────────────────

def run_app():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    class PlayerView(tk.Canvas):
        """The now-playing panel, drawn by hand on a canvas: the track's
        waveform (played part in gold), a thin progress line under it, and
        round vector icons for repeat / previous / play / next / shuffle,
        plus volume and the mini-player switch. Click or drag on the
        waveform or the line to seek."""

        def __init__(self, master, app):
            super().__init__(master, highlightthickness=0, bd=0, height=196)
            self.app = app
            self.title, self.sub = "Nothing playing", ""
            self.scope = None         # live line samples, -1..1
            self.frac = 0.0
            self.time_text = ""
            self.playing = False
            self.mini = False
            self._seek_drag = None
            self._vol_drag = False
            self._imgs = {}          # rendered images; Tk needs them kept alive
            self._btn_imgs = {}
            self.search_entry = ttk.Entry(self, textvariable=app.search_var,
                                          style="Round.TEntry")
            self.search_entry.bind("<Escape>", lambda e: app.search_var.set(""))
            self.bind("<Configure>", lambda e: self.redraw())
            # In the mini player there is no title strip, so dragging any
            # empty part of the panel moves the window.
            self.bind("<ButtonPress-1>", self._mini_press, add="+")
            self.bind("<B1-Motion>", self._mini_drag, add="+")

        def _on_control(self):
            tags = self.gettags("current")
            return any(t.startswith("b_") or t in ("seekzone", "volzone") for t in tags)

        def _mini_press(self, e):
            self._mini_moving = self.mini and not self._on_control()
            if self._mini_moving:
                self.app._move_start(e)

        def _mini_drag(self, e):
            if getattr(self, "_mini_moving", False):
                self.app._move_drag(e)

        # ── state from the app ───────────────────────────────────────
        def set_track(self, title, sub):
            self.title, self.sub = title, sub
            self.redraw()

        def flash(self, msg, ms=4500):
            """Show a short message in place of the second line for a few
            seconds (this window has no status bar)."""
            self._flash = msg or None
            self._flash_id = getattr(self, "_flash_id", 0) + 1
            fid = self._flash_id
            self.redraw()
            if msg:
                self.after(ms, lambda: fid == self._flash_id and self.flash(""))

        def set_scope(self, pts):
            """Move the live line to these samples (None = a flat line)."""
            if not hasattr(self, "_sx0"):
                return
            n = 72
            pts = pts or [0.0] * n
            # Ease toward the new shape rather than jumping to it.
            prev = getattr(self, "_scope_prev", None)
            if prev is not None and len(prev) == len(pts):
                pts = [p * 0.55 + q * 0.45 for p, q in zip(prev, pts)]
            self._scope_prev = pts
            x0, x1, mid, amp = self._sx0, self._sx1, self._smid, self._samp * 0.85
            step = (x1 - x0) / float(len(pts) - 1)
            coords = []
            for i, v in enumerate(pts):
                # Taper to the centre line at both ends, like a plucked string.
                edge = min(1.0, i / 8.0, (len(pts) - 1 - i) / 8.0)
                v = max(-1.0, min(1.0, v * 1.8)) * edge
                coords += [x0 + i * step, mid - v * amp]
            self.coords("scope", *coords)

        def set_playing(self, on):
            if bool(on) != self.playing:
                self.playing = bool(on)
                if not self.playing:
                    self.scope = None
                self.redraw()

        def set_progress(self, frac, time_text):
            if self._seek_drag is not None:
                return
            self.frac = max(0.0, min(1.0, frac))
            self.time_text = time_text
            self._paint_progress()

        # ── drawing ──────────────────────────────────────────────────
        def _c(self, key):
            return self.app.colors[key]

        def _round_rect(self, x0, y0, x1, y1, r, **kw):
            pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
                   x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
            return self.create_polygon(pts, smooth=True, splinesteps=24, **kw)

        def redraw(self):
            self.delete("all")
            c = self.app.colors
            # The canvas is the window's colour; the card is a rounded panel
            # drawn on it.
            self.configure(background=MINI_KEY if self.mini else c["panel"])
            w = max(self.winfo_width(), 200)
            h = max(self.winfo_height(), 100)
            if HAVE_PIL:
                key = ("card", w, h, c["card"], c["accent"])
                if key not in self._imgs:
                    self._imgs = {k: v for k, v in self._imgs.items() if k[0] != "card"}
                    self._imgs[key] = ImageTk.PhotoImage(
                        render_card(w - 2, h - 2, 16, c["card"], c["accent"]), master=self)
                self.create_image(1, 1, anchor="nw", image=self._imgs[key])
            else:
                self._round_rect(1, 1, w - 2, h - 2, 16, fill=c["card"],
                                 outline=c["accent"])
            pad = 18
            big = ("Segoe UI" if sys.platform == "win32" else "TkDefaultFont")
            # Title, sub line, time (top right)
            self.create_text(pad, 16, text=self.title, anchor="w", fill=c["fg"],
                             font=(big, 12 if self.mini else 14, "bold"))
            flash = getattr(self, "_flash", None)
            self.create_text(pad, 36, text=flash or self.sub, anchor="w",
                             fill=c["accent_hi"] if flash else c["dim"], font=(big, 9))
            self.create_text(w - pad, 16, text=self.time_text, anchor="e",
                             fill=c["dim"], font=(big, 9), tags=("time",))
            # The live line: the music itself, a few milliseconds of it at a
            # time, redrawn as it plays. Flat when nothing is.
            top, wh = 50, (34 if self.mini else 52)
            x0, x1 = pad, w - pad
            self._sx0, self._sx1 = x0, x1
            self._smid, self._samp = top + wh / 2.0, wh / 2.0 - 2
            self._scope_prev = None
            self.create_line(x0, self._smid, x1, self._smid, width=2,
                             fill=c["accent"] if self.playing else c["trough"],
                             smooth=True, capstyle="round", joinstyle="round",
                             tags=("scope",))
            self.set_scope(self.scope)
            # Progress line
            py = top + wh + 12
            self._py, self._x0, self._x1 = py, x0, x1
            self.create_line(x0, py, x1, py, width=3, fill=c["trough"],
                             capstyle="round")
            self.create_line(x0, py, x0, py, width=3, fill=c["accent"],
                             capstyle="round", tags=("played",))
            if HAVE_PIL:
                self.create_image(-50, -50, image=self._img("knob", c["accent_hi"], 12),
                                  tags=("knob",))
            else:
                self.create_oval(0, 0, 0, 0, fill=c["accent_hi"], outline="",
                                 tags=("knob",))
            # Seek zone: waveform + line, on top so it gets the clicks.
            self.create_rectangle(x0 - 4, top - 4, x1 + 4, py + 8, outline="",
                                  fill="", tags=("seekzone",))
            self.tag_bind("seekzone", "<ButtonPress-1>", self._seek_press)
            self.tag_bind("seekzone", "<B1-Motion>", self._seek_move)
            self.tag_bind("seekzone", "<ButtonRelease-1>", self._seek_release)
            # Controls
            cy = py + 36
            cx = w / 2.0
            gap = 48 if self.mini else 56
            self._button("repeat", cx - 2 * gap, cy, self._ico_repeat,
                         active=self.app.repeat_on)
            self._button("prev", cx - gap, cy, self._ico_prev)
            self._button("play", cx, cy, self._ico_play, r=19)
            self._button("next", cx + gap, cy, self._ico_next)
            self._button("shuffle", cx + 2 * gap, cy, self._ico_shuffle,
                         active=self.app.shuffle_on)
            self._button("mini", w - pad - 8, cy, self._ico_mini)
            # Search, left of the repeat button (not in the mini player, which
            # has no list to search).
            ex1 = min(pad + 230, cx - 2 * gap - 28)
            if not self.mini and ex1 - pad > 110:
                if HAVE_PIL:
                    self.create_image(pad + 9, cy, image=self._img("search", c["dim"], 18))
                else:
                    self.create_text(pad + 9, cy, text="⌕", fill=c["dim"])
                self.create_window(pad + 22, cy, anchor="w", window=self.search_entry,
                                   width=int(ex1 - pad - 22), height=26)
            # Volume only where it fits clear of the shuffle button (the mini
            # player is usually too narrow for it).
            vx1 = w - pad - 40
            vx0 = vx1 - 92
            if vx0 - 26 > cx + 2 * gap + 22:
                self._volume(vx0, vx1, cy)
            self._paint_progress()

        def _img(self, name, color, box):
            key = (name, color, box, self.playing if name == "play" else None,
                   self.mini if name == "mini" else None)
            if key not in self._imgs:
                self._imgs[key] = ImageTk.PhotoImage(
                    render_icon(name, color, box, playing=self.playing, mini=self.mini),
                    master=self)
            return self._imgs[key]

        def _button(self, name, x, y, painter, r=16, active=None):
            c = self.app.colors
            tag = "b_" + name
            # A filled backdrop (the card colour) gives the button a hit area.
            self.create_oval(x - r, y - r, x + r, y + r, fill=c["card"], outline="",
                             tags=(tag, tag + "_bg"))
            col = (c["accent"] if active else (c["dim"] if active is False else c["fg"]))
            if HAVE_PIL:
                box = 42 if name == "play" else 26
                normal = self._img(name, col, box)
                hover = self._img(name, c["accent_hi"], box)
                self._btn_imgs[tag] = (normal, hover)
                self.create_image(x, y, image=normal, tags=(tag, tag + "_img"))
            else:
                painter(x, y, col, tag)
            self.tag_bind(tag, "<Enter>", lambda e: self._hover(tag, True, active))
            self.tag_bind(tag, "<Leave>", lambda e: self._hover(tag, False, active))
            self.tag_bind(tag, "<ButtonRelease-1>", lambda e: self.app.view_action(name))

        def _hover(self, tag, on, active):
            c = self.app.colors
            base = c["accent"] if active else (c["dim"] if active is False else c["fg"])
            col = c["accent_hi"] if on else base
            self.configure(cursor="hand2" if on else "")
            if tag in self._btn_imgs:
                self.itemconfigure(tag + "_img", image=self._btn_imgs[tag][1 if on else 0])
                return
            for item in self.find_withtag(tag + "_ico"):
                kind = self.type(item)
                if kind in ("line",):
                    self.itemconfigure(item, fill=col)
                elif kind in ("polygon", "rectangle") and self.itemcget(item, "fill"):
                    self.itemconfigure(item, fill=col)
                if kind in ("oval", "rectangle", "polygon") and self.itemcget(item, "outline"):
                    self.itemconfigure(item, outline=col)

        # vector icons -- every item tagged <tag>_ico so hover can recolour it
        def _ico_prev(self, x, y, col, tag):
            t = (tag, tag + "_ico")
            self.create_line(x - 7, y - 7, x - 7, y + 7, width=3, fill=col, tags=t)
            self.create_polygon(x + 7, y - 7, x + 7, y + 7, x - 4, y, fill=col,
                                outline="", tags=t)

        def _ico_next(self, x, y, col, tag):
            t = (tag, tag + "_ico")
            self.create_line(x + 7, y - 7, x + 7, y + 7, width=3, fill=col, tags=t)
            self.create_polygon(x - 7, y - 7, x - 7, y + 7, x + 4, y, fill=col,
                                outline="", tags=t)

        def _ico_play(self, x, y, col, tag):
            t = (tag, tag + "_ico")
            self.create_oval(x - 19, y - 19, x + 19, y + 19, outline=col, width=2,
                             fill="", tags=t)
            if self.playing:
                self.create_rectangle(x - 6, y - 7, x - 2, y + 7, fill=col, outline="", tags=t)
                self.create_rectangle(x + 2, y - 7, x + 6, y + 7, fill=col, outline="", tags=t)
            else:
                self.create_polygon(x - 4, y - 8, x - 4, y + 8, x + 8, y, fill=col,
                                    outline="", tags=t)

        def _ico_repeat(self, x, y, col, tag):
            t = (tag, tag + "_ico")
            kw = dict(width=2, fill=col, tags=t, arrow="last", arrowshape=(5, 6, 3))
            self.create_line(x - 9, y + 3, x - 9, y - 5, x + 8, y - 5, **kw)
            self.create_line(x + 9, y - 3, x + 9, y + 5, x - 8, y + 5, **kw)

        def _ico_shuffle(self, x, y, col, tag):
            t = (tag, tag + "_ico")
            kw = dict(width=2, fill=col, tags=t, arrow="last", arrowshape=(5, 6, 3))
            self.create_line(x - 10, y - 6, x - 4, y - 6, x + 3, y + 6, x + 10, y + 6, **kw)
            self.create_line(x - 10, y + 6, x - 4, y + 6, x + 3, y - 6, x + 10, y - 6, **kw)

        def _ico_mini(self, x, y, col, tag):
            t = (tag, tag + "_ico")
            self.create_rectangle(x - 9, y - 7, x + 9, y + 7, outline=col, width=2,
                                  fill="", tags=t)
            if self.mini:      # "back to full": the small box sits top-left
                self.create_rectangle(x - 6, y - 4, x, y, fill=col, outline="", tags=t)
            else:
                self.create_rectangle(x + 1, y + 1, x + 6, y + 4, fill=col, outline="", tags=t)

        def _volume(self, x0, x1, y):
            c = self.app.colors
            # speaker
            sx = x0 - 18
            if HAVE_PIL:
                self.create_image(sx, y, image=self._img("speaker", c["dim"], 22))
            else:
                self.create_polygon(sx - 5, y - 3, sx - 1, y - 3, sx + 4, y - 7, sx + 4,
                                    y + 7, sx - 1, y + 3, sx - 5, y + 3, fill=c["dim"],
                                    outline="")
            self._vx0, self._vx1, self._vy = x0, x1, y
            self.create_line(x0, y, x1, y, width=3, fill=c["trough"], capstyle="round")
            self.create_line(x0, y, x0, y, width=3, fill=c["accent"], capstyle="round",
                             tags=("vol",))
            if HAVE_PIL:
                self.create_image(-50, -50, image=self._img("knob", c["fg"], 12),
                                  tags=("volknob",))
            else:
                self.create_oval(0, 0, 0, 0, fill=c["fg"], outline="", tags=("volknob",))
            self.create_rectangle(x0 - 6, y - 9, x1 + 6, y + 9, outline="", fill="",
                                  tags=("volzone",))
            self.tag_bind("volzone", "<ButtonPress-1>", self._vol_set)
            self.tag_bind("volzone", "<B1-Motion>", self._vol_set)
            self._paint_volume()

        def _paint_volume(self):
            if not self.find_withtag("vol"):
                return
            v = self.app.engine.volume
            x = self._vx0 + (self._vx1 - self._vx0) * v
            self.coords("vol", self._vx0, self._vy, x, self._vy)
            if HAVE_PIL:
                self.coords("volknob", x, self._vy)
            else:
                self.coords("volknob", x - 5, self._vy - 5, x + 5, self._vy + 5)

        def _vol_set(self, e):
            v = (e.x - self._vx0) / float(self._vx1 - self._vx0)
            self.app.set_volume(max(0.0, min(1.0, v)))
            self._paint_volume()

        def _paint_progress(self):
            if not hasattr(self, "_x0"):
                return
            x = self._x0 + (self._x1 - self._x0) * self.frac
            self.coords("played", self._x0, self._py, x, self._py)
            on = bool(self.app.engine.pcm)
            if HAVE_PIL:
                self.coords("knob", x if on else -50, self._py if on else -50)
            else:
                r = 5 if on else 0
                self.coords("knob", x - r, self._py - r, x + r, self._py + r)
            self.itemconfigure("time", text=self.time_text)

        # ── seeking ──────────────────────────────────────────────────
        def _frac_at(self, x):
            return max(0.0, min(1.0, (x - self._x0) / float(self._x1 - self._x0)))

        def _seek_press(self, e):
            if not self.app.engine.pcm:
                return
            self._seek_drag = self._frac_at(e.x)
            self.frac = self._seek_drag
            self._paint_progress()

        def _seek_move(self, e):
            if self._seek_drag is None:
                return
            self._seek_drag = self.frac = self._frac_at(e.x)
            self._paint_progress()

        def _seek_release(self, e):
            if self._seek_drag is None:
                return
            f = self._frac_at(e.x)
            self._seek_drag = None
            self.app.seek_to(f)

    class App:
        def __init__(self, root):
            self.root = root
            self.settings = load_settings()
            self.lib = Library()
            self.engine = Engine()
            self.engine.volume = float(self.settings.get("volume", 0.8))
            self.engine.looping = self.settings.get("repeat", LOOP_FOREVER) == LOOP_FOREVER
            self.current = None          # Track playing
            self.visible = []            # tracks in the list, in order
            self.history = []
            self._loading = False
            self.playlists = load_playlists()
            self.view_mode = "all"           # "all" or a playlist name
            self.popup = InMenu(self)
            self.repeat_on = self.settings.get("repeat", LOOP_FOREVER) == LOOP_FOREVER
            self.shuffle_on = bool(self.settings.get("shuffle", False))
            self.mini = False

            root.title(APP_NAME)
            self.style = ttk.Style()
            self.theme = self.settings.get("theme", "dark")
            if self.theme not in THEMES:
                self.theme = "dark"
            self.colors = apply_theme(root, self.style, self.theme)
            self._initial_geometry = self.settings.get("geometry", "820x560")
            root.geometry(self._initial_geometry)
            root.minsize(520, 320)
            root.protocol("WM_DELETE_WINDOW", self.on_close)

            # BORDERLESS. The window draws its own title strip (name, theme,
            # minimise, maximise, close) and its own resize grip; Shift+drag
            # anywhere moves it, as does a plain drag on the title strip. The
            # root's background shows through a one-pixel gap as the outline.
            # Windows: an ordinary window whose title bar is switched off at the
            # source (see _hook_frame), so Windows still manages it like any
            # app -- it stays on its own virtual desktop, has its taskbar
            # button, Alt+Tab, minimise, Windows 11's rounded corners and
            # shadow. It starts invisible and appears once the bar is gone, so
            # the bar never flashes. Elsewhere Tk's override-redirect is used.
            if sys.platform == "win32":
                try:
                    root.attributes("-alpha", 0.0)
                    # Whatever happens, never stay invisible for long.
                    root.after(1500, lambda: root.attributes("-alpha", 1.0))
                except tk.TclError:
                    pass
            else:
                root.overrideredirect(True)
            root.configure(background=self.colors["dim"])
            self._maxed = None            # geometry to restore from maximise
            body = ttk.Frame(root)
            body.pack(fill="both", expand=True, padx=1, pady=1)
            self.body = body

            bar = ttk.Frame(body, style="Bar.TFrame", padding=(8, 0, 2, 0))
            bar.pack(fill="x")
            self._bar = bar
            # The app icon doubles as the settings button: click it for the
            # menu (import, export, columns, playlists, folders).
            self._icon_imgs = []
            try:
                full = tk.PhotoImage(data=APP_ICON_PNG, master=root)
                self._icon_imgs.append(full)
                root.iconphoto(True, full)              # taskbar / Alt+Tab
                if HAVE_PIL:
                    import base64
                    im = Image.open(io.BytesIO(base64.b64decode(APP_ICON_PNG)))
                    small = ImageTk.PhotoImage(im.resize((18, 18), Image.LANCZOS),
                                               master=root)
                else:
                    small = full.subsample(3, 3)
                self._icon_imgs.append(small)
                icon = ttk.Label(bar, image=small, style="BarIcon.TLabel", cursor="hand2")
            except Exception:
                icon = ttk.Label(bar, text="♪", style="BarIcon.TLabel", cursor="hand2")
            icon.pack(side="left", padx=(0, 6), pady=2)
            self.icon_lbl = icon
            icon.bind("<ButtonPress-1>", lambda e: self.show_settings_menu())
            self.title_lbl = ttk.Label(bar, text=APP_NAME, style="BarTitle.TLabel")
            self.title_lbl.pack(side="left")
            for txt, cmd, sty in (("✕", self.on_close, "BarClose.TButton"),
                                  ("▢", self.toggle_max, "Bar.TButton"),
                                  ("—", self.minimize, "Bar.TButton")):
                b = ttk.Button(bar, text=txt, width=3, style=sty, command=cmd,
                               takefocus=False)
                b.pack(side="right", padx=(2, 0))
            self.theme_btn = ttk.Button(bar, width=3, style="Bar.TButton",
                                        command=self.toggle_theme, takefocus=False)
            self.theme_btn.pack(side="right", padx=(2, 6))
            for w in (bar, self.title_lbl):
                w.bind("<ButtonPress-1>", self._move_start)
                w.bind("<B1-Motion>", self._move_drag)
                w.bind("<Double-1>", lambda e: self.toggle_max())

            # The search box sits in the player panel, left of the controls.
            self.search_var = tk.StringVar()
            self.search_var.trace_add("write", lambda *_: self.refresh_list())
            self._top = None

            # Middle: view tabs, then the track list
            mid = ttk.Frame(body, padding=(4, 4, 4, 2))
            mid.pack(fill="both", expand=True)
            self._mid = mid
            cols = ("fav", "num", "name", "length", "expansion", "composer", "file", "path")
            # The red outline is a rounded box drawn on this canvas, around
            # the list AND its scrollbars (they sit in a frame placed inside
            # it, inset just enough that their square corners stay within
            # the curve).
            c0 = self.colors
            self.list_canvas = tk.Canvas(mid, highlightthickness=0, bd=0,
                                         background=c0["panel"])
            self.list_canvas.grid(row=1, column=0, sticky="nsew")
            self.list_box = tk.Frame(self.list_canvas, bd=0, highlightthickness=0,
                                     background=c0["field"])
            self._list_win = self.list_canvas.create_window(
                0, 0, anchor="nw", window=self.list_box)
            self._list_img = None
            self.list_canvas.bind("<Configure>", lambda e: self._draw_list_box())
            self.tree = ttk.Treeview(self.list_box, columns=cols, show="headings",
                                     selectmode="extended")
            widths = self.settings.get("columns") or {}
            self._col_labels = {}
            srt = self.settings.get("sort") or [None, False]
            self.sort_col, self.sort_desc = srt[0], bool(srt[1])
            for c, label, w, mw, anchor in (("fav", "♥", 30, 26, "center"),
                                             ("num", "#", 54, 34, "e"),
                                             ("name", "NAME", 360, 120, "w"),
                                             ("length", "LENGTH", 80, 56, "center"),
                                             ("expansion", "EXPANSION", 170, 70, "w"),
                                             ("composer", "COMPOSER", 140, 70, "w"),
                                             ("file", "FILE", 140, 70, "w"),
                                             ("path", "FILE PATH", 320, 80, "w")):
                self._col_labels[c] = (("  " + label) if c in ("file", "path", "expansion",
                                                               "composer") else label)
                self.tree.heading(c, text=self._col_labels[c], anchor=anchor,
                                  command=lambda col=c: self.sort_by(col))
                # No column stretches: each is exactly as wide as you drag it,
                # and a scrollbar appears when they add up to more than fits.
                self.tree.column(c, width=int(widths.get(c, w)), minwidth=mw,
                                 anchor=anchor, stretch=False)
            self.tree.bind("<Motion>", self._tree_cursor, add="+")
            self.tree.bind("<ButtonRelease-1>", self._tree_click, add="+")
            self._apply_hidden_columns()
            self._sort_headings()
            sb = ttk.Scrollbar(self.list_box, orient="vertical", command=self.tree.yview)
            hsb = ttk.Scrollbar(self.list_box, orient="horizontal", command=self.tree.xview)
            def _hset(first, last, bar=hsb):
                # Only there when the columns are wider than the list.
                if float(first) <= 0.0 and float(last) >= 1.0:
                    bar.grid_remove()
                else:
                    bar.grid()
                bar.set(first, last)
            self.tree.configure(yscrollcommand=sb.set, xscrollcommand=_hset)
            mid.columnconfigure(0, weight=1)
            mid.rowconfigure(1, weight=1)
            self.list_box.columnconfigure(0, weight=1)
            self.list_box.rowconfigure(0, weight=1)
            self.tree.grid(row=0, column=0, sticky="nsew")
            sb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            self._drag_col = None
            self.tree.bind("<ButtonPress-1>", self._col_press, add="+")
            self.tree.bind("<B1-Motion>", self._col_motion, add="+")
            self.tree.bind("<ButtonRelease-1>", self._col_release, add="+")
            self.tree.bind("<Double-1>", lambda e: self.play_selected())
            self.tree.bind("<Return>", lambda e: self.play_selected())
            self.tree.bind("<F2>", lambda e: self.track_info())
            self.tree.bind("<Delete>", lambda e: self.remove_selected())
            self.tree.bind("<Control-a>", lambda e: (self.tree.selection_set(
                self.tree.get_children()), "break")[1])
            self.tree.bind("<Button-3>", self.on_right_click)
            self._tag_colors()

            c0 = self.colors
            # (the row menu is built fresh on each right-click -- see
            # on_right_click -- so its playlist items are always current)

            # Bottom: the drawn now-playing panel.
            bot = ttk.Frame(body, padding=(4, 0, 4, 2))
            bot.pack(fill="x")
            self._bot = bot
            self.view = PlayerView(bot, self)
            self.view.pack(fill="x")

            # No status row: messages (imports, removals, downloads) show for
            # a few seconds in the player panel's second line instead, so the
            # window ends at the bottom of the player.
            self.status_var = tk.StringVar(value="")
            self.status_var.trace_add("write", lambda *_: self.view.flash(
                self.status_var.get()))
            # Packing order decides who gives way when the window gets short:
            # the player is claimed from the bottom FIRST and the track list
            # (re-packed last) takes what is left, so shrinking the window
            # shrinks the list, never the controls.
            bot.pack_forget()
            bot.pack(side="bottom", fill="x")
            mid.pack_forget()
            mid.pack(fill="both", expand=True)
            # The resize grip floats in the window's bottom-right corner.
            grip = tk.Label(root, text="◢", background=self.colors["card"],
                            foreground=self.colors["dim"], bd=0, padx=0, pady=0,
                            font=(("Segoe UI" if sys.platform == "win32"
                                   else "TkDefaultFont"), 8),
                            cursor=("size_nw_se" if sys.platform == "win32"
                                    else "bottom_right_corner"))
            grip.place(relx=1.0, rely=1.0, x=-6, y=-6, anchor="se")
            grip.bind("<ButtonPress-1>", self._grip_start)
            grip.bind("<B1-Motion>", self._grip_drag)
            self._grip_lbl = grip

            # Shift+drag anywhere. Bound on the root, which is in every
            # child's bindtags, so it works over any widget in the window.
            root.bind("<Shift-ButtonPress-1>", self._move_start)
            root.bind("<Shift-B1-Motion>", self._move_drag)
            root.bind("<space>", self.on_space)
            # Keep a taskbar button and Alt+Tab entry, which a borderless
            # window otherwise loses on Windows.
            root.after(10, self._as_app_window)
            self._paint_theme()
            self._downloading = False

            self.lib.removed = {os.path.normcase(p)
                                for p in self.settings.get("removed_tracks", [])}
            folders = self.settings.get("folders")
            if folders is None:                      # older settings: one folder
                folders = [self.settings["folder"]] if self.settings.get("folder") else []
            for d in folders:
                if os.path.isdir(d):
                    try:
                        self.lib.add(d)
                    except OSError:
                        pass
            self.refresh_list()
            self._fill_missing()
            self.root.after(150, self.tick)
            self.root.after(200, self.scope_tick)
            if not find_vgmstream():
                self.root.after(400, self.offer_vgmstream)
            if self.settings.get("mini"):
                self.root.after(50, self.toggle_mini)

        # ── borderless window ────────────────────────────────────────
        def _hwnd(self):
            """The top-level window Windows sees (Tk's wrapper around ours)."""
            import ctypes
            from ctypes import wintypes
            u32 = ctypes.windll.user32
            u32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
            u32.GetAncestor.restype = wintypes.HWND
            u32.GetParent.argtypes = [wintypes.HWND]
            u32.GetParent.restype = wintypes.HWND
            wid = self.root.winfo_id()
            return u32.GetAncestor(wid, 2) or u32.GetParent(wid)    # GA_ROOT

        def _round_corners(self, _e=None):
            """Round the window's corners. Windows 11 does it properly (smooth,
            with its own thin border) when asked through DWM; older Windows
            gets a rounded window region instead, redone on every resize."""
            if sys.platform != "win32":
                return
            try:
                import ctypes
                hwnd = self._hwnd()
                if not hwnd:
                    return
                if sys.getwindowsversion().build >= 22000:
                    # Once per theme/mode/window: this runs on every <Configure>
                    # and from tick. The window handle is part of the key
                    # because Tk sometimes rebuilds its outer window, and the
                    # new one starts square.
                    mode = (self.theme, self.mini, int(hwnd))
                    if getattr(self, "_dwm_round", None) == mode:
                        return
                    self._dwm_round = mode
                    # The mini player draws its own rounded panel and makes the
                    # corners see-through, so Windows mustn't round or outline it.
                    pref = ctypes.c_int(1 if self.mini else 2)   # DONOTROUND / ROUND
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, 33, ctypes.byref(pref), 4)
                    # Windows draws the rounded outline itself, in the colour the
                    # window's own one-pixel outline used to be -- and that
                    # square inner outline is hidden, so there is just one line,
                    # rounded at the corners.
                    col = self.colors["dim"].lstrip("#")
                    ref = ctypes.c_uint(0xFFFFFFFE if self.mini else
                                        int(col[4:6] + col[2:4] + col[0:2], 16))
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(   # border colour
                        hwnd, 34, ctypes.byref(ref), 4)
                    if not self.mini:
                        self.root.configure(background=self.colors["panel"])
                    return
                w, h = self.root.winfo_width(), self.root.winfo_height()
                key = (w, h, int(hwnd), self.mini, bool(self._maxed))
                if key == getattr(self, "_rgn_size", None):
                    return
                self._rgn_size = key
                rad = 0 if self._maxed else (32 if self.mini else 18)
                rgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, rad, rad)
                ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
            except Exception:
                pass

        def _hook_frame(self):
            """Remove the Windows title bar and border by answering
            WM_NCCALCSIZE with "the whole window is client area".

            The window keeps its normal styles, so Windows treats it as an
            ordinary app window (and Tk is free to rebuild or restyle it); only
            the frame it would draw is gone. If Tk does rebuild the outer
            window, the new one is hooked too (tick calls this; it's a cheap
            no-op once the current window is hooked)."""
            if sys.platform != "win32":
                return
            try:
                import ctypes
                from ctypes import wintypes
                hwnd = self._hwnd()
                if not hwnd or getattr(self, "_hooked_hwnd", None) == hwnd:
                    return
                u32 = ctypes.windll.user32
                LRESULT = ctypes.c_ssize_t
                WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                                             wintypes.WPARAM, wintypes.LPARAM)
                u32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND,
                                                wintypes.UINT, wintypes.WPARAM,
                                                wintypes.LPARAM]
                u32.CallWindowProcW.restype = LRESULT
                if hasattr(u32, "SetWindowLongPtrW"):          # 64-bit
                    getp, setp = u32.GetWindowLongPtrW, u32.SetWindowLongPtrW
                else:                                         # 32-bit Python
                    getp, setp = u32.GetWindowLongW, u32.SetWindowLongW
                getp.argtypes = [wintypes.HWND, ctypes.c_int]
                getp.restype = ctypes.c_void_p
                setp.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
                setp.restype = ctypes.c_void_p
                GWLP_WNDPROC, WM_NCCALCSIZE = -4, 0x0083
                old = getp(hwnd, GWLP_WNDPROC)

                u32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                               wintypes.WPARAM, wintypes.LPARAM]
                u32.DefWindowProcW.restype = LRESULT

                def proc(h, msg, wp, lp):
                    # Runs for every message the window gets, so it must never let
                    # an exception escape into Windows.
                    try:
                        if msg == WM_NCCALCSIZE and wp:
                            return 0      # no title bar, no border: all client
                        return u32.CallWindowProcW(old, h, msg, wp, lp)
                    except Exception:
                        return u32.DefWindowProcW(h, msg, wp, lp)

                cb = WNDPROC(proc)
                # Keep every hook alive: Windows may still call an older one.
                self.__dict__.setdefault("_wndprocs", []).append((cb, old))
                setp(hwnd, GWLP_WNDPROC, ctypes.cast(cb, ctypes.c_void_p).value)
                self._hooked_hwnd = hwnd
                u32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                             ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                             ctypes.c_uint]
                # SWP_NOMOVE|NOSIZE|NOZORDER|NOACTIVATE|FRAMECHANGED
                u32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 |
                                 0x0010 | 0x0020)
            except Exception:
                pass

        def _frame_extra(self):
            """How much bigger than asked Tk makes the window: it still adds
            room for the title bar and border it thinks the window has, though
            _hook_frame has made all of it client area. 0,0 until hooked."""
            if sys.platform != "win32" or not getattr(self, "_hooked_hwnd", None):
                return 0, 0
            try:
                import ctypes
                from ctypes import wintypes
                u32 = ctypes.windll.user32
                hwnd = self._hooked_hwnd
                u32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
                u32.GetWindowLongW.restype = ctypes.c_long
                style = u32.GetWindowLongW(hwnd, -16) & 0xFFFFFFFF
                ex = u32.GetWindowLongW(hwnd, -20) & 0xFFFFFFFF
                rc = wintypes.RECT(0, 0, 0, 0)
                u32.AdjustWindowRectEx.argtypes = [ctypes.POINTER(wintypes.RECT),
                                                   wintypes.DWORD, wintypes.BOOL,
                                                   wintypes.DWORD]
                u32.AdjustWindowRectEx(ctypes.byref(rc), style, False, ex)
                return rc.right - rc.left, rc.bottom - rc.top
            except Exception:
                return 0, 0

        def _set_geometry(self, g):
            """root.geometry(g), but with a size that comes out at that size
            (see _frame_extra)."""
            m = re.match(r"^(\d+)x(\d+)(.*)$", g or "")
            if m:
                ex, ey = self._frame_extra()
                g = "%dx%d%s" % (max(50, int(m.group(1)) - ex),
                                 max(50, int(m.group(2)) - ey), m.group(3))
            self.root.geometry(g)

        def _as_app_window(self):
            if sys.platform != "win32":
                return
            self._hook_frame()
            self._set_geometry(self._initial_geometry)
            try:
                self.root.attributes("-alpha", 1.0)      # now it can be seen
            except tk.TclError:
                pass
            self.root.after(40, self._round_corners)
            self.root.bind("<Configure>", self._round_corners, add="+")

        def _move_start(self, e):
            if self._maxed:
                return "break"
            # On Windows, hand the drag to Windows itself, exactly as if the title
            # bar had been grabbed: the system moves the whole window in one piece
            # with the mouse, so the contents can't trail behind the frame. (Moving
            # it from Tk, one geometry change per mouse event, is what drifted.)
            # The mini player keeps Tk's own move so Windows can't snap it to half
            # the screen.
            hwnd = getattr(self, "_hooked_hwnd", None)
            if sys.platform == "win32" and hwnd and not self.mini:
                try:
                    import ctypes
                    from ctypes import wintypes
                    u32 = ctypes.windll.user32
                    u32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                                 wintypes.WPARAM, wintypes.LPARAM]
                    u32.ReleaseCapture()
                    # POSTED, not sent: Windows' drag runs its own loop until the
                    # button is let go, and running that loop from inside this Tk
                    # callback re-entered Tk underneath Python and crashed. Posted,
                    # it starts a moment later from Tk's own message loop instead.
                    u32.PostMessageW(hwnd, 0x00A1, 2, 0)    # WM_NCLBUTTONDOWN, HTCAPTION
                    self._drag = None
                    return "break"
                except Exception:
                    pass
            self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())
            return "break"

        def _check_snapped(self):
            """If Windows maximised the window (dragged to the top of the screen),
            swap that for OmniPlayer's own maximise: Windows' version would push
            the edges a few pixels off the screen, since its frame is hidden."""
            try:
                if self.mini or self.root.state() != "zoomed":
                    return
            except tk.TclError:
                return
            self.root.state("normal")            # back to the size it had before
            self.root.after(20, lambda: None if self._maxed else self.toggle_max())

        def _move_drag(self, e):
            d = getattr(self, "_drag", None)
            if d and not self._maxed:
                self.root.geometry("+%d+%d" % (e.x_root - d[0], e.y_root - d[1]))
            return "break"

        def _grip_start(self, e):
            self._grip = (e.x_root, e.y_root, self.root.winfo_width(),
                          self.root.winfo_height())
            return "break"

        def _grip_drag(self, e):
            x0, y0, w0, h0 = self._grip
            mw, mh = self.root.minsize()
            w = max(mw, w0 + e.x_root - x0)
            h = max(mh, h0 + e.y_root - y0)
            self._set_geometry("%dx%d" % (w, h))
            self._maxed = None
            return "break"

        def minimize(self):
            if sys.platform == "win32":
                self.root.iconify()            # an ordinary window: just minimise
                return
            # Tk refuses to iconify a borderless window; lift the flag for
            # the moment it takes, and put it back when it is shown again.
            self.root.overrideredirect(False)
            self.root.iconify()

            def back(_e=None):
                self.root.overrideredirect(True)
                self.root.unbind("<Map>")
            self.root.bind("<Map>", back)

        def toggle_max(self):
            r = self.root
            if self._maxed:
                self._set_geometry(self._maxed)
                self._maxed = None
                return
            self._maxed = r.geometry()
            x, y, w, h = 0, 0, r.winfo_screenwidth(), r.winfo_screenheight()
            if sys.platform == "win32":
                try:
                    # The work area of the monitor the window is on, so the
                    # taskbar stays visible.
                    import ctypes
                    from ctypes import wintypes

                    class MI(ctypes.Structure):
                        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
                    u32 = ctypes.windll.user32
                    mon = u32.MonitorFromWindow(self._hwnd(), 2)
                    mi = MI()
                    mi.cbSize = ctypes.sizeof(MI)
                    if u32.GetMonitorInfoW(mon, ctypes.byref(mi)):
                        rc = mi.rcWork
                        x, y, w, h = rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top
                except Exception:
                    pass
            self._set_geometry("%dx%d+%d+%d" % (w, h, x, y))

        # ── theme ────────────────────────────────────────────────────
        def _paint_theme(self):
            dark = self.theme == "dark"
            self.theme_btn.configure(text="☀" if dark else "☾")
            self.root.configure(background=self.colors["dim"])

        def toggle_theme(self):
            self.theme = "light" if self.theme == "dark" else "dark"
            self.colors = apply_theme(self.root, self.style, self.theme)
            c = self.colors
            self.list_box.configure(background=c["field"])
            self._draw_list_box()
            self.popup.close()
            for w in self.root.winfo_children():
                if isinstance(w, tk.Toplevel):
                    # The borderless export window's outline colour.
                    w.configure(background=c["dim"])
            self._paint_theme()
            self._grip_lbl.configure(background=c["card"], foreground=c["dim"])
            self._tag_colors()
            self.view.redraw()
            self._round_corners()
            self.settings["theme"] = self.theme
            self.save()

        # ── vgmstream ────────────────────────────────────────────────
        def offer_vgmstream(self):
            """vgmstream is missing: offer to fetch it rather than send
            the user off to find and unpack it by hand."""
            if self._downloading or find_vgmstream():
                return False
            if sys.platform != "win32":
                messagebox.showerror(APP_NAME, "vgmstream-cli was not found. "
                                     "Install it and put it on your PATH.")
                return False
            if not messagebox.askyesno(
                    APP_NAME,
                    APP_NAME + " uses vgmstream to read the game's music files, "
                    "and it isn't here yet.\n\nDownload it now? (about 4 MB, "
                    "from vgmstream's official releases on GitHub)"):
                self.status_var.set("vgmstream is needed to play anything -- "
                                    "click a track to be asked again.")
                return False
            self._downloading = True
            self.status_var.set("Downloading vgmstream…")

            def work():
                def prog(got, total):
                    if total:
                        self.root.after(0, lambda: self.status_var.set(
                            "Downloading vgmstream… %d%%" % (got * 100 // total)))
                try:
                    path = download_vgmstream(prog)
                    err = None
                except Exception as e:
                    path, err = None, str(e)
                self.root.after(0, lambda: self._vgm_done(path, err))

            threading.Thread(target=work, daemon=True).start()
            return True

        def _vgm_done(self, path, err):
            self._downloading = False
            if err:
                self.status_var.set("")
                messagebox.showerror(APP_NAME, "Could not download vgmstream:\n%s\n\n"
                                     "You can also extract vgmstream-win64.zip from "
                                     "vgmstream.org next to %s yourself." % (err, APP_NAME))
                return
            self.status_var.set("vgmstream ready.")
            missing = [t for t in self.lib.tracks if t.info is None]
            if missing:
                self._fill_missing()

        # ── folder & list ────────────────────────────────────────────
        def show_settings_menu(self):
            """The settings menu (click the app icon): import, export, the
            columns to show, playlists, rescan. Clicking the icon again closes
            it. Drawn inside the player window (see InMenu)."""
            if self.popup.is_open():
                self.popup.close()
                return
            shown = set(self._shown_columns())
            cols = [("check", self.COL_NAMES[cid], cid in shown,
                     lambda c_=cid: self.toggle_column(c_))
                    for cid in self.ALL_COLS if cid != "name"]
            pls = [("radio", "All tracks", self.view_mode == "all",
                    lambda: self.set_view("all"))]
            pls += [("radio", n, self.view_mode == n, lambda n_=n: self.set_view(n_))
                    for n in self.playlists]
            pls += [("sep",), ("cmd", "New playlist…", lambda: self.new_playlist([]))]
            if self.view_mode != "all":
                cur = self.view_mode
                pls += [("cmd", "Rename %s…" % cur, lambda: self.rename_playlist(cur)),
                        ("cmd", "Delete %s" % cur, lambda: self.delete_playlist(cur))]
            spec = [("cmd", "Import folder…", self.import_folder),
                    ("cmd", "Export selected…", self.export_selected),
                    ("sep",),
                    ("sub", "Columns", cols),
                    ("sub", "Playlists", pls)]
            if self.lib.folders:
                spec += [("sep",), ("cmd", "Rescan folders", self.rescan_folders)]
            # Which build this is, so two copies can be told apart.
            spec += [("sep",), ("cmd", "About %s %s…" % (APP_NAME, APP_VERSION),
                                 lambda: AboutDialog(self))]
            b = self.icon_lbl
            self.popup.show(spec, b.winfo_rootx(), b.winfo_rooty() + b.winfo_height() + 2)

        def import_folder(self):
            start = self.lib.roots[-1] if self.lib.roots else None
            d = filedialog.askdirectory(title="Folder holding .bgw files",
                                        initialdir=start)
            if not d:
                return
            try:
                n = self.lib.add(d, restore=True)
            except OSError as e:
                messagebox.showerror(APP_NAME, "Could not read the folder:\n%s" % e)
                return
            self._save_folders()
            self.refresh_list()
            self.status_var.set("Imported %d track%s from %s"
                                % (n, "" if n == 1 else "s", os.path.abspath(d)))
            self._fill_missing()

        def remove_selected(self):
            """Take the selected tracks off the list -- or, inside a playlist,
            out of that playlist. Files on disk are never touched; importing
            the folder again brings removed tracks back."""
            sel = self.selected_tracks()
            if not sel:
                return
            if self.view_mode != "all":
                self.remove_from_playlist(self.view_mode, sel)
                self.status_var.set("Removed %d from %s" % (len(sel), self.view_mode))
                return
            gone = self.lib.remove_tracks(sel)
            self._save_folders()
            self.refresh_list()
            msg = "Removed %d track%s from the list (files untouched)" % (
                len(sel), "" if len(sel) == 1 else "s")
            if gone:
                msg += " -- its folder is out of the library too"
            self.status_var.set(msg)

        def rescan_folders(self):
            for r in list(self.lib.roots):
                try:
                    self.lib.add(r)
                except OSError:
                    pass
            self.refresh_list()
            self._fill_missing()

        def _save_folders(self):
            self.settings["folders"] = self.lib.roots
            self.settings["removed_tracks"] = sorted(self.lib.removed)
            self.settings.pop("folder", None)
            self.save()

        def _fill_missing(self):
            missing = [t for t in self.lib.tracks if t.info is None]
            if missing and find_vgmstream():
                threading.Thread(target=self._fill_lengths, args=(missing,),
                                 daemon=True).start()

        def _fill_lengths(self, tracks):
            for i, t in enumerate(tracks):
                try:
                    self.lib.fill_info(t)
                except Exception:
                    continue
                if i % 10 == 9 or i == len(tracks) - 1:
                    self.root.after(0, self.refresh_list)
                    self.root.after(0, lambda n=i + 1: self.status_var.set(
                        "Reading track lengths… %d/%d" % (n, len(tracks))))
            self.lib.save_cache()
            self.root.after(0, lambda: self.status_var.set(""))

        # ── sorting ──────────────────────────────────────────────────
        def sort_by(self, col):
            """Click a heading: sort by it A-Z / low-high, again for
            Z-A / high-low, a third time to go back to library order."""
            if self.sort_col != col:
                self.sort_col, self.sort_desc = col, False
            elif not self.sort_desc:
                self.sort_desc = True
            else:
                self.sort_col, self.sort_desc = None, False
            self.settings["sort"] = [self.sort_col, self.sort_desc]
            self._sort_headings()
            self.refresh_list()

        def _sort_headings(self):
            for c, label in self._col_labels.items():
                mark = ""
                if c == self.sort_col:
                    mark = "  ▼" if self.sort_desc else "  ▲"
                self.tree.heading(c, text=label + mark)

        def _sorted(self, items):
            """items: (index, track, name). Numbers sort as numbers, text
            without regard to case; anything without a value (a track not
            yet measured, a file with no number) stays at the bottom both
            ways."""
            col = self.sort_col
            if not col:
                return items
            if col == "num":
                key = lambda it: it[1].number
            elif col == "length":
                key = lambda it: it[1].length_seconds()
            elif col == "name":
                key = lambda it: it[2].casefold()
            elif col == "fav":
                # Favourites first, each group A-Z by name.
                key = lambda it: (0 if self.lib.is_fav(it[1]) else 1, it[2].casefold())
            elif col == "expansion":
                key = lambda it: self.lib.expansion_of(it[1]).casefold() or None
            elif col == "composer":
                key = lambda it: self.lib.composer_of(it[1]).casefold() or None
            elif col == "path":
                key = lambda it: it[1].path.casefold()
            else:
                key = lambda it: os.path.basename(it[1].path).casefold()
            have = [it for it in items if key(it) is not None]
            none = [it for it in items if key(it) is None]
            have.sort(key=key, reverse=self.sort_desc)
            return have + none

        def refresh_list(self):
            q = self.search_var.get().strip().lower()
            sel = set(self.tree.selection())
            self.tree.delete(*self.tree.get_children())
            self.visible = []
            items = []
            for i, t in self._view_tracks():
                name = self.lib.name_of(t)
                if q and q not in name.lower() and q not in t.rel.lower() \
                        and q not in self.lib.expansion_of(t).lower() \
                        and q not in self.lib.composer_of(t).lower():
                    continue
                items.append((i, t, name))
            for i, t, name in self._sorted(items):
                tags = ["odd" if len(self.visible) % 2 else "even"]
                if t is self.current:
                    tags.append("playing")
                    name = "♪  " + name
                self.visible.append(t)
                iid = str(i)
                self.tree.insert("", "end", iid=iid,
                                 values=("♥" if self.lib.is_fav(t) else "♡",
                                         t.number if t.number is not None else "",
                                         name, fmt_time(t.length_seconds()),
                                         "  " + self.lib.expansion_of(t),
                                         "  " + self.lib.composer_of(t),
                                         "  " + os.path.basename(t.path),
                                         "  " + os.path.dirname(t.path)),
                                 tags=tags)
                if iid in sel:
                    self.tree.selection_add(iid)

        def _draw_list_box(self):
            """The rounded red outline around the track list."""
            cv = self.list_canvas
            c = self.colors
            w, h = cv.winfo_width(), cv.winfo_height()
            if w < 20 or h < 20:
                return
            r, inset = 10, 4
            cv.configure(background=c["panel"])
            cv.delete("outline")
            if HAVE_PIL:
                self._list_img = ImageTk.PhotoImage(
                    render_card(w, h, r, c["field"], c["accent"]), master=cv)
                cv.create_image(0, 0, anchor="nw", image=self._list_img, tags=("outline",))
            else:
                pts = [r, 0, w - r, 0, w - 1, 0, w - 1, r, w - 1, h - r, w - 1, h - 1,
                       w - r, h - 1, r, h - 1, 0, h - 1, 0, h - r, 0, r, 0, 0]
                cv.create_polygon(pts, smooth=True, fill=c["field"], outline=c["accent"],
                                  tags=("outline",))
            cv.tag_lower("outline")
            cv.coords(self._list_win, inset, inset)
            cv.itemconfigure(self._list_win, width=w - 2 * inset, height=h - 2 * inset)

        def _tree_cursor(self, e):
            """A resize cursor over the column dividers, so you can see
            where to grab."""
            sep = self.tree.identify_region(e.x, e.y) == "separator"
            cur = ("sb_h_double_arrow")
            self.tree.configure(cursor=cur if sep else "")

        def _tag_colors(self):
            c = self.colors
            bold = ("Segoe UI" if sys.platform == "win32" else "TkDefaultFont", 10, "bold")
            self.tree.tag_configure("even", background=c["field"])
            self.tree.tag_configure("odd", background=c["stripe"])
            self.tree.tag_configure("playing", foreground=c["accent"], font=bold)

        def selected_tracks(self):
            return [self.lib.tracks[int(i)] for i in self.tree.selection()]

        def on_right_click(self, e):
            row = self.tree.identify_row(e.y)
            if row and row not in self.tree.selection():
                self.tree.selection_set(row)
            if not row:
                return
            sel = self.selected_tracks()
            favs = all(self.lib.is_fav(t) for t in sel)
            add = [("cmd", n, lambda n_=n: self.add_to_playlist(n_, sel))
                   for n in self.playlists]
            if self.playlists:
                add.append(("sep",))
            add.append(("cmd", "New playlist…", lambda: self.new_playlist(sel)))
            spec = [("cmd", "Play", self.play_selected),
                    ("cmd", "Remove from favourites" if favs else "Add to favourites  ♥",
                     lambda: self.set_fav(sel, not favs)),
                    ("cmd", "Track info…  (F2)", self.track_info),
                    ("sep",),
                    ("sub", "Add to playlist", add),
                    ("sep",),
                    ("cmd", "Export…", self.export_selected),
                    ("cmd", ("Remove from this playlist" if self.view_mode != "all"
                             else "Remove from list") + "  (Del)", self.remove_selected)]
            self.popup.show(spec, e.x_root, e.y_root)
            return "break"

        # ── track info ───────────────────────────────────────────────
        def track_info(self):
            tracks = self.selected_tracks()
            if not tracks:
                return
            for t in tracks:
                # Older cached info has no format details; fetch them.
                if t.info is None or "encoding" not in t.info:
                    try:
                        t.info = None
                        t.folder._cache.pop(t.rel, None)
                        self.lib.fill_info(t)
                    except Exception:
                        pass
            used = sorted({self.lib.expansion_of(t) for t in self.lib.tracks} - {""})
            values = list(EXPANSIONS) + [u for u in used if u not in EXPANSIONS]
            res = TrackInfoDialog(self, tracks, values).result
            if res is None:
                return
            name, exp, comp = res
            if len(tracks) == 1 and name is not None:
                self.lib.rename(tracks[0], name)
            for key, val in (("expansion", exp), ("composer", comp)):
                if val is None:
                    continue
                for t in tracks:
                    v = val.strip()
                    # Matching the catalogue's own value: store nothing, so
                    # a corrected catalogue still shows through later.
                    cat = t.cat and t.cat[0 if key == "expansion" else 2]
                    self.lib.set_meta(t, key, "" if v == cat else v, save=False)
                for f in {t.folder for t in tracks}:
                    f.save_names()
            self.lib.save_cache()
            self.refresh_list()
            if self.current in tracks:
                self.show_now()

        def set_fav(self, tracks, on):
            for t in tracks:
                self.lib.set_meta(t, "fav", True if on else None, save=False)
            for f in {t.folder for t in tracks}:
                f.save_names()
            self.refresh_list()

        def _tree_click(self, e):
            """A click in the heart column toggles that track's favourite."""
            if self.tree.identify_region(e.x, e.y) != "cell":
                return
            row = self.tree.identify_row(e.y)
            col = self.tree.identify_column(e.x)          # "#n" of the DISPLAYED columns
            shown = self._shown_columns()
            try:
                cid = shown[int(col[1:]) - 1]
            except (ValueError, IndexError):
                return
            if cid == "fav" and row:
                t = self.lib.tracks[int(row)]
                self.set_fav([t], not self.lib.is_fav(t))

        # ── columns ──────────────────────────────────────────────────
        ALL_COLS = ("fav", "num", "name", "length", "expansion", "composer", "file", "path")
        COL_NAMES = {"fav": "Favourite ♥", "num": "#", "name": "Name", "length": "Length",
                     "expansion": "Expansion", "composer": "Composer", "file": "File",
                     "path": "File path"}

        def _col_order(self):
            order = [c for c in self.settings.get("col_order", []) if c in self.ALL_COLS]
            return order + [c for c in self.ALL_COLS if c not in order]

        def _shown_columns(self):
            hidden = set(self.settings.get("hidden_cols", ["path"]))
            hidden.discard("name")                       # the one that can't go
            return [c for c in self._col_order() if c not in hidden]

        # Drag a heading onto another to move that column there. A plain
        # click (no drag) still sorts; a press on a divider still resizes.
        def _heading_col(self, x):
            shown = self._shown_columns()
            try:
                return shown[int(self.tree.identify_column(x)[1:]) - 1]
            except (ValueError, IndexError):
                return None

        def _col_press(self, e):
            self._drag_col = None
            self._row_anchor = None
            region = self.tree.identify_region(e.x, e.y)
            if region == "heading":
                self._drag_col = (self._heading_col(e.x), e.x, False)
            elif region in ("cell", "tree") and not (e.state & 0x0005):
                # Plain press on a row: dragging from here selects a run of
                # rows (Ctrl/Shift+click keep their usual meaning).
                self._row_anchor = self.tree.identify_row(e.y)

        def _col_motion(self, e):
            a = getattr(self, "_row_anchor", None)
            if a:
                row = self.tree.identify_row(e.y)
                kids = self.tree.get_children()
                if row and row in kids and a in kids:
                    i, j = sorted((kids.index(a), kids.index(row)))
                    self.tree.selection_set(kids[i:j + 1])
                return
            d = self._drag_col
            if d and not d[2] and abs(e.x - d[1]) > 8:
                self._drag_col = (d[0], d[1], True)
                self.tree.configure(cursor="fleur")

        def _col_release(self, e):
            d, self._drag_col = self._drag_col, None
            if not d or not d[2]:
                return
            self.tree.configure(cursor="")
            src, dst = d[0], self._heading_col(e.x)
            if not src or not dst or src == dst:
                return
            order = self._col_order()
            order.remove(src)
            order.insert(order.index(dst) + (1 if e.x > d[1] else 0), src)
            self.settings["col_order"] = order
            self._apply_hidden_columns()
            self.save()

        def _apply_hidden_columns(self):
            self.tree.configure(displaycolumns=self._shown_columns())

        def toggle_column(self, col):
            hidden = set(self.settings.get("hidden_cols", ["path"]))
            hidden.symmetric_difference_update({col})
            self.settings["hidden_cols"] = sorted(hidden)
            self._apply_hidden_columns()
            self.save()

        # ── playlists & views ────────────────────────────────────────
        def set_view(self, key):
            """Show all tracks ("all") or one playlist. The title strip says
            which, so there is no extra row for it."""
            self.view_mode = key if (key == "all" or key in self.playlists) else "all"
            self.title_lbl.configure(text=APP_NAME if self.view_mode == "all"
                                     else "%s  ·  %s" % (APP_NAME, self.view_mode))
            self.refresh_list()

        def new_playlist(self, tracks):
            name = AskDialog(self, "New playlist", "Playlist name", "").result
            name = (name or "").strip()
            if not name:
                return
            if name == "all" or name in self.playlists:
                messagebox.showerror(APP_NAME, "There's already a playlist called %s." % name)
                return
            self.playlists[name] = []
            self.add_to_playlist(name, tracks)
            self.set_view(name)

        def add_to_playlist(self, name, tracks):
            pl = self.playlists.setdefault(name, [])
            have = {os.path.normcase(p) for p in pl}
            for t in tracks:
                if os.path.normcase(t.path) not in have:
                    pl.append(t.path)
            save_playlists(self.playlists)
            if tracks:
                self.status_var.set("Added %d to %s" % (len(tracks), name))
            if self.view_mode == name:
                self.refresh_list()

        def remove_from_playlist(self, name, tracks):
            gone = {os.path.normcase(t.path) for t in tracks}
            self.playlists[name] = [p for p in self.playlists.get(name, [])
                                    if os.path.normcase(p) not in gone]
            save_playlists(self.playlists)
            self.refresh_list()

        def rename_playlist(self, name):
            new = (AskDialog(self, "Rename playlist", "New name", name).result or "").strip()
            if not new or new == name or new in self.playlists or new == "all":
                return
            self.playlists = {(new if k == name else k): v for k, v in self.playlists.items()}
            save_playlists(self.playlists)
            if self.view_mode == name:
                self.set_view(new)

        def delete_playlist(self, name):
            if not messagebox.askyesno(APP_NAME, "Delete the playlist %s? (The music "
                                       "itself is not touched.)" % name):
                return
            self.playlists.pop(name, None)
            save_playlists(self.playlists)
            if self.view_mode == name:
                self.set_view("all")

        def _view_tracks(self):
            """(index, track) pairs for the current view, in its own order."""
            if self.view_mode == "all":
                return list(enumerate(self.lib.tracks))
            idx = {id(t): i for i, t in enumerate(self.lib.tracks)}
            out = []
            for p in self.playlists.get(self.view_mode, []):
                t = self.lib.track_by_path(p)
                if t is not None:
                    out.append((idx[id(t)], t))
            return out

        # ── playback ─────────────────────────────────────────────────
        def play_selected(self):
            tracks = self.selected_tracks()
            if tracks:
                self.play_track(tracks[0])

        def play_track(self, t, remember=True):
            if self._loading or self._downloading:
                return
            if not find_vgmstream():
                self.offer_vgmstream()
                return
            if remember and self.current is not None and self.current is not t:
                self.history.append(self.current)
                del self.history[:-200]
            self._loading = True
            self.status_var.set("Loading %s…" % self.lib.name_of(t))

            def work():
                try:
                    info = self.lib.fill_info(t)
                    self.engine.load(t, info)
                    err = None
                except Exception as e:
                    err = str(e)
                self.root.after(0, lambda: self._loaded(t, err))

            threading.Thread(target=work, daemon=True).start()

        def _loaded(self, t, err):
            self._loading = False
            if err:
                self.status_var.set("")
                messagebox.showerror(APP_NAME, "Could not play %s:\n%s" % (t.rel, err))
                return
            self.status_var.set("")
            self.current = t
            self.engine.play(0)
            self.view.set_playing(True)
            self.show_now()
            self.refresh_list()
            iid = str(self.lib.tracks.index(t))
            if self.tree.exists(iid):
                self.tree.see(iid)

        def show_now(self):
            t = self.current
            if t is None:
                self.view.set_track("Nothing playing", "")
                return
            parts = [os.path.basename(t.path)]
            if self.engine.has_loop():
                parts.append("loops from %s" % fmt_time(self.engine.loop_start / self.engine.rate))
            else:
                parts.append("plays once")
            self.view.set_track(self.lib.name_of(t), "   ·   ".join(parts))

        def toggle_play(self):
            e = self.engine
            if not e.playing:
                if self.current is not None and e.pcm:
                    e.play(0)
                    self.view.set_playing(True)
                else:
                    self.play_selected()
                return
            if e.is_paused():
                e.resume()
                self.view.set_playing(True)
            else:
                e.pause()
                self.view.set_playing(False)

        def on_space(self, e):
            if isinstance(e.widget, (tk.Entry, ttk.Entry)):
                return
            self.toggle_play()
            return "break"

        def stop(self):
            self.engine.stop()
            self.view.set_playing(False)

        def _neighbour(self, step):
            pool = self.visible or self.lib.tracks
            if not pool:
                return None
            if self.shuffle_on and len(pool) > 1:
                choices = [t for t in pool if t is not self.current]
                return random.choice(choices)
            if self.current in pool:
                i = (pool.index(self.current) + step) % len(pool)
            else:
                i = 0
            return pool[i]

        def next_track(self):
            t = self._neighbour(+1)
            if t is not None:
                self.play_track(t)

        def prev_track(self):
            # Early in a track: go back a track. Later: restart this one.
            if self.engine.playing and self.engine.position() > 3 * self.engine.rate:
                self.engine.play(0)
                return
            if self.shuffle_on and self.history:
                self.play_track(self.history.pop(), remember=False)
                return
            t = self._neighbour(-1)
            if t is not None:
                self.play_track(t)

        # ── the drawn panel's buttons ────────────────────────────────
        def view_action(self, name):
            if name == "play":
                self.toggle_play()
            elif name == "prev":
                self.prev_track()
            elif name == "next":
                self.next_track()
            elif name == "repeat":
                self.repeat_on = not self.repeat_on
                self.engine.set_looping(self.repeat_on)
                self.status_var.set("Repeat: loop forever, as in game" if self.repeat_on
                                    else "Repeat off: each track plays once, then the next")
                self.save()
                self.view.redraw()
            elif name == "shuffle":
                self.shuffle_on = not self.shuffle_on
                self.status_var.set("Shuffle on" if self.shuffle_on else "Shuffle off")
                self.save()
                self.view.redraw()
            elif name == "mini":
                self.toggle_mini()

        def set_volume(self, v):
            self.engine.set_volume(v)
            self.settings["volume"] = round(v, 3)

        def seek_to(self, frac):
            e = self.engine
            if e.pcm:
                e.play(frac * e.end_frame())
                self.view.set_playing(not e.is_paused())

        # ── mini player ──────────────────────────────────────────────
        def toggle_mini(self):
            """Fold down to just the player panel (on top of other windows),
            or back out to the full player. Each size remembers itself."""
            r = self.root
            if self._maxed:
                self.toggle_max()
            if not self.mini:
                # Just the rounded now-playing panel: no title strip, no
                # status line, no outline -- and the corners outside the
                # panel's curve see-through.
                self.settings["geometry"] = r.geometry()
                if self._top is not None:
                    self._top.pack_forget()
                self._mid.pack_forget()
                self._bar.pack_forget()
                self._grip_lbl.place_forget()
                self.body.pack_configure(padx=0, pady=0)
                self._bot.configure(padding=0)
                self.mini = self.view.mini = True
                self.view.configure(height=168)   # the mini layout is shorter
                r.configure(background=MINI_KEY)
                if sys.platform == "win32":
                    try:
                        r.attributes("-transparentcolor", MINI_KEY)
                    except tk.TclError:
                        pass
                r.minsize(380, 168)
                g = self.settings.get("mini_geometry") or ""
                pos = g[g.find("+"):] if "+" in g else ""
                w = g.split("x")[0] if "x" in g else "460"
                self._set_geometry("%sx%d%s" % (w, 168, pos))
                r.attributes("-topmost", True)
            else:
                self.settings["mini_geometry"] = r.geometry()
                self.mini = self.view.mini = False
                if sys.platform == "win32":
                    try:
                        r.attributes("-transparentcolor", "")
                    except tk.TclError:
                        pass
                r.configure(background=self.colors["dim"])
                self.body.pack_configure(padx=1, pady=1)
                self._bot.configure(padding=(4, 0, 4, 2))
                self.view.configure(height=196)
                self._bar.pack(fill="x", before=self._bot)
                self._grip_lbl.place(relx=1.0, rely=1.0, x=-6, y=-6, anchor="se")
                self._grip_lbl.lift()
                if self._top is not None:
                    self._top.pack(fill="x", after=self._bar)
                self._mid.pack(fill="both", expand=True)   # last: gives way first
                r.attributes("-topmost", False)
                r.minsize(520, 320)
                self._set_geometry(self.settings.get("geometry", "820x600"))
            self.settings["mini"] = self.mini
            save_settings(self.settings)
            self.view.redraw()
            self._dwm_round = None
            self._rgn_size = None
            self._round_corners()

        def tick(self):
            e = self.engine
            if sys.platform == "win32":
                self._check_snapped()        # Windows' snap-maximise -> ours
                self._hook_frame()           # cheap; re-hooks a rebuilt window
                self._round_corners()        # likewise
            try:
                e.tick()
                if e.finished():
                    if not e.looping:
                        self.next_track()
                    else:
                        # A track the game plays once (it has no loop) ends
                        # here too, just as it does in game.
                        self.stop()
                if e.pcm:
                    end = float(e.end_frame())
                    pos = e.position() if e.playing else 0
                    tail = "  ∞" if (e.looping and e.has_loop()) else ""
                    self.view.set_progress(
                        pos / end if end else 0.0,
                        "%s / %s%s" % (fmt_time(pos / float(e.rate)),
                                       fmt_time(end / e.rate), tail))
            finally:
                self.root.after(200, self.tick)

        def scope_tick(self):
            """~25 times a second: move the live line to where the music is."""
            e = self.engine
            try:
                if e.playing and not e.is_paused() and e.pcm:
                    pts = scope_points(e.pcm, e.position(), e.channels)
                    self.view.scope = pts
                    self.view.set_scope(pts)
            except Exception:
                pass
            finally:
                self.root.after(40, self.scope_tick)

        # ── export ───────────────────────────────────────────────────
        def export_selected(self):
            tracks = self.selected_tracks()
            if not tracks:
                messagebox.showinfo(APP_NAME, "Select one or more tracks to export.")
                return
            ExportDialog(self, tracks)

        def save(self):
            self.settings["repeat"] = LOOP_FOREVER if self.repeat_on else PLAY_ONCE
            self.settings["shuffle"] = bool(self.shuffle_on)
            self.settings["volume"] = round(self.engine.volume, 3)
            save_settings(self.settings)

        def on_close(self):
            try:
                if self.mini:
                    self.settings["mini_geometry"] = self.root.geometry()
                else:
                    self.settings["geometry"] = self._maxed or self.root.geometry()
                self.settings["folders"] = self.lib.roots
                self.settings["removed_tracks"] = sorted(self.lib.removed)
                self.settings.pop("folder", None)
                self.settings["columns"] = {
                    c: self.tree.column(c, "width") for c in self.ALL_COLS}
                self.save()
                self.lib.save_cache()
                self.engine.stop()
            finally:
                self.root.destroy()

    class InMenu:
        """A pop-up menu drawn INSIDE the player's own window.

        Native Tk menus are separate windows with a keyboard/mouse grab: if
        you switch virtual desktop or app while one is open, it can be left
        behind on the other desktop with the grab still held, and the player
        appears frozen. These are ordinary frames placed over the player, so
        they always go where the player goes and never hold a grab; a click
        anywhere outside, Esc, or picking an item closes them.

        spec items: ("cmd", label, fn) · ("check", label, on, fn) ·
        ("radio", label, on, fn) · ("sub", label, [spec]) ·
        ("sep",) · ("note", label)  (greyed, not clickable)
        """

        def __init__(self, app):
            self.app = app
            self.frames = []          # open levels, top-level first
            self.opened_at = 0.0

        def is_open(self):
            return bool(self.frames)

        def show(self, spec, x_root, y_root):
            self.close()
            self.opened_at = time.time()
            self._open_level(spec, x_root, y_root, 0)
            root = self.app.root
            root.bind_all("<ButtonPress-1>", self._outside, add="+")
            root.bind_all("<ButtonPress-3>", self._outside, add="+")
            root.bind_all("<Escape>", lambda e: self.close(), add="+")

        def close(self):
            for f in self.frames:
                try:
                    f.destroy()
                except tk.TclError:
                    pass
            if self.frames:
                root = self.app.root
                for seq in ("<ButtonPress-1>", "<ButtonPress-3>", "<Escape>"):
                    root.unbind_all(seq)
            self.frames = []

        def _inside(self, widget):
            w = widget
            while w is not None:
                if w in self.frames:
                    return True
                w = getattr(w, "master", None)
            return False

        def _outside(self, e):
            # The click that opened the menu reaches these handlers too.
            if time.time() - self.opened_at < 0.15:
                return
            if self.frames and not self._inside(e.widget):
                self.close()

        def _open_level(self, spec, x_root, y_root, depth):
            c = self.app.colors
            root = self.app.root
            del self.frames[depth:]
            f = tk.Frame(root, background=c["field"], highlightthickness=1,
                         highlightbackground=c["accent"], bd=0)
            font = ("Segoe UI" if sys.platform == "win32" else "TkDefaultFont", 10)
            for item in spec:
                kind = item[0]
                if kind == "sep":
                    tk.Frame(f, height=1, background=c["border"]).pack(
                        fill="x", padx=6, pady=3)
                    continue
                label = item[1]
                mark = ""
                if kind in ("check", "radio"):
                    mark = ("✓  " if kind == "check" else "●  ") if item[2] else "    "
                text = mark + label + ("   ›" if kind == "sub" else "")
                row = tk.Label(f, text=text, anchor="w", font=font, padx=12, pady=3,
                               background=c["field"],
                               foreground=c["dim"] if kind == "note" else c["fg"])
                row.pack(fill="x")
                if kind == "note":
                    continue
                row.bind("<Enter>", lambda e, r=row, it=item, d=depth: self._hover(r, it, d))
                row.bind("<Leave>", lambda e, r=row: r.configure(
                    background=c["field"], foreground=c["fg"]))
                if kind != "sub":
                    row.bind("<ButtonRelease-1>", lambda e, it=item: self._pick(it))
                else:
                    row.bind("<ButtonRelease-1>", lambda e, r=row, it=item, d=depth:
                             self._open_sub(r, it, d))
            f.update_idletasks()
            w, h = f.winfo_reqwidth(), f.winfo_reqheight()
            rx, ry = x_root - root.winfo_rootx(), y_root - root.winfo_rooty()
            W, H = root.winfo_width(), root.winfo_height()
            # Keep it inside the window: flip left / up when it would spill.
            if rx + w > W - 2:
                rx = max(2, (rx - w) if depth else (W - w - 2))
            if ry + h > H - 2:
                ry = max(2, H - h - 2)
            f.place(x=rx, y=ry)
            f.lift()
            self.frames.append(f)

        def _hover(self, row, item, depth):
            c = self.app.colors
            row.configure(background=c["accent"], foreground=c["sel_fg"])
            if item[0] == "sub":
                self._open_sub(row, item, depth)
            elif len(self.frames) > depth + 1:
                for f in self.frames[depth + 1:]:
                    f.destroy()
                del self.frames[depth + 1:]

        def _open_sub(self, row, item, depth):
            if len(self.frames) > depth + 1 and getattr(self, "_sub_of", None) is row:
                return
            for f in self.frames[depth + 1:]:
                f.destroy()
            del self.frames[depth + 1:]
            self._sub_of = row
            self._open_level(item[2], row.winfo_rootx() + row.winfo_width() - 2,
                             row.winfo_rooty() - 2, depth + 1)

        def _pick(self, item):
            fn = item[3] if item[0] in ("check", "radio") else item[2]
            self.close()
            self.app.root.after_idle(fn)

    class AboutDialog:
        """About OmniPlayer: a short how-to, the author, and the note that no
        music comes with the app."""

        HOW_TO = (
            "Import a music folder from the settings menu (click the icon at the "
            "top left) -- your FINAL FANTASY XI folder, or any folder of .bgw "
            "files. Import more folders to add them to the same list.\n\n"
            "Double-click a track to play it. It loops the way the game loops it; "
            "the repeat button switches to playing each track once, then the next.\n\n"
            "Click the heart to favourite a track. Click a column heading to sort, "
            "drag one to move it. Right-click a track for its info (name, "
            "expansion, composer), playlists, export to MP3 / FLAC / WAV, and "
            "removing it from the list.\n\n"
            "The square button at the bottom right of the player switches to the "
            "mini player and back.")
        DISCLAIMER = (
            "No music is included with or distributed by OmniPlayer. It plays and "
            "converts the .bgw files from your own installation of FINAL FANTASY "
            "XI. The music of FINAL FANTASY XI is © SQUARE ENIX CO., LTD.; "
            "OmniPlayer is a fan-made tool and is not affiliated with or endorsed "
            "by Square Enix.")
        CREDITS = ("Uses vgmstream (decoding), FLAC by Xiph.Org and LAME via lameenc "
                   "(export), pygame-ce (playback) and Pillow.")

        def __init__(self, app):
            c = app.colors
            w = self.win = tk.Toplevel(app.root)
            w.withdraw()
            w.overrideredirect(True)
            w.transient(app.root)
            w.configure(background=c["accent"])
            f = ttk.Frame(w, padding=(18, 12, 18, 14))
            f.pack(fill="both", expand=True, padx=1, pady=1)
            hdr = ttk.Frame(f)
            hdr.pack(fill="x")
            try:
                img = tk.PhotoImage(data=APP_ICON_PNG, master=w)
                self._img = img.subsample(2, 2)
                ttk.Label(hdr, image=self._img).pack(side="left", padx=(0, 10))
            except Exception:
                pass
            ttl = ttk.Frame(hdr)
            ttl.pack(side="left", fill="x")
            ttk.Label(ttl, text=APP_NAME, style="CardTitle.TLabel",
                      background=c["panel"]).pack(anchor="w")
            ttk.Label(ttl, text="Version %s   ·   by BalladOfWorms" % APP_VERSION,
                      style="Dim.TLabel").pack(anchor="w")
            wrap = 460
            for head, body in (("How to use", self.HOW_TO),
                               ("Please note", self.DISCLAIMER),
                               ("Credits", self.CREDITS)):
                ttk.Label(f, text=head, style="Now.TLabel").pack(anchor="w", pady=(12, 2))
                ttk.Label(f, text=body, wraplength=wrap, justify="left").pack(anchor="w")
            ttk.Button(f, text="Close", style="Round.TButton",
                       command=w.destroy).pack(anchor="e", pady=(14, 0))
            self._drag = None
            for wd in (hdr, ttl):
                wd.bind("<ButtonPress-1>", lambda e: setattr(
                    self, "_drag", (e.x_root - w.winfo_x(), e.y_root - w.winfo_y())))
                wd.bind("<B1-Motion>", lambda e: self._drag and w.geometry(
                    "+%d+%d" % (e.x_root - self._drag[0], e.y_root - self._drag[1])))
            w.bind("<Escape>", lambda e: w.destroy())
            w.update_idletasks()
            r = app.root
            x = r.winfo_rootx() + (r.winfo_width() - w.winfo_reqwidth()) // 2
            y = r.winfo_rooty() + max(0, (r.winfo_height() - w.winfo_reqheight()) // 3)
            w.geometry("+%d+%d" % (max(0, x), max(0, y)))
            w.deiconify()
            w.lift()
            w.focus_force()

    class AskDialog:
        """A small borderless prompt in the player's own colours: a text box,
        or a drop-down you can also type into when `values` is given.
        .result is the text, or None if cancelled."""

        def __init__(self, app, title, prompt, initial="", values=None):
            self.result = None
            c = app.colors
            w = self.win = tk.Toplevel(app.root)
            w.withdraw()
            w.overrideredirect(True)
            w.transient(app.root)
            w.configure(background=c["dim"])
            f = ttk.Frame(w, padding=(14, 10, 14, 12))
            f.pack(fill="both", expand=True, padx=1, pady=1)
            hdr = ttk.Label(f, text=title, style="Now.TLabel")
            hdr.pack(anchor="w")
            ttk.Label(f, text=prompt, style="Dim.TLabel").pack(anchor="w", pady=(2, 6))
            self.var = tk.StringVar(value=initial)
            if values:
                box = ttk.Combobox(f, textvariable=self.var, values=list(values), width=38)
            else:
                box = ttk.Entry(f, textvariable=self.var, width=40, style="Round.TEntry")
            box.pack(fill="x")
            bf = ttk.Frame(f)
            bf.pack(anchor="e", pady=(10, 0))
            ttk.Button(bf, text="OK", style="Round.TButton", command=self.ok).pack(side="left")
            ttk.Button(bf, text="Cancel", style="Round.TButton",
                       command=w.destroy).pack(side="left", padx=(6, 0))
            self._drag = None
            hdr.bind("<ButtonPress-1>", lambda e: setattr(
                self, "_drag", (e.x_root - w.winfo_x(), e.y_root - w.winfo_y())))
            hdr.bind("<B1-Motion>", lambda e: self._drag and w.geometry(
                "+%d+%d" % (e.x_root - self._drag[0], e.y_root - self._drag[1])))
            w.bind("<Return>", lambda e: self.ok())
            w.bind("<Escape>", lambda e: w.destroy())
            w.update_idletasks()
            r = app.root
            x = r.winfo_rootx() + (r.winfo_width() - w.winfo_reqwidth()) // 2
            y = r.winfo_rooty() + (r.winfo_height() - w.winfo_reqheight()) // 3
            w.geometry("+%d+%d" % (max(0, x), max(0, y)))
            w.deiconify()
            w.lift()
            w.focus_force()
            box.focus_set()
            try:
                box.select_range(0, "end")
            except Exception:
                pass
            try:
                w.grab_set()
            except tk.TclError:
                pass
            w.wait_window()

        def ok(self):
            self.result = self.var.get()
            self.win.destroy()

    def describe_format(info):
        """"PlayStation 4-bit ADPCM · 44.1 kHz stereo · 358 kbps · loops
        0:10 - 2:50" from a track's info."""
        if not info:
            return "?"
        bits = []
        if info.get("encoding"):
            # "PlayStation 4-bit ADPCM (configurable)" -> without the aside
            bits.append(re.sub(r"\s*\(.*?\)", "", info["encoding"]))
        ch = info.get("channels") or 0
        bits.append("%.1f kHz %s" % ((info.get("rate") or 0) / 1000.0,
                                     {1: "mono", 2: "stereo"}.get(ch, "%d ch" % ch)))
        if info.get("bitrate"):
            bits.append("%d kbps" % round(info["bitrate"] / 1000.0))
        if info.get("loop_start") is not None and info.get("rate"):
            r = float(info["rate"])
            bits.append("loops %s – %s" % (fmt_time(info["loop_start"] / r),
                                            fmt_time(info["loop_end"] / r)))
        else:
            bits.append("plays once")
        return "  ·  ".join(bits)

    class TrackInfoDialog:
        """Track info: name and expansion to edit; file name, path, length
        and format to read. With several tracks selected, the expansion is
        set on all of them (the name is per track, so it's left alone).
        .result is (name or None, expansion or None), or None if cancelled."""

        def __init__(self, app, tracks, exp_values):
            self.result = None
            c = app.colors
            lib = app.lib
            one = len(tracks) == 1
            t0 = tracks[0]
            w = self.win = tk.Toplevel(app.root)
            w.withdraw()
            w.overrideredirect(True)
            w.transient(app.root)
            w.configure(background=c["dim"])
            f = ttk.Frame(w, padding=(14, 10, 14, 12))
            f.pack(fill="both", expand=True, padx=1, pady=1)
            f.columnconfigure(1, weight=1)
            hdr = ttk.Label(f, text="Track info" if one else
                            "Track info  ·  %d tracks" % len(tracks), style="Now.TLabel")
            hdr.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

            self.name_var = tk.StringVar(value=lib.name_of(t0) if one else "")
            exps = {lib.expansion_of(t) for t in tracks}
            self.exp_var = tk.StringVar(value=exps.pop() if len(exps) == 1 else "")
            self._exp_start = self.exp_var.get()
            comps = {lib.composer_of(t) for t in tracks}
            self.comp_var = tk.StringVar(value=comps.pop() if len(comps) == 1 else "")
            self._comp_start = self.comp_var.get()

            def row(r, label, widget):
                ttk.Label(f, text=label, style="Dim.TLabel").grid(
                    row=r, column=0, sticky="w", padx=(0, 14), pady=2)
                widget.grid(row=r, column=1, sticky="we", pady=2)

            name_e = ttk.Entry(f, textvariable=self.name_var, width=46, style="Round.TEntry")
            if not one:
                name_e.state(["disabled"])
                self.name_var.set("(each track keeps its own)")
            row(1, "Name", name_e)
            exp_c = ttk.Combobox(f, textvariable=self.exp_var, values=list(exp_values), width=44)
            row(2, "Expansion", exp_c)
            comp_e = ttk.Entry(f, textvariable=self.comp_var, width=46, style="Round.TEntry")
            row(3, "Composer", comp_e)
            if not one and (len({lib.expansion_of(t) for t in tracks}) > 1
                            or len({lib.composer_of(t) for t in tracks}) > 1):
                ttk.Label(f, text="(blank ones differ -- typing sets it on all)",
                          style="Dim.TLabel").grid(row=4, column=1, sticky="w")
            if one:
                info = t0.info
                known = ("Catalogue", t0.cat[4] if t0.cat and len(t0.cat) > 4
                         else "not recognised")
                facts = ((("Heard in", lib.heard_in(t0)),) if lib.heard_in(t0) else ()) + (
                         known,
                         ("File name", os.path.basename(t0.path)),
                         ("Path", os.path.dirname(t0.path)),
                         ("Length", fmt_time(t0.length_seconds()) or "?"),
                         ("Format", describe_format(info)))
            else:
                total = sum(t.length_seconds() or 0 for t in tracks)
                facts = (("Files", "%d selected" % len(tracks)),
                         ("Length", "%s in total" % fmt_time(total)))
            for i, (k, v) in enumerate(facts, start=5):
                lab = ttk.Label(f, text=v, wraplength=420)
                row(i, k, lab)
            bf = ttk.Frame(f)
            bf.grid(row=12, column=0, columnspan=2, sticky="e", pady=(10, 0))
            ttk.Button(bf, text="Save", style="Round.TButton", command=self.ok).pack(side="left")
            ttk.Button(bf, text="Cancel", style="Round.TButton",
                       command=w.destroy).pack(side="left", padx=(6, 0))
            self._one = one
            self._drag = None
            hdr.bind("<ButtonPress-1>", lambda e: setattr(
                self, "_drag", (e.x_root - w.winfo_x(), e.y_root - w.winfo_y())))
            hdr.bind("<B1-Motion>", lambda e: self._drag and w.geometry(
                "+%d+%d" % (e.x_root - self._drag[0], e.y_root - self._drag[1])))
            w.bind("<Return>", lambda e: self.ok())
            w.bind("<Escape>", lambda e: w.destroy())
            w.update_idletasks()
            r = app.root
            x = r.winfo_rootx() + (r.winfo_width() - w.winfo_reqwidth()) // 2
            y = r.winfo_rooty() + (r.winfo_height() - w.winfo_reqheight()) // 3
            w.geometry("+%d+%d" % (max(0, x), max(0, y)))
            w.deiconify()
            w.lift()
            w.focus_force()
            (name_e if one else exp_c).focus_set()
            try:
                w.grab_set()
            except tk.TclError:
                pass
            w.wait_window()

        def ok(self):
            name = self.name_var.get() if self._one else None
            exp, comp = self.exp_var.get(), self.comp_var.get()
            if exp == self._exp_start:
                exp = None            # untouched: leave each track's own
            if comp == self._comp_start:
                comp = None
            self.result = (name, exp, comp)
            self.win.destroy()

    class ExportDialog:
        """Borderless export window. Hold Shift and drag anywhere on it to
        move it; Esc or Close shuts it."""

        def __init__(self, app, tracks):
            self.app, self.tracks = app, tracks
            s = app.settings
            c = app.colors
            w = self.win = tk.Toplevel(app.root)
            w.withdraw()
            w.overrideredirect(True)
            w.transient(app.root)
            w.configure(background=c["dim"])
            # A one-pixel border stands in for the frame the window gave up.
            f = ttk.Frame(w, padding=(14, 10, 14, 12))
            f.pack(fill="both", expand=True, padx=1, pady=1)
            f.columnconfigure(1, weight=1)

            title = "Export %d track%s" % (len(tracks), "" if len(tracks) == 1 else "s")
            # (header row below doubles as the drag handle)
            hdr = ttk.Frame(f)
            hdr.grid(row=0, column=0, columnspan=2, sticky="we", pady=(0, 10))
            ttl = ttk.Label(hdr, text=title, style="Now.TLabel")
            ttl.pack(side="left")
            # Drag the header to move the window (Shift+drag works anywhere).
            for wdg in (hdr, ttl):
                wdg.bind("<ButtonPress-1>", self._drag_start)
                wdg.bind("<B1-Motion>", self._drag_move)

            self.fmt = tk.StringVar(value=s.get("exp_fmt", "mp3"))
            ttk.Label(f, text="Format").grid(row=1, column=0, sticky="w")
            fr = ttk.Frame(f)
            fr.grid(row=1, column=1, sticky="w")
            ttk.Radiobutton(fr, text="MP3", value="mp3", variable=self.fmt).pack(side="left")
            ttk.Radiobutton(fr, text="FLAC", value="flac", variable=self.fmt).pack(side="left", padx=8)
            ttk.Radiobutton(fr, text="WAV", value="wav", variable=self.fmt).pack(side="left")
            if not have_mp3():
                ttk.Label(f, text="MP3 support is fetched the first time you use it (about 160 KB).",
                          style="Dim.TLabel").grid(row=2, column=1, sticky="w")

            self.bitrate = tk.IntVar(value=int(s.get("exp_bitrate", 256)))
            self.album = tk.StringVar(value=s.get("exp_album", DEFAULT_ALBUM))
            self.out = tk.StringVar(value=s.get("exp_dir") or os.path.expanduser("~"))

            ttk.Label(f, text="MP3 bitrate (kbps)").grid(row=3, column=0, sticky="w", pady=2)
            ttk.Combobox(f, textvariable=self.bitrate, width=6, values=(128, 192, 256, 320),
                         state="readonly").grid(row=3, column=1, sticky="w", pady=2)
            ttk.Label(f, text="Album tag").grid(row=4, column=0, sticky="w", pady=2)
            ttk.Entry(f, textvariable=self.album, width=30, style="Round.TEntry").grid(row=4, column=1, sticky="w", pady=2)

            ttk.Label(f, text="Save to").grid(row=5, column=0, sticky="w", pady=2, padx=(0, 12))
            of = ttk.Frame(f)
            of.grid(row=5, column=1, sticky="we")
            ttk.Entry(of, textvariable=self.out, width=30, style="Round.TEntry").pack(side="left")
            ttk.Button(of, text="…", width=3, style="Round.TButton",
                       command=self.pick_dir).pack(side="left", padx=4)

            ttk.Label(f, text="Each track is saved as it plays once through, without looping.",
                      style="Dim.TLabel").grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))

            self.prog = tk.StringVar(value="")
            ttk.Label(f, textvariable=self.prog).grid(row=7, column=0, columnspan=2, sticky="w", pady=(6, 0))
            bf = ttk.Frame(f)
            bf.grid(row=8, column=0, columnspan=2, sticky="e", pady=(8, 0))
            self.go_btn = ttk.Button(bf, text="Export", style="Round.TButton",
                                     command=self.go)
            self.go_btn.pack(side="left")
            ttk.Button(bf, text="Close", style="Round.TButton",
                       command=w.destroy).pack(side="left", padx=(6, 0))

            # Shift+drag anywhere moves it. Bound on the window itself, which
            # is in every child's bindtags, so it works over any widget.
            self._drag = None
            w.bind("<Shift-ButtonPress-1>", self._drag_start)
            w.bind("<Shift-B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
            w.bind("<Escape>", lambda e: w.destroy())

            # Centre over the player, then show and take the keyboard.
            w.update_idletasks()
            r = app.root
            x = r.winfo_rootx() + (r.winfo_width() - w.winfo_reqwidth()) // 2
            y = r.winfo_rooty() + (r.winfo_height() - w.winfo_reqheight()) // 3
            w.geometry("+%d+%d" % (max(0, x), max(0, y)))
            w.deiconify()
            w.lift()
            w.focus_force()

        def _drag_start(self, e):
            self._drag = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())
            return "break"

        def _drag_move(self, e):
            if self._drag:
                dx, dy = self._drag
                self.win.geometry("+%d+%d" % (e.x_root - dx, e.y_root - dy))
            return "break"

        def pick_dir(self):
            d = filedialog.askdirectory(parent=self.win, initialdir=self.out.get() or None)
            if d:
                self.out.set(d)

        def go(self):
            out = self.out.get()
            if not os.path.isdir(out):
                messagebox.showerror(APP_NAME, "Pick a folder to save to.", parent=self.win)
                return
            fmt = self.fmt.get()
            if fmt == "mp3" and not have_mp3():
                if not messagebox.askyesno(
                        APP_NAME, "MP3 export needs the LAME encoder, which isn't here "
                        "yet.\n\nDownload it now? (about 160 KB, the lameenc package "
                        "from PyPI)", parent=self.win):
                    return
            if fmt == "flac" and not find_flac():
                if not messagebox.askyesno(
                        APP_NAME, "FLAC export needs the FLAC encoder, which isn't here "
                        "yet.\n\nDownload it now? (about 1.3 MB, Xiph's official "
                        "Windows build from GitHub)", parent=self.win):
                    return
            s = self.app.settings
            s.update(exp_fmt=fmt, exp_bitrate=int(self.bitrate.get()),
                     exp_album=self.album.get(), exp_dir=out)
            save_settings(s)
            self.go_btn.state(["disabled"])
            args = (fmt, int(self.bitrate.get()), self.album.get(), out)
            threading.Thread(target=self.work, args=args, daemon=True).start()

        def _say(self, text):
            self.app.root.after(0, lambda: self.prog.set(text))

        def work(self, fmt, bitrate, album, out):
            done, failed = 0, []
            if fmt == "flac" and not find_flac():
                self._say("Fetching the FLAC encoder…")
                try:
                    download_flac()
                except Exception as e:
                    msg = "The FLAC encoder could not be fetched: %s" % e
                    self.app.root.after(0, lambda: self._finish(0, [msg]))
                    return
            if fmt == "mp3" and not have_mp3():
                self._say("Fetching MP3 support…")
                try:
                    ensure_mp3()
                except Exception as e:
                    msg = "MP3 support could not be fetched: %s" % e
                    self.app.root.after(0, lambda: self._finish(0, [msg]))
                    return
            for i, t in enumerate(self.tracks, start=1):
                name = self.app.lib.name_of(t)
                self._say("Exporting %d/%d: %s" % (i, len(self.tracks), name))
                try:
                    export_track(t, name, out, fmt=fmt, bitrate=bitrate, album=album,
                                 artist=self.app.lib.composer_of(t))
                    done += 1
                except Exception as e:
                    failed.append("%s: %s" % (name, e))
            self.app.root.after(0, lambda: self._finish(done, failed))

        def _finish(self, done, failed):
            msg = "Exported %d of %d." % (done, len(self.tracks))
            try:
                self.prog.set(msg)
                self.go_btn.state(["!disabled"])
            except tk.TclError:
                return            # closed while it worked
            if failed:
                messagebox.showerror(APP_NAME, msg + "\n\n" + "\n".join(failed[:10]),
                                     parent=self.win)

    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    run_app()