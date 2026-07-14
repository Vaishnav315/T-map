import os
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ConfigLoader")

class ConfigLoader:
    def __init__(self, base_dir=None):
        if base_dir is None:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        else:
            self.base_dir = base_dir

        self.camera_registry_path = os.path.join(self.base_dir, "..", "data", "camera_registry.json")
        self.map_layout_path = os.path.join(self.base_dir, "..", "data", "map_layout_config.json")
        
        self.camera_registry = {}
        self.map_layout = {}
        
        self.load_configs()

    def load_configs(self):
        """Loads and validates registry and map configs from JSON files."""
        # 1. Parse Camera Registry
        if not os.path.exists(self.camera_registry_path):
            raise FileNotFoundError(f"camera_registry.json not found at {self.camera_registry_path}")
        
        try:
            with open(self.camera_registry_path, "r") as f:
                self.camera_registry = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing camera_registry.json: {e}")
            raise

        # 2. Parse Map Layout Config
        if not os.path.exists(self.map_layout_path):
            raise FileNotFoundError(f"map_layout_config.json not found at {self.map_layout_path}")
        
        try:
            with open(self.map_layout_path, "r") as f:
                self.map_layout = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing map_layout_config.json: {e}")
            raise
            
        self.validate_configs()

    def validate_configs(self):
        """Validates semantic correctness of loaded configuration files."""
        # Check that all mapped items have a corresponding registry camera
        for dev_id, layout_data in self.map_layout.items():
            if dev_id not in self.camera_registry:
                logger.warning(f"Device ID {dev_id} in map_layout_config.json is missing in camera_registry.json")
            
            # Check percentage boundary conditions (only if coordinates are placed)
            px = layout_data.get("Percentage_X")
            py = layout_data.get("Percentage_Y")
            if px is not None and py is not None:
                if not (0 <= px <= 100) or not (0 <= py <= 100):
                    logger.error(f"Device ID {dev_id} has out-of-bounds percentages: X={px}, Y={py}")
                    raise ValueError(f"Out of bounds percentages for camera {dev_id}")
                
        logger.info(f"Configurations successfully loaded. Registry: {len(self.camera_registry)} cameras. Layouts: {len(self.map_layout)} placements.")

    def get_camera_registry(self):
        return self.camera_registry

    def get_map_layout(self):
        return self.map_layout

    def get_camera_details(self, device_id):
        return self.camera_registry.get(str(device_id))

    def get_layout_details(self, device_id):
        return self.map_layout.get(str(device_id))

    def get_csv_camera_record(self, device_id):
        csv_path = os.path.join(self.base_dir, "..", "data", "camera_access_report.csv")
        if not os.path.exists(csv_path):
            logger.warning(f"camera_access_report.csv not found at {csv_path}")
            return None

        # Get the registry IP for fallback matching
        registry_ip = None
        cam_registry_details = self.get_camera_details(device_id)
        if cam_registry_details:
            registry_ip = cam_registry_details.get("IP")

        import csv
        try:
            with open(csv_path, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    csv_dev_id = str(row.get('DeviceID', '')).strip()
                    csv_ip = str(row.get('IPAddress', '')).strip()
                    
                    match_by_id = (csv_dev_id == str(device_id).strip())
                    match_by_ip = (registry_ip and csv_ip == str(registry_ip).strip())
                    
                    if match_by_id or match_by_ip:
                        return {
                            "ID": row.get('DeviceID', ''),
                            "Name": row.get('DeviceName', ''),
                            "IP": row.get('IPAddress', ''),
                            "User": row.get('Username', ''),
                            "Pass": row.get('DecodedPassword', ''),
                            "Brand": row.get('Brand', '').upper().strip(),
                            "Accessible": row.get('Accessible', 'True').strip().lower() == 'true',
                            "Error": row.get('Error', '').strip()
                        }
        except Exception as e:
            logger.error(f"Error reading camera_access_report.csv: {e}")
        return None

    def get_physical_rtsp_url(self, device_id):
        """Constructs raw physical RTSP connection URL with credentials securely escaped."""
        csv_cam = self.get_csv_camera_record(device_id)
        if csv_cam:
            user = csv_cam["User"]
            ip = csv_cam["IP"]
            brand = csv_cam["Brand"]
            
            # Escape character rules from cam_api.py
            safe_pwd = csv_cam["Pass"].replace("#", "%23").replace("$", "%24").replace("@", "%40")

            if "MATRIX" in brand:
                return f"rtsp://{user}:{safe_pwd}@{ip}/unicaststream/1"
            elif "ONVIF" in brand:
                return f"rtsp://{user}:{safe_pwd}@{ip}/rtsp_tunnel?inst=1"
            else:
                return f"rtsp://{user}:{safe_pwd}@{ip}/h264"

        # Fallback to default json-based config loader logic:
        cam = self.get_camera_details(device_id)
        if not cam:
            return None
        
        from urllib.parse import quote
        
        # Safely quote credentials (special characters like @, #, $, : are encoded)
        username = quote(cam.get("Username", "admin"))
        password = quote(cam.get("DecodedPassword", ""))
        ip = cam.get("IP", "127.0.0.1")
        
        brand = cam.get("Brand", "").lower()
        port = cam.get("Port", 554)
        
        # Determine RTSP path based on brand
        if "dahua" in brand:
            path = "cam/realmonitor?channel=1&subtype=0"
        elif "hikvision" in brand:
            path = "Streaming/Channels/101"
        elif "axis" in brand:
            path = "axis-media/media.amp"
        elif "bosch" in brand:
            path = "rtsp_tunnel"
        elif "hanwha" in brand or "samsung" in brand:
            path = "profile2/media.smp"
        else:
            # Fallback
            path = "h264Preview_01_main"
            
        return f"rtsp://{username}:{password}@{ip}:{port}/{path}"

    def get_mediamtx_rtsp_url(self, device_id, internal_ip="127.0.0.1"):
        """URL for Flask backend or internal clients to pull from MediaMTX proxy server."""
        return f"rtsp://{internal_ip}:8554/live/stream_{device_id}"

# Global singleton loader
loader = ConfigLoader()

if __name__ == "__main__":
    # Test execution
    loader.validate_configs()
    print("Physical RTSP Example:", loader.get_physical_rtsp_url("224"))
    print("MediaMTX RTSP Example:", loader.get_mediamtx_rtsp_url("224"))
