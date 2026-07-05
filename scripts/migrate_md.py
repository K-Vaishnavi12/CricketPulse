"""Replace `st.markdown(f'''<html>''', unsafe_allow_html=True)` -> `_md(f'''<html>''')`.

Only touches markdown() calls that use triple-quoted strings AND have
unsafe_allow_html=True. Leaves single-line markdown calls alone.
"""
import re
from pathlib import Path

path = Path('src/dashboard/app.py')
text = path.read_text(encoding='utf-8')

# Pattern:  st.markdown(f?"""...""", unsafe_allow_html=True)
# We match across newlines. The body is non-greedy up to the closing triple-quote.
pattern = re.compile(
    r'st\.markdown\(\s*(f?"""(?:[^"]|"(?!""))*""")\s*,\s*unsafe_allow_html\s*=\s*True\s*\)',
    re.DOTALL,
)

def replacer(m):
    body = m.group(1)
    return f'_md({body})'

new_text, n = pattern.subn(replacer, text)
if n == 0:
    print("No matches found - already migrated?")
else:
    path.write_text(new_text, encoding='utf-8')
    print(f"Replaced {n} st.markdown(triple-quoted-html, unsafe_allow_html=True) call(s) with _md(...)")
