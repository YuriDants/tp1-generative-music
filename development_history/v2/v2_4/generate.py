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
# V2.3 — CANDIDATA FINAL PROCEDURAL
# ============================================================

STRUCTURE = ["R1", "R2", "R2", "R1", "R1", "R3", "R3", "R4", "R4", "R3"]
DISPLAY_FORM = "ABBAACCDDC"
ROLES = ("R1", "R2", "R3", "R4")

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

# Streams independentes derivados da mesma seed.
STREAM_MULTIPLIER = 1_000_003
STREAM_OFFSETS = {
    "toada": 11,
    "family": 23,
    "rhythm": 37,
    "instrument": 53,
    "micro": 71,
}

# Escala de C maior em um único registro coerente.
C_MAJOR_OFFSETS = {
    1: 0,
    2: 2,
    3: 4,
    4: 5,
    5: 7,
    6: 9,
    7: 11,
}

# ------------------------------------------------------------
# Gramática MOVE — slots 2..6 da TOADA_BASE.
# Produções inválidas são removidas antes do sorteio e os pesos
# restantes são renormalizados. Não existe clamp nem retry.
# ------------------------------------------------------------

MOVE_RULES = (
    ("STEP_UP", +1, 0.30),
    ("STEP_DOWN", -1, 0.30),
    ("REPEAT", 0, 0.15),
    ("LEAP_UP", +2, 0.125),
    ("LEAP_DOWN", -2, 0.125),
)

# ------------------------------------------------------------
# Gramática CADENCE — decisão computacional do projeto.
# NÃO representa uma afirmação histórica sobre o repente.
# ------------------------------------------------------------

CADENCE_RULES = (
    ("CAD_2_1", (2, 1), 0.35),
    ("CAD_3_1", (3, 1), 0.25),
    ("CAD_4_3", (4, 3), 0.20),
    ("CAD_2_3", (2, 3), 0.20),
)

CADENCE_BY_PAIR = {
    tuple(pair): (name, probability)
    for name, pair, probability in CADENCE_RULES
}

# ------------------------------------------------------------
# Transformações procedurais dos backbones.
# Cada passo escolhe uma categoria com P=0.25.
# Não existe busca, fitness, ranking ou rejeição por qualidade.
# ------------------------------------------------------------

FAMILY_TRANSFORMATIONS = (
    "PRESERVE",
    "ALTER_DEGREE",
    "INVERT_LOCAL_GESTURE",
    "ALTER_CADENCE",
)
N_FAMILY_TRANSFORMS = 3

# ------------------------------------------------------------
# Gramática rítmica por célula — equiprovável.
# ------------------------------------------------------------

RHYTHM_CELLS = (
    (1.0, 1.0),
    (0.5, 1.5),
    (1.5, 0.5),
)

# ------------------------------------------------------------
# Rótulos culturais e proxies General MIDI explícitos.
# A viola é a referência central da cantoria; os demais timbres
# são escolha de orquestração de inspiração nordestina do projeto.
# ------------------------------------------------------------

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
    # Mantido explicitamente no modelo/metadata, mas V2.3 exige 0.
    octave_offset: int = 0


@dataclass(frozen=True)
class FamilyBackbone:
    role: str
    pitches: tuple[PitchSpec, ...]
    initial_cadence_trace: dict[str, Any]
    final_cadence: dict[str, Any]
    transformation_trace: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class RhythmBackbone:
    role: str
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
class Event:
    phrase_index: int
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
    role: str
    role_occurrence: int
    instrument: InstrumentAssignment
    events: tuple[Event, ...]
    micro_decisions: tuple[dict[str, Any], ...]
    microvariations: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class Song:
    config: Config
    toada_base: tuple[PitchSpec, ...]
    toada_trace: dict[str, Any]
    families: dict[str, FamilyBackbone]
    rhythms: dict[str, RhythmBackbone]
    instruments: dict[str, InstrumentAssignment]
    phrases: tuple[Phrase, ...]


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
        random.Random(derive_stream_seed(seed, "toada")),
        random.Random(derive_stream_seed(seed, "family")),
        random.Random(derive_stream_seed(seed, "rhythm")),
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
    Sorteia entre escolhas válidas usando seus pesos originais.
    Retorna também as probabilidades efetivas após renormalização.
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


def cadence_rule_for_pair(pair: tuple[int, int]) -> tuple[str, float]:
    if pair not in CADENCE_BY_PAIR:
        raise ValueError(f"Cadência fora da gramática: {pair}")
    return CADENCE_BY_PAIR[pair]


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
# 1. TOADA_BASE PROCEDURAL
# ============================================================

def generate_toada_base(
    rng_toada: random.Random,
) -> tuple[tuple[PitchSpec, ...], dict[str, Any]]:

    initial_choices = [2, 3, 4, 5]
    initial_degree = rng_toada.choice(initial_choices)

    degrees = [initial_degree]
    internal_moves: list[dict[str, Any]] = []
    current = initial_degree

    # Slots 2..6.
    for position in range(2, 7):
        valid_rules: list[tuple[tuple[str, int], float]] = []

        for name, delta, probability in MOVE_RULES:
            candidate = current + delta
            if 1 <= candidate <= 7:
                valid_rules.append(((name, delta), probability))

        (move_name, delta), effective = weighted_choice_with_probabilities(
            rng_toada,
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
        rng_toada,
        cadence_choices,
    )

    degrees.extend(cadence_degrees)

    trace = {
        "initial_degree": initial_degree,
        "initial_degree_probabilities": {
            str(degree): 0.25 for degree in initial_choices
        },
        "internal_moves": internal_moves,
        "cadence": {
            "production": cadence_name,
            "degrees": list(cadence_degrees),
            "effective_probabilities": cadence_effective_records(cadence_effective),
            "note": (
                "Gramática cadencial definida como decisão computacional da V2.3; "
                "não é uma afirmação histórica sobre a cantoria/repente."
            ),
        },
    }

    return tuple(PitchSpec(degree=d, octave_offset=0) for d in degrees), trace


# ============================================================
# 2. BACKBONES R1..R4
# ============================================================

def family_degree_positions() -> list[int]:
    return [1, 2, 3, 4, 5, 6]


def invertible_pair_positions() -> list[tuple[int, int]]:
    return [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6)]


def apply_preserve(
    pitches: list[PitchSpec],
) -> dict[str, Any]:
    return {
        "transformation": "PRESERVE",
        "external_probability": 0.25,
        "positions": [],
        "before": [],
        "after": [],
    }


def apply_alter_degree(
    pitches: list[PitchSpec],
    rng_family: random.Random,
) -> dict[str, Any]:

    positions = family_degree_positions()
    position = rng_family.choice(positions)
    index = position - 1
    before = pitches[index]

    valid_deltas = [
        delta
        for delta in (-1, +1)
        if 1 <= before.degree + delta <= 7
    ]

    delta = rng_family.choice(valid_deltas)
    after = PitchSpec(
        degree=before.degree + delta,
        octave_offset=0,
    )
    pitches[index] = after

    return {
        "transformation": "ALTER_DEGREE",
        "external_probability": 0.25,
        "positions": [position],
        "position_probability": 1.0 / len(positions),
        "valid_deltas": [
            {
                "delta": d,
                "effective_probability": 1.0 / len(valid_deltas),
            }
            for d in valid_deltas
        ],
        "delta_degree": delta,
        "before": [pitch_spec_to_dict(before)],
        "after": [pitch_spec_to_dict(after)],
    }


def apply_invert_local_gesture(
    pitches: list[PitchSpec],
    rng_family: random.Random,
) -> dict[str, Any]:

    candidates: list[tuple[int, int, int]] = []

    for p1, p2 in invertible_pair_positions():
        first = pitches[p1 - 1]
        second = pitches[p2 - 1]
        inverted_second_degree = 2 * first.degree - second.degree

        if 1 <= inverted_second_degree <= 7:
            candidates.append((p1, p2, inverted_second_degree))

    if not candidates:
        return {
            "transformation": "INVERT_LOCAL_GESTURE",
            "external_probability": 0.25,
            "positions": [],
            "fallback": "PRESERVE_NO_VALID_GESTURE",
            "valid_candidates": [],
            "before": [],
            "after": [],
        }

    p1, p2, new_degree = rng_family.choice(candidates)
    first = pitches[p1 - 1]
    before_second = pitches[p2 - 1]

    after_second = PitchSpec(
        degree=new_degree,
        octave_offset=0,
    )
    pitches[p2 - 1] = after_second

    probability_each = 1.0 / len(candidates)

    return {
        "transformation": "INVERT_LOCAL_GESTURE",
        "external_probability": 0.25,
        "positions": [p1, p2],
        "pivot_position": p1,
        "valid_candidates": [
            {
                "positions": [c1, c2],
                "resulting_second_degree": result_degree,
                "effective_probability": probability_each,
            }
            for c1, c2, result_degree in candidates
        ],
        "before": [
            pitch_spec_to_dict(first),
            pitch_spec_to_dict(before_second),
        ],
        "after": [
            pitch_spec_to_dict(first),
            pitch_spec_to_dict(after_second),
        ],
    }


def apply_alter_cadence(
    pitches: list[PitchSpec],
    rng_family: random.Random,
) -> dict[str, Any]:

    cadence_before = (pitches[6].degree, pitches[7].degree)
    cadence_before_name, _ = cadence_rule_for_pair(cadence_before)

    alternatives = [
        ((name, pair), probability)
        for name, pair, probability in CADENCE_RULES
        if tuple(pair) != cadence_before
    ]

    (cadence_after_name, cadence_after), effective = weighted_choice_with_probabilities(
        rng_family,
        alternatives,
    )

    before_specs = [pitches[6], pitches[7]]
    pitches[6] = PitchSpec(cadence_after[0], 0)
    pitches[7] = PitchSpec(cadence_after[1], 0)

    return {
        "transformation": "ALTER_CADENCE",
        "external_probability": 0.25,
        "positions": [7, 8],
        "cadence_before": {
            "production": cadence_before_name,
            "degrees": list(cadence_before),
        },
        "cadence_after": {
            "production": cadence_after_name,
            "degrees": list(cadence_after),
        },
        "effective_probabilities": cadence_effective_records(effective),
        "before": [pitch_spec_to_dict(p) for p in before_specs],
        "after": [pitch_spec_to_dict(pitches[6]), pitch_spec_to_dict(pitches[7])],
    }


def generate_family_backbone(
    role: str,
    toada_base: tuple[PitchSpec, ...],
    rng_family: random.Random,
) -> FamilyBackbone:

    pitches = [PitchSpec(p.degree, 0) for p in toada_base]

    # Cada família recebe inicialmente sua própria expansão CADENCE.
    cadence_choices = [
        ((name, pair), probability)
        for name, pair, probability in CADENCE_RULES
    ]
    (cadence_name, cadence_degrees), cadence_effective = weighted_choice_with_probabilities(
        rng_family,
        cadence_choices,
    )

    cadence_before = [pitches[6], pitches[7]]
    pitches[6] = PitchSpec(cadence_degrees[0], 0)
    pitches[7] = PitchSpec(cadence_degrees[1], 0)

    initial_cadence_trace = {
        "production": cadence_name,
        "positions": [7, 8],
        "degrees": list(cadence_degrees),
        "before": [pitch_spec_to_dict(p) for p in cadence_before],
        "after": [pitch_spec_to_dict(pitches[6]), pitch_spec_to_dict(pitches[7])],
        "effective_probabilities": cadence_effective_records(cadence_effective),
        "note": (
            "Cadência própria da família gerada por CADENCE; decisão "
            "computacional da V2.3."
        ),
    }

    trace: list[dict[str, Any]] = []

    for step in range(1, N_FAMILY_TRANSFORMS + 1):
        transformation = rng_family.choice(list(FAMILY_TRANSFORMATIONS))

        if transformation == "PRESERVE":
            result = apply_preserve(pitches)
        elif transformation == "ALTER_DEGREE":
            result = apply_alter_degree(pitches, rng_family)
        elif transformation == "INVERT_LOCAL_GESTURE":
            result = apply_invert_local_gesture(pitches, rng_family)
        elif transformation == "ALTER_CADENCE":
            result = apply_alter_cadence(pitches, rng_family)
        else:
            raise RuntimeError(f"Transformação desconhecida: {transformation}")

        result["derivation_step"] = step
        trace.append(result)

    final_pair = (pitches[6].degree, pitches[7].degree)
    final_name, final_original_probability = cadence_rule_for_pair(final_pair)

    final_cadence = {
        "production": final_name,
        "degrees": list(final_pair),
        "original_probability": final_original_probability,
    }

    return FamilyBackbone(
        role=role,
        pitches=tuple(pitches),
        initial_cadence_trace=initial_cadence_trace,
        final_cadence=final_cadence,
        transformation_trace=tuple(trace),
    )


def generate_all_families(
    toada_base: tuple[PitchSpec, ...],
    rng_family: random.Random,
) -> dict[str, FamilyBackbone]:
    return {
        role: generate_family_backbone(role, toada_base, rng_family)
        for role in ROLES
    }


# ============================================================
# 3. RITMOS-BASE
# ============================================================

def generate_rhythm_backbone(
    role: str,
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
        role=role,
        cell_indices=cell_indices,
        durations=tuple(durations),
    )


def generate_all_rhythms(
    rng_rhythm: random.Random,
) -> dict[str, RhythmBackbone]:
    return {
        role: generate_rhythm_backbone(role, rng_rhythm)
        for role in ROLES
    }


# ============================================================
# 4. PERMUTAÇÃO Rk ↔ INSTRUMENTO
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
                f"o timbre MIDI/MuseScore utilizado como proxy é {midi_instrument}."
            ),
        )

    return result


# ============================================================
# 5. MICROVARIAÇÕES POR OCORRÊNCIA
# ============================================================

def realize_phrase(
    phrase_index: int,
    role: str,
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
        # V2.3 exige registro único.
        if backbone_pitch.octave_offset != 0:
            raise RuntimeError("V2.3 recebeu octave_offset != 0 no backbone")

        realized_degree = backbone_pitch.degree
        microvaried = False

        if position in MUTABLE_POSITIONS:
            # Sempre dois draws por posição, independentemente de p_var.
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

                before_midi = degree_to_midi(
                    backbone_pitch.degree,
                    0,
                    config.tonic_midi,
                )
                after_midi = degree_to_midi(
                    realized_degree,
                    0,
                    config.tonic_midi,
                )

                microvariations.append(
                    {
                        "position": position,
                        "gate": gate,
                        "selector": selector,
                        "degree_before": backbone_pitch.degree,
                        "degree_after": realized_degree,
                        "octave_offset": 0,
                        "midi_before": before_midi,
                        "midi_after": after_midi,
                    }
                )

        backbone_midi = degree_to_midi(
            backbone_pitch.degree,
            0,
            config.tonic_midi,
        )
        realized_midi = degree_to_midi(
            realized_degree,
            0,
            config.tonic_midi,
        )

        events.append(
            Event(
                phrase_index=phrase_index,
                role=role,
                position=position,
                backbone_degree=backbone_pitch.degree,
                backbone_octave_offset=0,
                backbone_midi=backbone_midi,
                realized_degree=realized_degree,
                realized_octave_offset=0,
                realized_midi=realized_midi,
                duration=duration,
                velocity=config.velocity,
                microvaried=microvaried,
            )
        )

    return Phrase(
        index=phrase_index,
        role=role,
        role_occurrence=role_occurrence,
        instrument=instrument,
        events=tuple(events),
        micro_decisions=tuple(micro_decisions),
        microvariations=tuple(microvariations),
    )


# ============================================================
# 6. GERAÇÃO DA COMPOSIÇÃO
# ============================================================

def generate_song(config: Config) -> Song:
    if not 0.0 <= config.p_var <= 1.0:
        raise ValueError("p_var deve estar entre 0 e 1")

    (
        rng_toada,
        rng_family,
        rng_rhythm,
        rng_instrument,
        rng_micro,
    ) = make_rngs(config.seed)

    toada_base, toada_trace = generate_toada_base(rng_toada)
    families = generate_all_families(toada_base, rng_family)
    rhythms = generate_all_rhythms(rng_rhythm)
    instruments = generate_instrument_assignment(rng_instrument)

    occurrence_counter = {role: 0 for role in ROLES}
    phrases: list[Phrase] = []

    for phrase_index, role in enumerate(STRUCTURE, start=1):
        occurrence_counter[role] += 1

        phrases.append(
            realize_phrase(
                phrase_index=phrase_index,
                role=role,
                role_occurrence=occurrence_counter[role],
                family=families[role],
                rhythm=rhythms[role],
                instrument=instruments[role],
                config=config,
                rng_micro=rng_micro,
            )
        )

    return Song(
        config=config,
        toada_base=toada_base,
        toada_trace=toada_trace,
        families=families,
        rhythms=rhythms,
        instruments=instruments,
        phrases=tuple(phrases),
    )


# ============================================================
# ASSINATURAS PARA REPRODUTIBILIDADE / EXPERIMENTO
# ============================================================

def toada_signature(song: Song) -> tuple[tuple[int, int], ...]:
    return tuple((p.degree, p.octave_offset) for p in song.toada_base)


def family_signature(song: Song) -> tuple:
    return tuple(
        (
            role,
            tuple((p.degree, p.octave_offset) for p in song.families[role].pitches),
        )
        for role in ROLES
    )


def cadence_signature(song: Song) -> tuple:
    return tuple(
        (
            role,
            song.families[role].final_cadence["production"],
            tuple(song.families[role].final_cadence["degrees"]),
        )
        for role in ROLES
    )


def rhythm_signature(song: Song) -> tuple:
    return tuple(
        (role, tuple(song.rhythms[role].durations))
        for role in ROLES
    )


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


def micro_flow_signature(song: Song) -> tuple:
    """Ignora somente o campo applied, que depende de p_var."""
    result: list[tuple[Any, ...]] = []

    for phrase in song.phrases:
        for decision in phrase.micro_decisions:
            result.append(
                (
                    phrase.index,
                    phrase.role,
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

    checks: dict[str, bool] = {}

    checks["exactly_10_phrases"] = len(song.phrases) == 10
    checks["structure_is_R1R2R2R1R1R3R3R4R4R3"] = [p.role for p in song.phrases] == STRUCTURE
    checks["corresponds_to_ABBAACCDDC"] = DISPLAY_FORM == "ABBAACCDDC" and len(STRUCTURE) == 10
    checks["exactly_8_events_per_phrase"] = all(len(p.events) == 8 for p in song.phrases)
    checks["exactly_80_total_events"] = len(all_events) == 80

    # Posições exatas de cada papel.
    checks["role_phrase_positions_exact"] = all(
        tuple(p.index for p in song.phrases if p.role == role) == ROLE_PHRASE_INDICES[role]
        for role in ROLES
    )

    role_event_counts = {
        role: sum(len(p.events) for p in song.phrases if p.role == role)
        for role in ROLES
    }
    checks["role_event_counts_exact"] = role_event_counts == EXPECTED_EVENT_COUNTS

    checks["toada_has_8_slots"] = len(song.toada_base) == 8
    checks["toada_degrees_valid"] = all(1 <= p.degree <= 7 for p in song.toada_base)
    checks["toada_initial_degree_valid"] = song.toada_base[0].degree in (2, 3, 4, 5)

    valid_cadence_pairs = {tuple(pair) for _, pair, _ in CADENCE_RULES}
    checks["toada_cadence_valid"] = (
        song.toada_base[6].degree,
        song.toada_base[7].degree,
    ) in valid_cadence_pairs

    checks["four_families_exist"] = set(song.families) == set(ROLES)
    checks["family_backbones_have_8_slots"] = all(
        len(song.families[role].pitches) == 8 for role in ROLES
    )
    checks["family_degrees_valid"] = all(
        1 <= pitch.degree <= 7
        for family in song.families.values()
        for pitch in family.pitches
    )
    checks["family_cadences_valid"] = all(
        (
            song.families[role].pitches[6].degree,
            song.families[role].pitches[7].degree,
        ) in valid_cadence_pairs
        for role in ROLES
    )

    # REGISTER_SHIFT foi removido: todos os offsets devem ser zero.
    checks["all_toada_octave_offsets_zero"] = all(
        p.octave_offset == 0 for p in song.toada_base
    )
    checks["all_backbone_octave_offsets_zero"] = all(
        p.octave_offset == 0
        for family in song.families.values()
        for p in family.pitches
    )
    checks["all_event_octave_offsets_zero"] = all(
        event.backbone_octave_offset == 0
        and event.realized_octave_offset == 0
        for event in all_events
    )

    checks["four_rhythm_backbones_exist"] = set(song.rhythms) == set(ROLES)
    checks["rhythm_backbones_have_8_events"] = all(
        len(rhythm.durations) == 8 for rhythm in song.rhythms.values()
    )
    checks["every_rhythm_cell_sums_2_beats"] = all(
        math.isclose(
            sum(rhythm.durations[cell_start:cell_start + 2]),
            2.0,
            abs_tol=1e-9,
        )
        for rhythm in song.rhythms.values()
        for cell_start in (0, 2, 4, 6)
    )
    checks["every_phrase_is_8_beats"] = all(
        math.isclose(sum(e.duration for e in phrase.events), 8.0, abs_tol=1e-9)
        for phrase in song.phrases
    )

    # Instrumentos: uma permutação sem repetição dos quatro rótulos/timbres.
    checks["four_instrument_assignments_exist"] = set(song.instruments) == set(ROLES)
    checks["cultural_labels_are_unique"] = len({
        song.instruments[role].cultural_label for role in ROLES
    }) == 4
    checks["midi_instruments_are_unique"] = len({
        song.instruments[role].midi_instrument for role in ROLES
    }) == 4
    checks["midi_programs_valid"] = all(
        0 <= song.instruments[role].midi_program <= 127 for role in ROLES
    )
    checks["phrase_instrument_matches_role"] = all(
        phrase.instrument == song.instruments[phrase.role]
        for phrase in song.phrases
    )

    checks["durations_positive"] = all(event.duration > 0 for event in all_events)
    checks["realized_degrees_valid"] = all(1 <= event.realized_degree <= 7 for event in all_events)
    checks["midi_pitches_valid"] = all(0 <= event.realized_midi <= 127 for event in all_events)

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

    checks["phrases_use_family_backbone"] = all(
        event.backbone_degree == song.families[phrase.role].pitches[event.position - 1].degree
        for phrase in song.phrases
        for event in phrase.events
    )
    checks["phrases_use_family_rhythm"] = all(
        math.isclose(
            event.duration,
            song.rhythms[phrase.role].durations[event.position - 1],
            abs_tol=1e-9,
        )
        for phrase in song.phrases
        for event in phrase.events
    )

    regenerated = generate_song(song.config)
    checks["same_seed_and_config_are_reproducible"] = (
        toada_signature(song) == toada_signature(regenerated)
        and family_signature(song) == family_signature(regenerated)
        and cadence_signature(song) == cadence_signature(regenerated)
        and rhythm_signature(song) == rhythm_signature(regenerated)
        and instrument_signature(song) == instrument_signature(regenerated)
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
        "same_toada_base": toada_signature(m1) == toada_signature(m3),
        "same_family_backbones": family_signature(m1) == family_signature(m3),
        "same_family_cadences": cadence_signature(m1) == cadence_signature(m3),
        "same_rhythm_backbones": rhythm_signature(m1) == rhythm_signature(m3),
        "same_instrument_assignment": instrument_signature(m1) == instrument_signature(m3),
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

    degree_equal = 0
    pitch_equal = 0
    rhythm_equal = 0
    combined_equal = 0

    for event_a, event_b in zip(phrase_a.events, phrase_b.events):
        same_degree = event_a.realized_degree == event_b.realized_degree
        same_pitch = event_a.realized_midi == event_b.realized_midi
        same_rhythm = math.isclose(event_a.duration, event_b.duration, abs_tol=1e-9)

        degree_equal += int(same_degree)
        pitch_equal += int(same_pitch)
        rhythm_equal += int(same_rhythm)
        combined_equal += int(same_pitch and same_rhythm)

    return {
        "degree_similarity": degree_equal / 8.0,
        "pitch_similarity": pitch_equal / 8.0,
        "rhythm_similarity": rhythm_equal / 8.0,
        "combined_similarity": combined_equal / 8.0,
    }


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def compute_metrics(song: Song) -> dict[str, Any]:
    eligible_positions = len(song.phrases) * len(MUTABLE_POSITIONS)
    microvariation_count = sum(
        int(event.microvaried)
        for phrase in song.phrases
        for event in phrase.events
    )

    intra_pairs: list[dict[str, Any]] = []
    inter_pairs: list[dict[str, Any]] = []

    intra_degree: list[float] = []
    inter_degree: list[float] = []
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
            **similarities,
        }

        if phrase_a.role == phrase_b.role:
            intra_pairs.append(record)
            intra_degree.append(similarities["degree_similarity"])
            intra_pitch.append(similarities["pitch_similarity"])
            intra_rhythm.append(similarities["rhythm_similarity"])
            intra_combined.append(similarities["combined_similarity"])
        else:
            inter_pairs.append(record)
            inter_degree.append(similarities["degree_similarity"])
            inter_pitch.append(similarities["pitch_similarity"])
            inter_rhythm.append(similarities["rhythm_similarity"])
            inter_combined.append(similarities["combined_similarity"])

    backbone_pairs: list[dict[str, Any]] = []
    backbone_degree_values: list[float] = []
    backbone_pitch_values: list[float] = []

    for role_a, role_b in combinations(ROLES, 2):
        pitches_a = song.families[role_a].pitches
        pitches_b = song.families[role_b].pitches

        degree_similarity = sum(
            int(a.degree == b.degree)
            for a, b in zip(pitches_a, pitches_b)
        ) / 8.0

        pitch_similarity = sum(
            int(
                degree_to_midi(a.degree, 0, song.config.tonic_midi)
                == degree_to_midi(b.degree, 0, song.config.tonic_midi)
            )
            for a, b in zip(pitches_a, pitches_b)
        ) / 8.0

        backbone_pairs.append(
            {
                "role_i": role_a,
                "role_j": role_b,
                "degree_similarity": degree_similarity,
                "pitch_similarity": pitch_similarity,
            }
        )
        backbone_degree_values.append(degree_similarity)
        backbone_pitch_values.append(pitch_similarity)

    return {
        "eligible_microvariation_positions": eligible_positions,
        "microvariation_count": microvariation_count,
        "observed_microvariation_rate": microvariation_count / eligible_positions,

        "mean_intra_class_degree_similarity": mean(intra_degree),
        "mean_inter_class_degree_similarity": mean(inter_degree),
        "mean_intra_class_pitch_similarity": mean(intra_pitch),
        "mean_inter_class_pitch_similarity": mean(inter_pitch),
        "mean_intra_class_rhythm_similarity": mean(intra_rhythm),
        "mean_inter_class_rhythm_similarity": mean(inter_rhythm),
        "mean_intra_class_combined_similarity": mean(intra_combined),
        "mean_inter_class_combined_similarity": mean(inter_combined),
        "intra_greater_than_inter_combined": mean(intra_combined) > mean(inter_combined),

        "intra_class_pair_count": len(intra_pairs),
        "inter_class_pair_count": len(inter_pairs),
        "intra_class_pairs": intra_pairs,
        "inter_class_pairs": inter_pairs,

        "mean_backbone_degree_similarity_between_roles": mean(backbone_degree_values),
        "mean_backbone_pitch_similarity_between_roles": mean(backbone_pitch_values),
        "backbone_role_pairs": backbone_pairs,
    }


# ============================================================
# MIDI — QUATRO TRACKS, UMA POR PAPEL
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

    return pm


def validate_midi_structure(
    pm: pretty_midi.PrettyMIDI,
    song: Song,
) -> dict[str, bool]:
    checks: dict[str, bool] = {}

    checks["exactly_4_instrument_tracks"] = len(pm.instruments) == 4

    by_name = {instrument.name: instrument for instrument in pm.instruments}
    expected_names = {song.instruments[role].track_name for role in ROLES}
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

    checks["total_midi_notes_80"] = (
        len(tracks_by_role) == 4
        and sum(len(track.notes) for track in tracks_by_role.values()) == 80
    )

    # Confirma que cada track toca apenas nas janelas temporais das frases do papel.
    seconds_per_beat = 60.0 / song.config.bpm
    phrase_seconds = 8.0 * seconds_per_beat
    eps = 1e-7

    windows_ok = True
    if len(tracks_by_role) != 4:
        windows_ok = False
    else:
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
        "role": family.role,
        "backbone": [
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
        "initial_cadence": family.initial_cadence_trace,
        "final_cadence": family.final_cadence,
        "transformations": list(family.transformation_trace),
    }


def rhythm_to_dict(rhythm: RhythmBackbone) -> dict[str, Any]:
    return {
        "role": rhythm.role,
        "cell_indices": list(rhythm.cell_indices),
        "cells": [list(RHYTHM_CELLS[index]) for index in rhythm.cell_indices],
        "durations": list(rhythm.durations),
        "cell_probability": 1.0 / len(RHYTHM_CELLS),
    }


def instrument_to_dict(assignment: InstrumentAssignment) -> dict[str, Any]:
    return {
        "role": assignment.role,
        "cultural_label": assignment.cultural_label,
        "track_label": assignment.track_label,
        "midi_instrument": assignment.midi_instrument,
        "midi_program": assignment.midi_program,
        "track_name": assignment.track_name,
        "proxy_note": assignment.proxy_note,
    }


def phrase_to_dict(phrase: Phrase, song: Song) -> dict[str, Any]:
    return {
        "phrase_index": phrase.index,
        "role": phrase.role,
        "role_occurrence": phrase.role_occurrence,
        "cultural_label": phrase.instrument.cultural_label,
        "midi_instrument": phrase.instrument.midi_instrument,
        "midi_program": phrase.instrument.midi_program,
        "track_name": phrase.instrument.track_name,
        "seed": song.config.seed,
        "p_var": song.config.p_var,
        "microvariation_positions": [m["position"] for m in phrase.microvariations],
        "micro_decisions": list(phrase.micro_decisions),
        "microvariations": list(phrase.microvariations),
        "events": [
            {
                "position": event.position,
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


def save_metadata(
    song: Song,
    validation: dict[str, bool],
    midi_validation: dict[str, bool],
    metrics: dict[str, Any],
    experiment_validation: dict[str, bool],
    path: Path,
) -> None:

    payload = {
        "version": "V2.3",
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
                for name in ("toada", "family", "rhythm", "instrument", "micro")
            },
        },
        "formal_grammar": {
            "axiom_rule": "S -> R1 R2 R2 R1 R1 R3 R3 R4 R4 R3",
            "display_correspondence": "ABBAACCDDC",
            "move_rules": [
                {"production": name, "delta": delta, "probability": probability}
                for name, delta, probability in MOVE_RULES
            ],
            "cadence_rules": [
                {"production": name, "degrees": list(pair), "probability": probability}
                for name, pair, probability in CADENCE_RULES
            ],
            "family_transformations": {
                "productions": list(FAMILY_TRANSFORMATIONS),
                "probability_each": 0.25,
                "derivations_per_family": N_FAMILY_TRANSFORMS,
                "cumulative": True,
                "register_shift_present": False,
            },
            "rhythm_cell_rules": {
                "productions": [list(cell) for cell in RHYTHM_CELLS],
                "probability_each": 1.0 / len(RHYTHM_CELLS),
            },
            "microvariation_rule": (
                "positions 2..6: PRESERVE [1-p_var] | ALTER_DEGREE(±1 valid) [p_var]"
            ),
            "protected_positions_during_occurrence_microvariation": list(PROTECTED_POSITIONS),
            "octave_offset_rule": "octave_offset = 0 for every event in V2.3",
        },
        "instrument_assignment": {
            role: instrument_to_dict(song.instruments[role])
            for role in ROLES
        },
        "instrumentation_note": (
            "A viola é a referência cultural central à cantoria neste projeto. "
            "Rabeca, sanfona e violão são escolhas de orquestração de inspiração "
            "nordestina; os timbres General MIDI/MuseScore são proxies explícitos, "
            "não uma afirmação de instrumentação tradicional fixa do repente."
        ),
        "toada_base": {
            "pitches": [
                {
                    **pitch_spec_to_dict(pitch),
                    "midi_pitch": degree_to_midi(
                        pitch.degree,
                        pitch.octave_offset,
                        song.config.tonic_midi,
                    ),
                }
                for pitch in song.toada_base
            ],
            "generation_trace": song.toada_trace,
        },
        "families": {
            role: {
                **family_to_dict(song.families[role], song.config),
                "instrument": instrument_to_dict(song.instruments[role]),
            }
            for role in ROLES
        },
        "rhythm_bases": {
            role: rhythm_to_dict(song.rhythms[role])
            for role in ROLES
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
        failed = [name for name, result in pre_write_midi_validation.items() if not result]
        raise RuntimeError(
            f"Falha de validação MIDI antes da escrita em {song.config.name}: {failed}"
        )

    pm.write(str(midi_path))

    # Reabre o arquivo efetivamente gravado para validar tracks/programs/notas.
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
        "  toada-base:",
        " ".join(str(p.degree) for p in song.toada_base),
    )
    print(
        "  backbones:",
        " | ".join(
            f"{role}=" + "-".join(str(p.degree) for p in song.families[role].pitches)
            for role in ROLES
        ),
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
        "  microvariações: "
        f"{metrics['microvariation_count']}/"
        f"{metrics['eligible_microvariation_positions']} "
        f"({metrics['observed_microvariation_rate']:.3f})"
    )
    print(
        "  similaridade combinada intra/inter: "
        f"{metrics['mean_intra_class_combined_similarity']:.3f} / "
        f"{metrics['mean_inter_class_combined_similarity']:.3f}"
    )
    print("  Sim_intra > Sim_inter:", metrics["intra_greater_than_inter_combined"])
    print(f"  MIDI: {midi_path}")
    print(f"  WAV MuseScore: {wav_path}")


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    base_dir = Path(__file__).resolve().parent
    output_dir = base_dir / "outputs_v23"
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

    print("Validação cruzada V2.3:")
    print("  M1/M3 mesma toada-base: OK")
    print("  M1/M3 mesmos backbones R1/R2/R3/R4: OK")
    print("  M1/M3 mesmas cadências-base/finais: OK")
    print("  M1/M3 mesmos ritmos-base: OK")
    print("  M1/M3 mesma associação R↔instrumento: OK")
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
    print(f"Arquivos V2.3 gerados em: {output_dir}")


if __name__ == "__main__":
    main()
