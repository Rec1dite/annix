{
  description = "Dead simple package management for your NixOS config";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        overlays = [];
        pkgs = import nixpkgs { inherit system overlays; };
        deps = [ (pkgs.python312.withPackages (pyPkgs: with pyPkgs; [ argcomplete pip jupyter notebook ])) ];
        version = "v1.0.0";
      in
      rec {
        packages = rec {
          annix = pkgs.stdenv.mkDerivation {
            name = "annix";
            inherit version;

            nativeBuildInputs = [ pkgs.installShellFiles ];
            propagatedBuildInputs = deps;

            ANNIX_FILE = "/etc/nixos/an.nix";

            dontUnpack = true;
            installPhase = ''
              install -Dm755 ${./annix.py} $out/bin/annix
              installShellCompletion --bash --name annix.bash <(register-python-argcomplete annix)
              installShellCompletion --zsh  --name annix.zsh <(register-python-argcomplete annix)
            '';
          };
          default = annix;
        };

        apps = rec {
          annix = {
            type = "app";
            program = "${packages.annix}/bin/annix";
          };
          default = annix;
        };

        devShells = rec {
          default = pkgs.mkShell {
            packages = deps ++ [ packages.annix ];
            shellHook = "";
          };
        };


      }
    );
}
