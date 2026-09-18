from datetime import datetime

class InfrastructureAsset:
    """
    InfrastructureAsset entity mapping to Figure 4.3 Class Diagram and Figure 4.5 Database Schema.
    Represents monitored roads, bridges, and buildings in the infrastructure network.
    """
    def __init__(self, asset_type, location, description='', current_condition='Good', asset_id=None, coordinates=None, created_at=None):
        self.asset_id = str(asset_id) if asset_id else None
        self.asset_type = asset_type  # 'Road / Pavement', 'Bridge', 'Building'
        self.location = location      # e.g., 'Uhuru Highway near Nyayo Stadium'
        self.description = description
        self.current_condition = current_condition  # 'Good', 'Fair', 'Poor', 'Critical'
        self.coordinates = coordinates or {'lat': -1.2921, 'lng': 36.8219}  # Default Nairobi area
        self.created_at = created_at or datetime.utcnow().isoformat()

    def update_condition(self, new_condition):
        """Updates the asset's aggregate structural condition score."""
        self.current_condition = new_condition

    def to_dict(self):
        return {
            'asset_id': self.asset_id,
            'asset_type': self.asset_type,
            'location': self.location,
            'description': self.description,
            'current_condition': self.current_condition,
            'coordinates': self.coordinates,
            'created_at': self.created_at
        }

    @classmethod
    def from_dict(cls, data):
        if not data:
            return None
        return cls(
            asset_id=data.get('_id') or data.get('asset_id'),
            asset_type=data.get('asset_type', 'Road / Pavement'),
            location=data.get('location', ''),
            description=data.get('description', ''),
            current_condition=data.get('current_condition', 'Good'),
            coordinates=data.get('coordinates'),
            created_at=data.get('created_at')
        )
