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
    tileLayer: null,
    reportsData: [],
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
    showHotspotLayer: true,
    heatGradient: {
        0.30: '#10b981', // Clean low-density green
        0.55: '#f59e0b', // Moderate yellow/amber
        0.75: '#ea580c', // Higher orange
        0.90: '#ef4444', // Concentrated core red
        1.00: '#991b1b'  // Peak hotspot crimson
    },

    getZoomHeatOptions(zoom) {
        // Zoom-aware radius, blur, and opacity scaling.
        // Prevents country-scale ballooning and city-scale foggy halos.
        if (zoom <= 7) {
            // Far / country scale: strongly attenuated to prevent misleading nationwide clouds
            return { radius: 10, blur: 8, minOpacity: 0.05, attenuated: true };
        } else if (zoom <= 10) {
            // Regional / greater Nairobi view
            return { radius: 14, blur: 10, minOpacity: 0.10, attenuated: false };
        } else if (zoom <= 13) {
            // City / Nairobi default scale (zoom 11-13) - crisp point concentration, visible roads
            return { radius: 18, blur: 12, minOpacity: 0.18, attenuated: false };
        } else {
            // Street / neighbourhood scale (zoom >= 14)
            return { radius: 26, blur: 16, minOpacity: 0.22, attenuated: false };
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

        // Low-zoom attenuation: below analytical threshold (<= 7),
        // remove heat layer from map so Nairobi does not cover all of Kenya,
        // and restore automatically when zooming back in.
        if (this.showHotspotLayer) {
            if (opts.attenuated) {
                if (heatPane) heatPane.style.display = 'none';
                if (this.map.hasLayer(this.heatLayer)) {
                    this.map.removeLayer(this.heatLayer);
                }
            } else {
                if (heatPane) heatPane.style.display = '';
                if (!this.map.hasLayer(this.heatLayer)) {
                    this.heatLayer.addTo(this.map);
                }
                if (typeof this.heatLayer.redraw === 'function') {
                    this.heatLayer.redraw();
                }
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
                btn.innerHTML = '🔥 Hide Hotspots';
                btn.setAttribute('aria-pressed', 'true');
                btn.title = 'Hide defect density hotspot surface';
            } else {
                btn.classList.remove('active-hotspot');
                btn.innerHTML = '🔥 Show Hotspots';
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

            // Sync initial hotspot button and legend state
            this.syncHotspotButtonState();

            // Zoom-aware dynamic heatmap adaptation
            this.map.on('zoomend', () => {
                this.updateZoomAwareHeatmap();
            });

            // Initialize marker cluster group with severity-aware visual treatment
            if (typeof L.markerClusterGroup === 'function') {
                this.markerCluster = L.markerClusterGroup({
                    chunkedLoading: true,
                    maxClusterRadius: 40,
                    spiderfyOnMaxZoom: true,
                    showCoverageOnHover: false,
                    zoomToBoundsOnClick: true,
                    iconCreateFunction: (cluster) => {
                        const childMarkers = cluster.getAllChildMarkers();
                        const count = childMarkers.length;

                        // Severity composition weighting: Low = 1, Medium = 2, Critical = 3
                        // cluster_severity_score = sum(report severity weights) / number of reports
                        let sumWeights = 0;
                        for (const m of childMarkers) {
                            const sev = (m.reportSeverity || m.options?.severity || 'Low').toLowerCase();
                            if (sev === 'critical') {
                                sumWeights += 3;
                            } else if (sev === 'medium' || sev === 'moderate') {
                                sumWeights += 2;
                            } else {
                                sumWeights += 1;
                            }
                        }

                        const score = count > 0 ? (sumWeights / count) : 1.0;

                        // Presentation bands:
                        // 1.00 – 1.49 -> Green
                        // 1.50 – 2.24 -> Amber
                        // 2.25 – 3.00 -> Red
                        let innerColor = '#10b981'; // Green: Low priority composition
                        let ringColor = 'rgba(16, 185, 129, 0.25)';
                        let shadowColor = 'rgba(16, 185, 129, 0.4)';

                        if (score >= 2.25) {
                            innerColor = '#ef4444'; // Red: Critical density composition
                            ringColor = 'rgba(239, 68, 68, 0.25)';
                            shadowColor = 'rgba(239, 68, 68, 0.45)';
                        } else if (score >= 1.50) {
                            innerColor = '#f59e0b'; // Amber: Medium priority composition
                            ringColor = 'rgba(245, 158, 11, 0.25)';
                            shadowColor = 'rgba(245, 158, 11, 0.45)';
                        }

                        return L.divIcon({
                            html: `
                                <div style="width:42px; height:42px; border-radius:50%; background-color:${ringColor}; display:flex; align-items:center; justify-content:center; transition:transform 0.15s ease;" title="Cluster Severity Score: ${score.toFixed(2)} (${count} reports)">
                                    <div style="width:32px; height:32px; border-radius:50%; background-color:${innerColor}; color:#ffffff; font-family:var(--font-sans, system-ui, -apple-system, sans-serif); font-weight:700; font-size:13px; display:flex; align-items:center; justify-content:center; box-shadow:0 2px 6px ${shadowColor};">
                                        ${count}
                                    </div>
                                </div>
                            `,
                            className: 'custom-severity-cluster-icon',
                            iconSize: L.point(42, 42)
                        });
                    }
                });
                this.map.addLayer(this.markerCluster);
            } else {
                console.warn("[DefectMap] Leaflet.markercluster not found. Falling back to standard LayerGroup.");
                this.markerCluster = L.layerGroup().addTo(this.map);
            }

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

    createMarkerIcon(severity, isUnusual, status) {
        const isResolved = status === 'Resolved' || this.activeFilters.status === 'Resolved';
        const isUnderReview = status === 'Under Review';

        let pinColor = '#10b981'; // Low: Green
        if (severity === 'Critical') pinColor = '#ef4444'; // Critical: Red
        else if (severity === 'Medium') pinColor = '#f59e0b'; // Medium: Amber

        let iconInner = '';
        if (isResolved) {
            // Distinct resolved treatment: Green pin with crisp checkmark
            iconInner = `
                <div class="custom-leaflet-pin resolved-pin" style="position:relative; width:28px; height:36px; cursor:pointer;" title="Resolved Infrastructure Defect">
                    <svg viewBox="0 0 30 38" width="28" height="36" style="filter: drop-shadow(0 2px 5px rgba(16,185,129,0.5));">
                        <path d="M15 0C6.7 0 0 6.7 0 15c0 10.5 15 23 15 23s15-12.5 15-23c0-8.3-6.7-15-15-15z" fill="#059669"/>
                        <circle cx="15" cy="14" r="6" fill="#ffffff"/>
                        <path d="M12 14l2 2 4-4" fill="none" stroke="#059669" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </div>
            `;
        } else {
            iconInner = `
                <div class="custom-leaflet-pin" style="position:relative; width:28px; height:36px; cursor:pointer;">
                    <svg viewBox="0 0 30 38" width="28" height="36" style="filter: drop-shadow(0 2px 4px rgba(0,0,0,0.35));">
                        <path d="M15 0C6.7 0 0 6.7 0 15c0 10.5 15 23 15 23s15-12.5 15-23c0-8.3-6.7-15-15-15z" fill="${pinColor}"/>
                        <circle cx="15" cy="14" r="5.5" fill="#ffffff"/>
                    </svg>
                    ${isUnderReview ? '<span style="position:absolute; top:-3px; right:-4px; font-size:10px; background:#0f172a; border-radius:50%; padding:1px; line-height:1;" title="Under Review">🔍</span>' : ''}
                    ${isUnusual ? '<span style="position:absolute; top:-3px; right:-3px; font-size:11px;" title="Unusual Pairing Flagged">⚠️</span>' : ''}
                </div>
            `;
        }

        return L.divIcon({
            className: 'leaflet-pin-wrapper',
            html: iconInner,
            iconSize: [28, 36],
            iconAnchor: [14, 36],
            popupAnchor: [0, -34]
        });
    },

    createPopupContent(point) {
        const repId = point.report_id ? point.report_id.slice(-6).toUpperCase() : '0000';
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
                    <code style="font-weight:700; color:#1e293b; font-size:0.85rem;">#REP-${repId}</code>
                    <span class="severity-pill ${sevClass}" style="font-size:0.7rem; padding:2px 8px;">${sev}</span>
                </div>
                ${resolvedImgUrl ? `<div style="width:100%; height:110px; border-radius:6px; overflow:hidden; margin-bottom:8px; background:#0f172a;"><img src="${resolvedImgUrl}" alt="Defect" style="width:100%; height:100%; object-fit:cover;" onerror="this.parentElement.style.display='none'"></div>` : ''}
                <div style="font-size:0.9rem; font-weight:700; color:#0f172a; margin-bottom:3px;">${defect}</div>
                <div style="font-size:0.78rem; color:#475569; margin-bottom:6px;">📍 ${location}</div>
                <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.75rem; color:#64748b; margin-bottom:8px;">
                    <span>Asset: <strong>${asset}</strong></span>
                    <span class="status-chip ${statusSlug}" style="font-size:0.7rem; padding:2px 8px;">${status}</span>
                </div>
                ${point.nearby_report_count > 0 ? `
                    <div style="font-size:0.75rem; color:#0284c7; font-weight:600; margin-bottom:6px; background:#f0f9ff; padding:3px 6px; border-radius:4px; border:1px solid #bae6fd;">
                        📍 Density: ${point.nearby_report_count} nearby defect report(s) within 50m
                    </div>
                ` : ''}
                <div style="font-size:0.72rem; color:#94a3b8; border-top:1px solid #f1f5f9; padding-top:6px; display:flex; justify-content:space-between; align-items:center;">
                    <span>📅 ${dateStr}</span>
                    <span style="color:#059669; font-weight:600;">🔒 Reporter Protected</span>
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

            const countEl = document.getElementById('mapReportCount');
            if (countEl) countEl.textContent = `${this.reportsData.length} Pinpoints`;

            this.renderMarkers(this.reportsData);
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

        // Remove any existing empty overlay
        const existingOverlay = document.querySelector('.map-empty-overlay');
        if (existingOverlay) existingOverlay.remove();

        const container = document.getElementById('infrastructureMapContainer');

        if (points.length === 0) {
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

        const markers = [];
        const heatPoints = [];

        points.forEach((point) => {
            const lat = Number(point.latitude);
            const lng = Number(point.longitude);

            if (isNaN(lat) || isNaN(lng) || lat === 0 || lng === 0) return;

            const icon = this.createMarkerIcon(point.relative_severity, point.is_unusual, point.status);
            const marker = L.marker([lat, lng], { icon: icon });
            marker.reportSeverity = point.relative_severity;

            const popupContent = this.createPopupContent(point);
            marker.bindPopup(popupContent, { maxWidth: 300, className: 'leaflet-custom-popup' });

            markers.push(marker);

            // Defect Report Density / Monitoring Priority intensity mapping (Section 4):
            // Low      = 0.35
            // Medium   = 0.65
            // Critical = 1.00
            const sev = (point.relative_severity || 'Low').toLowerCase();
            let intensity = 0.35; // Low severity baseline
            if (sev === 'critical') {
                intensity = 1.00;
            } else if (sev === 'medium' || sev === 'moderate') {
                intensity = 0.65;
            }

            // Unresolved defects require active monitoring
            if (point.status && point.status !== 'Resolved') {
                intensity = Math.min(intensity + 0.05, 1.0);
            }

            heatPoints.push([lat, lng, intensity]);
        });

        if (typeof this.markerCluster.addLayers === 'function') {
            this.markerCluster.addLayers(markers);
        } else {
            markers.forEach(m => this.markerCluster.addLayer(m));
        }

        // Update or initialize Leaflet heat/density layer underneath clusters
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
                if (this.showHotspotLayer && !zoomOpts.attenuated && this.map) {
                    if (heatPane) heatPane.style.display = '';
                    this.heatLayer.addTo(this.map);
                } else if (heatPane) {
                    heatPane.style.display = 'none';
                }
            } else {
                this.heatLayer.setLatLngs(heatPoints);
                this.heatLayer.setOptions({
                    radius: zoomOpts.radius,
                    blur: zoomOpts.blur,
                    minOpacity: zoomOpts.minOpacity,
                    gradient: this.heatGradient
                });
                if (this.showHotspotLayer && !zoomOpts.attenuated && this.map) {
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
    }
};

window.DefectMap = DefectMap;

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.DefectMap.init();
});
