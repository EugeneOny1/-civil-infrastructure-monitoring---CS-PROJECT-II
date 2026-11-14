import json
import sys

FORBIDDEN_PII = {
    'user_id',
    'submitted_by_name',
    'submitted_by_email',
    'email',
    'engineer_notes',
    'inspection_notebook',
    'password_hash'
}

def main():
    if len(sys.argv) < 2:
        print("Usage: eval_public_reports.py <raw_json_response> [max_limit]")
        sys.exit(1)

    raw = sys.argv[1].strip()
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    if not raw:
        print("ERROR: Empty response body received from /api/reports/public/recent")
        sys.exit(2)

    try:
        data = json.loads(raw)
    except Exception as exc:
        print(f"INVALID_JSON: Unable to parse response: {raw[:150]}")
        sys.exit(3)

    if not isinstance(data, dict):
        print(f"CONTRACT_MISMATCH: Expected root JSON object (dict), got {type(data).__name__}")
        sys.exit(4)

    if "error" in data:
        print(f"API_ERROR: Public reports endpoint returned error: {data.get('error')}")
        sys.exit(5)

    if "reports" not in data:
        print(f"CONTRACT_MISMATCH: Missing 'reports' key in response. Keys found: {list(data.keys())}")
        sys.exit(6)

    reports = data["reports"]
    if not isinstance(reports, list):
        print(f"CONTRACT_MISMATCH: 'reports' field is not a list, got {type(reports).__name__}")
        sys.exit(7)

    if "count" not in data:
        print(f"CONTRACT_MISMATCH: Missing 'count' key in response. Keys found: {list(data.keys())}")
        sys.exit(8)

    count = data["count"]
    if not isinstance(count, int):
        print(f"CONTRACT_MISMATCH: 'count' field is not an integer, got {type(count).__name__}")
        sys.exit(9)

    if count != len(reports):
        print(f"CONTRACT_MISMATCH: 'count' ({count}) does not match len(reports) ({len(reports)})")
        sys.exit(10)

    if len(reports) > limit:
        print(f"LIMIT_EXCEEDED: Number of reports ({len(reports)}) exceeds requested limit ({limit})")
        sys.exit(11)

    for idx, item in enumerate(reports):
        if not isinstance(item, dict):
            print(f"ITEM_MISMATCH: Report item {idx} is not a dict: {type(item).__name__}")
            sys.exit(12)

        leaked_pii = FORBIDDEN_PII.intersection(item.keys())
        if leaked_pii:
            print(f"PRIVACY_VIOLATION: Report item {idx} contains forbidden PII keys: {leaked_pii}")
            sys.exit(13)

        if "report_id" not in item and "display_id" not in item:
            print(f"ITEM_MISMATCH: Report item {idx} missing report_id and display_id: {item}")
            sys.exit(14)

    print(f"VALID: /api/reports/public/recent returned {count} report(s) (limit <= {limit}, empty-safe, privacy-preserved).")
    sys.exit(0)

if __name__ == '__main__':
    main()
