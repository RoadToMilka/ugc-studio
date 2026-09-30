"""Extraction de la piste son d'une source (§6.2) : conversions des échantillons, fin du décodage."""

from array import array

from ugc_studio.audio import lire_wav, wav_depuis_pcm
from ugc_studio.ui.extraction import ExtracteurAudio, _en_entiers_16_bits, wav_16_bits_court


class FauxDecodeur:
    """Imite le décodeur de Qt sous Windows : stop() signale « fini » immédiatement, pendant
    que l'extracteur est encore en train de le libérer."""

    def __init__(self, extracteur: ExtracteurAudio):
        self.extracteur = extracteur
        self.arrete = False

    def bufferAvailable(self) -> bool:  # noqa: N802 — nom imposé par Qt
        return False

    def duration(self) -> int:
        return 1000

    def blockSignals(self, _bloquer: bool) -> bool:  # noqa: N802
        return False

    def stop(self) -> None:
        self.arrete = True
        self.extracteur._decodage_fini()

    def deleteLater(self) -> None:  # noqa: N802
        pass


def test_fin_signalee_pendant_l_arret_du_decodeur(qtbot):
    extracteur = ExtracteurAudio()
    recus: list[bytes] = []
    extracteur.termine.connect(recus.append)
    decodeur = FauxDecodeur(extracteur)
    extracteur._decodeur, extracteur._fini = decodeur, False
    extracteur._pcm = bytearray(b"\x01\x00" * 1600)
    extracteur._decodage_fini()  # ne doit ni planter, ni envoyer le résultat deux fois
    assert decodeur.arrete and len(recus) == 1
    pcm, frequence, canaux = lire_wav(recus[0])
    assert (len(pcm), frequence, canaux) == (3200, 16_000, 1)
    extracteur.annuler()  # rien à libérer : sans effet


def test_conversion_en_entiers_16_bits():
    assert _en_entiers_16_bits(b"\x01\x02", "Int16") == b"\x01\x02"
    flottants = array("f", [0.5, -1.0]).tobytes()
    assert array("h", _en_entiers_16_bits(flottants, "Float")).tolist() == [16383, -32767]
    entiers = array("i", [100 << 16, -(100 << 16)]).tobytes()
    assert array("h", _en_entiers_16_bits(entiers, "Int32")).tolist() == [100, -100]
    assert array("h", _en_entiers_16_bits(bytes([128, 255, 0]), "UInt8")).tolist() == [0, 127 << 8, -128 << 8]


def test_wav_16_bits_court(tmp_path):
    prise = tmp_path / "prise.wav"
    prise.write_bytes(wav_depuis_pcm(b"\x00\x00" * 24_000, 24_000))
    assert wav_16_bits_court(prise)
    video = tmp_path / "pub.mp4"
    video.write_bytes(b"pas un fichier WAV")
    assert not wav_16_bits_court(video)
