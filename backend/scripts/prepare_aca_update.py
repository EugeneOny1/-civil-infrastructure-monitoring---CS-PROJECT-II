#!/usr/bin/env python3
"""
InfraVision — Azure Container Apps Coordinated Update Preparation

Generates a clean, coordinated Azure Container Apps update payload.
Ensures private registry credentials (ACR with managed identity) and container image
are updated atomically, preventing Azure from attempting to reprovision obsolete images.
"""

import json
import sys
from typing import Any, Dict


def transform_aca_config(
    app_data: Dict[str, Any],
    acr_server: str,
    identity_id: str,
    acr_image: str,
    expected_model: str,
    runtime_client_id: str,
) -> Dict[str, Any]:
    """Transform existing Container App JSON into a clean update payload.

    - Replaces registry credentials with ACR + Managed Identity
    - Removes obsolete GHCR tokens
    - Updates container image to ACR image
    - Strips unsupported revision suffixes
    - Preserves all secrets, networking, probes, scaling, and environment variables
    """
    props = app_data.get('properties', {})
    config = props.setdefault('configuration', {})

    # 1. Coordinated registry configuration: Managed identity for ACR
    config['registries'] = [
        {
            'server': acr_server,
            'identity': identity_id,
        }
    ]

    # 2. Clean up obsolete GHCR token references from secrets
    if 'secrets' in config and isinstance(config['secrets'], list):
        config['secrets'] = [s for s in config['secrets'] if s.get('name') != 'ghcr-token']

    # 3. Coordinated template update: Update container image to ACR
    template = props.setdefault('template', {})
    # Express consumption environment does not support custom revision suffixes
    template.pop('revisionSuffix', None)

    containers = template.setdefault('containers', [])
    if containers:
        containers[0]['image'] = acr_image
        envs = containers[0].setdefault('env', [])
        env_dict = {e.get('name'): e for e in envs if 'name' in e}

        for k, v in [
            ('MODEL_VERSION', expected_model),
            ('REQUIRE_PERSISTENT_DB', 'True'),
            ('AZURE_CLIENT_ID', runtime_client_id),
        ]:
            if k in env_dict:
                env_dict[k]['value'] = v
            else:
                envs.append({'name': k, 'value': v})

    # Construct clean resource payload for coordinated update
    clean_payload: Dict[str, Any] = {
        'location': app_data.get('location'),
        'properties': {
            'managedEnvironmentId': props.get('managedEnvironmentId'),
            'configuration': config,
            'template': template,
        },
    }
    if 'identity' in app_data:
        clean_payload['identity'] = app_data['identity']

    return clean_payload


def main() -> None:
    if len(sys.argv) < 8:
        print(
            "Usage: prepare_aca_update.py <in_json> <out_yaml> <acr_server> <identity_id> <acr_image> <expected_model> <runtime_client_id>",
            file=sys.stderr,
        )
        sys.exit(1)

    in_path, out_path, acr_server, identity_id, acr_image, expected_model, runtime_client_id = sys.argv[1:8]

    with open(in_path, 'r', encoding='utf-8') as fh:
        app_data = json.load(fh)

    clean_payload = transform_aca_config(
        app_data,
        acr_server=acr_server,
        identity_id=identity_id,
        acr_image=acr_image,
        expected_model=expected_model,
        runtime_client_id=runtime_client_id,
    )

    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(clean_payload, fh, indent=2)


if __name__ == '__main__':
    main()
