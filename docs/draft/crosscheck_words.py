#!/usr/bin/env python3
"""Quick cross-check of total word count."""
import re
from pathlib import Path

text = (Path(__file__).parent / "draft_report.md").read_text()

ref_start = text.find('# References')
ch1_start = text.find('# Chapter 1')
body = text[ch1_start:ref_start]

# Remove code blocks
body = re.sub(r'```.*?```', '', body, flags=re.DOTALL)
# Remove table rows
lines = body.split('\n')
non_table = [l for l in lines if not (l.strip().startswith('|') or re.match(r'^[\s|:-]+$', l.strip()))]
body = '\n'.join(non_table)
# Remove image refs
body = re.sub(r'!\[.*?\]\(.*?\)', '', body)
# Remove figure/table captions
body = re.sub(r'^\*(?:Figure|Table).*?\*$', '', body, flags=re.MULTILINE)
# Remove horizontal rules
body = re.sub(r'^---$', '', body, flags=re.MULTILINE)
# Remove LaTeX math blocks (these are figures/formulas)
body = re.sub(r'\$\$.*?\$\$', '', body, flags=re.DOTALL)
# Clean markdown syntax but keep words
body = re.sub(r'\*{1,3}', '', body)
body = re.sub(r'`([^`]*)`', r'\1', body)
body = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', body)
body = re.sub(r'^#{1,4}\s+', '', body, flags=re.MULTILINE)

words = body.split()
total = len(words)
print(f"Total body words (cross-check): {total}")
print()

# Also count the claim in the document header
print("Header states: ~8,700 words")
print(f"Actual count:  ~{total:,} words")
print()
if total > 9500:
    print(f"❌ OVER LIMIT by {total - 9500} words")
elif total < 6000:
    print(f"⚠️  SIGNIFICANTLY UNDER - only {total/9500*100:.0f}% of allowance used")
    print(f"   You have room for ~{9500 - total:,} more words")
else:
    print(f"✅ Within limit ({9500 - total:,} words remaining)")
