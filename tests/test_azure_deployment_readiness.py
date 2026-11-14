"""
Automated Verification Suite: Azure Container Apps & Azure Blob Storage Readiness.
Validates:
1. StorageService 'azure' backend initialization (Managed Identity via AZURE_CLIENT_ID
   and optional AZURE_STORAGE_CONNECTION_STRING fallback).
2. Mocked Azure Blob persistence under 'reports/<filename>' in private containers.
3. Explicit failure semantics: failed Azure uploads clean temp files and raise RuntimeError
   (never silently falling back to ephemeral container disk).
4. Cross-restart / cross-replica simulation: serve_file retrieves from mocked Azure Blob Storage
   when the local ephemeral file has been removed.
5. Path traversal protection & extension validation preserved across storage backends.
6. Production security defaults: ProductionConfig enforces DEBUG=False, ENABLE_DEMO_OTP=False,
   and non-wildcard CORS_ORIGINS (same-origin).
7. Genuine readiness probes (/ready and /api/ready): HTTP 200 when SavedModel loaded, 503 when not.
8. V2.1 SavedModel provenance (file existence, exact SHA-256 checksum, serving_default signature).
9. PowerShell deployment script (deploy_azure.ps1) syntax and required Azure parameters.

NOTE: Mocked Azure storage tests validate StorageService integration contracts locally and are NOT
claimed as proof of live Azure cloud connectivity until executed against provisioned Azure resources.
"""

import hashlib
import io
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from PIL import Image
from werkzeug.datastructures import FileStorage

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / 'backend'
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.app import create_app
from backend.app.config import ProductionConfig
from backend.app.services.inference import inference_service
from backend.app.services.storage import StorageService


def _make_test_image_storage(filename='road_test.jpg', color=(110, 120, 130)):
    buf = io.BytesIO()
    Image.new('RGB', (120, 120), color=color).save(buf, format='JPEG')
    buf.seek(0)
    return FileStorage(stream=buf, filename=filename, content_type='image/jpeg')


class TestAzureDeploymentReadiness(unittest.TestCase):
    """Validates Azure Blob Storage integration, probes, security config, and V2.1 model provenance."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.client = cls.app.test_client()

    def test_01_azure_storage_managed_identity_upload_and_temp_cleanup(self):
        """Mocked Azure test: verifies Managed Identity upload to private container and temp cleanup."""
        mock_blob_client = MagicMock()
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client

        mock_service_client = MagicMock()
        mock_service_client.get_container_client.return_value = mock_container_client

        svc = StorageService(
            backend='azure',
            azure_account_url='https://infravisionsttest.blob.core.windows.net',
            azure_container_name='defect-images',
            azure_client_id='test-client-id-1234'
        )

        with patch('azure.identity.DefaultAzureCredential') as mock_cred_cls, \
             patch('azure.storage.blob.BlobServiceClient', return_value=mock_service_client) as mock_bsc_cls, \
             self.app.app_context():
            fs = _make_test_image_storage('azure_pothole.jpg')
            unique_name, dest_path, orig_name, file_size, storage_url = svc.save_file(fs)

            mock_cred_cls.assert_called_once_with(managed_identity_client_id='test-client-id-1234')
            mock_bsc_cls.assert_called_once()
            mock_service_client.get_container_client.assert_called_once_with('defect-images')
            mock_container_client.get_blob_client.assert_called_once_with(f'reports/{unique_name}')
            mock_blob_client.upload_blob.assert_called_once()
            self.assertEqual(orig_name, 'azure_pothole.jpg')
            self.assertGreater(file_size, 0)
            self.assertEqual(storage_url, f'/api/reports/images/{unique_name}')
            self.assertTrue(os.path.exists(dest_path))

            # Simulate post-inference temp cleanup
            svc.cleanup_local_temp_file(dest_path)
            self.assertFalse(os.path.exists(dest_path))

    def test_02_azure_upload_failure_never_silently_falls_back_to_local(self):
        """Azure upload failure must clean temp file and raise RuntimeError explicitly."""
        mock_blob_client = MagicMock()
        mock_blob_client.upload_blob.side_effect = ConnectionError('Simulated Azure outage')
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_service_client = MagicMock()
        mock_service_client.get_container_client.return_value = mock_container_client

        svc = StorageService(
            backend='azure',
            azure_account_url='https://infravisionsttest.blob.core.windows.net',
            azure_container_name='defect-images',
        )

        upload_dir = Path(self.app.config['UPLOAD_FOLDER'])
        before_files = set(p.name for p in upload_dir.glob('infra_*'))

        with patch('azure.identity.DefaultAzureCredential'), \
             patch('azure.storage.blob.BlobServiceClient', return_value=mock_service_client), \
             self.app.app_context():
            fs = _make_test_image_storage('fail_upload.jpg')
            with self.assertRaises(RuntimeError) as ctx:
                svc.save_file(fs)
            self.assertIn('Azure Blob Storage', str(ctx.exception))

        after_files = set(p.name for p in upload_dir.glob('infra_*'))
        self.assertEqual(before_files, after_files, 'Temp upload must be cleaned up on Azure failure')

    def test_03_azure_missing_credentials_raises_explicit_error(self):
        """Missing AZURE_STORAGE_ACCOUNT_URL and connection string raises RuntimeError on save_file."""
        svc = StorageService(
            backend='azure',
            azure_account_url='',
            azure_container_name='defect-images',
            azure_connection_string='',
        )
        with self.app.app_context():
            fs = _make_test_image_storage('missing_creds.jpg')
            with self.assertRaises(RuntimeError):
                svc.save_file(fs)

    def test_04_azure_serve_file_persists_without_local_disk_copy(self):
        """Mocked Azure test: verifies serve_file streams blob content cleanly when local disk file is absent."""
        img_bytes = io.BytesIO()
        Image.new('RGB', (80, 80), color=(20, 40, 60)).save(img_bytes, format='JPEG')
        raw_jpeg = img_bytes.getvalue()

        mock_downloader = MagicMock()
        mock_downloader.readall.return_value = raw_jpeg

        mock_props = MagicMock()
        mock_props.content_settings.content_type = 'image/jpeg'

        mock_blob_client = MagicMock()
        mock_blob_client.exists.return_value = True
        mock_blob_client.download_blob.return_value = mock_downloader
        mock_blob_client.get_blob_properties.return_value = mock_props

        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_service_client = MagicMock()
        mock_service_client.get_container_client.return_value = mock_container_client

        svc = StorageService(
            backend='azure',
            azure_connection_string='DefaultEndpointsProtocol=https;AccountName=demo;AccountKey=fakekey==;EndpointSuffix=core.windows.net',
            azure_container_name='defect-images',
        )

        with patch('azure.storage.blob.BlobServiceClient.from_connection_string', return_value=mock_service_client), \
             self.app.test_request_context():
            resp = svc.serve_file('infra_restarted_replica_9999.jpg')
            try:
                resp.direct_passthrough = False
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.mimetype, 'image/jpeg')
                self.assertIn('private', resp.headers.get('Cache-Control', ''))
                self.assertEqual(resp.get_data(), raw_jpeg)
            finally:
                resp.close()

    def test_05_readiness_probe_reflects_savedmodel_state(self):
        """Readiness endpoints (/ready, /api/ready) return 200 when loaded and 503 when unavailable."""
        resp_ready = self.client.get('/ready')
        self.assertEqual(resp_ready.status_code, 200)
        self.assertEqual(resp_ready.get_json().get('status'), 'ready')
        self.assertEqual(resp_ready.get_json().get('model'), 'ssd_mobilenet_v2_lr00015_step1500_v2_1')

        with patch.object(inference_service, 'is_loaded', False):
            resp_unready = self.client.get('/api/ready')
            self.assertEqual(resp_unready.status_code, 503)
            self.assertEqual(resp_unready.get_json().get('status'), 'initializing')

            # Lightweight liveness probe stays HTTP 200
            resp_live = self.client.get('/health')
            self.assertEqual(resp_live.status_code, 200)

    def test_06_production_security_defaults(self):
        """ProductionConfig enforces DEBUG=False, no demo OTP fallback by default, and no wildcard CORS."""
        self.assertFalse(ProductionConfig.DEBUG)
        self.assertFalse(ProductionConfig.ENABLE_DEMO_OTP)
        self.assertNotEqual(ProductionConfig.CORS_ORIGINS, '*')

    def test_07_v2_1_savedmodel_provenance_and_checksum(self):
        """Verifies exact V2.1 SavedModel files, SHA-256 digest, and serving_default signature."""
        model_dir = REPO_ROOT / 'backend' / 'models' / 'structural_defect_detector'
        pb_file = model_dir / 'saved_model.pb'
        fp_file = model_dir / 'fingerprint.pb'
        var_data = model_dir / 'variables' / 'variables.data-00000-of-00001'
        var_idx = model_dir / 'variables' / 'variables.index'
        self.assertTrue(pb_file.is_file())
        self.assertTrue(fp_file.is_file())
        self.assertTrue(var_data.is_file())
        self.assertTrue(var_idx.is_file())
        self.assertEqual(hashlib.sha256(pb_file.read_bytes()).hexdigest(), '384977d303af3e293dfbff4ae922cd0e7fd8a72b9a9713bb08b9378fc2f205a9')
        self.assertEqual(hashlib.sha256(fp_file.read_bytes()).hexdigest(), 'e8536ffb467db6879a7d0207a272cd0c9c10c19381c4224e3d9cbb253b69f4ee')
        self.assertEqual(hashlib.sha256(var_data.read_bytes()).hexdigest(), '48c9c32dc59d15f281e69a18125489210693e1fe1fa5c4c2e8971630322efa7e')
        self.assertEqual(hashlib.sha256(var_idx.read_bytes()).hexdigest(), '1e4861f42b49fafc321fe8dba62bf8aa66513c6744df5cb720e51d99d109ea42')
        self.assertTrue(inference_service.is_loaded)
        self.assertEqual(inference_service.model_version, 'ssd_mobilenet_v2_lr00015_step1500_v2_1')

    def test_08_deploy_azure_ps1_syntax_and_contracts(self):
        """Validates deploy_azure.ps1 parses with zero PowerShell syntax errors and defines Azure safeguards."""
        ps1_path = REPO_ROOT / 'deploy_azure.ps1'
        self.assertTrue(ps1_path.is_file())
        content = ps1_path.read_text(encoding='utf-8')
        for token in (
            'infravision-rg',
            'infravision-env',
            'defect-images',
            'ssd_mobilenet_v2_lr00015_step1500_v2_1',
            'Azure for Students',
            'Storage Blob Data Contributor',
            'minReplicas: 0',
            'maxReplicas: 2',
        ):
            self.assertIn(token, content)

        if os.name == 'nt':
            cmd = [
                'powershell',
                '-NoProfile',
                '-Command',
                f"$errors=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('{ps1_path}', [ref]$null, [ref]$errors); if($errors.Count -gt 0){{ $errors | ForEach-Object {{ Write-Error $_ }}; exit 1 }}"
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            self.assertEqual(proc.returncode, 0, f"PowerShell syntax errors in deploy_azure.ps1: {proc.stderr}")

    def test_09_production_db_unavailable_fails_explicitly(self):
        """ProductionConfig requires persistent MongoDB and fails loudly rather than using mock store."""
        from backend.app.services.database import DatabaseService, db_service

        self.assertTrue(ProductionConfig.REQUIRE_PERSISTENT_DB)
        with self.assertRaises(RuntimeError) as ctx:
            DatabaseService(
                uri='mongodb://127.0.0.1:27999/civil_infrastructure?serverSelectionTimeoutMS=500',
                db_name='civil_infrastructure',
                require_persistent_db=True,
            )
        self.assertIn('Persistent MongoDB connection is required in production', str(ctx.exception))

        # Restore /ready probe check when REQUIRE_PERSISTENT_DB is enabled but db_service is disconnected
        with patch.dict(self.app.config, {'REQUIRE_PERSISTENT_DB': True}), \
             patch.object(db_service, 'is_connected', return_value=False):
            resp = self.client.get('/ready')
            self.assertEqual(resp.status_code, 503)
            self.assertFalse(resp.get_json().get('database_ready'))

    def test_10_github_actions_workflow_and_cloudshell_contracts(self):
        """Validates GitHub Actions workflow and Azure Cloud Shell provisioner definitions."""
        wf_path = REPO_ROOT / '.github' / 'workflows' / 'deploy-azure.yml'
        cs_path = REPO_ROOT / 'scripts' / 'provision_azure_infra.sh'
        self.assertTrue(wf_path.is_file())
        self.assertTrue(cs_path.is_file())

        wf = wf_path.read_text(encoding='utf-8')
        for expected in (
            'workflow_dispatch',
            'id-token: write',
            'azure/login@v2',
            '384977d303af3e293dfbff4ae922cd0e7fd8a72b9a9713bb08b9378fc2f205a9',
            '1e4861f42b49fafc321fe8dba62bf8aa66513c6744df5cb720e51d99d109ea42',
            'ssd_mobilenet_v2_lr00015_step1500_v2_1',
            'ghcr.io',
            'sha-${GITHUB_SHA}',
            'REQUIRE_PERSISTENT_DB',
            'infravision-identity',
            'uaenorth',
            'AZURE_RUNTIME_CLIENT_ID',
            '/ready',
            '/health',
            '/api/health',
        ):
            self.assertIn(expected, wf)

        cs = cs_path.read_text(encoding='utf-8')
        for expected in (
            '--allow-blob-public-access false',
            '--public-access off',
            'Storage Blob Data Contributor',
            'infravision-identity',
            'infravision-github-deploy',
            'az identity federated-credential',
            'api://AzureADTokenExchange',
            'AZURE_CLIENT_ID',
            'AZURE_RUNTIME_CLIENT_ID',
            'uaenorth',
        ):
            self.assertIn(expected, cs)

    def test_11_historical_upload_classifier_and_non_destructive_migration(self):
        """Historical image audit excludes unreferenced test files and skips existing blobs."""
        import tempfile
        from backend.scripts.migrate_uploads_to_azure_blob import (
            classify_local_uploads,
            upload_files_to_azure,
        )

        with tempfile.TemporaryDirectory() as tmp:
            primary = Path(tmp) / 'backend_uploads'
            secondary = Path(tmp) / 'uploads'
            primary.mkdir()
            secondary.mkdir()

            (primary / 'infra_real_1.jpg').write_bytes(b'real1')
            (primary / 'infra_orphan_test.jpg').write_bytes(b'orphan')
            (primary / 'seed_pothole.jpg').write_bytes(b'seed')
            (secondary / 'infra_real_1.jpg').write_bytes(b'dup')
            (secondary / 'infra_orphan_sec.jpg').write_bytes(b'orphan2')

            summary = classify_local_uploads(
                {'infra_real_1.jpg'},
                primary_dir=primary,
                secondary_dir=secondary,
            )
            self.assertEqual(list(summary['migration_candidates'].keys()), ['infra_real_1.jpg'])
            self.assertEqual(list(summary['seed_files'].keys()), ['seed_pothole.jpg'])
            self.assertEqual(summary['unreferenced_primary'], ['infra_orphan_test.jpg'])
            self.assertEqual(summary['missing_from_disk'], [])

            # Verify mocked upload skips already existing blobs cleanly and preserves local files
            existing_blob = MagicMock()
            existing_blob.exists.return_value = True
            new_blob = MagicMock()
            new_blob.exists.return_value = False
            container_client = MagicMock()
            container_client.get_blob_client.side_effect = lambda name: (
                existing_blob if name == 'reports/infra_real_1.jpg' else new_blob
            )

            stats = upload_files_to_azure(
                {
                    'infra_real_1.jpg': primary / 'infra_real_1.jpg',
                    'seed_pothole.jpg': primary / 'seed_pothole.jpg',
                },
                container_client,
                overwrite=False,
            )
            self.assertEqual(stats, {'uploaded': 1, 'skipped_existing': 1, 'failed': 0})
            existing_blob.upload_blob.assert_not_called()
            new_blob.upload_blob.assert_called_once()
            self.assertTrue((primary / 'infra_real_1.jpg').is_file())

    def test_12_atlas_migration_redaction_and_non_destructive_upsert(self):
        """Atlas migration utility redacts credentials and preserves existing Atlas documents."""
        from pymongo import UpdateOne
        from backend.scripts.migrate_mongo_to_atlas import migrate_collection, redact_uri

        redacted = redact_uri('mongodb+srv://admin:SuperSecretPass@cluster0.xyz.mongodb.net/civil_infrastructure')
        self.assertNotIn('SuperSecretPass', redacted)
        self.assertIn('cluster0.xyz.mongodb.net/civil_infrastructure', redacted)

        src_col = MagicMock()
        src_col.find.return_value = [{'_id': 'doc_1', 'status': 'Verified'}, {'_id': 'doc_2', 'status': 'Received'}]
        tgt_col = MagicMock()
        tgt_res = MagicMock()
        tgt_res.upserted_count = 1
        tgt_res.modified_count = 0
        tgt_col.bulk_write.return_value = tgt_res

        stats = migrate_collection(src_col, tgt_col, overwrite=False)
        self.assertEqual(stats['inserted'], 1)
        self.assertEqual(stats['skipped_existing'], 1)
        ops = tgt_col.bulk_write.call_args[0][0]
        self.assertTrue(all(isinstance(op, UpdateOne) for op in ops))


if __name__ == '__main__':
    unittest.main()

