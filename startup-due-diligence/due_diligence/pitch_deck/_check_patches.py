"""Quick verification that all patches are in place."""
files = {
    'layout_engine': r'c:\Users\AKSHARA\OneDrive\Desktop\Projects\POCs - Qubrid\startup-due-diligence\due_diligence\pitch_deck\layout_engine.py',
    'utils': r'c:\Users\AKSHARA\OneDrive\Desktop\Projects\POCs - Qubrid\startup-due-diligence\due_diligence\utils.py',
    'llm_client': r'c:\Users\AKSHARA\OneDrive\Desktop\Projects\POCs - Qubrid\startup-due-diligence\due_diligence\llm_client.py',
    'content_planner': r'c:\Users\AKSHARA\OneDrive\Desktop\Projects\POCs - Qubrid\startup-due-diligence\due_diligence\pitch_deck\content_planner.py',
    'theme_selector': r'c:\Users\AKSHARA\OneDrive\Desktop\Projects\POCs - Qubrid\startup-due-diligence\due_diligence\pitch_deck\theme_selector.py',
}

checks = {
    'layout_engine': [
        ('risk_assessment in registry', 'risk_assessment'),
        ('standard header fallback', 'standard header fallback'),
    ],
    'utils': [
        ('strip_think_tags function', 'def strip_think_tags'),
        ('think tag removal', '<think>'),
        ('extract_json calls strip_think_tags', 'strip_think_tags(text)'),
    ],
    'llm_client': [
        ('response_format param', 'response_format'),
        ('disable_thinking param', 'disable_thinking'),
        ('json_object mode applied', 'response_format'),
    ],
    'content_planner': [
        ('temperature=0', 'temperature=0'),
        ('json_object mode', 'json_object'),
        ('disable_thinking=True', 'disable_thinking=True'),
        ('density check function', '_check_slide_density'),
        ('density enforce function', '_enforce_density'),
        ('slide body regen function', '_regenerate_slide_body'),
        ('metric regex', '_METRIC_PATTERN'),
        ('MIN_BULLETS constant', '_MIN_BULLETS = 4'),
        ('strip_think_tags import', 'strip_think_tags'),
        ('DENSITY_RETRIES', '_DENSITY_RETRIES'),
    ],
    'theme_selector': [
        ('disable_thinking', 'disable_thinking=True'),
        ('strip_think_tags import', 'strip_think_tags'),
        ('strip applied to response', 'strip_think_tags(raw_text)'),
    ],
}

all_ok = True
for file_key, file_checks in checks.items():
    path = files[file_key]
    with open(path, encoding='utf-8') as f:
        src = f.read()
    for check_name, needle in file_checks:
        ok = needle in src
        status = 'OK  ' if ok else 'FAIL'
        if not ok:
            all_ok = False
        print(f'  {status}  [{file_key}] {check_name}')

print()
print('All checks passed!' if all_ok else 'SOME CHECKS FAILED — review output above')
