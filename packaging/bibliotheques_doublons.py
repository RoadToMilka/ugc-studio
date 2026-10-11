"""Pour la recette du .exe seulement (packaging/ugc_studio.spec), jamais lancé : PyInstaller analyse ce
fichier pour connaître les modules de Python dont numpy et ONNX Runtime ont besoin. Les deux
bibliothèques voyagent à part dans le .exe (ugc_studio/doublons/bibliotheques.py) ; ces modules de
Python, eux, doivent être avec l'app."""

import numpy  # noqa: F401
import onnxruntime  # noqa: F401
