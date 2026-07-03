import json

log_path = r"C:\Users\João Luccas\.gemini\antigravity-cli\brain\8fc0659d-7b59-40b6-b014-6792944b4527\.system_generated\logs\transcript.jsonl"

with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            content = data.get('content', '')
            if not content:
                continue
            
            # Look for browser console logs printed by the client/system
            # Or text describing the logs
            if 'State Monitor' in content or 'Reset Effect' in content:
                print(content[:300])
        except Exception as e:
            pass
