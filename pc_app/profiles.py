"""
profiles.py - Profile management for the fan controller.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple
from config import Config, DEFAULT_CURVE_SILENT, DEFAULT_CURVE_BALANCED, \
    DEFAULT_CURVE_PERFORMANCE, DEFAULT_CURVE_GAME, PROFILE_NAMES


@dataclass
class Profile:
    id: int
    name: str
    description: str
    default_cpu_curve: Tuple[List[int], List[int]]
    default_gpu_curve: Tuple[List[int], List[int]]


PROFILES: List[Profile] = [
    Profile(0, "Silent",
            "Ultra-low noise, fans stay slow until temps rise sharply.",
            (DEFAULT_CURVE_SILENT["temps"],     DEFAULT_CURVE_SILENT["percents"]),
            (DEFAULT_CURVE_SILENT["temps"],     DEFAULT_CURVE_SILENT["percents"])),
    Profile(1, "Balanced",
            "Reasonable tradeoff for everyday use.",
            (DEFAULT_CURVE_BALANCED["temps"],   DEFAULT_CURVE_BALANCED["percents"]),
            (DEFAULT_CURVE_BALANCED["temps"],   DEFAULT_CURVE_BALANCED["percents"])),
    Profile(2, "Performance",
            "Aggressive cooling, suitable for heavy workloads.",
            (DEFAULT_CURVE_PERFORMANCE["temps"],DEFAULT_CURVE_PERFORMANCE["percents"]),
            (DEFAULT_CURVE_PERFORMANCE["temps"],DEFAULT_CURVE_PERFORMANCE["percents"])),
    Profile(3, "Game",
            "Boosted curve, fans never below 60%.",
            (DEFAULT_CURVE_GAME["temps"],      DEFAULT_CURVE_GAME["percents"]),
            (DEFAULT_CURVE_GAME["temps"],      DEFAULT_CURVE_GAME["percents"])),
]


def get_profile(pid: int) -> Profile:
    for p in PROFILES:
        if p.id == pid:
            return p
    return PROFILES[1]


def list_profiles() -> List[Profile]:
    return PROFILES


def get_curve_for(config: Config, pid: int, fan: str) -> Tuple[List[int], List[int]]:
    try:
        return config.get_curve(pid, fan)
    except Exception:
        p = get_profile(pid)
        return (p.default_cpu_curve if fan.lower() == "cpu"
                else p.default_gpu_curve)


def push_curve_to_esp(client, config: Config, pid: int, fan: str) -> bool:
    temps, percents = get_curve_for(config, pid, fan)
    return client.set_curve(fan, temps, percents)


def push_all_curves(client, config: Config) -> None:
    pid = config.active_profile
    push_curve_to_esp(client, config, pid, "cpu")
    push_curve_to_esp(client, config, pid, "gpu")
