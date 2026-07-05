"""Find any st.markdown() calls with indented HTML that Streamlit will misrender."""
import re
import sys

content = open('src/dashboard/app.py', encoding='utf-8').read()
lines = content.split('\n')

# find `st.markdown(f"""` or `st.markdown("""` followed by a line starting with 4+ spaces then `<`
issues = []
in_block = False
block_start = 0
indent = 0
for i, line in enumerate(lines, start=1):
    if not in_block:
        m = re.match(r"\s*st\.markdown\(f?\"\"\"\s*$", line)
        if m:
            in_block = True
            block_start = i
            indent = 0
    else:
        # first non-empty line after the opener
        if indent == 0 and line.strip():
            leading = len(line) - len(line.lstrip(' '))
            if leading >= 4 and line.lstrip().startswith('<'):
                issues.append((block_start, leading, line.strip()[:60]))
            indent = leading if leading > 0 else 1
        if '"""' in line:
            in_block = False
            indent = 0

if issues:
    print(f"Found {len(issues)} potentially misrendered HTML block(s):")
    for line_no, ind, snippet in issues:
        print(f"  line {line_no}: {ind} spaces indent  ->  {snippet}")
else:
    print("No indented-HTML-in-markdown bugs remaining.")
