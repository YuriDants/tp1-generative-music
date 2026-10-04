from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pretty_midi

import generate_v25 as v25


# ============================================================
# TOLERÂNCIA DE SERIALIZAÇÃO MIDI (SOMENTE PARA O WRAPPER)
# ============================================================

# A V2.5 final usa eps=1e-7 s na validação de janelas de frase.
# Em BPMs mais altos, ao escrever e reabrir um arquivo MIDI, tempos
# exatamente na fronteira entre frases podem voltar alguns microssegundos
# antes por quantização em ticks. Isso não altera a música, mas pode fazer
# a validação pós-escrita classificar a primeira nota da frase seguinte
# como pertencente à frase anterior.
#
# Não alteramos generate_v25.py. O wrapper substitui apenas a função de
# validação em memória, usando uma tolerância de 1 tick MIDI para a checagem
# das janelas temporais. Todas as demais checagens continuam sendo as da V2.5.

_ORIGINAL_VALIDATE_MIDI_STRUCTURE = v25.validate_midi_structure


def validate_midi_structure_with_tick_tolerance(pm, song):
    checks = _ORIGINAL_VALIDATE_MIDI_STRUCTURE(pm, song)

    by_name = {instrument.name: instrument for instrument in pm.instruments}
    tracks_by_role = {}

    for role in v25.ROLES:
        assignment = song.instruments[role]
        track = by_name.get(assignment.track_name)
        if track is not None:
            tracks_by_role[role] = track

    seconds_per_beat = 60.0 / song.config.bpm
    phrase_seconds = 8.0 * seconds_per_beat

    # Uma tolerância equivalente a 1 tick é suficientemente grande para
    # absorver a quantização da serialização MIDI e muito menor que a menor
    # duração musical da V2.5 (0.5 beat).
    resolution = getattr(pm, "resolution", 220) or 220
    eps = seconds_per_beat / resolution

    windows_ok = len(tracks_by_role) == 4

    if windows_ok:
        for role in v25.ROLES:
            track = tracks_by_role[role]
            expected_phrase_indices = set(v25.ROLE_PHRASE_INDICES[role])

            for phrase_index in range(1, 11):
                start = (phrase_index - 1) * phrase_seconds
                end = phrase_index * phrase_seconds

                count = sum(
                    1
                    for note in track.notes
                    if start - eps <= note.start < end - eps
                )

                expected = 8 if phrase_index in expected_phrase_indices else 0

                if count != expected:
                    windows_ok = False
                    break

            if not windows_ok:
                break

    checks["tracks_only_play_expected_phrases"] = windows_ok
    checks["all_valid"] = all(
        value
        for key, value in checks.items()
        if key != "all_valid"
    )

    return checks


# Aplica a correção somente ao módulo importado nesta execução auxiliar.
# O arquivo generate_v25.py permanece byte-a-byte inalterado.
v25.validate_midi_structure = validate_midi_structure_with_tick_tolerance


# ============================================================
# EXEMPLOS SUPLEMENTARES DA V2.5
#
# Este script NÃO altera a arquitetura V2.5 e NÃO participa dos
# experimentos M1/M2/M3 usados no artigo. Ele apenas instancia
# novas Configs e reutiliza a implementação congelada em
# generate_v25.py.
# ============================================================

SUPPLEMENTARY_CONFIGS = (
    v25.Config(name="m4", p_var=0.20, seed=303, bpm=96),
    v25.Config(name="m5", p_var=0.20, seed=404, bpm=96),
    v25.Config(name="m6", p_var=0.20, seed=505, bpm=96),
    v25.Config(name="m7", p_var=0.20, seed=606, bpm=120),
    v25.Config(name="m8", p_var=0.20, seed=707, bpm=120),
    v25.Config(name="m9", p_var=0.20, seed=808, bpm=144),
    v25.Config(name="m10", p_var=0.20, seed=909, bpm=144),
)

EXPECTED_STEMS = {config.name for config in SUPPLEMENTARY_CONFIGS}

# save_song_outputs() exige um objeto para o campo
# experiment_validation do metadata. Estes arquivos, porém, NÃO são
# novos experimentos do paper. O marcador abaixo deixa isso explícito.
SUPPLEMENTARY_STATUS: dict[str, bool] = {
    "supplementary_examples_only": True,
    "not_used_in_paper_experiments": True,
    "v25_generation_logic_reused_unchanged": True,
    "all_valid": True,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_directory(path: Path) -> dict[str, tuple[int, int, str]]:
    """Registra tamanho, mtime e SHA-256 de todos os arquivos."""
    return {
        str(file.relative_to(path)): (
            file.stat().st_size,
            file.stat().st_mtime_ns,
            sha256_file(file),
        )
        for file in sorted(path.rglob("*"))
        if file.is_file()
    }


def require_frozen_v25_outputs(base_dir: Path) -> Path:
    output_dir = base_dir / "outputs_v25"
    if not output_dir.is_dir():
        raise RuntimeError(
            "A pasta outputs_v25/ não foi encontrada. "
            "Este script exige os outputs finais M1/M2/M3 já existentes "
            "para poder verificar que eles permanecem intocados."
        )

    expected = {
        output_dir / f"m{index}.{extension}"
        for index in (1, 2, 3)
        for extension in ("mid", "wav", "json")
    }
    missing = sorted(str(path) for path in expected if not path.is_file())
    if missing:
        raise RuntimeError(
            "outputs_v25/ está incompleto. Arquivos ausentes:\n  "
            + "\n  ".join(missing)
        )

    return output_dir


def prepare_supplementary_output_dir(base_dir: Path) -> Path:
    output_dir = base_dir / "supplementary_outputs_v25"
    output_dir.mkdir(parents=True, exist_ok=True)

    existing_outputs = sorted(
        path.name
        for path in output_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".mid", ".wav", ".json"}
    )
    if existing_outputs:
        raise RuntimeError(
            "supplementary_outputs_v25/ já contém MIDIs/WAVs/JSONs. "
            "Para evitar sobrescrever ou misturar realizações, mova/remova "
            "esses arquivos antes de executar novamente. Encontrados: "
            + ", ".join(existing_outputs)
        )

    return output_dir


def mark_supplementary_metadata(json_path: Path, config: v25.Config) -> None:
    """
    Acrescenta somente informações editoriais sobre o caráter suplementar.

    A música já foi completamente gerada por generate_v25.py neste ponto.
    A correção de toada_profile.bpm resolve um detalhe descritivo da V2.5:
    essa função original usa a constante global BPM=96, enquanto config.bpm
    é o valor efetivamente usado para escrever o MIDI.
    """
    with json_path.open("r", encoding="utf-8") as file:
        payload: dict[str, Any] = json.load(file)

    if payload.get("version") != "V2.5":
        raise RuntimeError(f"{json_path.name}: metadata não identificado como V2.5")

    recorded_bpm = payload.get("config", {}).get("bpm")
    if recorded_bpm != config.bpm:
        raise RuntimeError(
            f"{json_path.name}: config.bpm={recorded_bpm}, esperado={config.bpm}"
        )

    # Apenas metadata descritivo; não altera MIDI/WAV/eventos.
    if "toada_profile" in payload:
        payload["toada_profile"]["bpm"] = config.bpm

    payload["supplementary_example"] = {
        "is_supplementary": True,
        "used_in_paper_quantitative_results": False,
        "source_implementation": "generate_v25.py",
        "source_version": "V2.5",
        "note": (
            "Exemplo suplementar gerado diretamente pela V2.5 congelada. "
            "Não integra os experimentos M1/M2/M3 nem as tabelas quantitativas do paper."
        ),
    }

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def midi_bpm(path: Path) -> float:
    pm = pretty_midi.PrettyMIDI(str(path))
    _, tempi = pm.get_tempo_changes()
    if len(tempi) != 1:
        raise RuntimeError(
            f"{path.name}: esperado exatamente 1 tempo MIDI, encontrados {len(tempi)}"
        )
    return float(tempi[0])


def verify_supplementary_outputs(output_dir: Path) -> None:
    mids = sorted(output_dir.glob("*.mid"))
    wavs = sorted(output_dir.glob("*.wav"))
    jsons = sorted(output_dir.glob("*.json"))

    if len(mids) != 7:
        raise RuntimeError(f"Esperados 7 MIDIs; encontrados {len(mids)}")
    if len(wavs) != 7:
        raise RuntimeError(f"Esperados 7 WAVs; encontrados {len(wavs)}")
    if len(jsons) != 7:
        raise RuntimeError(f"Esperados 7 JSONs; encontrados {len(jsons)}")

    if {path.stem for path in mids} != EXPECTED_STEMS:
        raise RuntimeError("Conjunto de MIDIs não corresponde exatamente a M4..M10")
    if {path.stem for path in wavs} != EXPECTED_STEMS:
        raise RuntimeError("Conjunto de WAVs não corresponde exatamente a M4..M10")
    if {path.stem for path in jsons} != EXPECTED_STEMS:
        raise RuntimeError("Conjunto de JSONs não corresponde exatamente a M4..M10")

    configs_by_name = {config.name: config for config in SUPPLEMENTARY_CONFIGS}

    print("\nVerificação dos exemplos suplementares:")
    print("  MIDIs: 7/7 OK")
    print("  WAVs:  7/7 OK")
    print("  JSONs: 7/7 OK")

    for json_path in jsons:
        config = configs_by_name[json_path.stem]
        with json_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        metadata_bpm = payload["config"]["bpm"]
        profile_bpm = payload["toada_profile"]["bpm"]
        actual_midi_bpm = midi_bpm(output_dir / f"{config.name}.mid")

        if metadata_bpm != config.bpm:
            raise RuntimeError(
                f"{config.name}: BPM no config JSON={metadata_bpm}; esperado={config.bpm}"
            )
        if profile_bpm != config.bpm:
            raise RuntimeError(
                f"{config.name}: BPM no TOADA_PROFILE={profile_bpm}; esperado={config.bpm}"
            )
        if not math.isclose(actual_midi_bpm, config.bpm, abs_tol=1e-3):
            raise RuntimeError(
                f"{config.name}: BPM MIDI={actual_midi_bpm}; esperado={config.bpm}"
            )

        supplementary = payload.get("supplementary_example", {})
        if not supplementary.get("is_supplementary", False):
            raise RuntimeError(f"{config.name}: marcador supplementary_example ausente")
        if supplementary.get("used_in_paper_quantitative_results", True):
            raise RuntimeError(f"{config.name}: metadata marcou uso indevido no paper")

        print(
            f"  {config.name.upper()}: seed={config.seed}, p_var={config.p_var:.2f}, "
            f"BPM JSON/MIDI={metadata_bpm}/{actual_midi_bpm:.1f} OK"
        )


def main() -> None:
    base_dir = Path(__file__).resolve().parent

    frozen_output_dir = require_frozen_v25_outputs(base_dir)
    frozen_before = snapshot_directory(frozen_output_dir)

    supplementary_output_dir = prepare_supplementary_output_dir(base_dir)

    print("Gerando exemplos suplementares com a implementação V2.5 congelada...")
    print("Pasta de destino:", supplementary_output_dir)

    for config in SUPPLEMENTARY_CONFIGS:
        song = v25.generate_song(config)
        v25.save_song_outputs(
            song=song,
            output_dir=supplementary_output_dir,
            experiment_validation=SUPPLEMENTARY_STATUS,
        )
        mark_supplementary_metadata(
            supplementary_output_dir / f"{config.name}.json",
            config,
        )

    verify_supplementary_outputs(supplementary_output_dir)

    frozen_after = snapshot_directory(frozen_output_dir)
    if frozen_before != frozen_after:
        raise RuntimeError(
            "ERRO: algum arquivo em outputs_v25/ mudou durante a execução. "
            "Os exemplos suplementares não devem modificar M1/M2/M3."
        )

    print("\nIntegridade da V2.5 final:")
    print("  outputs_v25/ permaneceu byte-a-byte e mtime-a-mtime inalterado: OK")
    print("\nConcluído: M4..M10 são exemplos suplementares da V2.5, não novos experimentos do paper.")


if __name__ == "__main__":
    main()
