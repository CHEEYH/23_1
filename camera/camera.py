import sys
import socket
import struct
from camera.SciCam_class import *

m_currentCam = SciCamera()
m_currentDeviceInfo = None

from datetime import datetime

def AutoCaptureFlow(callback=None):
    # Step 1: Discovery devices
    print("[Step 1/6] Discovering devices...")
    devInfos = SCI_DEVICE_INFO_LIST()
    reVal = SciCamera.SciCam_DiscoveryDevices(devInfos, SciCamTLType.SciCam_TLType_Unkown)

    if reVal != SCI_CAMERA_OK:
        msg = f"ERROR: Discovery devices failed, error code: {reVal}"
        print(msg)
        if callback:
            callback(False, msg, None)
        return False

    if devInfos.count == 0:
        msg = "ERROR: No devices found!"
        print(msg)
        if callback:
            callback(False, msg, None)
        return False

    print(f"Found {devInfos.count} device(s)")
    for i in range(devInfos.count):
        dev = devInfos.pDevInfo[i]
        if dev.tlType == SciCamTLType.SciCam_TLType_Gige:
            # Get camera IP
            cam_ip = uint32_to_ipv4(dev.info.gigeInfo.ip)

            # Get camera model name
            cam_name = ''
            for per in dev.info.gigeInfo.modelName:
                if per == 0:
                    break
                cam_name = cam_name + chr(per)

            print(f"  [{i}] {cam_name} - IP: {cam_ip}")
        else:
            cam_name = ''
            if dev.tlType == SciCamTLType.SciCam_TLType_Usb3:
                for per in dev.info.usb3Info.modelName:
                    if per == 0:
                        break
                    cam_name = cam_name + chr(per)
            elif dev.tlType == SciCamTLType.SciCam_TLType_CL:
                for per in dev.info.clInfo.cameraModel:
                    if per == 0:
                        break
                    cam_name = cam_name + chr(per)

            tl_type = "USB3" if dev.tlType == SciCamTLType.SciCam_TLType_Usb3 else "CameraLink"
            print(f"  [{i}] {cam_name} - Interface: {tl_type}")

    print("\nAuto-selecting first device (Index: 0)\n")
    global m_currentDeviceInfo
    m_currentDeviceInfo = devInfos.pDevInfo[0]

    # Show selected camera IP
    if m_currentDeviceInfo.tlType == SciCamTLType.SciCam_TLType_Gige:
        cam_ip = uint32_to_ipv4(m_currentDeviceInfo.info.gigeInfo.ip)
        print(f"Selected Camera IP: {cam_ip}")
        print(f"Connecting to camera at {cam_ip}...\n")

    # Step 2: Open device
    print("[Step 2/6] Opening device...")
    reVal = m_currentCam.SciCam_CreateDevice(m_currentDeviceInfo)
    if reVal != SCI_CAMERA_OK:
        msg = f"ERROR: Create device failed, error code: {reVal}"
        print(msg)
        if callback:
            callback(False, msg, None)
        return False

    reVal = m_currentCam.SciCam_OpenDevice()
    if reVal != SCI_CAMERA_OK:
        msg = f"ERROR: Open device failed, error code: {reVal}"
        print(msg)
        if callback:
            callback(False, msg, None)
        return False
    print("Device opened successfully!\n")

    # set parameter xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxvalue
    m_currentCam.SciCam_SetFloatValueEx(0, "ExposureTime", 15000)

    # Step 3: Start grabbing
    print("[Step 3/6] Starting grabbing...")
    reVal = m_currentCam.SciCam_StartGrabbing()
    if reVal != SCI_CAMERA_OK:
        msg = f"ERROR: Start grabbing failed, error code: {reVal}"
        print(msg)
        m_currentCam.SciCam_CloseDevice()
        m_currentCam.SciCam_DeleteDevice()
        if callback:
            callback(False, msg, None)
        return False
    print("Grabbing started!\n")

    # Step 4: Grab and save image
    print("[Step 4/6] Capturing and saving image as BMP...")
    ppayload = ctypes.c_void_p()
    reVal = m_currentCam.SciCam_Grab(ppayload)
    if reVal != SCI_CAMERA_OK:
        msg = f"ERROR: Grab failed, error code: {reVal}"
        print(msg)
        m_currentCam.SciCam_StopGrabbing()
        m_currentCam.SciCam_CloseDevice()
        m_currentCam.SciCam_DeleteDevice()
        if callback:
            callback(False, msg, None)
        return False

    payloadAttribute = SCI_CAM_PAYLOAD_ATTRIBUTE()
    reVal = SciCam_Payload_GetAttribute(ppayload, payloadAttribute)
    if reVal != SCI_CAMERA_OK:
        msg = f"ERROR: Get payload attribute failed, error code: {reVal}"
        print(msg)
        m_currentCam.SciCam_FreePayload(ppayload)
        m_currentCam.SciCam_StopGrabbing()
        m_currentCam.SciCam_CloseDevice()
        m_currentCam.SciCam_DeleteDevice()
        if callback:
            callback(False, msg, None)
        return False

    imgWidth = payloadAttribute.imgAttr.width
    imgHeight = payloadAttribute.imgAttr.height
    framID = payloadAttribute.frameID
    imgPixelType = payloadAttribute.imgAttr.pixelType

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # e.g., 20260126_151230
    save_file_param = f"Image_{timestamp}.bmp"

    imgData = ctypes.c_void_p()
    reVal = SciCam_Payload_GetImage(ppayload, imgData)
    if reVal != SCI_CAMERA_OK:
        msg = f"ERROR: Get image data failed, error code: {reVal}"
        print(msg)
        m_currentCam.SciCam_FreePayload(ppayload)
        m_currentCam.SciCam_StopGrabbing()
        m_currentCam.SciCam_CloseDevice()
        m_currentCam.SciCam_DeleteDevice()
        if callback:
            callback(False, msg, None)
        return False

    dstImgSize = ctypes.c_int()

    # Check if mono format
    mono_formats = [
        SciCamPixelType.Mono1p, SciCamPixelType.Mono2p, SciCamPixelType.Mono4p,
        SciCamPixelType.Mono8s, SciCamPixelType.Mono8, SciCamPixelType.Mono10,
        SciCamPixelType.Mono10p, SciCamPixelType.Mono12, SciCamPixelType.Mono12p,
        SciCamPixelType.Mono14, SciCamPixelType.Mono16, SciCamPixelType.Mono10Packed,
        SciCamPixelType.Mono12Packed, SciCamPixelType.Mono14p
    ]

    if imgPixelType in mono_formats:
        reVal = SciCam_Payload_ConvertImage(payloadAttribute.imgAttr, imgData, SciCamPixelType.Mono8, None, dstImgSize,
                                            True)
        if reVal == SCI_CAMERA_OK:
            pDstData = (ctypes.c_ubyte * dstImgSize.value)()
            reVal = SciCam_Payload_ConvertImageEx(payloadAttribute.imgAttr, imgData, SciCamPixelType.Mono8, pDstData,
                                                  dstImgSize, True, 0)
            if reVal == SCI_CAMERA_OK:
                reVal = SciCam_Payload_SaveImage(save_file_param, SciCamPixelType.Mono8, pDstData, imgWidth, imgHeight)
    else:
        reVal = SciCam_Payload_ConvertImage(payloadAttribute.imgAttr, imgData, SciCamPixelType.RGB8, None, dstImgSize,
                                            True)
        if reVal == SCI_CAMERA_OK:
            pDstData = (ctypes.c_ubyte * dstImgSize.value)()
            reVal = SciCam_Payload_ConvertImage(payloadAttribute.imgAttr, imgData, SciCamPixelType.RGB8, pDstData,
                                                dstImgSize, True)
            if reVal == SCI_CAMERA_OK:
                reVal = SciCam_Payload_SaveImage(save_file_param, SciCamPixelType.RGB8, pDstData, imgWidth, imgHeight)

    if reVal == SCI_CAMERA_OK:
        msg = f"Image saved successfully: {save_file_param}"
        print(msg + "\n")
    else:
        msg = f"ERROR: Save image failed, error code: {reVal}"
        print(msg + "\n")
        m_currentCam.SciCam_FreePayload(ppayload)
        m_currentCam.SciCam_StopGrabbing()
        m_currentCam.SciCam_CloseDevice()
        m_currentCam.SciCam_DeleteDevice()
        if callback:
            callback(False, msg, None)
        return False

    m_currentCam.SciCam_FreePayload(ppayload)

    # Step 5: Stop grabbing
    print("[Step 5/6] Stopping grabbing...")
    reVal = m_currentCam.SciCam_StopGrabbing()
    if reVal != SCI_CAMERA_OK:
        print(f"WARNING: Stop grabbing failed, error code: {reVal}")
    else:
        print("Grabbing stopped!\n")

    # Step 6: Close device
    print("[Step 6/6] Closing device...")
    reVal = m_currentCam.SciCam_CloseDevice()
    if reVal != SCI_CAMERA_OK:
        print(f"WARNING: Close device failed, error code: {reVal}")
    else:
        m_currentCam.SciCam_DeleteDevice()
        print("Device closed!\n")

    if callback:
        callback(True, "Capture successful!", save_file_param)

    return True

def uint32_to_ipv4(ip_uint32):
    """Convert uint32 IP address to dotted decimal format"""
    network_order_ip = socket.htonl(ip_uint32)
    packed_ip = struct.pack("!I", network_order_ip)
    ipv4_address = socket.inet_ntoa(packed_ip)
    return ipv4_address


if __name__ == "__main__":
    success = AutoCaptureFlow()

    if not success:
        print("\n[FAILED] Auto-capture encountered errors.")
        sys.exit(1)
    else:
        print("\n[SUCCESS] Image captured and saved!")
        sys.exit(0)