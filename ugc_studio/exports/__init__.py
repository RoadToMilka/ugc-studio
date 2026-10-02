"""Exports vidéo (V3, cahier des charges §8) : le calque transparent (lot 1), puis la vidéo avec ses
sous-titres incrustés (lot 2) et le HDR (lot 3).

Le principe : les sous-titres sont dessinés par le moteur de l'aperçu (rendu/moteur.py), une image
par moment de la vidéo, puis confiés à FFmpeg, le programme qui écrit les fichiers vidéo. FFmpeg est
intégré au .exe (version GPL 9.0.2 « essentials » de gyan.dev) : rien à installer.

- cadence.py : fréquences d'images exactes (29,97 = 30 000 / 1 001) et moment de chaque image ;
- ffmpeg.py : où trouver FFmpeg, les commandes données à FFmpeg, le suivi de son travail ;
- plan.py : ce qui sera exporté (source, réglages, nom, dossier, résumé avant export) ;
- calque.py : les images du calque, dessinées par le moteur de l'aperçu (Qt).

Tout, sauf calque.py, se teste sans interface.
"""
