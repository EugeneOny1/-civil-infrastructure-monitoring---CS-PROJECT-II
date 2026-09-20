from flask import Blueprint, request, jsonify
from ..models.asset import InfrastructureAsset
from ..services.database import db_service
from ..utils.auth_helpers import login_required, role_required

assets_bp = Blueprint('assets', __name__, url_prefix='/api/assets')

@assets_bp.route('', methods=['GET'])
@login_required
def list_assets(current_user):
    """Returns registered civil infrastructure assets."""
    asset_type = request.args.get('type')
    query = {}
    if asset_type:
        query['asset_type'] = asset_type

    records = db_service.find('infrastructure_assets', query)
    assets = [InfrastructureAsset.from_dict(r).to_dict() for r in records]
    return jsonify({'assets': assets, 'count': len(assets)}), 200

@assets_bp.route('/<asset_id>', methods=['GET'])
@login_required
def get_asset(current_user, asset_id):
    """Returns details and inspection history for a single asset."""
    asset_data = db_service.find_one('infrastructure_assets', {'_id': asset_id})
    if not asset_data:
        return jsonify({'error': 'Infrastructure asset not found.'}), 404

    asset = InfrastructureAsset.from_dict(asset_data).to_dict()
    reports = db_service.find('infrastructure_reports', {'asset_id': asset_id})
    return jsonify({'asset': asset, 'reports': reports}), 200

@assets_bp.route('', methods=['POST'])
@role_required('engineer', 'admin')
def create_asset(current_user):
    """Registers a new infrastructure asset in the monitored network."""
    data = request.get_json() or {}
    asset_type = data.get('asset_type', 'Road / Pavement')
    location = data.get('location', '').strip()
    description = data.get('description', '').strip()
    current_condition = data.get('current_condition', 'Good')
    coordinates = data.get('coordinates', {'lat': -1.2921, 'lng': 36.8219})

    if not location:
        return jsonify({'error': 'Asset location is required.'}), 400

    asset = InfrastructureAsset(
        asset_type=asset_type,
        location=location,
        description=description,
        current_condition=current_condition,
        coordinates=coordinates
    )
    asset_id = db_service.insert('infrastructure_assets', asset.to_dict())
    asset.asset_id = asset_id

    return jsonify({'message': 'Asset registered successfully.', 'asset': asset.to_dict()}), 201
