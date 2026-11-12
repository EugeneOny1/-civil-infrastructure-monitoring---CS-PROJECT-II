import os
import uuid
from datetime import datetime, timezone
from bson import ObjectId
from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from werkzeug.security import generate_password_hash

class DatabaseService:
    """
    MongoDB service managing the 6 core collections specified in Figure 4.5:
    - users
    - infrastructure_assets
    - infrastructure_reports
    - submitted_images
    - ai_assessments
    - professional_reviews
    
    Includes an in-memory fallback store to ensure development and testing
    can proceed uninterrupted when offline or before Atlas credentials are configured.
    """
    def __init__(self, uri=None, db_name=None):
        self.uri = uri or os.getenv('MONGO_URI', 'mongodb://localhost:27017/civil_infrastructure')
        self.db_name = db_name or os.getenv('DB_NAME', 'civil_infrastructure')
        self.client = None
        self.db = None
        self.use_mock = False
        self._mock_data = {
            'users': {},
            'infrastructure_assets': {},
            'infrastructure_reports': {},
            'submitted_images': {},
            'ai_assessments': {},
            'professional_reviews': {},
            'safety_advisories': {},
            'notifications': {},
            'system_audit_logs': {},
            'citizen_feedback': {}
        }
        self.connect()

    def init_app(self, app):
        """Initializes database connection from Flask application configuration."""
        self.uri = app.config.get('MONGO_URI', self.uri)
        self.db_name = app.config.get('DB_NAME', self.db_name)
        self.connect()

    def connect(self):
        """Attempts connection to MongoDB, falling back to mock store if unavailable."""
        try:
            if self.client is not None:
                try:
                    self.client.close()
                except Exception:
                    pass
            self.client = MongoClient(self.uri, serverSelectionTimeoutMS=2000)
            self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            self.use_mock = False
            safe_uri = self.uri.split('@')[-1] if '@' in self.uri else self.uri
            print(f"[Database] Connected to MongoDB at {safe_uri}")
            self._ensure_indexes()
            self._ensure_initial_seeds()
        except (ConnectionFailure, ServerSelectionTimeoutError, Exception) as e:
            self.use_mock = True
            print(f"[Database] MongoDB connection not available ({e}). Using in-memory mock store for development.")
            self._seed_mock_data()

    def _ensure_indexes(self):
        """Creates required collection indexes."""
        if not self.use_mock and self.db is not None:
            try:
                self.db['users'].create_index([('email', ASCENDING)], unique=True)
                self.db['infrastructure_reports'].create_index([('user_id', ASCENDING)])
                self.db['infrastructure_reports'].create_index([('date_submitted', -1)])
            except Exception as e:
                print(f"[Database] Index setup note: {e}")

    def _seed_mock_data(self):
        """Seeds realistic default assets and accounts without fabricated personas or measurements."""
        admin_id = 'usr_admin_01'
        engineer_id = 'usr_eng_01'
        citizen_id = 'usr_cit_01'

        now_iso = datetime.now(timezone.utc).isoformat()

        # Seed Primary Administrative & Operational Accounts
        self._mock_data['users'][admin_id] = {
            '_id': admin_id,
            'name': 'System Administrator',
            'email': 'admin@strathmore.edu',
            'password_hash': generate_password_hash('Admin@123'),
            'role': 'admin',
            'verification_status': 'verified',
            'two_factor_enabled': True,
            'must_change_password': True,
            'created_at': now_iso
        }
        self._mock_data['users'][engineer_id] = {
            '_id': engineer_id,
            'name': 'Eng. Civil Infrastructure Reviewer',
            'email': 'engineer@kenha.go.ke',
            'password_hash': generate_password_hash('Engineer@123'),
            'role': 'engineer',
            'engineering_category': 'Professional Engineer',
            'professional_reg_no': 'A3947',
            'organization': 'KeNHA',
            'verification_status': 'verified',
            'two_factor_enabled': True,
            'must_change_password': True,
            'created_at': now_iso
        }
        self._mock_data['users'][citizen_id] = {
            '_id': citizen_id,
            'name': 'Citizen Reporter',
            'email': 'citizen@strathmore.edu',
            'password_hash': generate_password_hash('Citizen@123'),
            'role': 'citizen',
            'verification_status': 'verified',
            'two_factor_enabled': False,
            'must_change_password': True,
            'created_at': now_iso
        }

        # Monitored Nairobi Infrastructure Assets
        asset_1 = 'ast_uhuru_01'
        asset_2 = 'ast_outer_02'
        asset_3 = 'ast_nyayo_03'

        self._mock_data['infrastructure_assets'][asset_1] = {
            '_id': asset_1,
            'asset_type': 'Road / Pavement',
            'location': 'Uhuru Highway (Chainage 14+350)',
            'description': 'Primary urban arterial carriageway subject to continuous heavy traffic.',
            'current_condition': 'Critical',
            'coordinates': {'lat': -1.2921, 'lng': 36.8219},
            'created_at': now_iso
        }
        self._mock_data['infrastructure_assets'][asset_2] = {
            '_id': asset_2,
            'asset_type': 'Bridge',
            'location': 'Outer Ring Road Viaduct (Pier 4)',
            'description': 'Elevated reinforced concrete bridge section.',
            'current_condition': 'Fair',
            'coordinates': {'lat': -1.2758, 'lng': 36.8835},
            'created_at': now_iso
        }
        self._mock_data['infrastructure_assets'][asset_3] = {
            '_id': asset_3,
            'asset_type': 'Building',
            'location': 'Nyayo Municipal Annex',
            'description': 'Public civil structure perimeter retaining wall.',
            'current_condition': 'Poor',
            'coordinates': {'lat': -1.3005, 'lng': 36.8231},
            'created_at': now_iso
        }

        # Seed realistic sample reports with Kenya County attribution
        rep_1 = 'REP-2026-0001'
        img_1 = 'img_seed_01'
        ass_1 = 'ass_seed_01'

        self._mock_data['infrastructure_reports'][rep_1] = {
            '_id': rep_1,
            'report_id': rep_1,
            'user_id': citizen_id,
            'asset_id': asset_1,
            'description': 'Road surface cavity observed across center southbound carriageway.',
            'status': 'Received',
            'date_submitted': now_iso,
            'latitude': -1.2921,
            'longitude': 36.8219,
            'county': 'Nairobi',
            'metadata': {
                'location_name': 'Uhuru Highway near Nyayo Stadium, Nairobi',
                'county': 'Nairobi',
                'asset_type': 'Road / Pavement',
                'priority': 'Critical',
                'relative_severity': 'Critical',
                'validation_status': 'valid',
                'is_unusual': False,
                'requires_engineer_review': True,
                'latitude': -1.2921,
                'longitude': 36.8219
            }
        }
        self._mock_data['submitted_images'][img_1] = {
            '_id': img_1,
            'report_id': rep_1,
            'image_path': 'seed_pothole.jpg',
            'original_filename': 'pothole_inspection.jpg',
            'file_size': 1024500,
            'upload_date': now_iso,
            'dimensions': {'width': 1280, 'height': 720}
        }
        self._mock_data['ai_assessments'][ass_1] = {
            '_id': ass_1,
            'report_id': rep_1,
            'image_id': img_1,
            'defect_class': 'Pothole',
            'confidence_score': 0.946,
            'bounding_box': [0.22, 0.25, 0.72, 0.78],
            'relative_severity': 'Critical',
            'area_percentage': 26.5,
            'detections': [
                {
                    'defect_class': 'Pothole',
                    'confidence_score': 0.946,
                    'bounding_box': [0.22, 0.25, 0.72, 0.78],
                    'area_ratio': 0.265
                }
            ],
            'model_name': 'SSD-MobileNetV2',
            'model_version': 'ssd_mobilenet_v2_lr00015_step1500_v2_1',
            'class_id': 2,
            'class_name': 'Pothole',
            'validation_status': 'valid',
            'created_at': now_iso
        }

        # Seed Active Safety Advisory for rep_1 (composite marker & context popup verification)
        adv_1 = 'adv_seed_01'
        self._mock_data['safety_advisories'][adv_1] = {
            '_id': adv_1,
            'advisory_id': adv_1,
            'report_id': rep_1,
            'latitude': -1.2921,
            'longitude': 36.8219,
            'location_name': 'Uhuru Highway near Nyayo Stadium, Nairobi',
            'status': 'active',
            'note': 'Reduce speed across center southbound carriageway due to severe pavement depression.',
            'created_at': now_iso,
            'issued_at': now_iso
        }

        # Seed additional reports to provide baseline statistical volume for Nairobi
        rep_2 = 'REP-2026-0002'
        img_2 = 'img_seed_02'
        ass_2 = 'ass_seed_02'
        self._mock_data['infrastructure_reports'][rep_2] = {
            '_id': rep_2,
            'report_id': rep_2,
            'user_id': citizen_id,
            'asset_id': asset_2,
            'description': 'Structural longitudinal crack on viaduct support beam.',
            'status': 'Verified',
            'date_submitted': now_iso,
            'latitude': -1.2758,
            'longitude': 36.8835,
            'county': 'Nairobi',
            'metadata': {
                'location_name': 'Outer Ring Road Viaduct, Nairobi',
                'county': 'Nairobi',
                'asset_type': 'Bridge',
                'priority': 'Medium',
                'relative_severity': 'Medium',
                'validation_status': 'valid',
                'is_unusual': False,
                'requires_engineer_review': False,
                'latitude': -1.2758,
                'longitude': 36.8835
            }
        }
        self._mock_data['ai_assessments'][ass_2] = {
            '_id': ass_2,
            'report_id': rep_2,
            'image_id': img_2,
            'defect_class': 'Crack',
            'confidence_score': 0.892,
            'relative_severity': 'Medium',
            'area_percentage': 12.0,
            'model_name': 'SSD-MobileNetV2',
            'created_at': now_iso
        }

        rep_3 = 'REP-2026-0003'
        img_3 = 'img_seed_03'
        ass_3 = 'ass_seed_03'
        self._mock_data['infrastructure_reports'][rep_3] = {
            '_id': rep_3,
            'report_id': rep_3,
            'user_id': citizen_id,
            'asset_id': asset_3,
            'description': 'Surface deterioration along municipal retaining wall perimeter.',
            'status': 'Received',
            'date_submitted': now_iso,
            'latitude': -1.3005,
            'longitude': 36.8231,
            'county': 'Nairobi',
            'metadata': {
                'location_name': 'Nyayo Municipal Annex, Nairobi',
                'county': 'Nairobi',
                'asset_type': 'Building',
                'priority': 'Low',
                'relative_severity': 'Low',
                'validation_status': 'valid',
                'is_unusual': False,
                'requires_engineer_review': False,
                'latitude': -1.3005,
                'longitude': 36.8231
            }
        }
        self._mock_data['ai_assessments'][ass_3] = {
            '_id': ass_3,
            'report_id': rep_3,
            'image_id': img_3,
            'defect_class': 'Surface deterioration',
            'confidence_score': 0.854,
            'relative_severity': 'Low',
            'area_percentage': 8.5,
            'model_name': 'SSD-MobileNetV2',
            'created_at': now_iso
        }

    def _ensure_initial_seeds(self):
        """Seeds initial assets and accounts into MongoDB if database is empty."""
        try:
            if self.db['users'].count_documents({}) == 0:
                self._seed_mock_data()
                for col_name, items in self._mock_data.items():
                    for doc in items.values():
                        self.db[col_name].update_one({'_id': doc['_id']}, {'$setOnInsert': doc}, upsert=True)
                print("[Database] Initial reference infrastructure assets, reports, and accounts seeded into MongoDB.")
        except Exception as e:
            print(f"[Database] Seeding note: {e}")

    # Collection Operations
    def insert(self, collection_name, doc):
        doc = dict(doc)
        if '_id' not in doc or not doc['_id']:
            doc['_id'] = str(uuid.uuid4())

        if not self.use_mock:
            self.db[collection_name].insert_one(doc)
            return doc['_id']
        else:
            col = self._mock_data.setdefault(collection_name, {})
            col[doc['_id']] = doc
            return doc['_id']

    def _get_nested(self, item, key):
        if not key or not isinstance(item, dict):
            return None
        if '.' not in key:
            return item.get(key)
        curr = item
        for part in key.split('.'):
            if isinstance(curr, dict):
                curr = curr.get(part)
            else:
                return None
        return curr

    def _matches_query(self, item, query):
        if not query:
            return True
        for k, v in query.items():
            if k == '$or' and isinstance(v, list):
                if not any(self._matches_query(item, sub_q) for sub_q in v):
                    return False
            elif k == '$and' and isinstance(v, list):
                if not all(self._matches_query(item, sub_q) for sub_q in v):
                    return False
            elif isinstance(v, dict):
                val = self._get_nested(item, k)
                for op, op_val in v.items():
                    if op == '$ne' and val == op_val:
                        return False
                    elif op == '$in' and (not isinstance(op_val, (list, tuple, set)) or val not in op_val):
                        return False
                    elif op == '$nin' and (isinstance(op_val, (list, tuple, set)) and val in op_val):
                        return False
            else:
                val = self._get_nested(item, k)
                if val != v:
                    return False
        return True

    def find_one(self, collection_name, query):
        if not self.use_mock:
            doc = self.db[collection_name].find_one(self._format_query(query))
            return self._clean_doc(doc)
        else:
            col = self._mock_data.setdefault(collection_name, {})
            for item in col.values():
                if self._matches_query(item, query):
                    return dict(item)
            return None

    def find(self, collection_name, query=None, sort_key=None, reverse=False):
        if query is None:
            query = {}
        if not self.use_mock:
            cursor = self.db[collection_name].find(self._format_query(query))
            if sort_key:
                cursor = cursor.sort(sort_key, -1 if reverse else 1)
            return [self._clean_doc(d) for d in cursor]
        else:
            results = []
            col = self._mock_data.setdefault(collection_name, {})
            for item in col.values():
                if self._matches_query(item, query):
                    results.append(dict(item))
            if sort_key:
                results.sort(key=lambda x: x.get(sort_key, ''), reverse=reverse)
            return results

    def count(self, collection_name, query=None):
        """Returns document count for collection matching query."""
        if query is None:
            query = {}
        if not self.use_mock and self.db is not None:
            return self.db[collection_name].count_documents(self._format_query(query))
        else:
            return len(self.find(collection_name, query))

    def update_one(self, collection_name, query, update_values, upsert=False):
        if not self.use_mock and self.db is not None:
            return self.db[collection_name].update_one(self._format_query(query), {'$set': update_values}, upsert=upsert)
        else:
            col = self._mock_data.setdefault(collection_name, {})
            item = self.find_one(collection_name, query)
            if item:
                target_id = item['_id']
                col[target_id].update(update_values)
                return True
            elif upsert:
                doc = dict(query)
                doc.update(update_values)
                self.insert(collection_name, doc)
                return True
            return False

    def update_many(self, collection_name, query, update_values):
        if not self.use_mock and self.db is not None:
            return self.db[collection_name].update_many(self._format_query(query), {'$set': update_values})
        else:
            col = self._mock_data.setdefault(collection_name, {})
            items = self.find(collection_name, query)
            for item in items:
                target_id = item['_id']
                col[target_id].update(update_values)
            return True

    def delete_one(self, collection_name, query):
        if not self.use_mock:
            return self.db[collection_name].delete_one(self._format_query(query))
        else:
            col = self._mock_data.setdefault(collection_name, {})
            item = self.find_one(collection_name, query)
            if item and item['_id'] in col:
                del col[item['_id']]
                return True
            return False

    def delete_many(self, collection_name, query):
        if not self.use_mock and self.db is not None:
            return self.db[collection_name].delete_many(self._format_query(query))
        else:
            col = self._mock_data.setdefault(collection_name, {})
            items = self.find(collection_name, query)
            for item in items:
                if item['_id'] in col:
                    del col[item['_id']]
            return True

    def _format_query(self, query):
        formatted = {}
        for k, v in query.items():
            if k == '_id' and isinstance(v, str) and ObjectId.is_valid(v):
                formatted['$or'] = [{'_id': v}, {'_id': ObjectId(v)}]
            else:
                formatted[k] = v
        return formatted

    def _clean_doc(self, doc):
        if doc and '_id' in doc and isinstance(doc['_id'], ObjectId):
            doc['_id'] = str(doc['_id'])
        return doc

# Global singleton database instance
db_service = DatabaseService()
