# nixpkgs = fetchTarball "https://github.com/NixOS/nixpkgs/tarball/nixos-24.05";
{
  pkgs ? import <nixpkgs> {},
  annixFile ? "/etc/nixos/an.nix",
  ...
}:
pkgs.stdenv.mkDerivation {

  name = "annix";
  version = "v1.0.0";

  nativeBuildInputs = [ pkgs.installShellFiles ];
  propagatedBuildInputs = import ./deps.nix { inherit pkgs; };

  ANNIX_FILE = annixFile;

  dontUnpack = true;
  installPhase = ''
    install -Dm755 ${./annix.py} $out/bin/annix
    installShellCompletion --bash --name annix.bash <(register-python-argcomplete annix)
    installShellCompletion --zsh  --name annix.zsh <(register-python-argcomplete annix)
  '';

}
