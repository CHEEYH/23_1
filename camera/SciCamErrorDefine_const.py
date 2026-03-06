# coding: utf-8

SCI_CAMERA_OK								        = 0			    # < \~chinese 成功					\~english Success

SCI_ERR_CAMERA_INCORRECT_INIT_OBJECT		        = 100100001	    # < \~chinese 对象初始化错误		    \~english Incorrect initialization object
SCI_ERR_CAMERA_PARAM_INVALID				        = 100100002	    # < \~chinese 参数无效错误			\~english Parameter is invalid
SCI_ERR_CAMERA_SDK_VERSION_MISMATCH			        = 100100003	    # < \~chinese SDK版本不匹配错误		\~english SDK version mismatch
SCI_ERR_CAMERA_UNKNOW						        = 100100004	    # < \~chinese 未知错误				\~english Unknow error
SCI_ERR_CAMERA_FUNCTION_CONFLICT                    = 100100006		# < \~chinese 功能或接口调用存在冲突	\~english Function or interface call conflict.

SCI_ERR_CAMERA_ENUM_DEVICES_FAILED			        = 100100005	    # < \~chinese 搜索相机错误			\~english Failed to search Camera
SCI_ERR_CAMERA_MODIFY_IP_ADDRESS_FAILED             = 100100007     # < \~chinese 设置相机IP失败			\~english Failed to modify camera ip address.
SCI_ERR_CAMERA_SET_PERSISTENT_IP_FAILED             = 100100008     # < \~chinese 设置永久性IP失败		    \~english Failed to modify persistent camera ip address.
SCI_ERR_CAMERA_CREATE_FAILED				        = 100100009	    # < \~chinese 创建相机对象失败		    \~english Failed to create a camera object
SCI_ERR_CAMERA_EXCEPTION					        = 100100010	    # < \~chinese 相机操作异常错误		    \~english Camera operation exception
SCI_ERR_CAMERA_NOT_FOUND					        = 100100011	    # < \~chinese 查找相机失败错误		    \~english Cannot to find Camera
SCI_ERR_CAMERA_OFFLINE						        = 100100012	    # < \~chinese 相机已掉线			    \~english Camera is offline
SCI_ERR_CAMERA_OPEN_FAILED					        = 100100013	    # < \~chinese 打开相机失败			\~english Failed to open camera
SCI_ERR_CAMERA_NOT_MISMATCHACQ				        = 100100014	    # < \~chinese 相机与采集库不匹配	    \~english Camera mismatch witch ACQ
SCI_ERR_CAMERA_NOT_SUPPORT					        = 100100015	    # < \~chinese 相机不支持			    \~english Camera does not support
SCI_ERR_CAMERA_NOT_OPEN						        = 100100016	    # < \~chinese 相机未打开			    \~english Camera isn't open
SCI_ERR_CAMERA_ALLREADY_OPEN				        = 100100017	    # < \~chinese 相机已打开			    \~english Camera allready open
SCI_ERR_CAMERA_OCCUPANCY					        = 100100018	    # < \~chinese 相机被占用			    \~english Camera occupied by another device
SCI_ERR_CAMERA_ROMOVED						        = 100100019	    # < \~chinese 相机已被移除			\~english The camera was removed

SCI_ERR_CAMERA_START_GRAB_FAILED			        = 100100020	    # < \~chinese 开始采集失败			\~english Failed to start grab
SCI_ERR_CAMERA_NOT_GRABBING					        = 100100021	    # < \~chinese 相机未打开采集		    \~english Camera isn't grabbing
SCI_ERR_CAMERA_GRABBING						        = 100100022	    # < \~chinese 相机已开启采集		    \~english Camera is grabbing
SCI_ERR_CAMERA_GRAB_FAILED					        = 100100023	    # < \~chinese 相机采集失败			\~english Camera grab failed
SCI_ERR_CAMERA_GRAB_TIMEOUT					        = 100100024	    # < \~chinese 相机采集超时			\~english Grab image timeout
SCI_ERR_CAMERA_TRIGGER_WAIT_FAILED			        = 100100025	    # < \~chinese 等待触发错误			\~english Wait for trigger failed
SCI_ERR_CAMERA_SOFTWARE_TRIGGER_FAILED		        = 100100026	    # < \~chinese 软触发失败			    \~english Failed to set software trigger
SCI_ERR_CAMERA_GRAB_EXCEPTION				        = 100100027	    # < \~chinese 相机采集其他异常		    \~english Camera grab image exception
SCI_ERR_CAMERA_GRAB_INTERRUPTED                     = 100100028     # < \~chinese 采集被中断				\~english Capture interrupted.
SCI_ERR_CAMERA_GRAB_INSUFFICIENT_BUFFER             = 100100029     # < \~chinese 采集缓冲区不足			\~english Insufficient buffer for capture.

SCI_ERR_CAMERA_SET_VALUE_FAILED				        = 100100030	    # < \~chinese 设置参数错误			\~english Failed to set parameter value
SCI_ERR_CAMERA_GET_VALUE_FAILED				        = 100100031	    # < \~chinese 获取参数错误			\~english Failed to Get parameter value
SCI_ERR_CAMERA_SEND_CMD_FAILED				        = 100100032	    # < \~chinese 发送命令错误			\~english Failed to send command
SCI_ERR_CAMERA_WRONG_ACK					        = 100100033	    # < \~chinese 接受应答错误			\~english Get ACK failed, maybe result of wrong IP
SCI_ERR_CAMERA_FILE_OPEN_FAILED				        = 100100034	    # < \~chinese 打开相机配置文件错误	    \~english Open camera configuration file error

SCI_ERR_CAMERA_NODE_XML_TYPE                        = 100100040     # < \~chinese xml类型错误			    \~english XML type error.
SCI_ERR_CAMERA_NODE_NAME_INVALID			        = 100100041	    # < \~chinese 节点名称无效			\~english Node name is invalid
SCI_ERR_CAMERA_NODE_READ_FORBIDDEN			        = 100100042	    # < \~chinese 该节点禁止读取		    \~english Node is forbidden to read
SCI_ERR_CAMERA_NODE_WRITE_FORBIDDEN			        = 100100043	    # < \~chinese 该节点禁止写入		    \~english Node is forbidden to write
SCI_ERR_CAMERA_NODE_TYPE_INVALID			        = 100100044	    # < \~chinese 该节点类型无效		    \~english Node type is invalid
SCI_ERR_CAMERA_NODE_TYPE_UNMATCH			        = 100100045	    # < \~chinese 该节点类型不匹配		    \~english Node type is unmatched
SCI_ERR_CAMERA_NODE_VALUE					        = 100100046	    # < \~chinese 该节点值错误			\~english The value of node is wrong
SCI_ERR_CAMERA_NODE_MAP_INVALID				        = 100100047	    # < \~chinese 节点树无效			    \~english Failed to access the node map
SCI_ERR_CAMERA_NODE_GET_ROOT_NODE_FAILED            = 100100048     # < \~chinese 获取Root节点失败		\~english Failed to get root node.
SCI_ERR_CAMERA_NODE_TRAVERSE                        = 100100049     # < \~chinese 遍历节点失败			\~english Failed to traverse nodes.

SCI_ERR_CAMERA_IMAGE_INVALID				        = 100100050	    # < \~chinese 图像数据无效			\~english Image data is invalid
SCI_ERR_CAMERA_IMAGE_CREATE_FAILED			        = 100100051	    # < \~chinese 创建图像失败			\~english Failed to create image file
SCI_ERR_CAMERA_IMAGE_TYPE_NOT_SUPPORT		        = 100100052	    # < \~chinese 图像类型不支持		    \~english Image type does not support
SCI_ERR_CAMERA_IMAGE_NOT_COMPLETE			        = 100100053	    # < \~chinese 采集图像不完整		    \~english Grab Image not complete
SCI_ERR_CAMERA_IMAGE_DATACONVERT_FAILED		        = 100100054	    # < \~chinese 图像转换失败			\~english Failed to convert to image
SCI_ERR_CAMERA_IMAGE_FORMAT					        = 100100055	    # < \~chinese 图像格式错误			\~english Image format is wrong
SCI_ERR_CAMERA_IMAGE_GET_PROPERTY                   = 100100056     # < \~chinese 获取图像属性失败		    \~english Failed to get image properties (e.g., width, height).
SCI_ERR_CAMERA_IMAGE_OUT_OF_BOUNDS                  = 100100057     # < \~chinese 图像数据越界			\~english Image data out of bounds.
SCI_ERR_CAMERA_IMAGE_SAVE_FAILED                    = 100100058     # < \~chinese 图像保存失败			\~english Failed to save image.

SCI_ERR_CAMERA_CHUNKDATA_EMPTY				        = 100100060	    # < \~chinese ChunkData为空			\~english Chunk data is empty
SCI_ERR_CAMERA_CHUNKDATA_LENGTH				        = 100100061	    # < \~chinese ChunkData长度异常		\~english Chunk data length is abnormal
SCI_ERR_CAMERA_CHUNKDATA_PARSING_EXCEPTION          = 100100062     # < \~chinese 解析ChunkData异常		\~english Chunk parsing exception.

SCI_ERR_CAMERA_MEMORY_ALLOCATION_FAILED             = 100100070     # < \~chinese 申请内存失败			\~english Memory allocation failed.
SCI_ERR_CAMERA_APPEND_BUFFER_FAILED                 = 100100071     # < \~chinese 追加缓存失败			\~english Failed to append buffer.
SCI_ERR_CAMERA_SYSTEM_RESOURCE_EXHAUSTED            = 100100072     # < \~chinese 系统资源耗尽			\~english System resource exhausted.
SCI_ERR_CAMERA_INSUFFICIENT_MEMORY_LENGTH           = 100100073     # < \~chinese 目标地址内存长度不足	    \~english Insufficient memory length at the target address.

SCI_ERR_CAMERA_GET_CTI_OBJECT_NULL					= 100120001		# < \~chinese 获取CTI对象为空						    \~english Failed to get CTI object.
SCI_ERR_CAMERA_GET_ANY_PORT_FAILED					= 100120002		# < \~chinese 获取采集卡端口或数据流端口或设备端口为空	\~english Failed to get any port (card port, data stream port, or device port) is null.
SCI_ERR_CAMERA_GET_IF_PORT_FAILED					= 100120003		# < \~chinese 获取IF端口为空							\~english Failed to get IF port.
SCI_ERR_CAMERA_GET_DEVICE_PORT_FAILED				= 100120004		# < \~chinese 获取设备端口失败						    \~english Failed to get device port.
SCI_ERR_CAMERA_GET_DEVICE_DATA_STREAM_PORT_FAILED	= 100120005		# < \~chinese 获取设备数据流端口失败					\~english Failed to get device data stream port.
SCI_ERR_CAMERA_GET_DEVICE_DATA_STREAM_FAILED		= 100120006		# < \~chinese 获取设备数据流失败						\~english Failed to get device data stream.
SCI_ERR_CAMERA_GET_DEVICE_DATA_STREAM_COUNT_ZERO	= 100120007		# < \~chinese 获取设备数据流个数为0					\~english Device data stream count is zero.
SCI_ERR_CAMERA_GET_DATA_STREAM_ID_FAILED			= 100120008		# < \~chinese 获取设备数据流ID失败					    \~english Failed to get device data stream ID.
SCI_ERR_CAMERA_OPEN_DATA_STREAM_FAILED				= 100120009		# < \~chinese 打开数据流失败							\~english Failed to open data stream.
SCI_ERR_CAMERA_NODEMAP_NULL							= 100120010		# < \~chinese 获取设备nodemap为空					    \~english Device nodemap is null.
SCI_ERR_CAMERA_PAYLOAD_SIZE_INVALID					= 100120011		# < \~chinese 获取payloadsize无效					    \~english Invalid payload size.
SCI_ERR_CAMERA_REGISTER_IMAGE_EVENT_FAILED			= 100120012		# < \~chinese 注册图像事件失败						    \~english Failed to register image event.
SCI_ERR_CAMERA_CTI									= 100120013		# < \~chinese CTI错误								\~english CTI error.
SCI_ERR_CAMERA_DS									= 100120014		# < \~chinese DS错误								    \~english DS error.
SCI_ERR_CAMERA_GEN_TL_EVENT							= 100120015		# < \~chinese GenTL Event错误						\~english GenTL Event error.
SCI_ERR_CAMERA_BUF									= 100120016		# < \~chinese BUF错误								\~english Buf error.