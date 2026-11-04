#!/usr/bin/env python3
"""Render profile YAML into marked sections of recipe configuration guides."""
import argparse
import html
import re
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


def empty(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    if isinstance(value, (dict, list)):
        items = value.values() if isinstance(value, dict) else value
        return all(empty(item) for item in items)
    return False


def rows(data, labels, prefix=''):
    for key, value in data.items():
        if empty(value):
            continue
        path = f'{prefix}.{key}' if prefix else str(key)
        if isinstance(value, dict):
            yield from rows(value, labels, path)
            continue
        label = labels.get(path)
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f'Missing display label for {path}')
        if isinstance(value, list):
            yield f'| {cell(label)} | ' + '<br>'.join(cell(item) for item in value if not empty(item)) + ' |'
        else:
            yield f'| {cell(label)} | {cell(value)} |'


def profile_identity(data):
    caption = data.get('id')
    if not isinstance(caption, str):
        raise ValueError('Profile id must be Model / Format / Hardware / Memory')
    parts = caption.split(' / ')
    if len(parts) != 4 or any(not part.strip() for part in parts):
        raise ValueError('Profile id must have four nonempty parts: Model / Format / Hardware / Memory')
    slug = '-'.join(re.sub(r'[^a-z0-9.-]+', '-', part.lower()).strip('-') for part in parts)
    return caption, slug


def render(recipe):
    lines = []
    identity = None
    links = []
    profiles = sorted(recipe.glob('results/*/profile.yaml'), reverse=True)
    for index, profile in enumerate(profiles, 1):
        data = yaml.safe_load(profile.read_text())
        if not isinstance(data, dict):
            raise ValueError(f'{profile}: expected a YAML mapping')
        caption, slug = profile_identity(data)
        if recipe.name != slug:
            raise ValueError(f'{profile}: recipe folder must be {slug}')
        if identity is None:
            identity = caption
            lines += [f'# {cell(caption)}', '']
        elif caption != identity:
            raise ValueError(f'{profile}: all results in a recipe must share the same id')
        relative = quote(profile.relative_to(recipe).as_posix())
        if len(profiles) > 1:
            lines += [f'## Experiment {index}', '']
        profile_label = 'Profile YAML' if len(profiles) == 1 else f'Experiment {index} profile YAML'
        links.append(f'[{profile_label}]({relative})')
        summary = profile.parent / 'summary.md'
        if summary.is_file():
            heading = next((line[2:].strip() for line in summary.read_text().splitlines() if line.startswith('# ')), 'Results')
            title = re.sub(r'^\d{4}-\d{2}-\d{2}\s*[—–-]\s*', '', heading)
            title = cell(title).replace('[', '&#91;').replace(']', '&#93;')
            target = quote(summary.relative_to(recipe).as_posix())
            lines += [f'**[View results: {title}]({target})** — workload, performance statistics, memory usage, and observations.', '']
        labels = data.get('labels')
        if not isinstance(labels, dict):
            raise ValueError(f'{profile}: expected a labels mapping')
        for key, value in data.items():
            if key in {'labels', 'id'}:
                continue
            if empty(value):
                continue
            if isinstance(value, dict):
                title = labels.get(key)
                if not isinstance(title, str) or not title.strip():
                    raise ValueError(f'Missing display label for {key}')
                lines += ['', f'{"###" if len(profiles) > 1 else "##"} {cell(title)}', '']
                section_rows = list(rows(value, labels, key))
            else:
                section_rows = list(rows({key: value}, labels))
            if section_rows:
                lines += ['', '| Setting | Value |', '|---|---|', *section_rows, '']
    if links:
        lines += ['---', '', ' · '.join(links), '']
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
