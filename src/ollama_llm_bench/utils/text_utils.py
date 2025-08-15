import json


def extract_json(s):
    start_index = s.find('{')
    end_index = s.rfind('}')
    if start_index == -1 or end_index == -1 or end_index < start_index:
        return s
    return s[start_index:end_index + 1]


def sanitize_json_string(input_string: str) -> str:
    json_string = input_string

    if json_string.startswith('<start_of_turn>'):
        json_string = json_string[16:]
    if json_string.endswith('</start_of_turn>'):
        json_string = json_string[:-16]
    if json_string.startswith('<end_of_turn>'):
        json_string = json_string[16:]
    if json_string.endswith('</end_of_turn>'):
        json_string = json_string[:-16]
    if json_string.startswith("```json"):
        json_string = json_string[7:]
    if json_string.endswith("```"):
        json_string = json_string[:-3]
    json_string = json_string.strip()

    return extract_json(json_string)


def parse_judge_response(json_string: str) -> tuple[bool, float, str]:
    has_error = False
    try:
        json_string = sanitize_json_string(json_string)
        data = json.loads(json_string)
        reason = data.get("reason", "")
        grade = float(data.get("grade", 0.0))
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        has_error = True
        reason = f"Failed to parse judge response: {str(e)}"
        grade = 0.0
    return has_error, grade, reason
