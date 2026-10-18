/**
 * InfraVision Map Module - Interactive Civil Infrastructure Defect Map & Hotspot Visualization
 * Supports Google Maps JS API with Advanced Markers/Clustering and an Interactive Fallback Canvas.
 * Adheres to role-based privacy (no citizen names/emails exposed).
 */
const DefectMap = {
    mapInstance: null,
    markers: [],
    reportsData: [],
    activeFilters: {
        defect_class: '',
        status: '',
        severity: '',
        asset_type: ''
    },

    init() {
        this.bindEvents();
    },

    bindEvents() {
        const classFilter = document.getElementById('mapFilterClass');
        const statusFilter = document.getElementById('mapFilterStatus');
        const severityFilter = document.getElementById('mapFilterSeverity');
        const assetFilter = document.getElementById('mapFilterAsset');
        const refreshBtn = document.getElementById('btnRefreshMap');

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
                window.App.showToast("Refreshed infrastructure map data.");
            });
        }
    },

    async loadMapData() {
        const container = document.getElementById('infrastructureMapContainer');
        if (!container) return;

        try {
            const data = await window.Api.getMapPoints(this.activeFilters);
            this.reportsData = data.points || [];

            const countEl = document.getElementById('mapReportCount');
            if (countEl) countEl.textContent = `${this.reportsData.length} Pinpoints`;

            if (window.google && window.google.maps) {
                this.renderGoogleMap(container, this.reportsData);
            } else {
                this.renderInteractiveCanvasMap(container, this.reportsData);
            }
        } catch (err) {
            console.error("Map data load error:", err);
            container.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#dc2626;">Failed to load infrastructure map points.</div>`;
        }
    },

    renderGoogleMap(container, points) {
        const center = points.length > 0
            ? { lat: points[0].latitude, lng: points[0].longitude }
            : { lat: -1.2921, lng: 36.8219 }; // Nairobi corridor center default

        if (!this.mapInstance) {
            this.mapInstance = new google.maps.Map(container, {
                zoom: 12,
                center: center,
                mapTypeId: 'roadmap',
                styles: [
                    { featureType: 'poi', stylers: [{ visibility: 'off' }] }
                ]
            });
        } else {
            this.mapInstance.setCenter(center);
        }

        // Clear existing markers
        this.markers.forEach(m => m.setMap(null));
        this.markers = [];

        const infoWindow = new google.maps.InfoWindow();

        points.forEach(pt => {
            const color = pt.relative_severity === 'Critical' ? '#ef4444' : (pt.relative_severity === 'Medium' ? '#f59e0b' : '#10b981');
            const marker = new google.maps.Marker({
                position: { lat: pt.latitude, lng: pt.longitude },
                map: this.mapInstance,
                title: `${pt.defect_class} (${pt.relative_severity})`,
                icon: {
                    path: google.maps.SymbolPath.CIRCLE,
                    scale: 9,
                    fillColor: color,
                    fillOpacity: 0.95,
                    strokeWeight: 2,
                    strokeColor: '#ffffff'
                }
            });

            marker.addListener('click', () => {
                const dateStr = pt.date_submitted ? new Date(pt.date_submitted).toLocaleDateString() : 'Recent';
                const statusSlug = (pt.status || 'Received').toLowerCase().replace(' ', '-');
                infoWindow.setContent(`
                    <div class="map-popup-card">
                        <div class="map-popup-title">${pt.defect_class || 'Infrastructure Defect'}</div>
                        <div class="map-popup-meta">${pt.asset_type || 'Road'} • ${pt.location_name || 'Corridor'}</div>
                        <div style="margin: 0.4rem 0;">
                            <span class="status-chip ${statusSlug}">${pt.status || 'Received'}</span>
                            <span class="severity-pill ${(pt.relative_severity || 'Low').toLowerCase()}">${(pt.relative_severity || 'Low').toUpperCase()}</span>
                        </div>
                        <div style="font-size:0.75rem; color:#6b7280; margin-top:0.35rem;">
                            Coordinates: ${pt.latitude.toFixed(4)}°, ${pt.longitude.toFixed(4)}°<br>
                            Date: ${dateStr}
                        </div>
                    </div>
                `);
                infoWindow.open(this.mapInstance, marker);
            });

            this.markers.push(marker);
        });
    },

    renderInteractiveCanvasMap(container, points) {
        // High quality vector fallback canvas with GPS normalization, clustering, and click popups
        container.innerHTML = `
            <div style="position: relative; width: 100%; height: 100%; background: #1e293b; overflow: hidden; border-radius: var(--radius-lg);">
                <div style="position: absolute; top: 12px; left: 16px; z-index: 10; background: rgba(15,23,42,0.85); backdrop-filter: blur(8px); padding: 6px 12px; border-radius: 980px; font-size: 0.75rem; color: #cbd5e1; border: 1px solid #334155;">
                    🌐 Infrastructure GIS Defect Hotspot Visualizer
                </div>
                <div style="position: absolute; top: 12px; right: 16px; z-index: 10; display: flex; gap: 6px;">
                    <button type="button" class="btn-micro" id="btnMapZoomIn" style="background:rgba(15,23,42,0.85); color:#fff; border-color:#334155;">+</button>
                    <button type="button" class="btn-micro" id="btnMapZoomOut" style="background:rgba(15,23,42,0.85); color:#fff; border-color:#334155;">-</button>
                </div>
                <canvas id="vectorMapCanvas" style="width: 100%; height: 100%; display: block; cursor: grab;"></canvas>
                <div id="vectorMapTooltip" style="position: absolute; display: none; background: #ffffff; border: 1px solid #e5e5ea; border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.18); z-index: 20; pointer-events: none; max-width: 260px;"></div>
            </div>
        `;

        const canvas = document.getElementById('vectorMapCanvas');
        const tooltip = document.getElementById('vectorMapTooltip');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const width = container.clientWidth || 800;
        const height = container.clientHeight || 580;
        canvas.width = width;
        canvas.height = height;

        // Bounding box of points
        let minLat = -1.35, maxLat = -1.25, minLng = 36.75, maxLng = 36.90;
        if (points.length > 0) {
            minLat = Math.min(...points.map(p => p.latitude)) - 0.02;
            maxLat = Math.max(...points.map(p => p.latitude)) + 0.02;
            minLng = Math.min(...points.map(p => p.longitude)) - 0.02;
            maxLng = Math.max(...points.map(p => p.longitude)) + 0.02;
        }

        const project = (lat, lng) => {
            const x = ((lng - minLng) / (maxLng - minLng)) * (width - 120) + 60;
            const y = height - (((lat - minLat) / (maxLat - minLat)) * (height - 120) + 60);
            return { x, y };
        };

        // Draw Map Canvas
        const draw = () => {
            ctx.clearRect(0, 0, width, height);

            // Background grid & corridor lines
            ctx.fillStyle = '#0f172a';
            ctx.fillRect(0, 0, width, height);

            ctx.strokeStyle = '#1e293b';
            ctx.lineWidth = 1;
            for (let x = 0; x < width; x += 40) {
                ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke();
            }
            for (let y = 0; y < height; y += 40) {
                ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke();
            }

            // Road corridor outlines
            ctx.strokeStyle = '#334155';
            ctx.lineWidth = 5;
            ctx.beginPath();
            ctx.moveTo(40, height * 0.7);
            ctx.quadraticCurveTo(width * 0.4, height * 0.4, width - 40, height * 0.3);
            ctx.stroke();

            ctx.beginPath();
            ctx.moveTo(width * 0.3, height - 20);
            ctx.lineTo(width * 0.65, 20);
            ctx.stroke();

            if (points.length === 0) {
                ctx.fillStyle = '#94a3b8';
                ctx.font = '14px "Montserrat", sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText("No infrastructure defect reports match the current filter criteria.", width / 2, height / 2);
                return;
            }

            // Draw defect pinpoint markers
            points.forEach(pt => {
                const pos = project(pt.latitude, pt.longitude);
                pt._screenPos = pos;

                const color = pt.relative_severity === 'Critical' ? '#ef4444' : (pt.relative_severity === 'Medium' ? '#f59e0b' : '#10b981');

                // Outer pulsing glow
                ctx.fillStyle = color;
                ctx.globalAlpha = 0.25;
                ctx.beginPath();
                ctx.arc(pos.x, pos.y, 14, 0, 2 * Math.PI);
                ctx.fill();

                // Core pin
                ctx.globalAlpha = 1.0;
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(pos.x, pos.y, 7, 0, 2 * Math.PI);
                ctx.fill();

                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 2;
                ctx.stroke();

                // Label tag
                ctx.fillStyle = '#f8fafc';
                ctx.font = 'bold 10px "Montserrat", sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText(pt.defect_class, pos.x, pos.y - 12);
            });
        };

        draw();

        // Canvas interactive hover tooltip
        canvas.onmousemove = (e) => {
            const rect = canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;

            let hovered = null;
            for (const pt of points) {
                if (pt._screenPos) {
                    const dist = Math.hypot(pt._screenPos.x - mouseX, pt._screenPos.y - mouseY);
                    if (dist <= 14) {
                        hovered = pt;
                        break;
                    }
                }
            }

            if (hovered && tooltip) {
                const dateStr = hovered.date_submitted ? new Date(hovered.date_submitted).toLocaleDateString() : 'Recent';
                const statusSlug = (hovered.status || 'Received').toLowerCase().replace(' ', '-');
                tooltip.style.display = 'block';
                tooltip.style.left = `${Math.min(width - 250, mouseX + 15)}px`;
                tooltip.style.top = `${Math.max(10, mouseY - 70)}px`;
                tooltip.innerHTML = `
                    <div style="padding: 10px 12px; font-family: 'Montserrat', sans-serif;">
                        <strong style="color:#0f172a; font-size: 0.85rem; display:block;">${hovered.defect_class}</strong>
                        <div style="font-size: 0.72rem; color: #64748b; margin-top: 2px;">${hovered.asset_type || 'Road'} • ${hovered.location_name || 'Corridor Asset'}</div>
                        <div style="margin-top: 6px; display: flex; gap: 4px;">
                            <span class="status-chip ${statusSlug}">${hovered.status || 'Received'}</span>
                            <span class="severity-pill ${(hovered.relative_severity || 'Low').toLowerCase()}">${(hovered.relative_severity || 'Low').toUpperCase()}</span>
                        </div>
                        <div style="font-size: 0.7rem; color: #94a3b8; margin-top: 6px;">
                            ${hovered.latitude.toFixed(4)}°, ${hovered.longitude.toFixed(4)}° • ${dateStr}
                        </div>
                    </div>
                `;
            } else if (tooltip) {
                tooltip.style.display = 'none';
            }
        };

        canvas.onmouseleave = () => {
            if (tooltip) tooltip.style.display = 'none';
        };

        const zoomInBtn = document.getElementById('btnMapZoomIn');
        const zoomOutBtn = document.getElementById('btnMapZoomOut');
        if (zoomInBtn) {
            zoomInBtn.onclick = () => {
                minLat += 0.005; maxLat -= 0.005;
                minLng += 0.005; maxLng -= 0.005;
                draw();
            };
        }
        if (zoomOutBtn) {
            zoomOutBtn.onclick = () => {
                minLat -= 0.005; maxLat += 0.005;
                minLng -= 0.005; maxLng += 0.005;
                draw();
            };
        }
    }
};

window.DefectMap = DefectMap;
