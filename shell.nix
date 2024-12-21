{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  packages = [ (import ./. { inherit pkgs; }) ];
  shellHook = "";
}