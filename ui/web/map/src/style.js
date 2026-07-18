export const MAP_THEMES = {
  dark: {
    background: "#141414",
    roadCasing: [48, 49, 51, 255],
    roadFast: [64, 158, 255, 255],
    roadRegular: [96, 98, 102, 255],
    laneGuide: [163, 166, 173, 180],
    signal: {
      green: [103, 194, 58],
      yellow: [230, 162, 60],
      red: [245, 108, 108],
      unknown: [144, 147, 153]
    },
    vehicle: {human: [230, 162, 60], automated: [64, 158, 255]},
    signalOutline: [29, 30, 31, 255],
    vehicleOutline: [229, 234, 243, 245],
    ambientLight: [229, 234, 243],
    keyLight: [255, 245, 224]
  },
  light: {
    background: "#f2f3f5",
    roadCasing: [220, 223, 230, 255],
    roadFast: [64, 158, 255, 255],
    roadRegular: [144, 147, 153, 255],
    laneGuide: [255, 255, 255, 230],
    signal: {
      green: [103, 194, 58],
      yellow: [230, 162, 60],
      red: [245, 108, 108],
      unknown: [144, 147, 153]
    },
    vehicle: {human: [230, 162, 60], automated: [64, 158, 255]},
    signalOutline: [255, 255, 255, 255],
    vehicleOutline: [48, 49, 51, 235],
    ambientLight: [245, 247, 250],
    keyLight: [255, 245, 224]
  }
};

export const LAYER_STYLE = {
  roadCasingWidthM: 5.6,
  roadSurfaceWidthM: 3.8,
  laneGuideWidthPx: 0.85,
  signalHaloRadiusM: 6,
  signalRadiusM: 2.2,
  vehicleModelScale: 0.75,
  vehicleMarkerRadiusM: 2.2
};
