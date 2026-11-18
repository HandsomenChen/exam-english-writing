#!/usr/bin/env python3
"""Check essay lengths, topic coverage, and basic chart structure."""
import argparse
from collections import Counter
import json
from math import isfinite
from pathlib import Path
import re
import sys

TRACKS = ('E1A', 'E1B', 'E2A', 'E2B')
WORD = re.compile(r"[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+\.[0-9]+|[A-Za-z0-9]+(?:[’'\-–‑][A-Za-z0-9]+)*")
TASK_TEXT = ('id', 'title', 'prompt', 'analysis', 'advanced_zh', 'structure', 'self_check', 'source')


def count_words(text):
    return len(WORD.findall(text))


def check_chart(chart, label, errors):
    chart_label = f"{label} 图表 {chart.get('title', '')}"
    for key in ('title', 'unit', 'scope'):
        if not isinstance(chart.get(key), str) or not chart[key].strip():
            errors.append(f'{chart_label} 缺少 {key}')
    mode = chart.get('mode')
    if mode not in ('single-share', 'multi-share', 'values'):
        errors.append(f'{chart_label} 需要明确统计类型')
    if mode in ('single-share', 'multi-share') and chart.get('unit') != '%':
        errors.append(f'{chart_label} 的占比单位应为 %')
    if not isinstance(chart.get('simulated'), bool):
        errors.append(f'{chart_label} 需要标明数据是否模拟')
    categories = chart.get('labels', [])
    series_list = chart.get('series', [])
    if not categories or not series_list:
        errors.append(f'{chart_label} 缺类别或数据系列')
    for series in series_list:
        name = series.get('name', '')
        values = series.get('values', [])
        if not name or len(values) != len(categories):
            errors.append(f'{chart_label} 的系列 {name} 与类别数不一致，或缺系列名')
            continue
        if any(type(v) not in (float, int) or not isfinite(v) for v in values):
            errors.append(f'{chart_label} 的系列 {name} 有非有限数值')
            continue
        if mode in ('single-share', 'multi-share') and any(v < 0 or v > 100 for v in values):
            errors.append(f'{chart_label} 的系列 {name} 有超出 0–100 的占比')
        if mode == 'single-share' and not 99 <= sum(values) <= 101:
            errors.append(f'{chart_label} 的系列 {name} 单选占比合计 {sum(values):g}%')


def inspect(items, args):
    errors = []
    identifiers = Counter(item.get('id') for item in items)
    tracks = Counter(item.get('track') for item in items)
    for number, item in enumerate(items, 1):
        label = item.get('id') or f'第 {number} 题'
        for key in TASK_TEXT:
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(f'{label} 缺少 {key}')
        if identifiers[item.get('id')] > 1:
            errors.append(f'{label} 题号重复')
        track = item.get('track')
        if track not in TRACKS:
            errors.append(f'{label} 卷种无效')
            continue
        if not isinstance(item.get('expressions'), list) or not item['expressions']:
            errors.append(f'{label} 缺少推荐表达')
        allowed = (args.small_min, args.small_max) if track.endswith('A') else (args.large_min, args.large_max)
        summaries = []
        models = item.get('models', {})
        for variant in ('basic', 'advanced'):
            model = models.get(variant, {})
            body = model.get('body', '')
            if not isinstance(body, str) or not body.strip():
                errors.append(f'{label} {variant} 缺英文正文')
                continue
            words = count_words(body)
            complete = ' '.join(part for part in (model.get('opening', ''), body, model.get('closing', '')) if part)
            summaries.append(f'{variant} 正文 {words} / 全文 {count_words(complete)}')
            if not allowed[0] <= words <= allowed[1]:
                errors.append(f'{label} {variant} 正文 {words} 词，目标 {allowed[0]}–{allowed[1]}')
        basic = models.get('basic', {}).get('body')
        advanced = models.get('advanced', {}).get('body')
        if basic and advanced and WORD.findall(basic.lower()) == WORD.findall(advanced.lower()):
            errors.append(f'{label} 两版范文正文相同')
        for chart in item.get('charts', []):
            check_chart(chart, label, errors)
        print(f'{label}  ' + '  |  '.join(summaries))
    if args.per_track is not None:
        for track in TRACKS:
            if tracks[track] != args.per_track:
                errors.append(f'{track} {tracks[track]} 题，目标 {args.per_track} 题')
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch', type=Path)
    parser.add_argument('--per-track', type=int)
    parser.add_argument('--small-min', type=int, default=100)
    parser.add_argument('--small-max', type=int, default=120)
    parser.add_argument('--large-min', type=int, default=175)
    parser.add_argument('--large-max', type=int, default=185)
    args = parser.parse_args(argv)
    if not (0 < args.small_min <= args.small_max and 0 < args.large_min <= args.large_max):
        parser.error('词数上下限无效')
    try:
        document = json.loads(args.batch.read_text(encoding='utf-8'))
        items = document.get('items', [])
        if not isinstance(items, list) or not items or not all(isinstance(item, dict) for item in items):
            raise ValueError('items 必须是非空题目列表')
        errors = inspect(items, args)
    except (OSError, ValueError, TypeError, AttributeError) as error:
        print(f'输入无法读取：{error}', file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f'{len(items)} 题通过结构、图表和篇幅检查。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
