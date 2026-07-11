from pathlib import Path

path = Path(__file__).with_name("apply_classifier_precedence_patch.py")
text = path.read_text(encoding="utf-8")
calculator_block = '''    if re.search(r"/calcul|/calculator|/simulateur|/simulation", p):
        return "calculator"
'''
loan_block = '''    if BROAD_LOAN_SEGMENT_RE.search(clean):
        return "loan_program"
'''
if calculator_block not in text or loan_block not in text:
    raise SystemExit("Classifier ordering anchors not found")
text = text.replace(calculator_block, "", 1)
text = text.replace(loan_block, loan_block + calculator_block, 1)
path.write_text(text, encoding="utf-8")
