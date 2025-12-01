#include "c_wrapper.h"
#include "protocol/usb_class.h"
#include <vector>
#include <functional>
#include <string>

// 全局 C 回调（简单示例）
static can_frame_callback_t g_callback = nullptr;

// C++ -> C 的桥接函数：接收真实的 can_value_type 并把地址以 void* 传给 C 回调
void frame_callback_handler(can_value_type& value) {
    if (g_callback) {
        // 把指针当作不透明指针传出去
        g_callback(static_cast<const void*>(&value));
    }
}

extern "C" {

usb_class_handle usb_class_new(uint32_t nom_baud, uint32_t dat_baud, const char* sn) {
    return static_cast<usb_class_handle>(new usb_class(nom_baud, dat_baud, std::string(sn)));
}

void usb_class_delete(usb_class_handle obj) {
    if (obj) {
        delete static_cast<usb_class*>(obj);
    }
}

void usb_class_set_frame_callback(usb_class_handle obj, can_frame_callback_t cb) {
    if (!obj) return;
    g_callback = cb;
    usb_class* instance = static_cast<usb_class*>(obj);
    if (cb) {
        instance->setFrameCallback(frame_callback_handler);
    } else {
        instance->setFrameCallback({});
    }
}

void usb_class_fdcan_frame_send(usb_class_handle obj, uint8_t* data, uint32_t can_id, uint8_t dlc) {
    if (!obj) return;
    usb_class* instance = static_cast<usb_class*>(obj);
    std::vector<uint8_t> data_vec(data, data + dlc);
    instance->fdcanFrameSend(data_vec, can_id);
}

} // extern "C"
