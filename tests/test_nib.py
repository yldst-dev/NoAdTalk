import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Scripts'))
from nib import Archive, patch_file


def varint(value):
    result = bytearray()
    while value >= 128:
        result.append(value & 127)
        value >>= 7
    result.append(value | 128)
    return bytes(result)


def relocate(data):
    archive = Archive(data)
    header = list(struct.unpack_from('<10I', data, 10))
    order = [0] + list(reversed(range(1, len(archive.objects))))
    references = {old: new for new, old in enumerate(order)}
    objects = b''.join(varint(value) for index in order for value in archive.objects[index])
    keys = ['unrelatedFutureLayoutProperty'] + list(reversed(archive.keys))
    key_ids = {key: index for index, key in enumerate(keys)}
    key_data = b''.join(varint(len(key.encode())) + key.encode() for key in keys)
    values = []
    for index, (key, kind, value) in enumerate(archive.values):
        start, end = archive.spans[index]
        payload = data[start + len(archive.prefixes[index]):end]
        if kind == 10:
            payload = b'\x0a' + struct.pack('<I', references[value])
        values.append(varint(key_ids[key]) + payload)
    value_data = b''.join(values)
    classes = data[header[9]:]
    header[3] = 50
    header[4] = len(keys)
    header[5] = header[3] + len(objects)
    header[7] = header[5] + len(key_data)
    header[9] = header[7] + len(value_data)
    return b'NIBArchive' + struct.pack('<10I', *header) + objects + key_data + value_data + classes


def find_outlet(archive, name):
    return next(index for index in range(len(archive.objects)) if archive.class_name(index) == 'NSNibOutletConnector' and archive.string(archive.value(index, 'NSLabel', 10)) == name)


class NibTests(unittest.TestCase):
    def test_current_golden(self):
        if hashlib.sha256(original).hexdigest() == '21842c678fde4ce88583ad7c3b42863e7ac91daba7b5f6d106b06714020257be':
            self.assertEqual(hashlib.sha256(Archive(original).patch()).hexdigest(), 'd71a99a9b6ea0a825c6b01a3e12557d9386c3c6b7cba71e5bea92f2d3a4a5651')

    def test_relocated_objects_and_keys(self):
        shifted = relocate(original)
        self.assertNotEqual(shifted, original)
        archive = Archive(Archive(shifted).patch())
        outlet = find_outlet(archive, 'advertiseContainerView')
        self.assertIsNone(archive.value(outlet, 'NSDestination', 9))
        height = archive.value(find_outlet(archive, 'advertiseContainerHeightConstraint'), 'NSDestination', 10)
        view = archive.value(height, 'NSFirstItem', 10)
        self.assertEqual(archive.value(height, 'NSConstant', 7), 0)
        self.assertTrue(archive.value(view, 'NSvFlags', 2) & 0x80000000)
        Path(output).write_bytes(Archive(shifted).patch())

    def test_missing_outlet(self):
        with self.assertRaises(ValueError):
            Archive(original.replace(b'advertiseContainerView', b'advertiseContainerGone')).patch()

    def test_wrong_constraint(self):
        archive = Archive(original)
        constraint = archive.value(find_outlet(archive, 'advertiseContainerHeightConstraint'), 'NSDestination', 10)
        index = archive.field(constraint, 'NSFirstAttributeV2')
        data = bytearray(original)
        data[archive.spans[index][1] - 1] = 7
        with self.assertRaises(ValueError):
            Archive(bytes(data)).patch()

    def test_truncated_and_unsupported(self):
        for length in (0, 10, 49, 50, len(original) // 2, len(original) - 1):
            with self.subTest(length=length), self.assertRaises(ValueError):
                Archive(original[:length]).patch()
        data = bytearray(original)
        struct.pack_into('<I', data, 10, 2)
        with self.assertRaises(ValueError):
            Archive(bytes(data))

    def test_relative_constraint_to_object_zero(self):
        archive = Archive(original)
        constraint = archive.value(find_outlet(archive, 'advertiseContainerHeightConstraint'), 'NSDestination', 10)
        index = archive.field(constraint, 'NSShouldBeArchived')
        start, end = archive.spans[index]
        payload = varint(archive.keys.index('NSSecondItem')) + b'\x0a\0\0\0\0'
        data = bytearray(original)
        data[start:end] = payload
        struct.pack_into('<I', data, 46, struct.unpack_from('<I', original, 46)[0] + len(payload) - (end - start))
        with self.assertRaises(ValueError):
            Archive(bytes(data)).patch()

    def test_invalid_input_preserves_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source, destination = Path(directory) / 'input.nib', Path(directory) / 'output.nib'
            source.write_bytes(b'invalid')
            destination.write_bytes(b'keep')
            with self.assertRaises(ValueError):
                patch_file(source, destination)
            self.assertEqual(destination.read_bytes(), b'keep')
            source.unlink()
            source.symlink_to(destination)
            with self.assertRaises(ValueError):
                patch_file(source, destination)

    def test_already_disconnected_is_not_an_original(self):
        with self.assertRaises(ValueError):
            Archive(Archive(original).patch()).patch()


if __name__ == '__main__':
    original = Path(sys.argv[1]).read_bytes()
    output = sys.argv[2]
    unittest.main(argv=[sys.argv[0]])
