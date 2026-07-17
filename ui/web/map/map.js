(() => {
  "use strict";

  const status = document.getElementById("map-status");
  if (typeof window.L === "undefined") {
    status.textContent = "Leaflet 本地资源缺失或损坏，请重新安装 TrafficVerse。";
    return;
  }

  const map = L.map("map", {
    crs: L.CRS.Simple,
    minZoom: -5,
    maxZoom: 4,
    zoomControl: true,
    attributionControl: true,
  });
  map.attributionControl.setPrefix("TrafficVerse · Leaflet");
  const roadLayer = L.geoJSON(null, {
    coordsToLatLng: (coords) => L.latLng(coords[1], coords[0]),
    style: { color: "#53677d", weight: 1.3, opacity: 0.85 },
    pointToLayer: (_feature, latlng) =>
      L.circleMarker(latlng, { radius: 5, color: "#9aa9ba", fillOpacity: 0.95 }),
  }).addTo(map);
  const vehicles = new Map();
  const signalMarkers = new Map();
  let bridge = null;

  function vehicleColor(level) {
    return { HUMAN: "#37c6ff", ACC: "#54e39d", L2: "#ffd166", L3: "#ff9f43", L4: "#ff5c8a" }[level] || "#ffffff";
  }

  function signalColor(phase) {
    return { RED: "#ff4d5a", YELLOW: "#ffd23f", GREEN: "#42dc83", OFF: "#697789" }[phase] || "#697789";
  }

  window.TrafficVerseMap = {
    setNetwork(geojson) {
      roadLayer.clearLayers();
      signalMarkers.clear();
      roadLayer.addData(geojson);
      roadLayer.eachLayer((layer) => {
        const properties = layer.feature && layer.feature.properties;
        if (properties && properties.signal_id) {
          signalMarkers.set(properties.signal_id, layer);
        }
      });
      const bounds = roadLayer.getBounds();
      if (bounds.isValid()) map.fitBounds(bounds.pad(0.03));
      status.textContent = `路网已加载 · ${geojson.features.length} 个要素`;
    },

    setVehicles(values) {
      const active = new Set();
      values.forEach((vehicle) => {
        active.add(vehicle.vehicle_id);
        const point = [vehicle.position.y, vehicle.position.x];
        let marker = vehicles.get(vehicle.vehicle_id);
        if (!marker) {
          marker = L.circleMarker(point, {
            radius: 4,
            weight: 1,
            color: "#071018",
            fillColor: vehicleColor(vehicle.automation_level),
            fillOpacity: 0.95,
          }).addTo(map);
          marker.on("click", () => {
            if (bridge) bridge.selectVehicle(vehicle.vehicle_id);
          });
          vehicles.set(vehicle.vehicle_id, marker);
        }
        marker.setLatLng(point);
        marker.bindTooltip(`${vehicle.vehicle_id} · ${(vehicle.speed_mps * 3.6).toFixed(1)} km/h`);
      });
      vehicles.forEach((marker, vehicleId) => {
        if (!active.has(vehicleId)) {
          map.removeLayer(marker);
          vehicles.delete(vehicleId);
        }
      });
      status.textContent = `全局车辆 ${values.length} · 点击车辆可控制`;
    },

    setTrafficLights(values) {
      values.forEach((light) => {
        const marker = signalMarkers.get(light.signal_id);
        if (marker && marker.setStyle) {
          const color = signalColor(light.phase);
          marker.setStyle({ color, fillColor: color });
          marker.bindTooltip(`${light.signal_id} · ${light.phase}`);
        }
      });
    },
  };

  if (window.qt && window.QWebChannel) {
    new QWebChannel(qt.webChannelTransport, (channel) => {
      bridge = channel.objects.trafficVerseBridge;
      bridge.mapReady();
    });
  }
})();
