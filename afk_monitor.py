import argparse
import ctypes
import json
import os
import re
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
try:
    from discord_webhook import DiscordWebhook
    discord_enabled = True
except ImportError:
    discord_enabled = False
    print("discord-webhook unavailable - operating with terminal output only\n")

def fallover(message):
    print(message)
    if sys.argv[0].count("\\") > 1: input("Press ENTER to exit")
    sys.exit()

# Internals
DEBUG_MODE = False
DISCORD_TEST = False
VERSION = 260122
GITHUB_REPO = "PsiPab/ED-AFK-Monitor"
DUPE_MAX = 5
MAX_FILES = 10
FUEL_LOW = 0.2		# 20%
FUEL_CRIT = 0.1		# 10%
TRUNC_FACTION = 30
KILLS_RECENT = 10
WARN_NOKILLS = 5	# Minutes before warning of no kills at session start
WARN_COOLDOWN = 15	# Cooldown in minutes after a kill rate warning (doubled each time thereafter)
UNKNOWN = "[Unknown]"
REG_JOURNAL = r"^Journal\.\d{4}-\d{2}-\d{2}T\d{6}\.\d{2}\.log$"
REG_WEBHOOK = r"^https:\/\/(?:canary\.|ptb\.)?discord(?:app)?\.com\/api\/webhooks\/\d+\/[A-z0-9_-]+$"
SHIPS_EASY = ["adder", "asp", "asp_scout", "cobramkiii", "cobramkiv", "diamondback", "diamondbackxl", "eagle", "empire_courier", "empire_eagle", "krait_light", "sidewinder", "viper", "viper_mkiv"]
SHIPS_HARD = ["typex", "typex_2", "typex_3", "anaconda", "federation_dropship_mkii", "federation_dropship", "federation_gunship", "ferdelance", "empire_trader", "krait_mkii", "python", "vulture", "type9_military"]
BAIT_MESSAGES = ["$Pirate_ThreatTooHigh", "$Pirate_NotEnoughCargo", "$Pirate_OnNoCargoFound"]
LOGLEVEL_DEFAULTS = {"ScanIncoming": 1, "ScanEasy": 1, "ScanHard": 2, "KillEasy": 2, "KillHard": 2, "FighterHull": 2, "FighterDown": 3, "ShipShields": 3, "ShipHull": 3, "Died": 3, "CargoLost": 3, "BaitValueLow": 2, "SecurityScan": 2, "SecurityAttack": 3, "FuelLow": 2, "FuelCritical": 3, "FuelReport": 1, "Missions": 2, "MissionsAll": 3, "Merits": 0, "SummaryKills": 2, "SummaryBounties": 2, "SummaryMerits": 2, "NoKills": 3, "KillRate": 3}
COMBAT_RANKS = ["Harmless", "Mostly Harmless", "Novice", "Competent", "Expert", "Master", "Dangerous", "Deadly", "Elite", "Elite I", "Elite II", "Elite III", "Elite IV", "Elite V"]

class Col:
    CYAN = "\033[96m"
    YELL = "\033[93m"
    EASY = "\x1b[38;5;157m"
    HARD = "\x1b[38;5;217m"
    WARN = "\x1b[38;5;215m"
    BAD = "\x1b[38;5;15m\x1b[48;5;1m"
    GOOD = "\x1b[38;5;15m\x1b[48;5;2m"
    WHITE = "\033[97m"
    END = "\x1b[0m"

# Update check
url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
latest_version = 0
try:
    with urlopen(url, timeout=1) as response:
        if response.status == 200:
            release_data = json.loads(response.read())
            latest_version = int(release_data["tag_name"][1:])
except Exception:
    pass

# Print header
title = f"ED AFK Monitor v{VERSION} by CMDR PSIPAB"
print(f"{Col.CYAN}{"="*len(title)}")
print(f"{title}")
print(f"{"="*len(title)}{Col.END}\n")
if VERSION < latest_version:
    print(f"{Col.YELL}Update v{latest_version} is available!{Col.END}\n{Col.WHITE}Download:{Col.END} https://github.com/{GITHUB_REPO}/releases\n")

# Load config file
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    configfile = Path(__file__).parents[1] / "afk_monitor.toml"
else:
    configfile = Path(__file__).parent / "afk_monitor.toml"
if configfile.is_file():
    with open(configfile, mode="rb") as f:
        try:
            config = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            fallover(f"Config decode error: {e}")
else:
    fallover("Config file not found: copy and rename afk_monitor.example.toml to afk_monitor.toml\n")

# Command line overrides
parser = argparse.ArgumentParser(
    prog="ED AFK Monitor",
    description="Live monitoring of Elite Dangerous AFK sessions to terminal and Discord")
parser.add_argument("-p", "--profile", help="Load a specific profile for config settings")
parser.add_argument("-j", "--journal", help="Override for path to journal folder")
parser.add_argument("-w", "--webhook", help="Override for Discord webhook URL")
parser.add_argument("-r", "--resetsession", action="store_true", default=None, help="Reset session stats after preloading")
parser.add_argument("-t", "--test", action="store_true", default=None, help="Re-routes Discord messages to terminal")
parser.add_argument("-d", "--debug", action="store_true", default=None, help="Print information for debugging")
file_group = parser.add_mutually_exclusive_group()
file_group.add_argument("-s", "--setfile", help="Set specific journal file to use")
file_group.add_argument("-f", "--fileselect", action="store_true", default=None, help="Show list of recent journals to chose from")
args = parser.parse_args()

# Get a setting from config
def getconfig(category, setting, default=None):
    if profile and config.get(profile, {}).get(category, {}).get(setting) is not None:
        return config.get(profile, {}).get(category, {}).get(setting)
    elif config.get(category, {}).get(setting) is not None:
        return config.get(category, {}).get(setting)
    else:
        return default if default is not None else None

# Get settings from arguments
profile = args.profile if args.profile is not None else None
setting_fileselect = args.fileselect if args.fileselect is not None else False
setting_journal_dir = args.journal if args.journal is not None else getconfig("Settings", "JournalFolder")
setting_journal_file = args.setfile if args.setfile is not None else None
discord_test = args.test if args.test is not None else DISCORD_TEST
debug_mode = args.debug if args.debug is not None else DEBUG_MODE

def debug(message):
    if debug_mode:
        print(f"{Col.WHITE}[Debug]{Col.END} {message} [{datetime.strftime(datetime.now(), "%H:%M:%S")}]")

debug(f"Arguments: {args}")
debug(f"Config: {config}")

class Stats:
    def __init__(self):
        self.reset()

    def reset(self):
        self.scansinrecents = []
        self.scansoutrecents = []
        self.lastkillutc = 0
        self.lastkillmono = 0
        self.killstime = 0
        self.killsrecent = []
        self.scansin = 0
        self.kills = 0
        self.bounties = 0
        self.factions = {}
        self.merits = 0
        self.lastsecurity = ""
        self.baitfails = 0
        self.fuellasttime = 0
        self.fuellastremain = 0
        self.meritstoreport = 0

class Tracking:
    def __init__(self):
        self.deploytime = None
        self.warnednokills = None
        self.warnedkillrate = None
        self.fuelcapacity = 64
        self.killtype = "bounties"
        self.fighterhull = 0
        self.logged = 0
        self.lines = 0
        self.missions = False
        self.missionsactive = []
        self.missionredirects = 0
        self.lasteventname = None
        self.thiseventtime = None
        self.dupeevent = ""
        self.duperepeats = 1
        self.dupewarn = False
        self.preloading = True
        self.cmdrname = None
        self.cmdrship = None
        self.cmdrcombatrank = None
        self.cmdrcombatprogress = None
        self.cmdrgamemode = None
        self.cmdrlocation = None
        self.lastcheck = None
    
    def sessionstart(self, reset=False):
        if not self.deploytime or reset:
            self.deploytime = self.thiseventtime
            debug(f"Session tracking started at {self.deploytime}")
            session.reset()
            self.warnednokills = None
            self.warnedkillrate = None
            self.lastcheck = time.monotonic()
            updatetitle()

    def sessionend(self):
        if self.deploytime:
            debug(f"Session tracking ended at {self.thiseventtime} ({time_format((self.thiseventtime-self.deploytime).total_seconds())})")
            self.deploytime = None
            updatetitle(True)

session = Stats()
total = Stats()
track = Tracking()

# Set journal directory
if not setting_journal_dir:
    journal_dir = Path.home() / "Saved Games" / "Frontier Developments" / "Elite Dangerous"
else:
    journal_dir = Path(setting_journal_dir)
if not journal_dir.is_dir():
    fallover(f"Directory {journal_dir} not found")

print(f"{Col.YELL}Journal folder:{Col.END} {journal_dir}")

# Set journal file
if not setting_journal_file:
    journals = []
    journal_file = None

    # Get recent journals, newest first
    for entry in sorted(journal_dir.iterdir(), reverse=True):
        if entry.is_file() and bool(re.search(REG_JOURNAL, entry.name)):
            if not setting_fileselect:
                # Just the latest journal
                journal_file = entry.name
                break
            else:
                # Build list of recent journals
                journals.append(entry.name)
                if len(journals) == MAX_FILES: break
    
    # Exit if no journals were found
    if not journal_file and len(journals) == 0:
        fallover(f"Journal folder does not contain any valid journal files")
    
    # Journal selector
    if setting_fileselect:
        print(f"\nLatest journals:")

        # Get commander name from each journal and output list
        commanders = []
        for i, filename in enumerate(journals, start=1):
            commander = None
            with open(Path(journal_dir / filename), mode="r", encoding="utf-8") as file:
                for line in file:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError as e:
                        print(f"[Fileselect] JSON error in {filename}: {e}")
                    if entry["event"] == "Commander":
                        commander =  entry["Name"]
                        break

            num = f"{i:>{len(str(len(journals)))}}"
            print(f"{num} | {filename} | CMDR {commander if commander else UNKNOWN}")
            commanders.append(commander)

        # Prompt for journal choice
        print("\nInput journal number to load")
        selection = input("(ENTER for latest or any other input to quit)\n")
        if selection:
            try:
                selection = int(selection)
                if 1 <= selection <= MAX_FILES:
                    journal_file = journals[selection-1]
                    track.cmdrname = commanders[selection-1]
                else:
                    fallover(f"Invalid number, exiting...")
            except ValueError:
                fallover(f"Exiting...")
        else:
            journal_file = journals[0]
            track.cmdrname = commanders[0]
elif setting_journal_file:
    # Set specific journal file
    journal_file = setting_journal_file if bool(re.search(REG_JOURNAL, setting_journal_file)) else None
    if not journal_file or not (journal_dir / journal_file).is_file():
        fallover(f"Journal file '{setting_journal_file}' invalid or not found")

print(f"{Col.YELL}Journal file:{Col.END} {journal_file}")

# Get commander name if not already known
if not track.cmdrname:
    try:
        with open(Path(journal_dir / journal_file), mode="r", encoding="utf-8") as file:
            for line in file:
                entry = json.loads(line)
                if entry["event"] == "Commander":
                    track.cmdrname = entry["Name"]
                    break
            
            # If we *still* don't have a commander name wait for it
            if not track.cmdrname:
                print("Waiting for game load... (Press Ctrl+C to stop)")
                file.seek(0, 2)
                while True:
                    line = file.readline()
                    
                    if not line:
                        time.sleep(1)
                        continue
                    
                    entry = json.loads(line)
                    if entry["event"] == "Commander":
                        track.cmdrname = entry["Name"]
                        break
    except json.JSONDecodeError as e:
        print(f"[CMDR Name] JSON error in {journal_file}: {e}")
    except(KeyboardInterrupt):
        fallover("Quitting...")

print(f"{Col.YELL}Commander name:{Col.END} {track.cmdrname}")

# Check for a config profile if one is set
config_info = ""
if not args.profile:
    profile = track.cmdrname
    if profile in config:
        config_info = " (auto)"
if profile and not profile in config:
    debug(f"No config settings for '{profile}' found")
    profile = None

print(f"{Col.YELL}Config profile:{Col.END} {profile if profile else "Default"}{config_info}")
if profile: debug(f"Profile '{profile}': {config[profile]}")

# Get settings from config
setting_utc = getconfig("Settings", "UseUTC", False)
setting_dynamictitle = getconfig("Settings", "DynamicTitle", True)
setting_warnkillrate = getconfig("Settings", "WarnKillRate", 20)
setting_warnnokills = getconfig("Settings", "WarnNoKills", 20)
setting_piratenames = getconfig("Settings", "PirateNames", False)
setting_bountyfaction = getconfig("Settings", "BountyFaction", True)
setting_bountyvalue = getconfig("Settings", "BountyValue", False)
setting_extendedstats = getconfig("Settings", "ExtendedStats", False)
setting_minscanlevel = getconfig("Settings", "MinScanLevel", 1)
discord_webhook = args.webhook if args.webhook is not None else getconfig("Discord", "WebhookURL", "")
discord_user = getconfig("Discord", "UserID", 0)
discord_prependcmdr = getconfig("Discord", "PrependCmdrName", False)
discord_forumchannel = getconfig("Discord", "ForumChannel", False)
discord_threadcmdrnames = getconfig("Discord", "ThreadCmdrNames", False)
discord_timestamp = getconfig("Discord", "Timestamp", True)
discord_identity = getconfig("Discord", "Identity", True)

loglevel = {}
for level in LOGLEVEL_DEFAULTS:
    loglevel[level] = getconfig("LogLevels", level, LOGLEVEL_DEFAULTS[level])

debug(f"Log levels: {loglevel}")
print("\nStarting... (Press Ctrl+C to stop)\n")

# Check webhook appears valid before starting
if discord_enabled and re.search(REG_WEBHOOK, discord_webhook):
    webhook = DiscordWebhook(url=discord_webhook)
    if discord_identity:
        webhook.username = "ED AFK Monitor"
        webhook.avatar_url = "https://cdn.discordapp.com/attachments/1339930614064877570/1354083225923883038/t10.png"
    if discord_forumchannel:
        journal_start = datetime.fromisoformat(journal_file[8:-7])
        journal_start = datetime.strftime(journal_start, "%Y-%m-%d %H:%M:%S")
        if discord_threadcmdrnames:
            webhook.thread_name = f"{track.cmdrname} {journal_start}"
        else:
            webhook.thread_name = journal_start
        #debug(f"webhook.thread_name: {webhook.thread_name}")
elif discord_enabled:
    discord_enabled = False
    discord_test = False
    print(f"{Col.WHITE}Info:{Col.END} Discord webhook missing or invalid - operating with terminal output only\n")

# Send a webhook message or (don"t) die trying
def discordsend(message=""):
    if discord_enabled and message and not discord_test:
        try:
            webhook.content = message
            webhook.execute()
            if discord_forumchannel and webhook.thread_name and not webhook.thread_id:
                webhook.thread_name = None
                webhook.thread_id = webhook.id
                #debug(f"webhook.thread_id: {webhook.thread_id}")
        except Exception as e:
            print(f"{Col.WHITE}Discord:{Col.END} Webhook send error: {e}")
    elif discord_enabled and message and discord_test:
        print(f"{Col.WHITE}DISCORD:{Col.END} {message}")

# Log events
def logevent(msg_term, msg_discord=None, emoji=None, timestamp=None, loglevel=2, event=None):
    emoji = f"{emoji} " if emoji else ""
    loglevel = int(loglevel)
    if track.preloading and not discord_test:
        loglevel = 1 if loglevel > 0 else 0
    if timestamp:
        logtime = timestamp if setting_utc else timestamp.astimezone()
    else:
        logtime = datetime.now(timezone.utc) if setting_utc else datetime.now()
    logtime = datetime.strftime(logtime, "%H:%M:%S")
    track.logged +=1
    
    # Terminal
    if loglevel > 0 and not discord_test:
        print(f"[{logtime}]{emoji}{msg_term}")
    
    # Discord
    if discord_enabled and loglevel > 1:
        if event is not None and track.dupeevent == event:
            track.duperepeats += 1
        else:
            track.duperepeats = 1
            track.dupewarn = False
        track.dupeevent = event
        discord_message = msg_discord if msg_discord else f"**{msg_term}**"
        ping = f" <@{discord_user}>" if loglevel > 2 and track.duperepeats == 1 else ""
        logtime = f" {{{logtime}}}" if discord_timestamp else ""
        cmdrname = "" if not discord_prependcmdr else f"[{track.cmdrname}] "
        if track.duperepeats <= DUPE_MAX:
            discordsend(f"{cmdrname}{emoji}{discord_message}{logtime}{ping}")
        elif not track.dupewarn:
            discordsend(f"{cmdrname}⏸️ **Suppressing further duplicate messages**{logtime}")
            track.dupewarn = True

# Get log level from config or use default
def getloglevel(key=None) -> int:
    if key in loglevel and isinstance(loglevel[key], int):
        return loglevel[key]
    else:
        level = LOGLEVEL_DEFAULTS.get(key, 1)
        print(f"{Col.WHITE}Warning:{Col.END} '{key}' not found in 'LogLevels' (using default of {level})")
        return level

# Calculate somethings per hour
def perhour(seconds=0, precision=None):
    if seconds > 0:
        return round(3600 / seconds, precision)
    else:
        return 0

# Process incoming journal entries
def processevent(line):
    try:
        j = json.loads(line)
    except ValueError:
        print(f"{Col.WHITE}Warning:{Col.END} Journal parsing error, skipping line")
        return

    try:
        logtime = datetime.fromisoformat(j["timestamp"]) if "timestamp" in j else None
        track.thiseventtime = logtime
        match j["event"]:
            case "ReceiveText" if j["Channel"] == "npc":
                if "$Pirate_OnStartScanCargo" in j["Message"]:
                    piratename = j["From_Localised"] if "From_Localised" in j else UNKNOWN
                    if piratename not in session.scansinrecents:
                        session.scansin += 1
                        total.scansin += 1
                        scansin = f" (x{session.scansin})" if setting_extendedstats else ""
                        pirate = f" [{piratename}]" if setting_piratenames else ""
                        if len(session.scansinrecents) == 5:
                            session.scansinrecents.pop(0)
                        session.scansinrecents.append(piratename)                        
                        logevent(msg_term=f"Cargo scan{scansin}{pirate}",
                                 msg_discord=f"**Cargo scan{scansin}**{pirate}",
                                emoji="📦", timestamp=logtime, loglevel=getloglevel("ScanIncoming"))
                elif any(x in j["Message"] for x in BAIT_MESSAGES):
                    session.baitfails += 1
                    baitfails = f" (x{session.baitfails})" if setting_extendedstats else ""
                    logevent(msg_term=f"{Col.WARN}Pirate didn\"t engage due to insufficient cargo value{baitfails}{Col.END}",
                            msg_discord=f"**Pirate didn\"t engage due to insufficient cargo value**{baitfails}",
                            emoji="🎣", timestamp=logtime, loglevel=getloglevel("BaitValueLow"), event="BaitValueLow")
                elif "Police_Attack" in j["Message"]:
                    logevent(msg_term=f"{Col.BAD}Under attack by security services!{Col.END}",
                            msg_discord=f"**Under attack by security services!**",
                            emoji="🚨", timestamp=logtime, loglevel=getloglevel("SecurityAttack"))
            case "ShipTargeted" if "Ship" in j:
                ship = j["Ship_Localised"] if "Ship_Localised" in j else j["Ship"].title()
                rank = "" if not "PilotRank" in j else f" ({j["PilotRank"]})"
                # Security
                if ship != session.lastsecurity and "PilotName" in j and "$ShipName_Police" in j["PilotName"]:
                    session.lastsecurity = ship
                    logevent(msg_term=f"{Col.WARN}Scanned security{Col.END} ({ship})",
                            msg_discord=f"**Scanned security** ({ship})",
                            emoji="🚨", timestamp=logtime, loglevel=getloglevel("SecurityScan"))
                # Pirates etc.
                elif j["Ship"] in SHIPS_EASY or j["Ship"] in SHIPS_HARD:
                    track.sessionstart()
                    piratename = j["PilotName_Localised"] if "PilotName_Localised" in j else UNKNOWN
                    check = piratename if setting_minscanlevel != 0 else ship
                    scanstage = j["ScanStage"] if "ScanStage" in j else 0
                    if scanstage >= setting_minscanlevel and not check in session.scansoutrecents:
                        if len(session.scansoutrecents) == 10:
                            session.scansoutrecents.pop(0)
                        session.scansoutrecents.append(check)
                        pirate = f" [{piratename}]" if setting_piratenames else ""
                        hard = ""
                        log = getloglevel("ScanEasy")
                        if j["Ship"] in SHIPS_EASY:
                            col = Col.EASY
                        elif j["Ship"] in SHIPS_HARD:
                            col = Col.HARD
                            log = getloglevel("ScanHard")
                            hard = " ☠️"
                        else:
                            col = Col.WHITE
                        logevent(msg_term=f"{col}Scan{Col.END}: {ship}{rank}{pirate}",
                                msg_discord=f"**{ship}**{hard}{rank}{pirate}",
                                emoji="🔎", timestamp=logtime, loglevel=log)
            case "Bounty" | "FactionKillBond":
                track.sessionstart()
                if setting_minscanlevel == 0:
                    session.scansoutrecents.clear()
                session.kills +=1
                total.kills +=1
                thiskill = logtime
                killtime = ""
                track.lastcheck = time.monotonic()
                session.meritstoreport +=1
                
                if session.lastkillutc:
                    seconds = (thiskill-session.lastkillutc).total_seconds()
                    killtime = f" (+{time_format(seconds)})"
                    session.killstime += seconds
                    if len(session.killsrecent) == KILLS_RECENT: session.killsrecent.pop(0)
                    session.killsrecent.append(seconds)
                    total.killstime += seconds
                session.lastkillutc = logtime
                if not track.preloading:
                    session.lastkillmono = time.monotonic()

                hard = ""
                log = getloglevel("KillEasy")
                col = Col.WHITE
                if j["event"] == "Bounty":
                    if j["Target"] in SHIPS_EASY:
                        col = Col.EASY
                    elif j["Target"] in SHIPS_HARD:
                        col = Col.HARD
                        log = getloglevel("KillHard")
                        hard = " ☠️"
                    
                    bountyvalue = j["Rewards"][0]["Reward"]
                    ship = j["Target_Localised"] if "Target_Localised" in j else j["Target"].title()
                else:
                    bountyvalue = j["Reward"]
                    ship = "Bond"
                    track.killtype = "bonds"

                piratename = f" [{j['PilotName_Localised']}]" if "PilotName_Localised" in j and setting_piratenames else ""
                session.bounties += bountyvalue
                total.bounties += bountyvalue
                kills_t = f" x{session.kills}" if setting_extendedstats else ""
                kills_d = f"x{session.kills} " if setting_extendedstats else ""
                bountyvalue = f" [{num_format(bountyvalue)} cr]" if setting_bountyvalue else ""
                victimfaction = j["VictimFaction_Localised"] if "VictimFaction_Localised" in j else j["VictimFaction"]
                session.factions[victimfaction] = session.factions.get(victimfaction, 0) + 1
                total.factions[victimfaction] = total.factions.get(victimfaction, 0) + 1
                factioncount = f" x{session.factions[victimfaction]}" if setting_extendedstats else ""
                bountyfaction = victimfaction if len(victimfaction) <= TRUNC_FACTION+3 else f"{victimfaction[:TRUNC_FACTION].rstrip()}..."
                bountyfaction = f" [{bountyfaction}{factioncount}]" if setting_bountyfaction else ""
                logevent(msg_term=f"{col}Kill{Col.END}{kills_t}: {ship}{killtime}{piratename}{bountyvalue}{bountyfaction}",
                        msg_discord=f"{kills_d}**{ship}{hard}{killtime}**{piratename}{bountyvalue}{bountyfaction}",
                        emoji="💥", timestamp=logtime, loglevel=log)

                updatetitle()
                
                # Output stats every 10 kills
                if session.kills % 10 == 0:
                    summary(session, logtime=logtime)
            case "MissionRedirected" if "Mission_Massacre" in j["Name"]:
                track.missionredirects += 1
                msg = "a mission"
                missions = f"{track.missionredirects}/{len(track.missionsactive)}"
                if len(track.missionsactive) != track.missionredirects:
                    log = getloglevel("Missions")
                else:
                    log = getloglevel("MissionsAll")
                    msg = "all missions!"
                logevent(msg_term=f"Completed kills for {msg} ({missions})",
                        emoji="✅", timestamp=logtime, loglevel=log)
                updatetitle()
            case "ReservoirReplenished":
                fuelremaining = round((j["FuelMain"] / track.fuelcapacity) * 100)
                if session.fuellasttime and track.deploytime and logtime > session.fuellasttime:
                    fuel_time = (logtime-session.fuellasttime).total_seconds()
                    fuel_hour = 3600 / fuel_time * (session.fuellastremain-j["FuelMain"])
                    fuel_time_remain = time_format(j["FuelMain"] / fuel_hour * 3600)
                    fuel_time_remain = f" (~{fuel_time_remain})"
                    #debug(f"Fuel used since previous: {round(session.fuellastremain-j["FuelMain"],2)}t in {time_format(fuel_time)}")
                else:
                    fuel_time_remain = ""

                session.fuellasttime = logtime
                session.fuellastremain = j["FuelMain"]

                col = ""
                level = ":"
                fuel_loglevel = 0
                if j["FuelMain"] < track.fuelcapacity * FUEL_CRIT:
                    col = Col.BAD
                    fuel_loglevel = getloglevel("FuelCritical")
                    level = " critical!"
                elif j["FuelMain"] < track.fuelcapacity * FUEL_LOW:
                    col = Col.WARN
                    fuel_loglevel = getloglevel("FuelLow")
                    level = " low:"
                elif track.deploytime:
                    fuel_loglevel = getloglevel("FuelReport")

                logevent(msg_term=f"{col}Fuel: {fuelremaining}% remaining{Col.END}{fuel_time_remain}",
                    msg_discord=f"**Fuel{level} {fuelremaining}% remaining**{fuel_time_remain}",
                    emoji="⛽", timestamp=logtime, loglevel=fuel_loglevel)
            case "FighterDestroyed" if track.lasteventname != "StartJump":
                logevent(msg_term=f"{Col.BAD}Fighter destroyed!{Col.END}",
                        msg_discord=f"**Fighter destroyed!**",
                        emoji="🕹️", timestamp=logtime, loglevel=getloglevel("FighterDown"))
            case "LaunchFighter" if not j["PlayerControlled"]:
                logevent(msg_term="Fighter launched",
                        emoji="🕹️", timestamp=logtime, loglevel=2)
            case "ShieldState":
                if j["ShieldsUp"]:
                    shields = "back up"
                    col = Col.GOOD
                else:
                    shields = "down!"
                    col = Col.BAD
                logevent(msg_term=f"{col}Ship shields {shields}{Col.END}",
                        msg_discord=f"**Ship shields {shields}**",
                        emoji="🛡️", timestamp=logtime, loglevel=getloglevel("ShipShields"))
            case "HullDamage":
                hullhealth = round(j["Health"] * 100)
                if j["Fighter"] and not j["PlayerPilot"] and track.fighterhull != j["Health"]:
                    track.fighterhull = j["Health"]
                    logevent(msg_term=f"{Col.WARN}Fighter hull damaged!{Col.END} (Integrity: {hullhealth}%)",
                        msg_discord=f"**Fighter hull damaged!** (Integrity: {hullhealth}%)",
                        emoji="🕹️", timestamp=logtime, loglevel=getloglevel("FighterHull"))
                elif j["PlayerPilot"] and not j["Fighter"]:
                    logevent(msg_term=f"{Col.BAD}Ship hull damaged!{Col.END} (Integrity: {hullhealth}%)",
                        msg_discord=f"**Ship hull damaged!** (Integrity: {hullhealth}%)",
                        emoji="🛠️", timestamp=logtime, loglevel=getloglevel("ShipHull"))
            case "Died":
                logevent(msg_term=f"{Col.BAD}Ship destroyed!{Col.END}",
                        msg_discord="**Ship destroyed!**",
                        emoji="💀", timestamp=logtime, loglevel=getloglevel("Died"))
            case "Music" if j["MusicTrack"] == "MainMenu":
                track.sessionend()
                logevent(msg_term="Exited to main menu",
                    emoji="🚪", timestamp=logtime, loglevel=2)
            case "LoadGame":
                if "Ship_Localised" in j:
                    track.cmdrship = j["Ship_Localised"]
                elif "Ship" in j:
                    track.cmdrship = j["Ship"]

                if "GameMode" in j:
                    track.cmdrgamemode = "Private Group" if j["GameMode"] == "Group" else j["GameMode"]

                cmdrinfo =  f"{track.cmdrship} / {track.cmdrgamemode} / {track.cmdrcombatrank} +{track.cmdrcombatprogress}%"
                
                logevent(msg_term=f"CMDR {track.cmdrname} ({cmdrinfo})",
                         msg_discord=f"**CMDR {track.cmdrname}** ({cmdrinfo})",
                         emoji="🔄", timestamp=logtime, loglevel=2)
            case "Loadout":
                track.fuelcapacity = j["FuelCapacity"]["Main"] if j["FuelCapacity"]["Main"] >= 2 else 64
                #debug(f"Fuel capacity: {track.fuelcapacity}")
            case "SupercruiseDestinationDrop" if any(x in j["Type"] for x in ["$MULTIPLAYER", "$Warzone"]):
                track.sessionstart(True)
                type = j["Type_Localised"] if "Type_Localised" in j else UNKNOWN
                if "Resource Extraction Site" in type:
                    emoji = "🪐"
                else:
                    emoji = "⚔️"
                logevent(msg_term=f"Dropped at {type}",
                        emoji=emoji, timestamp=logtime, loglevel=2)
                debug(f"Deploy time by supercruise drop: {track.deploytime}")
            case "EjectCargo" if not j["Abandoned"] and j["Count"] == 1:
                name = j["Type_Localised"] if "Type_Localised" in j else j["Type"].title()
                logevent(msg_term=f"{Col.BAD}Cargo stolen!{Col.END} ({name})",
                        msg_discord=f"**Cargo stolen!** ({name})",
                        emoji="🪓", timestamp=logtime, loglevel=getloglevel("CargoLost"), event="CargoLost")
            case "Rank":
                track.cmdrcombatrank = COMBAT_RANKS[j["Combat"]]
            case "Progress":
                track.cmdrcombatprogress = j["Combat"]
            case "Missions" if "Active" in j and not track.missions:
                track.missionsactive.clear()
                track.missionredirects = 0
                for mission in j["Active"]:
                    if "Mission_Massacre" in mission["Name"] and mission["Expires"] > 0:
                        track.missionsactive.append(mission["MissionID"])
                track.missions = True
                logevent(msg_term=f"Missions loaded (active massacres: {len(track.missionsactive)})",
                        emoji="🎯", timestamp=logtime, loglevel=getloglevel("Missions"))
            case "MissionAccepted" if "Mission_Massacre" in j["Name"] and track.missions:
                track.missionsactive.append(j["MissionID"])
                logevent(msg_term=f"Accepted massacre mission (active: {len(track.missionsactive)})",
                        emoji="🎯", timestamp=logtime, loglevel=getloglevel("Missions"))
            case "MissionAbandoned" | "MissionCompleted" | "MissionFailed" if track.missions and j["MissionID"] in track.missionsactive:
                track.missionsactive.remove(j["MissionID"])
                if track.missionredirects > 0: track.missionredirects -= 1
                event = j["event"][7:].lower()
                logevent(msg_term=f"Massacre mission {event} (active: {len(track.missionsactive)})",
                        emoji="🎯", timestamp=logtime, loglevel=getloglevel("Missions"))
            case "PowerplayMerits":
                if session.meritstoreport > 0 and j["MeritsGained"] < 500:
                    session.merits += j["MeritsGained"]
                    total.merits += j["MeritsGained"]
                    logevent(msg_term=f"Merits: +{j["MeritsGained"]} ({j["Power"]})",
                             emoji="🎫", timestamp=logtime, loglevel=getloglevel("Merits"))
                    session.meritstoreport -= 1
            case "Location":
                #track.cmdrlocation = j["StarSystem"]
                if j["BodyType"] == "PlanetaryRing":
                    track.sessionstart()
                    #debug(f"Deploy time by location (planetary ring) {track.deploytime}")
            case "ShipyardSwap":
                track.cmdrship = j["ShipType"].title() if "ShipType_Localised" not in j else j["ShipType_Localised"]
                logevent(msg_term=f"Swapped ship to {track.cmdrship}",
                        emoji="🚢", timestamp=logtime, loglevel=2)
            case "Shutdown":
                logevent(msg_term="Quit to desktop",
                        emoji="🛑", timestamp=logtime, loglevel=2)
                if __name__ == "__main__": sys.exit()
            case "SupercruiseEntry" | "FSDJump":
                if j["event"] == "SupercruiseEntry":
                    event = "Supercruise entry in"
                    emoji = "🚀"
                else:
                    event = "FSD jump to"
                    emoji = "🌌"
                logevent(msg_term=f"{event} {j["StarSystem"]}",
                        emoji=emoji, timestamp=logtime, loglevel=2)
                track.sessionend()
        track.lasteventname = j["event"]
    except Exception as e:
        event = j["event"] if "event" in j else UNKNOWN
        logtime = datetime.strftime(logtime, "%H:%M:%S") if logtime else UNKNOWN
        print(f"{Col.WARN}Warning:{Col.END} Process event error for [{event}]: {e} (logtime: {logtime})")
        debug(line)

def time_format(seconds: int) -> str:
	if seconds is not None and seconds >= 0:
		seconds = int(seconds)
		h = seconds // 3600
		m = seconds % 3600 // 60
		s = seconds % 3600 % 60
		if h > 0:
			return '{:d}h{:d}m'.format(h, m)
		elif m > 0:
			return '{:d}m{:d}s'.format(m, s)
		else:
			return '{:d}s'.format(s)
	else:
		return "-"

def num_format(number: int) -> str:
    if number is not None:
        number = int(number)
        if number >= 999_500:
            return f"{round(number / 1_000_000, 1):g}m"
        elif number >= 1_000:
            return f"{round(number / 1_000):g}k"
        else:
            return number

def updatetitle(reset=False):
    # Title (Windows-only)
    if os.name=="nt":
        if setting_dynamictitle and not track.preloading and track.deploytime:
            timeutc = datetime.now(timezone.utc)
            if session.kills > 0:
                kills_hour = perhour((timeutc - track.deploytime).total_seconds() / session.kills, 1)
                kills_hour = f"{kills_hour}/h" if session.kills > 19 else f"{kills_hour}*/h"
            else:
                kills_hour = "-/h"
            
            if session.lastkillmono:
                lastkill = time_format(time.monotonic() - session.lastkillmono)
            elif session.kills > 0:
                lastkill = time_format((timeutc - session.lastkillutc).total_seconds())
            else:
                lastkill = time_format((timeutc - track.deploytime).total_seconds())
            
            ctypes.windll.kernel32.SetConsoleTitleW(f"💥{kills_hour} ⌚{lastkill} 🎯{track.missionredirects}/{len(track.missionsactive)}")
        elif reset == True:
            ctypes.windll.kernel32.SetConsoleTitleW(f"ED AFK Monitor v{VERSION}")
            #debug("Title update")

# Output stats for kills, bounties and merits
def summary(stats, logtime=None, session=True):
    if stats.kills > 1:
        type = "Session" if session else "Total"
        avgseconds = stats.killstime / (stats.kills - 1)
        kills_hour = perhour(avgseconds, 1)
        avgbounty = stats.bounties // stats.kills
        bounties_hour = perhour(stats.killstime / stats.bounties)
        fac_kills = max(stats.factions.values())
        fac_kills_hour = f" [Fac: {perhour(stats.killstime / (fac_kills - 1), 1)}/h]" if setting_extendedstats else ""
        
        kills_hour_recent = ""
        if session and setting_extendedstats and stats.kills > KILLS_RECENT:
            avgsecondsrecent = sum(stats.killsrecent) / (KILLS_RECENT)
            kills_hour_recent = f" [x{KILLS_RECENT}: {perhour(avgsecondsrecent, 1)}/h]"
        
        logevent(msg_term=f"{type} kills: {stats.kills:,} ({kills_hour}/h | {time_format(avgseconds)}/kill){fac_kills_hour}{kills_hour_recent}",
                 msg_discord=f"**{type} kills: {stats.kills:,} ({kills_hour}/h | {time_format(avgseconds)}/kill)**{fac_kills_hour}{kills_hour_recent}",
                emoji="📝", timestamp=logtime, loglevel=getloglevel("SummaryKills"))
        
        logevent(msg_term=f"{type} {track.killtype}: {num_format(stats.bounties)} ({num_format(bounties_hour)}/h | {num_format(avgbounty)}/kill)",
                emoji="📝", timestamp=logtime, loglevel=getloglevel("SummaryBounties"))
        
        if stats.merits > 0:
            avgmerits = round(stats.merits / stats.kills, 1)
            merits_hour = perhour(stats.killstime / stats.merits) if stats.merits > 0 else 0
            logevent(msg_term=f"{type} merits: {stats.merits:,} ({merits_hour:,}/h | {avgmerits:,}/kill)",
                    emoji="📝", timestamp=logtime, loglevel=getloglevel("SummaryMerits"))

if __name__ == "__main__":
    try:
        # Journal preloading
        if track.preloading:
            with open(journal_dir / journal_file, mode="r", encoding="utf-8") as file:
                for line in file:
                    processevent(line)
                    track.lines += 1
            track.preloading = False
            if args.resetsession:
                session.reset()
                logevent(msg_term=f"Session stats reset",
                        emoji="🔄", loglevel=1)
            updatetitle(True)

        # Send Discord startup
        update_notice = f"\n:arrow_up: Update **[v{latest_version}](https://github.com/{GITHUB_REPO}/releases)** available!" if VERSION < latest_version else ""

        if discord_enabled:
            if discord_forumchannel:
                discordsend(f"💥 **ED AFK Monitor** 💥 by CMDR PSIPAB ([v{VERSION}](https://github.com/{GITHUB_REPO})){update_notice}")
                webhook.content += f" <@{discord_user}>"
                webhook.edit()
            else:
                discordsend(f"# 💥 ED AFK Monitor 💥\n-# **by CMDR PSIPAB ([v{VERSION}](https://github.com/{GITHUB_REPO})){update_notice}**")
        
        logevent(msg_term=f"Monitor started ({journal_file})",
                 msg_discord=f"**Monitor started** ({journal_file})",
                 emoji="📖", loglevel=2)
        
        # Open journal from end and watch for new lines
        trackingerror = None
        cooldown = WARN_COOLDOWN
        
        with open(journal_dir / journal_file, mode="r", encoding="utf-8") as file:
            file.seek(0, 2)

            while True:
                line = file.readline()
                if not line:
                    try:
                        if track.deploytime:
                            # Check for instance problems every minute
                            timemono = time.monotonic()
                            if not track.lastcheck or timemono - track.lastcheck >= 60:
                                timeutc = datetime.now(timezone.utc)
                                sessionsecs = (timeutc - track.deploytime).total_seconds()
                                if sessionsecs == 0: sessionsecs = 1	# Avoid divide-by-zero if session started by first kill
                                #if track.lastcheck: debug(f"Last: {track.lastcheck} / This: {timemono} / Drift: {60-(timemono - track.lastcheck)}")
                                timemono = timemono + (60 - (timemono - track.lastcheck)) if track.lastcheck else timemono	# Account for drift
                                track.lastcheck = timemono
                                
                                if session.kills:
                                    # Clear last warned time if past cooldown
                                    if track.warnedkillrate and timemono - track.warnedkillrate >= (cooldown * 60):
                                        cooldown *= 2
                                        track.warnedkillrate = None
                                    
                                    # Check average kill rate
                                    kills_hour = perhour(sessionsecs / session.kills, 1)
                                    #debug(f"Kills per hour {kills_hour}")
                                    if kills_hour < setting_warnkillrate:
                                        if not track.warnedkillrate and sessionsecs >= (5 * 60) and (not track.warnednokills or
                                                timemono - track.warnednokills >= (5 * 60)):
                                            logevent(msg_term=f"Kill rate of {kills_hour}/h is below {setting_warnkillrate}/h threshold",
                                                    emoji="⚠️", loglevel=getloglevel("KillRate"))
                                            track.warnedkillrate = timemono
                                    else:
                                    # Check time since last kill
                                        lastkill = int((timeutc - session.lastkillutc).total_seconds() / 60)
                                        #debug(f"timeutc: {timeutc} | lastkill: {lastkill} | track.warnedkillrate: {track.warnedkillrate} | setting_warnnokills: {setting_warnnokills}")
                                        if not track.warnedkillrate and lastkill >= (setting_warnnokills):
                                            logevent(msg_term=f"Last logged kill was {lastkill} minutes ago",
                                                emoji="⚠️", loglevel=getloglevel("NoKills"))
                                            track.warnedkillrate = timemono
                                else:
                                    # Clear last warned time if past cooldown
                                    if track.warnednokills and timemono - track.warnednokills >= (cooldown * 60):
                                        track.warnednokills = None

                                    # Check time since deployment if no kills yet
                                    sessionmins = int(sessionsecs / 60)
                                    #debug(f"No kills logged since start of session {sessionmins} ({sessionsecs / 60}) minutes ago [WARN_NOKILLS*60: {WARN_NOKILLS * 60}]")
                                    if not track.warnednokills and sessionsecs >= (WARN_NOKILLS * 60):
                                        logevent(msg_term=f"No kills logged for {sessionmins} minutes",
                                                emoji="⚠️", loglevel=getloglevel("NoKills"))
                                        track.warnednokills = timemono
                    except Exception as e:
                        if repr(e) != trackingerror:
                            print(f"{Col.WARN}Warning:{Col.END} Kill rate tracking error: {e} [{datetime.strftime(datetime.now(), "%H:%M:%S")}])")
                            trackingerror = repr(e)
                    
                    time.sleep(1)
                    updatetitle()
                    continue

                processevent(line)
                track.lines += 1

    except (KeyboardInterrupt, SystemExit):
        summary(total, session=False)
        logevent(msg_term=f"Monitor stopped ({journal_file})",
        msg_discord=f"**Monitor stopped** ({journal_file})",
        emoji="📕", loglevel=2)
        debug(f"\nTrack: {track.__dict__}")
        
        if sys.argv[0].count("\\") > 1:
            input("\nPress ENTER to exit")	# This is *still* horrible
            sys.exit()
    except Exception as e:
        print(f"{Col.WARN}Warning:{Col.END} Something went wrong: {e} (journal line #{track.lines})")
        input("Press ENTER to exit")
