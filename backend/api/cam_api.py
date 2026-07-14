import os
import sys
import csv
import cv2

CSV_FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "camera_access_report.csv")

def get_camera_record(device_id):
    if not os.path.exists(CSV_FILE_PATH):
        print(f"❌ Critical Error: '{CSV_FILE_PATH}' missing from directory.")
        return None

    with open(CSV_FILE_PATH, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if str(row['DeviceID']).strip() == str(device_id).strip():
                return {
                    "ID": row['DeviceID'],
                    "Name": row['DeviceName'],
                    "IP": row['IPAddress'],
                    "User": row['Username'],
                    "Pass": row['DecodedPassword'],
                    "Brand": row['Brand'].upper().strip()
                }
    return None

def build_safe_rtsp_url(cam):
    """
    Constructs a customized inline string that explicitly escapes the '#' symbol,
    while removing explicit port colons to safeguard against FFMPEG parser crashes.
    """
    user = cam["User"]
    ip = cam["IP"]
    brand = cam["Brand"]
    
    # 🔐 Convert only the '#' character to hex code '%23'.
    # Since we remove the ':554' port string, FFMPEG will not read %23 as a broken port index!
    safe_pwd = cam["Pass"].replace("#", "%23")
    safe_pwd = safe_pwd.replace("$", "%24")
    safe_pwd = safe_pwd.replace("@", "%40")

    # Set paths natively
    if "MATRIX" in brand:
        # 🚀 THE PIECE THAT FIXES IT: Remove ':554'. RTSP defaults to 554 automatically.
        # This allows FFMPEG to read the hex password natively without a 'Port missing' failure.
        return f"rtsp://{user}:{safe_pwd}@{ip}/unicaststream/1"
    elif "ONVIF" in brand:
        return f"rtsp://{user}:{safe_pwd}@{ip}/rtsp_tunnel?inst=1"
    else:
        return f"rtsp://{user}:{safe_pwd}@{ip}/h264"

def start_video_dashboard(device_id):
    cam = get_camera_record(device_id)
    if not cam:
        print(f"❌ Error: Camera with Device ID '{device_id}' was not found.")
        return

    print(f"\n🎯 [Resolved Asset] ID: {cam['ID']} | Name: {cam['Name']} | Brand: {cam['Brand']}")
    
    # Build custom target URL layout
    rtsp_url = build_safe_rtsp_url(cam)
    print(f"🔗 Target Stream String: rtsp://{cam['User']}:******@{cam['IP']}/...")

    # Clear lingering global options and enforce stable TCP stream mapping
    if "OPENCV_FFMPEG_CAPTURE_OPTIONS" in os.environ:
        del os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"]
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print(f"\n❌ Connection Error: Stream entry verification failed for camera at {cam['IP']}.")
        
        # Secondary sub-stream fallback mechanism using the same structural logic
        if "MATRIX" in cam["Brand"]:
            print("🔄 Primary stream rejected. Testing alternative profile path /unicaststream/2...")
            safe_pwd = cam["Pass"].replace("#", "%23").replace("$", "%24").replace("@", "%40")
            alt_url = f"rtsp://{cam['User']}:{safe_pwd}@{cam['IP']}/unicaststream/2"
            cap = cv2.VideoCapture(alt_url, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                print("❌ Connection failed. Both stream profiles rejected connection handle parameters.")
                return
        else:
            return

    print(f"\n🎉 SUCCESS! Network authentication clear. Video pipeline active: {cam['Name']}\n")
    window_title = f"Map Dashboard Gateway - ID {device_id}"
    cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)

    while True:
        ret, frame = cap.read()
        if not ret:
            print("⚠️ Stream frame buffer dropped sync loops.")
            break
            
        cv2.imshow(window_title, frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("🔌 Video stream safely unmounted.")

if __name__ == "__main__":
    target_device = sys.argv[1] if len(sys.argv) > 1 else "145"
    start_video_dashboard(target_device)