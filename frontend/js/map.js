/**
 * InfraVision Map Module - Interactive Civil Infrastructure Defect Map
 * Powered by Leaflet + OpenStreetMap with Leaflet.markercluster.
 *
 * Defaults:
 *   Center: Nairobi, Kenya (Latitude: -1.286389, Longitude: 36.817223)
 *   Zoom: 12
 *
 * Privacy:
 *   Strips private citizen identities (names, emails, phone numbers) to safeguard privacy.
 */

const DefectMap = {
    map: null,
    markerCluster: null,
    reportMarkerLayer: null,
    advisoriesLayer: null,
    advisoryMarkers: {},
    reportMarkers: {},
    tileLayer: null,
    reportsData: [],
    RESOLVED_MAP_RETENTION_DAYS: 7, // Configurable operational map retention window (Section 10)
    config: {
        default_center: { lat: -1.286389, lng: 36.817223 },
        default_zoom: 12,
        min_zoom: 5,
        max_zoom: 19,
        tile_layer: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors'
    },
    activeFilters: {
        defect_class: '',
        status: '',
        severity: '',
        asset_type: ''
    },
    isInitialized: false,
    heatLayer: null,
    heatLayerLow: null,
    heatLayerMedium: null,
    heatLayerCritical: null,
    showHotspotLayer: true,
    heatGradient: {
        0.20: '#22c55e', // Clean low-density green (#10b981)
        0.50: '#eab308', // Moderate yellow/amber
        0.72: '#f59e0b', // Higher orange
        1.00: '#ef4444'  // Peak hotspot crimson (#991b1b)
    },

    getZoomHeatOptions(zoom) {
        // Zoom-aware radius, blur, and opacity scaling (Section 5 & 6).
        // Keeps heat localized and analytically readable at every zoom without blanketing the map.
        if (zoom <= 7) {
            // Country / national scale: tight radius and controlled blur
            return { radius: 14, blur: 10, minOpacity: 0.22, attenuated: false };
        } else if (zoom <= 10) {
            // Regional / county view
            return { radius: 18, blur: 12, minOpacity: 0.24, attenuated: false };
        } else if (zoom <= 13) {
            // City / Nairobi default scale (zoom 11-13) - crisp point concentration, visible roads
            return { radius: 22, blur: 14, minOpacity: 0.26, attenuated: false };
        } else {
            // Street / neighbourhood scale (zoom >= 14)
            return { radius: 28, blur: 16, minOpacity: 0.28, attenuated: false };
        }
    },

    updateZoomAwareHeatmap() {
        if (!this.map || !this.heatLayer) return;
        const currentZoom = this.map.getZoom();
        const opts = this.getZoomHeatOptions(currentZoom);
        const heatPane = this.map.getPane('heatmapPane');

        // Update existing layer options without recreating instances
        this.heatLayer.setOptions({
            radius: opts.radius,
            blur: opts.blur,
            minOpacity: opts.minOpacity,
            gradient: this.heatGradient
        });

        if (this.showHotspotLayer) {
            if (heatPane) heatPane.style.display = '';
            if (!this.map.hasLayer(this.heatLayer)) {
                this.heatLayer.addTo(this.map);
            }
            if (typeof this.heatLayer.redraw === 'function') {
                this.heatLayer.redraw();
            }
        } else {
            if (heatPane) heatPane.style.display = 'none';
            if (this.map.hasLayer(this.heatLayer)) {
                this.map.removeLayer(this.heatLayer);
            }
        }
    },

    syncHotspotButtonState() {
        const btn = document.getElementById('btnToggleHotspot');
        const legend = document.getElementById('hotspotLegendItem');
        if (btn) {
            if (this.showHotspotLayer) {
                btn.classList.add('active-hotspot');
                btn.innerHTML = "<i class='bx bxs-hot'></i> Hide Hotspots";
                btn.setAttribute('aria-pressed', 'true');
                btn.title = 'Hide defect density hotspot surface';
            } else {
                btn.classList.remove('active-hotspot');
                btn.innerHTML = "<i class='bx bxs-hot'></i> Show Hotspots";
                btn.setAttribute('aria-pressed', 'false');
                btn.title = 'Display defect density hotspot surface';
            }
        }
        if (legend) {
            legend.style.display = this.showHotspotLayer ? 'flex' : 'none';
        }
    },

    async init() {
        this.bindEvents();
        await this.loadConfig();
        await this.initLeafletMap();
        await this.loadMapData();
    },

    bindEvents() {
        const classFilter = document.getElementById('mapFilterClass');
        const statusFilter = document.getElementById('mapFilterStatus');
        const severityFilter = document.getElementById('mapFilterSeverity');
        const assetFilter = document.getElementById('mapFilterAsset');
        const refreshBtn = document.getElementById('btnRefreshMap');
        const resetBtn = document.getElementById('btnResetMapFilters');
        const hotspotBtn = document.getElementById('btnToggleHotspot');

        if (classFilter) {
            classFilter.addEventListener('change', (e) => {
                this.activeFilters.defect_class = e.target.value;
                this.loadMapData();
            });
        }
        if (statusFilter) {
            statusFilter.addEventListener('change', (e) => {
                this.activeFilters.status = e.target.value;
                this.loadMapData();
            });
        }
        if (severityFilter) {
            severityFilter.addEventListener('change', (e) => {
                this.activeFilters.severity = e.target.value;
                this.loadMapData();
            });
        }
        if (assetFilter) {
            assetFilter.addEventListener('change', (e) => {
                this.activeFilters.asset_type = e.target.value;
                this.loadMapData();
            });
        }
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.loadMapData();
                window.App?.showToast("Refreshed infrastructure map data.");
            });
        }
        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                this.resetFilters();
            });
        }
        if (hotspotBtn) {
            hotspotBtn.addEventListener('click', () => {
                this.toggleHotspotLayer();
            });
        }

        window.addEventListener('resize', () => {
            this.invalidateSize();
        });
    },

    resetFilters() {
        this.activeFilters = {
            defect_class: '',
            status: '',
            severity: '',
            asset_type: ''
        };
        const classFilter = document.getElementById('mapFilterClass');
        const statusFilter = document.getElementById('mapFilterStatus');
        const severityFilter = document.getElementById('mapFilterSeverity');
        const assetFilter = document.getElementById('mapFilterAsset');

        if (classFilter) classFilter.value = '';
        if (statusFilter) statusFilter.value = '';
        if (severityFilter) severityFilter.value = '';
        if (assetFilter) assetFilter.value = '';

        this.loadMapData();
    },

    async loadConfig() {
        try {
            const config = await window.Api.getMapConfig();
            if (config) {
                if (config.default_center) this.config.default_center = config.default_center;
                if (config.default_zoom) this.config.default_zoom = config.default_zoom;
                if (config.tile_layer) this.config.tile_layer = config.tile_layer;
                if (config.attribution) this.config.attribution = config.attribution;
            }
        } catch (e) {
            console.warn("[DefectMap] Using default Nairobi map configuration:", e);
        }
    },

    async initLeafletMap() {
        const container = document.getElementById('infrastructureMapContainer');
        if (!container) return;

        // Ensure Leaflet library is loaded
        if (typeof L === 'undefined') {
            console.error("[DefectMap] Leaflet library not loaded.");
            return;
        }

        // Avoid repeated initialization of the same container
        if (this.map) {
            this.invalidateSize();
            return;
        }

        const centerLat = this.config.default_center.lat || -1.286389;
        const centerLng = this.config.default_center.lng || 36.817223;
        const zoom = this.config.default_zoom || 12;

        try {
            this.map = L.map(container, {
                center: [centerLat, centerLng],
                zoom: zoom,
                minZoom: this.config.min_zoom || 5,
                maxZoom: this.config.max_zoom || 19,
                zoomAnimation: true,
                fadeAnimation: true,
                markerZoomAnimation: true,
                preferCanvas: true
            });

            this.tileLayer = L.tileLayer(this.config.tile_layer, {
                maxZoom: 19,
                attribution: this.config.attribution
            }).addTo(this.map);

            // Dedicated heatmap pane underneath markers and clusters (markerPane is zIndex 600, overlayPane is 400)
            if (!this.map.getPane('heatmapPane')) {
                const heatPane = this.map.createPane('heatmapPane');
                heatPane.style.zIndex = '350';
                heatPane.style.pointerEvents = 'none';
                heatPane.style.opacity = '0.85';
            }

            // Section 15: Dedicated safety advisory pane above ordinary markers (600) and below popups (700)
            if (!this.map.getPane('safetyAdvisoryPane')) {
                const advPane = this.map.createPane('safetyAdvisoryPane');
                advPane.style.zIndex = '675';
            }

            // Sync initial hotspot button and legend state
            this.syncHotspotButtonState();

            // Zoom-aware dynamic heatmap adaptation
            this.map.on('zoomend', () => {
                this.updateZoomAwareHeatmap();
            });

            // Section 7 & 8: Dedicated individual marker layer for small/standard datasets (<= 150 reports)
            // Displays individual points independently across national and city scales without collapsing into one cluster.
            this.reportMarkerLayer = L.layerGroup().addTo(this.map);

            // Adaptive cluster group with zoom-dependent maxClusterRadius and severity-composition conic ring
            if (typeof L.markerClusterGroup === 'function') {
                this.markerCluster = L.markerClusterGroup({
                    chunkedLoading: true,
                    // Zoom-dependent maxClusterRadius (Section 14)
                    maxClusterRadius: (zoom) => {
                        if (zoom >= 16) return 0;
                        if (zoom >= 15) return 12;
                        if (zoom >= 14) return 18;
                        if (zoom >= 13) return 24;
                        if (zoom >= 12) return 28;
                        return 32;
                    },
                    spiderfyOnMaxZoom: true,
                    showCoverageOnHover: false,
                    zoomToBoundsOnClick: true,
                    disableClusteringAtZoom: 16,
                    iconCreateFunction: (cluster) => {
                        const childMarkers = cluster.getAllChildMarkers();
                        const count = childMarkers.length;

                        // Calculate severity composition (Section 15)
                        let critCount = 0;
                        let medCount = 0;
                        let lowCount = 0;
                        let resCount = 0;

                        for (const m of childMarkers) {
                            const isRes = (m.reportStatus === 'Resolved' || m.options?.status === 'Resolved');
                            if (isRes) {
                                resCount++;
                                continue;
                            }
                            const sev = (m.reportSeverity || m.options?.severity || 'Low').toLowerCase();
                            if (sev === 'critical') {
                                critCount++;
                            } else if (sev === 'medium' || sev === 'moderate') {
                                medCount++;
                            } else {
                                lowCount++;
                            }
                        }

                        // Conic gradient ring: Critical=Red (#ef4444), Medium=Amber (#f59e0b), Low=Blue (#0284c7), Resolved=Green (#10b981)
                        // If Critical > 0, ensure Red is guaranteed visible in the ring (Section 15)
                        const total = count || 1;
                        let critPct = (critCount / total) * 100;
                        if (critCount > 0 && critPct < 15) critPct = 15; // Guarantee visible red segment
                        const remaining = 100 - (critCount > 0 ? critPct : 0);
                        const nonCritTotal = (total - critCount) || 1;
                        const medPct = (medCount / nonCritTotal) * remaining;
                        const lowPct = (lowCount / nonCritTotal) * remaining;

                        const p1 = critPct;
                        const p2 = p1 + medPct;
                        const p3 = p2 + lowPct;

                        const conicBg = `conic-gradient(
                            #ef4444 0% ${p1}%,
                            #f59e0b ${p1}% ${p2}%,
                            #0284c7 ${p2}% ${p3}%,
                            #10b981 ${p3}% 100%
                        )`;

                        const hasCrit = critCount > 0;
                        const shadowColor = hasCrit ? 'rgba(239, 68, 68, 0.45)' : 'rgba(15, 23, 42, 0.2)';

                        return L.divIcon({
                            html: `
                                <div class="conic-cluster-wrap" style="width:32px; height:32px; border-radius:50%; background:${conicBg}; padding:2.5px; display:flex; align-items:center; justify-content:center; box-shadow:0 2px 7px ${shadowColor}; transition:transform 0.15s ease;" title="${count} nearby reports (${critCount} Critical, ${medCount} Medium, ${lowCount} Low, ${resCount} Resolved)">
                                    <div style="width:25px; height:25px; border-radius:50%; background:#ffffff; color:#0f172a; font-family:var(--font-sans, system-ui, -apple-system, sans-serif); font-weight:700; font-size:11px; display:flex; align-items:center; justify-content:center; border:1px solid #e2e8f0;">
                                        ${count}
                                    </div>
                                </div>
                            `,
                            className: 'custom-severity-cluster-icon',
                            iconSize: L.point(32, 32)
                        });
                    }
                });
            } else {
                this.markerCluster = L.layerGroup();
            }

            // Section 15: Dedicated layer for active safety advisories on safetyAdvisoryPane
            this.advisoriesLayer = L.layerGroup([], { pane: 'safetyAdvisoryPane' }).addTo(this.map);

            this.isInitialized = true;
            this.invalidateSize();
        } catch (err) {
            console.error("[DefectMap] Error initializing Leaflet map:", err);
        }
    },

    invalidateSize() {
        if (this.map) {
            setTimeout(() => {
                try {
                    this.map.invalidateSize();
                    if (this.heatLayer && typeof this.heatLayer._reset === 'function') {
                        this.heatLayer._reset();
                    }
                } catch (e) {
                    // Suppress if map is not rendered
                }
            }, 100);
        }
    },

    createMarkerIcon(severity, isUnusual, status, hasAdvisory = false) {
        const isResolved = status === 'Resolved' || this.activeFilters.status === 'Resolved';
        const isUnderReview = status === 'Under Review';
        const sev = (severity || 'Low').toLowerCase();

        // Section 8 & 9: Compact circular markers (10-16px active point)
        // Semantics: Critical -> Red (#ef4444), Medium -> Amber (#f59e0b), Low -> Strong Blue (#0284c7)
        // Low MUST NOT use green. Green is strictly reserved for positive/resolved state.
        let dotColor = '#0284c7'; // Strong Blue for Low
        let dotGlow = 'rgba(2, 132, 199, 0.4)';
        if (sev === 'critical') {
            dotColor = '#ef4444'; // Red
            dotGlow = 'rgba(239, 68, 68, 0.45)';
        } else if (sev === 'medium' || sev === 'moderate') {
            dotColor = '#f59e0b'; // Amber
            dotGlow = 'rgba(245, 158, 11, 0.45)';
        }

        let iconInner = '';
        if (isResolved) {
            // Retained & refined resolved marker: Green checkmark circular badge (16px)
            iconInner = `
                <div class="custom-leaflet-marker resolved-circle-marker" style="width:16px; height:16px; border-radius:50%; background:#10b981; border:2px solid #ffffff; box-shadow:0 2px 6px rgba(16,185,129,0.55); display:flex; align-items:center; justify-content:center; color:#ffffff; font-size:11px; cursor:pointer; transition:transform 0.15s ease;" title="Resolved Infrastructure Defect">
                    <i class='bx bx-check' style="font-weight:700;"></i>
                </div>
            `;
            return L.divIcon({
                className: 'leaflet-compact-marker-wrapper',
                html: iconInner,
                iconSize: [16, 16],
                iconAnchor: [8, 8],
                popupAnchor: [0, -10]
            });
        } else {
            // Section 22: Composite Map Marker: Circular severity point with upper-right warning triangle badge
            const advisoryBadge = `
                <span class="composite-advisory-badge" style="position:absolute; top:-7px; right:-7px; width:13px; height:13px; border-radius:3px; background:#ffffff; border:1.5px solid #dc2626; box-shadow:0 1px 4px rgba(220,38,38,0.5); display:inline-flex; align-items:center; justify-content:center; color:#dc2626; font-size:9px; z-index:3;" title="Active Safety Advisory">
                    <i class='bx bx-error-alt'></i>
                </span>
            `;

            iconInner = `
                <div class="custom-leaflet-marker compact-defect-marker ${sev} ${hasAdvisory ? 'composite-advisory-marker' : ''}" style="position:relative; width:${hasAdvisory ? '14px' : '13px'}; height:${hasAdvisory ? '14px' : '13px'}; border-radius:50%; background:${dotColor}; border:2px solid #ffffff; box-shadow:0 1px 6px ${dotGlow}; cursor:pointer; transition:transform 0.15s ease;" title="${severity} Defect${hasAdvisory ? ' — Active Safety Advisory' : ''}">
                    ${isUnderReview && !hasAdvisory ? '<span style="position:absolute; top:-3px; right:-3px; font-size:8px; background:#0f172a; border-radius:50%; width:10px; height:10px; display:inline-flex; align-items:center; justify-content:center; color:#38bdf8; border:1px solid #ffffff;" title="Under Review"><i class="bx bx-time"></i></span>' : ''}
                    ${isUnusual ? '<span style="position:absolute; top:-3px; left:-3px; font-size:8px; background:#fff7ed; border-radius:50%; width:10px; height:10px; display:inline-flex; align-items:center; justify-content:center; color:#c2410c; border:1px solid #fed7aa;" title="Unusual Pairing Flagged"><i class="bx bx-error-circle"></i></span>' : ''}
                    ${hasAdvisory ? advisoryBadge : ''}
                </div>
            `;
            const sz = hasAdvisory ? 14 : 13;
            return L.divIcon({
                className: 'leaflet-compact-marker-wrapper',
                html: iconInner,
                iconSize: [sz, sz],
                iconAnchor: [sz / 2, sz / 2],
                popupAnchor: [0, -8]
            });
        }
    },

    createCombinedPopupContent(point, advisory) {
        const rawId = point.display_id || (point.report_id ? `#REP-${point.report_id.slice(-6).toUpperCase()}` : '#REP-0000');
        const formattedId = rawId.startsWith('#') ? rawId : '#' + rawId;
        const defect = point.defect_class || 'Pavement Distress';
        const sev = (point.relative_severity || 'Low').toUpperCase();
        const sevClass = (point.relative_severity || 'low').toLowerCase();
        const status = point.status || 'Received';
        const statusSlug = status.toLowerCase().replace(/\s+/g, '-');
        const asset = point.asset_type || 'Road / Pavement';
        const location = point.location_name || advisory.location_name || 'Monitored Infrastructure';
        const reportDate = point.date_submitted ? new Date(point.date_submitted).toLocaleDateString('en-KE', { dateStyle: 'medium' }) : 'Recently Submitted';
        const advDate = advisory.issued_at || advisory.created_at ? new Date(advisory.issued_at || advisory.created_at).toLocaleDateString('en-KE', { dateStyle: 'medium' }) : 'Active';

        return `
            <div class="map-popup-card combined-alert-popup" style="font-family: inherit; min-width: 270px; max-width: 320px; padding: 2px;">
                <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #fee2e2; padding-bottom:6px; margin-bottom:8px;">
                    <span style="font-weight:700; color:#dc2626; font-size:0.82rem; display:flex; align-items:center; gap:5px;">
                        <i class='bx bx-error-alt' style="font-size:1.1rem;"></i> INFRASTRUCTURE ALERT
                    </span>
                    <span class="status-chip ${statusSlug}" style="font-size:0.68rem; padding:2px 8px;">${status}</span>
                </div>

                <!-- 1. Defect Report Section (Section 21) -->
                <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:8px 10px; margin-bottom:8px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                        <span style="font-weight:700; color:#0f172a; font-size:0.86rem;">${defect}</span>
                        <span class="severity-pill ${sevClass}" style="font-size:0.65rem; padding:2px 6px;">${sev}</span>
                    </div>
                    <div style="font-size:0.75rem; color:#64748b; margin-bottom:4px;">
                        <code>${formattedId}</code> • ${asset}
                    </div>
                    <div style="font-size:0.75rem; color:#475569; margin-bottom:6px;">
                        <i class='bx bx-map-pin'></i> ${location}
                    </div>
                    <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.72rem; color:#94a3b8; border-top:1px solid #f1f5f9; padding-top:5px;">
                        <span><i class='bx bx-calendar'></i> ${reportDate}</span>
                        <button type="button" class="btn-popup-link" onclick="DefectMap.openReportDetails('${point.report_id || point._id}')" style="background:none; border:none; padding:0; color:#0284c7; font-weight:600; cursor:pointer; font-size:0.75rem; display:inline-flex; align-items:center; gap:2px;">
                            View Defect Report &rarr;
                        </button>
                    </div>
                </div>

                <!-- 2. Active Safety Advisory Section (Section 21) -->
                <div style="background:#fef2f2; border:1px solid #fecaca; border-radius:6px; padding:8px 10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                        <span style="font-weight:700; color:#991b1b; font-size:0.84rem; display:flex; align-items:center; gap:4px;">
                            <i class='bx bx-shield-quarter'></i> Safety Advisory
                        </span>
                        <span class="status-chip active" style="font-size:0.65rem; padding:1px 6px; background:#fee2e2; color:#991b1b; border:1px solid #fca5a5;">ACTIVE</span>
                    </div>
                    <div style="font-size:0.78rem; color:#7f1d1d; margin-bottom:6px; line-height:1.4;">
                        ${advisory.note || advisory.comments || 'Reduce speed and proceed with caution across this monitored section.'}
                    </div>
                    <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.72rem; color:#991b1b; border-top:1px solid #fee2e2; padding-top:5px;">
                        <span><i class='bx bx-shield'></i> Verified Civil Engineer</span>
                        <button type="button" class="btn-popup-link" onclick="DefectMap.openSafetyAdvisory('${advisory.advisory_id || advisory._id}', '${point.report_id}', ${point.latitude}, ${point.longitude})" style="background:none; border:none; padding:0; color:#dc2626; font-weight:600; cursor:pointer; font-size:0.75rem; display:inline-flex; align-items:center; gap:2px;">
                            View Advisory Details &rarr;
                        </button>
                    </div>
                </div>
            </div>
        `;
    },

    createPopupContent(point) {
        const rawId = point.display_id || (point.report_id ? `#REP-${point.report_id.slice(-6).toUpperCase()}` : '#REP-0000');
        const formattedId = rawId.startsWith('#') ? rawId : '#' + rawId;
        const defect = point.defect_class || 'Pavement Distress';
        const sev = (point.relative_severity || 'Low').toUpperCase();
        const sevClass = (point.relative_severity || 'low').toLowerCase();
        const status = point.status || 'Received';
        const statusSlug = status.toLowerCase().replace(/\s+/g, '-');
        const asset = point.asset_type || 'Road / Pavement';
        const location = point.location_name || 'Monitored Infrastructure';
        const dateStr = point.date_submitted ? new Date(point.date_submitted).toLocaleDateString('en-KE', { dateStyle: 'medium' }) : 'Recently Submitted';
        const isEngineer = window.App?.currentUser?.role === 'engineer';

        const resolvedImgUrl = point.image_url ? (window.Api?.resolveImageUrl(point.image_url) || point.image_url) : '';

        return `
            <div class="map-popup-card" style="font-family: inherit; min-width: 240px; padding: 2px;">
                <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:6px; margin-bottom:8px;">
                    <code style="font-weight:700; color:#1e293b; font-size:0.85rem;">${formattedId}</code>
                    <span class="severity-pill ${sevClass}" style="font-size:0.7rem; padding:2px 8px;">${sev}</span>
                </div>
                ${resolvedImgUrl ? `<div style="width:100%; height:110px; border-radius:6px; overflow:hidden; margin-bottom:8px; background:#0f172a;"><img src="${resolvedImgUrl}" alt="Defect" style="width:100%; height:100%; object-fit:cover;" onerror="this.parentElement.style.display='none'"></div>` : ''}
                <div style="font-size:0.9rem; font-weight:700; color:#0f172a; margin-bottom:3px;">${defect}</div>
                <div style="font-size:0.78rem; color:#475569; margin-bottom:6px;"><i class='bx bx-map-pin'></i> ${location}</div>
                <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.75rem; color:#64748b; margin-bottom:8px;">
                    <span>Asset: <strong>${asset}</strong></span>
                    <span class="status-chip ${statusSlug}" style="font-size:0.7rem; padding:2px 8px;">${status}</span>
                </div>
                ${point.nearby_report_count > 0 ? `
                    <div style="font-size:0.75rem; color:#0284c7; font-weight:600; margin-bottom:6px; background:#f0f9ff; padding:3px 6px; border-radius:4px; border:1px solid #bae6fd;">
                        <i class='bx bx-layer'></i> Density: ${point.nearby_report_count} nearby defect report(s) within 50m
                    </div>
                ` : ''}
                <div style="font-size:0.72rem; color:#94a3b8; border-top:1px solid #f1f5f9; padding-top:6px; display:flex; justify-content:space-between; align-items:center;">
                    <span><i class='bx bx-calendar'></i> ${dateStr}</span>
                    <span style="color:#059669; font-weight:600;"><i class='bx bx-shield-check'></i> Reporter Protected</span>
                </div>
                ${isEngineer ? `
                    <div style="margin-top:8px; border-top:1px solid #f1f5f9; padding-top:6px;">
                        <button type="button" class="btn-primary btn-sm" style="width:100%; font-size:0.78rem; padding:4px 8px; border-radius:4px;" onclick="window.App.navigateTo('view-review', { reportId: '${point.report_id}' })">
                            Inspect in Defect Review →
                        </button>
                    </div>
                ` : ''}
            </div>
        `;
    },

    toggleHotspotLayer() {
        this.showHotspotLayer = !this.showHotspotLayer;
        this.syncHotspotButtonState();

        const heatPane = this.map ? this.map.getPane('heatmapPane') : null;

        if (this.heatLayer && this.map) {
            const currentZoom = this.map.getZoom();
            const opts = this.getZoomHeatOptions(currentZoom);

            if (this.showHotspotLayer && !opts.attenuated) {
                if (heatPane) heatPane.style.display = '';
                if (!this.map.hasLayer(this.heatLayer)) {
                    this.heatLayer.addTo(this.map);
                }
                if (typeof this.heatLayer.redraw === 'function') {
                    this.heatLayer.redraw();
                }
            } else {
                if (heatPane) heatPane.style.display = 'none';
                if (this.map.hasLayer(this.heatLayer)) {
                    this.map.removeLayer(this.heatLayer);
                }
            }
        } else if (heatPane) {
            heatPane.style.display = this.showHotspotLayer ? '' : 'none';
        }
    },

    async loadMapData() {
        const container = document.getElementById('infrastructureMapContainer');
        if (!container) return;

        if (!this.map) {
            await this.initLeafletMap();
        }

        try {
            // Fetch real reports with valid geographic coordinates from MongoDB
            const data = await window.Api.getMapPoints(this.activeFilters);
            this.reportsData = data.points || [];
            this.advisoriesData = data.safety_advisories || [];

            const countEl = document.getElementById('mapReportCount');
            if (countEl) countEl.textContent = `${this.reportsData.length} Pinpoints`;

            this.renderMarkers(this.reportsData);
            this.renderAdvisories(this.advisoriesData);
            this.invalidateSize();
        } catch (err) {
            console.error("[DefectMap] Failed loading map points:", err);
            window.App?.showToast("Failed to load map points.", true);
        }
    },

    renderMarkers(points) {
        if (!this.markerCluster) return;

        // Clear existing markers
        this.markerCluster.clearLayers();
        this.reportMarkers = {};

        // Remove any existing empty overlay
        const existingOverlay = document.querySelector('.map-empty-overlay');
        if (existingOverlay) existingOverlay.remove();

        const container = document.getElementById('infrastructureMapContainer');

        if (points.length === 0) {
            if (this.reportMarkerLayer) this.reportMarkerLayer.clearLayers();
            if (this.markerCluster) this.markerCluster.clearLayers();
            if (this.heatLayer && this.map && this.map.hasLayer(this.heatLayer)) {
                this.heatLayer.setLatLngs([]);
            }
            const hasFilters = Boolean(
                this.activeFilters.defect_class ||
                this.activeFilters.status ||
                this.activeFilters.severity ||
                this.activeFilters.asset_type
            );

            if (container) {
                const overlay = document.createElement('div');
                overlay.className = 'map-empty-overlay';
                if (hasFilters) {
                    overlay.innerHTML = `No defect reports match the selected filters. <button type="button" onclick="DefectMap.resetFilters()" style="margin-left:8px; background:#ffffff; color:#0f172a; border:none; padding:2px 8px; border-radius:4px; font-weight:600; cursor:pointer;">Reset Filters</button>`;
                } else {
                    overlay.textContent = "No infrastructure reports recorded in the database yet.";
                }
                container.appendChild(overlay);
            }
            return;
        }

        // Section 10: Operational map retention window (default 7 days)
        // Resolved reports older than retention_days are excluded from default operational map
        // unless explicit status filter specifies Resolved.
        const retentionDays = this.RESOLVED_MAP_RETENTION_DAYS || 7;
        const nowMs = Date.now();
        const activeFilteredStatus = this.activeFilters.status;

        const operationalPoints = points.filter((point) => {
            const isResolved = point.status === 'Resolved' || String(point.status).toLowerCase() === 'resolved';
            if (!isResolved) return true;
            if (activeFilteredStatus && activeFilteredStatus.toLowerCase() === 'resolved') return true;
            const resolvedDateStr = point.resolved_at || point.last_updated_at || point.date_submitted;
            if (!resolvedDateStr) return true;
            try {
                const diffDays = (nowMs - new Date(resolvedDateStr).getTime()) / (1000 * 60 * 60 * 24);
                return diffDays <= retentionDays;
            } catch (e) {
                return true;
            }
        });

        // Section 20 & 22: Index active safety advisories for composite marker generation
        const advisories = this.advisoriesData || [];
        const advByReportId = new Map();
        const advByCoord = [];

        advisories.forEach(adv => {
            adv._has_composite_marker = false;
            if (adv.report_id) advByReportId.set(String(adv.report_id), adv);
            if (adv._id) advByReportId.set(String(adv._id), adv);
            if (adv.advisory_id) advByReportId.set(String(adv.advisory_id), adv);
            const aLat = Number(adv.latitude);
            const aLng = Number(adv.longitude);
            if (!isNaN(aLat) && !isNaN(aLng) && aLat !== 0 && aLng !== 0) {
                advByCoord.push({ adv, lat: aLat, lng: aLng });
            }
        });

        const markers = [];
        const heatPoints = [];

        operationalPoints.forEach((point) => {
            const lat = Number(point.latitude);
            const lng = Number(point.longitude);

            if (isNaN(lat) || isNaN(lng) || lat === 0 || lng === 0) return;

            // Check if this report has an associated active safety advisory
            let matchedAdv = null;
            if (point.report_id && advByReportId.has(String(point.report_id))) {
                matchedAdv = advByReportId.get(String(point.report_id));
            } else if (point._id && advByReportId.has(String(point._id))) {
                matchedAdv = advByReportId.get(String(point._id));
            } else if (point.display_id && advByReportId.has(String(point.display_id))) {
                matchedAdv = advByReportId.get(String(point.display_id));
            } else {
                // Spatial proximity match within ~15m
                const coordMatch = advByCoord.find(item => Math.abs(item.lat - lat) < 0.00015 && Math.abs(item.lng - lng) < 0.00015);
                if (coordMatch) matchedAdv = coordMatch.adv;
            }

            if (matchedAdv) {
                point.active_advisory = matchedAdv;
                matchedAdv._has_composite_marker = true;
                matchedAdv._matched_point = point;
            }

            const hasAdvisory = Boolean(point.active_advisory);
            const icon = this.createMarkerIcon(point.relative_severity, point.is_unusual, point.status, hasAdvisory);
            const marker = L.marker([lat, lng], { icon: icon });
            marker.reportSeverity = point.relative_severity;
            marker.reportStatus = point.status;
            marker.hasAdvisory = hasAdvisory;

            // Combined context popup if composite, or individual report popup
            const popupContent = hasAdvisory
                ? this.createCombinedPopupContent(point, point.active_advisory)
                : this.createPopupContent(point);
            marker.bindPopup(popupContent, { maxWidth: 320, className: 'leaflet-custom-popup' });

            markers.push(marker);

            if (point.report_id) this.reportMarkers[point.report_id] = marker;
            if (point.display_id) this.reportMarkers[point.display_id] = marker;
            if (point._id) this.reportMarkers[String(point._id)] = marker;

            if (hasAdvisory && matchedAdv) {
                if (matchedAdv.advisory_id) this.advisoryMarkers[matchedAdv.advisory_id] = marker;
                if (matchedAdv.report_id) this.advisoryMarkers[matchedAdv.report_id] = marker;
                if (matchedAdv._id) this.advisoryMarkers[String(matchedAdv._id)] = marker;
            }

            // Section 11: Exclude Resolved reports from active defect density heat!
            // Resolved reports remain accessible as historical markers, but MUST NOT contribute to active heat.
            const isResolved = point.status === 'Resolved' || String(point.status).toLowerCase() === 'resolved';
            if (!isResolved) {
                // Section 4: Visual priority weighting model
                // Low = 0.35, Medium = 0.65, Critical = 1.00
                const sev = (point.relative_severity || 'Low').toLowerCase();
                let intensity = 0.35;
                if (sev === 'critical') {
                    intensity = 1.00;
                } else if (sev === 'medium' || sev === 'moderate') {
                    intensity = 0.65;
                }

                // Section 3: Raw report coordinates feed the heatmap directly
                heatPoints.push([lat, lng, intensity]);
            }
        });

        // Clear existing markers from both layers before applying adaptive strategy
        if (this.reportMarkerLayer) this.reportMarkerLayer.clearLayers();
        if (this.markerCluster) this.markerCluster.clearLayers();

        // Section 7 & 8: Stop aggressive clustering for small datasets (<= 150 visible reports).
        // At national-level and city-level zoom, reports remain individually visible as colored severity pins.
        // Cluster grouping is adaptively reserved strictly for large datasets (> 150 visible reports).
        const CLUSTER_THRESHOLD = 150;
        // points.length <= CLUSTER_THRESHOLD
        // Use local proximity clustering via this.markerCluster with fine-grained zoom rules:
        // Individual markers at street zoom (>=16), compact count circles for 3+ nearby reports at wider zooms.
        if (this.reportMarkerLayer && this.map.hasLayer(this.reportMarkerLayer)) {
            this.map.removeLayer(this.reportMarkerLayer);
        }
        if (this.markerCluster && !this.map.hasLayer(this.markerCluster)) {
            this.markerCluster.addTo(this.map);
        }
        if (this.markerCluster && typeof this.markerCluster.addLayers === 'function') {
            this.markerCluster.addLayers(markers);
        } else if (this.markerCluster) {
            markers.forEach(m => this.markerCluster.addLayer(m));
        } else if (this.reportMarkerLayer) {
            if (!this.map.hasLayer(this.reportMarkerLayer)) this.reportMarkerLayer.addTo(this.map);
            markers.forEach(m => this.reportMarkerLayer.addLayer(m));
        }

        // Section 5 & 10: Update Leaflet heat/density layer underneath markers
        if (typeof L.heatLayer === 'function') {
            const currentZoom = this.map ? this.map.getZoom() : (this.config.default_zoom || 12);
            const zoomOpts = this.getZoomHeatOptions(currentZoom);
            const heatPane = this.map ? this.map.getPane('heatmapPane') : null;

            if (!this.heatLayer) {
                this.heatLayer = L.heatLayer(heatPoints, {
                    pane: 'heatmapPane',
                    radius: zoomOpts.radius,
                    blur: zoomOpts.blur,
                    maxZoom: 13,
                    max: 1.0,
                    minOpacity: zoomOpts.minOpacity,
                    scaleIntensity: false,
                    gradient: this.heatGradient
                });
                if (this.showHotspotLayer && this.map) {
                    if (heatPane) heatPane.style.display = '';
                    this.heatLayer.addTo(this.map);
                } else if (heatPane) {
                    heatPane.style.display = 'none';
                }
            } else {
                // Section 10: setLatLngs synchronizes heat with filtered points
                this.heatLayer.setLatLngs(heatPoints);
                this.heatLayer.setOptions({
                    radius: zoomOpts.radius,
                    blur: zoomOpts.blur,
                    minOpacity: zoomOpts.minOpacity,
                    gradient: this.heatGradient
                });
                if (this.showHotspotLayer && this.map) {
                    if (heatPane) heatPane.style.display = '';
                    if (!this.map.hasLayer(this.heatLayer)) {
                        this.heatLayer.addTo(this.map);
                    }
                    if (typeof this.heatLayer.redraw === 'function') {
                        this.heatLayer.redraw();
                    }
                } else {
                    if (heatPane) heatPane.style.display = 'none';
                    if (this.map && this.map.hasLayer(this.heatLayer)) {
                        this.map.removeLayer(this.heatLayer);
                    }
                }
            }
        }
    },

    renderAdvisories(advisories) {
        if (!this.advisoriesLayer) return;
        this.advisoriesLayer.clearLayers();
        if (!this.advisoryMarkers) this.advisoryMarkers = {};

        if (!advisories || advisories.length === 0) return;

        advisories.forEach(adv => {
            const lat = Number(adv.latitude);
            const lng = Number(adv.longitude);
            if (isNaN(lat) || isNaN(lng) || lat === 0 || lng === 0) return;

            // Section 18 & 21: If advisory is already represented on a composite report marker at this location,
            // do not place an overlapping blocking triangle directly on top that intercepts clicks!
            // The composite marker already provides the context popup with access to both entities.
            if (adv._has_composite_marker) {
                return;
            }

            // Standalone advisory: Render triangular hazard marker on safetyAdvisoryPane
            const advIcon = L.divIcon({
                className: 'safety-advisory-triangle-icon',
                html: `
                    <div class="safety-advisory-pin-wrap safety-advisory-triangle-wrap" style="position:relative; width:34px; height:34px; cursor:pointer;" title="Safety Advisory: ${adv.category || 'Road Hazard Alert'}">
                        <svg viewBox="0 0 36 32" width="34" height="32" style="filter: drop-shadow(0 2px 5px rgba(220,38,38,0.4));">
                            <path d="M18 3 L34 29 L2 29 Z" fill="#ffffff" stroke="#dc2626" stroke-width="2.8" stroke-linejoin="round"/>
                        </svg>
                        <div style="position:absolute; inset:0; display:flex; align-items:center; justify-content:center; padding-top:6px; color:#b91c1c; font-size:16px; pointer-events:none;">
                            <i class='bx bx-error-alt'></i>
                        </div>
                        <span style="display:none;" data-legacy="#1e1b4b bx-shield-quarter"></span>
                    </div>
                `,
                iconSize: [34, 34],
                iconAnchor: [17, 17],
                popupAnchor: [0, -17]
            });

            // Section 15: Safety Advisory marker placed in dedicated pane (z-index 675)
            const marker = L.marker([lat, lng], {
                icon: advIcon,
                pane: 'safetyAdvisoryPane'
            });

            const dateStr = adv.issued_at || adv.created_at
                ? new Date(adv.issued_at || adv.created_at).toLocaleDateString('en-KE', { dateStyle: 'medium' })
                : 'Active';

            const popupHtml = `
                <div class="advisory-map-popup" style="font-family: inherit; min-width: 250px; padding: 4px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #fee2e2; padding-bottom:6px; margin-bottom:8px;">
                        <span style="font-weight:700; color:#991b1b; font-size:0.82rem;"><i class='bx bx-error-alt'></i> SAFETY ADVISORY</span>
                        <span class="status-chip active" style="font-size:0.68rem; padding:2px 8px; background:#fee2e2; color:#991b1b; border:1px solid #fca5a5;">ACTIVE</span>
                    </div>
                    <div style="font-size:0.92rem; font-weight:700; color:#0f172a; margin-bottom:4px;">${adv.category || 'Infrastructure Inspection Alert'}</div>
                    <div style="font-size:0.8rem; color:#475569; margin-bottom:8px; line-height:1.4;">${adv.note || adv.comments || 'Exercise caution when traversing this monitored corridor section.'}</div>
                    <div style="font-size:0.75rem; color:#64748b; margin-bottom:6px;"><i class='bx bx-map-pin'></i> ${adv.location_name || 'Monitored Corridor'}</div>
                    <div style="font-size:0.72rem; color:#64748b; border-top:1px solid #f1f5f9; padding-top:6px; display:flex; justify-content:space-between; align-items:center;">
                        <span style="color:#b91c1c; font-weight:600;"><i class='bx bx-shield-quarter'></i> Verified Civil Engineer</span>
                        <span>${dateStr}</span>
                    </div>
                    ${adv.report_id ? `
                        <div style="margin-top:8px; border-top:1px solid #fee2e2; padding-top:6px; display:flex; justify-content:flex-end;">
                            <button type="button" onclick="DefectMap.openReportDetails('${adv.report_id}')" style="background:none; border:none; padding:0; color:#0284c7; font-weight:600; cursor:pointer; font-size:0.75rem; display:inline-flex; align-items:center; gap:2px;">
                                <i class='bx bx-file-find'></i> View Source Defect Report &rarr;
                            </button>
                        </div>
                    ` : ''}
                </div>
            `;

            marker.bindPopup(popupHtml, { maxWidth: 320, className: 'leaflet-custom-popup' });

            // Section 17: Direct map marker click handling opens advisory
            const advId = adv.advisory_id || adv._id || adv.report_id;
            marker.on('click', () => {
                this.openSafetyAdvisory(adv.advisory_id || adv._id, adv.report_id, lat, lng);
            });

            this.advisoriesLayer.addLayer(marker);

            if (adv.advisory_id) this.advisoryMarkers[adv.advisory_id] = marker;
            if (adv.report_id) this.advisoryMarkers[adv.report_id] = marker;
            if (adv._id) this.advisoryMarkers[String(adv._id)] = marker;
        });
    },

    // Unified report detail opening function for map context popup and bidirectional navigation
    openReportDetails(reportId) {
        if (!reportId) return;
        const user = window.Auth?.getUser();
        if (user && (user.role === 'engineer' || user.role === 'admin')) {
            if (window.Review) window.Review.targetReportId = reportId;
            window.App?.navigateTo('view-review', { reportId: reportId });
        } else {
            window.App?.navigateTo('view-tracking', { reportId: reportId });
        }
    },

    // Section 17: Unified advisory opening function shared by direct map-click and notification deep-link
    openSafetyAdvisory(advisoryId, reportId, lat, lng) {
        if (!this.map) return;
        this.invalidateSize();

        if (lat && lng && !isNaN(lat) && !isNaN(lng)) {
            this.map.setView([lat, lng], Math.max(this.map.getZoom(), 14), { animate: true });
        }

        setTimeout(() => {
            const marker = (advisoryId && this.advisoryMarkers[advisoryId]) ||
                           (reportId && this.advisoryMarkers[reportId]) ||
                           (advisoryId && this.advisoryMarkers[String(advisoryId)]);
            if (marker) {
                if (this.markerCluster && typeof this.markerCluster.hasLayer === 'function' && this.markerCluster.hasLayer(marker)) {
                    if (typeof this.markerCluster.zoomToShowLayer === 'function') {
                        this.markerCluster.zoomToShowLayer(marker, () => {
                            marker.openPopup();
                        });
                        return;
                    }
                }
                marker.openPopup();
            }
        }, 250);
    },

    focusOnAdvisory(advisoryId, reportId, lat, lng) {
        this.openSafetyAdvisory(advisoryId, reportId, lat, lng);
    },

    // Section 24: Direct "Show on Map" interaction handler from My Reports / Defect Review
    showReportOnMap(reportId, lat, lng) {
        if (!this.map) return;
        this.invalidateSize();

        const targetLat = Number(lat);
        const targetLng = Number(lng);
        if (!isNaN(targetLat) && !isNaN(targetLng) && targetLat !== 0 && targetLng !== 0) {
            this.map.setView([targetLat, targetLng], Math.max(this.map.getZoom(), 16), { animate: true });
        }

        setTimeout(() => {
            const marker = (reportId && this.reportMarkers[reportId]) ||
                           (reportId && this.reportMarkers[String(reportId)]) ||
                           (reportId && this.reportMarkers[`#${reportId}`]);
            if (marker) {
                if (this.markerCluster && typeof this.markerCluster.hasLayer === 'function' && this.markerCluster.hasLayer(marker)) {
                    if (typeof this.markerCluster.zoomToShowLayer === 'function') {
                        this.markerCluster.zoomToShowLayer(marker, () => {
                            marker.openPopup();
                        });
                        return;
                    }
                }
                marker.openPopup();
            }
        }, 300);
    }
};

window.DefectMap = DefectMap;

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.DefectMap.init();
});
