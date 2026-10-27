import math
import struct
import sys
from pathlib import Path


class Archive:
    def __init__(self, data):
        if len(data) < 50 or len(data) > 16 * 1024 * 1024 or data[:10] != b'NIBArchive':
            raise ValueError('지원하는 nib 파일이 아닙니다.')
        self.data = data
        header = struct.unpack_from('<10I', data, 10)
        if header[0] != 1:
            raise ValueError('지원하지 않는 nib 형식입니다.')
        _, _, object_count, objects_offset, key_count, keys_offset, value_count, values_offset, class_count, classes_offset = header
        offsets = [50, objects_offset, keys_offset, values_offset, classes_offset, len(data)]
        if offsets != sorted(offsets) or max(object_count, key_count, value_count, class_count) > 500000:
            raise ValueError('nib 테이블 범위가 잘못되었습니다.')
        self.position = objects_offset
        self.end = keys_offset
        self.objects = [tuple(self.varint() for _ in range(3)) for _ in range(object_count)]
        self.position = keys_offset
        self.end = values_offset
        self.keys = [self.take(self.varint()).decode('utf-8') for _ in range(key_count)]
        self.position = classes_offset
        self.end = len(data)
        self.classes = []
        for _ in range(class_count):
            length, extra = self.varint(), self.varint()
            if extra > 16:
                raise ValueError('지원하지 않는 nib 클래스 확장입니다.')
            self.take(extra * 4)
            self.classes.append(self.take(length).rstrip(b'\0').decode('utf-8'))
        self.position = values_offset
        self.end = classes_offset
        self.values = []
        self.spans = []
        self.prefixes = []
        for _ in range(value_count):
            start = self.position
            key = self.varint()
            prefix = data[start:self.position]
            kind = self.take(1)[0]
            if key >= key_count:
                raise ValueError('잘못된 nib 속성 번호입니다.')
            if kind in (0, 1, 2, 3, 6, 7, 10):
                format = {0: 'B', 1: 'H', 2: 'I', 3: 'Q', 6: 'f', 7: 'd', 10: 'I'}[kind]
                value = struct.unpack('<' + format, self.take(struct.calcsize(format)))[0]
                if kind == 10 and value >= object_count:
                    raise ValueError('잘못된 nib 객체 참조입니다.')
                if kind in (6, 7) and not math.isfinite(value):
                    raise ValueError('유효하지 않은 nib 숫자입니다.')
            elif kind == 8:
                value = self.take(self.varint())
            elif kind in (4, 5, 9):
                value = {4: True, 5: False, 9: None}[kind]
            else:
                raise ValueError('지원하지 않는 nib 값 형식입니다.')
            self.values.append((self.keys[key], kind, value))
            self.spans.append((start, self.position))
            self.prefixes.append(prefix)
        if self.position != classes_offset:
            raise ValueError('nib 값 테이블의 길이가 맞지 않습니다.')
        self.owners = [0] * value_count
        if sum(count for _, _, count in self.objects) > 500000:
            raise ValueError('nib 객체가 너무 복잡합니다.')
        for class_index, start, count in self.objects:
            if class_index >= class_count or start + count > value_count:
                raise ValueError('잘못된 nib 객체 범위입니다.')
            for index in range(start, start + count):
                self.owners[index] += 1
        self.changes = {}

    def take(self, count):
        end = self.position + count
        if count < 0 or end > self.end:
            raise ValueError('nib 파일이 잘렸거나 범위가 잘못되었습니다.')
        result = self.data[self.position:end]
        self.position = end
        return result

    def varint(self):
        value = 0
        for shift in range(0, 35, 7):
            byte = self.take(1)[0]
            value |= (byte & 127) << shift
            if byte & 128:
                if value > 0x7fffffff:
                    break
                return value
        raise ValueError('잘못된 nib 길이 값입니다.')

    def field(self, object_id, name, optional=False):
        _, start, count = self.objects[object_id]
        found = [i for i in range(start, start + count) if self.values[i][0] == name]
        if optional and not found:
            return None
        if len(found) != 1:
            raise ValueError('필수 nib 속성이 없거나 중복됩니다: ' + name)
        return found[0]

    def value(self, object_id, name, kind):
        index = self.field(object_id, name)
        _, actual, value = self.values[index]
        if actual != kind:
            raise ValueError('예상하지 못한 nib 속성 형식입니다: ' + name)
        return value

    def class_name(self, object_id):
        return self.classes[self.objects[object_id][0]]

    def string(self, object_id):
        if self.class_name(object_id) != 'NSString':
            raise ValueError('연결 이름이 문자열이 아닙니다.')
        return self.value(object_id, 'NS.bytes', 8).decode('utf-8')

    def replace(self, index, payload):
        if self.owners[index] != 1:
            raise ValueError('여러 객체가 공유하는 속성은 변경하지 않습니다.')
        self.changes[index] = self.prefixes[index] + payload

    def patch(self):
        names = ('advertiseContainerView', 'advertiseContainerHeightConstraint', 'adSeparatorHeightConstraint')
        outlets = {name: [] for name in names}
        for object_id in range(len(self.objects)):
            if self.class_name(object_id) == 'NSNibOutletConnector':
                label = self.string(self.value(object_id, 'NSLabel', 10))
                if label in outlets:
                    outlets[label].append(object_id)
        if any(len(found) != 1 for found in outlets.values()):
            raise ValueError('광고 연결 구조가 바뀌어 패치를 중단했습니다.')
        view_outlet, height_outlet, separator_outlet = [outlets[name][0] for name in names]
        sources = {self.value(i, 'NSSource', 10) for i in (view_outlet, height_outlet, separator_outlet)}
        if len(sources) != 1:
            raise ValueError('광고 연결의 컨트롤러가 서로 다릅니다.')
        owner = sources.pop()
        owner_name = self.string(self.value(owner, 'NSClassName', 10))
        if owner_name not in ('FSMainViewController', 'KakaoTalk.FSMainViewController'):
            raise ValueError('예상한 기본 창 컨트롤러가 아닙니다.')
        view = self.value(view_outlet, 'NSDestination', 10)
        height = self.value(height_outlet, 'NSDestination', 10)
        separator = self.value(separator_outlet, 'NSDestination', 10)
        if height == separator or self.value(height, 'NSFirstItem', 10) != view:
            raise ValueError('광고 높이 제약과 뷰의 연결이 맞지 않습니다.')
        if self.class_name(view) not in ('NSCustomView', 'NSView', 'BDView'):
            raise ValueError('예상한 광고 뷰가 아닙니다.')
        for constraint in (height, separator):
            if self.class_name(constraint) != 'NSLayoutConstraint':
                raise ValueError('광고 높이 제약의 클래스가 바뀌었습니다.')
            attributes = [self.field(constraint, key, True) for key in ('NSFirstAttribute', 'NSFirstAttributeV2')]
            attributes = [i for i in attributes if i is not None]
            if not attributes or any(self.values[i][1] not in (0, 1, 2, 3) or self.values[i][2] != 8 for i in attributes):
                raise ValueError('광고 제약이 높이 제약이 아닙니다.')
            for key in ('NSSecondItem', 'NSSecondAttribute', 'NSSecondAttributeV2'):
                index = self.field(constraint, key, True)
                if index is not None and (self.values[index][1] == 10 or self.values[index][2] not in (None, 0)):
                    raise ValueError('상대 높이 제약은 지원하지 않습니다.')
            constants = [self.field(constraint, key, True) for key in ('NSConstant', 'NSConstantV2')]
            constants = [i for i in constants if i is not None]
            if not constants or any(self.values[i][1] not in (6, 7) for i in constants):
                raise ValueError('광고 높이 상수 형식이 바뀌었습니다.')
            for index in constants:
                kind = self.values[index][1]
                self.replace(index, bytes([kind]) + bytes(4 if kind == 6 else 8))
        flags_index = self.field(view, 'NSvFlags')
        _, kind, flags = self.values[flags_index]
        if kind not in (0, 1, 2) or flags > 0xffffffff:
            raise ValueError('광고 뷰의 표시 속성 형식이 바뀌었습니다.')
        self.replace(flags_index, b'\x02' + struct.pack('<I', flags | 0x80000000))
        self.replace(self.field(view_outlet, 'NSDestination'), b'\x09')
        result = bytearray(self.data)
        delta = 0
        for index in sorted(self.changes, reverse=True):
            start, end = self.spans[index]
            payload = self.changes[index]
            result[start:end] = payload
            delta += len(payload) - (end - start)
        struct.pack_into('<I', result, 46, struct.unpack_from('<I', self.data, 46)[0] + delta)
        Archive(bytes(result))
        return bytes(result)


def patch_file(source, destination):
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or destination.is_symlink() or not source.is_file():
        raise ValueError('일반 파일만 처리할 수 있습니다.')
    if source.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('nib 파일이 너무 큽니다.')
    result = Archive(source.read_bytes()).patch()
    destination.write_bytes(result)


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('입력 nib와 출력 경로가 필요합니다.')
        patch_file(sys.argv[1], sys.argv[2])
    except (ValueError, OSError, struct.error) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
