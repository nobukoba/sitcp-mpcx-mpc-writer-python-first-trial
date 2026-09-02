import unittest

from sitcp_mpc_writer.eeprom import (
    EEPROM_BASE,
    EEPROM_WRITE_ENABLE,
    build_program_image,
    program_mpc_payload,
)


class FakeClient:
    def __init__(self, memory):
        self.memory = bytearray(memory)
        self.writes = []

    def _offset(self, address):
        return address - EEPROM_BASE

    def read(self, address, length):
        start = self._offset(address)
        return bytes(self.memory[start:start + length])

    def write(self, address, data):
        self.writes.append((address, bytes(data)))
        if address == EEPROM_WRITE_ENABLE:
            return bytes(data)
        start = self._offset(address)
        self.memory[start:start + len(data)] = data
        return bytes(data)


class EepromProgrammingTests(unittest.TestCase):
    def test_xg_preserves_fc10_fc11(self):
        memory = bytearray(range(0x80))
        payload = bytes(range(22))
        client = FakeClient(memory)
        address, image = build_program_image(client, payload, 1)
        self.assertEqual(address, EEPROM_BASE)
        self.assertEqual(image[0:16], payload[0:16])
        self.assertEqual(image[16:18], memory[16:18])
        self.assertEqual(image[18:24], payload[16:22])

    def test_normal_preserves_unmapped_bytes(self):
        memory = bytearray((i * 3) & 0xFF for i in range(0x80))
        original = bytes(memory)
        payload = bytes(range(22))
        client = FakeClient(memory)
        _, image = build_program_image(client, payload, 2)
        self.assertEqual(image[0x12:0x18], payload[0:6])
        self.assertEqual(image[0x40:0x50], payload[6:22])
        self.assertEqual(image[0:0x12], original[0:0x12])
        self.assertEqual(image[0x18:0x40], original[0x18:0x40])

    def test_program_disables_write_and_verifies(self):
        memory = bytearray(range(0x80))
        payload = bytes(range(22))
        client = FakeClient(memory)
        actual = program_mpc_payload(client, payload, 1)
        self.assertEqual(actual[0:16], payload[0:16])
        self.assertEqual(actual[18:24], payload[16:22])
        self.assertEqual(client.writes[0], (EEPROM_WRITE_ENABLE, b"\x00"))
        self.assertEqual(client.writes[-1], (EEPROM_WRITE_ENABLE, b"\xff"))


if __name__ == "__main__":
    unittest.main()
