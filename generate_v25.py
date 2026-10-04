from __future__ import annotations

import json
import math
import random
import shutil
import subprocess
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import pretty_midi


# ============================================================
# V2.5 — ARRANJO PERCUSSIVO SOBRE A GERAÇÃO MELÓDICA CONGELADA DA V2.4
# ============================================================

STRUCTURE = ["R1", "R2", "R2", "R1", "R1", "R3", "R3", "R4", "R4", "R3"]
DISPLAY_FORM = "ABBAACCDDC"
ROLES = ("R1", "R2", "R3", "R4")
FAMILY_IDS = ("F1", "F2", "F3", "F4")

ROLE_PHRASE_INDICES = {
    "R1": (1, 4, 5),
    "R2": (2, 3),
    "R3": (6, 7, 10),
    "R4": (8, 9),
}

EXPECTED_EVENT_COUNTS = {
    "R1": 24,
    "R2": 16,
    "R3": 24,
    "R4": 16,
}

TONIC_MIDI = 60  # C4
VELOCITY = 80
BPM = 96

MUTABLE_POSITIONS = (2, 3, 4, 5, 6)
PROTECTED_POSITIONS = (1, 7, 8)

# Streams independentes derivados deterministicamente da mesma seed.
STREAM_MULTIPLIER = 1_000_003
STREAM_OFFSETS = {
    "family": 11,
    "rhythm": 23,
    "role": 37,
    "instrument": 53,
    "micro": 71,
    "percussion": 89,
}

C_MAJOR_OFFSETS = {
    1: 0,
    2: 2,
    3: 4,
    4: 5,
    5: 7,
    6: 9,
    7: 11,
}

# TOADA_PROFILE: regras comuns; NÃO é uma melodia.
START_DEGREES = (2, 3, 4, 5)

MOVE_RULES = (
    ("STEP_UP", +1, 0.30),
    ("STEP_DOWN", -1, 0.30),
    ("REPEAT", 0, 0.15),
    ("LEAP_UP", +2, 0.125),
    ("LEAP_DOWN", -2, 0.125),
)

# Decisão computacional do projeto; não é tratada como regra histórica da décima.
CADENCE_RULES = (
    ("CAD_2_1", (2, 1), 0.35),
    ("CAD_3_1", (3, 1), 0.25),
    ("CAD_4_3", (4, 3), 0.20),
    ("CAD_2_3", (2, 3), 0.20),
)

RHYTHM_CELLS = (
    (1.0, 1.0),
    (0.5, 1.5),
    (1.5, 0.5),
)

CULTURAL_INSTRUMENTS = (
    {
        "cultural_label": "Viola nordestina / viola sertaneja",
        "track_label": "Viola",
        "preferred_midi_instrument": "Acoustic Guitar (steel)",
        "fallback_midi_instrument": None,
    },
    {
        "cultural_label": "Rabeca",
        "track_label": "Rabeca",
        "preferred_midi_instrument": "Fiddle",
        "fallback_midi_instrument": "Violin",
    },
    {
        "cultural_label": "Sanfona",
        "track_label": "Sanfona",
        "preferred_midi_instrument": "Accordion",
        "fallback_midi_instrument": None,
    },
    {
        "cultural_label": "Violão",
        "track_label": "Violão",
        "preferred_midi_instrument": "Acoustic Guitar (nylon)",
        "fallback_midi_instrument": None,
    },
)


# ============================================================
# PERCUSSÃO V2.5 — CAMADA DE ARRANJO, NÃO DEFINE R1/R2/R3/R4
# ============================================================

# General MIDI Level 1, canal de percussão (channel 10; índice 9 no arquivo MIDI).
# São proxies de arranjo: Bass Drum 1 aproxima a função grave de uma zabumba;
# Mute/Open Triangle aproximam a função aguda de um triângulo.
PERC_BASS_DRUM = 36
PERC_MUTE_TRIANGLE = 80
PERC_OPEN_TRIANGLE = 81
PERCUSSION_TRACK_NAME = "Percussao - Zabumba/Triangulo (GM proxies)"
PERCUSSION_BAR_COUNT = 20

# Cada produção ocupa exatamente um compasso 4/4.
# beat é relativo ao início do compasso; duration_beats é apenas uma duração curta
# para serialização MIDI da nota percussiva.
PERCUSSION_PATTERNS = {
    "BASIC_A": {
        "probability": 0.40,
        "hits": (
            (0.0, PERC_BASS_DRUM, 54),
            (0.5, PERC_MUTE_TRIANGLE, 38),
            (1.5, PERC_MUTE_TRIANGLE, 38),
            (2.0, PERC_BASS_DRUM, 50),
            (2.5, PERC_MUTE_TRIANGLE, 38),
            (3.5, PERC_OPEN_TRIANGLE, 44),
        ),
    },
    "BASIC_B": {
        "probability": 0.30,
        "hits": (
            (0.0, PERC_BASS_DRUM, 52),
            (1.0, PERC_MUTE_TRIANGLE, 38),
            (2.0, PERC_BASS_DRUM, 48),
            (2.5, PERC_MUTE_TRIANGLE, 40),
            (3.0, PERC_MUTE_TRIANGLE, 38),
            (3.5, PERC_OPEN_TRIANGLE, 44),
        ),
    },
    "BASIC_C": {
        "probability": 0.20,
        "hits": (
            (0.0, PERC_BASS_DRUM, 50),
            (0.5, PERC_MUTE_TRIANGLE, 36),
            (1.5, PERC_BASS_DRUM, 46),
            (2.0, PERC_MUTE_TRIANGLE, 38),
            (3.0, PERC_BASS_DRUM, 48),
            (3.5, PERC_OPEN_TRIANGLE, 42),
        ),
    },
    "FILL": {
        "probability": 0.10,
        "hits": (
            (0.0, PERC_BASS_DRUM, 56),
            (0.5, PERC_MUTE_TRIANGLE, 40),
            (1.5, PERC_MUTE_TRIANGLE, 40),
            (2.0, PERC_BASS_DRUM, 52),
            (2.5, PERC_MUTE_TRIANGLE, 42),
            (3.0, PERC_MUTE_TRIANGLE, 44),
            (3.5, PERC_OPEN_TRIANGLE, 48),
            (3.75, PERC_MUTE_TRIANGLE, 44),
        ),
    },
}

PERCUSSION_GM_NAMES = {
    36: "Bass Drum 1",
    80: "Mute Triangle",
    81: "Open Triangle",
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
class PitchSpec:
    degree: int
    octave_offset: int = 0


@dataclass(frozen=True)
class FamilyBackbone:
    family_id: str
    pitches: tuple[PitchSpec, ...]
    generation_trace: dict[str, Any]


@dataclass(frozen=True)
class RhythmBackbone:
    family_id: str
    cell_indices: tuple[int, int, int, int]
    durations: tuple[float, ...]


@dataclass(frozen=True)
class InstrumentAssignment:
    role: str
    cultural_label: str
    track_label: str
    midi_instrument: str
    midi_program: int
    track_name: str
    proxy_note: str


@dataclass(frozen=True)
class PercussionHit:
    bar_index: int
    pattern: str
    beat_in_bar: float
    midi_note: int
    gm_name: str
    velocity: int


@dataclass(frozen=True)
class PercussionCell:
    bar_index: int
    production: str
    probability: float
    hits: tuple[PercussionHit, ...]


@dataclass(frozen=True)
class PercussionArrangement:
    cells: tuple[PercussionCell, ...]


@dataclass(frozen=True)
class Event:
    phrase_index: int
    family_id: str
    role: str
    position: int

    backbone_degree: int
    backbone_octave_offset: int
    backbone_midi: int

    realized_degree: int
    realized_octave_offset: int
    realized_midi: int

    duration: float
    velocity: int
    microvaried: bool


@dataclass(frozen=True)
class Phrase:
    index: int
    family_id: str
    role: str
    role_occurrence: int
    instrument: InstrumentAssignment
    events: tuple[Event, ...]
    micro_decisions: tuple[dict[str, Any], ...]
    microvariations: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class Song:
    config: Config
    families: dict[str, FamilyBackbone]
    rhythms: dict[str, RhythmBackbone]
    role_mapping: dict[str, str]  # role -> family_id
    instruments: dict[str, InstrumentAssignment]
    phrases: tuple[Phrase, ...]
    percussion: PercussionArrangement


# ============================================================
# RNGs INDEPENDENTES
# ============================================================

def derive_stream_seed(seed: int, stream_name: str) -> int:
    return seed * STREAM_MULTIPLIER + STREAM_OFFSETS[stream_name]


def make_rngs(seed: int) -> tuple[
    random.Random,
    random.Random,
    random.Random,
    random.Random,
    random.Random,
]:
    return (
        random.Random(derive_stream_seed(seed, "family")),
        random.Random(derive_stream_seed(seed, "rhythm")),
        random.Random(derive_stream_seed(seed, "role")),
        random.Random(derive_stream_seed(seed, "instrument")),
        random.Random(derive_stream_seed(seed, "micro")),
    )


# ============================================================
# AUXILIARES
# ============================================================

def degree_to_midi(degree: int, octave_offset: int, tonic_midi: int) -> int:
    if degree not in C_MAJOR_OFFSETS:
        raise ValueError(f"Grau inválido: {degree}")

    midi_pitch = tonic_midi + C_MAJOR_OFFSETS[degree] + 12 * octave_offset

    if not 0 <= midi_pitch <= 127:
        raise ValueError(f"Pitch MIDI fora do intervalo: {midi_pitch}")

    return midi_pitch


def pitch_spec_to_dict(pitch: PitchSpec) -> dict[str, int]:
    return {
        "degree": pitch.degree,
        "octave_offset": pitch.octave_offset,
    }


def weighted_choice_with_probabilities(
    rng: random.Random,
    choices: list[tuple[Any, float]],
) -> tuple[Any, list[dict[str, Any]]]:
    """
    Sorteia usando pesos originais e retorna as probabilidades efetivas
    após remover produções inválidas e renormalizar.
    """
    if not choices:
        raise ValueError("Lista vazia em weighted_choice_with_probabilities")

    total = sum(weight for _, weight in choices)
    if total <= 0:
        raise ValueError("Soma de pesos inválida")

    effective = [
        {
            "item": item,
            "original_weight": weight,
            "effective_probability": weight / total,
        }
        for item, weight in choices
    ]

    x = rng.random() * total
    cumulative = 0.0

    for item, weight in choices:
        cumulative += weight
        if x < cumulative:
            return item, effective

    return choices[-1][0], effective


def select_from_unit_interval(value: float, items: list[Any]) -> Any:
    if not items:
        raise ValueError("Lista vazia em select_from_unit_interval")
    index = min(int(value * len(items)), len(items) - 1)
    return items[index]


def cadence_effective_records(
    effective: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for entry in effective:
        name, pair = entry["item"]
        records.append(
            {
                "production": name,
                "degrees": list(pair),
                "original_weight": entry["original_weight"],
                "effective_probability": entry["effective_probability"],
            }
        )
    return records


# ============================================================
# 1. GERAÇÃO INDEPENDENTE DE F1..F4 PELO TOADA_PROFILE
# ============================================================

def generate_family(
    family_id: str,
    rng_family: random.Random,
) -> FamilyBackbone:
    """
    FAMILY -> START MOVE MOVE MOVE MOVE MOVE CADENCE

    Cada chamada é uma nova derivação da mesma gramática. Não existe
    TOADA_BASE compartilhada e nenhuma família é derivada de outra.
    """
    initial_degree = rng_family.choice(list(START_DEGREES))
    degrees = [initial_degree]
    current = initial_degree

    internal_moves: list[dict[str, Any]] = []

    # Slots 2..6.
    for position in range(2, 7):
        valid_rules: list[tuple[tuple[str, int], float]] = []

        for name, delta, probability in MOVE_RULES:
            candidate = current + delta
            if 1 <= candidate <= 7:
                valid_rules.append(((name, delta), probability))

        (move_name, delta), effective = weighted_choice_with_probabilities(
            rng_family,
            valid_rules,
        )
        next_degree = current + delta

        effective_records = [
            {
                "production": entry["item"][0],
                "delta": entry["item"][1],
                "original_weight": entry["original_weight"],
                "effective_probability": entry["effective_probability"],
            }
            for entry in effective
        ]

        internal_moves.append(
            {
                "position": position,
                "production": move_name,
                "delta": delta,
                "degree_before": current,
                "degree_after": next_degree,
                "effective_probabilities": effective_records,
            }
        )

        degrees.append(next_degree)
        current = next_degree

    cadence_choices = [
        ((name, pair), probability)
        for name, pair, probability in CADENCE_RULES
    ]
    (cadence_name, cadence_degrees), cadence_effective = weighted_choice_with_probabilities(
        rng_family,
        cadence_choices,
    )

    degrees.extend(cadence_degrees)

    trace = {
        "family_id": family_id,
        "grammar": "FAMILY -> START MOVE MOVE MOVE MOVE MOVE CADENCE",
        "initial_degree": initial_degree,
        "initial_degree_probabilities": {
            str(degree): 1.0 / len(START_DEGREES)
            for degree in START_DEGREES
        },
        "internal_moves": internal_moves,
        "cadence": {
            "production": cadence_name,
            "degrees": list(cadence_degrees),
            "effective_probabilities": cadence_effective_records(cadence_effective),
            "note": (
                "Catálogo cadencial definido como decisão computacional da V2.4; "
                "não é tratado como regra histórica da décima espinela."
            ),
        },
    }

    return FamilyBackbone(
        family_id=family_id,
        pitches=tuple(PitchSpec(degree=d, octave_offset=0) for d in degrees),
        generation_trace=trace,
    )


def generate_all_families(
    rng_family: random.Random,
) -> dict[str, FamilyBackbone]:
    # Quatro execuções independentes da mesma gramática/profiling rules.
    return {
        family_id: generate_family(family_id, rng_family)
        for family_id in FAMILY_IDS
    }


# ============================================================
# 2. RITMOS-BASE POR FAMÍLIA F
# ============================================================

def generate_rhythm_backbone(
    family_id: str,
    rng_rhythm: random.Random,
) -> RhythmBackbone:
    cell_indices = tuple(
        rng_rhythm.randrange(len(RHYTHM_CELLS))
        for _ in range(4)
    )

    durations: list[float] = []
    for cell_index in cell_indices:
        durations.extend(RHYTHM_CELLS[cell_index])

    return RhythmBackbone(
        family_id=family_id,
        cell_indices=cell_indices,
        durations=tuple(durations),
    )


def generate_all_rhythms(
    rng_rhythm: random.Random,
) -> dict[str, RhythmBackbone]:
    return {
        family_id: generate_rhythm_backbone(family_id, rng_rhythm)
        for family_id in FAMILY_IDS
    }


# ============================================================
# 3. PERMUTAÇÃO F -> R
# ============================================================

def generate_role_mapping(
    rng_role: random.Random,
) -> dict[str, str]:
    shuffled_families = list(FAMILY_IDS)
    rng_role.shuffle(shuffled_families)
    return {
        role: family_id
        for role, family_id in zip(ROLES, shuffled_families)
    }


# ============================================================
# 4. PERMUTAÇÃO R -> INSTRUMENTO
# ============================================================

def resolve_midi_instrument(preferred: str, fallback: str | None) -> tuple[str, int]:
    try:
        program = pretty_midi.instrument_name_to_program(preferred)
        return preferred, program
    except ValueError:
        if fallback is None:
            raise
        program = pretty_midi.instrument_name_to_program(fallback)
        return fallback, program


def generate_instrument_assignment(
    rng_instrument: random.Random,
) -> dict[str, InstrumentAssignment]:
    specs = [dict(spec) for spec in CULTURAL_INSTRUMENTS]
    rng_instrument.shuffle(specs)

    result: dict[str, InstrumentAssignment] = {}

    for role, spec in zip(ROLES, specs):
        midi_instrument, midi_program = resolve_midi_instrument(
            spec["preferred_midi_instrument"],
            spec["fallback_midi_instrument"],
        )

        # Hífen ASCII para compatibilidade com metadados MIDI Latin-1.
        track_name = f"{role} - {spec['track_label']}"

        result[role] = InstrumentAssignment(
            role=role,
            cultural_label=spec["cultural_label"],
            track_label=spec["track_label"],
            midi_instrument=midi_instrument,
            midi_program=midi_program,
            track_name=track_name,
            proxy_note=(
                f"{spec['cultural_label']} é rótulo cultural do projeto; "
                f"o timbre General MIDI/MuseScore usado como proxy é {midi_instrument}."
            ),
        )

    return result


# ============================================================
# 5. MICROVARIAÇÕES POR OCORRÊNCIA
# ============================================================

def realize_phrase(
    phrase_index: int,
    role: str,
    family_id: str,
    role_occurrence: int,
    family: FamilyBackbone,
    rhythm: RhythmBackbone,
    instrument: InstrumentAssignment,
    config: Config,
    rng_micro: random.Random,
) -> Phrase:
    events: list[Event] = []
    micro_decisions: list[dict[str, Any]] = []
    microvariations: list[dict[str, Any]] = []

    for position, (backbone_pitch, duration) in enumerate(
        zip(family.pitches, rhythm.durations),
        start=1,
    ):
        if backbone_pitch.octave_offset != 0:
            raise RuntimeError("V2.4 recebeu octave_offset != 0 no backbone")

        realized_degree = backbone_pitch.degree
        microvaried = False

        if position in MUTABLE_POSITIONS:
            # Sempre dois draws por posição. Assim seed igual + estrutura igual
            # implica o mesmo fluxo aleatório para qualquer p_var.
            gate = rng_micro.random()
            selector = rng_micro.random()

            valid_deltas = [
                delta
                for delta in (-1, +1)
                if 1 <= backbone_pitch.degree + delta <= 7
            ]
            proposed_delta = select_from_unit_interval(selector, valid_deltas)
            proposed_degree = backbone_pitch.degree + proposed_delta
            applied = gate < config.p_var

            micro_decisions.append(
                {
                    "position": position,
                    "gate": gate,
                    "selector": selector,
                    "valid_deltas": list(valid_deltas),
                    "proposed_delta": proposed_delta,
                    "degree_before": backbone_pitch.degree,
                    "degree_after_if_applied": proposed_degree,
                    "applied": applied,
                }
            )

            if applied:
                realized_degree = proposed_degree
                microvaried = True

                microvariations.append(
                    {
                        "position": position,
                        "gate": gate,
                        "selector": selector,
                        "degree_before": backbone_pitch.degree,
                        "degree_after": realized_degree,
                        "octave_offset": 0,
                        "midi_before": degree_to_midi(
                            backbone_pitch.degree, 0, config.tonic_midi
                        ),
                        "midi_after": degree_to_midi(
                            realized_degree, 0, config.tonic_midi
                        ),
                    }
                )

        events.append(
            Event(
                phrase_index=phrase_index,
                family_id=family_id,
                role=role,
                position=position,
                backbone_degree=backbone_pitch.degree,
                backbone_octave_offset=0,
                backbone_midi=degree_to_midi(
                    backbone_pitch.degree, 0, config.tonic_midi
                ),
                realized_degree=realized_degree,
                realized_octave_offset=0,
                realized_midi=degree_to_midi(
                    realized_degree, 0, config.tonic_midi
                ),
                duration=duration,
                velocity=config.velocity,
                microvaried=microvaried,
            )
        )

    return Phrase(
        index=phrase_index,
        family_id=family_id,
        role=role,
        role_occurrence=role_occurrence,
        instrument=instrument,
        events=tuple(events),
        micro_decisions=tuple(micro_decisions),
        microvariations=tuple(microvariations),
    )


# ============================================================
# PERCUSSÃO — GRAMÁTICA PROBABILÍSTICA DE 20 COMPASSOS
# ============================================================

def make_percussion_rng(seed: int) -> random.Random:
    return random.Random(derive_stream_seed(seed, "percussion"))


def generate_percussion(seed: int) -> PercussionArrangement:
    rng = make_percussion_rng(seed)
    choices = [
        (name, spec["probability"])
        for name, spec in PERCUSSION_PATTERNS.items()
    ]

    cells: list[PercussionCell] = []

    for bar_index in range(1, PERCUSSION_BAR_COUNT + 1):
        production, _effective = weighted_choice_with_probabilities(rng, choices)
        spec = PERCUSSION_PATTERNS[production]

        hits = tuple(
            PercussionHit(
                bar_index=bar_index,
                pattern=production,
                beat_in_bar=beat,
                midi_note=midi_note,
                gm_name=PERCUSSION_GM_NAMES[midi_note],
                velocity=velocity,
            )
            for beat, midi_note, velocity in spec["hits"]
        )

        cells.append(
            PercussionCell(
                bar_index=bar_index,
                production=production,
                probability=spec["probability"],
                hits=hits,
            )
        )

    return PercussionArrangement(cells=tuple(cells))


# ============================================================
# 6. GERAÇÃO DA COMPOSIÇÃO
# ============================================================

def generate_song(config: Config) -> Song:
    if not 0.0 <= config.p_var <= 1.0:
        raise ValueError("p_var deve estar entre 0 e 1")

    (
        rng_family,
        rng_rhythm,
        rng_role,
        rng_instrument,
        rng_micro,
    ) = make_rngs(config.seed)

    families = generate_all_families(rng_family)
    rhythms = generate_all_rhythms(rng_rhythm)
    role_mapping = generate_role_mapping(rng_role)
    instruments = generate_instrument_assignment(rng_instrument)

    occurrence_counter = {role: 0 for role in ROLES}
    phrases: list[Phrase] = []

    for phrase_index, role in enumerate(STRUCTURE, start=1):
        occurrence_counter[role] += 1
        family_id = role_mapping[role]

        phrases.append(
            realize_phrase(
                phrase_index=phrase_index,
                role=role,
                family_id=family_id,
                role_occurrence=occurrence_counter[role],
                family=families[family_id],
                rhythm=rhythms[family_id],
                instrument=instruments[role],
                config=config,
                rng_micro=rng_micro,
            )
        )

    percussion = generate_percussion(config.seed)

    return Song(
        config=config,
        families=families,
        rhythms=rhythms,
        role_mapping=role_mapping,
        instruments=instruments,
        phrases=tuple(phrases),
        percussion=percussion,
    )


# ============================================================
# ASSINATURAS / REPRODUTIBILIDADE
# ============================================================

def family_signature(song: Song) -> tuple:
    return tuple(
        (
            family_id,
            tuple((p.degree, p.octave_offset) for p in song.families[family_id].pitches),
        )
        for family_id in FAMILY_IDS
    )


def family_cadence_signature(song: Song) -> tuple:
    return tuple(
        (
            family_id,
            song.families[family_id].generation_trace["cadence"]["production"],
            tuple(song.families[family_id].generation_trace["cadence"]["degrees"]),
        )
        for family_id in FAMILY_IDS
    )


def rhythm_signature(song: Song) -> tuple:
    return tuple(
        (family_id, tuple(song.rhythms[family_id].durations))
        for family_id in FAMILY_IDS
    )


def role_mapping_signature(song: Song) -> tuple:
    return tuple((role, song.role_mapping[role]) for role in ROLES)


def instrument_signature(song: Song) -> tuple:
    return tuple(
        (
            role,
            song.instruments[role].cultural_label,
            song.instruments[role].midi_instrument,
            song.instruments[role].midi_program,
        )
        for role in ROLES
    )


def percussion_signature(song: Song) -> tuple:
    return tuple(
        (
            cell.bar_index,
            cell.production,
            tuple(
                (hit.beat_in_bar, hit.midi_note, hit.velocity)
                for hit in cell.hits
            ),
        )
        for cell in song.percussion.cells
    )


def micro_flow_signature(song: Song) -> tuple:
    """Ignora apenas applied, pois ele depende de p_var."""
    result: list[tuple[Any, ...]] = []

    for phrase in song.phrases:
        for decision in phrase.micro_decisions:
            result.append(
                (
                    phrase.index,
                    phrase.role,
                    phrase.family_id,
                    decision["position"],
                    decision["gate"],
                    decision["selector"],
                    tuple(decision["valid_deltas"]),
                    decision["proposed_delta"],
                    decision["degree_before"],
                    decision["degree_after_if_applied"],
                )
            )

    return tuple(result)


def realized_signature(song: Song) -> tuple:
    return tuple(
        (
            phrase.index,
            phrase.role,
            phrase.family_id,
            tuple(
                (
                    event.position,
                    event.realized_degree,
                    event.realized_octave_offset,
                    event.realized_midi,
                    event.duration,
                )
                for event in phrase.events
            ),
        )
        for phrase in song.phrases
    )


def mutation_map(song: Song) -> dict[tuple[int, int], tuple[int, int]]:
    result: dict[tuple[int, int], tuple[int, int]] = {}
    for phrase in song.phrases:
        for event in phrase.events:
            if event.microvaried:
                result[(phrase.index, event.position)] = (
                    event.backbone_midi,
                    event.realized_midi,
                )
    return result


# ============================================================
# VALIDAÇÃO DA COMPOSIÇÃO
# ============================================================

def validate_song(song: Song) -> dict[str, bool]:
    all_events = [event for phrase in song.phrases for event in phrase.events]
    valid_cadence_pairs = {tuple(pair) for _, pair, _ in CADENCE_RULES}

    checks: dict[str, bool] = {}

    checks["exactly_4_families"] = set(song.families) == set(FAMILY_IDS)
    checks["each_family_has_exactly_8_degrees"] = all(
        len(song.families[family_id].pitches) == 8
        for family_id in FAMILY_IDS
    )
    checks["family_degrees_valid"] = all(
        1 <= pitch.degree <= 7
        for family in song.families.values()
        for pitch in family.pitches
    )
    checks["family_start_degrees_valid"] = all(
        song.families[family_id].pitches[0].degree in START_DEGREES
        for family_id in FAMILY_IDS
    )
    checks["family_cadences_valid"] = all(
        (
            song.families[family_id].pitches[6].degree,
            song.families[family_id].pitches[7].degree,
        ) in valid_cadence_pairs
        for family_id in FAMILY_IDS
    )

    checks["role_mapping_keys_exact"] = set(song.role_mapping) == set(ROLES)
    checks["role_mapping_is_bijective_permutation"] = (
        len(song.role_mapping) == 4
        and set(song.role_mapping.values()) == set(FAMILY_IDS)
        and len(set(song.role_mapping.values())) == 4
    )

    checks["four_rhythm_backbones_exist"] = set(song.rhythms) == set(FAMILY_IDS)
    checks["each_rhythm_has_8_events"] = all(
        len(song.rhythms[family_id].durations) == 8
        for family_id in FAMILY_IDS
    )
    checks["every_rhythm_cell_sums_2_beats"] = all(
        math.isclose(
            sum(rhythm.durations[start:start + 2]),
            2.0,
            abs_tol=1e-9,
        )
        for rhythm in song.rhythms.values()
        for start in (0, 2, 4, 6)
    )

    checks["exactly_10_phrases"] = len(song.phrases) == 10
    checks["structure_is_R1R2R2R1R1R3R3R4R4R3"] = [
        phrase.role for phrase in song.phrases
    ] == STRUCTURE
    checks["corresponds_to_ABBAACCDDC"] = DISPLAY_FORM == "ABBAACCDDC"
    checks["exactly_8_events_per_phrase"] = all(
        len(phrase.events) == 8 for phrase in song.phrases
    )
    checks["exactly_80_total_events"] = len(all_events) == 80

    checks["role_phrase_positions_exact"] = all(
        tuple(phrase.index for phrase in song.phrases if phrase.role == role)
        == ROLE_PHRASE_INDICES[role]
        for role in ROLES
    )

    role_event_counts = {
        role: sum(len(phrase.events) for phrase in song.phrases if phrase.role == role)
        for role in ROLES
    }
    checks["role_event_counts_exact"] = role_event_counts == EXPECTED_EVENT_COUNTS

    checks["phrase_family_matches_role_mapping"] = all(
        phrase.family_id == song.role_mapping[phrase.role]
        for phrase in song.phrases
    )

    checks["every_phrase_is_8_beats"] = all(
        math.isclose(sum(event.duration for event in phrase.events), 8.0, abs_tol=1e-9)
        for phrase in song.phrases
    )

    checks["phrases_use_assigned_family_backbone"] = all(
        event.backbone_degree
        == song.families[phrase.family_id].pitches[event.position - 1].degree
        for phrase in song.phrases
        for event in phrase.events
    )
    checks["phrases_use_assigned_family_rhythm"] = all(
        math.isclose(
            event.duration,
            song.rhythms[phrase.family_id].durations[event.position - 1],
            abs_tol=1e-9,
        )
        for phrase in song.phrases
        for event in phrase.events
    )

    checks["all_octave_offsets_zero"] = all(
        pitch.octave_offset == 0
        for family in song.families.values()
        for pitch in family.pitches
    ) and all(
        event.backbone_octave_offset == 0
        and event.realized_octave_offset == 0
        for event in all_events
    )

    checks["protected_slots_never_microvaried"] = all(
        not event.microvaried
        for event in all_events
        if event.position in PROTECTED_POSITIONS
    )
    checks["microvariation_only_positions_2_to_6"] = all(
        event.position in MUTABLE_POSITIONS
        for event in all_events
        if event.microvaried
    )

    checks["durations_positive"] = all(event.duration > 0 for event in all_events)
    checks["realized_degrees_valid"] = all(
        1 <= event.realized_degree <= 7 for event in all_events
    )
    checks["midi_pitches_valid"] = all(
        0 <= event.realized_midi <= 127 for event in all_events
    )

    checks["four_instrument_assignments_exist"] = set(song.instruments) == set(ROLES)
    checks["instrument_mapping_is_bijective"] = (
        len({song.instruments[role].cultural_label for role in ROLES}) == 4
        and len({song.instruments[role].midi_instrument for role in ROLES}) == 4
    )
    checks["phrase_instrument_matches_role"] = all(
        phrase.instrument == song.instruments[phrase.role]
        for phrase in song.phrases
    )

    checks["exactly_20_percussion_cells"] = len(song.percussion.cells) == 20
    checks["percussion_bar_indices_exact"] = tuple(
        cell.bar_index for cell in song.percussion.cells
    ) == tuple(range(1, 21))
    checks["percussion_productions_valid"] = all(
        cell.production in PERCUSSION_PATTERNS
        and math.isclose(
            cell.probability,
            PERCUSSION_PATTERNS[cell.production]["probability"],
            abs_tol=1e-12,
        )
        for cell in song.percussion.cells
    )
    checks["percussion_hits_valid"] = all(
        0.0 <= hit.beat_in_bar < 4.0
        and hit.midi_note in PERCUSSION_GM_NAMES
        and 1 <= hit.velocity <= 127
        for cell in song.percussion.cells
        for hit in cell.hits
    )

    regenerated = generate_song(song.config)
    checks["same_seed_and_config_are_reproducible"] = (
        family_signature(song) == family_signature(regenerated)
        and family_cadence_signature(song) == family_cadence_signature(regenerated)
        and rhythm_signature(song) == rhythm_signature(regenerated)
        and role_mapping_signature(song) == role_mapping_signature(regenerated)
        and instrument_signature(song) == instrument_signature(regenerated)
        and percussion_signature(song) == percussion_signature(regenerated)
        and micro_flow_signature(song) == micro_flow_signature(regenerated)
        and realized_signature(song) == realized_signature(regenerated)
    )

    checks["all_valid"] = all(checks.values())
    return checks


# ============================================================
# VALIDAÇÃO M1 × M3
# ============================================================

def validate_experiment(m1: Song, m3: Song) -> dict[str, bool]:
    m1_mutations = mutation_map(m1)
    m3_mutations = mutation_map(m3)

    m1_is_subset = all(
        key in m3_mutations and m3_mutations[key] == value
        for key, value in m1_mutations.items()
    )

    checks = {
        "same_seed": m1.config.seed == m3.config.seed,
        "same_F1_F2_F3_F4": family_signature(m1) == family_signature(m3),
        "same_family_cadences": family_cadence_signature(m1) == family_cadence_signature(m3),
        "same_family_rhythms": rhythm_signature(m1) == rhythm_signature(m3),
        "same_role_mapping_F_to_R": role_mapping_signature(m1) == role_mapping_signature(m3),
        "same_instrument_mapping_R_to_instrument": instrument_signature(m1) == instrument_signature(m3),
        "same_percussion_arrangement": percussion_signature(m1) == percussion_signature(m3),
        "same_micro_random_flow": micro_flow_signature(m1) == micro_flow_signature(m3),
        "m1_microvariations_are_subset_of_m3": m1_is_subset,
        "realized_outputs_are_different": realized_signature(m1) != realized_signature(m3),
    }
    checks["all_valid"] = all(checks.values())
    return checks


# ============================================================
# MÉTRICAS
# ============================================================

def phrase_similarity(phrase_a: Phrase, phrase_b: Phrase) -> dict[str, float]:
    if len(phrase_a.events) != 8 or len(phrase_b.events) != 8:
        raise ValueError("Similaridade exige frases de 8 eventos")

    pitch_equal = 0
    rhythm_equal = 0
    combined_equal = 0

    for event_a, event_b in zip(phrase_a.events, phrase_b.events):
        same_pitch = event_a.realized_midi == event_b.realized_midi
        same_rhythm = math.isclose(event_a.duration, event_b.duration, abs_tol=1e-9)

        pitch_equal += int(same_pitch)
        rhythm_equal += int(same_rhythm)
        combined_equal += int(same_pitch and same_rhythm)

    return {
        "pitch_similarity": pitch_equal / 8.0,
        "rhythm_similarity": rhythm_equal / 8.0,
        "combined_similarity": combined_equal / 8.0,
    }


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def family_pitch_similarity(
    family_a: FamilyBackbone,
    family_b: FamilyBackbone,
    tonic_midi: int,
) -> float:
    equal = sum(
        int(
            degree_to_midi(a.degree, a.octave_offset, tonic_midi)
            == degree_to_midi(b.degree, b.octave_offset, tonic_midi)
        )
        for a, b in zip(family_a.pitches, family_b.pitches)
    )
    return equal / 8.0


def compute_family_similarity_matrix(song: Song) -> tuple[dict[str, dict[str, float]], list[float]]:
    matrix: dict[str, dict[str, float]] = {}

    for family_a in FAMILY_IDS:
        matrix[family_a] = {}
        for family_b in FAMILY_IDS:
            matrix[family_a][family_b] = family_pitch_similarity(
                song.families[family_a],
                song.families[family_b],
                song.config.tonic_midi,
            )

    off_diagonal = [
        matrix[a][b]
        for a, b in combinations(FAMILY_IDS, 2)
    ]
    return matrix, off_diagonal


def compute_metrics(song: Song) -> dict[str, Any]:
    eligible_positions = len(song.phrases) * len(MUTABLE_POSITIONS)
    microvariation_count = sum(
        int(event.microvaried)
        for phrase in song.phrases
        for event in phrase.events
    )

    intra_pairs: list[dict[str, Any]] = []
    inter_pairs: list[dict[str, Any]] = []
    intra_pitch: list[float] = []
    inter_pitch: list[float] = []
    intra_rhythm: list[float] = []
    inter_rhythm: list[float] = []
    intra_combined: list[float] = []
    inter_combined: list[float] = []

    for phrase_a, phrase_b in combinations(song.phrases, 2):
        similarities = phrase_similarity(phrase_a, phrase_b)
        record = {
            "phrase_i": phrase_a.index,
            "phrase_j": phrase_b.index,
            "role_i": phrase_a.role,
            "role_j": phrase_b.role,
            "family_i": phrase_a.family_id,
            "family_j": phrase_b.family_id,
            **similarities,
        }

        if phrase_a.role == phrase_b.role:
            intra_pairs.append(record)
            intra_pitch.append(similarities["pitch_similarity"])
            intra_rhythm.append(similarities["rhythm_similarity"])
            intra_combined.append(similarities["combined_similarity"])
        else:
            inter_pairs.append(record)
            inter_pitch.append(similarities["pitch_similarity"])
            inter_rhythm.append(similarities["rhythm_similarity"])
            inter_combined.append(similarities["combined_similarity"])

    family_matrix, family_pair_values = compute_family_similarity_matrix(song)

    return {
        "eligible_microvariation_positions": eligible_positions,
        "microvariation_count": microvariation_count,
        "observed_microvariation_rate": microvariation_count / eligible_positions,

        # Métricas separadas: não mascarar pitch com ritmo.
        "pitch_similarity_intra": mean(intra_pitch),
        "pitch_similarity_inter": mean(inter_pitch),
        "rhythm_similarity_intra": mean(intra_rhythm),
        "rhythm_similarity_inter": mean(inter_rhythm),
        "combined_similarity_intra": mean(intra_combined),
        "combined_similarity_inter": mean(inter_combined),
        "pitch_intra_greater_than_inter": mean(intra_pitch) > mean(inter_pitch),
        "combined_intra_greater_than_inter": mean(intra_combined) > mean(inter_combined),

        "intra_class_pair_count": len(intra_pairs),
        "inter_class_pair_count": len(inter_pairs),
        "intra_class_pairs": intra_pairs,
        "inter_class_pairs": inter_pairs,

        # F1..F4 antes da atribuição a R.
        "family_pitch_similarity_matrix": family_matrix,
        "mean_family_pitch_similarity": mean(family_pair_values),
        "max_family_pitch_similarity": max(family_pair_values),
        "min_family_pitch_similarity": min(family_pair_values),
        "family_similarity_is_analysis_only": True,
    }


# ============================================================
# MIDI — QUATRO TRACKS, UMA POR PAPEL R
# ============================================================

def build_pretty_midi(song: Song) -> pretty_midi.PrettyMIDI:
    pm = pretty_midi.PrettyMIDI(initial_tempo=song.config.bpm)
    pm.time_signature_changes.append(pretty_midi.TimeSignature(4, 4, 0.0))

    tracks = {
        role: pretty_midi.Instrument(
            program=song.instruments[role].midi_program,
            is_drum=False,
            name=song.instruments[role].track_name,
        )
        for role in ROLES
    }

    seconds_per_beat = 60.0 / song.config.bpm
    current_beat = 0.0

    for phrase in song.phrases:
        track = tracks[phrase.role]

        for event in phrase.events:
            start = current_beat * seconds_per_beat
            end = (current_beat + event.duration) * seconds_per_beat

            track.notes.append(
                pretty_midi.Note(
                    velocity=event.velocity,
                    pitch=event.realized_midi,
                    start=start,
                    end=end,
                )
            )
            current_beat += event.duration

    for role in ROLES:
        pm.instruments.append(tracks[role])

    percussion_track = pretty_midi.Instrument(
        program=0,
        is_drum=True,
        name=PERCUSSION_TRACK_NAME,
    )

    # 20 compassos × 4 beats = 80 beats, exatamente a duração melódica.
    hit_duration_seconds = 0.08
    for cell in song.percussion.cells:
        bar_start_beat = (cell.bar_index - 1) * 4.0
        for hit in cell.hits:
            start = (bar_start_beat + hit.beat_in_bar) * seconds_per_beat
            percussion_track.notes.append(
                pretty_midi.Note(
                    velocity=hit.velocity,
                    pitch=hit.midi_note,
                    start=start,
                    end=start + hit_duration_seconds,
                )
            )

    pm.instruments.append(percussion_track)

    return pm


def validate_midi_structure(
    pm: pretty_midi.PrettyMIDI,
    song: Song,
) -> dict[str, bool]:
    checks: dict[str, bool] = {}

    checks["exactly_5_instrument_tracks"] = len(pm.instruments) == 5

    by_name = {instrument.name: instrument for instrument in pm.instruments}
    expected_names = {song.instruments[role].track_name for role in ROLES} | {PERCUSSION_TRACK_NAME}
    checks["track_names_exact"] = set(by_name) == expected_names

    tracks_by_role: dict[str, pretty_midi.Instrument] = {}
    for role in ROLES:
        assignment = song.instruments[role]
        track = by_name.get(assignment.track_name)
        if track is not None:
            tracks_by_role[role] = track

    checks["track_programs_match_assignment"] = (
        len(tracks_by_role) == 4
        and all(
            tracks_by_role[role].program == song.instruments[role].midi_program
            for role in ROLES
        )
    )

    checks["track_note_counts_exact"] = (
        len(tracks_by_role) == 4
        and all(
            len(tracks_by_role[role].notes) == EXPECTED_EVENT_COUNTS[role]
            for role in ROLES
        )
    )

    checks["total_melodic_midi_notes_80"] = (
        len(tracks_by_role) == 4
        and sum(len(track.notes) for track in tracks_by_role.values()) == 80
    )

    percussion_track = by_name.get(PERCUSSION_TRACK_NAME)
    expected_percussion_hits = sum(
        len(cell.hits) for cell in song.percussion.cells
    )
    checks["percussion_track_is_drum"] = (
        percussion_track is not None and percussion_track.is_drum
    )
    checks["percussion_note_count_exact"] = (
        percussion_track is not None
        and len(percussion_track.notes) == expected_percussion_hits
    )
    checks["percussion_notes_use_expected_GM_keys"] = (
        percussion_track is not None
        and all(
            note.pitch in PERCUSSION_GM_NAMES
            for note in percussion_track.notes
        )
    )

    seconds_per_beat = 60.0 / song.config.bpm
    phrase_seconds = 8.0 * seconds_per_beat
    eps = 1e-7

    windows_ok = len(tracks_by_role) == 4
    if windows_ok:
        for role in ROLES:
            track = tracks_by_role[role]
            expected_phrase_indices = set(ROLE_PHRASE_INDICES[role])

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
    checks["all_valid"] = all(checks.values())
    return checks


# ============================================================
# WAV VIA MUSESCORE
# ============================================================

def musescore_command(midi_path: Path, wav_path: Path) -> list[str]:
    if shutil.which("flatpak-spawn"):
        return [
            "flatpak-spawn",
            "--host",
            "flatpak",
            "run",
            "org.musescore.MuseScore",
            "-o",
            str(wav_path),
            str(midi_path),
        ]

    if shutil.which("flatpak"):
        return [
            "flatpak",
            "run",
            "org.musescore.MuseScore",
            "-o",
            str(wav_path),
            str(midi_path),
        ]

    for executable in ("musescore", "mscore", "MuseScore4"):
        if shutil.which(executable):
            return [executable, "-o", str(wav_path), str(midi_path)]

    raise RuntimeError(
        "MuseScore não foi localizado. Instale-o ou execute em ambiente com "
        "flatpak-spawn/flatpak disponível."
    )


def render_wav_with_musescore(midi_path: Path, wav_path: Path) -> None:
    command = musescore_command(midi_path, wav_path)

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
        raise RuntimeError(f"MuseScore terminou sem criar: {wav_path}")


# ============================================================
# METADADOS
# ============================================================

def family_to_dict(family: FamilyBackbone, config: Config) -> dict[str, Any]:
    return {
        "family_id": family.family_id,
        "family_backbone": [
            {
                **pitch_spec_to_dict(pitch),
                "midi_pitch": degree_to_midi(
                    pitch.degree,
                    pitch.octave_offset,
                    config.tonic_midi,
                ),
            }
            for pitch in family.pitches
        ],
        "family_generation_trace": family.generation_trace,
    }


def rhythm_to_dict(rhythm: RhythmBackbone) -> dict[str, Any]:
    return {
        "family_id": rhythm.family_id,
        "cell_indices": list(rhythm.cell_indices),
        "cells": [list(RHYTHM_CELLS[index]) for index in rhythm.cell_indices],
        "family_rhythm": list(rhythm.durations),
        "cell_probability": 1.0 / len(RHYTHM_CELLS),
    }


def instrument_to_dict(assignment: InstrumentAssignment) -> dict[str, Any]:
    return {
        "role": assignment.role,
        "cultural_label": assignment.cultural_label,
        "track_label": assignment.track_label,
        "midi_instrument": assignment.midi_instrument,
        "program": assignment.midi_program,
        "track_name": assignment.track_name,
        "proxy_note": assignment.proxy_note,
    }


def phrase_to_dict(phrase: Phrase, song: Song) -> dict[str, Any]:
    return {
        "phrase_index": phrase.index,
        "family_id": phrase.family_id,
        "role": phrase.role,
        "role_occurrence": phrase.role_occurrence,
        "family_backbone": [
            pitch_spec_to_dict(pitch)
            for pitch in song.families[phrase.family_id].pitches
        ],
        "family_rhythm": list(song.rhythms[phrase.family_id].durations),
        "instrument": instrument_to_dict(phrase.instrument),
        "seed": song.config.seed,
        "p_var": song.config.p_var,
        "microvariation_positions": [m["position"] for m in phrase.microvariations],
        "micro_decisions": list(phrase.micro_decisions),
        "microvariations": list(phrase.microvariations),
        "events": [
            {
                "position": event.position,
                "family_id": event.family_id,
                "role": event.role,
                "backbone_degree": event.backbone_degree,
                "backbone_octave_offset": event.backbone_octave_offset,
                "backbone_midi": event.backbone_midi,
                "realized_degree": event.realized_degree,
                "realized_octave_offset": event.realized_octave_offset,
                "realized_midi": event.realized_midi,
                "duration": event.duration,
                "velocity": event.velocity,
                "microvaried": event.microvaried,
            }
            for event in phrase.events
        ],
    }


def toada_profile_metadata() -> dict[str, Any]:
    return {
        "description": (
            "TOADA_PROFILE é somente o conjunto comum de regras geradoras da V2.4; "
            "não é uma sequência melódica compartilhada entre as famílias."
        ),
        "pitch_collection": "C major degrees 1..7",
        "register": "single register; octave_offset = 0",
        "start_degrees": {
            str(degree): 1.0 / len(START_DEGREES)
            for degree in START_DEGREES
        },
        "move_rules": [
            {"production": name, "delta": delta, "probability": probability}
            for name, delta, probability in MOVE_RULES
        ],
        "cadence_rules": [
            {"production": name, "degrees": list(pair), "probability": probability}
            for name, pair, probability in CADENCE_RULES
        ],
        "rhythm_cells": [list(cell) for cell in RHYTHM_CELLS],
        "rhythm_cell_probability": 1.0 / len(RHYTHM_CELLS),
        "bpm": BPM,
    }


def save_metadata(
    song: Song,
    validation: dict[str, bool],
    midi_validation: dict[str, bool],
    metrics: dict[str, Any],
    experiment_validation: dict[str, bool],
    path: Path,
) -> None:
    inverse_mapping = {
        family_id: role for role, family_id in song.role_mapping.items()
    }

    payload = {
        "version": "V2.5",
        "config": {
            "name": song.config.name,
            "seed": song.config.seed,
            "p_var": song.config.p_var,
            "bpm": song.config.bpm,
            "time_signature": "4/4",
            "tonic_midi": song.config.tonic_midi,
            "velocity": song.config.velocity,
            "internal_structure": "R1 R2 R2 R1 R1 R3 R3 R4 R4 R3",
            "display_correspondence": DISPLAY_FORM,
            "rng_stream_seeds": {
                name: derive_stream_seed(song.config.seed, name)
                for name in ("family", "rhythm", "role", "instrument", "micro", "percussion")
            },
        },
        "conceptual_note": (
            "O mapeamento 10 versos -> 10 frases, 8 sílabas -> 8 eventos e "
            "ABBAACCDDC -> papéis recorrentes é uma decisão computacional do projeto. "
            "TOADA_PROFILE não é uma regra histórica da décima espinela."
        ),
        "formal_grammar": {
            "family_rule": "FAMILY -> START MOVE MOVE MOVE MOVE MOVE CADENCE",
            "axiom_rule": "S -> R1 R2 R2 R1 R1 R3 R3 R4 R4 R3",
            "display_correspondence": "ABBAACCDDC",
            "family_creation": (
                "F1,F2,F3,F4 são quatro derivações independentes da mesma gramática; "
                "não existe TOADA_BASE compartilhada."
            ),
            "role_assignment": "permute(F1,F2,F3,F4) -> R1,R2,R3,R4",
            "microvariation_rule": (
                "positions 2..6: PRESERVE [1-p_var] | ALTER_DEGREE(±1 valid) [p_var]"
            ),
            "protected_positions": list(PROTECTED_POSITIONS),
            "octave_offset_rule": "octave_offset = 0 for every melodic event; unchanged from V2.4",
            "percussion_rule": (
                "PERCUSSION -> PERC_CELL^20; "
                "PERC_CELL -> BASIC_A[0.40] | BASIC_B[0.30] | BASIC_C[0.20] | FILL[0.10]"
            ),
        },
        "toada_profile": toada_profile_metadata(),
        "families": {
            family_id: {
                **family_to_dict(song.families[family_id], song.config),
                "rhythm": rhythm_to_dict(song.rhythms[family_id]),
                "assigned_role": inverse_mapping[family_id],
            }
            for family_id in FAMILY_IDS
        },
        "role_mapping": {
            role: song.role_mapping[role]
            for role in ROLES
        },
        "family_to_role_mapping": inverse_mapping,
        "instrument_mapping": {
            role: instrument_to_dict(song.instruments[role])
            for role in ROLES
        },
        "instrumentation_note": (
            "A viola é a referência cultural central à cantoria neste projeto. "
            "Rabeca, sanfona e violão são escolhas de orquestração de inspiração "
            "nordestina; os timbres General MIDI/MuseScore são proxies explícitos, "
            "não uma afirmação de instrumentação tradicional fixa do repente."
        ),
        "percussion_note": (
            "A camada de percussão é uma escolha de arranjo inspirada no universo nordestino, "
            "não uma reconstrução histórica da instrumentação tradicional da cantoria. "
            "Bass Drum 1 funciona como proxy grave de zabumba e Mute/Open Triangle como "
            "proxies agudos de triângulo."
        ),
        "percussion": {
            "track_name": PERCUSSION_TRACK_NAME,
            "is_drum": True,
            "rng_stream_seed": derive_stream_seed(song.config.seed, "percussion"),
            "gm_notes": {str(note): name for note, name in PERCUSSION_GM_NAMES.items()},
            "grammar_probabilities": {
                name: spec["probability"]
                for name, spec in PERCUSSION_PATTERNS.items()
            },
            "cells": [
                {
                    "bar_index": cell.bar_index,
                    "production": cell.production,
                    "probability": cell.probability,
                    "hits": [
                        {
                            "beat_in_bar": hit.beat_in_bar,
                            "midi_note": hit.midi_note,
                            "gm_name": hit.gm_name,
                            "velocity": hit.velocity,
                        }
                        for hit in cell.hits
                    ],
                }
                for cell in song.percussion.cells
            ],
        },
        "validation": validation,
        "midi_validation": midi_validation,
        "experiment_validation": experiment_validation,
        "metrics": metrics,
        "phrases": [phrase_to_dict(phrase, song) for phrase in song.phrases],
    }

    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


# ============================================================
# SAÍDA
# ============================================================

def save_song_outputs(
    song: Song,
    output_dir: Path,
    experiment_validation: dict[str, bool],
) -> None:
    validation = validate_song(song)
    if not validation["all_valid"]:
        failed = [name for name, result in validation.items() if not result]
        raise RuntimeError(f"Falha de validação em {song.config.name}: {failed}")

    metrics = compute_metrics(song)

    midi_path = output_dir / f"{song.config.name}.mid"
    wav_path = output_dir / f"{song.config.name}.wav"
    json_path = output_dir / f"{song.config.name}.json"

    pm = build_pretty_midi(song)

    pre_write_midi_validation = validate_midi_structure(pm, song)
    if not pre_write_midi_validation["all_valid"]:
        failed = [
            name for name, result in pre_write_midi_validation.items() if not result
        ]
        raise RuntimeError(
            f"Falha de validação MIDI antes da escrita em {song.config.name}: {failed}"
        )

    pm.write(str(midi_path))

    reopened = pretty_midi.PrettyMIDI(str(midi_path))
    midi_validation = validate_midi_structure(reopened, song)
    if not midi_validation["all_valid"]:
        failed = [name for name, result in midi_validation.items() if not result]
        raise RuntimeError(
            f"Falha de validação do MIDI gravado em {song.config.name}: {failed}"
        )

    render_wav_with_musescore(midi_path, wav_path)

    save_metadata(
        song=song,
        validation=validation,
        midi_validation=midi_validation,
        metrics=metrics,
        experiment_validation=experiment_validation,
        path=json_path,
    )

    print()
    print(song.config.name.upper())
    print(f"  p_var={song.config.p_var:.2f}")
    print(f"  seed={song.config.seed}")
    print(
        "  famílias:",
        " | ".join(
            f"{family_id}=" + "-".join(
                str(p.degree) for p in song.families[family_id].pitches
            )
            for family_id in FAMILY_IDS
        ),
    )
    print(
        "  F→R:",
        " | ".join(f"{role}={song.role_mapping[role]}" for role in ROLES),
    )
    print(
        "  instrumentos:",
        " | ".join(
            f"{role}={song.instruments[role].track_label}"
            f"[{song.instruments[role].midi_instrument}]"
            for role in ROLES
        ),
    )
    print(
        "  percussão:",
        " ".join(cell.production for cell in song.percussion.cells),
    )
    print(
        "  microvariações: "
        f"{metrics['microvariation_count']}/"
        f"{metrics['eligible_microvariation_positions']} "
        f"({metrics['observed_microvariation_rate']:.3f})"
    )
    print(
        "  similaridade pitch intra/inter: "
        f"{metrics['pitch_similarity_intra']:.3f} / "
        f"{metrics['pitch_similarity_inter']:.3f}"
    )
    print(
        "  similaridade ritmo intra/inter: "
        f"{metrics['rhythm_similarity_intra']:.3f} / "
        f"{metrics['rhythm_similarity_inter']:.3f}"
    )
    print(
        "  similaridade combinada intra/inter: "
        f"{metrics['combined_similarity_intra']:.3f} / "
        f"{metrics['combined_similarity_inter']:.3f}"
    )
    print(
        "  famílias pitch mean/max/min: "
        f"{metrics['mean_family_pitch_similarity']:.3f} / "
        f"{metrics['max_family_pitch_similarity']:.3f} / "
        f"{metrics['min_family_pitch_similarity']:.3f}"
    )
    print("  Sim_pitch_intra > Sim_pitch_inter:", metrics["pitch_intra_greater_than_inter"])
    print(f"  MIDI: {midi_path}")
    print(f"  WAV MuseScore: {wav_path}")


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    base_dir = Path(__file__).resolve().parent
    output_dir = base_dir / "outputs_v25"
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

    experiment_validation = validate_experiment(
        songs["m1"],
        songs["m3"],
    )

    if not experiment_validation["all_valid"]:
        failed = [
            name
            for name, result in experiment_validation.items()
            if not result
        ]
        raise RuntimeError(
            f"Falha na validação experimental M1/M3: {failed}"
        )

    print("Validação cruzada V2.5:")
    print("  M1/M3 mesmas F1/F2/F3/F4: OK")
    print("  M1/M3 mesmas cadências das famílias: OK")
    print("  M1/M3 mesmos ritmos F1/F2/F3/F4: OK")
    print("  M1/M3 mesmo role_mapping F→R: OK")
    print("  M1/M3 mesma associação R↔instrumento: OK")
    print("  M1/M3 mesma percussão: OK")
    print("  M1/M3 mesmo fluxo rng_micro: OK")
    print("  microvariações de M1 contidas em M3: OK")
    print("  M1/M3 saídas realizadas diferentes: OK")

    experiment_path = output_dir / "experiment_validation.json"
    with experiment_path.open("w", encoding="utf-8") as file:
        json.dump(experiment_validation, file, ensure_ascii=False, indent=2)

    for config in configs:
        save_song_outputs(
            song=songs[config.name],
            output_dir=output_dir,
            experiment_validation=experiment_validation,
        )

    print()
    print(f"Arquivos V2.5 gerados em: {output_dir}")


if __name__ == "__main__":
    main()
