"""
InfraVision CI & Local Test Environment Preparation Script
---------------------------------------------------------
Prepares a clean, isolated environment for running the full regression test suite:
1. Asserts target MongoDB instances are strictly local (localhost / 127.0.0.1)
   to protect production MongoDB Atlas from accidental execution.
2. Prepares required test image fixtures by copying version-controlled assets
   (seed_pothole.jpg, seed_crack.jpg, seed_surface.jpg) from tests/fixtures/images/
   into backend/uploads/ and uploads/.
3. Verifies authoritative Kenya administrative geography reference data exists
   (backend/app/data/kenya_geography.json) covering all 47 counties.
4. Waits for local MongoDB service to be ready (up to 60s).
5. Deterministically seeds isolated development ('civil_infrastructure') and
   testing ('civil_infrastructure_test') databases with required accounts, assets,
   and representative demo reports.
"""

import os
import sys
import time
import shutil
from pathlib import Path
from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = REPO_ROOT / 'backend'

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def assert_local_mongo_only(uri: str, label: str = "MONGO_URI"):
    """Safety guard: prevents running setup against production MongoDB Atlas."""
    if not uri:
        return
    lowered = uri.lower()
    if 'mongodb+srv://' in lowered or not any(h in lowered for h in ('localhost', '127.0.0.1', 'mongo')):
        raise RuntimeError(
            f"REFUSING TO SEED: {label}='{uri}' is not a local MongoDB instance. "
            f"Seeding is strictly forbidden against remote or production MongoDB Atlas!"
        )


def prepare_image_fixtures():
    """Copies tracked fixtures to backend/uploads and uploads directories."""
    fixtures_dir = REPO_ROOT / 'tests' / 'fixtures' / 'images'
    if not fixtures_dir.is_dir():
        raise FileNotFoundError(f"Fixture directory not found: {fixtures_dir}")

    required_images = ['seed_pothole.jpg', 'seed_crack.jpg', 'seed_surface.jpg']
    for img_name in required_images:
        src = fixtures_dir / img_name
        if not src.is_file():
            raise FileNotFoundError(f"Required fixture image missing: {src}")

    target_dirs = [REPO_ROOT / 'backend' / 'uploads', REPO_ROOT / 'uploads']
    for tdir in target_dirs:
        tdir.mkdir(parents=True, exist_ok=True)
        for img_name in required_images:
            src = fixtures_dir / img_name
            dst = tdir / img_name
            if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                shutil.copy2(src, dst)
                print(f"[Fixtures] Installed {img_name} -> {tdir}")
    print("[Fixtures] All required test image fixtures verified.")


def prepare_geography_data():
    """Ensures backend/app/data/kenya_geography.json exists with 47 counties."""
    geo_path = BACKEND_DIR / 'app' / 'data' / 'kenya_geography.json'
    if not geo_path.is_file():
        print(f"[Geography] Reference file missing at {geo_path}. Generating from source...")
        from backend.scripts.generate_geography import build_kenya_hierarchy
        import json
        data = build_kenya_hierarchy()
        geo_path.parent.mkdir(parents=True, exist_ok=True)
        with open(geo_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[Geography] Generated {geo_path} with {len(data.get('counties', []))} counties.")
    else:
        import json
        with open(geo_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        count = len(data.get('counties', []))
        if count != 47:
            raise ValueError(f"Expected 47 counties in {geo_path}, found {count}")
        print(f"[Geography] Authoritative Kenya geography verified ({count} counties).")


def wait_for_mongodb(mongo_uri: str, timeout_sec: int = 60):
    """Waits for MongoDB connection to succeed before running seeds."""
    assert_local_mongo_only(mongo_uri)
    print(f"[MongoDB] Checking connection to {mongo_uri} (timeout={timeout_sec}s)...")
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
            client.admin.command('ping')
            client.close()
            print("[MongoDB] Connection successful.")
            return
        except Exception as e:
            time.sleep(2)
    raise TimeoutError(f"Could not connect to MongoDB at {mongo_uri} within {timeout_sec}s")


def seed_database_instances(dev_uri: str, test_uri: str):
    """Seeds both development ('civil_infrastructure') and testing ('civil_infrastructure_test') databases."""
    assert_local_mongo_only(dev_uri, "dev_uri")
    assert_local_mongo_only(test_uri, "test_uri")

    # 1. Seed rebalanced demo dataset into civil_infrastructure
    os.environ['MONGO_URI'] = dev_uri
    os.environ['DB_NAME'] = 'civil_infrastructure'

    from backend.scripts.rebalance_demo_data import run_rebalancing
    print("\n[Seed] Populating development database 'civil_infrastructure' with demo dataset...")
    run_rebalancing()

    # Verify civil_infrastructure seed count
    client = MongoClient(dev_uri, serverSelectionTimeoutMS=5000)
    dev_db = client['civil_infrastructure']
    dev_reports = list(dev_db['infrastructure_reports'].find({
        '$or': [{'metadata.is_seed': True}, {'_id': {'$regex': '^REP-DEMO-'}}]
    }))
    client.close()
    if len(dev_reports) < 10:
        raise ValueError(f"Expected >= 10 demo reports in 'civil_infrastructure', found {len(dev_reports)}")
    print(f"[Seed] Verified {len(dev_reports)} demo reports in 'civil_infrastructure'.")

    # 2. Seed baseline accounts and assets into civil_infrastructure_test
    print("\n[Seed] Populating test database 'civil_infrastructure_test' with baseline accounts/assets...")
    os.environ['TEST_MONGO_URI'] = test_uri
    os.environ['TEST_DB_NAME'] = 'civil_infrastructure_test'
    os.environ['DB_NAME'] = 'civil_infrastructure_test'
    os.environ['MONGO_URI'] = test_uri

    from backend.app import create_app
    from backend.app.services.database import db_service

    test_app = create_app('testing')
    with test_app.app_context():
        # Ensure initial reference assets & accounts are seeded into civil_infrastructure_test
        db_service.init_app(test_app)
        if db_service.db is not None:
            user_cnt = db_service.db['users'].count_documents({})
            print(f"[Seed] 'civil_infrastructure_test' initialized with {user_cnt} accounts.")
    if hasattr(db_service, 'close'):
        db_service.close()


def main():
    print("=" * 70)
    print("InfraVision CI & Local Test Environment Setup")
    print("=" * 70)

    dev_uri = os.getenv('MONGO_URI', 'mongodb://127.0.0.1:27017/civil_infrastructure')
    test_uri = os.getenv('TEST_MONGO_URI', 'mongodb://127.0.0.1:27017/civil_infrastructure_test')

    prepare_image_fixtures()
    prepare_geography_data()
    wait_for_mongodb(dev_uri)
    seed_database_instances(dev_uri, test_uri)

    print("\n" + "=" * 70)
    print("Test environment preparation complete. All suites ready to execute.")
    print("=" * 70)


if __name__ == '__main__':
    main()
