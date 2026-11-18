"""
Unit tests for Four-Phase Inspection Progress calculations and map contract.
"""
import unittest
from backend.app.routes.reviews import calculate_inspection_progress, get_default_notebook_template


class TestInspectionProgress(unittest.TestCase):

    def test_empty_checklist_returns_phase_1(self):
        prog = calculate_inspection_progress([])
        self.assertEqual(prog['phases_completed'], 0)
        self.assertEqual(prog['current_phase'], 1)
        self.assertEqual(prog['total_phases'], 4)
        self.assertEqual(prog['completed_items'], 0)
        self.assertEqual(prog['summary'], '0/10 checks completed')
        self.assertEqual(prog['percent'], 0)
        self.assertEqual(prog['quarters'], 0)

    def test_road_template_progression(self):
        tmpl = get_default_notebook_template('Road / Pavement')
        checklist = tmpl['checklist']
        self.assertEqual(len(checklist), 10)

        # Baseline: 0 items done
        p0 = calculate_inspection_progress(checklist)
        self.assertEqual(p0['phases_completed'], 0)
        self.assertEqual(p0['current_phase'], 1)
        self.assertEqual(p0['quarters'], 0)

        # Complete Phase 1 items (indices 0, 1, 2)
        checklist[0]['completed'] = True
        checklist[1]['completed'] = True
        checklist[2]['completed'] = True
        p1 = calculate_inspection_progress(checklist)
        self.assertEqual(p1['phases_completed'], 1)
        self.assertEqual(p1['current_phase'], 2)
        self.assertEqual(p1['completed_items'], 3)
        self.assertEqual(p1['quarters'], 1)
        self.assertEqual(p1['current_phase_name'], 'Condition Evaluation')

        # Complete Phase 2 items (indices 3, 4 - one completed, one marked N/A)
        checklist[3]['completed'] = True
        checklist[4]['is_na'] = True
        checklist[4]['status'] = 'na'
        checklist[4]['na_reason'] = 'No surface ponding observed'
        p2 = calculate_inspection_progress(checklist)
        self.assertEqual(p2['phases_completed'], 2)
        self.assertEqual(p2['current_phase'], 3)
        self.assertEqual(p2['completed_items'], 5)
        self.assertEqual(p2['quarters'], 2)
        self.assertEqual(p2['current_phase_name'], 'Safety & Priority')

        # Complete Phase 3 items (indices 5, 6)
        checklist[5]['completed'] = True
        checklist[6]['completed'] = True
        p3 = calculate_inspection_progress(checklist)
        self.assertEqual(p3['phases_completed'], 3)
        self.assertEqual(p3['current_phase'], 4)
        self.assertEqual(p3['completed_items'], 7)
        self.assertEqual(p3['quarters'], 3)
        self.assertEqual(p3['current_phase_name'], 'Remedial Sign-off')

        # Complete Phase 4 items (indices 7, 8, 9)
        checklist[7]['completed'] = True
        checklist[8]['completed'] = True
        checklist[9]['completed'] = True
        p4 = calculate_inspection_progress(checklist)
        self.assertEqual(p4['phases_completed'], 4)
        self.assertEqual(p4['current_phase'], 4)
        self.assertEqual(p4['completed_items'], 10)
        self.assertEqual(p4['quarters'], 4)
        self.assertEqual(p4['percent'], 100)
        self.assertEqual(p4['summary'], '10/10 checks completed')

    def test_building_template_progression(self):
        tmpl = get_default_notebook_template('Building / Structural')
        checklist = tmpl['checklist']
        self.assertEqual(len(checklist), 10)
        self.assertEqual(checklist[0]['text'], "Confirm reported structural / building defect type")

        # Mark 4 items completed
        for i in range(4):
            checklist[i]['completed'] = True

        p = calculate_inspection_progress(checklist, 'Building / Structural')
        self.assertEqual(p['phases_completed'], 1)  # Only Phase 1 fully done, Phase 2 partially done
        self.assertEqual(p['current_phase'], 2)
        self.assertEqual(p['completed_items'], 4)
        self.assertEqual(p['quarters'], 1)
        self.assertEqual(p['summary'], '4/10 checks completed')


if __name__ == '__main__':
    unittest.main()
