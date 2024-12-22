# annix
**Dead simple package management for your NixOS config**

<br />

> `annix` provides a straightforward wrapper interface for your NixOS system config that feels like a traditional imperative package manager.
> By maintaining an `an.nix` file to track package installations, `annix` enables you to quickly add, remove, list, and search packages, while ensuring that system changes are properly applied via `nixos-rebuild switch`.

---

## Usage
```
Usage: annix <command> [options]

annix [-f]: Update system packages to match an.nix
annix search <query>: Search for packages in nixpkgs
annix add <pkg1> <pkg2> ... <pkgN>: Add packages
annix rm <pkg1> <pkg2> ... <pkgN>: Remove packages
annix ls: List installed packages
annix clean: Remove disabled packages
annix save <name>: Backup current configuration
annix help: Show this help message
```

---


## Setup

### Try it
```bash
nix run github:rec1dite/annix -- help
```

### Install
1. **Add the following `an.nix` file** to your system configuration (typically `/etc/nixos`)
```nix
# Basic an.nix template
#@# A_HASH_WILL_BE_AUTO_GENERATED_HERE
# Lines ending with "#@" are 'code' lines
{ pkgs, upkgs, ... }: { environment.systemPackages = with pkgs; [      #@
  (import (fetchFromGitHub {                                           #@
    owner = "rec1dite"; repo = "annix"; rev = "master";                #@
    hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";      #@
  }) { inherit pkgs; configs = { ANNIX_FILE = "/path/to/an.nix"; }; }) #@

  # Unmarked lines represent active packages
  alacritty
  bottom
  cava

  # Disabled packages are marked with "#-"
  #- dmenu

  # New packages will be appended after the "#@+" marker
  #@+
]; } #@
```

2. **Import the `an.nix` file** as a module in your `configuration.nix`
```nix
{ lib, pkgs, ... }@inputs:
{
  imports = [ ./an.nix /* ... other modules ... */ ];

  # ...
}
```

3. **Register `an.nix`** with your dotfiles source control
```bash
$ git add an.nix
```

4. **Update the current commit hash** by running the following, then copying the expected hash to the `sha256-...` field above
```bash
$ sudo nixos-rebuild switch
```

5. **Override the `ANNIX_FILE` config** at the top of the `an.nix` file if it is different from the default `/etc/nixos/an.nix`.

6. **Apply the changes** by rerunning the `sudo nixos-rebuild switch` command

7. **Use `annix`** to manage your packages
```bash
$ annix add firefox
$ annix ls
```

---

## Syntax

The `an.nix` file uses a few special markers and symbols to control how `annix` interprets the package list.
All `annix` state is maintained in this file, so everything is fully transparent.
You may alter the file directly and even use it as a regular `.nix` file provided the following conventions are observed:

- **`<package>`**: Unmarked and uncommented lines in `an.nix` are interpreted as names of **installed packages**. These are standard package names from [nixpkgs](https://search.nixos.org/packages).

- **`#@# <hash>`**: This is the md5 **hash of the package list and code** in `an.nix` - it is calculated and updated by `annix` after each rebuild to mark the current state of the system. It should not be manually altered.
  
- **`#@`**: Lines ending with `#@` indicate **Nix code lines**. You can add arbitrary Nix code to the `an.nix` file, provided all non-package and non-comment lines end with this marker.

- **`#-`**: A line starting with `#-` marks a **disabled package**. `annix rm` 'disables' packages by default instead of deleting them from the file, such that they are still available for future reference. They can be manually removed or wiped via `annix clean`.

- **`#@+`**/**`#@+^`**: A single line in the `an.nix` file should contain an **addhere marker**. This determines the line at which new packages are appended after `annix add`. The `^` variant prepends packages above the marker.

- **`#`**: Any line starting with a single `#` are treated as **comments** and ignored by `annix`. These can be used freely for notes or documentation within `an.nix`. They may also appear at the end of active and disabled package lines.

## TODO
- [ ] `annix sort` -> Sorts the configuration file entries according to various criteria
- [ ] `annix try` -> Install temporarily; removes after a predefined duration
- [ ] Indent at same level as `#@+` marker when adding new packages
- [ ] Tagged `#@+` markers for different package categories
- [ ] Neater line parsing with regex and capture groups
- [ ] Profile switching between different an.nix files
- [ ] Add multiline code block markers
- [ ] Switch to pager for long output
- [ ] Package version handling
- [ ] Package name validation
- [ ] Better tab completion