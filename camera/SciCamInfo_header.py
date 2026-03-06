# coding: utf-8

import ctypes
from ctypes import *
from enum import Enum
from enum import IntEnum

## @~chinese
#  @brief 设备离线事件通知
#  @~english
#  @brief Device offline event notification
SCI_CAM_EVENT_OFFLINE		= 1001

## @~chinese
#  @brief 跳帧事件通知
#  @~english
#  @brief Frame skipping event notification
SCI_CAM_EVENT_FRAME_SKIP	= 5001

## @~chinese
#  @brief 设备传输类型
#  @~english
#  @brief Device transport Type
class SciCamTLType(IntEnum):
	## @~chinese
	#  @brief 未知类型
	#  @~english
	#  @brief Unknown type
	SciCam_TLType_Unkown = 0
	## @~chinese
	#  @brief 千兆以太网
	#  @~english
	#  @brief Gigabit ethernet
	SciCam_TLType_Gige = 1
	## @~chinese
	#  @brief USB 3.0
	#  @~english
	#  @brief USB 3.0
	SciCam_TLType_Usb3 = 2
	## @~chinese
	#  @brief CameraLink
	#  @~english
	#  @brief CameraLink
	SciCam_TLType_CL = 4
	## @~chinese
	#  @brief CoaXPress
	#  @~english
	#  @brief CoaXPress
	SciCam_TLType_CXP = 8
	## @~chinese
	#  @brief 1394-based Digital Camera Specification
	#  @~english
	#  @brief 1394-based Digital Camera Specification
	SciCam_TLType_IIDC = 16
	## @~chinese
	#  @brief USB Video Class
	#  @~english
	#  @brief USB Video Class
	SciCam_TLType_UVC = 32
	## @~chinese
	#  @brief Camera Link HS
	#  @~english
	#  @brief Camera Link HS
	SciCam_TLType_CLHS = 64
	## @~chinese
	#  @brief Ethernet
	#  @~english
	#  @brief Ethernet
	SciCam_TLType_Ethernet = 128
	## @~chinese
	#  @brief Peripheral Component Interconnect
	#  @~english
	#  @brief Peripheral Component Interconnect
	SciCam_TLType_PCI = 256
	## @~chinese
	#  @brief 仅支持CameraLink
	#  @~english
	#  @brief Only supports CameraLink
	SciCam_TLType_CL_CAM_ONLY = 32768

## @~chinese
#  @brief 设备类型
#  @brief
#  @~english
#  @brief Device Type
class SciCamDeviceType(IntEnum):
	## @~chinese
	#  @brief 未知类型
	#  @~english
	#  @brief Unknown type
	SciCam_DeviceType_Unknown = 0
	## @~chinese
	#  @brief 2D设备
	#  @~english
	#  @brief 2D device
	SciCam_DeviceType_2D = 2
	## @~chinese
	#  @brief 3D线扫激光设备
	#  @~english
	#  @brief 3D LP device
	SciCam_DeviceType_3DLP = 3

## @~chinese
#  @brief 采集策略
#  @~english
#  @brief Grabbing strategy
class SciCamGrabStrategy(IntEnum):
	## @~chinese
	#  @brief 从旧到新一帧一帧的从输出缓存列表中获取图像，打开设备后默认为该策略
	#  @~english
	#  @brief Obtain image from output cache list frame by frame in order, this function is default strategy when device is on.
	SciCam_GrabStrategy_OneByOne = 0
	## @~chinese
	#  @brief 从输出缓存列表中获取最新的帧图像
	#  @~english
	#  @brief Retrieve the latest frame image from the output buffer list.
	SciCam_GrabStrategy_Latest = 1
	## @~chinese
	#  @brief 在调用取流接口时忽略输出缓存列表中所有图像，并等待设备即将生成的一帧图像
	#  @~english
	#  @brief Ignore all images in output cache list when calling image acuiqisiotn interface, wait the next upcoming image generated.
	SciCam_GrabStrategy_Upcoming = 2

## @~chinese
#  @brief 设备XML类型
#  @~english
#  @brief Device XML type
class SciCamDeviceXmlType(IntEnum):
	## @~chinese
	#  @brief 相机
	#  @~english
	#  @brief Camera
	SciCam_DeviceXml_Camera = 0
	## @~chinese
	#  @brief 采集卡
	#  @~english
	#  @brief Capture card
	SciCam_DeviceXml_Card = 1
	## @~chinese
	#  @brief 传输层
	#  @~english
	#  @brief Transport layer
	SciCam_DeviceXml_TL = 2
	## @~chinese
	#  @brief 接口层
	#  @~english
	#  @brief Interface layer
	SciCam_DeviceXml_IF = 3
	## @~chinese
	#  @brief 数据流
	#  @~english
	#  @brief Data stream
	SciCam_DeviceXml_DS = 4

## @~chinese
#  @brief 节点类型
#  @~english
#  @brief Node type
class SciCamNodeType(IntEnum):
	## @~chinese
	#  @brief 未知类型
	#  @~english
	#  @brief Unknown type
	SciCam_NodeType_Unknown = 0
	## @~chinese
	#  @brief bool类型
	#  @~english
	#  @brief bool type
	SciCam_NodeType_Bool = 1
	## @~chinese
	#  @brief int类型
	#  @~english
	#  @brief int type
	SciCam_NodeType_Int = 2
	## @~chinese
	#  @brief float类型
	#  @~english
	#  @brief float type
	SciCam_NodeType_Float = 3
	## @~chinese
	#  @brief enum类型
	#  @~english
	#  @brief enum type
	SciCam_NodeType_Enum = 4
	## @~chinese
	#  @brief cmd类型
	#  @~english
	#  @brief cmd type
	SciCam_NodeType_Cmd = 5
	## @~chinese
	#  @brief string类型
	#  @~english
	#  @brief string type
	SciCam_NodeType_String = 6
	## @~chinese
	#  @brief category类型
	#  @~english
	#  @brief category type
	SciCam_NodeType_Category = 7
	## @~chinese
	#  @brief register类型
	#  @~english
	#  @brief register type
	SciCam_NodeType_Register = 8

## @~chinese
#  @brief 设备节点命名空间
#  @~english
#  @brief Device node namespace
class SciCamNodeNameSpace(IntEnum):
	## @~chinese
	#  @brief 自定义命名空间
	#  @~english
	#  @brief Custom namespace
	SciCam_NodeNameSpace_Custom = 0
	## @~chinese
	#  @brief 标准命名空间
	#  @~english
	#  @brief Standard namespace
	SciCam_NodeNameSpace_Standard = 1
	## @~chinese
	#  @brief 未知命名空间
	#  @~english
	#  @brief Unknown namespace
	SciCam_NodeNameSpace_Unknown = 2

## @~chinese
#  @brief 节点分组可见性类型
#  @~english
#  @brief Device node visibility
class SciCamNodeVisibility(IntEnum):
	## @~chinese
	#  @brief 初学者可见
	#  @~english
	#  @brief Visibility for beginners user
	SciCam_NodeVisibility_Beginner = 0
	## @~chinese
	#  @brief 专家可见
	#  @~english
	#  @brief Visibility for expert user
	SciCam_NodeVisibility_Expert = 1
	## @~chinese
	#  @brief 高级用户（骨灰级）可见
	#  @~english
	#  @brief Visibility for guru user
	SciCam_NodeVisibility_Guru = 2
	## @~chinese
	#  @brief 不可见性
	#  @~english
	#  @brief Invisible visibility
	SciCam_NodeVisibility_Invisible = 3
	## @~chinese
	#  @brief 未知可见性
	#  @~english
	#  @brief Unknown visibility
	SciCam_NodeVisibility_Unknown = 99

## @~chinese
#  @brief 设备节点访问模式
#  @~english
#  @brief Device node access mode
class SciCamNodeAccessMode(IntEnum):
	## @~chinese
	#  @brief 不可用
	#  @~english
	#  @brief Not implemented
	SciCam_NodeAccessMode_NI = 0
	## @~chinese
	#  @brief 不可访问
	#  @~english
	#  @brief Not accessible
	SciCam_NodeAccessMode_NA = 1
	## @~chinese
	#  @brief 只写
	#  @~english
	#  @brief Write only
	SciCam_NodeAccessMode_WO = 2
	## @~chinese
	#  @brief 只读
	#  @~english
	#  @brief Read only
	SciCam_NodeAccessMode_RO = 3
	## @~chinese
	#  @brief 读写
	#  @~english
	#  @brief Read/Write
	SciCam_NodeAccessMode_RW = 4
	## @~chinese
	#  @brief 未知模式
	#  @~english
	#  @brief Unknown mode
	SciCam_NodeAccessMode_Unknown = 5
	## @~chinese
	#  @brief 循环检测
	#  @~english
	#  @brief Cycle detect
	SciCam_NodeAccessMode_CycleDetect = 6

## @struct _SCI_DEVICE_GIGE_INFO_
#  @~chinese
#  @brief GigE设备信息结构体
#  @details 包含设备的状态、名称、制造商等信息
#  @param status 设备状态
#  @param name 设备名称
#  @param manufactureName 制造商名称
#  @param modelName 型号名称
#  @param version 版本号
#  @param userDefineName 用户自定义名称
#  @param serialNumber 序列号
#  @param mac 设备MAC地址
#  @param ip 设备IP地址
#  @param mask 设备子网掩码
#  @param gateway 设备网关
#  @param adapterIp 主机IP地址
#  @param adapterMask 主机子网掩码
#  @param adapterName 主机网卡名
#  @~english
#  @brief GigE device info structure
#  @details Contains device status, name, manufacturer and other information
#  @param status Device status
#  @param name Device name
#  @param manufactureName Manufacture name
#  @param modelName Model name
#  @param version Version
#  @param userDefineName User define name
#  @param serialNumber Serial number
#  @param mac Device MAC address
#  @param ip Device IP address
#  @param mask Device subnet mask
#  @param gateway Device gateway
#  @param adapterIp Host IP address
#  @param adapterMask Host subnet mask
#  @param adapterName Host network adapter name
class _SCI_DEVICE_GIGE_INFO_(ctypes.Structure):
	_fields_ = [
		('status', c_ubyte),
		('name', c_ubyte * 64),
		('manufactureName', c_ubyte * 32),
		('modelName', c_ubyte * 32),
		('version', c_ubyte * 32),
		('userDefineName', c_ubyte * 16),
		('serialNumber', c_ubyte * 16),
		('mac', c_ubyte * 6),
		('ip', c_uint),
		('mask', c_uint),
		('gateway', c_uint),
		('adapterIp', c_uint),
		('adapterMask', c_uint),
		('adapterName', c_ubyte * 260)]

## @~chinese
#  @brief GigE设备信息
#  @~english
#  @brief GigE device info
SCI_DEVICE_GIGE_INFO = _SCI_DEVICE_GIGE_INFO_
## @~chinese
#  @brief GigE设备信息指针
#  @~english
#  @brief GigE device info pointer
PSCI_DEVICE_GIGE_INFO = ctypes.POINTER(_SCI_DEVICE_GIGE_INFO_)

## @~chinese
#  @brief USB3.0 设备信息
#  @details 包含设备的状态、名称、制造商等信息
#  @param status 设备状态
#  @param name 设备名称
#  @param manufactureName 制造商名称
#  @param modelName 型号名称
#  @param version 版本号
#  @param userDefineName 用户自定义名称
#  @param serialNumber 序列号
#  @param guid GUID
#  @param U3VVersion U3V版本号
#  @param GenCPVersion GenCP版本号
#  @~english
#  @brief USB3.0 device info
#  @details Contains device status, name, manufacturer and other information
#  @param status Device status
#  @param name Device name
#  @param manufactureName Manufacture name
#  @param modelName Model name
#  @param version Version
#  @param userDefineName User define name
#  @param serialNumber Serial number
#  @param guid GUID
#  @param U3VVersion U3V version
#  @param GenCPVersion GenCP version
class _SCI_DEVICE_USB3_INFO_(ctypes.Structure):
	_fields_ = [
		('status', c_ubyte),
		('name', c_ubyte * 64),
		('manufactureName', c_ubyte * 64),
		('modelName', c_ubyte * 64),
		('version', c_ubyte * 64),
		('userDefineName', c_ubyte * 64),
		('serialNumber', c_ubyte * 64),
		('guid', c_ubyte * 64),
		('U3VVersion', c_ubyte * 64),
		('GenCPVersion', c_ubyte * 64)]

## @~chinese
#  @brief USB3.0设备信息
#  @~english
#  @brief USB3.0 device info
SCI_DEVICE_USB3_INFO = _SCI_DEVICE_USB3_INFO_
## @~chinese
#  @brief USB3.0设备信息指针
#  @~english
#  @brief USB3.0 device info pointer
PSCI_DEVICE_USB3_INFO = ctypes.POINTER(_SCI_DEVICE_USB3_INFO_)

## @~chinese
#  @brief CameraLink 设备信息
#  @details 包含设备的状态、名称、制造商等信息
#  @param cardStatus 采集卡状态
#  @param cardName 采集卡名称
#  @param cardManufacture 采集卡制造商名称
#  @param cardModel 采集卡型号
#  @param cardVersion 采集卡版本号
#  @param cardUserDefineName 采集卡用户自定义名称
#  @param cardSerialNumber 采集卡序列号
#  @param cameraStatus 相机状态
#  @param cameraType 相机类型
#  @param cameraBaud 相机波特率
#  @param cameraManufacture 相机制造商名称
#  @param cameraFamily 相机家族
#  @param cameraModel 相机型号
#  @param cameraVersion 相机版本号
#  @param cameraSerialNumber 相机序列号
#  @param cameraSerialPort 相机串口号
#  @param cameraProtocol 相机协议
#  @~english
#  @brief CameraLink device info
#  @details Contains device status, name, manufacturer and other information
#  @param cardStatus Card status
#  @param cardName Card name
#  @param cardManufacture Card manufacture name
#  @param cardModel Card model
#  @param cardVersion Card version
#  @param cardUserDefineName Card user define name
#  @param cardSerialNumber Card serial number
#  @param cameraStatus Camera status
#  @param cameraType Camera type
#  @param cameraBaud Camera baud
#  @param cameraManufacture Camera manufacture name
#  @param cameraFamily Camera family
#  @param cameraModel Camera model
#  @param cameraVersion Camera version
#  @param cameraSerialNumber Camera serial number
#  @param cameraSerialPort Camera serial port
#  @param cameraProtocol Camera protocol
class _SCI_DEVICE_CL_INFO_(ctypes.Structure):
	_fields_ = [
		('cardStatus', c_ubyte),
		('cardName', c_ubyte * 64),
		('cardManufacture', c_ubyte * 64),
		('cardModel', c_ubyte * 64),
		('cardVersion', c_ubyte * 64),
		('cardUserDefineName', c_ubyte * 64),
		('cardSerialNumber', c_ubyte * 64),
		('cameraStatus', c_ubyte),
		('cameraType', c_ubyte),
		('cameraBaud', c_uint),
		('cameraManufacture', c_ubyte * 64),
		('cameraFamily', c_ubyte * 64),
		('cameraModel', c_ubyte * 64),
		('cameraVersion', c_ubyte * 64),
		('cameraSerialNumber', c_ubyte * 64),
		('cameraSerialPort', c_ubyte * 64),
		('cameraProtocol', c_ubyte * 256)]

## @~chinese
#  @brief CameraLink设备信息
#  @~english
#  @brief CameraLink device info
SCI_DEVICE_CL_INFO = _SCI_DEVICE_CL_INFO_
## @~chinese
#  @brief CameraLink设备信息指针
#  @~english
#  @brief CameraLink device info pointer
PSCI_DEVICE_CL_INFO = ctypes.POINTER(_SCI_DEVICE_CL_INFO_)

## @~chinese
#  @brief CXP 设备信息
#  @details 包含设备的状态、名称、制造商等信息
#  @param extend 预留扩展
#  @~english
#  @brief CXP device info
#  @details Contains device status, name, manufacturer and other information
#  @param extend Reserved for extension
class _SCI_DEVICE_CXP_INFO_(ctypes.Structure):
	_fields_ = [('extend', c_ubyte * 2048)]

## @~chinese
#  @brief CXP设备信息
#  @~english
#  @brief CXP device info
SCI_DEVICE_CXP_INFO = _SCI_DEVICE_CXP_INFO_
## @~chinese
#  @brief CXP设备信息指针
#  @~english
#  @brief CXP device info pointer
PSCI_DEVICE_CXP_INFO = ctypes.POINTER(_SCI_DEVICE_CXP_INFO_)

## @~chinese
#  @brief 设备信息联合体
#  @details 包含了不同类型设备的详细信息
#  @param gigeInfo GigE设备信息
#  @param usb3Info USB3.0设备信息
#  @param clInfo CameraLink设备信息
#  @param cxpInfo CXP设备信息
#  @~english
#  @brief Device info union
#  @details Contains detailed information for different types of devices
#  @param gigeInfo GigE device info
#  @param usb3Info USB3.0 device info
#  @param clInfo CameraLink device info
#  @param cxpInfo CXP device info
class SCI_DEVICE_INFO_INFO_UNION(ctypes.Union):
	_fields_ = [
		("gigeInfo", SCI_DEVICE_GIGE_INFO),
		("usb3Info", SCI_DEVICE_USB3_INFO),
		("clInfo", SCI_DEVICE_CL_INFO),
		("cxpInfo", SCI_DEVICE_CXP_INFO)]

#  @~chinese
#  @brief 设备信息结构体
#  @details 包含设备传输类型、预留扩展和设备信息联合体
#  @param tlType 设备传输类型，参考@ref SciCamTLType "传输层类型"
#  @param devType 设备类型，参考@ref SciCamDevType "设备类型"
#  @param reserve 预留扩展字段
#  @param info 设备信息联合体，包含不同类型设备的详细信息
#  @~english
#  @brief Device info structure
#  @details Contains device transport type, reserved extension, and device info union
#  @param tlType Device transport layer type, reference @ref SciCamTLType "Transport Layer Type"
#  @param devType Device type, reference @ref SciCamDevType "Device Type"
#  @param reserve Reserved for extension
#  @param info Device info union containing detailed information for different device types
class _SCI_DEVICE_INFO_(ctypes.Structure):
	_fields_ = [
		('tlType', ctypes.c_int),
		("devType", ctypes.c_int),
		("reserve", ctypes.c_ubyte * 256),
		("info", SCI_DEVICE_INFO_INFO_UNION)]

## @~chinese
#  @typedef SCI_DEVICE_INFO
#  @brief 设备信息结构体
#  @~english
#  @typedef SCI_DEVICE_INFO
#  @brief Device info structure
SCI_DEVICE_INFO = _SCI_DEVICE_INFO_
## @~chinese
#  @typedef PSCI_DEVICE_INFO
#  @brief 设备信息结构体指针
#  @~english
#  @typedef PSCI_DEVICE_INFO
#  @brief Device info structure pointer
PSCI_DEVICE_INFO = ctypes.POINTER(_SCI_DEVICE_INFO_)

## @~chinese
#  @brief 设备信息列表
#  @details 包含在线设备数量和设备信息数组
#  @param count 在线设备数量
#  @param pDevInfo 设备信息数组（最多支持256个设备）
#  @~english
#  @brief Device info list
#  @details Contains the number of online devices and the device information array
#  @param count Number of online devices
#  @param pDevInfo Device information array (Supports up to 256 devices)
class _SCI_DEVICE_INFO_LIST_(ctypes.Structure):
	_fields_ = [
		("count", ctypes.c_uint),
		("pDevInfo", SCI_DEVICE_INFO * 256)]

## @~chinese
#  @brief 设备信息列表
#  @~english
#  @brief Device info list
SCI_DEVICE_INFO_LIST = _SCI_DEVICE_INFO_LIST_
## @~chinese
#  @brief 设备信息列表指针
#  @~english
#  @brief Device info list pointer
PSCI_DEVICE_INFO_LIST = ctypes.POINTER(_SCI_DEVICE_INFO_LIST_)

## @~chinese
#  @brief Int类型值
#  @details 包含当前值、最大值、最小值和步长
#  @param nVal 当前值
#  @param nMax 最大值
#  @param nMin 最小值
#  @param nInc 步长
#  @~english
#  @brief Int Value
#  @details Contains current value, maximum value, minimum value, and step
#  @param nVal Current value
#  @param nMax Maximum value
#  @param nMin Minimum value
#  @param nInc Step
class _SCI_NODE_VAL_INT_(ctypes.Structure):
	_fields_ = [
		('nVal', ctypes.c_int64),
		('nMax', ctypes.c_int64),
		('nMin', ctypes.c_int64),
		('nInc', ctypes.c_int64)]
## @~chinese
#  @brief Int类型值
#  @~english
#  @brief Int Value
SCI_NODE_VAL_INT = _SCI_NODE_VAL_INT_
## @~chinese
#  @brief Int类型值指针
#  @~english
#  @brief Int Value pointer
PSCI_NODE_VAL_INT = ctypes.POINTER(_SCI_NODE_VAL_INT_)

## @~chinese
#  @brief Float类型值
#  @details 包含当前值、最大值、最小值和步长
#  @param dVal 当前值
#  @param dMax 最大值
#  @param dMin 最小值
#  @param dInc 步长
#  @~english
#  @brief Float Value
#  @details Contains current value, maximum value, minimum value, and step
#  @param dVal Current value
#  @param dMax Maximum value
#  @param dMin Minimum value
#  @param dInc Step
class _SCI_NODE_VAL_FLOAT_(ctypes.Structure):
	_fields_ = [
		("dVal", ctypes.c_double),
		("dMax", ctypes.c_double),
		("dMin", ctypes.c_double),
		("dInc", ctypes.c_double)]

## @~chinese
#  @brief Float类型值
#  @~english
#  @brief Float Value
SCI_NODE_VAL_FLOAT = _SCI_NODE_VAL_FLOAT_
## @~chinese
#  @brief Float类型值指针
#  @~english
#  @brief Float Value pointer
PSCI_NODE_VAL_FLOAT = ctypes.POINTER(_SCI_NODE_VAL_FLOAT_)

## @~chinese
#  @brief String类型值
#  @details 包含当前值
#  @param val 当前值
#  @~english
#  @brief String Value
#  @details Contains current value
#  @param val Current value
class _SCI_NODE_VAL_STRING_(ctypes.Structure):
	_fields_ = [
		("val", ctypes.c_char * 1024)]

## @~chinese
#  @brief String类型值
#  @~english
#  @brief String Value
SCI_NODE_VAL_STRING = _SCI_NODE_VAL_STRING_
## @~chinese
#  @brief String类型值指针
#  @~english
#  @brief String Value pointer
PSCI_NODE_VAL_STRING = ctypes.POINTER(_SCI_NODE_VAL_STRING_)

## @~chinese
#  @brief Enum item值
#  @details 包含枚举值和枚举描述
#  @param val 枚举值
#  @param desc 枚举描述
#  @~english
#  @brief Enum item Value
#  @details Contains enumerated value and enumeration description
#  @param val Enumerated value
#  @param desc Enumeration description
class _SCI_NODE_VAL_ENUM_ITEM_(ctypes.Structure):
	_fields_ = [
		("val", ctypes.c_int64),
		("desc", ctypes.c_char * 256)]

## @~chinese
#  @brief Enum item值
#  @~english
#  @brief Enum item Value
SCI_NODE_VAL_ENUM_ITEM = _SCI_NODE_VAL_ENUM_ITEM_
## @~chinese
#  @brief Enum item值指针
#  @~english
#  @brief Enum item Value pointer
PSCI_NODE_VAL_ENUM_ITEM = ctypes.POINTER(_SCI_NODE_VAL_ENUM_ITEM_)

## @~chinese
#  @brief Enum类型值
#  @details 包含当前值、有效数据个数和枚举项
#  @param nVal 当前值
#  @param itemCount 有效数据个数
#  @param items 枚举项
#  @~english
#  @brief Enum Value
#  @details Contains current value, number of valid data, and enumerated items
#  @param nVal Current value
#  @param itemCount Number of valid data
#  @param items Enumerated items
class _SCI_NODE_VAL_ENUM_(ctypes.Structure):
	_fields_ = [
		("nVal", ctypes.c_int64),
		("itemCount", ctypes.c_uint),
		("items", SCI_NODE_VAL_ENUM_ITEM * 64)]

## @~chinese
#  @brief Enum类型值
#  @~english
#  @brief Enum Value
SCI_NODE_VAL_ENUM = _SCI_NODE_VAL_ENUM_
## @~chinese
#  @brief Enum类型值指针
#  @~english
#  @brief Enum Value pointer
PSCI_NODE_VAL_ENUM = ctypes.POINTER(_SCI_NODE_VAL_ENUM_)

## @~chinese
#  @brief 设备节点
#  @details 包含节点类型、名字空间、可见性、节点层级、节点名称和描述
#  @param type 节点类型
#  @param nameSpace 名字空间
#  @param accessMode 可见性
#  @param level 节点层级
#  @param name 节点名称
#  @param desc 描述
#  @~english
#  @brief Device node
#  @details Contains node type, namespace, visibility, node level, node name, and description
#  @param type Node type
#  @param nameSpace Namespace
#  @param accessMode Visibility
#  @param level Node level
#  @param name Node name
#  @param desc Description
class _SCI_CAM_NODE_(ctypes.Structure):
	_fields_ = [
		("type", ctypes.c_int),
		("nameSpace", ctypes.c_int),
		("visibility", ctypes.c_int),
		("accessMode", ctypes.c_int),
		("level", ctypes.c_int),
		("name", ctypes.c_char * 256),
		("desc", ctypes.c_char * 256)]

## @~chinese
#  @brief 设备节点
#  @~english
#  @brief Device node
SCI_CAM_NODE = _SCI_CAM_NODE_
## @~chinese
#  @brief 设备节点指针
#  @~english
#  @brief Device node pointer
PSCI_CAM_NODE = ctypes.POINTER(_SCI_CAM_NODE_)

## @~chinese
#  @brief 设备事件
#  @details 包含事件ID、事件时间戳和事件数据
#  @param id 事件ID
#  @param tick 事件时间戳（单位：us）
#  @param data 事件数据
#  @param len 事件数据长度
#  @~english
#  @brief Device event
#  @details Contains event ID, event timestamp, and event data
#  @param id Event ID
#  @param tick Event timestamp(unit: us)
#  @param data Event data
#  @param len Event data length
class _SCI_CAM_EVENT_(ctypes.Structure):
	_fields_ = [
		("id", ctypes.c_uint64),
		("tick", ctypes.c_uint64),
		("data", ctypes.c_void_p),
		("len", ctypes.c_uint64)]

## @~chinese
#  @brief 设备事件
#  @~english
#  @brief Device event
SCI_CAM_EVENT = _SCI_CAM_EVENT_
## @~chinese
#  @brief 设备事件指针
#  @~english
#  @brief Device event pointer
PSCI_CAM_EVENT = ctypes.POINTER(_SCI_CAM_EVENT_)

## @~chinese
#  @brief 3D线扫激光轮廓设备采集模式
#  @~english
#  @brief 3D LP camera grab mode
class SciCamLp3dGrabMode(IntEnum):
	## @~chinese
	#  @brief 无
	#  @~english
	#  @brief None
	SciCam_GrabMode_LP3D_None = 0
	## @~chinese
	#  @brief 2D图像
	#  @~english
	#  @brief Image mode
	SciCam_GrabMode_LP3D_Image = 1
	## @~chinese
	#  @brief 轮廓
	#  @~english
	#  @brief Contour mode
	SciCam_GrabMode_LP3D_Contour = 2
	## @~chinese
	#  @brief 3D深度图
	#  @~english
	#  @brief Batch Contour mode
	SciCam_GrabMode_LP3D_BatchContour = 3