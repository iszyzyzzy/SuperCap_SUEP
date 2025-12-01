//! SuperCap Debugger GUI in Rust with Iced.

// Wrap the generated bindings in a module
mod bindings {
    #![allow(non_upper_case_globals)]
    #![allow(non_camel_case_types)]
    #![allow(non_snake_case)]
    #![allow(dead_code)]
    include!(concat!(env!("OUT_DIR"), "/bindings.rs"));
}

use iced::widget::{
    button, checkbox, column, container, row, text, text_input, toggler,
    scrollable, vertical_space,
};
use iced::{Alignment, Element, Length, Sandbox, Settings, Theme};
use std::fmt;
use std::time::Instant;

// --- Configuration ---
const NOMINAL_BITRATE: u32 = 1_000_000;
const DATA_BITRATE: u32 = 5_000_000;
const DEFAULT_SN: &str = "14AA044B241402B10DDBDAFE448040BB";

const CONTROL_CAN_ID: u32 = 0x050;
const FEEDBACK_CAN_ID_OLD: u32 = 0x051;
const FEEDBACK_CAN_ID_NEW: u32 = 0x052;

// --- Data Structures ---

/// Data sent to the power board (Master -> SuperCap)
#[derive(Debug, Clone)]
struct ControlTxData {
    pub enable_dcdc: bool,
    pub system_restart: bool,
    pub clear_error: bool,
    pub enable_active_charging_limit: bool,
    pub use_new_feedback_message: bool,
    pub referee_power_limit: u16,
    pub referee_energy_buffer: u16,
    pub active_charging_limit_ratio: u8,
}

impl Default for ControlTxData {
    fn default() -> Self {
        Self {
            enable_dcdc: false,
            system_restart: false,
            clear_error: false,
            enable_active_charging_limit: false,
            use_new_feedback_message: true,
            referee_power_limit: 80,
            referee_energy_buffer: 50,
            active_charging_limit_ratio: 200,
        }
    }
}

impl ControlTxData {
    pub fn pack(&self) -> [u8; 8] {
        let mut byte0: u8 = 0;
        if self.enable_dcdc { byte0 |= 0x01; }
        if self.system_restart { byte0 |= 0x01 << 1; }
        if self.clear_error { byte0 |= 0x01 << 5; }
        if self.enable_active_charging_limit { byte0 |= 0x01 << 6; }
        if self.use_new_feedback_message { byte0 |= 0x01 << 7; }

        let mut data_bytes = Vec::with_capacity(8);
        data_bytes.push(byte0);
        data_bytes.extend_from_slice(&self.referee_power_limit.to_le_bytes());
        data_bytes.extend_from_slice(&self.referee_energy_buffer.to_le_bytes());
        data_bytes.push(self.active_charging_limit_ratio);
        data_bytes.resize(8, 0); // Pad to 8 bytes

        let mut result = [0u8; 8];
        result.copy_from_slice(&data_bytes);
        result
    }
}

/// Data received from the power board, parsed from raw bytes.
#[derive(Debug, Clone, Default)]
struct FeedbackRxData {
    pub status_code: u8,
    pub cap_energy: u16,
    pub chassis_power_limit: u16,
    pub chassis_power_new: f32,
    pub referee_power_new: f32,
    pub chassis_power_old: f32,
    pub is_new_format: bool,
}

/// Struct representing the memory layout of can_value_type from C++
/// This is for manual parsing and must match the C++ layout.
#[repr(C, packed)]
struct CanValueRaw {
    // can_head_type
    id: u32,
    time_stamp: u32,
    reserve: [u8; 3],
    bitfields: u8, // Packed bitfields: fram_type, can_type, id_type, dir, dlc
    // can_value_type data
    data: [u8; 64],
}

impl FeedbackRxData {
    /// Unpacks data from an opaque pointer to a `can_value_type` struct.
    pub fn unpack_from_ptr(&mut self, ptr: *const std::ffi::c_void) -> bool {
        if ptr.is_null() {
            return false;
        }

        unsafe {
            let raw_struct = &*(ptr as *const CanValueRaw);
            let can_id = raw_struct.id;
            let dlc = raw_struct.bitfields & 0x0F; // dlc is the lower 4 bits
            let data_slice = &raw_struct.data[..dlc as usize];

            if can_id == FEEDBACK_CAN_ID_NEW && data_slice.len() >= 7 {
                self.status_code = data_slice[0];
                let chassis_power_raw = u16::from_le_bytes([data_slice[1], data_slice[2]]);
                let referee_power_raw = u16::from_le_bytes([data_slice[3], data_slice[4]]);
                self.chassis_power_limit = u16::from(data_slice[5]);
                self.cap_energy = u16::from(data_slice[6]);

                self.chassis_power_new = (chassis_power_raw as f32 - 16384.0) / 64.0;
                self.referee_power_new = (referee_power_raw as f32 - 16384.0) / 64.0;
                self.is_new_format = true;
                true
            } else if can_id == FEEDBACK_CAN_ID_OLD && data_slice.len() >= 8 {
                self.status_code = data_slice[0];
                self.chassis_power_old = f32::from_le_bytes([data_slice[1], data_slice[2], data_slice[3], data_slice[4]]);
                self.chassis_power_limit = u16::from_le_bytes([data_slice[5], data_slice[6]]);
                self.cap_energy = u16::from(data_slice[7]);
                self.is_new_format = false;
                true
            } else {
                false
            }
        }
    }

    pub fn get_power_stage(&self) -> &'static str {
        if (self.status_code >> 7) & 1 == 1 { "ON" } else { "OFF" }
    }
    pub fn get_feedback_format(&self) -> &'static str {
        if (self.status_code >> 6) & 1 == 1 { "New (0x052)" } else { "Old (0x051)" }
    }
    pub fn get_control_limit(&self) -> &'static str {
        let reasons = ["None", "Vcap Max", "Vbus Max", "Ibus Max", "I_L Max"];
        reasons.get(((self.status_code >> 2) & 0b111) as usize).unwrap_or(&"Unknown")
    }
    pub fn get_error_level(&self) -> &'static str {
        let levels = ["No Error", "Warning", "Error", "Fatal"];
        levels.get((self.status_code & 0b11) as usize).unwrap_or(&"Unknown")
    }
}

/// Represents the overall state of the application.
#[derive(Debug)]
struct App {
    serial_number: String,
    connection_status: ConnectionStatus,
    can_manager_handle: Option<bindings::usb_class_handle>,
    tx_data: ControlTxData,
    rx_data: FeedbackRxData,
    auto_send_enabled: bool,
    log_messages: Vec<String>,
    last_ui_update: Instant,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ConnectionStatus { Disconnected, Connecting, Connected, Error }

impl fmt::Display for ConnectionStatus {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result { write!(f, "{:?}", self) }
}

#[derive(Debug, Clone)]
enum Message {
    SerialNumberInputChanged(String),
    ConnectButtonPressed,
    FindSNButtonPressed,
    ToggleAutoSend(bool),
    EnableDcdcToggled(bool),
    SystemRestartToggled(bool),
    ClearErrorToggled(bool),
    EnableActiveChargingLimitToggled(bool),
    UseNewFeedbackMessageToggled(bool),
    RefereePowerLimitInputChanged(String),
    RefereeEnergyBufferInputChanged(String),
    ActiveChargingLimitRatioInputChanged(String),
    SendOnceButtonPressed,
    // Message now holds the raw pointer. It must be handled immediately in `update`.
    CanMessageReceived(*const std::ffi::c_void),
    Log(String),
    Tick,
}

impl Sandbox for App {
    type Message = Message;

    fn new() -> Self {
        Self {
            serial_number: DEFAULT_SN.to_string(),
            connection_status: ConnectionStatus::Disconnected,
            can_manager_handle: None,
            tx_data: ControlTxData::default(),
            rx_data: FeedbackRxData::default(),
            auto_send_enabled: false,
            log_messages: Vec::new(),
            last_ui_update: Instant::now(),
        }
    }

    fn title(&self) -> String { String::from("SuperCap Debugger (Rust Iced)") }

    fn update(&mut self, message: Message) {
        match message {
            Message::SerialNumberInputChanged(s) => self.serial_number = s,
            Message::ConnectButtonPressed => { /* Simulated connection logic */ },
            Message::FindSNButtonPressed => self.log_messages.push("Find SN: Not implemented".to_string()),
            Message::ToggleAutoSend(enable) => self.auto_send_enabled = enable,
            Message::EnableDcdcToggled(b) => self.tx_data.enable_dcdc = b,
            Message::SystemRestartToggled(b) => self.tx_data.system_restart = b,
            Message::ClearErrorToggled(b) => self.tx_data.clear_error = b,
            Message::EnableActiveChargingLimitToggled(b) => self.tx_data.enable_active_charging_limit = b,
            Message::UseNewFeedbackMessageToggled(b) => self.tx_data.use_new_feedback_message = b,
            Message::RefereePowerLimitInputChanged(s) => if let Ok(val) = s.parse() { self.tx_data.referee_power_limit = val },
            Message::RefereeEnergyBufferInputChanged(s) => if let Ok(val) = s.parse() { self.tx_data.referee_energy_buffer = val },
            Message::ActiveChargingLimitRatioInputChanged(s) => if let Ok(val) = s.parse() { self.tx_data.active_charging_limit_ratio = val },
            Message::SendOnceButtonPressed => self.log_messages.push("Send Once: Not implemented".to_string()),
            Message::CanMessageReceived(ptr) => {
                if self.rx_data.unpack_from_ptr(ptr) {
                    // Successfully parsed, UI will update on next view()
                    // In a real `Application`, you might need to request a redraw.
                } else {
                    self.log_messages.push("Failed to unpack CAN message".to_string());
                }
            },
            Message::Log(msg) => self.log_messages.push(msg),
            Message::Tick => { /* Periodic update logic can go here */ },
        }
    }

    fn view(&self) -> Element<Message> {
        let connection_frame = row![
            text("Device SN:"),
            text_input(&self.serial_number, Message::SerialNumberInputChanged)
                .width(Length::Fixed(300.0)).padding(5),
            button("Find SN").on_press(Message::FindSNButtonPressed).width(Length::Fixed(80.0)),
            button(if self.connection_status == ConnectionStatus::Disconnected { "Connect" } else { "Disconnect" })
                .on_press(Message::ConnectButtonPressed).width(Length::Fixed(100.0)),
            text(self.connection_status.to_string())
        ]
        .spacing(10).align_items(Alignment::Center);

        let tx_frame = column![
            text("Transmit Control").size(20),
            checkbox("Enable DCDC", self.tx_data.enable_dcdc).on_toggle(Message::EnableDcdcToggled),
            checkbox("System Restart", self.tx_data.system_restart).on_toggle(Message::SystemRestartToggled),
            checkbox("Clear Error", self.tx_data.clear_error).on_toggle(Message::ClearErrorToggled),
            checkbox("Enable Active Charging Limit", self.tx_data.enable_active_charging_limit).on_toggle(Message::EnableActiveChargingLimitToggled),
            toggler(Some("New Feedback".to_string()), self.tx_data.use_new_feedback_message, Message::UseNewFeedbackMessageToggled),
            text_input(&self.tx_data.referee_power_limit.to_string(), Message::RefereePowerLimitInputChanged).padding(5),
            text_input(&self.tx_data.referee_energy_buffer.to_string(), Message::RefereeEnergyBufferInputChanged).padding(5),
            text_input(&self.tx_data.active_charging_limit_ratio.to_string(), Message::ActiveChargingLimitRatioInputChanged).padding(5),
            button("Send Once").on_press(Message::SendOnceButtonPressed),
            toggler(Some("Auto-Send".to_string()), self.auto_send_enabled, Message::ToggleAutoSend)
        ].spacing(10);

        let rx_frame = column![
            text("Receive Feedback").size(20),
            text(format!("Chassis Power: {:.2} W", if self.rx_data.is_new_format { self.rx_data.chassis_power_new } else { self.rx_data.chassis_power_old })),
            text(format!("Referee Power: {:.2} W", self.rx_data.referee_power_new)),
            text(format!("Chassis Power Limit: {} W", self.rx_data.chassis_power_limit)),
            text(format!("Cap Energy: {}", self.rx_data.cap_energy)),
            vertical_space().height(Length::Fixed(20.0)),
            text("Status Code Details").size(16),
            text(format!("Power Stage: {}", self.rx_data.get_power_stage())),
            text(format!("Feedback Format: {}", self.rx_data.get_feedback_format())),
            text(format!("Control Loop Limit: {}", self.rx_data.get_control_limit())),
            text(format!("Error Level: {}", self.rx_data.get_error_level()))
        ].spacing(10);

        let log_frame = column![
            text("Log Messages").size(20),
            scrollable(column(self.log_messages.iter().map(|s| text(s).into()).collect()).spacing(2))
        ].spacing(10);

        container(
            column![
                connection_frame,
                row![tx_frame.width(Length::FillPortion(1)), rx_frame.width(Length::FillPortion(2))].spacing(10),
                log_frame.height(Length::Fill),
            ]
            .spacing(10)
            .padding(10)
        )
        .width(Length::Fill)
        .height(Length::Fill)
        .center_x()
        .into()
    }

    fn theme(&self) -> Theme { Theme::Dark }
}

pub fn main() -> iced::Result {
    App::run(Settings::default())
}