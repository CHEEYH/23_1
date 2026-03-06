from camera.SciCamErrorDefine_const import *
from camera.SciCamPayload_header import *
from camera.SciCamInfo_header import *


class SciCamera():
    ## @ingroup module_Other
    #  @~chinese
    #  @brief ��ʼ��
    #  @param NULL
    #  @retval NULL
    #  @remarks �ӿڳ�ʼ��
    #  @~english
    #  @brief Initialize
    #  @param NULL
    #  @retval NULL
    #  @remarks Initialize the interface
    def __init__(self):
        self._handle = ctypes.c_void_p()
        self.handle = pointer(self._handle)

    ## @~chinese
    #  @brief ԭʼ���ݻص��������Ͷ���
    #  @details ����ע��ͼ�����ݻ��������ݵĻص�����
    #  @param payload [IN] �ɼ�����payload���ݣ�������ͼ�����ݻ���������
    #  @param tag [IN] �û��Զ�����������ڴ����û�����
    #  @retval NULL
    #  @remarks �ú�����������SciCam_RegisterPayloadCallBack�ӿ�
    #  @~english
    #  @brief Raw data callback function type definition
    #  @details Used to register callback functions for image data or contour data
    #  @param payload [IN] Acquired payload data, can be image data or contour data
    #  @param tag [IN] User-defined parameter for passing user data
    #  @retval NULL
    #  @remarks This function type is used for SciCam_RegisterPayloadCallBack interface
    fnOnPayload = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)

    ## @ingroup module_SDKVersionInfo
    #  @~chinese
    #  @brief ��ȡSDK�汾��
    #  @param NULL
    #  @retval ����4�ֽڰ汾��:
    #  | ���汾 | �ΰ汾 | �����汾 | ���԰汾 |
    #  | --- | --- | --- | --- |
    #  | 8bits | 8bits | 8bits | 8bits |
    #  @remarks ���緵��ֵΪ0x01000001����SDK�汾��ΪV1.0.0.1
    #  @~english
    #  @brief Get SDK Version
    #  @param NULL
    #  @retval Always return 4 Bytes of version number:
    #  | Main | Sub | Rev | Test |
    #  | --- | --- | --- | --- |
    #  | 8bits | 8bits | 8bits | 8bits |
    #  @remarks For example, if the return value is 0x01000001, the SDK version is V1.0.0.1
    @staticmethod
    def SciCam_GetSDKVersion():
        SciCamCtrlDll.SciCam_GetSDKVersion.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetSDKVersion()

    ## @ingroup module_Other
    #  @~chinese
    #  @brief ����SDK��־���·��
    #  @param logPath [IN] �ļ���·��(����·��)
    #  @retval �ɹ���@ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ���@ref SciCamErrorDefine_const "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Set the SDK log output path
    #  @param logPath [IN] Folder path (absolute path)
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine_const "Error Code List"
    #  @remarks NULL
    @staticmethod
    def SciCam_SetSDKLogPath(logPath):
        SciCamCtrlDll.SciCam_SetSDKLogPath.argtypes = ctypes.c_void_p
        SciCamCtrlDll.SciCam_SetSDKLogPath.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetSDKLogPath(logPath.encode('ascii'))

    ## @ingroup module_DeviceInitAndDestr
    #  @~chinese
    #  @brief �����豸
    #  @param devInfos [OUT] ���������豸�б�����ο���@ref PSCI_DEVICE_INFO_LIST "PSCI_DEVICE_INFO_LIST"
    #  @param tlType [IN] �����������ϣ�0������ȫ����������SciCam_TLType_Gige | SciCam_TLType_Usb3 ������GigE��USB3.0�豸��
    #  @retval �ɹ���@ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ���@ref SciCamErrorDefine_const "״̬��"
    #  @remarks ��tlTypeΪSciCam_TLType_CL_CAM_ONLYʱ��������CL�ɼ����µ������SciCam_TLType_CL_CAM_ONLY����������tlType���л����
    #  @~english
    #  @brief Search for devices
    #  @param devInfos [OUT] List of discovered devices, references: @ref PSCI_DEVICE_INFO_LIST "PSCI_DEVICE_INFO_LIST"
    #  @param tlType [IN] Combination of transport layer types (0: search all, others like SciCam_TLType_Gige | SciCam_TLType_Usb3 only search for GigE and USB3.0 devices)
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine_const "Error Code List"
    #  @remarks When tlType is set to SciCam_TLType_CL_CAM_ONLY, it only searches for cameras under CL capture cards. SciCam_TLType_CL_CAM_ONLY cannot be combined with other tlType values using bitwise OR operations.
    @staticmethod
    def SciCam_DiscoveryDevices(devInfos, tlType):
        SciCamCtrlDll.SciCam_DiscoveryDevices.argtypes = (PSCI_DEVICE_INFO_LIST, ctypes.c_uint)
        SciCamCtrlDll.SciCam_DiscoveryDevices.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_DiscoveryDevices(ctypes.byref(devInfos), ctypes.c_uint(tlType))

    ## @ingroup module_DeviceInitAndDestr
    #  @~chinese
    #  @brief ����������
    #  @param devInfo [IN] �豸��Ϣ�ṹ�壬����ο���@ref PSCI_DEVICE_INFO "PSCI_DEVICE_INFO"
    #  @retval �ɹ���@ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ���@ref SciCamErrorDefine_const "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Create Device Handle
    #  @param devInfo [IN] Device Information Structure, references: @ref PSCI_DEVICE_INFO "PSCI_DEVICE_INFO"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine_const "Error Code List"
    #  @remarks NULL
    def SciCam_CreateDevice(self, devInfo):
        SciCamCtrlDll.SciCam_CreateDevice.argtypes = (ctypes.c_void_p, PSCI_DEVICE_INFO)
        SciCamCtrlDll.SciCam_CreateDevice.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_CreateDevice(ctypes.byref(self.handle), devInfo)

    ## @ingroup module_DeviceInitAndDestr
    #  @~chinese
    #  @brief �����豸���
    #  @retval �ɹ���@ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ���@ref SciCamErrorDefine_const "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Destroy Device Handle
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine_const "Error Code List"
    #  @remarks NULL
    def SciCam_DeleteDevice(self):
        SciCamCtrlDll.SciCam_DeleteDevice.argtype = ctypes.c_void_p
        SciCamCtrlDll.SciCam_DeleteDevice.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_DeleteDevice(self.handle)

    ## @ingroup module_Other
    #  @~chinese
    #  @brief ע���豸�����¼�
    #  @param hDev		[IN] �豸���
    #  @param fn		[IN] �ص�����ָ��
    #  @param tag		[IN] �û��Զ������
    #  @retval NULL
    #  @remarks ͨ��ע��ص���ʽ����ʵʱ��ȡ��������ߡ����ߵ�֪ͨ��Ϣ
    #  @~english
    #  @brief Registering device monitoring events
    #  @param payload	[IN] Device event
    #  @param fn		[IN] Callback function pointer
    #  @param tag		[IN] User-defined parameters
    #  @retval NULL
    #  @remarks By registering a callback, you can receive real-time notification messages such as camera online/offline events.
    def SciCam_RegisterEventCallback(self, CallBackFun, tag):
        SciCamCtrlDll.SciCam_RegisterEventCallback.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_RegisterEventCallback.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_RegisterEventCallback(self.handle, CallBackFun, tag)

    ## @ingroup module_DeviceInitAndDestr
    #  @~chinese
    #  @brief ���豸
    #  @param hDev	[IN]  �豸���
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks ����GigE��U3V�豸Ϊ�������CL�豸Ϊ�򿪲ɼ������ɲο�SciCam_CL_OpenCam
    #  @~english
    #  @brief Open Device
    #  @param hDev	[IN]  Device handle
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks For opening cameras with GigE and U3V devices, and for opening capture cards with CL devices, refer to SciCam_CL_OpenCam
    def SciCam_OpenDevice(self):
        SciCamCtrlDll.SciCam_OpenDevice.argtype = ctypes.c_void_p
        SciCamCtrlDll.SciCam_OpenDevice.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_OpenDevice(self.handle)

    ## @ingroup module_DeviceInitAndDestr
    #  @~chinese
    #  @brief �ر��豸
    #  @param hDev	[IN]  �豸���
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks ͨ��SciCam_OpenDevice�����豸�󣬿���ͨ���ýӿڶϿ��豸���ӣ��ͷ���Դ�������CL�豸���رղɼ���ʱ��Ѳɼ����µ��������һ��ر�
    #  @~english
    #  @brief Close Device
    #  @param hDev	[IN]  Device handle
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After connecting to the device through SciCam_OpenDevice, you can use this interface to disconnect the device and release resources. If it is a CL device, closing the capture card will also close all cameras under the capture card.
    def SciCam_CloseDevice(self):
        SciCamCtrlDll.SciCam_CloseDevice.argtype = ctypes.c_void_p
        SciCamCtrlDll.SciCam_CloseDevice.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_CloseDevice(self.handle)

    ## @ingroup module_DeviceInitAndDestr
    #  @~chinese
    #  @brief �ж��豸�Ƿ�������
    #  @param hDev	[IN]  �豸���
    #  @retval true: �豸�����ӣ�false���豸δ����
    #  @remarks ����GigE��U3V�豸Ϊ����Ƿ������ӣ�����CL�豸Ϊ�ɼ����Ƿ������ӣ��ɲο�SciCam_CL_IsCamOpen
    #  @~english
    #  @brief Check if the device is connected
    #  @param hDev	[IN]  Device handle
    #  @retval true: Device connected; false: Device not connected
    #  @remarks To check if the camera is connected for GigE and U3V devices, and to check if the capture card is connected for CL devices, refer to SciCam_CL_IsCamOpen.
    def SciCam_IsDeviceOpen(self):
        SciCamCtrlDll.SciCam_IsDeviceOpen.argtype = ctypes.c_void_p
        SciCamCtrlDll.SciCam_IsDeviceOpen.restype = ctypes.c_bool
        return SciCamCtrlDll.SciCam_IsDeviceOpen(self.handle)

    ## @ingroup module_Grab
    #  @~chinese
    #  @brief ע��ԭʼ���ݣ�ͼ������/�������ݣ��ص�
    #  @param hDev		[IN]  �豸���
    #  @param fn		[IN]  �ص�����ָ��
    #  @param tag		[IN]  �Զ������
    #  @param autoFree	[IN]  �ص�ִ�����Ƿ��ͷ�payload��trueΪ�ͷţ�falseΪ���ͷţ��ֶ��ͷ�payload�ɲο���SciCam_FreePayload��
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks ͨ���ýӿڿ�������ͼ�����ݻ��������ݻص��������ڵ���SciCam_CreateDevice֮�󼴿�ʹ�á� \n
    #  		�ɼ�ͼ�����ݻ��������������ַ�ʽ�� \n
    #  		��ʽһ������SciCam_RegisterPayloadCallBack���ûص�������Ȼ�����SciCam_StartGrabbing��ʼ�ɼ����ɼ���ͼ��/�������������õĻص������з��ء� \n
    #  		��ʽ��������SciCam_StartGrabbing��ʼ�ɼ���Ȼ����Ӧ�ò�ѭ������SciCam_Grab��ȡ�õ�ͼ��/�������ݡ� \n
    #  		���÷�ʽ����ȡpayload����ʱ��Ӧ�ò������֡�ʿ��ƺõ��øýӿڵ�Ƶ�ʡ�
    #  		��ȡ����payload���ݿ�ͨ��SciCamPayload.h����Ӧ�Ľӿڻ�ȡ��payload������ԣ�ת�����������ݸ�ʽ��
    #  @~english
    #  @brief Register callback for raw data (image data/contour data).
    #  @param hDev		[IN]  Device handle
    #  @param fn		[IN]  Callback function pointer
    #  @param tag		[IN]  user defined parameters
    #  @param autoFree	[IN]  Whether to release the payload after the callback execution, true for release, false for not release (manually releasing payload can refer to: SciCam_FreePayload).
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks This interface allows you to set a callback function for image data or contour data, and it can be used after calling SciCam_CreateDevice. \n
    #  		There are two methods for capturing image data or contour data: \n
    #  		Method 1: Call SciCam_RegisterPayloadCallBack to set the callback function, then call SciCam_StartGrabbing to start capturing. The captured image/contour data will be returned in the set callback function. \n
    #  		Method 2: Call SciCam_StartGrabbing to start capturing, then in the application layer, loop calls SciCam_Grab to obtain image/contour data. \n
    #  		When using Method 2 to obtain payload data, the application layer should control the frequency of calling this interface based on the frame rate. \n
    #  		The obtained payload data can be converted into the desired data format by using the corresponding interfaces in SciCamPayload.h to access payload-related attributes.
    def SciCam_RegisterPayloadCallBack(self, CallBackFun, tag, autoFree):
        SciCamCtrlDll.SciCam_RegisterPayloadCallBack.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                                                 ctypes.c_bool)
        SciCamCtrlDll.SciCam_RegisterPayloadCallBack.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_RegisterPayloadCallBack(self.handle, CallBackFun, tag, ctypes.c_bool(autoFree))

    ## @ingroup module_Grab
    #  @~chinese
    #  @brief ��ȡ��ǰ�豸�ɼ�����
    #  @param hDev		[IN]  �豸���
    #  @param pStrategy	[OUT] ��ȡ���Ĳɼ����ԣ���ϸ�ο��� @ref SciCamGrabStrategy "SciCamGrabStrategy"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Get the current device acquisition strategy
    #  @param hDev		[IN]  Device handle
    #  @param pStrategy	[OUT] The obtained acquisition strategy, references: @ref SciCamGrabStrategy "SciCamGrabStrategy"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_GetGrabStrategy(self, pStrategy):
        SciCamCtrlDll.SciCam_GetGrabStrategy.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_GetGrabStrategy.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetGrabStrategy(self.handle, ctypes.byref(pStrategy))

    ## @ingroup module_Grab
    #  @~chinese
    #  @brief ���òɼ�����
    #  @param hDev			[IN] �豸���
    #  @param grabStrategy	[IN] �ɼ����ԣ���ϸ�ο��� @ref SciCamGrabStrategy "SciCamGrabStrategy"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Set the acquisition strategy
    #  @param hDev			[IN] Device handle
    #  @param grabStrategy	[IN] Grab strategy, references: @ref SciCamGrabStrategy "SciCamGrabStrategy"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_SetGrabStrategy(self, grabStrategy):
        SciCamCtrlDll.SciCam_SetGrabStrategy.argtypes = (ctypes.c_void_p, ctypes.c_int)
        SciCamCtrlDll.SciCam_SetGrabStrategy.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetGrabStrategy(self.handle, ctypes.c_int(grabStrategy))

    ## @ingroup module_Grab
    #  @~chinese
    #  @brief ��ȡ��ǰ�豸�ɼ�һ֡�ĵȴ���ʱʱ��
    #  @param hDev		[IN]  �豸���
    #  @param pTimeout	[OUT] ��ȡ���ĵȴ���ʱʱ�䣨��λ��ms��
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �ɼ�ʱ���õ��ǳ�ʱ�ȴ����ƣ�����ڳ�ʱ�ȴ�ʱ����δ��ɲɼ�����һ֡��ȴ�������ʱʱ��Ҳû�ɼ���һ֡����᷵�ش����룬��������õȴ���ʱʱ��
    #  @~english
    #  @brief Get the current device timeout waiting time for capturing one frame
    #  @param hDev		[IN]  Device handle
    #  @param pTimeout	[OUT] The obtained timeout waiting time(unit: ms)
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks During capture, a timeout waiting mechanism is used. If capturing a complete frame is not completed within the timeout waiting time or if no frame is captured within the specified timeout, an error code will be returned. Please set the timeout waiting time appropriately.
    def SciCam_GetGrabTimeout(self, pTimeout):
        SciCamCtrlDll.SciCam_GetGrabTimeout.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_GetGrabTimeout.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetGrabTimeout(self.handle, ctypes.byref(pTimeout))

    ## @ingroup module_Grab
    #  @~chinese
    #  @brief ���õ�ǰ�豸�ɼ�һ֡����ĵȴ���ʱʱ��
    #  @param hDev		[IN]  �豸���
    #  @param timeout	[IN]  �ȴ���ʱʱ�䣨��λ��ms��
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �ɼ�ʱ���õ��ǳ�ʱ�ȴ����ƣ�����ڳ�ʱ�ȴ�ʱ����δ��ɲɼ�����һ֡��ȴ�������ʱʱ��Ҳû�ɼ���һ֡����᷵�ش����룬��������õȴ���ʱʱ��
    #  @~english
    #  @brief Set the timeout waiting time required for capturing one frame for the current device.
    #  @param hDev		[IN]  Device handle
    #  @param timeout	[IN]  Timeout waiting time��unit��ms��
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks During capture, a timeout waiting mechanism is used. If capturing a complete frame is not completed within the timeout waiting time or if no frame is captured within the specified timeout, an error code will be returned. Please set the timeout waiting time appropriately.
    def SciCam_SetGrabTimeout(self, timeout):
        SciCamCtrlDll.SciCam_SetGrabTimeout.argtypes = (ctypes.c_void_p, ctypes.c_uint)
        SciCamCtrlDll.SciCam_SetGrabTimeout.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetGrabTimeout(self.handle, ctypes.c_uint(timeout))

    ## @ingroup module_Grab
    #  @~chinese
    #  @brief ��ȡ�ɼ�ʱ������д�С
    #  @param hDev			[IN]  �豸���
    #  @param pBufferCount	[OUT] ��ȡ���Ļ�����д�С
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �������Խ��Խ������Դ����ͬʱҲ�ܼ��ٶ�֡���ʣ��������仺����д�С
    #  @~english
    #  @brief Retrieve the size of the buffer queue during grabbing
    #  @param hDev			[IN]  Device handle
    #  @param pBufferCount	[OUT] The size of the obtained buffer queue
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks A larger buffer queue consumes more resources, but it can also reduce the probability of frame drops. Please allocate the buffer queue size judiciously.
    def SciCam_GetGrabBufferCount(self, pBufferCount):
        SciCamCtrlDll.SciCam_GetGrabBufferCount.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_GetGrabBufferCount.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetGrabBufferCount(self.handle, ctypes.byref(pBufferCount))

    ## @ingroup module_Grab
    #  @~chinese
    #  @brief ���òɼ�ʱ������д�С
    #  @param hDev			[IN]  �豸���
    #  @param pBufferCount	[IN]  ������д�С
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �������Խ��Խ������Դ����ͬʱҲ�ܼ��ٶ�֡���ʣ��������仺����д�С�� \n
    #  			bufferCountΪ0ʱ��ʾ�����ã�ʹ���Ƽ�������ԡ�
    #  @~english
    #  @brief Retrieve the size of the buffer queue during grabbing
    #  @param hDev			[IN]  Device handle
    #  @param pBufferCount	[IN]  Buffer queue size
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks A larger buffer queue consumes more resources, but it can also reduce the probability of frame drops. Please allocate the buffer queue size judiciously. \n
    #  			When bufferCount is set to 0, it indicates that no specific value is set, and the recommended caching strategy should be used.
    def SciCam_SetGrabBufferCount(self, bufferCount):
        SciCamCtrlDll.SciCam_SetGrabBufferCount.argtypes = (ctypes.c_void_p, ctypes.c_uint)
        SciCamCtrlDll.SciCam_SetGrabBufferCount.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetGrabBufferCount(self.handle, ctypes.c_uint(bufferCount))

    ## @ingroup module_Grab
    #  @~chinese
    #  @brief ��ʼ�ɼ�
    #  @param hDev	[IN]  �豸���
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Start grabbing
    #  @param hDev	[IN]  Device handle
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_StartGrabbing(self):
        SciCamCtrlDll.SciCam_StartGrabbing.argtype = ctypes.c_void_p
        SciCamCtrlDll.SciCam_StartGrabbing.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_StartGrabbing(self.handle)

    ## @ingroup module_Grab
    #  @~chinese
    #  @brief ֹͣ�ɼ�
    #  @param hDev	[IN]  �豸���
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Stop grabbing
    #  @param hDev	[IN]  Device handle
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_StopGrabbing(self):
        SciCamCtrlDll.SciCam_StopGrabbing.argtype = ctypes.c_void_p
        SciCamCtrlDll.SciCam_StopGrabbing.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_StopGrabbing(self.handle)

    ## @ingroup module_Grab
    #  @~chinese
    #  @brief �ɼ�һ֡���ݣ�ͼ������/�������ݣ�
    #  @param hDev		[IN]  �豸���
    #  @param ppayload	[OUT] һ֡������
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks ����SciCam_RegisterPayloadCallBack�ӿ�ע��ص�����ýӿڲ����ݣ����ȡ��һʹ�á� \n
    #  		��ȡ����payload���ݿ�ͨ��SciCamPayload.h����Ӧ�Ľӿڻ�ȡ��payload������ԣ�ת�����������ݸ�ʽ�� \n
    #  		֡����ʹ����������SciCam_FreePayload�����ͷţ������豸�޷������ɼ��������
    #  @~english
    #  @brief Grab one frame of data (image data/contour data)
    #  @param hDev		[IN]  Device handle
    #  @param ppayload	[OUT] One frame of data
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After registering a callback using the SciCam_RegisterPayloadCallBack interface, it is not compatible with this interface. Please choose one of them to use. \n
    #  		The obtained payload data can be converted into the desired data format by using the corresponding interfaces in SciCamPayload.h to access payload-related attributes. \n
    #  		After using the frame data, please call SciCam_FreePayload for release to avoid situations where the device cannot continue capturing.
    def SciCam_Grab(self, ppayload):
        SciCamCtrlDll.SciCam_Grab.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
        SciCamCtrlDll.SciCam_Grab.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_Grab(self.handle, ppayload)

    ## @ingroup module_Grab
    #  @~chinese
    #  @brief �ͷ�һ֡���ݣ�ͼ������/�������ݣ�
    #  @param hDev		[IN]  �豸���
    #  @param payload	[IN]  һ֡������
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Release a frame of data (image data/contour data)
    #  @param hDev		[IN]  Device handle
    #  @param payload	[IN]  One frame of data
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_FreePayload(self, payload):
        SciCamCtrlDll.SciCam_FreePayload.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_FreePayload.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_FreePayload(self.handle, payload)

    ## @ingroup module_Grab
    #  @~chinese
    #  @brief ��������������
    #  @param hDev		[IN]  �豸���
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Clear the cache queue data
    #  @param hDev		[IN]  Device handle
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_ClearPayloadBuffer(self):
        SciCamCtrlDll.SciCam_ClearPayloadBuffer.argtype = ctypes.c_void_p
        SciCamCtrlDll.SciCam_ClearPayloadBuffer.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_ClearPayloadBuffer(self.handle)

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡInteger����ֵ
    #  @param hDev		[IN]  �豸���
    #  @param key		[IN]  ���Լ�ֵ�����ȡ�����Ϣ��Ϊ"Width"
    #  @param pVal		[OUT] ���ظ��������й��豸���Խṹ��ָ�룬��ϸ�ο��� @ref PSCI_NODE_VAL_INT "PSCI_NODE_VAL_INT"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ��Ի�ȡint���͵�ָ���ڵ��ֵ��keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IInteger���Ľڵ�ֵ������ͨ���ýӿڻ�ȡ��key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		�˽ӿڽ�������ȡ����豸XML�С�IInteger�����ͽڵ�ֵ��CL��CXP�豸��ο��ӿڣ�SciCam_GetIntValueEx
    #  @~english
    #  @brief Get Integer value
    #  @param hDev		[IN]  Device handle
    #  @param key		[IN]  Key value, for example, using "Width" to get width
    #  @param pVal		[OUT] Structure pointer of camera features, references: @ref PSCI_NODE_VAL_INT "PSCI_NODE_VAL_INT"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks You can call this API to get the value of camera node with integer type after connecting the device. For key value, refer to MvCameraNode. All the node values of "IInteger" in the list can be obtained via this API. Key corresponds to the Name column. \n
    #  		This interface is only used to retrieve the values of "IInteger" type nodes in the camera device XML. For CL and CXP devices, please refer to the interface: SciCam_GetIntValueEx.
    def SciCam_GetIntValue(self, key, pVal):
        SciCamCtrlDll.SciCam_GetIntValue.argtypes = (ctypes.c_void_p, ctypes.c_void_p, PSCI_NODE_VAL_INT)
        SciCamCtrlDll.SciCam_GetIntValue.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetIntValue(self.handle, key.encode('ascii'), ctypes.byref(pVal))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ����Integer������ֵ
    #  @param hDev		[IN]  �豸���
    #  @param key		[IN]  ���Լ�ֵ�����ȡ�����Ϣ��Ϊ"Width"
    #  @param val		[IN]  ��Ҫ���õ��豸������ֵ
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ�������int���͵�ָ���ڵ��ֵ��keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IInteger���Ľڵ�ֵ������ͨ���ýӿ����ã�key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		�˽ӿڽ�������������豸XML�С�IInteger�����ͽڵ�ֵ��CL��CXP�豸��ο��ӿڣ�SciCam_SetIntValueEx
    #  @~english
    #  @brief Set Integer value
    #  @param hDev		[IN]  Device handle
    #  @param key		[IN]  Key value, for example, using "Width" to set width
    #  @param val		[IN]  Feature value to set
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks You can call this API to get the value of camera node with integer type after connecting the device. For key value, refer to MvCameraNode. All the node values of "IInteger" in the list can be obtained via this API. Key corresponds to the Name column. \n
    #  		This interface is only used to set the values of "IInteger" type nodes in the camera device XML. For CL and CXP devices, please refer to the interface: SciCam_SetIntValueEx.
    def SciCam_SetIntValue(self, key, val):
        SciCamCtrlDll.SciCam_SetIntValue.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64)
        SciCamCtrlDll.SciCam_SetIntValue.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetIntValue(self.handle, key.encode('ascii'), ctypes.c_int64(val))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡFloat����ֵ
    #  @param hDev		[IN]  �豸���
    #  @param key		[IN]  ���Լ�ֵ
    #  @param pVal		[OUT] ���ظ��������й��豸���Խṹ��ָ�룬��ϸ�ο��� @ref PSCI_NODE_VAL_FLOAT "PSCI_NODE_VAL_FLOAT"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ��Ի�ȡfloat���͵�ָ���ڵ��ֵ��keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IFloat���Ľڵ�ֵ������ͨ���ýӿڻ�ȡ��key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С�
    #  		�˽ӿڽ�������ȡ����豸XML�С�IFloat�����ͽڵ�ֵ��CL��CXP�豸��ο��ӿڣ�SciCam_GetFloatValueEx
    #  @~english
    #  @brief Get Float value
    #  @param hDev		[IN]  Device handle
    #  @param key		[IN]  Key value
    #  @param pVal		[OUT] Structure pointer of camera features
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to get specified float node. For detailed key value see: MvCameraNode. The node values of IFloat can be obtained through this interface, key value corresponds to the Name column. \n
    #  		This interface is only used to retrieve the values of "IFloat" type nodes in the camera device XML. For CL and CXP devices, please refer to the interface: SciCam_GetFloatValueEx.
    def SciCam_GetFloatValue(self, key, pVal):
        SciCamCtrlDll.SciCam_GetFloatValue.argtypes = (ctypes.c_void_p, ctypes.c_void_p, PSCI_NODE_VAL_FLOAT)
        SciCamCtrlDll.SciCam_GetFloatValue.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetFloatValue(self.handle, key.encode('ascii'), ctypes.byref(pVal))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ����float������ֵ
    #  @param hDev		[IN]  �豸���
    #  @param key		[IN]  ���Լ�ֵ
    #  @param val		[IN]  ��Ҫ���õ��豸������ֵ
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ�������float���͵�ָ���ڵ��ֵ��keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IFloat���Ľڵ�ֵ������ͨ���ýӿ����ã�key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		�˽ӿڽ�������������豸XML�С�IFloat�����ͽڵ�ֵ��CL��CXP�豸��ο��ӿڣ�SciCam_SetFloatValueEx
    #  @~english
    #  @brief Set float value
    #  @param hDev		[IN]  Device handle
    #  @param key		[IN]  Key value
    #  @param val		[IN]  Feature value to set
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to set specified float node. For detailed key value see: MvCameraNode. The node values of IFloat can be set through this interface, key value corresponds to the Name column. \n
    #  		This interface is only used to set the values of "IFloat" type nodes in the camera device XML. For CL and CXP devices, please refer to the interface: SciCam_SetFloatValueEx.
    def SciCam_SetFloatValue(self, key, val):
        SciCamCtrlDll.SciCam_SetFloatValue.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double)
        SciCamCtrlDll.SciCam_SetFloatValue.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetFloatValue(self.handle, key.encode('ascii'), ctypes.c_double(val))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡBoolean����ֵ
    #  @param hDev		[IN]  �豸���
    #  @param key		[IN]  ���Լ�ֵ
    #  @param pVal		[OUT] ���ظ��������й��豸����ֵ
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ��Ի�ȡbool���͵�ָ���ڵ��ֵ��keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IBoolean���Ľڵ�ֵ������ͨ���ýӿڻ�ȡ��key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		�˽ӿڽ�������ȡ����豸XML�С�IBoolean�����ͽڵ�ֵ��CL��CXP�豸��ο��ӿڣ�SciCam_GetBoolValueEx
    #  @~english
    #  @brief Get Boolean value
    #  @param hDev		[IN]  Device handle
    #  @param key		[IN]  Key value
    #  @param pVal		[OUT] Structure pointer of camera features
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to get specified bool nodes. For value of key, see MvCameraNode. The node values of IBoolean can be obtained through this interface, key value corresponds to the Name column. \n
    #  		This interface is only used to retrieve the values of "IBoolean" type nodes in the camera device XML. For CL and CXP devices, please refer to the interface: SciCam_GetBoolValueEx.
    def SciCam_GetBoolValue(self, key, pVal):
        SciCamCtrlDll.SciCam_GetBoolValue.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_GetBoolValue.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetBoolValue(self.handle, key.encode('ascii'), ctypes.byref(pVal))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ����Boolean������ֵ
    #  @param hDev		[IN]  �豸���
    #  @param key		[IN]  ���Լ�ֵ
    #  @param val		[IN]  ��Ҫ���õ��豸������ֵ
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ�������bool���͵�ָ���ڵ��ֵ��strKeyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IBoolean���Ľڵ�ֵ������ͨ���ýӿ����ã�strKey����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		�˽ӿڽ�������������豸XML�С�IBoolean�����ͽڵ�ֵ��CL��CXP�豸��ο��ӿڣ�SciCam_SetBoolValueEx
    #  @~english
    #  @brief Set Boolean value
    #  @param hDev		[IN]  Device handle
    #  @param key		[IN]  Key value
    #  @param val		[IN]  Feature value to set
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to set specified bool nodes. For value of key, see MvCameraNode. The node values of IBoolean can be set through this interface, key value corresponds to the Name column. \n
    #  		This interface is only used to set the values of "IBoolean" type nodes in the camera device XML. For CL and CXP devices, please refer to the interface: SciCam_SetBoolValueEx.
    def SciCam_SetBoolValue(self, key, val):
        SciCamCtrlDll.SciCam_SetBoolValue.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool)
        SciCamCtrlDll.SciCam_SetBoolValue.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetBoolValue(self.handle, key.encode('ascii'), ctypes.c_bool(val))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡString����ֵ
    #  @param hDev		[IN]  �豸���
    #  @param key		[IN]  ���Լ�ֵ
    #  @param pVal		[OUT] ���ظ��������й��豸���Խṹ��ָ�룬��ϸ�ο��� @ref PSCI_NODE_VAL_STRING "PSCI_NODE_VAL_STRING"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ��Ի�ȡstring���͵�ָ���ڵ��ֵ��Keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IString���Ľڵ�ֵ������ͨ���ýӿڻ�ȡ��key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		�˽ӿڽ�������ȡ����豸XML�С�IString�����ͽڵ�ֵ��CL��CXP�豸��ο��ӿڣ�SciCam_GetStringValueEx
    #  @~english
    #  @brief Get String value
    #  @param hDev		[IN]  Device handle
    #  @param key		[IN]  Key value
    #  @param pVal		[OUT] Structure pointer of camera features, references: @ref PSCI_NODE_VAL_STRING "PSCI_NODE_VAL_STRING"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to get specified string nodes. For value of key, see MvCameraNode. The node values of IString can be obtained through this interface, key value corresponds to the Name column. \n
    #  		This interface is only used to retrieve the values of "IString" type nodes in the camera device XML. For CL and CXP devices, please refer to the interface: SciCam_GetStringValueEx.
    def SciCam_GetStringValue(self, key, pVal):
        SciCamCtrlDll.SciCam_GetStringValue.argtypes = (ctypes.c_void_p, ctypes.c_void_p, PSCI_NODE_VAL_STRING)
        SciCamCtrlDll.SciCam_GetStringValue.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetStringValue(self.handle, key.encode('ascii'), ctypes.byref(pVal))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ����String������ֵ
    #  @param hDev		[IN] �豸���
    #  @param key		[IN] ���Լ�ֵ
    #  @param val		[IN] ��Ҫ���õ��豸������ֵ
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ�������string���͵�ָ���ڵ��ֵ��Keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IString���Ľڵ�ֵ������ͨ���ýӿ����ã�key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		�˽ӿڽ�������������豸XML�С�IString�����ͽڵ�ֵ��CL��CXP�豸��ο��ӿڣ�SciCam_SetStringValueEx
    #  @~english
    #  @brief Set String value
    #  @param hDev		[IN] Device handle
    #  @param key		[IN] Key value
    #  @param val		[IN] Feature value to set
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to set specified string nodes. For value of key, see MvCameraNode. The node values of IString can be set through this interface, key value corresponds to the Name column.
    #  		This interface is only used to set the values of "IString" type nodes in the camera device XML. For CL and CXP devices, please refer to the interface: SciCam_SetStringValueEx.
    def SciCam_SetStringValue(self, key, val):
        SciCamCtrlDll.SciCam_SetStringValue.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_SetStringValue.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetStringValue(self.handle, key.encode('ascii'), val.encode('ascii'))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡEnum����ֵ
    #  @param hDev		[IN]  �豸���
    #  @param key		[IN]  ���Լ�ֵ�����ȡ���ظ�ʽ��Ϣ��Ϊ"PixelFormat"
    #  @param pVal		[OUT] ���ظ��������й��豸���Խṹ��ָ�룬��ϸ�ο��� @ref PSCI_NODE_VAL_ENUM "PSCI_NODE_VAL_ENUM"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ��Ի�ȡEnum���͵�ָ���ڵ��ֵ��keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IEnumeration���Ľڵ�ֵ������ͨ���ýӿڻ�ȡ��key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		�˽ӿڽ�������ȡ����豸XML�С�IEnumeration�����ͽڵ�ֵ��CL��CXP�豸��ο��ӿڣ�SciCam_GetEnumValueEx
    #  @~english
    #  @brief Get Enum value
    #  @param hDev		[IN]  Device handle
    #  @param key		[IN]  Key value, for example, using "PixelFormat" to get pixel format
    #  @param pVal		[OUT] Structure pointer of camera features
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to get specified Enum nodes. For value of key, see MvCameraNode, The node values of IEnumeration can be obtained through this interface, key value corresponds to the Name column. \n
    #  		This interface is only used to retrieve the values of "IEnumeration" type nodes in the camera device XML. For CL and CXP devices, please refer to the interface: SciCam_GetEnumValueEx.
    def SciCam_GetEnumValue(self, key, pVal):
        SciCamCtrlDll.SciCam_GetEnumValue.argtypes = (ctypes.c_void_p, ctypes.c_void_p, PSCI_NODE_VAL_ENUM)
        SciCamCtrlDll.SciCam_GetEnumValue.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetEnumValue(self.handle, key.encode('ascii'), ctypes.byref(pVal))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ����Enum������ֵ
    #  @param hDev		[IN]  �豸���
    #  @param key		[IN]  ���Լ�ֵ�����ȡ���ظ�ʽ��Ϣ��Ϊ"PixelFormat"
    #  @param val		[IN]  ��Ҫ���õ��豸������ֵ
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ�������Enum���͵�ָ���ڵ��ֵ��keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IEnumeration���Ľڵ�ֵ������ͨ���ýӿ����ã�key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		�˽ӿڽ�������������豸XML�С�IEnumeration�����ͽڵ�ֵ��CL��CXP�豸��ο��ӿڣ�SciCam_SetEnumValueEx
    #  @~english
    #  @brief Set Enum value
    #  @param hDev		[IN]  Device handle
    #  @param key		[IN]  Key value, for example, using "PixelFormat" to set pixel format
    #  @param val		[IN]  Feature value to set
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to get specified Enum nodes. For value of key, see MvCameraNode, The node values of IEnumeration can be obtained through this interface, key value corresponds to the Name column. \n
    #  		This interface is only used to set the values of "IEnumeration" type nodes in the camera device XML. For CL and CXP devices, please refer to the interface: SciCam_SetEnumValueEx.
    def SciCam_SetEnumValue(self, key, val):
        SciCamCtrlDll.SciCam_SetEnumValue.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64)
        SciCamCtrlDll.SciCam_SetEnumValue.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetEnumValue(self.handle, key.encode('ascii'), ctypes.c_int64(val))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ����Enum������ֵ
    #  @param hDev		[IN]  �豸���
    #  @param key		[IN]  ���Լ�ֵ�����ȡ���ظ�ʽ��Ϣ��Ϊ"PixelFormat"
    #  @param val		[IN]  ��Ҫ���õ��豸�������ַ���
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ�������Enum���͵�ָ���ڵ��ֵ��keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IEnumeration���Ľڵ�ֵ������ͨ���ýӿ����ã�key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		�˽ӿڽ�������������豸XML�С�IEnumeration�����ͽڵ�ֵ��CL��CXP�豸��ο��ӿڣ�SciCam_SetEnumValueByStringEx
    #  @~english
    #  @brief Set Enum value
    #  @param hDev		[IN]  Device handle
    #  @param key		[IN]  Key value, for example, using "PixelFormat" to set pixel format
    #  @param val		[IN]  Feature String to set
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After connecting to the device, calling this interface allows you to set the value of a specific node of Enum type. The possible values for the "key" parameter can be referenced from the list of XML node parameter types, where the nodes with data type "IEnumeration" can be set using this interface. The "key" parameter value corresponds to the "Name" column in the list. \n
    #  		This interface is only used to set the values of "IEnumeration" type nodes in the camera device XML. For CL and CXP devices, please refer to the interface: SciCam_SetEnumValueByStringEx.
    def SciCam_SetEnumValueByString(self, key, val):
        SciCamCtrlDll.SciCam_SetEnumValueByString.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_SetEnumValueByString.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetEnumValueByString(self.handle, key.encode('ascii'), val.encode('ascii'))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ����Command������ֵ
    #  @param hDev		[IN]  �豸���
    #  @param key		[IN]  ���Լ�ֵ
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ�������ָ����Command���ͽڵ㡣keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��ICommand���Ľڵ㶼����ͨ���ýӿ����ã�key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		�˽ӿڽ�������������豸XML�С�ICommand�����ͽڵ�ֵ��CL��CXP�豸��ο��ӿڣ�SciCam_SetCommandValueEx
    #  @~english
    #  @brief Set Command value
    #  @param hDev		[IN]  Device handle
    #  @param key		[IN]  Key value
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to set specified Command nodes. For value of strKey, see MvCameraNode. The node values of ICommand can be set through this interface, strKey value corresponds to the Name column.
    #  		This interface is only used to set the values of "ICommand" type nodes in the camera device XML. For CL and CXP devices, please refer to the interface: SciCam_SetCommandValueEx.
    def SciCam_SetCommandValue(self, key):
        SciCamCtrlDll.SciCam_SetCommandValue.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_SetCommandValue.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetCommandValue(self.handle, key.encode('ascii'))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ö�ٽڵ㼯��
    #  @param hDev			[IN]      �豸���
    #  @param nodes			[IN][OUT] �ڵ㼯����ϸ�ο��� @ref PSCI_CAM_NODE "PSCI_CAM_NODE"
    #  @param nodesCount	[IN][OUT] �ڵ����
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks ��ȡ��ǰ���ӵ��豸���нڵ㼯�ϣ���nodes����Ϊ��ʱ��Ĭ��ֻ���ص�ǰ�ڵ����
    #  @~english
    #  @brief Set Command value by xml type
    #  @param hDev			[IN]      Device handle
    #  @param nodes			[IN][OUT] Node collection, references: @ref PSCI_CAM_NODE "PSCI_CAM_NODE"
    #  @param nodesCount	[IN][OUT] Number of nodes
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks Retrieve the collection of all nodes for the currently connected device. When the nodes parameter is empty, it defaults to only returning the current number of nodes.
    def SciCam_GetNodes(self, nodes, nodesCount):
        SciCamCtrlDll.SciCam_GetNodes.argtypes = (ctypes.c_void_p, PSCI_CAM_NODE, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_GetNodes.restype = ctypes.c_uint
        if nodes == None:
            return SciCamCtrlDll.SciCam_GetNodes(self.handle, nodes, ctypes.byref(nodesCount))
        return SciCamCtrlDll.SciCam_GetNodes(self.handle, ctypes.byref(nodes), ctypes.byref(nodesCount))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡ�ڵ�����
    #  @param hDev			[IN]  �豸���
    #  @param key			[IN]  ���Լ�ֵ
    #  @param pType			[OUT] �ڵ����ͣ���ϸ�ο��� @ref SciCamNodeType "SciCamNodeType"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Get node type
    #  @param hDev			[IN]  Device handle
    #  @param key			[IN]  Attribute key value
    #  @param pType			[OUT] Node type, references: @ref SciCamNodeType "SciCamNodeType"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_GetNodeType(self, key, pType):
        SciCamCtrlDll.SciCam_GetNodeType.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_GetNodeType.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetNodeType(self.handle, key.encode('ascii'), ctypes.byref(pType))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡ�ڵ������ռ�
    #  @param hDev			[IN]  �豸���
    #  @param key			[IN]  ���Լ�ֵ
    #  @param pNameSpace	[OUT] �ڵ������ռ䣬��ϸ�ο��� @ref SciCamNodeNameSpace "SciCamNodeNameSpace"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Get node name space
    #  @param hDev			[IN]  Device handle
    #  @param key			[IN]  Attribute key value
    #  @param pNameSpace	[OUT] Node name space, references: @ref SciCamNodeNameSpace "SciCamNodeNameSpace"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_GetNodeNameSpace(self, key, pNameSpace):
        SciCamCtrlDll.SciCam_GetNodeNameSpace.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_GetNodeNameSpace.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetNodeNameSpace(self.handle, key.encode('ascii'), ctypes.byref(pNameSpace))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡ�ڵ�ɼ���
    #  @param hDev			[IN]  �豸���
    #  @param key			[IN]  ���Լ�ֵ
    #  @param pVisibility	[OUT] �ڵ�ɼ��ԣ���ϸ�ο��� @ref SciCamNodeVisibility "SciCamNodeVisibility"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Get node visibility
    #  @param hDev			[IN]  Device handle
    #  @param key			[IN]  Attribute key value
    #  @param pVisibility	[OUT] Node visibility, references: @ref SciCamNodeVisibility "SciCamNodeVisibility"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_GetNodeVisibility(self, key, pVisibility):
        SciCamCtrlDll.SciCam_GetNodeVisibility.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_GetNodeVisibility.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetNodeVisibility(self.handle, key.encode('ascii'), ctypes.byref(pVisibility))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡ�ڵ����ģʽ
    #  @param hDev			[IN]  �豸���
    #  @param key			[IN]  ���Լ�ֵ
    #  @param pAccessMode	[OUT] �ڵ����ģʽ����ϸ�ο��� @ref SciCamNodeAccessMode "SciCamNodeAccessMode"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Get node access mode
    #  @param hDev			[IN]  Device handle
    #  @param key			[IN]  Attribute key value
    #  @param pAccessMode	[OUT] Node access mode, references: @ref SciCamNodeAccessMode "SciCamNodeAccessMode"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_GetNodeAccessMode(self, key, pAccessMode):
        SciCamCtrlDll.SciCam_GetNodeAccessMode.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_GetNodeAccessMode.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetNodeAccessMode(self.handle, key.encode('ascii'), ctypes.byref(pAccessMode))

    ## @ingroup module_DeviceAttributeManipulation
    #  @~chinese
    #  @brief ����������Ե�����XML�ļ�
    #  @param hDev			[IN]      �豸���
    #  @param strFileName	[IN]      XML�ļ���
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ��Խ��豸���Ե���������XML�ļ���strFileNameΪ�����ļ���·�������ƣ�CL��CXP�豸��ο��ӿڣ�@ref SciCam_FeatureSaveEx "SciCam_FeatureSaveEx"
    #  @~english
    #  @brief Export camera attribute to local XML file
    #  @param hDev			[IN]      Device handle
    #  @param strFileName	[IN]      XML file name
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After connecting the device, call this interface to export the device attribute to a local XML file. strFileName is the path and name of the exported XML.
    def SciCam_FeatureSave(self, strFileName):
        SciCamCtrlDll.SciCam_FeatureSave.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_FeatureSave.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_FeatureSave(self.handle, strFileName.encode('ascii'))

    ## @ingroup module_DeviceAttributeManipulation
    #  @~chinese
    #  @brief �ӱ���XML�ļ������������
    #  @param hDev			[IN]      �豸���
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ��Խ�����XML�ļ������豸���ԣ�strFileNameΪ�����ļ���·�������ƣ�CL��CXP�豸��ο��ӿڣ�@ref SciCam_FeatureLoadEx "SciCam_FeatureLoadEx"
    #  @~english
    #  @brief Import camera attribute from local XML file
    #  @param hDev			[IN]      Device handle
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After connecting the device, call this interface to import the device attribute from a local XML file. strFileName is the path and name of the imported XML.
    def SciCam_FeatureLoad(self, strFileName):
        SciCamCtrlDll.SciCam_FeatureLoad.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_FeatureLoad.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_FeatureLoad(self.handle, strFileName.encode('ascii'))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡInteger����ֵ�����ݲ�ͬXML���ͣ�
    #  @param hDev		[IN]  �豸���
    #  @param xmlType	[IN]  XML���ͣ���ϸ�ο��� @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  ���Լ�ֵ�����ȡ�����Ϣ��Ϊ"Width"
    #  @param pVal		[OUT] ���ظ��������й��豸���Խṹ��ָ�룬��ϸ�ο��� @ref PSCI_NODE_VAL_INT "PSCI_NODE_VAL_INT"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ��Ի�ȡint���͵�ָ���ڵ��ֵ��keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IInteger���Ľڵ�ֵ������ͨ���ýӿڻ�ȡ��key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		���ݲ�ͬXML���Ϳɻ�ȡ�豸XML�С�IInteger�����ͽڵ�ֵ������CL�ɼ�����xmlTypeΪSciCamDeviceXmlType::SciCam_DeviceXml_Card
    #  @~english
    #  @brief Get Integer value by xml type
    #  @param hDev		[IN]  Device handle
    #  @param xmlType	[IN]  XML type��references: @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  Key value, for example, using "Width" to get width
    #  @param pVal		[OUT] Structure pointer of camera features, references: PSCI_NODE_VAL_INT "PSCI_NODE_VAL_INT"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks You can call this API to get the value of camera node with integer type after connecting the device. For key value, refer to MvCameraNode. All the node values of "IInteger" in the list can be obtained via this API. Key corresponds to the Name column. \n
    #  		You can retrieve the values of "IInteger" type nodes in the device XML based on different XML types. For example, for a CL capture card, the xmlType would be SciCamDeviceXmlType::SciCam_DeviceXml_Card.
    def SciCam_GetIntValueEx(self, xmlType, key, pVal):
        SciCamCtrlDll.SciCam_GetIntValueEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                                                       PSCI_NODE_VAL_INT)
        SciCamCtrlDll.SciCam_GetIntValueEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetIntValueEx(self.handle, ctypes.c_int(xmlType), key.encode('ascii'),
                                                  ctypes.byref(pVal))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ����Integer������ֵ�����ݲ�ͬXML���ͣ�
    #  @param hDev		[IN]  �豸���
    #  @param xmlType	[IN]  XML���ͣ���ϸ�ο��� @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  ���Լ�ֵ�����ȡ�����Ϣ��Ϊ"Width"
    #  @param val		[IN]  ��Ҫ���õ��豸������ֵ
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ�������int���͵�ָ���ڵ��ֵ��keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IInteger���Ľڵ�ֵ������ͨ���ýӿ����ã�key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		���ݲ�ͬXML���Ϳ������豸XML�С�IInteger�����ͽڵ�ֵ������CL�ɼ�����xmlTypeΪSciCamDeviceXmlType::SciCam_DeviceXml_Card
    #  @~english
    #  @brief Set Integer value by xml type
    #  @param hDev		[IN]  Device handle
    #  @param xmlType	[IN]  XML type, references: @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  Key value, for example, using "Width" to set width
    #  @param val		[IN]  Feature value to set
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks You can call this API to get the value of camera node with integer type after connecting the device. For key value, refer to MvCameraNode. All the node values of "IInteger" in the list can be obtained via this API. Key corresponds to the Name column. \n
    #  		You can set the values of "IInteger" type nodes in the device XML based on different XML types. For example, for a CL capture card, the xmlType would be SciCamDeviceXmlType::SciCam_DeviceXml_Card.
    def SciCam_SetIntValueEx(self, xmlType, key, val):
        SciCamCtrlDll.SciCam_SetIntValueEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int64)
        SciCamCtrlDll.SciCam_SetIntValueEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetIntValueEx(self.handle, ctypes.c_int(xmlType), key.encode('ascii'),
                                                  ctypes.c_int64(val))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡFloat����ֵ�����ݲ�ͬXML���ͣ�
    #  @param hDev		[IN]  �豸���
    #  @param xmlType	[IN]  XML���ͣ���ϸ�ο��� @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  ���Լ�ֵ
    #  @param pVal		[OUT] ���ظ��������й��豸���Խṹ��ָ�룬��ϸ�ο��� @ref PSCI_NODE_VAL_FLOAT "PSCI_NODE_VAL_FLOAT"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ��Ի�ȡfloat���͵�ָ���ڵ��ֵ��keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IFloat���Ľڵ�ֵ������ͨ���ýӿڻ�ȡ��key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С�
    #  		���ݲ�ͬXML���Ϳɻ�ȡ�豸XML�С�IFloat�����ͽڵ�ֵ������CL�ɼ�����xmlTypeΪSciCamDeviceXmlType::SciCam_DeviceXml_Card
    #  @~english
    #  @brief Get Float value by xml type
    #  @param hDev		[IN]  Device handle
    #  @param xmlType	[IN]  XML type, references: @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  Key value
    #  @param pVal		[OUT] Structure pointer of camera features, references: @ref PSCI_NODE_VAL_FLOAT "PSCI_NODE_VAL_FLOAT"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to get specified float node. For detailed key value see: MvCameraNode. The node values of IFloat can be obtained through this interface, key value corresponds to the Name column. \n
    #  		You can retrieve the values of "IFloat" type nodes in the device XML based on different XML types. For example, for a CL capture card, the xmlType would be SciCamDeviceXmlType::SciCam_DeviceXml_Card.
    def SciCam_GetFloatValueEx(self, xmlType, key, pVal):
        SciCamCtrlDll.SciCam_GetFloatValueEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                                                         PSCI_NODE_VAL_FLOAT)
        SciCamCtrlDll.SciCam_GetFloatValueEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetFloatValueEx(self.handle, ctypes.c_int(xmlType), key.encode('ascii'),
                                                    ctypes.byref(pVal))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ����float������ֵ�����ݲ�ͬXML���ͣ�
    #  @param hDev		[IN]  �豸���
    #  @param xmlType	[IN]  XML���ͣ���ϸ�ο��� @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  ���Լ�ֵ
    #  @param val		[IN]  ��Ҫ���õ��豸������ֵ
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ�������float���͵�ָ���ڵ��ֵ��keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IFloat���Ľڵ�ֵ������ͨ���ýӿ����ã�key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		���ݲ�ͬXML���Ϳ������豸XML�С�IFloat�����ͽڵ�ֵ������CL�ɼ�����xmlTypeΪSciCamDeviceXmlType::SciCam_DeviceXml_Card
    #  @~english
    #  @brief Set float value by xml type
    #  @param hDev		[IN]  Device handle
    #  @param xmlType	[IN]  XML type, references: @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  Key value
    #  @param val		[IN]  Feature value to set
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to set specified float node. For detailed key value see: MvCameraNode. The node values of IFloat can be set through this interface, key value corresponds to the Name column. \n
    #  		You can set the values of "IFloat" type nodes in the device XML based on different XML types. For example, for a CL capture card, the xmlType would be SciCamDeviceXmlType::SciCam_DeviceXml_Card.
    def SciCam_SetFloatValueEx(self, xmlType, key, val):
        SciCamCtrlDll.SciCam_SetFloatValueEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                                                         ctypes.c_double)
        SciCamCtrlDll.SciCam_SetFloatValueEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetFloatValueEx(self.handle, ctypes.c_int(xmlType), key.encode('ascii'),
                                                    ctypes.c_double(val))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡBoolean����ֵ�����ݲ�ͬXML���ͣ�
    #  @param hDev		[IN]  �豸���
    #  @param xmlType	[IN]  XML���ͣ���ϸ�ο��� @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  ���Լ�ֵ
    #  @param pVal		[OUT] ���ظ��������й��豸����ֵ
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ��Ի�ȡbool���͵�ָ���ڵ��ֵ��keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IBoolean���Ľڵ�ֵ������ͨ���ýӿڻ�ȡ��key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		���ݲ�ͬXML���Ϳɻ�ȡ�豸XML�С�IBoolean�����ͽڵ�ֵ������CL�ɼ�����xmlTypeΪSciCamDeviceXmlType::SciCam_DeviceXml_Card
    #  @~english
    #  @brief Get Boolean value by xml type
    #  @param hDev		[IN]  Device handle
    #  @param xmlType	[IN]  XML type, references: @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  Key value
    #  @param pVal		[OUT] Structure pointer of camera features
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to get specified bool nodes. For value of key, see MvCameraNode. The node values of IBoolean can be obtained through this interface, key value corresponds to the Name column. \n
    #  		You can retrieve the values of "IFloat" type nodes in the device XML based on different XML types. For example, for a CL capture card, the xmlType would be SciCamDeviceXmlType::SciCam_DeviceXml_Card.
    def SciCam_GetBoolValueEx(self, xmlType, key, pVal):
        SciCamCtrlDll.SciCam_GetBoolValueEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_GetBoolValueEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetBoolValueEx(self.handle, ctypes.c_int(xmlType), key.encode('ascii'),
                                                   ctypes.byref(pVal))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ����Boolean������ֵ�����ݲ�ͬXML���ͣ�
    #  @param hDev		[IN]  �豸���
    #  @param xmlType	[IN]  XML���ͣ���ϸ�ο��� @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  ���Լ�ֵ
    #  @param val		[IN]  ��Ҫ���õ��豸������ֵ
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ�������bool���͵�ָ���ڵ��ֵ��strKeyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IBoolean���Ľڵ�ֵ������ͨ���ýӿ����ã�strKey����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		���ݲ�ͬXML���Ϳ������豸XML�С�IBoolean�����ͽڵ�ֵ������CL�ɼ�����xmlTypeΪSciCamDeviceXmlType::SciCam_DeviceXml_Card
    #  @~english
    #  @brief Set Boolean value by xml type
    #  @param hDev		[IN]  Device handle
    #  @param xmlType	[IN]  XML type, references: @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  Key value
    #  @param val		[IN]  Feature value to set
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to set specified bool nodes. For value of key, see MvCameraNode. The node values of IBoolean can be set through this interface, key value corresponds to the Name column. \n
    #  		You can set the values of "IBoolean" type nodes in the device XML based on different XML types. For example, for a CL capture card, the xmlType would be SciCamDeviceXmlType::SciCam_DeviceXml_Card.
    def SciCam_SetBoolValueEx(self, xmlType, key, val):
        SciCamCtrlDll.SciCam_SetBoolValueEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_bool)
        SciCamCtrlDll.SciCam_SetBoolValueEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetBoolValueEx(self.handle, ctypes.c_int(xmlType), key.encode('ascii'),
                                                   ctypes.c_bool(val))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡString����ֵ�����ݲ�ͬXML���ͣ�
    #  @param hDev		[IN]  �豸���
    #  @param xmlType	[IN]  XML���ͣ���ϸ�ο��� @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  ���Լ�ֵ
    #  @param pVal		[OUT] ���ظ��������й��豸���Խṹ��ָ��
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ��Ի�ȡstring���͵�ָ���ڵ��ֵ��Keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IString���Ľڵ�ֵ������ͨ���ýӿڻ�ȡ��key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		���ݲ�ͬXML���Ϳɻ�ȡ�豸XML�С�IString�����ͽڵ�ֵ������CL�ɼ�����xmlTypeΪSciCamDeviceXmlType::SciCam_DeviceXml_Card
    #  @~english
    #  @brief Get String value by xml type
    #  @param hDev		[IN]  Device handle
    #  @param xmlType	[IN]  XML type, references: @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  Key value
    #  @param pVal		[OUT] Structure pointer of camera features
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to get specified string nodes. For value of key, see MvCameraNode. The node values of IString can be obtained through this interface, key value corresponds to the Name column. \n
    #  		You can retrieve the values of "IString" type nodes in the device XML based on different XML types. For example, for a CL capture card, the xmlType would be SciCamDeviceXmlType::SciCam_DeviceXml_Card.
    def SciCam_GetStringValueEx(self, xmlType, key, pVal):
        SciCamCtrlDll.SciCam_GetStringValueEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                                                          PSCI_NODE_VAL_STRING)
        SciCamCtrlDll.SciCam_GetStringValueEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetStringValueEx(self.handle, ctypes.c_int(xmlType), key.encode('ascii'),
                                                     ctypes.byref(pVal))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ����String������ֵ�����ݲ�ͬXML���ͣ�
    #  @param hDev		[IN] �豸���
    #  @param xmlType	[IN] XML���ͣ���ϸ�ο��� @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN] ���Լ�ֵ
    #  @param val		[IN] ��Ҫ���õ��豸������ֵ
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ�������string���͵�ָ���ڵ��ֵ��Keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IString���Ľڵ�ֵ������ͨ���ýӿ����ã�key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		���ݲ�ͬXML���Ϳ������豸XML�С�IString�����ͽڵ�ֵ������CL�ɼ�����xmlTypeΪSciCamDeviceXmlType::SciCam_DeviceXml_Card
    #  @~english
    #  @brief Set String value by xml type
    #  @param hDev		[IN] Device handle
    #  @param xmlType	[IN] XML type, references: @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN] Key value
    #  @param val		[IN] Feature value to set
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to set specified string nodes. For value of key, see MvCameraNode. The node values of IString can be set through this interface, key value corresponds to the Name column.
    #  		You can set the values of "IString" type nodes in the device XML based on different XML types. For example, for a CL capture card, the xmlType would be SciCamDeviceXmlType::SciCam_DeviceXml_Card.
    def SciCam_SetStringValueEx(self, xmlType, key, val):
        SciCamCtrlDll.SciCam_SetStringValueEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                                                          ctypes.c_void_p)
        SciCamCtrlDll.SciCam_SetStringValueEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetStringValueEx(self.handle, ctypes.c_int(xmlType), key.encode('ascii'),
                                                     val.encode('ascii'))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡEnum����ֵ�����ݲ�ͬXML���ͣ�
    #  @param hDev		[IN]  �豸���
    #  @param xmlType	[IN]  XML���ͣ���ϸ�ο��� @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  ���Լ�ֵ�����ȡ���ظ�ʽ��Ϣ��Ϊ"PixelFormat"
    #  @param pVal		[OUT] ���ظ��������й��豸���Խṹ��ָ�룬��ϸ�ο��� @ref PSCI_NODE_VAL_ENUM "PSCI_NODE_VAL_ENUM"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ��Ի�ȡEnum���͵�ָ���ڵ��ֵ��keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IEnumeration���Ľڵ�ֵ������ͨ���ýӿڻ�ȡ��key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		���ݲ�ͬXML���Ϳɻ�ȡ�豸XML�С�IEnumeration�����ͽڵ�ֵ������CL�ɼ�����xmlTypeΪSciCamDeviceXmlType::SciCam_DeviceXml_Card
    #  @~english
    #  @brief Get Enum value by xml type
    #  @param hDev		[IN]  Device handle
    #  @param xmlType	[IN]  XML type, references: @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  Key value, for example, using "PixelFormat" to get pixel format
    #  @param pVal		[OUT] Structure pointer of camera features, references: @ref PSCI_NODE_VAL_ENUM "PSCI_NODE_VAL_ENUM"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to get specified Enum nodes. For value of key, see MvCameraNode, The node values of IEnumeration can be obtained through this interface, key value corresponds to the Name column. \n
    #  		You can retrieve the values of "IEnumeration" type nodes in the device XML based on different XML types. For example, for a CL capture card, the xmlType would be SciCamDeviceXmlType::SciCam_DeviceXml_Card.
    def SciCam_GetEnumValueEx(self, xmlType, key, pVal):
        SciCamCtrlDll.SciCam_GetEnumValueEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                                                        PSCI_NODE_VAL_ENUM)
        SciCamCtrlDll.SciCam_GetEnumValueEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetEnumValueEx(self.handle, ctypes.c_int(xmlType), key.encode('ascii'),
                                                   ctypes.byref(pVal))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ����Enum������ֵ�����ݲ�ͬXML���ͣ�
    #  @param hDev		[IN]  �豸���
    #  @param xmlType	[IN]  XML���ͣ���ϸ�ο��� @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  ���Լ�ֵ�����ȡ���ظ�ʽ��Ϣ��Ϊ"PixelFormat"
    #  @param val		[IN]  ��Ҫ���õ��豸������ֵ
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ�������Enum���͵�ָ���ڵ��ֵ��keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IEnumeration���Ľڵ�ֵ������ͨ���ýӿ����ã�key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		���ݲ�ͬXML���Ϳ������豸XML�С�IEnumeration�����ͽڵ�ֵ������CL�ɼ�����xmlTypeΪSciCamDeviceXmlType::SciCam_DeviceXml_Card
    #  @~english
    #  @brief Set Enum value by xml type
    #  @param hDev		[IN]  Device handle
    #  @param xmlType	[IN]  XML type, references: @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  Key value, for example, using "PixelFormat" to set pixel format
    #  @param val		[IN]  Feature value to set
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to get specified Enum nodes. For value of key, see MvCameraNode, The node values of IEnumeration can be obtained through this interface, key value corresponds to the Name column. \n
    #  		You can set the values of "IEnumeration" type nodes in the device XML based on different XML types. For example, for a CL capture card, the xmlType would be SciCamDeviceXmlType::SciCam_DeviceXml_Card.
    def SciCam_SetEnumValueEx(self, xmlType, key, val):
        SciCamCtrlDll.SciCam_SetEnumValueEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int64)
        SciCamCtrlDll.SciCam_SetEnumValueEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetEnumValueEx(self.handle, ctypes.c_int(xmlType), key.encode('ascii'),
                                                   ctypes.c_int64(val))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ����Enum������ֵ�����ݲ�ͬXML���ͣ�
    #  @param hDev		[IN]  �豸���
    #  @param xmlType	[IN]  XML���ͣ���ϸ�ο��� @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  ���Լ�ֵ�����ȡ���ظ�ʽ��Ϣ��Ϊ"PixelFormat"
    #  @param val		[IN]  ��Ҫ���õ��豸�������ַ���
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ�������Enum���͵�ָ���ڵ��ֵ��keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��IEnumeration���Ľڵ�ֵ������ͨ���ýӿ����ã�key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		���ݲ�ͬXML���Ϳ������豸XML�С�IEnumeration�����ͽڵ�ֵ������CL�ɼ�����xmlTypeΪSciCamDeviceXmlType::SciCam_DeviceXml_Card
    #  @~english
    #  @brief Set Enum value by xml type
    #  @param hDev		[IN]  Device handle
    #  @param xmlType	[IN]  XML type, references: @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  Key value, for example, using "PixelFormat" to set pixel format
    #  @param val		[IN]  Feature String to set
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After connecting to the device, calling this interface allows you to set the value of a specific node of Enum type. The possible values for the "key" parameter can be referenced from the list of XML node parameter types, where the nodes with data type "IEnumeration" can be set using this interface. The "key" parameter value corresponds to the "Name" column in the list. \n
    #  		You can set the values of "IEnumeration" type nodes in the device XML based on different XML types. For example, for a CL capture card, the xmlType would be SciCamDeviceXmlType::SciCam_DeviceXml_Card.
    def SciCam_SetEnumValueByStringEx(self, xmlType, key, val):
        SciCamCtrlDll.SciCam_SetEnumValueByStringEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                                                                ctypes.c_void_p)
        SciCamCtrlDll.SciCam_SetEnumValueByStringEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetEnumValueByStringEx(self.handle, ctypes.c_int(xmlType), key.encode('ascii'),
                                                           val.encode('ascii'))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ����Command������ֵ�����ݲ�ͬXML���ͣ�
    #  @param hDev		[IN]  �豸���
    #  @param xmlType	[IN]  XML���ͣ���ϸ�ο��� @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  ���Լ�ֵ
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ�������ָ����Command���ͽڵ㡣keyȡֵ���Բο�XML�ڵ���������б����������������Ϊ��ICommand���Ľڵ㶼����ͨ���ýӿ����ã�key����ȡֵ��Ӧ�б�����ġ����ơ�һ�С� \n
    #  		�˽ӿڽ�������������豸XML�С�ICommand�����ͽڵ�ֵ��CL��CXP�豸��ο��ӿڣ�SciCam_SetCommandValueEx
    #  @~english
    #  @brief Set Command value by xml type
    #  @param hDev		[IN]  Device handle
    #  @param xmlType	[IN]  XML type, references: @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  Key value
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After the device is connected, call this interface to set specified Command nodes. For value of strKey, see MvCameraNode. The node values of ICommand can be set through this interface, strKey value corresponds to the Name column.
    #  		You can set the values of "ICommand" type nodes in the device XML based on different XML types. For example, for a CL capture card, the xmlType would be SciCamDeviceXmlType::SciCam_DeviceXml_Card.
    def SciCam_SetCommandValueEx(self, xmlType, key):
        SciCamCtrlDll.SciCam_SetCommandValueEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_SetCommandValueEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_SetCommandValueEx(self.handle, ctypes.c_int(xmlType), key.encode('ascii'))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ö�ٽڵ㼯��
    #  @param hDev			[IN]      �豸���
    #  @param xmlType		[IN]      XML���ͣ���ϸ�ο��� @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param nodes			[IN][OUT] �ڵ㼯����ϸ�ο��� @ref PSCI_CAM_NODE "PSCI_CAM_NODE"
    #  @param nodesCount	[IN][OUT] �ڵ����
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks ��ȡ��ǰ���ӵ��豸���нڵ㼯��
    #  @~english
    #  @brief Set Command value by xml type
    #  @param hDev			[IN]      Device handle
    #  @param xmlType		[IN]      XML type, references: @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param nodes			[IN][OUT] Node collection, references: @ref PSCI_CAM_NODE "PSCI_CAM_NODE"
    #  @param nodesCount	[IN][OUT] Number of nodes
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks Retrieve the collection of all nodes for the currently connected device.
    def SciCam_GetNodesEx(self, xmlType, nodes, nodesCount):
        SciCamCtrlDll.SciCam_GetNodesEx.argtypes = (ctypes.c_void_p, ctypes.c_int, PSCI_CAM_NODE, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_GetNodesEx.restype = ctypes.c_uint
        if nodes == None:
            return SciCamCtrlDll.SciCam_GetNodesEx(self.handle, ctypes.c_int(xmlType), nodes, ctypes.byref(nodesCount))
        return SciCamCtrlDll.SciCam_GetNodesEx(self.handle, ctypes.c_int(xmlType), ctypes.byref(nodes),
                                               ctypes.byref(nodesCount))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡ�ڵ����ͣ����ݲ�ͬXML���ͣ�
    #  @param hDev		[IN]  �豸���
    #  @param xmlType	[IN]  XML���ͣ���ϸ�ο��� @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  ���Լ�ֵ
    #  @param pType		[OUT] �ڵ����ͣ���ϸ�ο��� @ref SciCamNodeType "SciCamNodeType"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Get node type (based on different XML types)
    #  @param hDev		[IN]  Device handle
    #  @param xmlType	[IN]  XML type, references: @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  Attribute key value
    #  @param pType		[OUT] Node type, references: @ref SciCamNodeType "SciCamNodeType"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_GetNodeTypeEx(self, xmlType, key, pType):
        SciCamCtrlDll.SciCam_GetNodeTypeEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_GetNodeTypeEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetNodeTypeEx(self.handle, ctypes.c_int(xmlType), key.encode('ascii'),
                                                  ctypes.byref(pType))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡ�ڵ������ռ䣨���ݲ�ͬXML���ͣ�
    #  @param hDev		[IN]  �豸���
    #  @param xmlType	[IN]  XML���ͣ���ϸ�ο��� @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  ���Լ�ֵ
    #  @param pNameSpace	[OUT] �ڵ������ռ䣬��ϸ�ο��� @ref SciCamNodeNameSpace "SciCamNodeNameSpace"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Get node namespace (based on different XML types)
    #  @param hDev		[IN]  Device handle
    #  @param xmlType	[IN]  XML type, references: @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  Attribute key value
    #  @param pNameSpace	[OUT] Node namespace, references: @ref SciCamNodeNameSpace "SciCamNodeNameSpace"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_GetNodeNameSpaceEx(self, xmlType, key, pNameSpace):
        SciCamCtrlDll.SciCam_GetNodeNameSpaceEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                                                            ctypes.c_void_p)
        SciCamCtrlDll.SciCam_GetNodeNameSpaceEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetNodeNameSpaceEx(self.handle, ctypes.c_int(xmlType), key.encode('ascii'),
                                                       ctypes.byref(pNameSpace))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡ�ڵ�ɼ��ԣ����ݲ�ͬXML���ͣ�
    #  @param hDev		[IN]  �豸���
    #  @param xmlType	[IN]  XML���ͣ���ϸ�ο��� @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  ���Լ�ֵ
    #  @param pVisibility	[OUT] �ڵ�ɼ��ԣ���ϸ�ο��� @ref SciCamNodeVisibility "SciCamNodeVisibility"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Get node visibility (based on different XML types)
    #  @param hDev		[IN]  Device handle
    #  @param xmlType	[IN]  XML type, references: @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  Attribute key value
    #  @param pVisibility	[OUT] Node visibility, references: @ref SciCamNodeVisibility "SciCamNodeVisibility"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_GetNodeVisibilityEx(self, xmlType, key, pVisibility):
        SciCamCtrlDll.SciCam_GetNodeVisibilityEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                                                             ctypes.c_void_p)
        SciCamCtrlDll.SciCam_GetNodeVisibilityEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetNodeVisibilityEx(self.handle, ctypes.c_int(xmlType), key.encode('ascii'),
                                                        ctypes.byref(pVisibility))

    ## @ingroup module_Node
    #  @~chinese
    #  @brief ��ȡ�ڵ����ģʽ�����ݲ�ͬXML���ͣ�
    #  @param hDev		[IN]  �豸���
    #  @param xmlType	[IN]  XML���ͣ���ϸ�ο��� @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  ���Լ�ֵ
    #  @param pAccessMode	[OUT] �ڵ����ģʽ����ϸ�ο��� @ref SciCamNodeAccessMode "SciCamNodeAccessMode"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Get node access mode (based on different XML types)
    #  @param hDev		[IN]  Device handle
    #  @param xmlType	[IN]  XML type, references: @ref SciCamDeviceXmlType "SciCamDeviceXmlType"
    #  @param key		[IN]  Attribute key value
    #  @param pAccessMode	[OUT] Node access mode, references: @ref SciCamNodeAccessMode "SciCamNodeAccessMode"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_GetNodeAccessModeEx(self, xmlType, key, pAccessMode):
        SciCamCtrlDll.SciCam_GetNodeAccessModeEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                                                             ctypes.c_void_p)
        SciCamCtrlDll.SciCam_GetNodeAccessModeEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_GetNodeAccessModeEx(self.handle, ctypes.c_int(xmlType), key.encode('ascii'),
                                                        ctypes.byref(pAccessMode))

    ## @ingroup module_DeviceAttributeManipulation
    #  @~chinese
    #  @brief �����豸���Ե�����XML�ļ�
    #  @param hDev			[IN]      �豸���
    #  @param xmlType		[IN]      XML�ļ�����
    #  @param strFileName	[IN]      XML�ļ���
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ��Խ�����XML�ļ������豸���ԣ�strFileNameΪ�����ļ���·�������ƣ�xmlTypeΪ�豸���ͣ�֧��CL��CXP�豸
    #  @~english
    #  @brief Export device attribute to local XML file
    #  @param hDev			[IN]      Device handle
    #  @param xmlType		[IN]      XML file type
    #  @param strFileName	[IN]      XML file name
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After connecting the device, call this interface to export the device attribute to a local XML file. strFileName is the path and name of the exported XML.
    #           xmlType is the type of the exported XML file, supporting CL and CXP devices.
    def SciCam_FeatureSaveEx(self, xmlType, strFileName):
        SciCamCtrlDll.SciCam_FeatureSaveEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_FeatureSaveEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_FeatureSaveEx(self.handle, ctypes.c_int(xmlType), strFileName.encode('ascii'))

    ## @ingroup module_DeviceAttributeManipulation
    #  @~chinese
    #  @brief �ӱ���XML�ļ������豸����
    #  @param hDev			[IN]      �豸���
    #  @param xmlType		[IN]      XML�ļ�����
    #  @param strFileName	[IN]      XML�ļ���
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks �����豸֮����øýӿڿ��Խ�����XML�ļ������豸���ԣ�strFileNameΪ�����ļ���·�������ƣ�xmlTypeΪ�豸���ͣ�֧��CL��CXP�豸
    #  @~english
    #  @brief Import device attribute from local XML file
    #  @param hDev			[IN]      Device handle
    #  @param xmlType		[IN]      XML file type
    #  @param strFileName	[IN]      XML file name
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retvalOther references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks After connecting the device, call this interface to import the device attribute from a local XML file. strFileName is the path and name of the imported XML.
    #           xmlType is the type of the imported XML file, supporting CL and CXP devices.
    def SciCam_FeatureLoadEx(self, xmlType, strFileName):
        SciCamCtrlDll.SciCam_FeatureLoadEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_FeatureLoadEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_FeatureLoadEx(self.handle, ctypes.c_int(xmlType), strFileName.encode('ascii'))

    ## @ingroup module_Other
    #  @~chinese
    #  @brief ����GigE�豸IP��������������ص�ַ
    #  @param sn		[IN]  �豸���к�
    #  @param ip		[IN]  ip��ַ
    #  @param mask		[IN]  ��������
    #  @param gateway	[IN]  ����
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks
    #  @~english
    #  @brief Open the camera devices connected to the CL capture card.
    #  @param sn		[IN]  Serial number
    #  @param ip		[IN]  ip
    #  @param mask		[IN]  mask
    #  @param gateway	[IN]  gateway
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks
    @staticmethod
    def SciCam_Gige_ModifyCamIp(sn, ip, mask, gateway):
        SciCamCtrlDll.SciCam_Gige_ModifyCamIp.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint)
        SciCamCtrlDll.SciCam_Gige_ModifyCamIp.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_Gige_ModifyCamIp(sn.encode('ascii'), ctypes.c_uint(ip), ctypes.c_uint(mask),
                                                     ctypes.c_uint(gateway))

    ## @ingroup module_Other
    #  @~chinese
    #  @brief ����GigE�豸IP��������������ص�ַ
    #  @param sn		[IN]  �豸���к�
    #  @param ip		[IN]  ip��ַ����ʽΪ�ַ�������"192.168.1.100"
    #  @param mask		[IN]  �������룬��ʽΪ�ַ�������"255.255.255.0"
    #  @param gateway	[IN]  ���أ���ʽΪ�ַ�������"192.168.1.1"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks
    #  @~english
    #  @brief Open the camera devices connected to the CL capture card.
    #  @param sn		[IN]  Serial number
    #  @param ip		[IN]  ip, e.g. "192.168.1.100"
    #  @param mask		[IN]  mask, e.g. "255.255.255.0"
    #  @param gateway	[IN]  gateway, e.g. "192.168.1.1"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks
    @staticmethod
    def SciCam_Gige_ModifyCamIpEx(sn, ip, mask, gateway):
        SciCamCtrlDll.SciCam_Gige_ModifyCamIpEx.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                                            ctypes.c_void_p)
        SciCamCtrlDll.SciCam_Gige_ModifyCamIpEx.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_Gige_ModifyCamIpEx(sn.encode('ascii'), ip.encode('ascii'), mask.encode('ascii'),
                                                       gateway.encode('ascii'))

    ## @ingroup module_DeviceInitAndDestr
    #  @~chinese
    #  @brief ��CL�ɼ������ӵ�����豸
    #  @param hDev		[IN]  �豸���
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks ֻ�ܶ�CL�ɼ������ӵ�������в���
    #  @~english
    #  @brief Open the camera devices connected to the CL capture card.
    #  @param hDev		[IN]  Device handle
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks Operations can only be performed on cameras connected to the CL capture card.
    def SciCam_CL_OpenCam(self):
        SciCamCtrlDll.SciCam_CL_OpenCam.argtype = ctypes.c_void_p
        SciCamCtrlDll.SciCam_CL_OpenCam.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_CL_OpenCam(self.handle)

    ## @ingroup module_DeviceInitAndDestr
    #  @~chinese
    #  @brief �ر�CL�ɼ������ӵ�����豸
    #  @param hDev		[IN]  �豸���
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks ֻ�ܶ�CL�ɼ������ӵ�������в���
    #  @~english
    #  @brief Disconnecting the Camera Device Connected to the CL Acquisition Card
    #  @param hDev		[IN]  Device handle
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks Operations can only be performed on cameras connected to the CL capture card.
    def SciCam_CL_CloseCam(self):
        SciCamCtrlDll.SciCam_CL_CloseCam.argtype = ctypes.c_void_p
        SciCamCtrlDll.SciCam_CL_CloseCam.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_CL_CloseCam(self.handle)

    ## @ingroup module_DeviceInitAndDestr
    #  @~chinese
    #  @brief �ж�CL�ɼ����е�����Ƿ�������
    #  @param hDev		[IN]  �豸���
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks ֻ�ܶ�CL�ɼ���������������в���
    #  @~english
    #  @brief Check if the camera in the CL capture card is connected.
    #  @param hDev		[IN]  Device handle
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks Operations can only be performed on cameras connected to the CL capture card.
    def SciCam_CL_IsCamOpen(self):
        SciCamCtrlDll.SciCam_CL_IsCamOpen.argtype = ctypes.c_void_p
        SciCamCtrlDll.SciCam_CL_IsCamOpen.restype = ctypes.c_bool
        return SciCamCtrlDll.SciCam_CL_IsCamOpen(self.handle)

    ## @ingroup module_Grab
    #  @~chinese
    #  @brief ���òɼ����ͣ�3D��ɨ���������豸��
    #  @param hDev		[IN]  �豸���
    #  @param mode		[IN]  �ɼ����ͣ���ϸ�ο��� @ref SciCamLp3dGrabMode "SciCamLp3dGrabMode"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Set the grab type(3D LP camera)
    #  @param hDev		[IN]  Device handle
    #  @param mode		[IN]  Grab type, references: @ref SciCamLp3dGrabMode "SciCamLp3dGrabMode"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_LP3D_SetGrabType(self, mode):
        SciCamCtrlDll.SciCam_LP3D_SetGrabType.argtypes = (ctypes.c_void_p, ctypes.c_int)
        SciCamCtrlDll.SciCam_LP3D_SetGrabType.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_LP3D_SetGrabType(self.handle, ctypes.c_int(mode))

    ## @ingroup module_Grab
    #  @~chinese
    #  @brief ��ʼ¼��
    #  @param hDev			[IN]  �豸���
    #  @param recoredInfo	[IN]  ¼����Ϣ����ϸ�ο��� @ref SCI_RECORD_INFO "SCI_RECORD_INFO"
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Start recording
    #  @param hDev			[IN]  Device handle
    #  @param recoredInfo	[IN]  Recording information, references: @ref SCI_RECORD_INFO "SCI_RECORD_INFO"
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_StartRecord(self, recordInfo):
        SciCamCtrlDll.SciCam_StartRecord.argtypes = (ctypes.c_void_p, PSCI_RECORD_INFO)
        SciCamCtrlDll.SciCam_StartRecord.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_StartRecord(self.handle, ctypes.byref(recordInfo))

    ## @ingroup module_Grab
    #  @~chinese
    #  @brief ����¼������
    #  @param hDev		[IN]  �豸���
    #  @param payload	[IN]  �ɼ�����payload����
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Input recording data
    #  @param hDev		[IN]  Device handle
    #  @param payload	[IN]  Payload data captured
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_InputOneFrame(self, payload):
        SciCamCtrlDll.SciCam_InputOneFrame.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        SciCamCtrlDll.SciCam_InputOneFrame.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_InputOneFrame(self.handle, payload)

    ## @ingroup module_Grab
    #  @~chinese
    #  @brief ֹͣ¼��
    #  @param hDev		[IN]  �豸���
    #  @retval �ɹ��� @ref SCI_CAMERA_OK "SCI_CAMERA_OK"(0)
    #  @retval �����μ�: @ref SciCamErrorDefine.h "״̬��"
    #  @remarks NULL
    #  @~english
    #  @brief Stop recording
    #  @param hDev		[IN]  Device handle
    #  @retval Success: @ref SCI_CAMERA_OK "SCI_CAMERA_OK"
    #  @retval Other references: @ref SciCamErrorDefine.h "Error Code List"
    #  @remarks NULL
    def SciCam_StopRecord(self):
        SciCamCtrlDll.SciCam_StopRecord.argtype = ctypes.c_void_p
        SciCamCtrlDll.SciCam_StopRecord.restype = ctypes.c_uint
        return SciCamCtrlDll.SciCam_StopRecord(self.handle)


class CameraOperation:
    def __init__(self, obj_cam, currentCam):
        self.obj_cam = obj_cam
        self.currentCam = currentCam

    def Open_Device(self):
        # self.obj_cam = SciCamera()
        self.obj_cam.SciCam_CreateDevice(self.currentCam)
        self.obj_cam.SciCam_OpenDevice()

    # SciCam_Grab
    def Start_Grabbing(self):
        reVal = self.obj_cam.SciCam_StartGrabbing()
