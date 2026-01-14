"""
optolinkvs2.py
----------------
Optolink VS2 / 300 Protocol handler
Reworked by Francesco Montorsi based on the original code by philippoo66

TODO: remove all print() operations and replace with proper logging
TODO: remove mqtt_publ_callback to move MQTT logic out of this class

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


class OptolinkVS2Protocol:
    """
    Optolink VS2 / 300 Protocol handler
    """

    def __init__(
        self,
        ser: serial.Serial,
        ser2: serial.Serial = None,
        mqtt_publ_callback=None,
        show_opto_rx: bool = False,
    ):
        """
        Parameters
        ----------
        ser : serial.Serial
            Primary serial interface
        ser2 : serial.Serial, optional
            Secondary serial interface (forwarding / duplex)
        mqtt_publ_callback : callable, optional
            Callback for MQTT publishing
        """
        self.ser = ser
        self.ser2 = ser2
        self.mqtt_publ_callback = mqtt_publ_callback
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
                print(buff)
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
                print(buff)
            if buff and buff[0] == 0x06:  # ACK
                return True

        logging.error("VS2: Timeout waiting for 0x06")
        return False

    # ------------------------------------------------------------------
    # Datapoint read/write
    # ------------------------------------------------------------------

    def read_datapoint(self, addr: int, rdlen: int) -> bytes:
        _, _, data = self.read_datapoint_ext(addr, rdlen)
        return data

    def read_datapoint_ext(self, addr: int, rdlen: int) -> tuple[int, int, bytearray]:
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

        return self.receive_telegr(resptelegr=True, raw=False)

    def write_datapoint(self, addr: int, data: bytes) -> bool:
        retcode, _, _ = self.write_datapoint_ext(addr, data)
        return retcode == 0x01

    def write_datapoint_ext(self, addr: int, data: bytes) -> tuple[int, int, bytearray]:
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

        return self.receive_telegr(resptelegr=True, raw=False)

    # ------------------------------------------------------------------
    # Generic request
    # ------------------------------------------------------------------

    def do_request(
        self, fctcode: int, addr: int, rlen: int, data: bytes = b"", protid: int = 0x00
    ) -> tuple[int, int, bytearray]:
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

        print(OptolinkVS2Protocol.bbbstr(outbuff))

        self.ser.reset_input_buffer()
        self.ser.write(outbuff)

        return self.receive_telegr(resptelegr=True, raw=False)

    # ------------------------------------------------------------------
    # Telegram receive
    # ------------------------------------------------------------------

    def receive_telegr(self, resptelegr: bool, raw: bool) -> tuple[int, int, bytearray]:
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

        A tuple[int, int, bytearray], containing the following elements:

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

        Notes:
        ---------
        This function will block until the message has been fully received or a timeout has occurred.
        """
        state = 0
        inbuff = bytearray()
        alldata = bytearray()
        retdata = bytearray()
        addr = 0
        msgid = 0x100  # message type identifier, byte 2 (3. byte; 0 = Request Message, 1 = Response Message, 2 = UNACKD Message, 3 = Error Message)
        msqn = 0x100  # message sequence number, top 3 bits of byte 3
        fctcd = 0x100  # function code, low 5 bis of byte 3 (https://github.com/sarnau/InsideViessmannVitosoft/blob/main/VitosoftCommunication.md#defined-commandsfunction-codes)
        dlen = -1

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
                return 0xAA, 0, retdata

            if state == 0:
                if resptelegr and inbuff:
                    if self.show_opto_rx:
                        print(f"rx: {inbuff[0]:02x}")
                    if inbuff[0] == 0x06:
                        state = 1
                    elif inbuff[0] == 0x15:  # VS2_NACK
                        logging.error("VS2 NACK Error")
                        return self._return(
                            0x15, addr, alldata, msgid, msqn, fctcd, dlen, raw
                        )
                    else:
                        logging.error("VS2 unknown first byte error")
                        return self._return(
                            0x20, addr, alldata, msgid, msqn, fctcd, dlen, raw
                        )
                    # Separate the first byte
                    inbuff = inbuff[1:]
                else:
                    state = 1

            # From this point on, the master request and slave response have an identical structure (apart from error messages and such).
            if state == 1 and inbuff:
                if inbuff[0] != 0x41:  # STX
                    logging.error(f"VS2 STX Error: {inbuff[0]:02x}")
                    # It might be necessary to wait for any remaining part of the telegram.
                    return self._return(
                        0x41, addr, alldata, msgid, msqn, fctcd, dlen, raw
                    )
                state = 2

            if state == 2 and len(inbuff) > 1:
                pllen = inbuff[1]
                if pllen < 5:  # protocol_Id + MsgId|FnctCode + AddrHi + AddrLo + BlkLen
                    logging.error(f"VS2 Len Error: {pllen}")
                    return self._return(
                        0xFD, addr, alldata, msgid, msqn, fctcd, dlen, raw
                    )
                if len(inbuff) >= pllen + 3:  # STX + Len + Payload + CRC
                    # receive complete
                    inbuff = inbuff[: pllen + 4]  # make sure no tailing trash
                    msgid = inbuff[2]
                    msqn = (inbuff[3] & 0xE0) >> 5
                    fctcd = inbuff[3] & 0x1F
                    addr = (inbuff[4] << 8) + inbuff[5]
                    dlen = inbuff[6]
                    retdata = inbuff[7 : pllen + 2]

                    if inbuff[-1] != self.calc_crc(inbuff):
                        logging.error("VS2 CRC Error")
                        return self._return(
                            0xFE, addr, retdata, msgid, msqn, fctcd, dlen, raw
                        )

                    if inbuff[2] & 0x0F == 0x03:
                        return self._return(
                            0x03, addr, retdata, msgid, msqn, fctcd, dlen, raw
                        )

                    return self._return(
                        0x01, addr, retdata, msgid, msqn, fctcd, dlen, raw
                    )

        # timed-out if we get here

        return self._return(0xFF, addr, retdata, msgid, msqn, fctcd, dlen, raw)

    # ------------------------------------------------------------------
    # Raw receive
    # ------------------------------------------------------------------

    def receive_fullraw(self, eot_time: float, timeout: float):
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

    def _return(self, code, addr, data, msgid, msqn, fctcd, dlen, raw):
        if self.mqtt_publ_callback:
            self.mqtt_publ_callback(code, addr, data, msgid, msqn, fctcd, dlen)
        return code, addr, data if not raw else bytearray(data)

    @staticmethod
    def bbbstr(data):
        try:
            return " ".join([format(byte, "02x") for byte in data])
        except:
            return data
