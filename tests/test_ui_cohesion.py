"""
Automated Integration & Contract Tests for UI Cleanup and Experience-Cohesion Pass.
Validates:
1. Critical Reports Calendar visual contrast and month styling:
   - Active month is white (#ffffff) with high-contrast text and subtle border.
   - Inactive/background months are faded (opacity ~0.55).
   - Duplicate lower recurrence insights card strip is eliminated.
2. Monitoring Intelligence compact workspace:
   - Cohesive compact workspace with target max-height <= 520px.
   - Default clean empty state without auto-loaded cards before query.
   - 5 compact suggestion chips.
   - Progressive disclosure for evidence & comparison breakdown.
   - Max 2 primary action buttons.
3. Defect Review Stage-Aware Lifecycle & Inspection Drawer:
   - Clean location name without raw coordinates in primary review view.
   - Strict stage-aware UI (Received -> Under Review -> Verified -> Resolved).
   - Validation form is hidden when professional validation already exists.
   - Verified assessment summary displays confirmed/overridden details.
   - Inspection Notebook checklist, compliance prompts, and note cards reside in slide-over drawer.
   - Compact progress pill displays and synchronizes completion count.
"""

import unittest
import re
from backend.app import create_app
from backend.app.services.database import db_service


class TestUICohesionPass(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.client = cls.app.test_client()

        with open('frontend/css/main.css', 'r', encoding='utf-8') as f:
            cls.css_content = f.read()

        with open('frontend/index.html', 'r', encoding='utf-8') as f:
            cls.html_content = f.read()

        with open('frontend/js/dashboard.js', 'r', encoding='utf-8') as f:
            cls.dashboard_js = f.read()

        with open('frontend/js/review.js', 'r', encoding='utf-8') as f:
            cls.review_js = f.read()

    def test_01_calendar_styling_and_contrast(self):
        """Calendar active month card must be white (#ffffff) and duplicate card strip eliminated."""
        # 1. Verify active month card styling in CSS
        self.assertIn('.cal-month-card.is-active', self.css_content)
        self.assertIn('background: #ffffff', self.css_content)
        self.assertIn('border-color: #0070d1', self.css_content)

        # 2. Verify faded background months
        self.assertIn('.cal-month-card.is-prev', self.css_content)
        self.assertIn('opacity: 0.55', self.css_content)

        # 3. Verify intensity 0 cell high contrast
        self.assertIn('.cal-intensity-0', self.css_content)
        self.assertIn('color: #334155', self.css_content)

        # 4. Verify duplicate lower recurrence card strip eliminated
        self.assertIn('id="dashboardRecurrenceInsights"', self.html_content)
        self.assertIn('style="display: none;"', self.html_content)
        # Verify dashboard.js clears container
        self.assertIn("container.innerHTML = '';", self.dashboard_js)

    def test_02_monitoring_intelligence_compact_workspace(self):
        """Monitoring Intelligence must be a compact workspace <= 520px with progressive disclosure."""
        # 1. Verify workspace height in CSS
        self.assertIn('.monitoring-intelligence-workspace', self.css_content)
        self.assertIn('max-height: 520px', self.css_content)

        # 2. Verify default state has clean prompt and no auto-loaded analysis
        self.assertIn('hasUserQueriedIntelligence: false', self.dashboard_js)
        self.assertIn('class="intel-empty-state"', self.html_content)

        # 3. Verify 5 compact suggestion chips
        suggestion_chips = re.findall(r'class="intel-chip-suggestion"', self.html_content)
        self.assertGreaterEqual(len(suggestion_chips), 5)

        # 4. Verify progressive disclosure button and collapsible container
        self.assertIn('btnToggleIntelEvidence', self.dashboard_js)
        self.assertIn('intelCollapsibleEvidence', self.dashboard_js)
        self.assertIn('View evidence &amp; breakdown', self.dashboard_js)
        self.assertIn('Hide evidence & breakdown', self.dashboard_js)

        # 5. Verify maximum 2 primary action buttons rendered
        self.assertIn('slice(0, 2)', self.dashboard_js)

    def test_03_defect_review_clean_location(self):
        """Primary review view must show clean location name without raw coordinate strings."""
        # reviewGps must not concatenate raw lat/lng numbers
        self.assertIn("locEl.textContent = locName;", self.review_js)
        self.assertNotIn("locEl.textContent = `${locName}${coordsStr}`", self.review_js)

    def test_04_defect_review_stage_aware_lifecycle(self):
        """Defect review must enforce stage-awareness and hide form if already validated."""
        # 1. Received state hides reviewForm
        self.assertIn("if (isReceived) {", self.review_js)
        self.assertIn("if (reviewForm) reviewForm.classList.add('hidden');", self.review_js)

        # 2. Existing validation hides reviewForm and shows verified summary
        self.assertIn("if (reviewForm) reviewForm.classList.add('hidden');", self.review_js)
        self.assertIn("verifiedSummary.classList.remove('hidden');", self.review_js)

        # 3. Verified summary card exists in HTML
        self.assertIn('id="verifiedAssessmentSummary"', self.html_content)
        self.assertIn('id="verifiedSummaryClass"', self.html_content)
        self.assertIn('id="verifiedSummarySeverity"', self.html_content)
        self.assertIn('id="verifiedSummaryReviewer"', self.html_content)
        self.assertIn('id="verifiedSummaryDecision"', self.html_content)

    def test_05_inspection_notebook_slide_over_drawer(self):
        """Inspection notebook must reside in a slide-over drawer accessible via summary pill."""
        # 1. Drawer overlay and container exist in HTML
        self.assertIn('id="inspectionNotebookDrawerOverlay"', self.html_content)
        self.assertIn('id="inspectionNotebookDrawer"', self.html_content)
        self.assertIn('id="btnCloseNotebookDrawer"', self.html_content)
        self.assertIn('id="btnSaveInspectionNotebook"', self.html_content)

        # 2. Compact summary pill exists in primary right column
        self.assertIn('id="notebookSummaryPill"', self.html_content)
        self.assertIn('id="btnOpenNotebookDrawer"', self.html_content)
        self.assertIn('id="notebookProgressCount"', self.html_content)

        # 3. Drawer open/close/escape handlers wired in review.js
        self.assertIn('btnOpenNotebookDrawer', self.review_js)
        self.assertIn('btnCloseNotebookDrawer', self.review_js)
        self.assertIn("drawerOverlay.style.display = 'flex'", self.review_js)
        self.assertIn("e.key === 'Escape'", self.review_js)

        # 4. Progress count synced to both drawer and summary pill
        self.assertIn('drawerProgress.textContent = countText', self.review_js)
        self.assertIn('pillProgress.textContent = countText', self.review_js)

        # 5. Drawer CSS animations exist
        self.assertIn('.notebook-drawer-overlay', self.css_content)
        self.assertIn('.notebook-drawer', self.css_content)
        self.assertIn('animation: drawerSlideIn', self.css_content)

    def test_06_public_landing_page_and_ebk_workflow_contract(self):
        """Public landing page, verified incident articles, Boxicons role cards, and EBK register UI must exist."""
        self.assertIn('id="view-landing"', self.html_content)
        self.assertIn('How InfraVision Works', self.html_content)
        self.assertIn('Why Early Reporting Matters', self.html_content)
        self.assertIn('id="landingRecentReportsGrid"', self.html_content)
        self.assertIn('https://citizen.digital/article/nca-names-developer-contractor-and-engineers-behind-collapsed-eastleigh-building-n392650', self.html_content)
        self.assertIn('https://www.kbc.co.ke/sakaja-says-collapsed-eastleigh-building-lacked-construction-approval/', self.html_content)
        self.assertIn('https://engineers.ebk.go.ke/', self.html_content)
        self.assertIn('Verify against EBK Register', self.html_content)
        self.assertIn("bx bx-group", self.html_content)
        self.assertIn("bx bx-hard-hat", self.html_content)
        self.assertIn("bx bx-buildings", self.html_content)
        self.assertIn('Physical Engineering Assessment', self.html_content)
        self.assertIn('value="in"', self.html_content)


if __name__ == '__main__':
    unittest.main()

