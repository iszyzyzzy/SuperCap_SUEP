#ifndef C_WRAPPER_H
#define C_WRAPPER_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// 不直接引用或声明 C++ 的 can_value_type，使用不透明指针
typedef void (*can_frame_callback_t)(const void* /* can_value_type* */);

// 句柄类型
typedef void* usb_class_handle;

usb_class_handle usb_class_new(uint32_t nom_baud, uint32_t dat_baud, const char* sn);
void usb_class_delete(usb_class_handle obj);

void usb_class_set_frame_callback(usb_class_handle obj, can_frame_callback_t cb);
/* data 为原始字节数组，dlc 为长度 */
void usb_class_fdcan_frame_send(usb_class_handle obj, uint8_t* data, uint32_t can_id, uint8_t dlc);

#ifdef __cplusplus
}
#endif

#endif // C_WRAPPER_H
