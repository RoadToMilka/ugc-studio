"""Module Renommer (V4, lot 2) : le masque d'Ant Renamer, l'ordre, les noms permis par Windows, le
renommage en deux temps avec retour en arrière, et « Annuler le dernier renommage »."""

import os
from pathlib import Path

import pytest
from PIL import Image

from ugc_studio import renommage
from ugc_studio.renommage import (
    DATE_MODIFICATION,
    DATE_PRISE_DE_VUE,
    NOM,
    ContenuDuDossier,
    ImageDuDossier,
    JournalDesRenommages,
    Numerotation,
    Renommage,
    RenommageImpossible,
    analyser_le_masque,
    annuler,
    appliquer_le_masque,
    cle_windows,
    lire_le_dossier,
    masques_recents,
    ordre_final,
    planifier,
    probleme_du_nom,
    renommer,
    trier,
)


def _contenu(dossier: Path, noms, autres=()) -> ContenuDuDossier:
    return ContenuDuDossier(dossier, tuple(ImageDuDossier(dossier / nom, 0.0) for nom in noms), frozenset(autres))


def _creer(dossier: Path, noms) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    for nom in noms:
        (dossier / nom).write_bytes(nom.encode("utf-8"))  # le contenu suit le fichier : on le reconnaît


def _contenus(dossier: Path) -> dict[str, str]:
    return {f.name: f.read_bytes().decode("utf-8") for f in dossier.iterdir() if f.is_file()}


# --- Le masque ---------------------------------------------------------------------------------


def test_numerotation_comme_ant_renamer():
    deux = Numerotation(depart=1, chiffres=2, pas=1)
    assert [deux.numero(rang) for rang in (0, 1, 8, 98, 99)] == ["01", "02", "09", "99", "100"]
    assert [Numerotation(0, 3, 5).numero(rang) for rang in range(3)] == ["000", "005", "010"]
    assert Numerotation(7, 1, 1).numero(0) == "7"


def test_le_masque_de_l_utilisateur():
    chemin = Path("C:/Boutique/NeMu/Photos/IMG_0042.JPG")
    assert appliquer_le_masque("NeMu_JPG_%num%%ext%", chemin, "01") == "NeMu_JPG_01.JPG"
    assert appliquer_le_masque("%name%_%num%%ext%", chemin, "07") == "IMG_0042_07.JPG"
    assert appliquer_le_masque("%folder1%-%folder2%_%num%%ext%", chemin, "03") == "Photos-NeMu_03.JPG"
    assert appliquer_le_masque("100%%_%NUM%%Ext%", chemin, "12") == "100%_12.JPG"  # %% et majuscules
    assert appliquer_le_masque("100%_promo_%num%", chemin, "01") == "100%_promo_01"  # un « % » seul reste
    assert appliquer_le_masque("%date%_%num%", chemin, "01") == "%date%_01"  # balise inconnue : telle quelle
    assert appliquer_le_masque("%folder9%%num%", chemin, "01") == "01"  # au-delà du disque : rien
    assert appliquer_le_masque("archive_%num%%ext%", Path("a/b.tar.gz"), "1") == "archive_1.gz"


def test_analyse_du_masque():
    analyse = analyser_le_masque("NeMu_%folder2%_%num%_%date%%ext%")
    assert (analyse.avec_numero, analyse.avec_extension) == (True, True)
    assert analyse.inconnues == ("%date%",) and analyse.niveaux == (2,)
    assert not analyser_le_masque("photo%ext%").avec_numero
    assert analyser_le_masque("%folder0%_%num%").inconnues == ("%folder0%",)


def test_masques_recents():
    assert masques_recents(["b", "a", "c"], "a") == ["a", "b", "c"]
    assert len(masques_recents([f"m{i}" for i in range(30)], "nouveau")) == renommage.MASQUES_RECENTS_MAX
    assert masques_recents(["", None, "x"], "y") == ["y", "x"]


# --- Les noms permis par Windows ---------------------------------------------------------------


def test_noms_refuses_par_windows():
    assert probleme_du_nom("NeMu_JPG_01.jpg") == ""
    assert probleme_du_nom("") == "Nom vide."
    assert probleme_du_nom("photo?.jpg") == "Caractère interdit par Windows : ?"
    assert probleme_du_nom('a<b>:c".jpg') == 'Caractère interdit par Windows : < > : "'
    assert probleme_du_nom("photo\t1.jpg") == "Caractère interdit par Windows : (invisible)"
    assert probleme_du_nom("photo.") == probleme_du_nom("photo ") == "Un nom ne peut pas finir par un espace ou un point."
    for reserve in ("CON", "con.jpg", "Nul.tar.gz", "COM1.png", "lpt9.jpg", "COM¹.jpg", "AUX .jpg"):
        assert probleme_du_nom(reserve).endswith("est un nom réservé par Windows."), reserve
    for permis in ("CONSOLE.jpg", "COM10.jpg", "nul_01.jpg", "LPT.jpg"):
        assert probleme_du_nom(permis) == "", permis
    assert probleme_du_nom("a" * 252 + ".jpg") == "Nom trop long (255 caractères au plus)."


def test_majuscules_et_minuscules_sont_le_meme_nom():
    assert cle_windows("Photo.JPG") == cle_windows("photo.jpg")
    assert cle_windows("straße.jpg") != cle_windows("strasse.jpg")  # comme Windows


# --- L'ordre -----------------------------------------------------------------------------------


def test_images_cliquees_d_abord_puis_l_ordre_de_l_affichage():
    a, b, c, d = (Path(f"{nom}.jpg") for nom in "abcd")
    assert ordre_final([a, b, c, d], [c, a]) == [(c, True), (a, True), (b, False), (d, False)]
    assert ordre_final([a, b], []) == [(a, False), (b, False)]


def test_tri_par_date():
    images = [ImageDuDossier(Path("a.jpg"), 300.0, 100.0), ImageDuDossier(Path("b.jpg"), 100.0, None), ImageDuDossier(Path("c.jpg"), 200.0, 50.0)]
    assert [i.chemin.name for i in trier(images, NOM)] == ["a.jpg", "b.jpg", "c.jpg"]
    assert [i.chemin.name for i in trier(images, DATE_MODIFICATION)] == ["b.jpg", "c.jpg", "a.jpg"]
    # Sans date de prise de vue (b), celle de modification.
    assert [i.chemin.name for i in trier(images, DATE_PRISE_DE_VUE)] == ["c.jpg", "a.jpg", "b.jpg"]


# --- Le plan -----------------------------------------------------------------------------------


def test_plan_du_masque_de_l_utilisateur(tmp_path):
    contenu = _contenu(tmp_path, ["IMG_1.jpg", "IMG_2.png", "IMG_10.webp"])
    a, b, c = (image.chemin for image in contenu.images)
    plan = planifier(contenu, ordre_final([a, b, c], [c, a]), "NeMu_JPG_%num%%ext%", Numerotation())
    assert [(ligne.chemin.name, ligne.numero, ligne.choisie, ligne.nouveau) for ligne in plan.lignes] == [
        ("IMG_10.webp", "01", True, "NeMu_JPG_01.webp"),
        ("IMG_1.jpg", "02", True, "NeMu_JPG_02.jpg"),
        ("IMG_2.png", "03", False, "NeMu_JPG_03.png"),
    ]
    assert plan.possible and not plan.alertes
    assert plan.resume() == "3 images : de « NeMu_JPG_01.webp » à « NeMu_JPG_03.png »."
    assert plan.changements() == [("IMG_10.webp", "NeMu_JPG_01.webp"), ("IMG_1.jpg", "NeMu_JPG_02.jpg"), ("IMG_2.png", "NeMu_JPG_03.png")]


def test_masque_vide_ou_sans_numero(tmp_path):
    contenu = _contenu(tmp_path, ["a.jpg"])
    ordre = ordre_final([contenu.images[0].chemin], [])
    vide = planifier(contenu, ordre, "", Numerotation())
    assert vide.erreur.startswith("Écris le masque") and not vide.possible and not vide.lignes
    sans_numero = planifier(contenu, ordre, "photo%ext%", Numerotation())
    assert sans_numero.erreur.startswith("Le masque doit contenir %num%") and sans_numero.resume() == sans_numero.erreur


def test_noms_impossibles_et_noms_deja_pris(tmp_path):
    contenu = _contenu(tmp_path, ["a.jpg", "b.jpg"], autres=["02", "notes.txt"])
    ordre = ordre_final([image.chemin for image in contenu.images], [])
    # « LPT9 » est réservé (« LPT10 », non) ; « 02 » est déjà pris par un sous-dossier, qui n'est pas renommé.
    plan = planifier(contenu, ordre, "LPT%num%", Numerotation(9, 1, 1))
    assert [ligne.probleme for ligne in plan.lignes] == ["« LPT9 » est un nom réservé par Windows.", ""]
    plan = planifier(contenu, ordre, "%num%", Numerotation(1, 2, 1))
    assert plan.lignes[1].probleme == "Nom déjà pris par un autre fichier du dossier (qui n'est pas renommé)."
    assert not plan.possible
    assert plan.resume() == "1 image a un nom impossible (en rouge) : rien n'est renommé tant que c'est le cas."


def test_deux_images_au_meme_nom(tmp_path):
    contenu = _contenu(tmp_path, ["a.jpg", "b.JPG"])
    ordre = ordre_final([image.chemin for image in contenu.images], [])
    # Avec %num%, deux images n'ont jamais le même numéro ; un pas de 0 (impossible dans l'app) le
    # force, pour vérifier le contrôle : « photo_01.jpg » et « photo_01.JPG », le même nom pour Windows.
    plan = planifier(contenu, ordre, "photo_%num%%ext%", Numerotation(1, 2, 0))
    assert [ligne.probleme for ligne in plan.lignes] == ["Même nom que l'image n° 01."] * 2
    assert not plan.possible


def test_alertes_en_orange(tmp_path):
    contenu = _contenu(tmp_path, ["a.jpg", "b.png"])
    ordre = ordre_final([image.chemin for image in contenu.images], [])
    sans_extension = planifier(contenu, ordre, "NeMu_%num%", Numerotation())
    assert sans_extension.possible  # permis, mais signalé
    assert sans_extension.alertes == [
        "2 images sans extension (.jpg…) : Windows ne saura plus avec quelle app les ouvrir. Ajoute %ext% à la fin du masque."
    ]
    assert sans_extension.lignes[0].avertissement == "Sans extension : Windows ne saura plus avec quelle app l'ouvrir."
    jpg_force = planifier(contenu, ordre, "NeMu_%num%.jpg", Numerotation())
    assert [ligne.avertissement for ligne in jpg_force.lignes] == ["", "Extension changée (.png devient .jpg) : l'image risque de ne plus s'ouvrir."]
    assert jpg_force.alertes == ["1 image change d'extension : elle risque de ne plus s'ouvrir. Utilise plutôt %ext%."]
    autres = planifier(contenu, ordre, "%date%_%folder30%_%num%%ext%", Numerotation())
    assert autres.alertes == [
        "%date% n'est pas une balise : écrit tel quel dans les noms.",
        "%folder30% : pas de dossier à ce niveau, remplacé par rien.",
    ]


def test_images_qui_ont_deja_leur_nom(tmp_path):
    contenu = _contenu(tmp_path, ["photo_01.jpg", "photo_02.jpg", "zzz.jpg"])
    ordre = ordre_final([image.chemin for image in contenu.images], [])
    plan = planifier(contenu, ordre, "photo_%num%%ext%", Numerotation())
    assert [ligne.inchangee for ligne in plan.lignes] == [True, True, False]
    assert plan.resume() == "3 images : de « photo_01.jpg » à « photo_03.jpg » (2 gardent leur nom)."
    assert plan.changements() == [("zzz.jpg", "photo_03.jpg")]
    deja = planifier(_contenu(tmp_path, ["photo_01.jpg"]), ordre_final([tmp_path / "photo_01.jpg"], []), "photo_%num%%ext%", Numerotation())
    assert not deja.possible and deja.resume() == "1 image : elle a déjà ces noms."


# --- Le renommage ------------------------------------------------------------------------------


def test_renommer_en_deux_temps_meme_en_echangeant_les_noms(tmp_path):
    _creer(tmp_path, ["1.jpg", "2.jpg", "3.jpg"])
    # 1 → 2, 2 → 3, 3 → 1 : chaque nouveau nom est encore pris au début.
    assert renommer(tmp_path, [("1.jpg", "2.jpg"), ("2.jpg", "3.jpg"), ("3.jpg", "1.jpg")]) == 3
    assert _contenus(tmp_path) == {"2.jpg": "1.jpg", "3.jpg": "2.jpg", "1.jpg": "3.jpg"}
    assert not [f for f in tmp_path.iterdir() if f.name.startswith(renommage.PREFIXE_PROVISOIRE)]


def test_majuscules_seulement(tmp_path):
    _creer(tmp_path, ["Photo.JPG"])
    assert renommer(tmp_path, [("Photo.JPG", "photo.jpg"), ("x.jpg", "x.jpg")]) == 1  # un nom inchangé est ignoré
    assert [f.name for f in tmp_path.iterdir()] == ["photo.jpg"]


def test_rien_ne_change_si_un_nom_est_pris_ou_un_fichier_a_disparu(tmp_path):
    _creer(tmp_path, ["a.jpg", "b.jpg", "pris.jpg"])
    avant = _contenus(tmp_path)
    with pytest.raises(RenommageImpossible):
        renommer(tmp_path, [("a.jpg", "x.jpg"), ("b.jpg", "pris.jpg")])
    try:
        renommer(tmp_path, [("a.jpg", "x.jpg"), ("b.jpg", "pris.jpg")])
    except RenommageImpossible as erreur:
        assert str(erreur) == "« pris.jpg » : ce nom est déjà pris dans le dossier. Rien n'a changé." and erreur.definitif
    try:
        renommer(tmp_path, [("a.jpg", "x.jpg"), ("disparu.jpg", "y.jpg")])
    except RenommageImpossible as erreur:
        assert str(erreur) == "« disparu.jpg » n'est plus dans le dossier. Rien n'a changé." and erreur.definitif
    assert _contenus(tmp_path) == avant


def _bloquer(monkeypatch, nom_bloque: str, temps: int):
    """Simule un fichier bloqué, une fois, comme le fait Windows (PermissionError) : au 1er temps, le
    fichier `nom_bloque` est ouvert dans une autre app ; au 2e temps, le passage du nom provisoire au
    nom final `nom_bloque` est refusé (un antivirus qui examine le fichier, par exemple)."""
    vrai = os.rename
    bloque = [True]

    def rename(source, cible):
        source, cible = Path(source), Path(cible)
        nom = source.name if temps == 1 else cible.name
        if bloque[0] and nom == nom_bloque:
            bloque[0] = False
            raise PermissionError(13, "Le processus ne peut pas accéder au fichier", str(source))
        vrai(source, cible)

    monkeypatch.setattr(renommage.os, "rename", rename)


def test_fichier_bloque_au_premier_temps(tmp_path, monkeypatch):
    _creer(tmp_path, ["1.jpg", "2.jpg", "3.jpg"])
    avant = _contenus(tmp_path)
    _bloquer(monkeypatch, "3.jpg", temps=1)
    try:
        renommer(tmp_path, [("1.jpg", "2.jpg"), ("2.jpg", "3.jpg"), ("3.jpg", "1.jpg")])
        raise AssertionError("RenommageImpossible attendue")
    except RenommageImpossible as erreur:
        assert str(erreur) == "« 3.jpg » est ouvert dans une autre app, ou protégé : ferme-la puis réessaie. Rien n'a changé."
        assert not erreur.definitif  # réessayer plus tard peut marcher
    assert _contenus(tmp_path) == avant


def test_fichier_bloque_au_second_temps(tmp_path, monkeypatch):
    _creer(tmp_path, ["1.jpg", "2.jpg", "3.jpg"])
    avant = _contenus(tmp_path)
    _bloquer(monkeypatch, "1.jpg", temps=2)  # le 3e changement (3 → 1) échoue, après 1 → 2 et 2 → 3
    try:
        renommer(tmp_path, [("1.jpg", "2.jpg"), ("2.jpg", "3.jpg"), ("3.jpg", "1.jpg")])
        raise AssertionError("RenommageImpossible attendue")
    except RenommageImpossible as erreur:
        assert str(erreur).startswith("« 3.jpg » est ouvert dans une autre app") and str(erreur).endswith("Rien n'a changé.")
    assert _contenus(tmp_path) == avant  # tout est revenu comme avant


# --- Le dossier ----------------------------------------------------------------------------------


def test_lire_le_dossier(tmp_path):
    exif = Image.Exif()
    exif.get_ifd(0x8769)[0x9003] = "2025:06:01 10:30:00"
    Image.new("RGB", (8, 8)).save(tmp_path / "photo10.jpg", exif=exif.tobytes())
    Image.new("RGB", (8, 8)).save(tmp_path / "photo2.png")
    (tmp_path / "notes.txt").write_text("pas une image", encoding="utf-8")
    (tmp_path / "Sous-dossier").mkdir()
    (tmp_path / "Sous-dossier" / "cachee.jpg").write_bytes(b"")
    (tmp_path / "Thumbs.db").write_bytes(b"")
    contenu = lire_le_dossier(tmp_path)
    assert [image.chemin.name for image in contenu.images] == ["photo2.png", "photo10.jpg"]  # ordre de l'Explorateur
    assert contenu.images[0].prise_de_vue is None and contenu.images[1].prise_de_vue is not None
    assert contenu.autres_noms == {"notes.txt", "Sous-dossier", "Thumbs.db"}


# --- Le journal et « Annuler » -------------------------------------------------------------------


def test_annuler_le_dernier_renommage(tmp_path):
    dossier = tmp_path / "Produits"
    _creer(dossier, ["IMG_1.jpg", "IMG_2.jpg"])
    journal = JournalDesRenommages(tmp_path / "donnees" / "renommages.json")
    assert journal.dernier() is None
    changements = (("IMG_1.jpg", "NeMu_02.jpg"), ("IMG_2.jpg", "NeMu_01.jpg"))
    renommer(dossier, changements)
    fait = Renommage(dossier, "2026-10-04T19:42:00", changements)
    journal.ajouter(fait)
    assert journal.dernier() == fait
    assert annuler(journal.dernier()) == 2
    journal.retirer(fait)
    assert _contenus(dossier) == {"IMG_1.jpg": "IMG_1.jpg", "IMG_2.jpg": "IMG_2.jpg"}
    assert journal.dernier() is None


def test_journal_limite_et_fichier_abime(tmp_path):
    chemin = tmp_path / "renommages.json"
    journal = JournalDesRenommages(chemin)
    for numero in range(renommage.RENOMMAGES_GARDES + 5):
        journal.ajouter(Renommage(tmp_path, f"2026-10-04T10:{numero:02d}:00", (("a.jpg", f"{numero}.jpg"),)))
    liste = journal.renommages()
    assert len(liste) == renommage.RENOMMAGES_GARDES and liste[0].date == "2026-10-04T10:24:00"  # le plus récent d'abord
    chemin.write_text("{abîmé", encoding="utf-8")
    assert journal.renommages() == []  # mis de côté, l'app repart d'une liste vide


def test_annuler_impossible_si_un_fichier_a_disparu(tmp_path):
    _creer(tmp_path, ["NeMu_01.jpg"])
    fait = Renommage(tmp_path, "2026-10-04T19:42:00", (("a.jpg", "NeMu_01.jpg"), ("b.jpg", "NeMu_02.jpg")))
    try:
        annuler(fait)
        raise AssertionError("RenommageImpossible attendue")
    except RenommageImpossible as erreur:
        assert erreur.definitif and str(erreur) == "« NeMu_02.jpg » n'est plus dans le dossier. Rien n'a changé."
    assert _contenus(tmp_path) == {"NeMu_01.jpg": "NeMu_01.jpg"}
