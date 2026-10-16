import re

with open('app.js', 'r', encoding='utf-8') as f:
    app_js = f.read()

with open('index.html', 'r', encoding='utf-8') as f:
    index_html = f.read()

ids_in_js = set(re.findall(r"document\.getElementById\(['\"]([^'\"]+)['\"]", app_js))
ids_in_html = set(re.findall(r"id=['\"]([^'\"]+)['\"]", index_html))

missing = [i for i in ids_in_js if i not in ids_in_html]
print(f'Total IDs in JS: {len(ids_in_js)}')
print(f'Missing IDs count: {len(missing)}')
if missing:
    print('Missing IDs:', missing)
else:
    print('ALL element IDs exist in index.html!')
