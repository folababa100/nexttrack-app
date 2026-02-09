#!/usr/bin/env python3
"""
Precise word counter for the draft report.
Excludes: title/metadata, table of contents, tables, figures, code blocks,
figure/table captions, image references, references section.
"""

import re
from pathlib import Path

MD_FILE = Path(__file__).parent / "draft_report.md"

def count_words_by_chapter(md_text):
    lines = md_text.split('\n')

    # Define chapter boundaries
    chapters = {
        'Ch1 Introduction': {'start': '# Chapter 1: Introduction', 'end': '# Chapter 2:', 'limit': 1000},
        'Ch2 Literature Review': {'start': '# Chapter 2: Literature Review', 'end': '# Chapter 3:', 'limit': 2500},
        'Ch3 Design': {'start': '# Chapter 3: Design', 'end': '# Chapter 4:', 'limit': 2000},
        'Ch4 Implementation': {'start': '# Chapter 4: Implementation', 'end': '# Chapter 5:', 'limit': 2000},
        'Ch5 Evaluation': {'start': '# Chapter 5: Evaluation', 'end': '# Chapter 6:', 'limit': 2500},
        'Ch6 Conclusion': {'start': '# Chapter 6: Conclusion', 'end': '# References', 'limit': 1000},
    }

    results = {}
    total_words = 0

    for name, info in chapters.items():
        # Extract chapter text
        start_idx = md_text.find(info['start'])
        end_idx = md_text.find(info['end'], start_idx + 1) if info['end'] else len(md_text)

        if start_idx == -1:
            print(f"WARNING: Could not find start of {name}")
            continue
        if end_idx == -1:
            end_idx = len(md_text)

        chapter_text = md_text[start_idx:end_idx]
        chapter_lines = chapter_text.split('\n')

        # Count words excluding non-counted elements
        word_count = 0
        in_code_block = False
        in_table = False
        excluded_lines = []
        counted_lines = []

        for line in chapter_lines:
            stripped = line.strip()

            # Track code blocks
            if stripped.startswith('```'):
                in_code_block = not in_code_block
                excluded_lines.append(f"  [CODE FENCE] {stripped[:60]}")
                continue

            if in_code_block:
                excluded_lines.append(f"  [CODE] {stripped[:60]}")
                continue

            # Skip horizontal rules
            if stripped in ['---', '***', '___']:
                continue

            # Skip empty lines
            if not stripped:
                continue

            # Skip image references
            if re.match(r'^!\[.*\]\(.*\)', stripped):
                excluded_lines.append(f"  [IMAGE] {stripped[:60]}")
                continue

            # Skip figure/table captions (italic lines starting with *Figure or *Table)
            if (stripped.startswith('*Figure') or stripped.startswith('*Table')) and stripped.endswith('*'):
                excluded_lines.append(f"  [CAPTION] {stripped[:60]}")
                continue

            # Skip table rows (lines with |)
            if '|' in stripped and (stripped.startswith('|') or re.match(r'^[\s|:-]+$', stripped)):
                # Check if it's a table row
                cells = [c.strip() for c in stripped.strip('|').split('|')]
                if len(cells) >= 2:
                    excluded_lines.append(f"  [TABLE] {stripped[:60]}")
                    continue

            # Skip headings from word count? Actually headings ARE counted.
            # Count this line
            words_in_line = len(stripped.split())

            # Remove markdown formatting for accurate count
            clean = stripped
            # Remove heading markers
            clean = re.sub(r'^#{1,4}\s+', '', clean)
            # Remove bold/italic markers
            clean = re.sub(r'\*{1,3}', '', clean)
            # Remove inline code backticks but keep the text
            clean = re.sub(r'`([^`]*)`', r'\1', clean)
            # Remove link syntax but keep text: [text](url) -> text
            clean = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', clean)
            # Remove any remaining markdown artifacts
            clean = clean.strip()

            words = len(clean.split()) if clean else 0
            word_count += words
            if words > 0:
                counted_lines.append(f"  [{words:3d}w] {clean[:80]}")

        results[name] = {
            'words': word_count,
            'limit': info['limit'],
            'over': word_count - info['limit'],
            'excluded': excluded_lines,
            'counted_sample': counted_lines[:5] + ['  ...'] + counted_lines[-3:] if len(counted_lines) > 8 else counted_lines
        }
        total_words += word_count

    return results, total_words


def main():
    md_text = MD_FILE.read_text(encoding='utf-8')
    results, total = count_words_by_chapter(md_text)

    print("=" * 72)
    print("DRAFT REPORT WORD COUNT VERIFICATION")
    print("=" * 72)
    print()
    print(f"{'Chapter':<30} {'Words':>7} {'Limit':>7} {'Remaining':>10} {'Status':>8}")
    print("-" * 72)

    any_over = False
    for name, data in results.items():
        remaining = data['limit'] - data['words']
        status = "✅ OK" if remaining >= 0 else "❌ OVER"
        if remaining < 0:
            any_over = True
        print(f"{name:<30} {data['words']:>7,} {data['limit']:>7,} {remaining:>+10,} {status:>8}")

    print("-" * 72)
    total_limit = 9500
    total_remaining = total_limit - total
    total_status = "✅ OK" if total_remaining >= 0 else "❌ OVER"
    print(f"{'TOTAL':<30} {total:>7,} {total_limit:>7,} {total_remaining:>+10,} {total_status:>8}")
    print("=" * 72)

    if any_over:
        print()
        print("⚠️  CHAPTERS EXCEEDING WORD LIMIT:")
        for name, data in results.items():
            if data['over'] > 0:
                print(f"  → {name}: {data['over']} words over limit")
                print(f"    Need to cut approximately {data['over']} words")

    # Show excluded items summary
    print()
    print("EXCLUDED FROM COUNT (not counted per instructions):")
    print("-" * 72)
    for name, data in results.items():
        code_count = sum(1 for l in data['excluded'] if '[CODE' in l)
        table_count = sum(1 for l in data['excluded'] if '[TABLE]' in l)
        image_count = sum(1 for l in data['excluded'] if '[IMAGE]' in l)
        caption_count = sum(1 for l in data['excluded'] if '[CAPTION]' in l)
        if any([code_count, table_count, image_count, caption_count]):
            items = []
            if code_count: items.append(f"{code_count} code lines")
            if table_count: items.append(f"{table_count} table rows")
            if image_count: items.append(f"{image_count} images")
            if caption_count: items.append(f"{caption_count} captions")
            print(f"  {name}: {', '.join(items)}")


if __name__ == '__main__':
    main()
