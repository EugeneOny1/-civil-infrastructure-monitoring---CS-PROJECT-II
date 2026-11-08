/**
 * Review Module - AI Defect Assessment & Professional Engineer Review Terminal (Figure 4.8)
 *
 * Responsibilities:
 * - Detailed professional casework review of individual infrastructure defect reports.
 * - Real-time case searching and filtering across ID, location, defect, status, severity, and asset type.
 * - Deep-linked casework loading from Monitoring Dashboard ("Review & Sign Off").
 * - Clean empty states (eliminates fake #REP-0000 placeholders).
 * - Multi-detection bounding box rendering with label collision prevention.
 * - Canonical lifecycle management: Received -> Under Review -> Verified -> Resolved.
 * - Professional Engineer sign-off (Confirm AI Assessment vs Override Assessment with mandatory review notes).
 */

const Review = {
    currentReport: null,
    currentAssessment: null,
    caseworkReports: [],
    targetReportId: null,
    activeImageIndex: 0,
    activeReportData: null,

    init() {
        this.bindEvents();
    },

    bindEvents() {
        const signOffBtn = document.getElementById('btnSubmitSignOff');
        if (signOffBtn) {
            signOffBtn.addEventListener('click', () => this.submitProfessionalValidation());
        }

        const decisionRadios = document.querySelectorAll('input[name="reviewDecision"]');
        decisionRadios.forEach(radio => {
            radio.addEventListener('change', (e) => {
                const overrideFields = document.getElementById('overrideFields');
                if (e.target.value === 'Overridden') {
                    if (overrideFields) overrideFields.classList.remove('hidden');
                } else {
                    if (overrideFields) overrideFields.classList.add('hidden');
                }
            });
        });

        const nextActionSelect = document.getElementById('reviewNextAction');
        const followUpGroup = document.getElementById('followUpDateGroup');
        if (nextActionSelect) {
            nextActionSelect.addEventListener('change', (e) => {
                if (followUpGroup) {
                    followUpGroup.classList.toggle('hidden', e.target.value !== 'On-site inspection recommended');
                }
            });
        }

        const reportSelect = document.getElementById('reviewReportSelect');
        if (reportSelect) {
            reportSelect.addEventListener('change', (e) => {
                if (e.target.value) {
                    this.loadReportForReview(e.target.value);
                } else {
                    this.renderEmptyCaseworkState();
                }
            });
        }

        const searchInput = document.getElementById('reviewSearchInput');
        const filterStatus = document.getElementById('reviewFilterStatus');

        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.filterCasework(e.target.value, filterStatus ? filterStatus.value : '');
            });
        }

        if (filterStatus) {
            filterStatus.addEventListener('change', (e) => {
                this.filterCasework(searchInput ? searchInput.value : '', e.target.value);
            });
        }

        const refreshCaseworkBtn = document.getElementById('btnRefreshCasework');
        if (refreshCaseworkBtn) {
            refreshCaseworkBtn.addEventListener('click', () => {
                this.loadCaseworkList();
                window.App.showToast("Refreshed defect casework queue.");
            });
        }

        // Contextual Stage & Lifecycle Controls (Canonical: Received -> Verified -> Under Review -> Resolved)
        const btnStartInspection = document.getElementById('btnStartInspection');
        if (btnStartInspection) {
            btnStartInspection.addEventListener('click', async () => {
                if (!this.currentReport) return;
                const reportId = this.currentReport.report_id || this.currentReport._id;
                try {
                    btnStartInspection.disabled = true;
                    btnStartInspection.innerHTML = "<i class='bx bx-loader-alt bx-spin'></i> Starting...";
                    await window.Api.updateReportStatus(reportId, 'Under Review', 'Detailed inspection and engineering review initiated.');
                    window.App?.showToast("Inspection initiated. Inspection Notebook is now active.");
                    await this.loadReportForReview(reportId);
                    openDrawer();
                } catch (err) {
                    window.App?.showToast(err.message || "Failed to start inspection.", true);
                } finally {
                    btnStartInspection.disabled = false;
                    btnStartInspection.innerHTML = "<i class='bx bx-play-circle'></i> Start Inspection / Review";
                }
            });
        }

        const btnReviewOpenNotebook = document.getElementById('btnReviewOpenNotebook');
        if (btnReviewOpenNotebook) {
            btnReviewOpenNotebook.addEventListener('click', () => openDrawer());
        }

        const btnUnderReview = document.getElementById('btnMoveUnderReview');
        const btnVerified = document.getElementById('btnMarkVerified');
        const btnResolved = document.getElementById('btnMarkResolved');

        if (btnUnderReview) {
            btnUnderReview.addEventListener('click', () => this.handleLifecycleTransition('Under Review', 'Inspection initiated by certified engineer.'));
        }
        if (btnVerified) {
            btnVerified.addEventListener('click', () => this.handleLifecycleTransition('Verified', 'Engineering defect verification and severity confirmation completed.'));
        }
        if (btnResolved) {
            btnResolved.addEventListener('click', () => this.handleResolutionWorkflow(openDrawer));
        }

        // Section 24: Direct "Show on Map" button in Defect Review
        const btnShowOnMap = document.getElementById('btnReviewShowOnMap');
        if (btnShowOnMap) {
            btnShowOnMap.addEventListener('click', () => {
                if (!this.currentReport) {
                    window.App?.showToast("Please select a report first.", true);
                    return;
                }
                const lat = this.currentReport.latitude || this.currentReport.metadata?.latitude;
                const lng = this.currentReport.longitude || this.currentReport.metadata?.longitude;
                if (!lat || !lng) {
                    window.App?.showToast("No geographic coordinates recorded for this defect report.", true);
                    return;
                }
                const reportId = this.currentReport.report_id || this.currentReport._id;
                window.App?.navigateTo('view-map');
                window.DefectMap?.showReportOnMap(reportId, lat, lng);
            });
        }

        // Sections 30-33 & 43: Inspection Notebook Drawer & Objective Handlers
        const btnOpenDrawer = document.getElementById('btnOpenNotebookDrawer');
        const btnCloseDrawer = document.getElementById('btnCloseNotebookDrawer');
        const drawerOverlay = document.getElementById('inspectionNotebookDrawerOverlay');
        const drawerBackdrop = document.getElementById('notebookDrawerBackdrop');

        const openDrawer = () => {
            if (drawerOverlay) {
                drawerOverlay.classList.remove('hidden');
                drawerOverlay.style.display = 'flex';
            }
        };

        const closeDrawer = () => {
            if (drawerOverlay) {
                drawerOverlay.classList.add('hidden');
                drawerOverlay.style.display = 'none';
            }
        };

        if (btnOpenDrawer) btnOpenDrawer.addEventListener('click', openDrawer);
        if (btnCloseDrawer) btnCloseDrawer.addEventListener('click', closeDrawer);
        if (drawerBackdrop) drawerBackdrop.addEventListener('click', closeDrawer);

        window.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && drawerOverlay && !drawerOverlay.classList.contains('hidden') && drawerOverlay.style.display !== 'none') {
                closeDrawer();
            }
        });

        // Internal Drawer Tabs Switching
        const drawerTabBtns = document.querySelectorAll('.notebook-tab-btn');
        drawerTabBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const target = e.currentTarget.getAttribute('data-target');
                this.switchDrawerTab(target);
            });
        });

        const btnSaveNb = document.getElementById('btnSaveInspectionNotebook');
        if (btnSaveNb) {
            btnSaveNb.addEventListener('click', () => this.saveInspectionNotebook());
        }

        const btnAddCustom = document.getElementById('btnAddCustomObjective');
        if (btnAddCustom) {
            btnAddCustom.addEventListener('click', () => this.addCustomObjective());
        }

        const btnAddNote = document.getElementById('btnAddNoteCard');
        if (btnAddNote) {
            btnAddNote.addEventListener('click', () => this.addNoteCard());
        }

        // Mark Objective N/A Modal Events
        const modalMarkNa = document.getElementById('markObjectiveNaModal');
        const btnCloseMarkNa = document.getElementById('btnCloseMarkNa');
        const btnCancelMarkNa = document.getElementById('btnCancelMarkNa');
        const btnConfirmMarkNa = document.getElementById('btnConfirmMarkNa');
        const closeMarkNa = () => { if (modalMarkNa) modalMarkNa.classList.remove('active'); };

        if (btnCloseMarkNa) btnCloseMarkNa.addEventListener('click', closeMarkNa);
        if (btnCancelMarkNa) btnCancelMarkNa.addEventListener('click', closeMarkNa);
        if (btnConfirmMarkNa) {
            btnConfirmMarkNa.addEventListener('click', () => {
                const idx = this._pendingNaIndex;
                if (idx === undefined || idx === null) return;
                const reason = document.getElementById('markNaReasonInput')?.value.trim() || '';
                if (!reason) {
                    window.App?.showToast("Documented justification is mandatory to mark an objective N/A.", true);
                    return;
                }
                const user = window.Auth?.getUser() || window.App?.currentUser;
                const authorName = user?.name || 'Reviewing Engineer';
                const it = this.currentNotebook.checklist[idx];
                if (it) {
                    it.is_na = true;
                    it.status = 'not_applicable';
                    it.na_reason = reason;
                    it.na_by = authorName;
                    it.na_at = new Date().toISOString();
                    it.completed = false;
                    it.checked = false;
                }
                closeMarkNa();
                this.renderChecklistItems();
                window.App?.showToast("Objective marked N/A with documented justification.");
            });
        }

        // Transfer Lead Modal Events
        const modalTransfer = document.getElementById('transferLeadModal');
        const btnOpenTransfer = document.getElementById('btnOpenTransferLeadModal');
        const btnCloseTransfer = document.getElementById('btnCloseTransferLead');
        const btnCancelTransfer = document.getElementById('btnCancelTransferLead');
        const btnConfirmTransfer = document.getElementById('btnConfirmTransferLead');
        const closeTransfer = () => { if (modalTransfer) modalTransfer.classList.remove('active'); };

        if (btnOpenTransfer) {
            btnOpenTransfer.addEventListener('click', () => {
                if (!this.currentReport) return;
                const refEl = document.getElementById('transferLeadReportRef');
                const repId = this.currentReport.report_id || this.currentReport._id;
                if (refEl) refEl.textContent = `#REP-${repId.slice(-6).toUpperCase()}`;
                if (modalTransfer) modalTransfer.classList.add('active');
            });
        }
        if (btnCloseTransfer) btnCloseTransfer.addEventListener('click', closeTransfer);
        if (btnCancelTransfer) btnCancelTransfer.addEventListener('click', closeTransfer);
        if (btnConfirmTransfer) {
            btnConfirmTransfer.addEventListener('click', async () => {
                if (!this.currentReport) return;
                const reportId = this.currentReport.report_id || this.currentReport._id;
                const newLeadId = document.getElementById('transferLeadSelect')?.value;
                const reason = document.getElementById('transferLeadReason')?.value.trim() || '';

                if (!newLeadId) {
                    window.App?.showToast("Please select the new Lead Engineer.", true);
                    return;
                }
                if (!reason) {
                    window.App?.showToast("Mandatory transfer reason is required.", true);
                    return;
                }

                try {
                    btnConfirmTransfer.disabled = true;
                    btnConfirmTransfer.textContent = "Transferring...";
                    await window.Api.transferLeadEngineer(reportId, newLeadId, reason);
                    window.App?.showToast("Lead Engineer accountability transferred successfully.");
                    closeTransfer();
                    await this.loadReportForReview(reportId);
                    this.loadDrawerTeam();
                } catch (err) {
                    window.App?.showToast(err.message || "Failed to transfer Lead Engineer.", true);
                } finally {
                    btnConfirmTransfer.disabled = false;
                    btnConfirmTransfer.textContent = "Confirm Transfer";
                }
            });
        }

        // Invite Collaborator
        const btnInvite = document.getElementById('btnSendEngineerInvite');
        if (btnInvite) {
            btnInvite.addEventListener('click', async () => {
                if (!this.currentReport) return;
                const reportId = this.currentReport.report_id || this.currentReport._id;
                const engineerId = document.getElementById('inviteEngineerSelect')?.value;
                const role = document.getElementById('inviteEngineerRole')?.value.trim() || 'Collaborating Engineer';

                if (!engineerId) {
                    window.App?.showToast("Please select an accredited engineer to invite.", true);
                    return;
                }

                try {
                    btnInvite.disabled = true;
                    btnInvite.textContent = "Inviting...";
                    await window.Api.addCollaborator(reportId, engineerId, role);
                    window.App?.showToast("Engineer invited to inspection team.");
                    const fresh = await window.Api.getReportById(reportId);
                    this.currentReport = fresh.report;
                    this.loadDrawerTeam();
                    const roleInp = document.getElementById('inviteEngineerRole');
                    if (roleInp) roleInp.value = '';
                } catch (err) {
                    window.App?.showToast(err.message || "Failed to invite collaborator.", true);
                } finally {
                    btnInvite.disabled = false;
                    btnInvite.textContent = "Invite";
                }
            });
        }

        // Engineer Report-Linked Safety Advisory (Section S)
        const btnAdvisory = document.getElementById('btnOpenSafetyAdvisory');
        const modalAdvisory = document.getElementById('safetyAdvisoryModal');
        const btnCloseAdvisory = document.getElementById('btnCloseSafetyAdvisory');
        const btnCancelAdvisory = document.getElementById('btnCancelSafetyAdvisory');
        const btnConfirmAdvisory = document.getElementById('btnConfirmSafetyAdvisory');

        const closeAdvisory = () => {
            if (modalAdvisory) modalAdvisory.classList.remove('active');
        };

        if (btnAdvisory) {
            btnAdvisory.addEventListener('click', () => {
                if (!this.currentReport) {
                    window.App?.showToast("Please select a report first to issue a safety advisory.", true);
                    return;
                }
                const locEl = document.getElementById('advisoryLocationName');
                if (locEl) {
                    locEl.textContent = this.currentReport.location_name || this.currentReport.metadata?.location_name || 'Corridor Asset';
                }
                if (modalAdvisory) modalAdvisory.classList.add('active');
            });
        }

        if (btnCloseAdvisory) btnCloseAdvisory.addEventListener('click', closeAdvisory);
        if (btnCancelAdvisory) btnCancelAdvisory.addEventListener('click', closeAdvisory);

        if (btnConfirmAdvisory) {
            btnConfirmAdvisory.addEventListener('click', async () => {
                if (!this.currentReport) return;
                const reportId = this.currentReport.report_id || this.currentReport._id;
                const category = document.getElementById('advisoryCategorySelect')?.value || 'Exercise caution';
                const note = document.getElementById('advisoryNoteText')?.value.trim() || '';

                try {
                    btnConfirmAdvisory.disabled = true;
                    btnConfirmAdvisory.textContent = 'Publishing...';
                    await window.Api.issueSafetyAdvisory(reportId, category, note);
                    window.App?.showToast(`Safety Advisory (${category}) published successfully!`);
                    closeAdvisory();
                    if (document.getElementById('advisoryNoteText')) {
                        document.getElementById('advisoryNoteText').value = '';
                    }
                } catch (err) {
                    window.App?.showToast(err.message || 'Failed to publish advisory.', true);
                } finally {
                    btnConfirmAdvisory.disabled = false;
                    btnConfirmAdvisory.textContent = 'Publish Advisory';
                }
            });
        }
    },

    async loadCaseworkList(preselectReportId = null) {
        const reportSelect = document.getElementById('reviewReportSelect');
        if (!reportSelect) return;

        try {
            reportSelect.innerHTML = `<option value="">Loading defect casework...</option>`;
            const data = await window.Api.getReports({ limit: 100 });
            this.caseworkReports = data.reports || [];

            if (this.caseworkReports.length === 0) {
                reportSelect.innerHTML = `<option value="">No defect casework available</option>`;
                this.renderEmptyCaseworkState("No infrastructure reports exist yet in the database.");
                return;
            }

            // Populate select dropdown with real report context
            this.populateReportSelectOptions(this.caseworkReports);

            // Determine which report to load
            let targetId = preselectReportId;
            if (!targetId || !this.caseworkReports.some(r => (r.report_id || r._id) === targetId)) {
                targetId = this.caseworkReports[0].report_id || this.caseworkReports[0]._id;
            }

            reportSelect.value = targetId;
            await this.loadReportForReview(targetId);

        } catch (err) {
            console.error("[Review] Failed loading casework list:", err);
            reportSelect.innerHTML = `<option value="">Failed to load casework queue</option>`;
            this.renderEmptyCaseworkState("Failed to connect to casework repository.");
        }
    },

    populateReportSelectOptions(reportsList) {
        const reportSelect = document.getElementById('reviewReportSelect');
        if (!reportSelect) return;

        if (reportsList.length === 0) {
            reportSelect.innerHTML = `<option value="">No matching defect casework found</option>`;
            return;
        }

        reportSelect.innerHTML = reportsList.map(rep => {
            const ai = rep.assessment || {};
            const defect = ai.defect_class || rep.metadata?.defect_class || 'Distress';
            const status = rep.status || 'Received';
            const loc = rep.asset?.location || rep.metadata?.location_name || 'Corridor';
            const repId = rep.report_id || rep._id;
            const displayId = rep.display_id || (repId.length > 18 ? repId.slice(0, 16) + '...' : repId);
            const formattedId = displayId.startsWith('#') ? displayId : '#' + displayId;
            const sev = (ai.relative_severity || rep.metadata?.relative_severity || 'Low').toUpperCase();

            return `<option value="${repId}">${formattedId} — ${defect} (${status} • ${sev}) • ${loc}</option>`;
        }).join('');
    },

    filterCasework(query = '', statusFilter = '') {
        const q = query.toLowerCase().trim();
        const sf = statusFilter.toLowerCase().trim();

        const filtered = this.caseworkReports.filter(rep => {
            const ai = rep.assessment || {};
            const repId = (rep.report_id || rep._id || '').toLowerCase();
            const loc = (rep.asset?.location || rep.metadata?.location_name || '').toLowerCase();
            const defect = (ai.defect_class || rep.metadata?.defect_class || '').toLowerCase();
            const status = (rep.status || '').toLowerCase();
            const sev = (ai.relative_severity || rep.metadata?.relative_severity || '').toLowerCase();
            const assetType = (rep.asset?.asset_type || rep.metadata?.asset_type || '').toLowerCase();

            const matchesQuery = !q || (
                repId.includes(q) ||
                loc.includes(q) ||
                defect.includes(q) ||
                status.includes(q) ||
                sev.includes(q) ||
                assetType.includes(q)
            );

            let matchesStatus = true;
            if (sf) {
                const currentUserId = String(window.App?.currentUser?.id || window.App?.currentUser?.user_id || window.App?.currentUser?._id || '');
                const assignedId = String(rep.assigned_engineer_id || rep.metadata?.assigned_engineer_id || rep.metadata?.reviewer_id || '');
                if (sf === 'awaiting_review') {
                    matchesStatus = (status === 'received');
                } else if (sf === 'my_reviews') {
                    matchesStatus = (status === 'under review') && (assignedId && assignedId === currentUserId);
                } else if (sf === 'my_verified') {
                    matchesStatus = (status === 'verified') && (assignedId && assignedId === currentUserId);
                } else if (sf === 'resolved') {
                    matchesStatus = (status === 'resolved');
                } else {
                    matchesStatus = (status === sf);
                }
            }

            return matchesQuery && matchesStatus;
        });

        this.populateReportSelectOptions(filtered);

        const reportSelect = document.getElementById('reviewReportSelect');
        if (filtered.length > 0) {
            const nextId = filtered[0].report_id || filtered[0]._id;
            if (reportSelect) reportSelect.value = nextId;
            this.loadReportForReview(nextId);
        } else {
            this.renderEmptyCaseworkState("No reports match the search filter criteria.");
        }
    },

    renderEmptyCaseworkState(message = "Select a defect report from the casework list above to begin inspection.") {
        this.currentReport = null;
        this.currentAssessment = null;

        const frameEl = document.getElementById('reviewFrameId');
        const locEl = document.getElementById('reviewGps');
        const statusEl = document.getElementById('reviewHeaderStatus');
        const badgeDot = document.getElementById('reviewBadgeDot');
        const citizenNotesEl = document.getElementById('reviewCitizenNotes');
        const predClassEl = document.getElementById('reviewPredictedClass');
        const calcSevEl = document.getElementById('reviewCalculatedSeverity');
        const confEl = document.getElementById('telemConfidence');
        const sevEl = document.getElementById('telemSeverity');
        const areaEl = document.getElementById('telemArea');

        if (frameEl) frameEl.textContent = 'No Case Selected';
        if (locEl) locEl.textContent = '—';
        if (statusEl) statusEl.textContent = 'Status: Awaiting Case Selection';
        if (badgeDot) badgeDot.className = 'badge-dot';
        if (citizenNotesEl) citizenNotesEl.textContent = message;
        if (predClassEl) predClassEl.textContent = '—';
        if (calcSevEl) calcSevEl.textContent = '[ NO CASE LOADED ]';
        if (confEl) confEl.textContent = '—';
        if (sevEl) sevEl.textContent = '—';
        if (areaEl) areaEl.textContent = '—';

        const gallery = document.getElementById('reviewImageGallery');
        if (gallery) {
            gallery.classList.add('hidden');
            gallery.style.display = 'none';
        }
        const combinedBlock = document.getElementById('reviewCombinedMultiViewBlock');
        if (combinedBlock) combinedBlock.classList.add('hidden');

        const thumbList = document.getElementById('reviewThumbnailList');
        if (thumbList) thumbList.innerHTML = '';
        this.activeReportData = null;
        this.activeImageIndex = 0;

        // Draw clear empty placeholder on canvas
        const canvas = document.getElementById('reviewCanvas');
        if (canvas) {
            canvas.width = 640;
            canvas.height = 420;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#0f172a';
            ctx.fillRect(0, 0, 640, 420);
            ctx.fillStyle = '#94a3b8';
            ctx.font = '14px "Montserrat", sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(message, 320, 210);
        }
    },

    async loadReportForReview(reportId) {
        if (!reportId) {
            this.renderEmptyCaseworkState();
            return;
        }

        try {
            const data = await window.Api.getReportById(reportId);
            this.currentReport = data.report;
            this.currentAssessment = data.assessment;

            // Sync select dropdown if not already matched
            const reportSelect = document.getElementById('reviewReportSelect');
            if (reportSelect && reportSelect.value !== reportId) {
                reportSelect.value = reportId;
            }

            // Sync URL with clean bookmarkable report_id query parameter
            const url = new URL(window.location);
            url.searchParams.set('report_id', reportId);
            window.history.replaceState({}, '', url);

            // Populate Case Meta Header: Infrastructure Asset and Lifecycle Status
            const repId = data.report.report_id || data.report._id;
            const displayId = data.report.display_id || (repId.startsWith('REP-') ? repId : '#' + repId);
            const frameEl = document.getElementById('reviewFrameId');
            if (frameEl) frameEl.textContent = displayId.startsWith('#') ? displayId : '#' + displayId;

            const assetType = data.asset?.asset_type || data.report.metadata?.asset_type || 'Road / Pavement';
            const assetTypeEl = document.getElementById('reviewAssetType');
            if (assetTypeEl) assetTypeEl.textContent = assetType;

            const status = data.report.status || 'Received';
            const statusSlug = status.toLowerCase().replace(/\s+/g, '-');
            const lifecycleEl = document.getElementById('reviewLifecycleStatus');
            if (lifecycleEl) {
                lifecycleEl.innerHTML = `<span class="status-chip ${statusSlug}">${status}</span>`;
            }

            // Assigned Engineer & Header Status (Sections 25 & 28)
            const assignedEng = data.report.assigned_engineer_name || data.report.metadata?.assigned_engineer_name || data.report.metadata?.reviewed_by || 'Unassigned';
            const assignedEl = document.getElementById('reviewAssignedEngineer');
            if (assignedEl) assignedEl.textContent = assignedEng;
            const topOwnerBadge = document.getElementById('reviewTopOwnerBadge');
            if (topOwnerBadge) topOwnerBadge.textContent = assignedEng;

            const topStatusBadge = document.getElementById('reviewTopStatusBadge');
            if (topStatusBadge) {
                topStatusBadge.textContent = status;
                topStatusBadge.className = `status-chip ${statusSlug}`;
            }

            // Contextual Lifecycle Action Card (Sections 25, 26, 27)
            const wfStageBadge = document.getElementById('reviewWorkflowStageBadge');
            if (wfStageBadge) {
                wfStageBadge.textContent = status;
                wfStageBadge.className = `status-chip ${statusSlug}`;
            }

            const stageReceived = document.getElementById('actionStageReceived');
            const stageUnderReview = document.getElementById('actionStageUnderReview');
            const stageVerified = document.getElementById('actionStageVerified');

            // Render inspection notebook & objectives (Sections 30-33 & 43)
            this.renderInspectionNotebook(data.report, assetType);

            // Clean Location: Display clean name without raw coordinates in primary view
            const locName = data.asset?.location || data.report.metadata?.location_name || 'Corridor Asset';
            const locEl = document.getElementById('reviewGps');
            if (locEl) locEl.textContent = locName;

            const drawerRef = document.getElementById('drawerReportReference');
            if (drawerRef) {
                drawerRef.textContent = `Report #${reportId.length > 8 ? reportId.slice(-8) : reportId} • ${locName}`;
            }

            const isResolved = (status === 'Resolved');
            const isUnderReview = (status === 'Under Review');
            const isVerified = (status === 'Verified');
            const isReceived = (status === 'Received');
            const hasReview = Boolean(data.review || (data.report.metadata?.engineer_assessment && data.report.metadata?.engineer_assessment?.decision));

            // Contextual Stage Visibility (Canonical: Received -> Verified -> Under Review -> Resolved)
            if (stageReceived) stageReceived.style.display = isReceived ? 'flex' : 'none';
            if (stageVerified) stageVerified.style.display = isVerified ? 'flex' : 'none';
            if (stageUnderReview) stageUnderReview.style.display = isUnderReview ? 'flex' : 'none';

            // Submitter & Authorship distinction
            const submitter = data.submitter || {};
            const submitterName = submitter.name || data.report.metadata?.submitted_by_name || 'Reporter';
            const submitterRole = (submitter.role || data.report.metadata?.submitted_by_role || 'citizen').toUpperCase();
            const submitterEl = document.getElementById('reviewSubmitter');
            if (submitterEl) {
                submitterEl.textContent = `${submitterName} (${submitterRole})`;
            }

            // Self-Review / Authorship Notice
            const currentUser = window.App?.currentUser;
            const currentUserId = currentUser ? String(currentUser.user_id || currentUser._id) : '';
            const reportUserId = String(data.report.user_id || data.report.metadata?.submitted_by_id || '');
            const isSelfSubmit = Boolean(currentUserId && reportUserId && currentUserId === reportUserId);
            const selfReviewBanner = document.getElementById('selfReviewBanner');
            if (selfReviewBanner) {
                selfReviewBanner.classList.toggle('hidden', !isSelfSubmit);
            }

            const citizenNotesEl = document.getElementById('reviewCitizenNotes');
            if (citizenNotesEl) {
                citizenNotesEl.textContent = data.report.description || data.report.metadata?.citizen_notes || 'No citizen field observations recorded.';
            }

            // Section 7: Enforce Read-Only Mode for Resolved Defect Reports
            const resolvedNotice = document.getElementById('reviewResolvedNotice');
            if (resolvedNotice) {
                resolvedNotice.classList.toggle('hidden', !isResolved);
                if (isResolved) {
                    const revName = data.review?.reviewer_name || data.report.metadata?.reviewed_by || 'Accredited Civil Engineer';
                    const revNameEl = document.getElementById('resolvedReviewerName');
                    if (revNameEl) revNameEl.textContent = revName;

                    const revDate = data.review?.review_date || data.report.metadata?.reviewed_at || data.report.date_submitted;
                    const dateEl = document.getElementById('resolvedDate');
                    if (dateEl) dateEl.textContent = revDate ? new Date(revDate).toLocaleDateString('en-KE', { dateStyle: 'medium' }) : 'Verified';

                    const finalClass = data.review?.override_details?.override_class || data.assessment?.defect_class || data.report.metadata?.defect_class || 'Confirmed Class';
                    const classEl = document.getElementById('resolvedFinalClass');
                    if (classEl) classEl.textContent = finalClass;

                    const finalSev = data.review?.override_details?.override_severity || data.assessment?.relative_severity || data.report.metadata?.relative_severity || 'Confirmed Severity';
                    const sevEl = document.getElementById('resolvedFinalSeverity');
                    if (sevEl) sevEl.textContent = finalSev;
                }
            }

            // Stage-aware Professional Review Form vs Verified Assessment Summary
            const reviewForm = document.getElementById('professionalReviewForm');
            const verifiedSummary = document.getElementById('verifiedAssessmentSummary');

            if (isReceived) {
                // In Received state, engineer evaluates automated detections and provides sign-off
                if (reviewForm) reviewForm.classList.remove('hidden');
                if (verifiedSummary) verifiedSummary.classList.add('hidden');
            } else {
                // In Verified, Under Review, or Resolved states, professional validation is confirmed
                if (reviewForm) reviewForm.classList.add('hidden');
                if (verifiedSummary) {
                    verifiedSummary.classList.remove('hidden');
                    const vClass = document.getElementById('verifiedSummaryClass');
                    const vSev = document.getElementById('verifiedSummarySeverity');
                    const vRev = document.getElementById('verifiedSummaryReviewer');
                    const vDec = document.getElementById('verifiedSummaryDecision');
                    const vAct = document.getElementById('verifiedSummaryNextAction');
                    const vNotes = document.getElementById('verifiedSummaryNotes');

                    const effClass = data.review?.override_details?.override_class || data.assessment?.defect_class || data.report.metadata?.defect_class || 'Pothole';
                    const effSev = data.review?.override_details?.override_severity || data.assessment?.relative_severity || data.report.metadata?.relative_severity || 'Critical';
                    const effRev = data.review?.reviewer_name || data.report.metadata?.assigned_engineer_name || data.report.metadata?.reviewed_by || 'Accredited Civil Engineer';
                    const effDec = data.review?.decision || (data.report.metadata?.engineer_assessment?.decision) || 'Confirmed';
                    const effAct = data.report.metadata?.next_action || (data.report.metadata?.engineer_assessment?.next_action) || 'Continue monitoring';
                    const effNotes = data.review?.comments || data.report.metadata?.engineer_notes || 'Defect verification confirmed.';

                    if (vClass) vClass.textContent = effClass;
                    if (vSev) vSev.textContent = effSev;
                    if (vRev) vRev.textContent = effRev;
                    if (vDec) {
                        vDec.textContent = effDec;
                        vDec.className = `status-chip ${effDec === 'Overridden' ? 'warning' : 'success'}`;
                    }
                    if (vAct) vAct.textContent = effAct;
                    if (vNotes) vNotes.textContent = effNotes;
                }
            }

            // Lock or unlock review controls based on resolution state
            const btnSignOff = document.getElementById('btnSubmitSignOff');
            const notesEl = document.getElementById('engineerNotes');
            const ocSelect = document.getElementById('overrideClassSelect');
            const osSelect = document.getElementById('overrideSeveritySelect');
            const bReview = document.getElementById('btnMoveUnderReview');
            const bVerify = document.getElementById('btnMarkVerified');
            const bResolve = document.getElementById('btnMarkResolved');

            if (isResolved) {
                if (btnSignOff) {
                    btnSignOff.disabled = true;
                    btnSignOff.style.opacity = '0.5';
                    btnSignOff.style.cursor = 'not-allowed';
                    btnSignOff.title = 'This defect report is resolved and read-only.';
                }
                if (notesEl) {
                    notesEl.value = data.review?.comments || data.report.metadata?.engineer_notes || 'Repairs completed and validated.';
                    notesEl.disabled = true;
                    notesEl.readOnly = true;
                }
                document.querySelectorAll('input[name="reviewDecision"]').forEach(r => r.disabled = true);
                if (ocSelect) ocSelect.disabled = true;
                if (osSelect) osSelect.disabled = true;
                if (bReview) bReview.disabled = true;
                if (bVerify) bVerify.disabled = true;
                if (bResolve) bResolve.disabled = true;
            } else {
                if (btnSignOff) {
                    btnSignOff.disabled = false;
                    btnSignOff.style.opacity = '1';
                    btnSignOff.style.cursor = 'pointer';
                    btnSignOff.title = 'Submit professional validation';
                }
                if (notesEl) {
                    notesEl.disabled = false;
                    notesEl.readOnly = false;
                }
                document.querySelectorAll('input[name="reviewDecision"]').forEach(r => r.disabled = false);
                if (ocSelect) ocSelect.disabled = false;
                if (osSelect) osSelect.disabled = false;
                if (bReview) bReview.disabled = false;
                if (bVerify) bVerify.disabled = false;
                if (bResolve) bResolve.disabled = false;
            }

            // Next Action & Follow-up Inspection controls
            const nextActionEl = document.getElementById('reviewNextAction');
            const followUpDateEl = document.getElementById('reviewFollowUpDate');
            const followUpGroup = document.getElementById('followUpDateGroup');
            const curNextAction = data.report.metadata?.next_action || (data.report.metadata?.engineer_assessment?.next_action) || 'Continue monitoring';
            const curFollowUpDate = data.report.metadata?.follow_up_date || (data.report.metadata?.engineer_assessment?.follow_up_date) || '';

            if (nextActionEl) {
                nextActionEl.value = curNextAction;
                nextActionEl.disabled = isResolved;
            }
            if (followUpDateEl) {
                followUpDateEl.value = curFollowUpDate;
                followUpDateEl.disabled = isResolved;
            }
            if (followUpGroup) {
                followUpGroup.classList.toggle('hidden', curNextAction !== 'On-site inspection recommended');
            }

            // Canonical Status & Validation Flags
            const isUnusual = data.report.metadata?.is_unusual === true || data.report.validation_status === 'unusual';
            const statusEl = document.getElementById('reviewHeaderStatus');
            const badgeDot = document.getElementById('reviewBadgeDot');

            if (isResolved) {
                if (statusEl) statusEl.textContent = `Status: Resolved (Case Closed)`;
                if (badgeDot) badgeDot.className = 'badge-dot success';
            } else if (data.review) {
                if (statusEl) statusEl.textContent = `Status: ${status} (Validated: ${data.review.decision})`;
                if (badgeDot) badgeDot.className = 'badge-dot success';
                if (notesEl && !notesEl.value) notesEl.value = data.review.comments || '';
            } else if (isUnusual) {
                if (statusEl) statusEl.textContent = `Status: ${status} — Unusual Pairing Flagged`;
                if (badgeDot) badgeDot.className = 'badge-dot warning';
                if (notesEl && !notesEl.value) notesEl.value = data.report.metadata?.advisory_notes || '';
            } else {
                if (statusEl) statusEl.textContent = `Status: ${status}`;
                if (badgeDot) badgeDot.className = `badge-dot ${status === 'Verified' ? 'success' : 'warning'}`;
                if (notesEl && !notesEl.value) notesEl.value = '';
            }

            // Multi-image angle switching & AI Telemetry rendering
            this.activeReportData = data;
            this.activeImageIndex = 0;
            this.renderImageGallery(data);

            // Render Combined Multi-View Assessment Block if present
            const combinedBlock = document.getElementById('reviewCombinedMultiViewBlock');
            const combinedData = data.combined_multi_view_assessment || data.report.metadata?.combined_multi_view_assessment;
            if (combinedBlock) {
                if (combinedData && combinedData.detected_classes && combinedData.detected_classes.length > 0) {
                    combinedBlock.classList.remove('hidden');
                    const sevPill = document.getElementById('reviewCombinedSeverityPill');
                    const sev = (combinedData.highest_visual_severity || 'Low').toUpperCase();
                    if (sevPill) {
                        sevPill.textContent = sev;
                        sevPill.className = `severity-pill ${sev.toLowerCase()}`;
                    }
                    const rowsEl = document.getElementById('reviewCombinedClassRows');
                    if (rowsEl) {
                        rowsEl.innerHTML = combinedData.detected_classes.map(cls => {
                            const support = combinedData.per_class_view_support?.[cls] || '1/1';
                            const conf = combinedData.strongest_model_confidence?.[cls]
                                ? `${Math.round(combinedData.strongest_model_confidence[cls] * 100)}%`
                                : '—';
                            return `
                                <div style="display:flex; justify-content:space-between; align-items:center; background:#1e293b; padding:0.35rem 0.6rem; border-radius:4px;">
                                    <span style="font-weight:600; color:#f8fafc;">${cls}</span>
                                    <div style="display:flex; gap:0.6rem; font-size:0.75rem;">
                                        <span style="color:#94a3b8;">Support: <strong style="color:#38bdf8;">${support}</strong></span>
                                        <span style="color:#94a3b8;">Max Conf: <strong style="color:#10b981;">${conf}</strong></span>
                                    </div>
                                </div>
                            `;
                        }).join('');
                    }
                } else {
                    combinedBlock.classList.add('hidden');
                }
            }

        } catch (e) {
            console.error("[Review] Load report review error:", e);
            window.App.showToast("Failed to load defect report for review.", true);
            this.renderEmptyCaseworkState("Could not retrieve defect report.");
        }
    },

    renderImageGallery(data) {
        const galleryContainer = document.getElementById('reviewImageGallery');
        const thumbList = document.getElementById('reviewThumbnailList');
        const carouselNav = document.getElementById('reviewCarouselNav');
        const carouselOverlay = document.getElementById('reviewCarouselOverlay');
        const dotsContainer = document.getElementById('reviewPaginationDots');
        const counterEl = document.getElementById('reviewGalleryCounter');
        const titleEl = document.getElementById('reviewGalleryTitle');

        const images = (data.images && data.images.length > 0) ? data.images : (data.image ? [data.image] : []);

        if (images.length <= 1) {
            if (galleryContainer) {
                galleryContainer.classList.add('hidden');
                galleryContainer.style.display = 'none';
            }
            if (carouselNav) {
                carouselNav.classList.add('hidden');
                carouselNav.style.display = 'none';
            }
            if (carouselOverlay) {
                carouselOverlay.classList.add('hidden');
                carouselOverlay.style.display = 'none';
            }
            if (thumbList) thumbList.innerHTML = '';
            if (dotsContainer) dotsContainer.innerHTML = '';
            const img = images[0] || {};
            const ass = (data.assessments && data.assessments[0]) || data.assessment || {};
            this.updateTelemetryAndCanvas(img.url, ass);
            return;
        }

        const isSameDefect = (data.report?.metadata?.multi_image_mode === 'same_defect' || data.multi_image_mode === 'same_defect');
        if (titleEl) {
            titleEl.textContent = isSameDefect ? "Multi-View Perspectives:" : "Corridor Observations:";
        }

        // Hide large separate thumbnail strip slab; show sleek integrated floating controls
        if (galleryContainer) {
            galleryContainer.classList.add('hidden');
            galleryContainer.style.display = 'none';
        }
        if (carouselNav) {
            carouselNav.classList.remove('hidden');
            carouselNav.style.display = 'flex';
        }
        if (carouselOverlay) {
            carouselOverlay.classList.remove('hidden');
            carouselOverlay.style.display = 'flex';
        }

        // Hook prev / next carousel buttons
        const btnPrev = document.getElementById('btnReviewPrev');
        const btnNext = document.getElementById('btnReviewNext');
        if (btnPrev && !btnPrev._bound) {
            btnPrev._bound = true;
            btnPrev.addEventListener('click', () => {
                const imgs = (this.activeReportData?.images || []);
                if (imgs.length <= 1) return;
                const nextIdx = (this.activeImageIndex - 1 + imgs.length) % imgs.length;
                this.selectActiveImage(nextIdx);
            });
        }
        if (btnNext && !btnNext._bound) {
            btnNext._bound = true;
            btnNext.addEventListener('click', () => {
                const imgs = (this.activeReportData?.images || []);
                if (imgs.length <= 1) return;
                const nextIdx = (this.activeImageIndex + 1) % imgs.length;
                this.selectActiveImage(nextIdx);
            });
        }

        // Global keyboard listener for ArrowLeft / ArrowRight
        if (!this._keyboardBound) {
            this._keyboardBound = true;
            window.addEventListener('keydown', (e) => {
                const reviewView = document.getElementById('view-review');
                if (!reviewView || reviewView.classList.contains('hidden')) return;
                const imgs = (this.activeReportData?.images || []);
                if (imgs.length <= 1) return;
                if (e.key === 'ArrowLeft') {
                    const nextIdx = (this.activeImageIndex - 1 + imgs.length) % imgs.length;
                    this.selectActiveImage(nextIdx);
                } else if (e.key === 'ArrowRight') {
                    const nextIdx = (this.activeImageIndex + 1) % imgs.length;
                    this.selectActiveImage(nextIdx);
                }
            });
        }

        // Touch swipe listener on review canvas
        const canvas = document.getElementById('reviewCanvas');
        if (canvas && !canvas._swipeBound) {
            canvas._swipeBound = true;
            let touchStartX = 0;
            canvas.addEventListener('touchstart', (e) => {
                if (e.changedTouches && e.changedTouches[0]) {
                    touchStartX = e.changedTouches[0].clientX;
                }
            }, { passive: true });
            canvas.addEventListener('touchend', (e) => {
                if (e.changedTouches && e.changedTouches[0]) {
                    const deltaX = e.changedTouches[0].clientX - touchStartX;
                    const imgs = (this.activeReportData?.images || []);
                    if (imgs.length <= 1) return;
                    if (deltaX > 40) {
                        // Swipe right -> prev
                        const nextIdx = (this.activeImageIndex - 1 + imgs.length) % imgs.length;
                        this.selectActiveImage(nextIdx);
                    } else if (deltaX < -40) {
                        // Swipe left -> next
                        const nextIdx = (this.activeImageIndex + 1) % imgs.length;
                        this.selectActiveImage(nextIdx);
                    }
                }
            }, { passive: true });
        }

        this.selectActiveImage(0);
    },

    selectActiveImage(index) {
        this.activeImageIndex = index;
        const data = this.activeReportData;
        if (!data) return;

        const images = (data.images && data.images.length > 0) ? data.images : (data.image ? [data.image] : []);
        const activeImg = images[index] || images[0] || {};
        const activeAss = (data.assessments && data.assessments[index]) || (index === 0 ? data.assessment : {}) || {};

        // Update floating carousel counter
        const counterEl = document.getElementById('reviewGalleryCounter');
        if (counterEl) {
            counterEl.textContent = `Photo ${index + 1} of ${images.length}`;
        }

        // Update floating carousel pagination dots
        const dotsContainer = document.getElementById('reviewPaginationDots');
        if (dotsContainer) {
            dotsContainer.innerHTML = images.map((_, idx) => {
                const isActive = idx === index;
                const dotColor = isActive ? '#38bdf8' : 'rgba(255, 255, 255, 0.45)';
                const dotWidth = isActive ? '16px' : '6px';
                return `<button type="button" data-dot-index="${idx}" style="cursor: pointer; padding: 0; border: none; outline: none; display: inline-block; width: ${dotWidth}; height: 6px; border-radius: 3px; background: ${dotColor}; transition: all 0.2s ease; pointer-events: auto;" title="View photo ${idx + 1}"></button>`;
            }).join('');
            dotsContainer.querySelectorAll('button[data-dot-index]').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const dotIdx = parseInt(e.currentTarget.getAttribute('data-dot-index'), 10);
                    this.selectActiveImage(dotIdx);
                });
            });
        }

        // Update active class and styles on thumbnails (if present in DOM)
        const thumbList = document.getElementById('reviewThumbnailList');
        if (thumbList) {
            thumbList.querySelectorAll('.review-thumb-btn').forEach((btn, idx) => {
                const isActive = idx === index;
                btn.classList.toggle('active', isActive);
                btn.style.border = isActive ? '2px solid #0284c7' : '2px solid transparent';
                btn.style.opacity = isActive ? '1' : '0.7';
                btn.style.boxShadow = isActive ? '0 0 0 2px rgba(2, 132, 199, 0.4)' : 'none';
            });
        }

        this.updateTelemetryAndCanvas(activeImg.url, activeAss);
    },

    updateTelemetryAndCanvas(imageUrl, ai) {
        ai = ai || {};
        const detections = (ai.detections && ai.detections.length > 0)
            ? ai.detections
            : (ai.defect_class && ai.defect_class !== 'None Detected' ? [ai] : []);
        const hasDetections = detections.length > 0;

        const defectClass = ai.class_name || ai.defect_class || (hasDetections ? detections[0].class_name || 'Crack' : 'None Detected');
        const severity = (ai.severity || ai.relative_severity || 'Low').toUpperCase();
        const rawScore = ai.confidence !== undefined ? ai.confidence : (ai.confidence_score !== undefined ? ai.confidence_score : 0.0);
        const confidence = hasDetections ? Math.round(rawScore * 1000) / 10 : 0.0;
        const areaRatio = Math.round((ai.area_percentage || 0) * 10) / 10;

        const predClassEl = document.getElementById('reviewPredictedClass');
        const calcSevEl = document.getElementById('reviewCalculatedSeverity');
        if (predClassEl) predClassEl.textContent = defectClass;
        if (calcSevEl) calcSevEl.textContent = `RELATIVE SEVERITY: ${severity}`;

        const confEl = document.getElementById('telemConfidence');
        const sevEl = document.getElementById('telemSeverity');
        const areaEl = document.getElementById('telemArea');
        if (confEl) confEl.textContent = hasDetections ? `${confidence}%` : '—';
        if (sevEl) sevEl.textContent = severity;
        if (areaEl) areaEl.textContent = `${areaRatio}%`;

        // Render inspection canvas with scaled bounding boxes
        this.drawReviewCanvas(imageUrl, ai);
    },

    renderImageUnavailablePlaceholder(canvas, message) {
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const placeholderW = 640;
        const placeholderH = 400;
        canvas.width = placeholderW;
        canvas.height = placeholderH;
        ctx.fillStyle = '#0f172a';
        ctx.fillRect(0, 0, placeholderW, placeholderH);
        ctx.fillStyle = '#f59e0b';
        ctx.font = 'bold 15px "Montserrat", sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Evidence image unavailable', placeholderW / 2, 185);
        ctx.fillStyle = '#94a3b8';
        ctx.font = '12px "Montserrat", sans-serif';
        ctx.fillText(message || 'Source photographic file could not be retrieved from storage.', placeholderW / 2, 215);
    },

    drawReviewCanvas(imageUrl, aiData) {
        const canvas = document.getElementById('reviewCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');

        const resolvedUrl = window.Api?.resolveImageUrl(imageUrl) || imageUrl;

        if (!resolvedUrl) {
            this.renderImageUnavailablePlaceholder(canvas, 'Source photographic file is not stored for this report.');
            return;
        }

        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => {
            const origW = img.naturalWidth;
            const origH = img.naturalHeight;

            // Strict image load guard: do NOT draw bounding boxes if image dimensions are invalid
            if (!origW || !origH || origW === 0 || origH === 0) {
                this.renderImageUnavailablePlaceholder(canvas, 'Source photographic evidence could not be decoded.');
                return;
            }

            canvas.width = origW;
            canvas.height = origH;
            ctx.drawImage(img, 0, 0, origW, origH);

            // Optional Crack-Region Grouping Presentation Envelope
            if (aiData.crack_regions && Array.isArray(aiData.crack_regions)) {
                aiData.crack_regions.forEach(region => {
                    const env = region.pixel_envelope;
                    if (!env) return;
                    const rw = env.xmax - env.xmin;
                    const rh = env.ymax - env.ymin;
                    ctx.save();
                    ctx.strokeStyle = '#f59e0b';
                    ctx.lineWidth = Math.max(2, Math.round(origW / 300));
                    ctx.setLineDash([8, 6]);
                    ctx.strokeRect(env.xmin - 4, env.ymin - 4, rw + 8, rh + 8);
                    
                    // Region label banner
                    const regLabel = `[ ${region.label || 'Crack Region'} ]`;
                    ctx.font = `bold ${Math.max(12, Math.round(origW * 0.018))}px "Montserrat", sans-serif`;
                    const rtw = ctx.measureText(regLabel).width;
                    ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
                    ctx.fillRect(env.xmin - 4, Math.max(0, env.ymin - 26), rtw + 12, 22);
                    ctx.fillStyle = '#f59e0b';
                    ctx.fillText(regLabel, env.xmin + 2, Math.max(16, env.ymin - 10));
                    ctx.restore();
                });
            }

            const detections = (aiData.detections && aiData.detections.length > 0)
                ? aiData.detections
                : (aiData.defect_class && aiData.defect_class !== 'None Detected' ? [aiData] : []);

            if (detections.length === 0) {
                const bannerH = Math.max(40, Math.round(origH * 0.08));
                ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
                ctx.fillRect(0, 0, origW, bannerH);
                ctx.fillStyle = '#10b981';
                const fontSize = Math.max(14, Math.round(origW * 0.024));
                ctx.font = `600 ${fontSize}px "Montserrat", sans-serif`;
                ctx.fillText('No Structural Defects Detected (Confidence >= 30%)', 16, Math.round(bannerH * 0.65));
                return;
            }

            detections.forEach(det => {
                let xmin, ymin, xmax, ymax;

                if (det.bounding_box && typeof det.bounding_box === 'object' && !Array.isArray(det.bounding_box)) {
                    xmin = det.bounding_box.xmin;
                    ymin = det.bounding_box.ymin;
                    xmax = det.bounding_box.xmax;
                    ymax = det.bounding_box.ymax;
                } else if (Array.isArray(det.bounding_box)) {
                    ymin = det.bounding_box[0] * origH;
                    xmin = det.bounding_box[1] * origW;
                    ymax = det.bounding_box[2] * origH;
                    xmax = det.bounding_box[3] * origW;
                } else if (Array.isArray(det.normalized_box)) {
                    ymin = det.normalized_box[0] * origH;
                    xmin = det.normalized_box[1] * origW;
                    ymax = det.normalized_box[2] * origH;
                    xmax = det.normalized_box[3] * origW;
                } else {
                    return;
                }

                xmin = Math.max(0, Math.min(origW, xmin));
                ymin = Math.max(0, Math.min(origH, ymin));
                xmax = Math.max(xmin, Math.min(origW, xmax));
                ymax = Math.max(ymin, Math.min(origH, ymax));

                const boxW = xmax - xmin;
                const boxH = ymax - ymin;
                const defectClass = det.class_name || det.defect_class || 'Defect';
                const color = defectClass === 'Pothole' ? '#ef4444' : (defectClass === 'Crack' ? '#f59e0b' : '#0284c7');

                const lineWidth = Math.max(3, Math.round(origW / 240));
                ctx.strokeStyle = color;
                ctx.lineWidth = lineWidth;
                ctx.strokeRect(xmin, ymin, boxW, boxH);

                // Precision corner crosshairs
                const ch = Math.max(6, Math.round(origW / 80));
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 2;
                [[xmin, ymin], [xmax, ymin], [xmin, ymax], [xmax, ymax]].forEach(([cx, cy]) => {
                    ctx.beginPath();
                    ctx.moveTo(cx - ch, cy); ctx.lineTo(cx + ch, cy);
                    ctx.moveTo(cx, cy - ch); ctx.lineTo(cx, cy + ch);
                    ctx.stroke();
                });

                // Target banner pill with smart edge clamping and collision handling
                const confVal = det.confidence !== undefined ? det.confidence : (det.confidence_score || 0.0);
                const confText = Math.round(confVal * 100);
                const sevVal = det.severity || det.relative_severity || '';
                const labelText = sevVal
                    ? `${defectClass} • ${confText}% • ${sevVal}`
                    : `${defectClass} • ${confText}%`;

                const fontSize = Math.max(13, Math.round(origW * 0.022));
                ctx.font = `bold ${fontSize}px "JetBrains Mono", monospace`;
                const tw = ctx.measureText(labelText).width;
                const pillW = tw + 16;
                const pillH = fontSize + 12;

                const pillX = Math.max(2, Math.min(origW - pillW - 2, xmin));
                let pillY = (ymin >= pillH + 4) ? (ymin - pillH - 2) : (ymin + lineWidth + 2);

                if (!window._drawnReviewPills) window._drawnReviewPills = [];
                for (const prev of window._drawnReviewPills) {
                    if (Math.abs(prev.x - pillX) < pillW * 0.7 && Math.abs(prev.y - pillY) < pillH) {
                        pillY = prev.y + pillH + 4;
                    }
                }
                window._drawnReviewPills.push({ x: pillX, y: pillY, w: pillW, h: pillH });

                ctx.fillStyle = 'rgba(15, 23, 42, 0.92)';
                ctx.fillRect(pillX, pillY, pillW, pillH);
                ctx.strokeStyle = color;
                ctx.lineWidth = 1;
                ctx.strokeRect(pillX, pillY, pillW, pillH);

                ctx.fillStyle = color;
                ctx.fillText(labelText, pillX + 8, pillY + fontSize + 2);
            });
            window._drawnReviewPills = [];
        };

        img.onerror = () => {
            this.renderImageUnavailablePlaceholder(canvas, 'Source photographic evidence could not be retrieved from storage.');
        };

        img.src = resolvedUrl;
    },

    async handleLifecycleTransition(targetStatus, reason = '') {
        if (!this.currentReport) {
            window.App.showToast("No active defect report loaded.", true);
            return;
        }

        if (this.currentReport.status === 'Resolved') {
            window.App.showToast("This defect report has already completed professional review and resolution. The record is displayed in read-only mode.", true);
            return;
        }

        const reportId = this.currentReport.report_id || this.currentReport._id;

        try {
            const res = await window.Api.updateReportStatus(reportId, targetStatus, reason);
            window.App.showToast(`Lifecycle status updated: ${res.report.status}`);
            
            // Reload report to refresh indicators
            await this.loadReportForReview(reportId);

            // Also refresh Dashboard queue if active
            if (window.Dashboard) {
                window.Dashboard.loadDashboardData();
            }
        } catch (err) {
            console.error("[Review] Lifecycle transition failed:", err);
            window.App.showToast(err.message || `Cannot transition to '${targetStatus}'.`, true);
        }
    },

    /**
     * Section 3: Client-side Resolution Guard & Case Closure Workflow
     * Validates:
     * 1. Action taken only by assigned Lead Engineer (or system admin).
     * 2. All field objectives in Inspection Notebook completed OR marked N/A with documented justification.
     * 3. Formal case closure summary note provided.
     */
    async handleResolutionWorkflow(openDrawerCallback = null) {
        if (!this.currentReport) {
            window.App?.showToast("No active defect report loaded.", true);
            return;
        }

        if (this.currentReport.status === 'Resolved') {
            window.App?.showToast("This defect report has already completed professional review and resolution. The record is displayed in read-only mode.", true);
            return;
        }

        const reportId = this.currentReport.report_id || this.currentReport._id;
        const meta = this.currentReport.metadata || {};

        // 1. Lead Engineer Authorization Guard
        const user = window.Auth?.getUser() || window.App?.currentUser;
        const currentUserId = String(user?.id || user?.user_id || user?._id || '');
        const isEngAdmin = (user?.role === 'admin');
        const leadEng = meta.lead_engineer || {};
        const leadEngId = String(leadEng.user_id || this.currentReport.assigned_engineer_id || meta.assigned_engineer_id || '');

        if (!isEngAdmin && leadEngId && currentUserId && currentUserId !== leadEngId) {
            const leadName = leadEng.name || meta.assigned_engineer_name || 'Assigned Lead Engineer';
            window.App?.showToast(`Resolution Guard: Only the assigned Lead Engineer (${leadName}) or a system administrator can formally resolve this case.`, true);
            return;
        }

        // 2. Inspection Notebook Field Objectives Guard
        const checklist = this.currentNotebook.checklist || [];
        const incomplete = [];
        const missingNaReasons = [];

        for (const item of checklist) {
            const isDone = item.completed || item.checked || item.status === 'completed';
            const isNa = item.is_na || item.status === 'not_applicable';
            if (!isDone && !isNa) {
                incomplete.push(item.text || item.label || 'Pending objective');
            } else if (isNa) {
                const reason = (item.na_reason || item.reason || '').trim();
                if (!reason) {
                    missingNaReasons.push(item.text || item.label || 'N/A objective');
                }
            }
        }

        if (incomplete.length > 0) {
            window.App?.showToast(`Resolution Guard: ${incomplete.length} inspection objective(s) are pending. Complete all items in the Inspection Notebook before closing this case.`, true);
            if (openDrawerCallback) openDrawerCallback();
            this.switchDrawerTab('drawerPanelObjectives');
            return;
        }

        if (missingNaReasons.length > 0) {
            window.App?.showToast(`Resolution Guard: ${missingNaReasons.length} objective(s) marked N/A require documented justification.`, true);
            if (openDrawerCallback) openDrawerCallback();
            this.switchDrawerTab('drawerPanelObjectives');
            return;
        }

        // 3. Mandatory Formal Resolution Summary Note
        let resolutionNotes = document.getElementById('engineerNotes')?.value.trim() || '';
        if (!resolutionNotes) {
            const promptNote = window.prompt(
                "Resolution Guard: Please enter a formal defect remediation / case closure summary note:",
                "All field inspection objectives completed and verified on-site. Maintenance repairs completed to standard. Case formally resolved."
            );
            if (!promptNote || !promptNote.trim()) {
                window.App?.showToast("Resolution cancelled: Professional case closure summary note is required.", true);
                return;
            }
            resolutionNotes = promptNote.trim();
        }

        // 4. Submit Resolution Transition
        const btnResolved = document.getElementById('btnMarkResolved');
        try {
            if (btnResolved) {
                btnResolved.disabled = true;
                btnResolved.innerHTML = "<i class='bx bx-loader-alt bx-spin'></i> Resolving...";
            }

            await window.Api.updateReportStatus(reportId, 'Resolved', resolutionNotes);
            window.App?.showToast("Case successfully marked RESOLVED. Defect record is now closed and read-only.");
            
            await this.loadReportForReview(reportId);

            if (window.Dashboard) {
                window.Dashboard.loadDashboardData();
            }
        } catch (err) {
            console.error("[Review] Resolution failed:", err);
            window.App?.showToast(err.message || "Failed to resolve defect report.", true);
        } finally {
            if (btnResolved) {
                btnResolved.disabled = false;
                btnResolved.innerHTML = "<i class='bx bx-check-double'></i> Mark Resolved";
            }
        }
    },

    async submitProfessionalValidation() {
        if (!this.currentReport) {
            window.App.showToast("No active defect report loaded to review.", true);
            return;
        }

        if (this.currentReport.status === 'Resolved') {
            window.App.showToast("This defect report has already completed professional review and resolution. The record is displayed in read-only mode.", true);
            return;
        }

        const decision = document.querySelector('input[name="reviewDecision"]:checked')?.value || 'Confirmed';
        const comments = document.getElementById('engineerNotes')?.value.trim() || '';
        const reportId = this.currentReport.report_id || this.currentReport._id;

        // Validation rule: professional engineer notes are mandatory
        if (!comments) {
            window.App.showToast("Professional engineer review notes are required before signing off.", true);
            const notesEl = document.getElementById('engineerNotes');
            if (notesEl) notesEl.focus();
            return;
        }

        const overrideDetails = decision === 'Overridden' ? {
            override_class: document.getElementById('overrideClassSelect').value,
            override_severity: document.getElementById('overrideSeveritySelect').value
        } : {};

        const nextAction = document.getElementById('reviewNextAction')?.value || 'Continue monitoring';
        const followUpDate = document.getElementById('reviewFollowUpDate')?.value || '';

        try {
            await window.Api.reviewReportDirect(reportId, {
                decision,
                comments,
                override_details: overrideDetails,
                next_action: nextAction,
                follow_up_date: followUpDate
            });

            window.App.showToast("Defect verified. You are now the Lead Engineer for this case.");

            // Reload report state
            await this.loadReportForReview(reportId);

            // Refresh dashboard
            if (window.Dashboard) {
                window.Dashboard.loadDashboardData();
            }
        } catch (e) {
            console.error("[Review] Sign off error:", e);
            window.App.showToast(e.message || "Failed to submit professional validation.", true);
        }
    },

    // -------------------------------------------------------------------------
    // Sections 30-33 & 43: Professional Inspection Notebook & Field Work Notes
    // -------------------------------------------------------------------------
    currentNotebook: {
        checklist: [],
        note_cards: [],
        compliance_context: {},
        last_updated_at: null
    },
    _pendingNaIndex: null,

    renderInspectionNotebook(report, assetType = '') {
        const isBuilding = assetType.toLowerCase().includes('building') || assetType.toLowerCase().includes('structure');
        const meta = report.metadata || {};
        const savedNb = meta.inspection_notebook || {};

        // Default objectives based on asset type (Sections 31 & 32)
        const defaultRoadItems = [
            "Confirm reported defect type",
            "Inspect surrounding pavement condition",
            "Determine extent of visible distress",
            "Check for additional cracking/potholes/ravelling",
            "Review drainage/ponding evidence",
            "Assess road-user impact",
            "Determine likely maintenance priority",
            "Determine whether structural evaluation is required",
            "Record recommended remedial action",
            "Schedule follow-up inspection if necessary"
        ];

        const defaultBuildingItems = [
            "Visual condition of structural elements reviewed",
            "Visible additions/alterations reviewed",
            "Surrounding ground/slope/drainage reviewed",
            "Available construction/design history reviewed",
            "Further structural assessment required",
            "Non-destructive testing recommended",
            "Material testing recommended",
            "Remedial work recommendation recorded"
        ];

        const defaultLabels = isBuilding ? defaultBuildingItems : defaultRoadItems;
        const savedList = savedNb.checklist || [];

        let mergedChecklist = [];
        if (savedList.length > 0) {
            mergedChecklist = savedList.map((item, i) => {
                const text = item.text || item.label || (defaultLabels[i] || `Objective ${i+1}`);
                const isCompleted = Boolean(item.completed || item.checked || item.status === 'completed');
                const isNa = Boolean(item.is_na || item.status === 'not_applicable');
                return {
                    id: item.id || `obj_${i+1}`,
                    text,
                    label: text,
                    completed: isCompleted,
                    checked: isCompleted,
                    status: isNa ? 'not_applicable' : (isCompleted ? 'completed' : 'pending'),
                    is_na: isNa,
                    na_reason: item.na_reason || null,
                    na_by: item.na_by || null,
                    na_at: item.na_at || null,
                    completed_by: item.completed_by || null,
                    completed_at: item.completed_at || null,
                    custom: Boolean(item.custom)
                };
            });
        } else {
            mergedChecklist = defaultLabels.map((label, i) => ({
                id: `obj_${i+1}`,
                text: label,
                label,
                completed: false,
                checked: false,
                status: 'pending',
                is_na: false,
                na_reason: null,
                na_by: null,
                na_at: null,
                completed_by: null,
                completed_at: null,
                custom: false
            }));
        }

        this.currentNotebook.checklist = mergedChecklist;
        this.currentNotebook.note_cards = savedNb.note_cards || [];
        this.currentNotebook.compliance_context = savedNb.compliance_context || {};
        this.currentNotebook.last_updated_at = savedNb.last_updated_at || null;

        const titleEl = document.getElementById('checklistTitle');
        if (titleEl) {
            titleEl.textContent = isBuilding ? "Building / Structural Inspection Objectives" : "Road / Pavement Inspection Objectives";
        }

        this.renderChecklistItems();

        // Building Compliance Card (Section 43)
        const compCard = document.getElementById('reviewBuildingComplianceCard');
        if (compCard) {
            if (isBuilding) {
                compCard.classList.remove('hidden');
                compCard.style.display = 'block';
                const ctx = this.currentNotebook.compliance_context;
                const selAppr = document.getElementById('compApprovalSelect');
                const selAlt = document.getElementById('compAlterationSelect');
                const selFl = document.getElementById('compFloorsSelect');
                const selNca = document.getElementById('compNcaSelect');
                const inpNotes = document.getElementById('compNotesInput');

                if (selAppr) selAppr.value = ctx.approval_info || 'Unknown';
                if (selAlt) selAlt.value = ctx.alterations || 'Unknown';
                if (selFl) selFl.value = ctx.additional_floors || 'Unknown';
                if (selNca) selNca.value = ctx.nca_county_verification || 'No';
                if (inpNotes) inpNotes.value = ctx.notes || '';
            } else {
                compCard.classList.add('hidden');
                compCard.style.display = 'none';
            }
        }

        this.renderNoteCards();
    },

    renderChecklistItems() {
        const container = document.getElementById('reviewChecklistItems');
        const progressEl = document.getElementById('checklistProgress');
        if (!container) return;

        const items = this.currentNotebook.checklist || [];
        const total = items.length;
        const doneCount = items.filter(i => i.completed || i.checked || i.is_na || i.status === 'completed' || i.status === 'not_applicable').length;

        const countText = `${doneCount} of ${total} completed`;
        if (progressEl) progressEl.textContent = countText;
        const drawerProgress = document.getElementById('drawerChecklistProgress');
        if (drawerProgress) drawerProgress.textContent = countText;
        const pillProgress = document.getElementById('notebookProgressCount');
        if (pillProgress) pillProgress.textContent = countText;
        const underReviewProgress = document.getElementById('reviewUnderReviewProgress');
        if (underReviewProgress) underReviewProgress.textContent = countText;

        container.innerHTML = items.map((item, idx) => {
            const isCompleted = Boolean(item.completed || item.checked || item.status === 'completed');
            const isNa = Boolean(item.is_na || item.status === 'not_applicable');
            const text = item.text || item.label || 'Inspection Objective';
            const author = item.completed_by || item.na_by || '';
            const dateStr = item.completed_at || item.na_at ? new Date(item.completed_at || item.na_at).toLocaleDateString('en-KE', { dateStyle: 'short' }) : '';

            let styleText = 'color: #1e293b;';
            if (isCompleted) styleText = 'text-decoration: line-through; color: #64748b;';
            if (isNa) styleText = 'text-decoration: line-through; color: #94a3b8; font-style: italic;';

            return `
                <div class="notebook-objective-item" style="display:flex; flex-direction:column; gap:2px; padding:6px 8px; border-radius:6px; background:${isNa ? '#f8fafc' : isCompleted ? '#f0fdf4' : '#ffffff'}; border:1px solid ${isNa ? '#e2e8f0' : isCompleted ? '#bbf7d0' : '#e2e8f0'};">
                    <div style="display:flex; align-items:flex-start; gap:0.55rem;">
                        <input type="checkbox" data-index="${idx}" ${isCompleted ? 'checked' : ''} ${isNa ? 'disabled' : ''} style="margin-top:2px; cursor:pointer;">
                        <div style="flex:1;">
                            <span style="${styleText}; font-size:0.8rem; line-height:1.35; display:block;">
                                ${text}
                                ${isNa ? `<span style="display:inline-block; margin-left:4px; font-size:0.7rem; color:#b45309; background:#fef3c7; padding:1px 5px; border-radius:3px;">N/A: ${item.na_reason || 'Documented'}</span>` : ''}
                            </span>
                            ${(author && (isCompleted || isNa)) ? `
                                <span style="font-size:0.68rem; color:#64748b; display:block; margin-top:1px;">
                                    ${isCompleted ? '✓ Completed by' : '— Excluded by'} ${author}${dateStr ? ` on ${dateStr}` : ''}
                                </span>
                            ` : ''}
                        </div>
                        <div style="display:flex; align-items:center; gap:0.3rem;">
                            ${isNa ? `
                                <button type="button" data-unmark-na="${idx}" style="font-size:0.68rem; padding:1px 5px; background:none; border:1px solid #cbd5e1; border-radius:3px; color:#475569; cursor:pointer;" title="Re-enable this objective">
                                    Re-enable
                                </button>
                            ` : `
                                <button type="button" data-mark-na="${idx}" style="font-size:0.68rem; padding:1px 5px; background:none; border:1px solid #cbd5e1; border-radius:3px; color:#64748b; cursor:pointer;" title="Mark this objective as not applicable">
                                    N/A
                                </button>
                            `}
                            ${item.custom ? `
                                <button type="button" data-remove-index="${idx}" style="background:none; border:none; color:#ef4444; cursor:pointer; font-size:12px; line-height:1;" title="Remove custom objective">✕</button>
                            ` : ''}
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        // Wire checkbox toggles
        container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', (e) => {
                const idx = parseInt(e.target.getAttribute('data-index'), 10);
                const user = window.Auth?.getUser() || window.App?.currentUser;
                const authorName = user?.name || 'Reviewing Engineer';
                const it = this.currentNotebook.checklist[idx];
                if (it) {
                    it.completed = e.target.checked;
                    it.checked = e.target.checked;
                    it.status = e.target.checked ? 'completed' : 'pending';
                    it.completed_by = e.target.checked ? authorName : null;
                    it.completed_at = e.target.checked ? new Date().toISOString() : null;
                    this.renderChecklistItems();
                    this.debouncedSaveNotebook();
                }
            });
        });

        // Wire Mark N/A
        container.querySelectorAll('button[data-mark-na]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const idx = parseInt(e.currentTarget.getAttribute('data-mark-na'), 10);
                this.openMarkNaModal(idx);
            });
        });

        // Wire Re-enable
        container.querySelectorAll('button[data-unmark-na]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const idx = parseInt(e.currentTarget.getAttribute('data-unmark-na'), 10);
                const it = this.currentNotebook.checklist[idx];
                if (it) {
                    it.is_na = false;
                    it.status = 'pending';
                    it.na_reason = null;
                    it.na_by = null;
                    it.na_at = null;
                    this.renderChecklistItems();
                    this.debouncedSaveNotebook();
                }
            });
        });

        // Wire Remove
        container.querySelectorAll('button[data-remove-index]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const idx = parseInt(e.currentTarget.getAttribute('data-remove-index'), 10);
                this.currentNotebook.checklist.splice(idx, 1);
                this.renderChecklistItems();
                this.debouncedSaveNotebook();
            });
        });
    },

    openMarkNaModal(idx) {
        const item = this.currentNotebook.checklist[idx];
        if (!item) return;
        this._pendingNaIndex = idx;
        const modal = document.getElementById('markObjectiveNaModal');
        const labelEl = document.getElementById('markNaObjectiveLabel');
        const reasonInput = document.getElementById('markNaReasonInput');
        if (labelEl) labelEl.textContent = item.text || item.label || 'Objective';
        if (reasonInput) reasonInput.value = '';
        if (modal) modal.classList.add('active');
    },

    addCustomObjective() {
        const inp = document.getElementById('customObjectiveInput');
        if (!inp) return;
        const val = inp.value.trim();
        if (!val) return;

        this.currentNotebook.checklist.push({
            id: `custom_${Date.now()}`,
            text: val,
            label: val,
            completed: false,
            checked: false,
            status: 'pending',
            is_na: false,
            na_reason: null,
            na_by: null,
            na_at: null,
            completed_by: null,
            completed_at: null,
            custom: true
        });
        inp.value = '';
        this.renderChecklistItems();
    },

    renderNoteCards() {
        const container = document.getElementById('reviewNoteCardsList');
        const countEl = document.getElementById('noteCardsCount');
        if (!container) return;

        const cards = this.currentNotebook.note_cards || [];
        if (countEl) countEl.textContent = `${cards.length} card${cards.length === 1 ? '' : 's'}`;

        if (cards.length === 0) {
            container.innerHTML = `
                <div style="font-size: 0.78rem; color: #94a3b8; font-style: italic; text-align: center; padding: 0.5rem;">
                    No inspection note cards recorded yet.
                </div>
            `;
            return;
        }

        const categoryColors = {
            'Observation': { bg: '#f0f9ff', border: '#bae6fd', text: '#0369a1' },
            'Follow-Up': { bg: '#fffbeb', border: '#fde68a', text: '#b45309' },
            'Maintenance': { bg: '#f0fdf4', border: '#bbf7d0', text: '#15803d' },
            'Compliance Context': { bg: '#fff7ed', border: '#fed7aa', text: '#c2410c' }
        };

        container.innerHTML = cards.map((card, idx) => {
            const cat = card.category || 'Observation';
            const colors = categoryColors[cat] || categoryColors['Observation'];
            const dateStr = card.timestamp ? new Date(card.timestamp).toLocaleString('en-KE', { dateStyle: 'short', timeStyle: 'short' }) : 'Recent';
            return `
                <div style="background: ${colors.bg}; border: 1px solid ${colors.border}; border-radius: 6px; padding: 0.5rem 0.65rem; display: flex; flex-direction: column; gap: 0.25rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.7rem;">
                        <span style="font-weight: 700; color: ${colors.text}; text-transform: uppercase; letter-spacing: 0.04em;">${cat}</span>
                        <div style="display: flex; align-items: center; gap: 0.4rem; color: #64748b;">
                            <span>${card.author || 'Engineer'} • ${dateStr}</span>
                            <button type="button" data-del-card="${idx}" style="background:none; border:none; color:#94a3b8; cursor:pointer; font-size:12px; line-height:1;" title="Delete note card">✕</button>
                        </div>
                    </div>
                    <p style="margin: 0; font-size: 0.8rem; color: #0f172a; line-height: 1.35;">${card.text}</p>
                </div>
            `;
        }).join('');

        container.querySelectorAll('button[data-del-card]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const idx = parseInt(e.currentTarget.getAttribute('data-del-card'), 10);
                this.currentNotebook.note_cards.splice(idx, 1);
                this.renderNoteCards();
            });
        });
    },

    addNoteCard() {
        const catSelect = document.getElementById('noteCategorySelect');
        const textInp = document.getElementById('noteCardTextInput');
        if (!textInp) return;
        const text = textInp.value.trim();
        if (!text) {
            window.App?.showToast("Please enter text for the note card.", true);
            return;
        }

        const category = catSelect?.value || 'Observation';
        const user = window.Auth?.getUser() || window.App?.currentUser;
        const author = user?.name || 'Reviewing Engineer';
        const timestamp = new Date().toISOString();

        if (!this.currentNotebook.note_cards) {
            this.currentNotebook.note_cards = [];
        }

        this.currentNotebook.note_cards.unshift({
            id: 'card_' + Date.now(),
            category,
            text,
            author,
            timestamp
        });

        textInp.value = '';
        this.renderNoteCards();
    },

    // -------------------------------------------------------------------------
    // Internal Drawer Tabs (Shadcn Tabs UI Pattern)
    // -------------------------------------------------------------------------
    switchDrawerTab(panelId) {
        document.querySelectorAll('.notebook-tab-btn').forEach(btn => {
            const isMatch = btn.getAttribute('data-target') === panelId;
            btn.classList.toggle('active', isMatch);
            btn.style.color = isMatch ? '#0070d1' : '#64748b';
            btn.style.borderBottom = isMatch ? '2px solid #0070d1' : '2px solid transparent';
            btn.style.fontWeight = isMatch ? '600' : '500';
        });

        document.querySelectorAll('.drawer-tab-panel').forEach(panel => {
            const isMatch = panel.id === panelId;
            panel.classList.toggle('hidden', !isMatch);
            panel.style.display = isMatch ? 'block' : 'none';
        });

        if (panelId === 'drawerPanelEvidence') {
            this.renderDrawerEvidence();
        } else if (panelId === 'drawerPanelTeam') {
            this.loadDrawerTeam();
        }
    },

    renderDrawerEvidence() {
        const data = this.activeReportData || { report: this.currentReport, assessment: this.currentAssessment };
        const images = (data.images && data.images.length > 0) ? data.images : (data.image ? [data.image] : []);
        const thumbsContainer = document.getElementById('drawerEvidenceThumbnails');
        const detailsContainer = document.getElementById('drawerEvidenceDetails');
        if (!thumbsContainer) return;

        if (images.length === 0) {
            thumbsContainer.innerHTML = `<p style="color:#94a3b8; font-style:italic;">No photographic evidence attached.</p>`;
            if (detailsContainer) detailsContainer.innerHTML = '';
            return;
        }

        thumbsContainer.innerHTML = images.map((img, idx) => {
            const isActive = idx === this.activeImageIndex;
            const thumbUrl = window.Api?.resolveImageUrl(img.url) || img.url;
            return `
                <div class="evidence-thumb-card" data-idx="${idx}" style="cursor:pointer; border:2px solid ${isActive ? '#0284c7' : '#e2e8f0'}; border-radius:6px; overflow:hidden; background:#0f172a; position:relative; aspect-ratio:4/3; transition: transform 0.15s ease;">
                    <img src="${thumbUrl}" alt="Photo ${idx+1}" style="width:100%; height:100%; object-fit:cover;" onerror="this.parentElement.style.background='#1e293b';">
                    <span style="position:absolute; bottom:2px; left:4px; font-size:0.68rem; color:#ffffff; background:rgba(0,0,0,0.65); padding:1px 5px; border-radius:3px;">
                        Photo ${idx+1}
                    </span>
                </div>
            `;
        }).join('');

        thumbsContainer.querySelectorAll('.evidence-thumb-card').forEach(card => {
            card.addEventListener('click', (e) => {
                const idx = parseInt(e.currentTarget.getAttribute('data-idx'), 10);
                this.selectActiveImage(idx);
                this.renderDrawerEvidence();
            });
        });

        // Telemetry details
        const ai = (data.assessments && data.assessments[this.activeImageIndex]) || data.assessment || {};
        const detections = ai.detections || [];
        if (detailsContainer) {
            detailsContainer.innerHTML = `
                <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:6px; padding:0.65rem 0.85rem; margin-top:0.5rem; display:flex; flex-direction:column; gap:0.4rem;">
                    <div style="display:flex; justify-content:space-between; font-size:0.75rem;">
                        <span style="color:#64748b;">Active Frame:</span>
                        <strong style="color:#0f172a;">Photo ${this.activeImageIndex + 1} of ${images.length}</strong>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:0.75rem;">
                        <span style="color:#64748b;">Detected Objects:</span>
                        <strong style="color:#0284c7;">${detections.length} defect bounding box${detections.length === 1 ? '' : 'es'}</strong>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:0.75rem;">
                        <span style="color:#64748b;">Primary Defect:</span>
                        <strong style="color:#0f172a;">${ai.defect_class || 'Surface distress'}</strong>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:0.75rem;">
                        <span style="color:#64748b;">Visual Severity:</span>
                        <span class="severity-pill ${(ai.relative_severity || 'low').toLowerCase()}" style="font-size:0.65rem; padding:1px 6px;">${(ai.relative_severity || 'Low').toUpperCase()}</span>
                    </div>
                </div>
            `;
        }
    },

    async loadDrawerTeam() {
        if (!this.currentReport) return;
        const reportId = this.currentReport.report_id || this.currentReport._id;
        const meta = this.currentReport.metadata || {};

        // Lead Engineer info
        const leadEng = meta.lead_engineer || {};
        const leadName = leadEng.name || meta.assigned_engineer_name || 'Eng. Regina';
        const leadEmail = leadEng.email || meta.assigned_engineer_email || 'regina@kenha.co.ke';
        const leadNameEl = document.getElementById('drawerLeadEngineerName');
        const leadEmailEl = document.getElementById('drawerLeadEngineerEmail');
        if (leadNameEl) leadNameEl.textContent = leadName;
        if (leadEmailEl) leadEmailEl.textContent = leadEmail;

        // Render Collaborators
        const collabs = meta.collaborators || [];
        const countEl = document.getElementById('drawerCollaboratorsCount');
        const listEl = document.getElementById('drawerCollaboratorsList');
        if (countEl) countEl.textContent = `${collabs.length} Collaborator${collabs.length === 1 ? '' : 's'}`;

        if (listEl) {
            if (collabs.length === 0) {
                listEl.innerHTML = `
                    <div style="font-size: 0.76rem; color: #94a3b8; font-style: italic; padding: 0.5rem 0; text-align: center;">
                        No inspection collaborators added yet.
                    </div>
                `;
            } else {
                listEl.innerHTML = collabs.map((c, idx) => {
                    const addedDate = c.added_at ? new Date(c.added_at).toLocaleDateString('en-KE', { dateStyle: 'short' }) : '';
                    return `
                        <div style="display:flex; justify-content:space-between; align-items:center; background:#ffffff; border:1px solid #e2e8f0; border-radius:6px; padding:0.5rem 0.65rem;">
                            <div style="display:flex; align-items:center; gap:0.5rem;">
                                <div style="width:28px; height:28px; border-radius:50%; background:#e0f2fe; color:#0369a1; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:0.75rem;">
                                    ${(c.name || 'E').charAt(0).toUpperCase()}
                                </div>
                                <div>
                                    <span style="font-size:0.8rem; font-weight:600; color:#0f172a; display:block;">${c.name || 'Engineer'}</span>
                                    <span style="font-size:0.7rem; color:#64748b;">${c.role || 'Collaborating Engineer'}${addedDate ? ` • ${addedDate}` : ''}</span>
                                </div>
                            </div>
                            <button type="button" class="btn-remove-collab" data-collab-id="${c.user_id || c.engineer_id || idx}" style="background:none; border:none; color:#ef4444; font-size:0.72rem; cursor:pointer; padding:2px 6px; border-radius:4px;" title="Remove collaborator">
                                Remove
                            </button>
                        </div>
                    `;
                }).join('');

                listEl.querySelectorAll('.btn-remove-collab').forEach(btn => {
                    btn.addEventListener('click', async (e) => {
                        const collabId = e.currentTarget.getAttribute('data-collab-id');
                        try {
                            await window.Api.removeCollaborator(reportId, collabId);
                            window.App?.showToast("Collaborator removed.");
                            const fresh = await window.Api.getReportById(reportId);
                            this.currentReport = fresh.report;
                            this.loadDrawerTeam();
                        } catch (err) {
                            window.App?.showToast(err.message || "Failed to remove collaborator.", true);
                        }
                    });
                });
            }
        }

        // Populate available engineers in invite select & transfer lead select
        try {
            const availData = await window.Api.getAvailableEngineers(reportId);
            const engineers = availData.engineers || availData.available_engineers || [];
            
            const inviteSelect = document.getElementById('inviteEngineerSelect');
            if (inviteSelect) {
                if (engineers.length === 0) {
                    inviteSelect.innerHTML = `<option value="">No other engineers available</option>`;
                } else {
                    inviteSelect.innerHTML = `<option value="">Select available engineer...</option>` +
                        engineers.map(e => `<option value="${e.user_id || e._id}">${e.name} (${e.email || 'Accredited'})</option>`).join('');
                }
            }

            const transferSelect = document.getElementById('transferLeadSelect');
            if (transferSelect) {
                if (engineers.length === 0) {
                    transferSelect.innerHTML = `<option value="">No available engineers</option>`;
                } else {
                    transferSelect.innerHTML = `<option value="">Select new Lead Engineer...</option>` +
                        engineers.map(e => `<option value="${e.user_id || e._id}">${e.name} (${e.email || 'Accredited'})</option>`).join('');
                }
            }
        } catch (err) {
            console.warn("[Review] Failed loading available engineers:", err);
        }
    },

    _saveDebounceTimer: null,
    debouncedSaveNotebook() {
        const saveStatus = document.getElementById('drawerSaveStatus');
        if (saveStatus) {
            saveStatus.textContent = 'Saving...';
            saveStatus.style.color = '#f59e0b';
        }
        if (this._saveDebounceTimer) clearTimeout(this._saveDebounceTimer);
        this._saveDebounceTimer = setTimeout(() => {
            this.saveInspectionNotebook(true);
        }, 800);
    },

    async saveInspectionNotebook(isAutosave = false) {
        if (!this.currentReport || !this.currentNotebook) {
            if (!isAutosave) {
                window.App?.showToast("No active report loaded to save notebook.", true);
            }
            return;
        }

        const reportId = this.currentReport.report_id || this.currentReport._id;

        const selAppr = document.getElementById('compApprovalSelect');
        const selAlt = document.getElementById('compAlterationSelect');
        const selFl = document.getElementById('compFloorsSelect');
        const selNca = document.getElementById('compNcaSelect');
        const inpNotes = document.getElementById('compNotesInput');

        const compliance_context = {
            approval_info: selAppr?.value || 'Unknown',
            alterations: selAlt?.value || 'Unknown',
            additional_floors: selFl?.value || 'Unknown',
            nca_county_verification: selNca?.value || 'No',
            notes: inpNotes?.value.trim() || ''
        };

        const expected_updated_at = this.currentNotebook.last_updated_at ||
            this.currentReport.metadata?.inspection_notebook?.last_updated_at || null;

        const payload = {
            checklist: this.currentNotebook.checklist,
            note_cards: this.currentNotebook.note_cards,
            compliance_context,
            expected_updated_at
        };

        const saveStatus = document.getElementById('drawerSaveStatus');
        const btnSave = document.getElementById('btnSaveInspectionNotebook');

        try {
            if (saveStatus) {
                saveStatus.textContent = 'Saving...';
                saveStatus.style.color = '#f59e0b';
            }
            if (btnSave && !isAutosave) {
                btnSave.disabled = true;
                btnSave.innerHTML = "<i class='bx bx-loader-alt bx-spin'></i> Saving...";
            }

            const res = await window.Api.updateInspectionNotebook(reportId, payload);
            if (res.inspection_notebook) {
                this.currentNotebook.last_updated_at = res.inspection_notebook.last_updated_at;
                if (this.currentReport.metadata) {
                    this.currentReport.metadata.inspection_notebook = res.inspection_notebook;
                }
            }

            if (saveStatus) {
                saveStatus.textContent = 'Saved';
                saveStatus.style.color = '#059669';
            }

            if (!isAutosave) {
                window.App?.showToast("Inspection notebook saved successfully.");
                if (btnSave) {
                    btnSave.disabled = false;
                    btnSave.innerHTML = "<i class='bx bx-check'></i> Saved";
                    setTimeout(() => {
                        btnSave.innerHTML = "<i class='bx bx-save'></i> Save Notebook";
                    }, 2000);
                }
            }
        } catch (err) {
            console.error("[Review] Failed saving inspection notebook:", err);
            if (saveStatus) {
                saveStatus.textContent = 'Save Error';
                saveStatus.style.color = '#ef4444';
            }
            if (!isAutosave) {
                if (err.conflict || err.status === 409) {
                    window.App?.showToast("Notebook was modified by another engineer in the team. Refreshing latest inspection record...", true);
                    await this.loadReportForReview(reportId);
                } else {
                    window.App?.showToast(err.message || "Failed to save inspection notebook.", true);
                }
                if (btnSave) {
                    btnSave.disabled = false;
                    btnSave.innerHTML = "<i class='bx bx-save'></i> Save Notebook";
                }
            }
        }
    }
};

window.Review = Review;
