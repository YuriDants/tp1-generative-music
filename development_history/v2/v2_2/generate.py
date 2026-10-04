from __future__ import annotations

import hashlib
import json
import math
import random
import subprocess
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Literal

import pretty_midi


# ============================================================
# V2.1 — CONFIGURAÇÃO CONGELADA
# ============================================================

FORM = list("ABBAACCDDC")

TONIC_MIDI = 60  # C4
VELOCITY = 80
BPM = 96

MUTABLE_POSITIONS = {2, 3, 4, 5, 6}
ANCHOR_POSITIONS = {1, 7, 8}

MUSESCORE_FLATPAK_ID = "org.musescore.MuseScore"


# ============================================================
# FAMÍLIAS MELÓDICAS
# ============================================================

MELODIC_VARIANTS = {
    "A": [
        [1, 2, 3, 2, 1, 3, 2, 1],
        [1, 3, 4, 3, 2, 3, 2, 1],
        [1, 2, 4, 3, 1, 2, 2, 1],
        [1, 3, 2, 4, 3, 2, 2, 1],
    ],
    "B": [
        [3, 4, 5, 4, 3, 5, 4, 5],
        [3, 5, 6, 5, 4, 6, 4, 5],
        [3, 4, 6, 5, 3, 4, 4, 5],
        [3, 2, 4, 5, 6, 5, 4, 5],
    ],
    "C": [
        [5, 6, 5, 4, 3, 4, 3, 2],
        [5, 7, 6, 4, 3, 5, 3, 2],
        [5, 4, 6, 5, 4, 3, 3, 2],
        [5, 6, 7, 5, 3, 2, 3, 2],
    ],
    "D": [
        [2, 3, 4, 5, 4, 3, 6, 5],
        [2, 4, 5, 6, 4, 2, 6, 5],
        [2, 3, 5, 4, 6, 4, 6, 5],
        [2, 1, 3, 5, 4, 3, 6, 5],
    ],
}


# ============================================================
# FAMÍLIAS RÍTMICAS
# ============================================================

RHYTHMIC_VARIANTS = [
    [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    [0.5, 1.5, 1.0, 1.0, 0.5, 1.5, 1.0, 1.0],
    [1.5, 0.5, 1.0, 1.0, 1.5, 0.5, 1.0, 1.0],
    [0.5, 0.5, 1.0, 2.0, 0.5, 0.5, 1.0, 2.0],
]


# ============================================================
# IDENTIDADE INSTRUMENTAL
# ============================================================

INSTRUMENT_NAMES = {
    "A": "Acoustic Guitar (nylon)",
    "B": "Accordion",
    "C": "Flute",
    "D": "Violin",
}


# ============================================================
# ESCALA — C MAIOR
# ============================================================

C_MAJOR_OFFSETS = {
    1: 0,
    2: 2,
    3: 4,
    4: 5,
    5: 7,
    6: 9,
    7: 11,
}


# ============================================================
# ESTRUTURAS
# ============================================================

@dataclass(frozen=True)
class Config:
    name: str
    p_var: float
    seed: int
    bpm: int = BPM
    tonic_midi: int = TONIC_MIDI
    velocity: int = VELOCITY


@dataclass(frozen=True)
class MicroVariation:
    position: int
    degree_before: int
    degree_after: int
    midi_before: int
    midi_after: int


@dataclass(frozen=True)
class Event:
    phrase_index: int
    phrase_class: str
    position: int
    melodic_variant: int
    rhythmic_variant: int
    macro_realization: str
    base_degree: int
    realized_degree: int
    midi_pitch: int
    duration: float
    velocity: int
    microvaried: bool
    terminal: Literal["NOTE"] = "NOTE"


@dataclass(frozen=True)
class Phrase:
    index: int
    phrase_class: str
    melodic_variant: int
    rhythmic_variant: int
    macro_realization: str
    instrument_name: str
    base_melody: tuple[int, ...]
    rhythm: tuple[float, ...]
    microvariations: tuple[MicroVariation, ...]
    events: tuple[Event, ...]


@dataclass(frozen=True)
class Song:
    config: Config
    macro_rng_seed: int
    micro_rng_seed: int
    phrases: tuple[Phrase, ...]


# ============================================================
# RNGs INDEPENDENTES DERIVADOS DA MESMA SEED
# ============================================================

def derive_stream_seed(seed: int, stream_name: str) -> int:
    """Deriva deterministicamente uma seed independente para cada stream."""

    payload = f"tp1-decima-v21|{seed}|{stream_name}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def make_rngs(seed: int) -> tuple[random.Random, random.Random, int, int]:
    macro_seed = derive_stream_seed(seed, "macro")
    micro_seed = derive_stream_seed(seed, "micro")

    rng_macro = random.Random(macro_seed)
    rng_micro = random.Random(micro_seed)

    return rng_macro, rng_micro, macro_seed, micro_seed


# ============================================================
# AUXILIARES
# ============================================================

def degree_to_midi(degree: int, tonic_midi: int) -> int:
    if degree not in C_MAJOR_OFFSETS:
        raise ValueError(f"Grau inválido: {degree}")

    return tonic_midi + C_MAJOR_OFFSETS[degree]


def get_instrument_programs() -> dict[str, int]:
    return {
        phrase_class: pretty_midi.instrument_name_to_program(instrument_name)
        for phrase_class, instrument_name in INSTRUMENT_NAMES.items()
    }


# ============================================================
# GRAMÁTICA
# ============================================================

# S -> A B B A A C C D D C

def expand_axiom() -> list[str]:
    return FORM.copy()


# X -> Xij, com i,j equiprováveis e independentes.
# P(Xij) = 1/16.

def choose_macro_realization(
    phrase_class: str,
    rng_macro: random.Random,
) -> tuple[int, int, str]:
    melodic_variant = rng_macro.randrange(4)
    rhythmic_variant = rng_macro.randrange(4)

    macro_realization = (
        f"{phrase_class}{melodic_variant}{rhythmic_variant}"
    )

    return melodic_variant, rhythmic_variant, macro_realization


# Microgramática nas posições 2..6:
# Ek -> NOTE(base_degree, duration, velocity)      [1-p_var]
# Ek -> NOTE(base_degree +/- 1, duration, velocity) [p_var]
#
# Para cada posição são consumidos SEMPRE dois draws do rng_micro:
# 1) gate: decide se varia;
# 2) selector: escolhe o vizinho permitido.
#
# Assim seeds iguais percorrem o mesmo stream micro, mesmo com p_var diferente.

def apply_microvariations(
    base_melody: list[int],
    p_var: float,
    rng_micro: random.Random,
    tonic_midi: int,
) -> tuple[list[int], tuple[MicroVariation, ...]]:
    realized = list(base_melody)
    changes: list[MicroVariation] = []

    for position in range(2, 7):
        gate = rng_micro.random()
        selector = rng_micro.random()

        if gate >= p_var:
            continue

        index = position - 1
        before = base_melody[index]

        valid_deltas = [
            delta
            for delta in (-1, +1)
            if 1 <= before + delta <= 7
        ]

        selected_index = min(
            int(selector * len(valid_deltas)),
            len(valid_deltas) - 1,
        )

        delta = valid_deltas[selected_index]
        after = before + delta
        realized[index] = after

        changes.append(
            MicroVariation(
                position=position,
                degree_before=before,
                degree_after=after,
                midi_before=degree_to_midi(before, tonic_midi),
                midi_after=degree_to_midi(after, tonic_midi),
            )
        )

    return realized, tuple(changes)


def expand_phrase(
    phrase_index: int,
    phrase_class: str,
    config: Config,
    rng_macro: random.Random,
    rng_micro: random.Random,
) -> Phrase:
    melodic_variant, rhythmic_variant, macro_realization = (
        choose_macro_realization(phrase_class, rng_macro)
    )

    base_melody = list(
        MELODIC_VARIANTS[phrase_class][melodic_variant]
    )

    rhythm = list(
        RHYTHMIC_VARIANTS[rhythmic_variant]
    )

    realized_melody, microvariations = apply_microvariations(
        base_melody=base_melody,
        p_var=config.p_var,
        rng_micro=rng_micro,
        tonic_midi=config.tonic_midi,
    )

    changed_positions = {
        variation.position
        for variation in microvariations
    }

    events: list[Event] = []

    for position, (base_degree, realized_degree, duration) in enumerate(
        zip(base_melody, realized_melody, rhythm),
        start=1,
    ):
        events.append(
            Event(
                phrase_index=phrase_index,
                phrase_class=phrase_class,
                position=position,
                melodic_variant=melodic_variant,
                rhythmic_variant=rhythmic_variant,
                macro_realization=macro_realization,
                base_degree=base_degree,
                realized_degree=realized_degree,
                midi_pitch=degree_to_midi(
                    realized_degree,
                    config.tonic_midi,
                ),
                duration=duration,
                velocity=config.velocity,
                microvaried=position in changed_positions,
            )
        )

    return Phrase(
        index=phrase_index,
        phrase_class=phrase_class,
        melodic_variant=melodic_variant,
        rhythmic_variant=rhythmic_variant,
        macro_realization=macro_realization,
        instrument_name=INSTRUMENT_NAMES[phrase_class],
        base_melody=tuple(base_melody),
        rhythm=tuple(rhythm),
        microvariations=microvariations,
        events=tuple(events),
    )


def generate_song(config: Config) -> Song:
    if not 0.0 <= config.p_var <= 1.0:
        raise ValueError("p_var deve estar no intervalo [0, 1].")

    rng_macro, rng_micro, macro_seed, micro_seed = make_rngs(config.seed)

    phrases = tuple(
        expand_phrase(
            phrase_index=index,
            phrase_class=phrase_class,
            config=config,
            rng_macro=rng_macro,
            rng_micro=rng_micro,
        )
        for index, phrase_class in enumerate(expand_axiom(), start=1)
    )

    return Song(
        config=config,
        macro_rng_seed=macro_seed,
        micro_rng_seed=micro_seed,
        phrases=phrases,
    )


# ============================================================
# ASSINATURAS
# ============================================================

def macro_signature(song: Song) -> tuple:
    return tuple(
        (
            phrase.phrase_class,
            phrase.melodic_variant,
            phrase.rhythmic_variant,
            phrase.macro_realization,
            phrase.base_melody,
            phrase.rhythm,
            phrase.instrument_name,
        )
        for phrase in song.phrases
    )


def song_signature(song: Song) -> tuple:
    return tuple(
        (
            phrase.index,
            phrase.phrase_class,
            phrase.macro_realization,
            tuple(
                (
                    event.position,
                    event.base_degree,
                    event.realized_degree,
                    event.midi_pitch,
                    event.duration,
                    event.velocity,
                    event.microvaried,
                )
                for event in phrase.events
            ),
        )
        for phrase in song.phrases
    )


# ============================================================
# VALIDAÇÃO INDIVIDUAL
# ============================================================

def validate_song(song: Song) -> dict[str, bool]:
    all_events = [
        event
        for phrase in song.phrases
        for event in phrase.events
    ]

    programs = get_instrument_programs()

    checks: dict[str, bool] = {}

    checks["exactly_10_phrases"] = len(song.phrases) == 10

    checks["form_is_ABBAACCDDC"] = (
        [phrase.phrase_class for phrase in song.phrases] == FORM
    )

    checks["exactly_8_events_per_phrase"] = all(
        len(phrase.events) == 8
        for phrase in song.phrases
    )

    checks["exactly_80_total_events"] = len(all_events) == 80

    checks["each_phrase_is_8_beats"] = all(
        math.isclose(
            sum(event.duration for event in phrase.events),
            8.0,
            abs_tol=1e-9,
        )
        for phrase in song.phrases
    )

    checks["macro_indices_valid"] = all(
        0 <= phrase.melodic_variant <= 3
        and 0 <= phrase.rhythmic_variant <= 3
        for phrase in song.phrases
    )

    checks["macro_names_valid"] = all(
        phrase.macro_realization
        == f"{phrase.phrase_class}{phrase.melodic_variant}{phrase.rhythmic_variant}"
        for phrase in song.phrases
    )

    checks["base_melody_matches_macro"] = all(
        list(phrase.base_melody)
        == MELODIC_VARIANTS[phrase.phrase_class][phrase.melodic_variant]
        for phrase in song.phrases
    )

    checks["rhythm_matches_macro"] = all(
        list(phrase.rhythm)
        == RHYTHMIC_VARIANTS[phrase.rhythmic_variant]
        for phrase in song.phrases
    )

    checks["degrees_are_valid"] = all(
        1 <= event.realized_degree <= 7
        for event in all_events
    )

    checks["midi_pitches_are_valid"] = all(
        0 <= event.midi_pitch <= 127
        for event in all_events
    )

    checks["durations_are_positive"] = all(
        event.duration > 0
        for event in all_events
    )

    checks["only_NOTE_terminals_remain"] = all(
        event.terminal == "NOTE"
        for event in all_events
    )

    checks["anchor_positions_unchanged"] = all(
        event.position not in ANCHOR_POSITIONS
        or event.realized_degree == event.base_degree
        for event in all_events
    )

    checks["microvariations_only_at_positions_2_to_6"] = all(
        variation.position in MUTABLE_POSITIONS
        for phrase in song.phrases
        for variation in phrase.microvariations
    )

    checks["microvariations_change_exactly_one_scale_degree"] = all(
        abs(variation.degree_after - variation.degree_before) == 1
        and 1 <= variation.degree_after <= 7
        for phrase in song.phrases
        for variation in phrase.microvariations
    )

    checks["microvariation_metadata_matches_events"] = all(
        {
            variation.position: (
                variation.degree_before,
                variation.degree_after,
            )
            for variation in phrase.microvariations
        }
        == {
            event.position: (
                event.base_degree,
                event.realized_degree,
            )
            for event in phrase.events
            if event.microvaried
        }
        for phrase in song.phrases
    )

    checks["non_microvaried_events_equal_base"] = all(
        event.microvaried
        or event.realized_degree == event.base_degree
        for event in all_events
    )

    checks["instrument_names_valid"] = all(
        phrase.instrument_name == INSTRUMENT_NAMES[phrase.phrase_class]
        for phrase in song.phrases
    )

    checks["instrument_programs_resolved"] = (
        len(programs) == 4
        and all(
            isinstance(program, int) and 0 <= program <= 127
            for program in programs.values()
        )
    )

    regenerated = generate_song(song.config)

    checks["same_seed_and_config_are_reproducible"] = (
        song_signature(song) == song_signature(regenerated)
    )

    checks["all_valid"] = all(checks.values())

    return checks


# ============================================================
# VALIDAÇÃO CRUZADA DO EXPERIMENTO
# ============================================================

def validate_experiment(songs: dict[str, Song]) -> dict[str, bool]:
    m1 = songs["m1"]
    m2 = songs["m2"]
    m3 = songs["m3"]

    checks = {
        "m1_and_m3_have_same_seed": (
            m1.config.seed == m3.config.seed
        ),
        "m1_and_m3_have_different_p_var": (
            m1.config.p_var != m3.config.p_var
        ),
        "m1_and_m3_use_same_macro_rng_seed": (
            m1.macro_rng_seed == m3.macro_rng_seed
        ),
        "m1_and_m3_use_same_micro_rng_seed": (
            m1.micro_rng_seed == m3.micro_rng_seed
        ),
        "m1_and_m3_have_identical_macro_realizations": (
            macro_signature(m1) == macro_signature(m3)
        ),
        "m1_and_m3_realized_outputs_are_different": (
            song_signature(m1) != song_signature(m3)
        ),
        "m1_and_m2_are_different": (
            song_signature(m1) != song_signature(m2)
        ),
    }

    checks["all_valid"] = all(checks.values())
    return checks


# ============================================================
# MÉTRICAS
# ============================================================

def phrase_similarity(phrase_a: Phrase, phrase_b: Phrase) -> dict[str, float]:
    pitch_equal = 0
    rhythm_equal = 0
    combined_equal = 0

    for event_a, event_b in zip(phrase_a.events, phrase_b.events):
        same_pitch = event_a.realized_degree == event_b.realized_degree
        same_rhythm = math.isclose(
            event_a.duration,
            event_b.duration,
            abs_tol=1e-9,
        )

        if same_pitch:
            pitch_equal += 1
        if same_rhythm:
            rhythm_equal += 1
        if same_pitch and same_rhythm:
            combined_equal += 1

    return {
        "pitch_similarity": pitch_equal / 8.0,
        "rhythm_similarity": rhythm_equal / 8.0,
        "combined_similarity": combined_equal / 8.0,
    }


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def compute_metrics(song: Song) -> dict:
    microvariation_count = sum(
        len(phrase.microvariations)
        for phrase in song.phrases
    )

    total_mutable_positions = len(song.phrases) * len(MUTABLE_POSITIONS)

    intra_pitch: list[float] = []
    intra_rhythm: list[float] = []
    intra_combined: list[float] = []

    inter_pitch: list[float] = []
    inter_rhythm: list[float] = []
    inter_combined: list[float] = []

    pair_details = []

    for phrase_a, phrase_b in combinations(song.phrases, 2):
        similarities = phrase_similarity(phrase_a, phrase_b)
        same_class = phrase_a.phrase_class == phrase_b.phrase_class

        pair_details.append(
            {
                "phrase_i": phrase_a.index,
                "phrase_j": phrase_b.index,
                "class_i": phrase_a.phrase_class,
                "class_j": phrase_b.phrase_class,
                "macro_i": phrase_a.macro_realization,
                "macro_j": phrase_b.macro_realization,
                "same_class": same_class,
                **similarities,
            }
        )

        if same_class:
            intra_pitch.append(similarities["pitch_similarity"])
            intra_rhythm.append(similarities["rhythm_similarity"])
            intra_combined.append(similarities["combined_similarity"])
        else:
            inter_pitch.append(similarities["pitch_similarity"])
            inter_rhythm.append(similarities["rhythm_similarity"])
            inter_combined.append(similarities["combined_similarity"])

    return {
        "microvariation_count": microvariation_count,
        "total_mutable_positions": total_mutable_positions,
        "observed_microvariation_rate": (
            microvariation_count / total_mutable_positions
        ),
        "mean_intra_class_pitch_similarity": mean(intra_pitch),
        "mean_inter_class_pitch_similarity": mean(inter_pitch),
        "mean_intra_class_rhythm_similarity": mean(intra_rhythm),
        "mean_inter_class_rhythm_similarity": mean(inter_rhythm),
        "mean_intra_class_combined_similarity": mean(intra_combined),
        "mean_inter_class_combined_similarity": mean(inter_combined),
        "pair_details": pair_details,
    }


# ============================================================
# MIDI
# ============================================================

def build_pretty_midi(song: Song) -> pretty_midi.PrettyMIDI:
    pm = pretty_midi.PrettyMIDI(initial_tempo=song.config.bpm)

    pm.time_signature_changes.append(
        pretty_midi.TimeSignature(4, 4, 0.0)
    )

    programs = get_instrument_programs()

    instruments = {
        phrase_class: pretty_midi.Instrument(
            program=programs[phrase_class],
            is_drum=False,
            name=f"{phrase_class} - {INSTRUMENT_NAMES[phrase_class]}",
        )
        for phrase_class in ("A", "B", "C", "D")
    }

    seconds_per_beat = 60.0 / song.config.bpm
    current_beat = 0.0

    for phrase in song.phrases:
        instrument = instruments[phrase.phrase_class]

        for event in phrase.events:
            start = current_beat * seconds_per_beat
            end = (current_beat + event.duration) * seconds_per_beat

            instrument.notes.append(
                pretty_midi.Note(
                    velocity=event.velocity,
                    pitch=event.midi_pitch,
                    start=start,
                    end=end,
                )
            )

            current_beat += event.duration

    for phrase_class in ("A", "B", "C", "D"):
        pm.instruments.append(instruments[phrase_class])

    return pm


# ============================================================
# WAV FINAL VIA MUSESCORE
# ============================================================

def render_wav_with_musescore(
    midi_path: Path,
    wav_path: Path,
) -> None:
    """
    Renderiza o MIDI para WAV usando o MuseScore instalado
    no sistema host.

    Como o projeto pode ser executado dentro do VS Code Flatpak,
    usamos flatpak-spawn --host para acessar o Flatpak do host.
    """

    command = [
        "flatpak-spawn",
        "--host",
        "flatpak",
        "run",
        "org.musescore.MuseScore",
        "-o",
        str(wav_path),
        str(midi_path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "MuseScore falhou ao renderizar WAV.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    if not wav_path.exists():
        raise RuntimeError(
            f"MuseScore terminou sem criar: {wav_path}"
        )

# ============================================================
# METADADOS
# ============================================================

def microvariation_to_dict(variation: MicroVariation) -> dict:
    return {
        "position": variation.position,
        "degree_before": variation.degree_before,
        "degree_after": variation.degree_after,
        "midi_before": variation.midi_before,
        "midi_after": variation.midi_after,
    }


def event_to_dict(event: Event) -> dict:
    return {
        "position": event.position,
        "base_degree": event.base_degree,
        "realized_degree": event.realized_degree,
        "midi_pitch": event.midi_pitch,
        "duration": event.duration,
        "velocity": event.velocity,
        "microvaried": event.microvaried,
        "terminal": event.terminal,
    }


def phrase_to_dict(
    phrase: Phrase,
    song: Song,
    programs: dict[str, int],
) -> dict:
    return {
        "phrase_index": phrase.index,
        "class": phrase.phrase_class,
        "melodic_variant": phrase.melodic_variant,
        "rhythmic_variant": phrase.rhythmic_variant,
        "macro_realization": phrase.macro_realization,
        "instrument": phrase.instrument_name,
        "instrument_program": programs[phrase.phrase_class],
        "seed": song.config.seed,
        "p_var": song.config.p_var,
        "microvariation_positions": [
            variation.position
            for variation in phrase.microvariations
        ],
        "microvariations": [
            microvariation_to_dict(variation)
            for variation in phrase.microvariations
        ],
        "events": [
            event_to_dict(event)
            for event in phrase.events
        ],
    }


def save_metadata(
    song: Song,
    validation: dict,
    experiment_validation: dict,
    metrics: dict,
    path: Path,
) -> None:
    programs = get_instrument_programs()

    payload = {
        "version": "V2.1",
        "config": {
            "name": song.config.name,
            "seed": song.config.seed,
            "p_var": song.config.p_var,
            "bpm": song.config.bpm,
            "time_signature": "4/4",
            "tonic_midi": song.config.tonic_midi,
            "velocity": song.config.velocity,
            "form": "".join(FORM),
            "macro_rng_seed": song.macro_rng_seed,
            "micro_rng_seed": song.micro_rng_seed,
        },
        "formal_grammar": {
            "axiom": "S",
            "structural_rule": "S -> A B B A A C C D D C",
            "macro_rule": "X -> Xij with i,j in {0,1,2,3}",
            "macro_probability": "P(Xij) = 1/16",
            "micro_rule": (
                "positions 2..6: keep pitch [1-p_var] "
                "or move +/-1 scale degree [p_var]"
            ),
            "anchors": [1, 7, 8],
            "terminal": "NOTE(degree, duration, velocity)",
        },
        "instrument_programs": programs,
        "validation": validation,
        "experiment_validation": experiment_validation,
        "metrics": metrics,
        "phrases": [
            phrase_to_dict(phrase, song, programs)
            for phrase in song.phrases
        ],
    }

    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


# ============================================================
# SAÍDA DE UMA MÚSICA
# ============================================================

def save_song_outputs(
    song: Song,
    output_dir: Path,
    experiment_validation: dict,
) -> None:
    validation = validate_song(song)

    if not validation["all_valid"]:
        failed = [
            name
            for name, result in validation.items()
            if not result
        ]
        raise RuntimeError(
            f"Falha de validação em {song.config.name}: {failed}"
        )

    metrics = compute_metrics(song)

    midi_path = output_dir / f"{song.config.name}.mid"
    wav_path = output_dir / f"{song.config.name}.wav"
    json_path = output_dir / f"{song.config.name}.json"

    pm = build_pretty_midi(song)
    pm.write(str(midi_path))

    save_metadata(
        song=song,
        validation=validation,
        experiment_validation=experiment_validation,
        metrics=metrics,
        path=json_path,
    )

    render_wav_with_musescore(
        midi_path=midi_path,
        wav_path=wav_path,
    )

    print()
    print(song.config.name.upper())
    print(f"  p_var={song.config.p_var:.2f}")
    print(f"  seed={song.config.seed}")
    print(
        "  macros: "
        + " ".join(
            phrase.macro_realization
            for phrase in song.phrases
        )
    )
    print(
        "  microvariações: "
        f"{metrics['microvariation_count']}/"
        f"{metrics['total_mutable_positions']} "
        f"({metrics['observed_microvariation_rate']:.3f})"
    )
    print(
        "  similaridade combinada intra/inter: "
        f"{metrics['mean_intra_class_combined_similarity']:.3f} / "
        f"{metrics['mean_inter_class_combined_similarity']:.3f}"
    )
    print(f"  MIDI: {midi_path}")
    print(f"  WAV MuseScore: {wav_path}")


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    base_dir = Path(__file__).resolve().parent
    output_dir = base_dir / "outputs_v21"
    output_dir.mkdir(parents=True, exist_ok=True)

    configs = [
        Config(name="m1", p_var=0.20, seed=101),
        Config(name="m2", p_var=0.20, seed=202),
        Config(name="m3", p_var=0.70, seed=101),
    ]

    songs = {
        config.name: generate_song(config)
        for config in configs
    }

    experiment_validation = validate_experiment(songs)

    if not experiment_validation["all_valid"]:
        failed = [
            name
            for name, result in experiment_validation.items()
            if not result
        ]
        raise RuntimeError(
            f"Falha na validação cruzada do experimento: {failed}"
        )

    with (output_dir / "experiment_validation.json").open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            experiment_validation,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("Validação cruzada V2.1:")
    print(
        "  M1/M3 mesmas macro-realizações: OK"
    )
    print(
        "  M1/M3 mesmo material pré-microvariação: OK"
    )
    print(
        "  M1/M3 saídas realizadas diferentes: OK"
    )

    for config in configs:
        save_song_outputs(
            song=songs[config.name],
            output_dir=output_dir,
            experiment_validation=experiment_validation,
        )

    print()
    print(f"Arquivos V2.1 gerados em: {output_dir}")


if __name__ == "__main__":
    main()
