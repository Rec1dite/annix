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
# Lines ending with "#@" are non-package code lines
{ pkgs, ... }: with pkgs; [ #@
  (annix ...) #@

  # Unmarked lines represent active packages
  alacritty
  bottom
  cava

  # New packages will be appended after the "#@+" marker
  #@+
] #@
```

2. **Register `an.nix`** with your dotfiles source control
```bash
$ git add an.nix
```

3. **Import `an.nix`** in your `configuration.nix`
```nix
environment.systemPackages = (import ./an.nix nixpkgs) ++ (with pkgs; [ /* non-annix-managed packages here */ ]);
```

4. **Apply the changes**
```bash
$ sudo nixos-rebuild switch
```

---

## Syntax

The `an.nix` file uses a few special markers and symbols to control how `annix` interprets the package list.
All `annix` state is maintained in this file, so everything is fully transparent.
You may alter the file directly and even use it as a regular `.nix` file provided the following conventions are observed:

- **`<package>`**: Unmarked and uncommented lines in `an.nix` are names of **installed packages**. These are standard package names from [nixpkgs](https://search.nixos.org/packages).

- **`#@# <hash>`**: This is the md5 **hash of the package list and code** in `an.nix` - it is calculated and updated by `annix` after each rebuild to mark the current state of the system. It should not be manually altered.
  
- **`#@`**: Lines ending with `#@` indicate arbitrary **Nix code lines**. You can add arbitrary Nix code to the `an.nix` file, provided all non-package and non-comment lines end with this marker.

- **`#- `**: A line starting with `#- ` marks a **disabled package**. `annix rm` 'disables' packages by default instead of deleting them from the file, such that they are still available for future reference. They can be manually removed or wiped via `annix clean`.

- **`#@+`**/**`#@+^`**: Lines ending with `#@+` are **ignored by `annix`** and can be used for notes or documentation within `an.nix`.

- **`#`**: Any line starting with a single `#` are treated as **comments** and ignored by `annix`. These can be used freely for notes or documentation within `an.nix`. They may also appear at the end of active and disabled package lines.

## TODO
- [ ] `annix sort` -> Sorts the configuration file entries according to various criteria
- [ ] `annix try` -> Install temporarily; removes after a predefined duration
- [ ] Tagged `#@+` markers for different package categories
- [ ] Neater line parsing with regex and capture groups
- [ ] Profile switching between different an.nix files
- [ ] Add multiline code block markers
- [ ] Package version handling
- [ ] Package name validation
- [ ] Better tab completion