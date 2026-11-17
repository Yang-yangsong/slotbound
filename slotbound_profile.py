from decimal import Decimal
import json
from pathlib import Path
import re
from slotbound_paths import DATA


TOTAL = 10_000
DEFAULT = (5000, 2500, 1400, 600, 500)
KEYS = ("normal", "advanced", "rare", "legendary", "prism")
SYMBOL_KEYS = ("W", "A", "S", "H", "M", "D", "Joker")
SYMBOL_DEFAULT = (1970, 1970, 1970, 1478, 1477, 985, 150)
JOKER_MAX = 500
PROFILE = DATA / "profile.json"


def percent_units(value):
    value = value.strip()
    if not re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{1,2})?", value):
        raise ValueError("请输入 0 到 100，最多两位小数。")
    units = int(Decimal(value) * 100)
    if units > TOTAL:
        raise ValueError("每一档的概率须在 0% 到 100% 之间。")
    return units


def format_percent(units):
    return f"{units / 100:.2f}".rstrip("0").rstrip(".")


def valid_distribution(values, size=len(KEYS)):
    return (
        isinstance(values, (list, tuple))
        and len(values) == size
        and all(type(value) is int and 0 <= value <= TOTAL for value in values)
        and sum(values) == TOTAL
    )


def valid_symbols(values):
    return valid_distribution(values, len(SYMBOL_KEYS)) and values[-1] <= JOKER_MAX


def apportion(weights, total):
    weights = list(weights)
    if not any(weights):
        weights = [1] * len(weights)
    denominator = sum(weights)
    shares = [divmod(weight * total, denominator) for weight in weights]
    result = [share for share, _ in shares]
    ranked = sorted(range(len(shares)), key=lambda index: -shares[index][1])
    for index in ranked[:total - sum(result)]:
        result[index] += 1
    return result


def redistribute(values, index, amount, joker_max=None):
    others = [value for position, value in enumerate(values) if position != index]
    result = apportion(others, TOTAL - amount)
    result.insert(index, amount)
    if joker_max is not None and index != len(values) - 1 and result[-1] > joker_max:
        others = [value for position, value in enumerate(values[:-1]) if position != index]
        result = apportion(others, TOTAL - amount - joker_max)
        result.insert(index, amount)
        result.append(joker_max)
    return result


def limit_joker(values):
    if values[-1] <= JOKER_MAX:
        return values
    return redistribute(values, len(values) - 1, JOKER_MAX)


def read_profile():
    if not PROFILE.exists():
        return list(DEFAULT), None
    values = json.loads(PROFILE.read_text(encoding="utf-8"))
    symbols = None
    if isinstance(values, dict):
        symbols = values.get("symbols")
        values = values.get("rarity")
    if not valid_distribution(values):
        raise ValueError("上次保存的概率配置无效。")
    if symbols is not None and not valid_symbols(symbols):
        raise ValueError("上次保存的符号配置无效。")
    return values, symbols


def save_profile(values, symbols=None):
    if not valid_distribution(values):
        raise ValueError("五档概率必须合计 100%。")
    if symbols is not None and not valid_symbols(symbols):
        raise ValueError("符号概率必须合计 100%，小丑上限为 5%。")
    PROFILE.parent.mkdir(parents=True, exist_ok=True)
    pending = PROFILE.with_suffix(".tmp")
    pending.write_text(json.dumps({"rarity": values, "symbols": symbols}) + "\n", encoding="utf-8")
    pending.replace(PROFILE)
