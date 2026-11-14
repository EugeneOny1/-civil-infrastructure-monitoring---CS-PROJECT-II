import json
import sys

def main():
    if len(sys.argv) < 4:
        print("Usage: eval_readiness.py <http_code> <expected_model> <raw_body>")
        sys.exit(1)

    code = sys.argv[1].strip()
    expected_model = sys.argv[2].strip()
    raw = sys.argv[3].strip()

    if code == '000':
        print("CONNECTING: Endpoint not yet reachable or accepting connections")
        sys.exit(2)

    try:
        data = json.loads(raw)
    except Exception as exc:
        print(f"INVALID_JSON (HTTP {code}): raw={raw[:120]}")
        sys.exit(3)

    status = data.get('status')
    model_loaded = data.get('model_loaded')
    db_ready = data.get('database_ready')
    model = data.get('model')

    if code == '200' and status == 'ready' and model_loaded is True and db_ready is True and model == expected_model:
        print(f"READY: model={model}, database_ready={db_ready}")
        sys.exit(0)
    elif code == '503':
        print(f"INITIALIZING (HTTP 503): model_loaded={model_loaded}, database_ready={db_ready}")
        sys.exit(4)
    else:
        print(f"PENDING (HTTP {code}): status={status}, model={model}, db_ready={db_ready}")
        sys.exit(5)

if __name__ == '__main__':
    main()
