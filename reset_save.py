import argparse
import os
import re
from datetime import datetime
from pathlib import Path
from shutil import copy2
from slotbound_paths import DATA


def root_fields(data):
    tokens = rb'"(?:[^"\\]|\\.)*"|[{}]'
    depth = 0
    fields = {}
    for token in re.finditer(tokens, data):
        if token[0] == b'{':
            depth += 1
        elif token[0] == b'}':
            depth -= 1
        elif depth == 1 and data[token.start() - 1:token.start()] == b'[':
            if data[token.end():token.end() + 2] == b']=':
                fields[token[0][1:-1]] = token.end() + 2
    return fields


def read_upgrades(data, upgrade_start):
    upgrades = re.match(rb'\{((?:\["[^"]+"\]=[^,{}]+,)*)\}', data[upgrade_start:])
    if upgrades is None:
        raise ValueError('Unexpected upgrade format')
    return upgrades


def upgrade_entries(upgrades):
    return re.finditer(rb'\["([^"]+)"\]=([^,]+),', upgrades[1])


def purchased_upgrades(data):
    upgrades = read_upgrades(data, root_fields(data)[b'upgrades'])
    return {
        name for name, value in (entry.groups() for entry in upgrade_entries(upgrades))
        if value == b'true' and not name.startswith(b'__')
    }


def reset(data, prices):
    fields = root_fields(data)
    upgrade_start = fields[b'upgrades']
    upgrades = read_upgrades(data, upgrade_start)
    points_start = fields[b'originite']
    points = re.match(rb'\d+(?=,)', data[points_start:])
    if points is None:
        raise ValueError('Unexpected currency format')

    purchased = []
    metadata = []
    for entry in upgrade_entries(upgrades):
        name, value = entry.groups()
        if name.startswith(b'__'):
            metadata.append(entry[0])
        elif value == b'true':
            purchased.append(name)
        else:
            raise ValueError(f'Unexpected value for {name!r}: {value!r}')

    refund = sum(prices[name] for name in purchased)
    balance = int(points[0]) + refund
    changes = [
        (upgrade_start, upgrade_start + upgrades.end(), b'{' + b''.join(metadata) + b'}'),
        (points_start, points_start + points.end(), str(balance).encode('ascii')),
    ]
    for start, end, replacement in sorted(changes, reverse=True):
        data = data[:start] + replacement + data[end:]
    return data, len(purchased), refund, balance


def reset_profile(preview=False, save_dir=None, backup_root=None):
    work = Path(__file__).resolve().parent
    if save_dir is None:
        save_dir = Path(os.environ['APPDATA']) / 'slotbound_full'
    if backup_root is None:
        backup_root = DATA / 'backups'
    paths = [save_dir / 'save_fallback.dat', save_dir / 'save_fallback.bak']
    prices = {}
    for line in (work / 'costs.txt').read_bytes().splitlines():
        name, amount = line.split()
        cost = int(amount)
        if name in prices and prices[name] != cost:
            raise ValueError(f'Conflicting costs for {name!r}')
        prices[name] = cost

    original = paths[0].read_bytes()
    edited, count, refund, balance = reset(original, prices)
    assert reset(edited, prices) == (edited, 0, 0, balance)
    backup = None
    if count and not preview:
        backup = backup_root / datetime.now().strftime('reset-%Y%m%d-%H%M%S-%f')
        backup.mkdir(parents=True)
        for path in paths:
            copy2(path, backup / path.name)
        assert (backup / paths[0].name).read_bytes() == original
        updated = []
        try:
            for path in reversed(paths):
                staged = path.with_suffix(path.suffix + '.reset-tmp')
                staged.write_bytes(edited)
                staged.replace(path)
                updated.append(path)
                assert path.read_bytes() == edited
        except OSError:
            for path in updated:
                copy2(backup / path.name, path)
            raise
    return count, refund, balance, backup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    count, refund, balance, backup = reset_profile(preview=args.preview)
    if backup:
        print(f'Backup: {backup}')
    print(f'Upgrades: {count}, refund: {refund}, balance: {balance}')


if __name__ == '__main__':
    main()
