{ pkgs }: {
  deps = [
    # Python — Replit peut avoir 3.12 ou 3.13 selon le canal Nix
    # stable-23_11 → python312 | plus récent → python313
    # Si python312 absent, décommenter python313
    pkgs.python312
    # pkgs.python313  # ← décommenter si "attribute 'python312' missing"
    pkgs.cmake
    pkgs.ninja
    pkgs.gcc
    pkgs.openssl
    # pkgs.liboqs — absent de nixpkgs stable-23_11
    # liboqs est compilé automatiquement au démarrage par replit_start.sh si cmake est disponible
    pkgs.curl
    pkgs.git
  ];
}
