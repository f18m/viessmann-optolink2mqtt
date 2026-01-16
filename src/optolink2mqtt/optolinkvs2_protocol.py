"""
optolinkvs2_protocol.py
----------------
Optolink VS2 / 300 Protocol handler
Reworked by Francesco Montorsi based on the original code by philippoo66
by making it object-oriented and easier to integrate in other projects,
decoupling from MQTT and remoing references to global variables.

TODO: collect return codes in an Enum
TODO: replace hardcoded protocol constants with named constants
TODO: add stats for errors, timeouts, retries, etc.

----------------

Copyright 2024 philippoo66

Licensed under the GNU GENERAL PUBLIC LICENSE, Version 3 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.gnu.org/licenses/gpl-3.0.html

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import time
import serial
import logging


class OptolinkVS2RxData:
    """
    OptolinkVS2RxData holds a VS2 telegram received over Optolink interface,
    plus some extra attribute:

    1. **ReturnCode (int)**
        Receive status code:
        - 0x01 = Success
        - 0x03 = Error message
        - 0x15 = NACK
        - 0x20 = Byte0 unknown error
        - 0x41 = STX error
        - 0xAA = Handle lost
        - 0xFD = Packet length error
        - 0xFE = CRC error
        - 0xFF = Timeout

    2. **Addr (int)**
        Address of the data point.

    3. **Data (bytearray)**
        Payload data of the received telegram.
    """

    def __init__(self, return_code: int, address: int, data: bytearray):
        self.return_code = return_code
        self.address = address
        self.data = data

    def is_successful(self) -> bool:
        return self.return_code == 0x01


class OptolinkVS2Protocol:
    """
    Optolink VS2 / 300 Protocol handler

    See https://github.com/sarnau/InsideViessmannVitosoft/blob/main/VitosoftCommunication.md
        https://github.com/openv/openv/wiki/Protokoll-300
    """

    def __init__(
        self,
        ser: serial.Serial,
        ser2: serial.Serial = None,
        show_opto_rx: bool = False,
    ):
        """
        Parameters
        ----------
        ser : serial.Serial
            Primary serial interface
        ser2 : serial.Serial, optional
            Secondary serial interface. This is used in the original optolink-splitter project
            to forward every received byte to another serial port connected to the Vitoconnect device.
            This is currently not supported by optolink2mqtt but might be in future.
        show_opto_rx : bool, optional
            If True, received Optolink bytes are logged for debugging purposes
        """
        self.ser = ser
        self.ser2 = ser2
        self.show_opto_rx = show_opto_rx

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def init_vs2(self) -> bool:
        # after the serial port read buffer is emptied
        self.ser.reset_input_buffer()
        # then an EOT (0x04) is send
        self.ser.write(bytes([0x04]))  # EOT

        # and for 30x100ms waited for an ENQ (0x05)
        for _ in range(30):
            time.sleep(0.1)
            buff = self.ser.read(1)
            if self.show_opto_rx:
                logging.debug(buff)
            if buff and buff[0] == 0x05:  # ENQ
                break
        else:
            logging.error("VS2: Timeout waiting for 0x05")
            return False

        self.ser.reset_input_buffer()

        # after which a VS2_START_VS2, 0, 0 (0x16,0x00,0x00) is send
        self.ser.write(bytes([0x16, 0x00, 0x00]))  # START_VS2

        # and within 30x100ms an VS2_ACK (0x06) is expected.
        for _ in range(30):
            time.sleep(0.1)
            buff = self.ser.read(1)
            if self.show_opto_rx:
                logging.debug(buff)
            if buff and buff[0] == 0x06:  # ACK
                logging.info("VS2 Protocol initialized successfully")
                return True

        logging.error("VS2: Timeout waiting for 0x06")
        return False

    # ------------------------------------------------------------------
    # Datapoint read/write
    # ------------------------------------------------------------------

    # deprecated because does not return error code
    # def read_datapoint(self, addr: int, rdlen: int) -> bytes:
    #     rxdata = self.read_datapoint_ext(addr, rdlen)
    #     return rxdata.data

    def read_datapoint_ext(self, addr: int, rdlen: int) -> OptolinkVS2RxData:
        outbuff = bytearray(8)
        outbuff[0] = 0x41  # 0x41 frame start
        outbuff[1] = 0x05  # Len Payload
        outbuff[2] = 0x00  # 0x00 Request Message
        outbuff[3] = 0x01  # Virtual_READ
        outbuff[4] = (addr >> 8) & 0xFF  # hi byte
        outbuff[5] = addr & 0xFF  # lo byte
        outbuff[6] = rdlen  # how many bytes to read
        outbuff[7] = self.calc_crc(outbuff)

        self.ser.reset_input_buffer()
        self.ser.write(outbuff)

        return self.receive_telegram(resptelegr=True, raw=False)

    # deprecated because does not return error code
    # def write_datapoint(self, addr: int, data: bytes) -> bool:
    #     retcode, _, _ = self.write_datapoint_ext(addr, data)
    #     return retcode == 0x01

    def write_datapoint_ext(self, addr: int, data: bytes) -> OptolinkVS2RxData:
        wrlen = len(data)
        outbuff = bytearray(wrlen + 8)
        outbuff[0] = 0x41
        outbuff[1] = 5 + wrlen
        outbuff[2] = 0x00
        outbuff[3] = 0x02  # Virtual_WRITE
        outbuff[4] = (addr >> 8) & 0xFF
        outbuff[5] = addr & 0xFF
        outbuff[6] = wrlen

        outbuff[7 : 7 + wrlen] = data
        outbuff[7 + wrlen] = self.calc_crc(outbuff)

        self.ser.reset_input_buffer()
        self.ser.write(outbuff)

        return self.receive_telegram(resptelegr=True, raw=False)

    # ------------------------------------------------------------------
    # Generic request
    # ------------------------------------------------------------------

    def do_request(
        self, fctcode: int, addr: int, rlen: int, data: bytes = b"", protid: int = 0x00
    ) -> OptolinkVS2RxData:
        pldlen = 5 + len(data)
        outbuff = bytearray(pldlen + 3)  # + STX, LEN, CRC

        outbuff[0] = 0x41  # 0x41 frame start
        outbuff[1] = pldlen  # Len Payload
        outbuff[2] = protid  # Protocol|MsgIdentifier
        # function code (sequence num is suppressed/ignored/overwritten here)
        outbuff[3] = fctcode & 0xFF
        outbuff[4] = (addr >> 8) & 0xFF  # hi byte
        outbuff[5] = addr & 0xFF  # lo byte
        outbuff[6] = rlen
        outbuff[7 : 7 + len(data)] = data
        outbuff[-1] = self.calc_crc(outbuff)

        logging.debug(OptolinkVS2Protocol.readable_hex(outbuff))

        self.ser.reset_input_buffer()
        self.ser.write(outbuff)

        return self.receive_telegram(resptelegr=True, raw=False)

    # ------------------------------------------------------------------
    # Telegram receive
    # ------------------------------------------------------------------

    def receive_telegram(self, resptelegr: bool, raw: bool) -> OptolinkVS2RxData:
        """
        Receives a VS2 telegram in response to a Virtual_READ or Virtual_WRITE request.

        Parameters:
        ---------
        resptelegr: bool
            If True, the received telegram is interpreted as a response telegram.
            If False, a regular data telegram is expected.

        raw: bool
            Specifies whether the receive mode is raw (unprocessed).
            True = Raw data mode (no protocol evaluation),
            False = Decoded protocol data.

        Return values:
        -------------

        An OptolinkVS2RxData instance.

        Notes:
        ---------
        This function will block until the message has been fully received or a timeout has occurred.
        """
        state = 0
        inbuff = bytearray()
        alldata = bytearray()
        retdata = bytearray()
        addr = 0
        # msgid = 0x100  # message type identifier, byte 2 (3. byte; 0 = Request Message, 1 = Response Message, 2 = UNACKD Message, 3 = Error Message)
        # msqn = 0x100  # message sequence number, top 3 bits of byte 3
        # fctcd = 0x100  # function code, low 5 bis of byte 3 (https://github.com/sarnau/InsideViessmannVitosoft/blob/main/VitosoftCommunication.md#defined-commandsfunction-codes)
        # dlen = -1

        # for up 30x100ms serial data is read. (we do 600x5ms)
        for _ in range(600):
            time.sleep(0.005)
            try:
                inbytes = self.ser.read_all()
                if inbytes:
                    inbuff += inbytes
                    alldata += inbytes
                    if self.ser2:
                        self.ser2.write(inbytes)
            except Exception:
                return OptolinkVS2RxData(0xAA, 0, retdata)

            if state == 0:
                if not resptelegr:
                    state = 1
                elif len(inbuff) > 0:
                    if self.show_opto_rx:
                        logging.debug(f"VS2 received: {inbuff.hex()}")

                    if inbuff[0] == 0x06:  # VS2_ACK
                        state = 1
                        # keep going...

                    elif inbuff[0] == 0x15:  # VS2_NACK
                        logging.error("VS2 NACK Error")
                        return OptolinkVS2RxData(
                            0x15, addr, alldata if not raw else bytearray(alldata)
                        )
                    else:
                        logging.error("VS2 unknown first byte error")
                        return OptolinkVS2RxData(
                            0x20, addr, alldata if not raw else bytearray(alldata)
                        )

                    # Separate the first byte
                    inbuff = inbuff[1:]

            # From this point on, the master request and slave response have an identical structure
            # (apart from error messages and such)
            if state == 1 and len(inbuff) > 0:
                if self.show_opto_rx:
                    logging.debug(f"VS2 received: {inbuff.hex()}")

                if inbuff[0] != 0x41:  # STX
                    logging.error(f"VS2 STX Error: {inbuff.hex()}")
                    # It might be necessary to wait for any remaining part of the telegram.
                    return OptolinkVS2RxData(
                        0x41, addr, alldata if not raw else bytearray(alldata)
                    )
                state = 2

            if state == 2 and len(inbuff) > 1:
                pllen = inbuff[1]
                if pllen < 5:  # protocol_Id + MsgId|FnctCode + AddrHi + AddrLo + BlkLen
                    logging.error(f"VS2 Len Error: {pllen}")
                    return OptolinkVS2RxData(
                        0xFD, addr, alldata if not raw else bytearray(alldata)
                    )
                if len(inbuff) >= pllen + 3:  # STX + Len + Payload + CRC

                    if self.show_opto_rx:
                        logging.debug(f"VS2 received: {inbuff.hex()}")

                    # receive complete
                    inbuff = inbuff[: pllen + 4]  # make sure no tailing trash
                    # msgid = inbuff[2]
                    # msqn = (inbuff[3] & 0xE0) >> 5
                    # fctcd = inbuff[3] & 0x1F
                    addr = (inbuff[4] << 8) + inbuff[5]
                    dlen = inbuff[6]
                    retdata = inbuff[7 : pllen + 2]

                    expected_crc = self.calc_crc(inbuff)
                    if inbuff[-1] != expected_crc:
                        logging.error(
                            f"VS2 CRC Error: expected=0x{expected_crc:02X} received=0x{inbuff[-1]:02X}"
                        )
                        return OptolinkVS2RxData(
                            0xFE, addr, retdata if not raw else bytearray(alldata)
                        )

                    if inbuff[2] & 0x0F == 0x03:
                        logging.error(
                            f"VS2 Error: dlen={dlen} content[hex]={retdata.hex()}"
                        )
                        return OptolinkVS2RxData(
                            0x03, addr, retdata if not raw else bytearray(alldata)
                        )

                    # successful receive!
                    logging.debug(
                        f"VS2 received successfully: address=0x{addr:02X} length={dlen} content[hex]={retdata.hex()}"
                    )
                    return OptolinkVS2RxData(
                        0x01, addr, retdata if not raw else bytearray(alldata)
                    )

        # timed-out if we get here

        return OptolinkVS2RxData(0xFF, addr, retdata if not raw else bytearray(retdata))

    # ------------------------------------------------------------------
    # Raw receive
    # ------------------------------------------------------------------

    def receive_fullraw(self, eot_time: float, timeout: float) -> tuple[int, bytearray]:
        inbuff = b""
        start = time.time()
        last_rx = start

        while True:
            inbytes = self.ser.read_all()
            if inbytes:
                # Add data to the data buffer
                inbuff += inbytes
                last_rx = time.time()
                if self.ser2:
                    self.ser2.write(inbytes)
            elif inbuff and (time.time() - last_rx) > eot_time:
                # if data received and no further receive since more than eot_time
                return 0x01, bytearray(inbuff)

            if (time.time() - start) > timeout:
                return 0xFF, bytearray(inbuff)

            time.sleep(0.005)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def calc_crc(telegram) -> int:
        firstbyte = 1
        lastbyte = telegram[1] + 1
        return sum(telegram[firstbyte : lastbyte + 1]) % 0x100

    @staticmethod
    def readable_hex(data: bytes) -> str:
        # try:
        #     return " ".join([format(byte, "02x") for byte in data])
        # except:
        #     return data
        return data.hex(sep=" ")
