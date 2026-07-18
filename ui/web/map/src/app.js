import {
  AmbientLight,
  COORDINATE_SYSTEM,
  DirectionalLight,
  LightingEffect
} from "@deck.gl/core";
import {GeoJsonLayer, ScatterplotLayer} from "@deck.gl/layers";
import {MapboxOverlay} from "@deck.gl/mapbox";
import {ScenegraphLayer} from "@deck.gl/mesh-layers";
import maplibregl from "maplibre-gl";

import blankStyle from "../styles/blank-style.json";

const EARTH_RADIUS_M = 6378137;
const RAD_TO_DEG = 180 / Math.PI;
const EMPTY_NETWORK = {type: "FeatureCollection", features: []};
const TRUCK_MODEL_URL = new URL(
  "../../assets/models/truck/truck.gltf",
  window.location.href
).href;
const VIEW_CONFIG = {
  "2d": {pitch: 0, bearing: 0},
  "3d": {pitch: 48, bearing: -18}
};
const FLAT_LAYER_PARAMETERS = {depthCompare: "always", depthWriteEnabled: false};

const lightingEffect = new LightingEffect({
  ambientLight: new AmbientLight({color: [210, 226, 242], intensity: 1.4}),
  keyLight: new DirectionalLight({
    color: [255, 244, 214],
    intensity: 2.2,
    direction: [-3, -5, -8]
  })
});

const state = {
  bridge: null,
  network: EMPTY_NETWORK,
  roadNetwork: EMPTY_NETWORK,
  signalPoints: [],
  trafficLights: new Map(),
  vehicles: [],
  networkBounds: null,
  viewMode: "3d",
  selectedVehicleId: null
};

const statusElement = document.getElementById("map-status");
const viewButtons = Array.from(document.querySelectorAll("[data-view-mode]"));

function setStatus(message, isError = false) {
  statusElement.textContent = message;
  statusElement.dataset.state = isError ? "error" : "ready";
}

let map;
try {
  map = new maplibregl.Map({
    container: "map",
    style: blankStyle,
    center: [0, 0],
    zoom: 15,
    pitch: VIEW_CONFIG[state.viewMode].pitch,
    bearing: VIEW_CONFIG[state.viewMode].bearing,
    attributionControl: false,
    antialias: true
  });
} catch (error) {
  setStatus(`地图初始化失败：${error.message}`, true);
  throw error;
}

const overlay = new MapboxOverlay({
  interleaved: true,
  effects: [lightingEffect],
  layers: []
});

function toMapPosition(position) {
  if (!position || !Number.isFinite(position.x) || !Number.isFinite(position.y)) {
    return [0, 0, 0];
  }
  return [position.x, position.y, Number.isFinite(position.z) ? position.z : 0];
}

function phaseColor(signalId, alpha = 245) {
  const phase = state.trafficLights.get(signalId)?.toUpperCase();
  if (phase === "GREEN") {
    return [52, 211, 153, alpha];
  }
  if (phase === "YELLOW") {
    return [250, 204, 21, alpha];
  }
  if (phase === "RED") {
    return [248, 86, 103, alpha];
  }
  return [111, 140, 166, alpha];
}

function vehicleColor(vehicle, alpha = 245) {
  return vehicle.automation_level === "HUMAN"
    ? [244, 114, 182, alpha]
    : [56, 189, 248, alpha];
}

function focusVehicle(vehicleId, duration = 600) {
  const vehicle = state.vehicles.find((candidate) => candidate.vehicle_id === vehicleId);
  if (!vehicle) {
    return;
  }
  state.selectedVehicleId = vehicleId;
  const [x, y] = toMapPosition(vehicle.position);
  const view = VIEW_CONFIG[state.viewMode];
  map.easeTo({
    center: localMetersToLngLat(x, y),
    zoom: 18.5,
    pitch: view.pitch,
    bearing: view.bearing,
    duration
  });
  renderLayers();
}

function selectVehicle({object}) {
  if (object) {
    focusVehicle(object.vehicle_id);
  }
  if (object && state.bridge) {
    state.bridge.selectVehicle(object.vehicle_id);
  }
}

function roadLayers() {
  const common = {
    data: state.roadNetwork,
    coordinateSystem: COORDINATE_SYSTEM.METER_OFFSETS,
    coordinateOrigin: [0, 0, 0],
    filled: false,
    stroked: true,
    pickable: false,
    parameters: FLAT_LAYER_PARAMETERS
  };
  return [
    new GeoJsonLayer({
      ...common,
      id: "trafficverse-road-casing",
      lineWidthUnits: "meters",
      getLineWidth: 5.6,
      lineWidthMinPixels: 3,
      getLineColor: [5, 12, 20, 255]
    }),
    new GeoJsonLayer({
      ...common,
      id: "trafficverse-road-surface",
      lineWidthUnits: "meters",
      getLineWidth: 3.8,
      lineWidthMinPixels: 2,
      getLineColor: (feature) =>
        feature.properties?.speed_limit_mps >= 20
          ? [42, 64, 80, 255]
          : [34, 51, 66, 255]
    }),
    new GeoJsonLayer({
      ...common,
      id: "trafficverse-lane-guides",
      lineWidthUnits: "pixels",
      getLineWidth: 0.85,
      getLineColor: [132, 164, 186, 180]
    })
  ];
}

function signalLayers(phaseTrigger) {
  const common = {
    data: state.signalPoints,
    coordinateSystem: COORDINATE_SYSTEM.METER_OFFSETS,
    coordinateOrigin: [0, 0, 0],
    getPosition: (signal) => signal.position,
    radiusUnits: "meters",
    pickable: false,
    parameters: FLAT_LAYER_PARAMETERS,
    updateTriggers: {getFillColor: phaseTrigger}
  };
  return [
    new ScatterplotLayer({
      ...common,
      id: "trafficverse-signal-halo",
      getFillColor: (signal) => phaseColor(signal.signalId, 45),
      getRadius: 6,
      radiusMinPixels: 5,
      radiusMaxPixels: 12
    }),
    new ScatterplotLayer({
      ...common,
      id: "trafficverse-signals",
      getFillColor: (signal) => phaseColor(signal.signalId),
      getRadius: 2.2,
      radiusMinPixels: 3,
      radiusMaxPixels: 7,
      stroked: true,
      getLineColor: [7, 17, 27, 255],
      lineWidthMinPixels: 1
    })
  ];
}

function vehicleLayers() {
  const common = {
    data: state.vehicles,
    coordinateSystem: COORDINATE_SYSTEM.METER_OFFSETS,
    coordinateOrigin: [0, 0, 0],
    getPosition: (vehicle) => toMapPosition(vehicle.position),
    pickable: true,
    onClick: selectVehicle
  };
  const layers = [
    new ScatterplotLayer({
      ...common,
      id: "trafficverse-vehicle-halo",
      getFillColor: (vehicle) => vehicleColor(vehicle, 55),
      getRadius: (vehicle) =>
        vehicle.vehicle_id === state.selectedVehicleId
          ? 7
          : state.viewMode === "3d"
            ? 4.6
            : 3.6,
      radiusUnits: "meters",
      radiusMinPixels: 5,
      parameters: FLAT_LAYER_PARAMETERS
    })
  ];
  if (state.viewMode === "3d") {
    layers.push(
      new ScenegraphLayer({
        ...common,
        id: "trafficverse-vehicle-models",
        scenegraph: TRUCK_MODEL_URL,
        sizeScale: 0.75,
        sizeMinPixels: 18,
        sizeMaxPixels: 80,
        getTranslation: [0, 0, 0.45],
        getColor: (vehicle) => vehicleColor(vehicle),
        getOrientation: (vehicle) => [
          0,
          180 - (Number.isFinite(vehicle.heading_rad) ? vehicle.heading_rad * RAD_TO_DEG : 0),
          90
        ],
        _lighting: "pbr",
        onError: (error) => setStatus(`三维车辆模型加载失败：${error.message}`, true)
      })
    );
  } else {
    layers.push(
      new ScatterplotLayer({
        ...common,
        id: "trafficverse-vehicle-markers",
        getFillColor: vehicleColor,
        getRadius: 2.2,
        radiusUnits: "meters",
        radiusMinPixels: 4,
        stroked: true,
        getLineColor: [226, 232, 240, 245],
        lineWidthMinPixels: 1,
        parameters: FLAT_LAYER_PARAMETERS
      })
    );
  }
  return layers;
}

function renderLayers() {
  const phaseTrigger = Array.from(state.trafficLights.entries()).flat();
  overlay.setProps({
    effects: [lightingEffect],
    layers: [...roadLayers(), ...signalLayers(phaseTrigger), ...vehicleLayers()]
  });
  setStatus(
    `车道 ${state.roadNetwork.features.length} · 信号 ${state.signalPoints.length} · 车辆 ${state.vehicles.length}`
  );
}

function signalPointFromFeature(feature) {
  const coordinates = feature?.geometry?.coordinates;
  const signalId = feature?.properties?.signal_id;
  if (
    feature?.geometry?.type !== "Point" ||
    !signalId ||
    !Array.isArray(coordinates) ||
    !Number.isFinite(coordinates[0]) ||
    !Number.isFinite(coordinates[1])
  ) {
    return null;
  }
  return {
    signalId,
    position: [coordinates[0], coordinates[1], coordinates[2] ?? 0]
  };
}

function localMetersToLngLat(x, y) {
  return [x * RAD_TO_DEG / EARTH_RADIUS_M, y * RAD_TO_DEG / EARTH_RADIUS_M];
}

function visitCoordinates(coordinates, visitor) {
  if (!Array.isArray(coordinates)) {
    return;
  }
  if (Number.isFinite(coordinates[0]) && Number.isFinite(coordinates[1])) {
    visitor(coordinates[0], coordinates[1]);
    return;
  }
  for (const child of coordinates) {
    visitCoordinates(child, visitor);
  }
}

function resetView(duration = 500) {
  if (!state.networkBounds || state.networkBounds.isEmpty()) {
    return;
  }
  map.fitBounds(state.networkBounds, {
    padding: {top: 100, right: 46, bottom: 46, left: 46},
    duration,
    maxZoom: 18
  });
  const view = VIEW_CONFIG[state.viewMode];
  map.easeTo({pitch: view.pitch, bearing: view.bearing, duration});
}

function fitNetwork(network) {
  const bounds = new maplibregl.LngLatBounds();
  for (const feature of network.features ?? []) {
    visitCoordinates(feature?.geometry?.coordinates, (x, y) => {
      bounds.extend(localMetersToLngLat(x, y));
    });
  }
  state.networkBounds = bounds;
  resetView(0);
}

function setViewMode(viewMode) {
  if (!(viewMode in VIEW_CONFIG)) {
    return;
  }
  state.viewMode = viewMode;
  for (const button of viewButtons) {
    button.classList.toggle("active", button.dataset.viewMode === viewMode);
  }
  const view = VIEW_CONFIG[viewMode];
  map.easeTo({pitch: view.pitch, bearing: view.bearing, duration: 500});
  renderLayers();
}

for (const button of viewButtons) {
  button.addEventListener("click", () => setViewMode(button.dataset.viewMode));
}
document.getElementById("reset-view").addEventListener("click", () => resetView());

window.TrafficVerseMap = {
  setNetwork(network) {
    state.network = network?.type === "FeatureCollection" ? network : EMPTY_NETWORK;
    state.roadNetwork = {
      type: "FeatureCollection",
      features: state.network.features.filter((feature) => feature.geometry?.type === "LineString")
    };
    state.signalPoints = state.network.features
      .map(signalPointFromFeature)
      .filter((point) => point !== null);
    fitNetwork(state.network);
    renderLayers();
  },
  setVehicles(vehicles) {
    state.vehicles = Array.isArray(vehicles) ? vehicles : [];
    renderLayers();
  },
  setTrafficLights(trafficLights) {
    state.trafficLights = new Map(
      (Array.isArray(trafficLights) ? trafficLights : []).map((light) => [
        light.signal_id,
        light.phase
      ])
    );
    renderLayers();
  },
  focusVehicle(vehicleId) {
    focusVehicle(vehicleId);
  }
};

function connectQtBridge() {
  if (!window.qt || !window.QWebChannel) {
    setStatus("地图已就绪 · 浏览器预览模式");
    return;
  }
  new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
    state.bridge = channel.objects.trafficVerseBridge;
    state.bridge.mapReady();
    setStatus("地图已就绪");
  });
}

map.once("load", () => {
  map.addControl(overlay);
  map.addControl(new maplibregl.NavigationControl({visualizePitch: true}), "top-right");
  setViewMode(state.viewMode);
  connectQtBridge();
});
map.on("error", (event) => {
  const message = event?.error?.message ?? "未知错误";
  setStatus(`地图资源加载失败：${message}`, true);
});
