import uuid
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

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
    def __init__(self, uri='mongodb://localhost:27017/civil_infrastructure', db_name='civil_infrastructure'):
        self.uri = uri
        self.db_name = db_name
        self.client = None
        self.db = None
        self.use_mock = False
        self._mock_data = {
            'users': {},
            'infrastructure_assets': {},
            'infrastructure_reports': {},
            'submitted_images': {},
            'ai_assessments': {},
            'professional_reviews': {}
        }
        self.connect()

    def connect(self):
        """Attempts connection to MongoDB, falling back to mock store if unavailable."""
        try:
            self.client = MongoClient(self.uri, serverSelectionTimeoutMS=2000)
            # Trigger server connection check
            self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            self.use_mock = False
            print(f"[Database] Connected to MongoDB at {self.uri.split('@')[-1] if '@' in self.uri else self.uri}")
            self._ensure_initial_seeds()
        except (ConnectionFailure, ServerSelectionTimeoutError, Exception) as e:
            self.use_mock = True
            print(f"[Database] MongoDB connection not available ({e}). Using robust in-memory mock store for development.")
            self._seed_mock_data()

    def _ensure_initial_seeds(self):
        """Seeds initial data into MongoDB if the database has not been seeded yet."""
        try:
            if self.db['infrastructure_assets'].count_documents({}) == 0:
                self._seed_mock_data()
                for col_name, items in self._mock_data.items():
                    for doc in items.values():
                        self.db[col_name].update_one({'_id': doc['_id']}, {'$setOnInsert': doc}, upsert=True)
                print("[Database] Initial infrastructure assets, reports, and accounts seeded into MongoDB.")
        except Exception as e:
            print(f"[Database] Note during seeding: {e}")

    def _seed_mock_data(self):
        """Seeds initial realistic assets and demo accounts matching proposal wireframes (Figure 4.7)."""
        from werkzeug.security import generate_password_hash

        # Demo Users
        admin_id = 'usr_admin_01'
        engineer_id = 'usr_eng_01'
        citizen_id = 'usr_cit_01'

        self._mock_data['users'][admin_id] = {
            '_id': admin_id,
            'name': 'Infrastructure Admin',
            'email': 'admin@infravision.ke',
            'password_hash': generate_password_hash('Admin@123'),
            'role': 'admin',
            'verification_status': 'verified',
            'created_at': datetime.utcnow().isoformat()
        }
        self._mock_data['users'][engineer_id] = {
            '_id': engineer_id,
            'name': 'Eng. Elena (Lead Certifier)',
            'email': 'elena@kenha.go.ke',
            'password_hash': generate_password_hash('Engineer@123'),
            'role': 'engineer',
            'verification_status': 'verified',
            'created_at': datetime.utcnow().isoformat()
        }
        self._mock_data['users'][citizen_id] = {
            '_id': citizen_id,
            'name': 'Eugene Onyango',
            'email': 'citizen@strathmore.edu',
            'password_hash': generate_password_hash('Citizen@123'),
            'role': 'citizen',
            'verification_status': 'verified',
            'created_at': datetime.utcnow().isoformat()
        }

        # Seed Assets matching Figure 4.7 Wireframe
        asset_1 = 'ast_uhuru_01'
        asset_2 = 'ast_outer_02'
        asset_3 = 'ast_nyayo_03'

        self._mock_data['infrastructure_assets'][asset_1] = {
            '_id': asset_1,
            'asset_type': 'Road / Pavement',
            'location': 'Uhuru Highway (Chainage 14+350)',
            'description': 'Primary urban arterial carriageway subject to heavy freight load.',
            'current_condition': 'Critical',
            'coordinates': {'lat': -1.2921, 'lng': 36.8219},
            'created_at': datetime.utcnow().isoformat()
        }
        self._mock_data['infrastructure_assets'][asset_2] = {
            '_id': asset_2,
            'asset_type': 'Bridge',
            'location': 'Outer Ring Road Viaduct (Pier 4)',
            'description': 'Elevated concrete bridge section with expansion joints.',
            'current_condition': 'Fair',
            'coordinates': {'lat': -1.2758, 'lng': 36.8835},
            'created_at': datetime.utcnow().isoformat()
        }
        self._mock_data['infrastructure_assets'][asset_3] = {
            '_id': asset_3,
            'asset_type': 'Building',
            'location': 'Nyayo Municipal Annex',
            'description': 'Public administrative building perimeter retaining facade.',
            'current_condition': 'Poor',
            'coordinates': {'lat': -1.3005, 'lng': 36.8231},
            'created_at': datetime.utcnow().isoformat()
        }

        # Seed Initial Reports & Assessments matching Figure 4.7
        rep_1 = 'INFRA-2024-0982-A'
        img_1 = 'img_seed_01'
        ass_1 = 'ass_seed_01'

        self._mock_data['infrastructure_reports'][rep_1] = {
            '_id': rep_1,
            'user_id': citizen_id,
            'asset_id': asset_1,
            'description': 'Severe road pothole cluster (depth ~68mm) causing vehicular obstruction.',
            'status': 'Pending',
            'date_submitted': datetime.utcnow().isoformat(),
            'metadata': {'location_name': 'Uhuru Highway near Nyayo Stadium', 'asset_type': 'Road / Pavement'}
        }
        self._mock_data['submitted_images'][img_1] = {
            '_id': img_1,
            'report_id': rep_1,
            'image_path': 'seed_pothole.jpg',
            'original_filename': 'pothole_sample.jpg',
            'file_size': 1024500,
            'upload_date': datetime.utcnow().isoformat(),
            'dimensions': {'width': 1280, 'height': 720}
        }
        self._mock_data['ai_assessments'][ass_1] = {
            '_id': ass_1,
            'image_id': img_1,
            'defect_class': 'Pothole',
            'confidence_score': 0.946,
            'bounding_box': [0.22, 0.25, 0.72, 0.78],
            'relative_severity': 'Critical',
            'detections': [
                {
                    'defect_class': 'Pothole',
                    'confidence_score': 0.946,
                    'bounding_box': [0.22, 0.25, 0.72, 0.78],
                    'area_ratio': 0.265
                }
            ],
            'model_name': 'SSD-MobileNetV2',
            'created_at': datetime.utcnow().isoformat()
        }

    # Collection Operations
    def insert(self, collection_name, doc):
        doc = dict(doc)
        if '_id' not in doc or not doc['_id']:
            doc['_id'] = str(uuid.uuid4())
        
        if not self.use_mock:
            self.db[collection_name].insert_one(doc)
            return doc['_id']
        else:
            self._mock_data[collection_name][doc['_id']] = doc
            return doc['_id']

    def find_one(self, collection_name, query):
        if not self.use_mock:
            return self.db[collection_name].find_one(query)
        else:
            for item in self._mock_data[collection_name].values():
                match = True
                for k, v in query.items():
                    if item.get(k) != v:
                        match = False
                        break
                if match:
                    return dict(item)
            return None

    def find(self, collection_name, query=None, sort_key=None, reverse=False):
        if query is None:
            query = {}
        if not self.use_mock:
            cursor = self.db[collection_name].find(query)
            if sort_key:
                cursor = cursor.sort(sort_key, -1 if reverse else 1)
            return list(cursor)
        else:
            results = []
            for item in self._mock_data[collection_name].values():
                match = True
                for k, v in query.items():
                    if item.get(k) != v:
                        match = False
                        break
                if match:
                    results.append(dict(item))
            if sort_key:
                results.sort(key=lambda x: x.get(sort_key, ''), reverse=reverse)
            return results

    def update_one(self, collection_name, query, update_values):
        if not self.use_mock:
            return self.db[collection_name].update_one(query, {'$set': update_values})
        else:
            item = self.find_one(collection_name, query)
            if item:
                target_id = item['_id']
                self._mock_data[collection_name][target_id].update(update_values)
                return True
            return False

# Global database instance initialized lazily or on import
db_service = DatabaseService()
