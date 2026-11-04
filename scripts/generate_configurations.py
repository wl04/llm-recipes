#!/usr/bin/env python3
"""Render profile YAML into marked sections of recipe configuration guides."""
import argparse
import html
from pathlib import Path
import sys
from urllib.parse import quote

import yaml

ROOT = Path(__file__).resolve().parents[1]
START = '<!-- BEGIN GENERATED CONFIGURATIONS -->'
END = '<!-- END GENERATED CONFIGURATIONS -->'


def cell(value):
    if value is None:
        return '—'
    return html.escape(str(value)).replace('|', '&#124;').replace('\n', '<br>')


def rows(data, labels, prefix=''):
    for key, value in data.items():
        path = f'{prefix}.{key}' if prefix else str(key)
        if isinstance(value, dict):
            yield from rows(value, labels, path)
            continue
        label = labels.get(path)
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f'Missing display label for {path}')
        if isinstance(value, list):
            yield f'| {cell(label)} | ' + '<br>'.join(cell(item) for item in value) + ' |'
        else:
            yield f'| {cell(label)} | {cell(value)} |'


def render(recipe):
    lines = ['## Configurations', '', 'Values below are generated from the result profiles. `—` means unspecified.', '']
    profiles = sorted(recipe.glob('results/*/profile.yaml'), reverse=True)
    for profile in profiles:
        data = yaml.safe_load(profile.read_text())
        if not isinstance(data, dict):
            raise ValueError(f'{profile}: expected a YAML mapping')
        relative = quote(profile.relative_to(recipe).as_posix())
        lines += [f'### {profile.parent.name}', '', f'[Profile]({relative})']
        if (profile.parent / 'summary.md').is_file():
            lines[-1] += f' · [Results]({quote((profile.parent / "summary.md").relative_to(recipe).as_posix())})'
        labels = data.get('labels')
        if not isinstance(labels, dict):
            raise ValueError(f'{profile}: expected a labels mapping')
        for key, value in data.items():
            if key == 'labels':
                continue
            if isinstance(value, dict):
                title = labels.get(key)
                if not isinstance(title, str) or not title.strip():
                    raise ValueError(f'Missing display label for {key}')
                lines += ['', f'#### {cell(title)}', '']
                section_rows = list(rows(value, labels, key))
            else:
                section_rows = list(rows({key: value}, labels))
            if section_rows:
                lines += ['', '| Setting | Value |', '|---|---|', *section_rows, '']
    return '\n'.join(lines).rstrip() + '\n'


def update(recipe):
    path = recipe / 'configuration.md'
    original = path.read_text()
    if original.count(START) != 1 or original.count(END) != 1:
        raise ValueError(f'{path}: expected exactly one pair of generated-section markers')
    before, rest = original.split(START)
    old, after = rest.split(END)
    return path, original, before + START + '\n\n' + render(recipe) + '\n' + END + after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if generated content is stale; write nothing')
    args = parser.parse_args()
    try:
        changes = [update(p.parent) for p in sorted((ROOT / 'recipes').glob('*/configuration.md'))]
    except (ValueError, OSError, yaml.YAMLError) as exc:
        print(exc, file=sys.stderr)
        return 2
    stale = False
    for path, old, new in changes:
        if old != new:
            stale = True
            if args.check:
                print(f'Stale: {path.relative_to(ROOT)}')
            else:
                path.write_text(new)
                print(f'Updated: {path.relative_to(ROOT)}')
    return int(args.check and stale)


if __name__ == '__main__':
    sys.exit(main())
