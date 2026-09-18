class SeverityService:
    """
    Implements FR-04: Relative Severity Assessment Module.
    Calculates defect extent relative to image dimensions and categorizes into
    Low, Medium, or Critical priority tiers.
    """
    @staticmethod
    def calculate_box_area_ratio(box):
        """
        Calculates relative area occupied by a normalized bounding box [ymin, xmin, ymax, xmax].
        All coordinates are within range [0.0, 1.0].
        """
        if not box or len(box) < 4:
            return 0.0
        ymin, xmin, ymax, xmax = box
        height = max(0.0, min(1.0, ymax) - max(0.0, ymin))
        width = max(0.0, min(1.0, xmax) - max(0.0, xmin))
        return round(height * width, 4)

    @classmethod
    def assess_severity(cls, detections, low_thresh=0.05, critical_thresh=0.15):
        """
        Determines aggregate relative severity from detected defect bounding boxes.
        - Area < 5%  -> Low
        - 5% to 15% -> Medium
        - Area >= 15% -> Critical
        """
        if not detections:
            return {
                'relative_severity': 'Low',
                'area_ratio': 0.0,
                'area_percentage': 0.0,
                'action_index': 'No actionable defect detected.',
                'sla_hours': 168  # 7 days
            }

        # Calculate maximum single defect area and cumulative defect area
        total_area = sum(d.get('area_ratio', 0.0) for d in detections)
        max_single_area = max(d.get('area_ratio', 0.0) for d in detections)
        effective_area = max(max_single_area, total_area * 0.85)

        # Defect class sensitivity weighting (e.g., severe potholes present immediate vehicular danger)
        has_pothole = any(d.get('defect_class') == 'Pothole' for d in detections)
        if has_pothole and effective_area >= 0.10:
            severity = 'Critical'
        elif effective_area >= critical_thresh:
            severity = 'Critical'
        elif effective_area >= low_thresh:
            severity = 'Medium'
        else:
            severity = 'Low'

        # SLA Turnaround mapping matching Figure 4.7 and 4.8 wireframes
        if severity == 'Critical':
            action_index = 'Action Index Matrix: CRITICAL - Requires emergency patch crew triage turnaround within 24h.'
            sla_hours = 24
        elif severity == 'Medium':
            action_index = 'Action Index Matrix: MEDIUM - Scheduled maintenance repair within 7 days.'
            sla_hours = 168
        else:
            action_index = 'Action Index Matrix: LOW - Surface distress noted. Include in quarterly cyclic monitoring.'
            sla_hours = 720

        return {
            'relative_severity': severity,
            'area_ratio': round(effective_area, 4),
            'area_percentage': round(effective_area * 100, 2),
            'action_index': action_index,
            'sla_hours': sla_hours
        }
