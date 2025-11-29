# SuperCap Debugger README

This directory contains a Python-based GUI application for debugging the RM2025 Power Control Board.

## Features

- **Real-time Control:** Send control packets to the power board via CAN bus.
- **Data Monitoring:** Receive and display feedback data from the power board.
- **UI Interface:** A simple graphical user interface to set control parameters and view feedback.
- **Data Plotting:** Forwards data to a local UDP port for easy plotting with tools like VOFA+.

## Prerequisites

- **Python 3:** The application is written in Python 3.
- **`python-can` library:** This library is required for CAN communication. Install it using pip:
  ```bash
  pip install python-can
  ```
- **`customtkinter` library:** Used for a modern UI look. Install it using pip:
  ```bash
  pip install customtkinter
  ```
- **CAN Hardware:** A USB-to-CAN adapter (e.g., PCAN, Vector, Kvaser, or a compatible slcan device) is required to connect the computer to the CAN bus.

## How to Run

1.  **Connect Hardware:** Connect your USB-to-CAN adapter to your computer and the CAN bus of the power control board.
2.  **Configure CAN:** Open the `debugger.py` script and modify the `CAN_INTERFACE` and `CAN_BITRATE` variables to match your hardware and setup.
3.  **Run the script:**
    ```bash
    python debugger.py
    ```

## UDP Data Forwarding

The application forwards received data to `localhost` on port `23456`. The data is sent as a string with key-value pairs, terminated by a newline character.

**Format:** `key1=value1,key2=value2\r\n`

**Example:** `chassisPower=10.5,refereePower=55.1,capEnergy=125\r\n`

You can use a tool like [VOFA+](https://vofa.plus/) to receive this UDP stream and plot the data in real-time.
- In VOFA+, set up a data source with the "Net Assistant" protocol.
- Set the IP to `127.0.0.1` and the port to `23456`.
- Configure the data format to match the sent string.
