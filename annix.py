#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
from typing import TypedDict, Callable, Hashable, IO, cast, Any
from textwrap import wrap
from enum import Enum
import argcomplete
import subprocess
import itertools
import argparse
import hashlib
import shutil
import pydoc
import json
import sys
import os
import re

#========================= CONFIGS =========================#

config = {}
try:
    configPath = "/".join(os.path.realpath(__file__).split("/")[:-1] + ["config.json"])
    with open(configPath, "r") as f: config = json.load(f)

except Exception as e:
    print(f"\033[93mConfig warning: Failed to load config:\n{e}\n\n\tDefaults will be used instead\n\033[0m")

# By default, env vars start with "ANNIX_"
def cfg(key: str, default: Any, env_prefix = True) -> Any:
    return os.environ.get(("ANNIX_" if env_prefix else "") + key, config[key] if key in config else default)


# The location of your an.nix file
ANNIX_FILE = cfg("ANNIX_FILE", "/etc/nixos/an.nix", False)
ANNIX_FILE_NAME = os.path.basename(ANNIX_FILE)

# Command to rebuild the system
REBUILD_COMMAND_DELIM = cfg("REBUILD_COMMAND_DELIM", None)
REBUILD_COMMAND = cfg("REBUILD_COMMAND", "nixos rebuild-switch").split(REBUILD_COMMAND_DELIM)

# Default token characters used to trick textwrap into correct ansi code handling
# Must have len() == 1 and not be split by wrap() or contained in the text to be split
TOKCHAR1 = cfg("TOKCHAR1", "ඞ")
TOKCHARN = cfg("TOKCHARN", "⍨")

# Minimum terminal width for text wrapping
MIN_WRAP_WIDTH = cfg("MIN_WRAP_WIDTH", 10)


#========================= UTILS =========================#

#-------------------- I/O --------------------#
def readf(path = ANNIX_FILE) -> list[str] | None:
    try:
        with open(path, "r") as f: return f.readlines()

    except PermissionError: error("File", f"Permission denied - Cannot read {path}")
    except Exception as e:  error("File", f"Failed to read:\n{e}")

    return None

def writef(lines: list[str], path = ANNIX_FILE) -> bool:
    try:
        with open(path, "w") as f:    f.writelines(lines); return True

    except PermissionError: error("File", f"Permission denied - Cannot write to {path}")
    except Exception as e:  error("File", f"Failed to save:\n{e}")

    return False


def error(type: str, message: str, line: tuple[int, str] | None = None):
    print(f"\033[91m{type} error: {message}\033[0m")
    if line:    print(f"{ANNIX_FILE}:{line[0]} \n\"\"\"\n{line[1].rstrip()}\n\"\"\"")
    sys.exit(1)

def warn(type: str, message: str, line: tuple[int, str] | None = None, suppress = False):
    if suppress: return
    print(f"\033[93m{type} warning: {message}\033[0m")
    if line:    print(f"{ANNIX_FILE}:{line[0]} \n\"\"\"\n{line[1].rstrip()}\n\"\"\"")


# Get string length ignoring ansi codes
def len_no_ansi(string):
    return len(re.sub(
        r'[\u001B\u009B][\[\]()#;?]*((([a-zA-Z\d]*(;[-a-zA-Z\d\/#&.:=?%@~_]*)*)?\u0007)|((\d{1,4}(?:;\d{0,4})*)?[\dA-PR-TZcf-ntqry=><~]))',
        '', string
    ))

# Disgusting hack to wrap() ansi strings ⍨
def wrapAnsiLine(text: str, tokens: list[tuple[int, str]], width: int, tok_char_1 = TOKCHAR1, tok_char_n = TOKCHARN) -> list[str]:
    singles = [f"\033[{t[0]}m{t[1]}\033[0m" for t in tokens if len(t[1]) == 1]
    multis = list(itertools.chain(*[
        [f"\033[{t[0]}m{t[1][0]}", f"{t[1][-1]}\033[0m"]
        for t in tokens if len(t[1]) > 1
    ]))

    def pack(tok: str) -> str:
        if not tok:         return ""
        elif len(tok) == 1: return tok_char_1
        else:               return tok_char_n + tok[1:-1] + tok_char_n

    # Given: [ (94, "hello"), (95, "world"), (96, "1") ]:
    # "> {} @ {} [{}]"   ->   "> ⍨ell⍨ @ ⍨orl⍨ [ඞ]"
    digest = text.format(*[pack(t[1]) for t in tokens])

    # "> ⍨ell⍨ @ ⍨orl⍨ [ඞ]"   ->   [ "> \033[94mell\033[0m @ \033[95morl\033[0m [\033[96m1\033[0m]" ]
    content = "\n".join(wrap(digest, width))
    content = content.replace(tok_char_1, "{}").format(*singles)
    content = content.replace(tok_char_n, "{}").format(*multis)
    return content.split("\n")

def wrapLines(text: str, width: int) -> list[str]:
    lines = [l.rstrip() for l in text.split("\n")]
    if not lines: return []
    return list(itertools.chain(*[wrap(l, width, tabsize=4) for l in lines]))

# Return all duplicate elements in a list
def findDuplicates(vals: list, key: Callable[[Any], Hashable] = lambda x: x) -> list:
    duplicates, seen = set(), set()
    for val in vals:
        k = key(val)
        if k in seen: duplicates.add(k)
        seen.add(k)

    return list(duplicates)

#-------------------- PARSING --------------------#
# Parsed an.nix file
Parsed = TypedDict("Parsed", {
    'hash':     tuple[str, int, str],           # (hash, line_no, comment incl. whitespace)
    'addhere':  tuple[bool, int],               # (above?, line_no)

    'pkgs':     list[tuple[str, int, str]],     # (pkg_name, line_no, comment incl. whitespace)
    'disabled': list[tuple[str, int, str]],     # (pkg_name, line_no, comment incl. whitespace)
    'code':     list[tuple[str, int]]           # (code, line_no)
})

class PkgMask(Enum): NONE = "n"; ACTIVE = "a"; DISABLED = "d"; ALL = "a"

# Parse a stripped package line into (pkg_name | err?, comment)
def parse_pkg_line(stripped_line: str) -> tuple[str | None, str]:
    pkg = stripped_line.split()[0]
    tail = stripped_line.removeprefix(pkg)
    if tail.strip() == "":              return (pkg, "")
    if tail.lstrip().startswith("#"):   return (pkg, tail)
    else:                               return (None, "multiplePackages")

# Parse a single an.nix line
# Returns a (type, content) tuple
def parse_line(line: str) -> tuple[str, dict[str, object]]:
    ln = line.strip()
    if not ln:                      return ("blank", {})

    if "/*" in ln or "*/" in ln:    return ("err", { '_': "multilineComment" })
    if "''" in ln:                  return ("err", { '_': "multilineString" })

    if ln.endswith("#@"):           return ("code", { '_': " ".join(ln.removesuffix("#@").strip().split()) })
    if ln.startswith("#@#") and (hash := ln.removeprefix("#@#").split()[0].strip()):
        try: int(hash, 16);         return ("hash", { 'hash': hash, 'comment': ln.split(hash)[-1] })
        except:                     return ("warn", { '_': "invalidHash" })

    if ln == "#@+":                 return ("addhere", { 'above': False })
    if ln == "#@+^":                return ("addhere", { 'above': True })

    if ln.startswith("#-") and (stripped_line := ln.removeprefix("#-").strip()) != "":
        # print(f"{ln=}, {stripped_line=}")
        pkg, comment = parse_pkg_line(stripped_line)
        if pkg is None:             return ("err", { '_': comment })
        else:                       return ("disabled", { 'pkg': pkg, 'comment': comment })

    if ln.startswith("#"):          return ("comment", {})

    pkg, comment = parse_pkg_line(ln)
    if pkg is None:             return ("err", { '_': comment })
    return ("pkg", { 'pkg': pkg, 'comment': comment })

# Parse an.nix and extract important features
def parse_annix(lines: list[str] | None = None, suppress_warn = False) -> Parsed | None:
    if lines is None: lines = readf()
    if lines is None: return None

    res: Parsed = { 'hash': ("", -1, ""), 'addhere': (False, -1), 'pkgs': [], 'disabled': [], 'code': [] }

    for i, line in enumerate(lines):
        (type, content) = parse_line(line)

        match type:
            case "blank" | "comment": continue

            case "err":
                match content['_']:
                    case "multilineComment":    error("Parse", "annix does not yet support multi-line comments", (i+1, line))
                    case "multilineString":     error("Parse", "annix does not yet support multi-line strings", (i+1, line))
                    case "multiplePackages":    error("Parse", "annix does not yet support multiple packages per line", (i+1, line))
                    case "invalidHash":         warn("Parse", f"Invalid hash found in {ANNIX_FILE_NAME}", (i+1, line), suppress_warn)
            
            case "hash":
                if res['hash'][1] != -1:        warn("Parse", f"Multiple hashes (#@#) found in {ANNIX_FILE_NAME}", (i+1, line), suppress_warn)
                else:                           res['hash'] = (cast(str, content['hash']), i, cast(str, content['comment']))

            case "addhere":
                if res['addhere'][1] != -1:     warn("Parse", f"Multiple addhere markers (#@+ / #@+^) found in {ANNIX_FILE_NAME}", (i+1, line), suppress_warn)
                else:                           res['addhere'] = (cast(bool, content['above']), i)
                continue

            case "pkg" | "disabled":
                pkg, comment = cast(str, content['pkg']), cast(str, content['comment'])
                res["pkgs" if type == "pkg" else type].append((pkg, i, comment))
                continue

            case "code": res["code"].append( (cast(str, content['_']), i) ); continue

    if len(dups := findDuplicates(res['pkgs'] + res['disabled'], lambda x: x[0])) != 0:
        warn("Parse", f"Duplicate packages found in {ANNIX_FILE}: [{', '.join(sorted(dups))}]", suppress=suppress_warn)

    return res


#-------------------- HASHING --------------------#
def get_hash_tokens(parsed: Parsed) -> list[str]:
    hpkgs = [("p", p, i) for p, i, _ in parsed['pkgs']]
    hcode = [("c", c, i) for c, i in parsed['code']]
    if len(hcode) == 0: return sorted([p for _, p, _ in hpkgs])
    if len(hpkgs) == 0: return [c for _, c, _ in hcode]

    mixed = sorted(hpkgs + hcode, key=lambda x: x[2]) # Sort by line no.
    tokens, i = [], 0

    while i < len(mixed):
        (t, x, _) = mixed[i]
        match t:
            case "p":
                pkgs = []
                while i < len(mixed) and t == "p":
                    (t, p, _) = mixed[i]
                    pkgs.append(p)
                    i += 1
                tokens += sorted(pkgs)

            case "c":
                tokens.append(x)
                i += 1

    return tokens

# Compute the package-order-invariant hash
def compute_hash(parsed: Parsed) -> str:
    tokens = get_hash_tokens(parsed)
    return hashlib.md5("\n".join(tokens).encode()).hexdigest()

# Compute + write new hash to an.nix
# Returns True if hash was updated
def update_hash() -> bool:
    if (lines := readf()) is None or (parsed := parse_annix(lines)) is None: return False

    (prev_hash, hashline, comment) = parsed["hash"]
    new_hash = compute_hash(parsed)

    if prev_hash == new_hash: return False

    if hashline == -1:  lines.insert(0, f"#@# {new_hash}\n")            # No hash found, add new
    else:               lines[hashline] = f"#@# {new_hash}{comment}\n"  # Update existing hash

    writef(lines)

    return True


#-------------------- REBUILD --------------------#
def needs_rebuild(parsed: Parsed | None = None) -> bool:
    if parsed is None: parsed = parse_annix()
    if parsed is None: return False
    return parsed["hash"][0] != compute_hash(parsed)

def nixos_rebuild(force=False) -> bool:
    if force or needs_rebuild():
        print("\033[93mRebuilding system...\033[0m")
        # proc = subprocess.Popen(REBUILD_COMMAND, stdout=subprocess.PIPE)
        # for c in iter(lambda: cast(IO[bytes], proc.stdout).read(1), b""):
        #     sys.stdout.buffer.write(c)

        # subprocess.run(REBUILD_COMMAND)

    else: print("\033[92mSystem up-to-date\033[0m")

    return update_hash()


#========================= COMMANDS =========================#

def annix_sync(force=False):
    nixos_rebuild(force)

def annix_search(query):
    if not query: return

    result = subprocess.run(["nix", "search", "--json", "nixpkgs", query], capture_output=True, text=True)
    pkgs = json.loads(result.stdout)

    if not pkgs:
        print("\033[91mNo packages found\033[0m")
    else:
        for pkg_data in pkgs.values():
            description = pkg_data.get("description", "").strip()
            termSize = shutil.get_terminal_size().columns - 6
            if termSize < MIN_WRAP_WIDTH: termSize = 1000 # No word wrapping

            title = "\n" + "\n  ".join(wrapAnsiLine("ᗌ {} @ {}", [
                (94, pkg_data["pname"]),
                (96, pkg_data["version"])
            ], termSize))

            print(title, end="")

            if not description: print()
            else: print(":\n    " + '\n    '.join(wrapLines(description, termSize)))

def annix_add(pkgs: list[str], skip_rebuild=False):
    if not pkgs: return
    pkgs = list(set(pkgs))

    #----- Get existing packages ----#
    if (lines := readf()) is None or (parsed := parse_annix(lines)) is None: return

    #----- Determine insertion point ----#
    # Look for #@+ marker
    insert_above, insert_idx = parsed["addhere"]
    
    if insert_idx == -1:   # Look for last package in the file
        last_pkg_line =         parsed['pkgs'][-1][1]       if parsed['pkgs']       else -1
        last_disabled_line =    parsed['disabled'][-1][1]   if parsed['disabled']   else -1
        insert_above, insert_idx =    False, max(last_pkg_line, last_disabled_line)

    if insert_idx == -1:   # Look for the closing bracket
        for (c, i) in parsed['code']:
            if c.startswith("]"):
                insert_above, insert_idx = True, i
                break
    
    if insert_idx == -1:   # Insert at EOF
        insert_above = True

    #----- Add packages ----#
    modified = False
    existing_pkg_names      = set([p for p, _, _ in parsed['pkgs']])
    existing, reenabled = set(), set()

    for pkg in pkgs:
        # Check if package is already enabled
        if pkg in existing_pkg_names: existing.add(pkg); continue

        # Check if package is disabled
        found = False
        for existing_pkg, line_no, comment in parsed['disabled']:
            if existing_pkg == pkg:
                lines[line_no] = f"  {pkg}{comment}\n"
                found, modified = True, True
                reenabled.add(pkg)
                break

        if found: continue

        # No existing package found, add new
        lines.insert(insert_idx + (0 if insert_above else 1), f"  {pkg}\n")
        modified = True

    if modified:
        writef(lines)
        if existing: print("{ " + ', '.join([f'\033[94m{p}\033[0m' for p in sorted(list(existing))]) + "} unchanged - already installed")
        if reenabled: print("{ " + ', '.join([f'\033[94m{p}\033[0m' for p in sorted(list(reenabled))]) + " } re-enabled")

        if not skip_rebuild: nixos_rebuild()
    else:
        print("\033[95mNo changes made - The specified packages were already installed\033[0m")


def annix_rm(pkgs: list[str], mask: PkgMask = PkgMask.ALL, delete = False, all_instances=False, skip_rebuild=False):
    if not pkgs: return
    pkgs = list(set(pkgs))

    if (lines := readf()) is None or (parsed := parse_annix(lines)) is None: return

    modified = False

    deadpool = []
    for pkg in pkgs:
        if mask in [PkgMask.ACTIVE, PkgMask.ALL]:
            for existing_pkg, line_no, comment in parsed['pkgs']:
                if pkg == existing_pkg:
                    if not delete:              lines[line_no] = f"  #- {pkg}{comment}\n"
                    elif comment != "":         lines[line_no] = f"  {comment.strip()}\n"
                    else:                       deadpool.append(line_no)
                    modified = True
                    if not all_instances: break

        if mask in [PkgMask.DISABLED, PkgMask.ALL] and delete:
            for existing_pkg, line_no, comment in parsed['disabled']:
                if pkg == existing_pkg:
                    if comment != "":       lines[line_no] = f"  {comment.strip()}\n"
                    else:                   deadpool.append(line_no)
                    modified = True
                    if not all_instances: break

    for line_no in sorted(deadpool, reverse=True): del lines[line_no]

    if modified:
        writef(lines)
        if not skip_rebuild: nixos_rebuild()
    else:
        print("\033[95mNo changes made - The specified packages were not installed\033[0m")


def annix_ls(as_json = False):
    if (parsed := parse_annix()) is None: return
    pkgs, disabled = parsed['pkgs'], parsed['disabled']

    if not pkgs and not disabled: print(f"No packages found in \033[93m{ANNIX_FILE}\033[0m"); return

    if as_json:
        print(json.dumps({"active": pkgs, "disabled": disabled}))
        return

    if pkgs:
        print("\n\033[92mActive\033[0m packages:")
        for (pkg, line_no, comment) in pkgs: print(f"    {pkg}")
    else: print("\nNo \033[92mactive\033[0m packages")

    if disabled:
        print("\n\033[95mDisabled\033[0m packages:")
        for (pkg, line_no, comment) in disabled: print(f"    {pkg}")
    else: print("\nNo \033[95mdisabled\033[0m packages")

def annix_clean():
    if (parsed := parse_annix(suppress_warn=True)) is None: return
    disabled = [p for p, _, _ in parsed["disabled"]]
    annix_rm(disabled, PkgMask.DISABLED, True, True, True)


def annix_save(name: str):
    name = "".join(name.strip().split())
    if not name:
        print("Usage: annix save <name>")
        return

    save_path = "/".join(ANNIX_FILE.split("/")[:-1])
    save_file = f"{save_path}/an_{name}.nix"
    if os.path.exists(save_file):
        print(f"'{save_file}' already exists, overwrite? [y/N] ")
        if input().lower() != "y": return

    if (content := readf()) is not None and writef(content, save_file):
        print(f"Configuration saved as an_{name}.nix")

def annix_help(parser: argparse.ArgumentParser):
    c_pre = "\033[93m"
    c_cmd = "\033[92m"
    c_arg = "\033[94m"
    c_rst = "\033[0m"
    prog = f"{c_pre}{parser.prog}{c_rst}"

    help_text = f"""
Usage: annix <command> [options]

{prog} {c_arg}[-f]{c_rst}: Update system packages to match {ANNIX_FILE_NAME}
{prog} {c_cmd}search{c_rst} {c_arg}<query>{c_rst}: Search for packages in nixpkgs
{prog} {c_cmd}add{c_rst} {c_arg}<pkg1> <pkg2> ... <pkgN>{c_rst}: Add packages
{prog} {c_cmd}rm{c_rst} {c_arg}<pkg1> <pkg2> ... <pkgN>{c_rst}: Remove packages
{prog} {c_cmd}ls{c_rst}: List installed packages
{prog} {c_cmd}clean{c_rst}: Remove disabled packages
{prog} {c_cmd}save{c_rst} {c_arg}<name>{c_rst}: Backup current configuration
{prog} {c_cmd}help{c_rst}: Show this help message
"""
    print(help_text)

def main():
    #---------- Define parser ----------#
    parser = argparse.ArgumentParser(description="annix: Dead simple package management for your Nix config", add_help=False)
    parser.add_argument("-f", action="store_true", help="Force")

    subparsers = parser.add_subparsers(dest="command")

    parser_sync = subparsers.add_parser("sync", help="Update system packages to match an.nix")
    parser_sync.add_argument("-f", "--force", action="store_true", help="Force")

    parser_search = subparsers.add_parser("search", help="Search for packages in nixpkgs")
    parser_search.add_argument("query", nargs="+", help="Query string for searching packages")

    parser_add = subparsers.add_parser("add", help="Add packages")
    parser_add.add_argument("packages", nargs="+", help="Packages to add")
    parser_add.add_argument("-s", "--skip-rebuild", action="store_true", help="Skip system rebuild")

    parser_rm = subparsers.add_parser("rm", help="Remove packages")
    parser_rm.add_argument("packages", nargs="+", help="Packages to remove")
    parser_rm.add_argument("-d", "--delete", action="store_true", help="Delete entry instead of disabling")
    parser_rm.add_argument("-a", "--all", action="store_true", help="Remove all instances if there's duplicates")
    parser_rm.add_argument("-s", "--skip-rebuild", action="store_true", help="Skip system rebuild")

    parser_ls = subparsers.add_parser("ls", help="List installed packages")
    parser_ls.add_argument("--json", action="store_true", help="Print as JSON")

    subparsers.add_parser("clean", help=f"Remove disabled packages from {ANNIX_FILE_NAME}")

    parser_save = subparsers.add_parser("save", help="Save current configuration")
    parser_save.add_argument("name", nargs="?", default="", help="Name for the saved configuration")

    subparsers.add_parser("help", help="Show this help message")

    argcomplete.autocomplete(parser) # Enable bash autocomplete
    args = parser.parse_args()

    #---------- Handle commands ----------#
    match args.command:
        case "sync":            annix_sync(args.force)
        case "search":          annix_search(" ".join(args.query))
        case "add":             annix_add(args.packages, args.skip_rebuild)
        case "rm":              annix_rm(args.packages, PkgMask.ALL, args.delete, args.all, args.skip_rebuild)
        case "ls":              annix_ls(args.json)
        case "clean":           annix_clean()
        case "save":            annix_save(args.name)
        case "help":            annix_help(parser)
        case _:
            if args.f:          annix_sync(True)
            else:               error("Arg", f"Unknown command - Use `{parser.prog} help` for available commands")

if __name__ == "__main__":
    main()
