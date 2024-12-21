{ pkgs, ... }: [
  (pkgs.python3.withPackages (pyPkgs: with pyPkgs; [
    argcomplete
    pip
    jupyter
    notebook
  ]))
]