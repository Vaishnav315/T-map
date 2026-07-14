import os
import csv
import json

# Define the 5 real prototype cameras mapped to their actual CSV DeviceIDs:
# 224 -> ID 28
# 225 -> ID 27
# 226 -> ID 33
# 227 -> ID 35
# 228 -> ID 3
REAL_IDS_MAP = {

    "27": {
        "Percentage_X": 42.432,
        "Percentage_Y": 25.814,
        "Viewing_Angle": 90,
        "LensCalibration": {
            "screenshot_pts": [[111, 329], [631, 106], [304, 105], [755, 235]],
            "blueprint_pts": [[496, 572], [453, 544], [442, 575], [487, 546]]
        }
    },
    "33": {
        "Percentage_X": 16.895,
        "Percentage_Y": 62.326,
        "Viewing_Angle": 180,
        "LensCalibration": {
            "screenshot_pts": [[225, 238], [122, 245], [544, 51], [531, 178]],
            "blueprint_pts": [[198, 268], [190, 261], [241, 258], [209, 277]]
        }
    },
    "35": {
        "Percentage_X": 17.188,
        "Percentage_Y": 69.612,
        "Viewing_Angle": 270,
        "LensCalibration": {
            "screenshot_pts": [[111, 329], [631, 106], [304, 105], [755, 235]],
            "blueprint_pts": [[496, 572], [453, 544], [442, 575], [487, 546]]
        }
    },
    "3": {
        "Percentage_X": 46.631,
        "Percentage_Y": 45.659,
        "Viewing_Angle": 0,
        "LensCalibration": {
            "screenshot_pts": [[297, 32], [726, 193], [270, 422], [474, 446]],
            "blueprint_pts": [[609, 417], [573, 443], [570, 419], [569, 423]]
        }
    },
    # Plant 1 Cams
    "111": {"Percentage_X": 15.723, "Percentage_Y": 38.295},
    "26": {"Percentage_X": 10.303, "Percentage_Y": 38.062},
    "122": {"Percentage_X": 16.602, "Percentage_Y": 31.318},
    "97": {"Percentage_X": 22.119, "Percentage_Y": 31.395},
    "103": {"Percentage_X": 19.434, "Percentage_Y": 31.473},
    "25": {"Percentage_X": 42.383, "Percentage_Y": 34.109},
    # Plant 2 Cams
    "113": {"Percentage_X": 41.406, "Percentage_Y": 30.155},
    "107": {"Percentage_X": 41.309, "Percentage_Y": 23.256},
    "124": {"Percentage_X": 38.867, "Percentage_Y": 30.310},
    "117": {"Percentage_X": 26.367, "Percentage_Y": 23.411},
    "106": {"Percentage_X": 20.703, "Percentage_Y": 30.233},
    # Plant 3 Cams
    "110": {"Percentage_X": 10.205, "Percentage_Y": 63.333},
    "119": {"Percentage_X": 16.553, "Percentage_Y": 62.403},
    "50": {"Percentage_X": 34.326, "Percentage_Y": 61.163},
    "49": {"Percentage_X": 36.768, "Percentage_Y": 61.085},
    "135": {"Percentage_X": 17.188, "Percentage_Y": 69.612},
    "108": {"Percentage_X": 18.262, "Percentage_Y": 62.326},
    "116": {"Percentage_X": 21.729, "Percentage_Y": 62.481},
    "32": {"Percentage_X": 27.393, "Percentage_Y": 62.558},
    "30": {"Percentage_X": 40.576, "Percentage_Y": 69.535},
    "31": {"Percentage_X": 40.674, "Percentage_Y": 62.248},
    # New cameras requested
    "4": {"Percentage_X": 47.559, "Percentage_Y": 45.736},
    "85": {"Percentage_X": 35.205, "Percentage_Y": 44.109},
    "125": {"Percentage_X": 49.561, "Percentage_Y": 18.605},
    "88": {"Percentage_X": 20.703, "Percentage_Y": 54.186},
    "86": {"Percentage_X": 20.410, "Percentage_Y": 45.969},
    "89": {"Percentage_X": 18.701, "Percentage_Y": 52.016},
    "87": {"Percentage_X": 21.484, "Percentage_Y": 48.760},
    "13": {"Percentage_X": 43.799, "Percentage_Y": 67.054},
    "14": {"Percentage_X": 8.350, "Percentage_Y": 70.698}
}

def classify_zone(name, ip):
    name_upper = name.upper()
    ip_clean = ip.strip()

    # Rule 4: PERIMETER & LOGISTICS keywords first
    perimeter_keywords = [
        "GATE", "SECURITY", "WATCH TOWER", "PARKING", "SEWAGE", "SCRAP", "LOGISTICS", "WATCHTOWER"
    ]
    if any(k in name_upper for k in perimeter_keywords):
        return "Perimeter/Logistics"

    # Rule 1: PLANT 1
    if "P1" in name_upper or "PLANT 1" in name_upper or "PLANT1" in name_upper:
        return "Plant 1"
    if ip_clean in ["10.10.25.14", "10.10.25.28", "10.10.25.29", "10.10.25.30"]:
        return "Plant 1"

    # Rule 2: PLANT 2
    if "P2" in name_upper or "PLANT 2" in name_upper or "PLANT2" in name_upper:
        return "Plant 2"
    p2_ips = ["10.10.25.102", "10.10.25.210"] + [f"10.10.25.{x}" for x in range(164, 170)]
    if ip_clean in p2_ips:
        return "Plant 2"

    # Rule 3: PLANT 3
    if "P3" in name_upper or "PLANT 3" in name_upper or "PLANT3" in name_upper:
        return "Plant 3"

    # Fallback to Perimeter/Logistics
    return "Perimeter/Logistics"

def generate_configs_from_csv():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, "camera_access_report.csv")
    registry_path = os.path.join(current_dir, "camera_registry.json")
    layout_path = os.path.join(current_dir, "map_layout_config.json")

    registry = {}
    layout = {}

    with open(csv_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            dev_id = str(row['DeviceID']).strip()
            name = str(row['DeviceName']).strip()
            ip = str(row['IPAddress']).strip()
            user = str(row['Username']).strip()
            password = str(row['DecodedPassword']).strip()
            brand = str(row['Brand']).strip().upper()
            
            # Catalog zone
            allocation = classify_zone(name, ip)

            registry[dev_id] = {
                "DeviceID": dev_id,
                "Name": name,
                "IP": ip,
                "Username": user,
                "DecodedPassword": password,
                "Brand": brand,
                "Allocation": allocation
            }

            # Map layout configuration
            layout_details = {
                "DeviceID": dev_id,
                "Facility_Map": "TASL Security Layout",
                "Percentage_X": None,
                "Percentage_Y": None,
                "Viewing_Angle": 0
            }

            # If it matches one of our prototype cameras, keep its placement
            if dev_id in REAL_IDS_MAP:
                layout_details.update(REAL_IDS_MAP[dev_id])

            layout[dev_id] = layout_details

    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2)

    with open(layout_path, "w") as f:
        json.dump(layout, f, indent=2)

    print(f"Successfully processed CSV. Registry: {len(registry)} cameras. Layouts: {len(layout)} configurations.")

if __name__ == "__main__":
    generate_configs_from_csv()


