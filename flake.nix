{
  description = "Dead simple package management for your NixOS config";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in
      rec {
        packages = rec {
          annix = import ./default.nix { inherit pkgs; };
          default = annix;
        };

        devShells = rec {
          default = import ./shell.nix { inherit pkgs; };
        };
      }
    );
}
