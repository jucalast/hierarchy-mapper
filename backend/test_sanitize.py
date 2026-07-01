import sys
sys.path.insert(0, '.')
from modules.agent.service.core.loop_utils import _sanitize_messages

# Exact pattern from the raw log bug:
# user(real) → assistant(tool_use) → user(EMPTY) → assistant(DUPLICATE tool_use) → user(tool_result)
msgs = [
    {"role": "user", "content": "mude o stage para qualificação"},
    {"role": "assistant", "content": [{"type": "tool_use", "id": "call_ecf3c817", "name": "pipedrive_update_deal", "input": {"deal_id": 2571, "fields": {"stage_id": 2}}}]},
    {"role": "user", "content": []},  # EMPTY — causes Gemini to skip it
    {"role": "assistant", "content": [{"type": "tool_use", "id": "call_ecf3c817", "name": "pipedrive_update_deal", "input": {"deal_id": 2571, "fields": {"stage_id": 2}}}]},  # DUPLICATE
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_ecf3c817", "tool_name": "pipedrive_update_deal", "content": '{"ok":true,"result":"Deal atualizado"}'}]},
]

result = _sanitize_messages(msgs)
print(f"Input: {len(msgs)} messages")
print(f"Output: {len(result)} messages")
print()
for m in result:
    content = m['content']
    if isinstance(content, str):
        print(f"  [{m['role']}] TEXT: {content[:60]}")
    elif isinstance(content, list):
        for b in content:
            if b.get('type') == 'tool_use':
                print(f"  [{m['role']}] tool_use: {b['name']} id={b['id']}")
            elif b.get('type') == 'tool_result':
                print(f"  [{m['role']}] tool_result: {b.get('tool_name')} content={b.get('content','')[:40]}")
            else:
                print(f"  [{m['role']}] {b}")

expected_roles = ["user", "assistant", "user"]
actual_roles = [m["role"] for m in result]
print()
print(f"Expected roles: {expected_roles}")
print(f"Actual roles:   {actual_roles}")
print(f"PASS: {expected_roles == actual_roles}")
