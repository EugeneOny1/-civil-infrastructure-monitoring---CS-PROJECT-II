/*
 (c) 2014, Vladimir Agafonkin
 simpleheat, a tiny JavaScript library for drawing heatmaps with Canvas
 https://github.com/mourner/simpleheat
 Refined for InfraVision: Custom panes, robust canvas resizing, non-zero dimensions guard.
*/
!function() {
    "use strict";

    function simpleheat(canvas) {
        if (!(this instanceof simpleheat)) return new simpleheat(canvas);
        this._canvas = canvas = typeof canvas === "string" ? document.getElementById(canvas) : canvas;
        this._ctx = canvas.getContext("2d");
        this._width = canvas.width;
        this._height = canvas.height;
        this._max = 1;
        this.clear();
    }

    simpleheat.prototype = {
        defaultRadius: 25,
        defaultGradient: {
            0.4: "blue",
            0.6: "cyan",
            0.7: "lime",
            0.8: "yellow",
            1.0: "red"
        },
        data: function(data) {
            this._data = data;
            return this;
        },
        max: function(max) {
            this._max = max;
            return this;
        },
        add: function(point) {
            this._data.push(point);
            return this;
        },
        clear: function() {
            this._data = [];
            return this;
        },
        radius: function(r, blur) {
            blur = blur === undefined ? 15 : blur;
            var circle = this._circle = document.createElement("canvas"),
                ctx = circle.getContext("2d"),
                radius = this._r = r + blur;
            circle.width = circle.height = 2 * radius;
            ctx.shadowOffsetX = ctx.shadowOffsetY = 200;
            ctx.shadowBlur = blur;
            ctx.shadowColor = "black";
            ctx.beginPath();
            ctx.arc(radius - 200, radius - 200, r, 0, 2 * Math.PI, true);
            ctx.closePath();
            ctx.fill();
            return this;
        },
        gradient: function(grad) {
            var canvas = document.createElement("canvas"),
                ctx = canvas.getContext("2d"),
                gradient = ctx.createLinearGradient(0, 0, 0, 256);
            canvas.width = 1;
            canvas.height = 256;
            for (var stop in grad) {
                gradient.addColorStop(stop, grad[stop]);
            }
            ctx.fillStyle = gradient;
            ctx.fillRect(0, 0, 1, 256);
            this._grad = ctx.getImageData(0, 0, 1, 256).data;
            return this;
        },
        draw: function(minOpacity) {
            if (!this._width || !this._height) return this;
            if (!this._circle) this.radius(this.defaultRadius);
            if (!this._grad) this.gradient(this.defaultGradient);

            var ctx = this._ctx;
            ctx.clearRect(0, 0, this._width, this._height);

            for (var i = 0, len = this._data.length; i < len; i++) {
                var p = this._data[i];
                ctx.globalAlpha = Math.min(Math.max(p[2] / this._max, minOpacity || 0.05), 1.0);
                ctx.drawImage(this._circle, p[0] - this._r, p[1] - this._r);
            }

            var img = ctx.getImageData(0, 0, this._width, this._height);
            this._colorize(img.data, this._grad);
            ctx.putImageData(img, 0, 0);
            return this;
        },
        _colorize: function(pixels, gradient) {
            for (var i = 3, len = pixels.length; i < len; i += 4) {
                var alpha = 4 * pixels[i];
                if (alpha) {
                    pixels[i - 3] = gradient[alpha];
                    pixels[i - 2] = gradient[alpha + 1];
                    pixels[i - 1] = gradient[alpha + 2];
                }
            }
        }
    };

    window.simpleheat = simpleheat;
}();

/*
 (c) 2014, Vladimir Agafonkin
 Leaflet.heat, a tiny and fast heatmap plugin for Leaflet.
 https://github.com/Leaflet/Leaflet.heat
 Refined for InfraVision: Custom pane support (heatmapPane at z-index 350), safe zoom scaling, and robust resize.
*/
L.HeatLayer = (L.Layer ? L.Layer : L.Class).extend({
    initialize: function(latlngs, options) {
        this._latlngs = latlngs || [];
        L.setOptions(this, options);
    },

    setLatLngs: function(latlngs) {
        this._latlngs = latlngs || [];
        return this.redraw();
    },

    addLatLng: function(latlng) {
        this._latlngs.push(latlng);
        return this.redraw();
    },

    setOptions: function(options) {
        L.setOptions(this, options);
        if (this._heat) this._updateOptions();
        return this.redraw();
    },

    redraw: function() {
        if (!this._heat || this._frame || (this._map && this._map._animating)) return this;
        this._frame = L.Util.requestAnimFrame(this._redraw, this);
        return this;
    },

    onAdd: function(map) {
        this._map = map;
        if (!this._canvas) this._initCanvas();

        // Support custom pane (e.g. heatmapPane at z-index 350)
        var targetPane = this.options.pane ? 
            (map.getPane(this.options.pane) || (map._panes && map._panes[this.options.pane])) : 
            (map.getPanes ? map.getPanes().overlayPane : (map._panes && map._panes.overlayPane));

        if (targetPane) {
            targetPane.appendChild(this._canvas);
        } else if (map._panes && map._panes.overlayPane) {
            map._panes.overlayPane.appendChild(this._canvas);
        }

        map.on('moveend', this._reset, this);
        if (map.options.zoomAnimation && L.Browser.any3d) {
            map.on('zoomanim', this._animateZoom, this);
        }
        this._reset();
    },

    onRemove: function(map) {
        if (this._canvas && this._canvas.parentNode) {
            this._canvas.parentNode.removeChild(this._canvas);
        }
        map.off('moveend', this._reset, this);
        if (map.options.zoomAnimation) {
            map.off('zoomanim', this._animateZoom, this);
        }
    },

    addTo: function(map) {
        map.addLayer(this);
        return this;
    },

    _initCanvas: function() {
        var canvas = this._canvas = L.DomUtil.create('canvas', 'leaflet-heatmap-layer leaflet-layer');
        var originProp = L.DomUtil.testProp(['transformOrigin', 'WebkitTransformOrigin', 'msTransformOrigin']);
        if (originProp) canvas.style[originProp] = '50% 50%';

        var size = this._map.getSize();
        canvas.width = size ? size.x : 0;
        canvas.height = size ? size.y : 0;

        var animated = this._map.options.zoomAnimation && L.Browser.any3d;
        L.DomUtil.addClass(canvas, 'leaflet-zoom-' + (animated ? 'animated' : 'hide'));

        this._heat = simpleheat(canvas);
        this._updateOptions();
    },

    _updateOptions: function() {
        this._heat.radius(this.options.radius || this._heat.defaultRadius, this.options.blur);
        if (this.options.gradient) this._heat.gradient(this.options.gradient);
        if (this.options.max) this._heat.max(this.options.max);
    },

    _reset: function() {
        if (!this._map || !this._canvas) return;
        var topLeft = this._map.containerPointToLayerPoint([0, 0]);
        L.DomUtil.setPosition(this._canvas, topLeft);

        var size = this._map.getSize();
        if (size && size.x > 0 && size.y > 0) {
            if (this._heat._width !== size.x) {
                this._canvas.width = this._heat._width = size.x;
            }
            if (this._heat._height !== size.y) {
                this._canvas.height = this._heat._height = size.y;
            }
            this._redraw();
        }
    },

    _redraw: function() {
        if (!this._map || !this._heat) return;
        var size = this._map.getSize();
        if (!size || size.x <= 0 || size.y <= 0) return;

        var data = [],
            r = this._heat._r,
            bounds = new L.Bounds(L.point([-r, -r]), size.add([r, r])),
            max = void 0 === this.options.max ? 1 : this.options.max,
            maxZoom = void 0 === this.options.maxZoom ? this._map.getMaxZoom() : this.options.maxZoom,
            // If scaleIntensity is disabled or zoom >= maxZoom, keep full 1.0 intensity
            f = (this.options.scaleIntensity === false || this.options.disableZoomScaling) ? 1 :
                1 / Math.pow(2, Math.max(0, Math.min(maxZoom - this._map.getZoom(), 12))),
            cellSize = r / 2,
            grid = [],
            panePos = this._map._getMapPanePos ? this._map._getMapPanePos() : { x: 0, y: 0 },
            offsetX = panePos.x % cellSize,
            offsetY = panePos.y % cellSize;

        for (var i = 0, len = this._latlngs.length; i < len; i++) {
            var pt = this._latlngs[i];
            var p = this._map.latLngToContainerPoint(pt);
            if (bounds.contains(p)) {
                var col = Math.floor((p.x - offsetX) / cellSize) + 2;
                var row = Math.floor((p.y - offsetY) / cellSize) + 2;
                var alt = void 0 !== pt.alt ? pt.alt : (void 0 !== pt[2] ? +pt[2] : 1);
                var weight = alt * f;

                grid[row] = grid[row] || [];
                var cell = grid[row][col];
                if (cell) {
                    cell[0] = (cell[0] * cell[2] + p.x * weight) / (cell[2] + weight);
                    cell[1] = (cell[1] * cell[2] + p.y * weight) / (cell[2] + weight);
                    cell[2] += weight;
                } else {
                    grid[row][col] = [p.x, p.y, weight];
                }
            }
        }

        for (var rowIdx = 0, rowLen = grid.length; rowIdx < rowLen; rowIdx++) {
            if (grid[rowIdx]) {
                for (var colIdx = 0, colLen = grid[rowIdx].length; colIdx < colLen; colIdx++) {
                    var c = grid[rowIdx][colIdx];
                    if (c) {
                        data.push([Math.round(c[0]), Math.round(c[1]), Math.min(c[2], max)]);
                    }
                }
            }
        }

        this._heat.data(data).draw(this.options.minOpacity);
        this._frame = null;
    },

    _animateZoom: function(e) {
        var scale = this._map.getZoomScale(e.zoom),
            offset = this._map._getCenterOffset(e.center)._multiplyBy(-scale).subtract(this._map._getMapPanePos());

        if (L.DomUtil.setTransform) {
            L.DomUtil.setTransform(this._canvas, offset, scale);
        } else {
            this._canvas.style[L.DomUtil.TRANSFORM] = L.DomUtil.getTranslateString(offset) + ' scale(' + scale + ')';
        }
    }
});

L.heatLayer = function(latlngs, options) {
    return new L.HeatLayer(latlngs, options);
};