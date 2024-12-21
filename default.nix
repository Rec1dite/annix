# nixpkgs = fetchTarball "https://github.com/NixOS/nixpkgs/tarball/nixos-24.05";
{
  pkgs ? import <nixpkgs> {},
  configs ? {},
  ... 
}:

pkgs.stdenv.mkDerivation {

  name = "annix";
  version = "v1.0.0";

  nativeBuildInputs = [ pkgs.installShellFiles ];
  propagatedBuildInputs = import ./deps.nix { inherit pkgs; };

  dontUnpack = true;
  installPhase = let
    configFile = pkgs.writeText "config.json" (builtins.toJSON configs);
  in ''
    install -Dm755 ${./annix.py} $out/bin/annix
    install -Dm644 ${configFile} $out/bin/config.json

    installShellCompletion --bash --name annix.bash <(register-python-argcomplete annix)
    installShellCompletion --zsh  --name annix.zsh <(register-python-argcomplete annix)
  '';

}
