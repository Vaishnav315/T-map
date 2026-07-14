import taslBlueprintImg from '../assets/tasl_security_layout.png';

export const MAP_CENTER = [17.2440, 78.5410];
export const MAP_ZOOM = 18;

export const BLUEPRINT_CONFIG = {
  url: taslBlueprintImg,
  width: 2048,
  height: 1290,
};

export const BLIND_SPOTS = [
  [{"lat":531.8000030517578,"lng":875.059209346093},{"lat":264.8000030517578,"lng":984.015883968435}],
  [{"lat":284.8000030517578,"lng":314.28219592284677},{"lat":264.8000030517578,"lng":739.1132666980333}],
  [{"lat":499.8000030517578,"lng":555.1864031153643},{"lat":401.8000030517578,"lng":757.1061120485118}],
  [{"lat":709.8000030517578,"lng":139.35175501541715},{"lat":590.8000030517578,"lng":197.32870114473673}],
  [{"lat":581.8000030517578,"lng":469.22058644085604},{"lat":510.8000030517578,"lng":519.2007124144075}],
  [{"lat":698.8000030517578,"lng":451.2277410903775},{"lat":589.8000030517578,"lng":500.20826454445785}],
  [{"lat":606.8000030517578,"lng":502.2074695834001},{"lat":592.8000030517578,"lng":632.1557971146335}],
  [{"lat":696.8000030517578,"lng":502.2074695833999},{"lat":676.8000030517578,"lng":914.0437076054632}],
  [{"lat":673.8000030517578,"lng":739.1132666980334},{"lat":608.8000030517578,"lng":757.1061120485117}],
  [{"lat":675.8000030517578,"lng":639.1530147509307},{"lat":611.8000030517578,"lng":653.1474500235249}],
  [{"lat":698.8000030517578,"lng":313.2825934033758},{"lat":676.8000030517578,"lng":450.22813857090654}],
  [{"lat":615.8000030517578,"lng":916.0429126444051},{"lat":675.8000030517578,"lng":884.0556320213323}],
  [{"lat":242.8000030517578,"lng":192.33068854738156},{"lat":102.80000305175781,"lng":620.1605668809812}],
  [{"lat":100.80000305175781,"lng":1004.0079343578556},{"lat":241.8000030517578,"lng":874.059606826622}],
  [{"lat":281.6000061035156,"lng":1129.9657861690603},{"lat":1097.6000061035156,"lng":1016.0110989493633}],
  [{"lat":1163.6000061035156,"lng":294.29807989128176},{"lat":915.6000061035156,"lng":806.0945698604477}],
  [{"lat":675.8000030517578,"lng":759.061991709796},{"lat":592.8000030517578,"lng":882.0131016047322}]
];

export const CAMERA_METADATA = [
  { id: '28', name: 'P2 C17', coords: [17.2439174, 78.5403015], blueprint_coords: [301, 541], ip: '10.10.25.224', area: 'Plant 2' },
  { id: '27', name: 'P2 C1', coords: [17.2438281, 78.5407760], blueprint_coords: [386, 849], ip: '10.10.25.223', area: 'Plant 2' },
  { id: '33', name: 'P3 A16', coords: [17.2439568, 78.5405590], blueprint_coords: [804, 346], ip: '10.10.25.226', area: 'Plant 3' },
  { id: '35', name: 'P3 B16', coords: [17.2440603, 78.5414556], blueprint_coords: [898, 352], ip: '10.10.25.230', area: 'Plant 3' },
  { id: '3', name: 'SECURITY IN', coords: [17.2444810, 78.5418086], blueprint_coords: [589, 955], ip: '10.10.25.205', area: 'Perimeter/Logistics' },
];

export const MAP_LAYERS = {
  satellite: {
    name: 'High-Res Satellite',
    url: 'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
    attribution: '&copy; Google Maps Imagery',
    maxNativeZoom: 20,
    isBlueprint: false,
  },
  hybrid: {
    name: 'Hybrid Tactical',
    url: 'https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
    attribution: '&copy; Google Maps Hybrid',
    maxNativeZoom: 20,
    isBlueprint: false,
  },
  streets: {
    name: 'Google Streets',
    url: 'https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
    attribution: '&copy; Google Maps Vector',
    maxNativeZoom: 20,
    isBlueprint: false,
  },
  blueprint: {
    name: 'TASL Security Layout',
    url: '',
    attribution: '&copy; TASL Industrial Engineering',
    maxNativeZoom: 4,
    isBlueprint: true,
  },
};
