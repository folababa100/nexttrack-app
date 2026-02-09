# NextTrack — Survey Data Collection & Reporting Guide

## Overview

This guide documents the process for collecting user evaluation data and incorporating results into the draft/final report.

---

## Step 1: Create the Digital Survey

Convert `evaluation_survey.md` into a digital form using one of these tools:

| Tool | Pros | Link |
|------|------|------|
| **Google Forms** | Free, auto-generates charts, exports to CSV/Sheets | [forms.google.com](https://forms.google.com) |
| **Microsoft Forms** | UoL students typically have access via Office 365 | [forms.office.com](https://forms.office.com) |
| **Typeform** | Better UX, free tier (10 questions limit) | [typeform.com](https://typeform.com) |

**Recommended:** Google Forms — free, handles all question types (Likert, multiple choice, open text), and auto-generates summary charts you can screenshot for the report.

---

## Step 2: Run Participant Sessions

### Prerequisites

Start the NextTrack API server:

```bash
cd /Users/folababa/Downloads/final-project
python -m uvicorn src.main:app --reload --port 8000
```

Participants open `http://localhost:8000` in their browser.

### For Remote Participants

Use ngrok to create a temporary public URL:

```bash
brew install ngrok
ngrok http 8000
# Share the generated URL with participants
```

### Session Structure (10–15 min per participant)

1. **Brief the participant** (~2 min)
   - Explain what NextTrack is
   - Reassure them: no personal data is collected about them

2. **Task 1: Basic Recommendation** (~3 min)
   - Search for 3 songs from an artist they like
   - Select them and request recommendations

3. **Task 2: Evaluate Recommendations** (~3 min)
   - Rate the quality of the recommendations

4. **Task 3: Adjust Preferences** (~2 min)
   - Set Energy to "High" and Tempo to "Fast"
   - Request new recommendations and re-evaluate

5. **Complete the survey** (~5 min)
   - Participant fills in the Google Form immediately after tasks

6. **Evaluator notes** (you fill in after session)
   - Participant ID, date, session duration
   - Observations, technical issues encountered
   - Your own quality assessment (artist coherence, genre consistency, diversity, overall — each out of 5)

### Target

- **Minimum:** 5 participants
- **Ideal:** 8–10 participants
- **Mix of:** technical levels (beginner to expert), age ranges, streaming platforms

---

## Step 3: Export & Analyse the Data

### Export from Google Forms

1. Open Google Forms → Responses tab
2. Click the Google Sheets icon to view in spreadsheet
3. File → Download → CSV
4. Save to: `data/survey_responses.csv`

### Analysis Script

Save and run the following script:

```python
# scripts/analyse_survey.py
import csv
from collections import Counter

def analyse_survey(filepath="data/survey_responses.csv"):
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        responses = list(reader)

    n = len(responses)
    print(f"Total participants: {n}\n")

    # --- SUS Scores ---
    # Map your Google Form column headers to these keys
    sus_questions = {
        "Easy to use": "Q14",
        "Interface intuitive": "Q16",
        "Felt confident": "Q17",
        "Would use regularly": "Q18",
    }

    print("=== Usability (SUS) ===")
    for label, q in sus_questions.items():
        scores = [int(r[q]) for r in responses if r.get(q)]
        mean = sum(scores) / len(scores) if scores else 0
        print(f"  {label}: {mean:.1f}/5")

    # --- Recommendation Quality ---
    quality_questions = {
        "Relevance": "Q8",
        "Would listen (tracks out of 5)": "Q7",
        "Variety": "Q9",
    }

    print("\n=== Recommendation Quality ===")
    for label, q in quality_questions.items():
        scores = [int(r[q]) for r in responses if r.get(q)]
        if scores:
            mean = sum(scores) / len(scores)
            print(f"  {label}: {mean:.1f}")

    # --- Privacy Perception ---
    print("\n=== Privacy Perception ===")
    privacy_appeal = [int(r["Q12"]) for r in responses if r.get("Q12")]
    if privacy_appeal:
        print(f"  'No tracking' appeal: {sum(privacy_appeal)/len(privacy_appeal):.1f}/5")

    trade_accuracy = Counter(r.get("Q13", "") for r in responses)
    print(f"  Would trade accuracy for privacy: {trade_accuracy}")

    # --- Qualitative Feedback ---
    print("\n=== Qualitative Feedback ===")
    print("\nLiked most:")
    for r in responses:
        if r.get("Q20"):
            print(f"  - \"{r['Q20']}\"")

    print("\nWould improve:")
    for r in responses:
        if r.get("Q21"):
            print(f"  - \"{r['Q21']}\"")

    print("\nBugs/issues:")
    for r in responses:
        if r.get("Q22"):
            print(f"  - \"{r['Q22']}\"")

if __name__ == "__main__":
    analyse_survey()
```

Run it:

```bash
cd /Users/folababa/Downloads/final-project
python scripts/analyse_survey.py
```

---

## Step 4: Calculate SUS Score

The System Usability Scale (SUS) score is calculated as follows:

1. For **positively worded** items (Q14, Q16, Q17, Q18): score contribution = response − 1
2. For **negatively worded** items (Q15): score contribution = 5 − response
3. Sum all contributions per participant, multiply by 2.5
4. Average across all participants

```python
def calculate_sus(responses):
    """Calculate SUS score from survey responses."""
    sus_scores = []
    for r in responses:
        q14 = int(r["Q14"]) - 1          # Easy to use (positive)
        q15 = 5 - int(r["Q15"])          # Need support (negative)
        q16 = int(r["Q16"]) - 1          # Intuitive (positive)
        q17 = int(r["Q17"]) - 1          # Confident (positive)
        q18 = int(r["Q18"]) - 1          # Use regularly (positive)
        total = (q14 + q15 + q16 + q17 + q18) * 2.5
        sus_scores.append(total)
    return sum(sus_scores) / len(sus_scores)
```

### Interpreting the SUS Score

| Score | Rating |
|-------|--------|
| > 80 | Excellent |
| 68–80 | Above average |
| 50–68 | Below average |
| < 50 | Poor |

Reference: Sauro, J. (2011) *A Practical Guide to the System Usability Scale*.

---

## Step 5: Update the Draft Report

Replace placeholder data in `draft_report.md` §5.5 with real results.

### Sections to update:

| Report Section | What to replace |
|----------------|-----------------|
| §5.5.1 Methodology | Participant count, demographics |
| §5.5.2 Usability Results | Table 8 (SUS scores), overall SUS score |
| §5.5.3 Recommendation Quality | Table 9 (mean ratings) |
| §5.5.4 Per-Participant Data | Table 10 (one row per real participant) |
| §5.5.5 Privacy Perception | Table 11 (appeal, trade-off %, concern %) |
| §5.5.6 Qualitative Feedback | Real quotes from Q20, Q21 |
| §5.5.7 Critical Assessment | Update sample size, note any new limitations |

### Template for per-participant table:

```markdown
| Participant | Relevance | Would Listen | vs. Random | Variety |
|-------------|-----------|--------------|------------|---------|
| P1          | ?         | ?            | ?          | ?       |
| P2          | ?         | ?            | ?          | ?       |
| ...         | ...       | ...          | ...        | ...     |
| **Mean**    | **?.??**  | **?.??**     | **?.??**   | **?.??**|
```

---

## Step 6: Generate Charts (Optional)

Charts improve marks. Save this script and run it after collecting data:

```python
# scripts/generate_charts.py
import matplotlib.pyplot as plt

# Replace with your real data
categories = ['Easy to use', 'Intuitive', 'Confident', 'Use regularly']
scores = [4.3, 4.1, 4.0, 3.6]  # Replace with real means

fig, ax = plt.subplots(figsize=(8, 5))
bars = ax.bar(categories, scores, color=['#4CAF50', '#2196F3', '#FF9800', '#9C27B0'])
ax.set_ylim(0, 5)
ax.set_ylabel('Mean Score (out of 5)')
ax.set_title('System Usability Scale Results')
ax.axhline(y=3, color='gray', linestyle='--', alpha=0.5, label='Neutral')

for bar, score in zip(bars, scores):
    ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.1,
            f'{score:.1f}', ha='center', va='bottom', fontweight='bold')

plt.tight_layout()
plt.savefig('docs/figures/sus_scores.png', dpi=150)
print("Saved to docs/figures/sus_scores.png")
```

Run:

```bash
mkdir -p docs/figures
cd /Users/folababa/Downloads/final-project
python scripts/generate_charts.py
```

Then reference in the report:

```markdown
![SUS Scores](figures/sus_scores.png)
*Figure X: System Usability Scale mean scores across N participants.*
```

---

## Timeline Checklist

| Step | Action | When |
|------|--------|------|
| ☐ | Create Google Form from `evaluation_survey.md` | Now |
| ☐ | Recruit 5–10 participants | This week |
| ☐ | Run participant sessions | Over 1–2 weeks |
| ☐ | Export CSV to `data/survey_responses.csv` | After all sessions |
| ☐ | Run `scripts/analyse_survey.py` | After export |
| ☐ | Calculate SUS score | After export |
| ☐ | Replace placeholder data in §5.5 of draft report | Before final submission |
| ☐ | Generate charts (optional) | Before final submission |
| ☐ | Add full survey as Appendix A in final report | Final report only |

---

## Notes

- For the **draft report**, placeholder data is acceptable — markers said *"We don't expect that your project work will be completed by this stage."*
- For the **final report**, replace all placeholders with real participant data.
- The survey itself (Appendix A) does **not** count toward the word limit.
- Adjust the Google Form column headers in the analysis script to match your actual form field names.
