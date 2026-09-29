"""Point d'entrée du .exe : c'est ce fichier que PyInstaller transforme en application Windows."""

from ugc_studio.app import main

if __name__ == "__main__":
    raise SystemExit(main())
