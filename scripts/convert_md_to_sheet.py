#!/usr/bin/env python3
"""Convert the evaluation_survey.md into a CSV suitable for Google Sheets import.

Usage:
    python scripts/convert_md_to_sheet.py docs/evaluation_survey.md data/survey_questions.csv

The output CSV has columns: Type, Question, Option1, Option2, ...
Type is one of: multiple choice, checkboxes, linear scale, short answer, paragraph.

For linear scale items the options encode:  Option1=min, Option2=max,
    Option3=low_label (optional), Option4=high_label (optional).
"""
import csv
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# Matches question headers in these formats:
#   ### Q1. text
#   **Q5. text**
#   **Q5. text**  (with trailing bold)
_Q_HEADER_RE = re.compile(
    r'^(?:#{1,4}\s*)?(?:\*\*)?Q(\d{1,3})\.\s*(.*?)(?:\*\*)?$'
)
_OPTION_RE = re.compile(r'^[-*]\s*\[.\]\s*(.+)$')
_TABLE_ROW_RE = re.compile(r'^\|')
_TABLE_Q_RE = re.compile(r'Q(\d{1,3})\.\s*(.*)')
_UNDERSCORE_RE = re.compile(r'^_{3,}$')


def _split_table_cells(line: str) -> list[str]:
    """Split a markdown table row into trimmed cells (dropping empties)."""
    return [c.strip() for c in line.split('|') if c.strip()]


def parse_markdown(md_text: str) -> list[dict]:
    lines = md_text.splitlines()
    questions: list[dict] = []
    current: dict | None = None

    # State for Q19-style grid tables
    grid_columns: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # ---- Question header (### Q1. or **Q5.**) ----
        m = _Q_HEADER_RE.match(line)
        if m:
            if current:
                questions.append(current)
            qtext = m.group(2).strip().rstrip('*')
            # Handle question text that wraps to the next line
            # (e.g. **Q13. Would you be willing to trade some recommendation
            #  accuracy for better privacy?**)
            while qtext and not qtext.endswith('?') and (i + 1) < len(lines):
                next_line = lines[i + 1].strip()
                # Stop if next line is an option, separator, or new question
                if (next_line.startswith('- [') or next_line.startswith('|')
                        or _Q_HEADER_RE.match(next_line) or next_line == '---'
                        or not next_line):
                    break
                i += 1
                qtext += ' ' + next_line.rstrip('*').strip()
            current = {
                'id': int(m.group(1)),
                'question': qtext,
                'options': [],
                'type': None,           # explicit type override
            }
            grid_columns = []           # reset grid state
            i += 1
            continue

        # ---- Table row with embedded Q-number (SUS table Q14-Q18) ----
        if _TABLE_ROW_RE.match(line) and _TABLE_Q_RE.search(line):
            tm = _TABLE_Q_RE.search(line)
            # Only treat as a new question if this is NOT a table header
            # and actually contains checkbox markers
            if tm and '[ ]' in line:
                if current:
                    questions.append(current)
                    current = None
                # Extract just the statement text before the first |
                raw_q = tm.group(2).strip()
                # Remove trailing table cells: ' | [ ] 1 | [ ] 2 | ...'
                raw_q = raw_q.split('|')[0].strip().rstrip('|').strip()
                questions.append({
                    'id': int(tm.group(1)),
                    'question': raw_q,
                    'options': ['1', '5', 'Strongly Disagree', 'Strongly Agree'],
                    'type': 'linear scale',
                })
                i += 1
                continue

        if current is None:
            i += 1
            continue

        # ---- Checkbox / bullet option: - [ ] Option ----
        mopt = _OPTION_RE.match(line)
        if mopt:
            opt = re.sub(r'_+', '', mopt.group(1)).strip()
            if opt:
                current['options'].append(opt)
            i += 1
            continue

        # ---- Table option rows for scale questions (Q8, Q12 style) ----
        # e.g.  | [ ] 1 | Not relevant at all |
        if (_TABLE_ROW_RE.match(line) and '[ ]' in line
                and current and current['type'] != 'grid'):
            cells = _split_table_cells(line)
            if len(cells) >= 2:
                val = cells[0].replace('[ ]', '').replace('[x]', '').strip()
                desc = cells[1].strip()
                current['options'].append(f'{val} - {desc}')
                # If we see numeric 1..5-style options, hint as scale
                if val.isdigit():
                    current.setdefault('_scale_vals', []).append(int(val))
            i += 1
            continue

        # ---- Grid table header (Q19 feature assessment header row) ----
        # Only match tables whose first column is "Feature" (not "Statement"
        # which is the SUS Likert table handled via embedded Q-numbers).
        if (_TABLE_ROW_RE.match(line) and current
                and '---' not in line and '[ ]' not in line):
            cells = _split_table_cells(line)
            # Detect a Feature/rating header like:
            # | Feature | Not Useful | Slightly Useful | ... |
            if (len(cells) >= 3 and cells[0].lower() == 'feature'
                    and any('useful' in c.lower() for c in cells)):
                grid_columns = cells[1:]    # column labels
                current['type'] = 'grid'
                current['_grid_cols'] = grid_columns
                current['_grid_rows'] = []
                i += 1
                continue

        # ---- Grid data rows (| Track search | [ ] | [ ] | … |) ----
        if (_TABLE_ROW_RE.match(line) and current
                and current.get('type') == 'grid' and '[ ]' in line):
            cells = _split_table_cells(line)
            if cells:
                feature = cells[0].replace('[ ]', '').strip()
                if feature and '---' not in feature:
                    current['_grid_rows'].append(feature)
            i += 1
            continue

        # ---- Table separator / header rows — skip ----
        if _TABLE_ROW_RE.match(line):
            i += 1
            continue

        # ---- Underscore lines → paragraph / open text ----
        if _UNDERSCORE_RE.match(line):
            current['type'] = 'paragraph'
            i += 1
            continue

        i += 1

    if current:
        questions.append(current)

    return questions


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify(q: dict) -> str:
    """Return the form question type string."""
    if q.get('type'):
        return q['type']

    opts = q.get('options', [])
    qtext = q.get('question', '').lower()

    if 'select all' in qtext:
        return 'checkboxes'

    if not opts:
        return 'paragraph'

    # Detect scale pattern: all options are "N - description"
    scale_vals = q.get('_scale_vals', [])
    if len(scale_vals) >= 3 and scale_vals == list(range(min(scale_vals),
                                                          max(scale_vals) + 1)):
        return 'linear scale'

    return 'multiple choice'


# ---------------------------------------------------------------------------
# Expansion & CSV writing
# ---------------------------------------------------------------------------

def _expand(questions: list[dict]) -> list[dict]:
    """Expand grid questions into individual rows; finalise scale options."""
    out: list[dict] = []
    for q in questions:
        qtype = classify(q)

        # Convert detected-scale multiple-choice into proper linear scale
        if qtype == 'linear scale' and q.get('_scale_vals'):
            vals = q['_scale_vals']
            lo, hi = min(vals), max(vals)
            # Try to extract label text from "1 - description" style options
            lo_label = hi_label = ''
            for o in q['options']:
                parts = o.split(' - ', 1)
                if len(parts) == 2:
                    if parts[0].strip() == str(lo):
                        lo_label = parts[1].strip()
                    elif parts[0].strip() == str(hi):
                        hi_label = parts[1].strip()
            new_opts = [str(lo), str(hi)]
            if lo_label:
                new_opts.append(lo_label)
            if hi_label:
                new_opts.append(hi_label)
            out.append({**q, 'options': new_opts, 'type': 'linear scale'})
            continue

        # Expand grid questions into one row per feature
        if qtype == 'grid':
            cols = q.get('_grid_cols', [])
            for feature in q.get('_grid_rows', []):
                out.append({
                    'id': q['id'],
                    'question': f'{q["question"]} [{feature}]',
                    'options': cols,
                    'type': 'multiple choice',
                })
            continue

        out.append({**q, 'type': qtype})
    return out


def write_csv(questions: list[dict], outfile: str):
    rows = _expand(questions)
    max_opts = max((len(q.get('options', [])) for q in rows), default=0)
    headers = ['Type', 'Question'] + [f'Option{i+1}' for i in range(max_opts)]
    Path(outfile).parent.mkdir(parents=True, exist_ok=True)
    with open(outfile, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for q in rows:
            opts = q.get('options', [])
            row = [q.get('type', 'paragraph'), q.get('question', '')]
            row.extend(opts)
            row.extend([''] * (max_opts - len(opts)))
            writer.writerow(row)
    print(f'Wrote {len(rows)} rows to {outfile}')


def main(argv):
    if len(argv) < 3:
        print('Usage: convert_md_to_sheet.py <input.md> <output.csv>')
        return 1
    infile = argv[1]
    outfile = argv[2]
    text = Path(infile).read_text(encoding='utf-8')
    questions = parse_markdown(text)
    write_csv(questions, outfile)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
