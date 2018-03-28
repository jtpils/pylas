""" The definition of the VLR Header, VLR, and VRL List as well as all the KnownVLR
 are in this module.

 A KnownVLR is a VLR that we know how to parse its record_data
"""
import ctypes
from abc import abstractmethod

from .rawvlr import NULL_BYTE, VLR_HEADER_SIZE, UnknownVLR, BaseVLR, VLR
from ..extradims import get_type_for_extra_dim


class KnownVLR(UnknownVLR):
    @staticmethod
    @abstractmethod
    def official_user_id(): pass

    @staticmethod
    @abstractmethod
    def official_record_ids(): pass

    @abstractmethod
    def parse_record_data(self, record_data): pass

    @classmethod
    def from_raw(cls, raw):
        vlr = cls()
        vlr.parse_record_data(raw.record_data)
        return vlr


class ClassificationLookupStruct(ctypes.LittleEndianStructure):
    _fields_ = [
        ('class_number', ctypes.c_uint8),
        ('description', ctypes.c_char * 15)
    ]

    def __init__(self, class_number, description):
        if isinstance(description, str):
            super().__init__(class_number, description.encode())
        else:
            super().__init__(class_number, description)

    def __repr__(self):
        return 'ClassificationLookup({} : {})'.format(self.class_number, self.description)

    @staticmethod
    def size():
        return ctypes.sizeof(ClassificationLookupStruct)


class ClassificationLookupVlr(BaseVLR, KnownVLR):
    _lookup_size = ClassificationLookupStruct.size()

    def __init__(self):
        super().__init__(self.official_user_id(), self.official_record_ids()[0], description='')
        self.lookups = []

    def _is_max_num_lookups_reached(self):
        return len(self) >= 256

    def add_lookup(self, class_number, description):
        if not self._is_max_num_lookups_reached():
            self.lookups.append(ClassificationLookupStruct(class_number, description))
        else:
            raise ValueError('Cannot add more lookups')

    def into_raw(self):
        raw = super().into_raw()
        raw.record_data = b''.join(bytes(lookup) for lookup in self.lookups)
        return raw

    def __len__(self):
        return VLR_HEADER_SIZE + len(self.lookups) * ctypes.sizeof(ClassificationLookupStruct)

    def parse_record_data(self, record_data):
        if len(record_data) % self._lookup_size != 0:
            raise ValueError("Length of ClassificationLookup VLR's record_data must be a multiple of {}".format(
                self._lookup_size))
        for i in range(len(record_data) // ctypes.sizeof(ClassificationLookupStruct)):
            self.lookups.append(ClassificationLookupStruct.from_buffer(
                record_data[self._lookup_size * i: self._lookup_size * (i + 1)]))

    @staticmethod
    def official_user_id():
        return "LASF_Spec"

    @staticmethod
    def official_record_ids():
        return 0,


class LasZipVlr(VLR, KnownVLR):
    def __init__(self, data):
        super().__init__(
            LasZipVlr.official_user_id(),
            LasZipVlr.official_record_ids()[0],
            'http://laszip.org',
        )
        self.record_data = data

    def parse_record_data(self, record_data):
        # Only laz-perf/laszip knows how to parse this
        pass

    @staticmethod
    def official_user_id():
        return 'laszip encoded'

    @staticmethod
    def official_record_ids():
        return 22204,

    @classmethod
    def from_raw(cls, raw_vlr):
        return cls(raw_vlr.record_data)


class ExtraBytesStruct(ctypes.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ('reserved', ctypes.c_uint8 * 2),
        ('data_type', ctypes.c_uint8),
        ('options', ctypes.c_uint8),
        ('name', ctypes.c_char * 32),
        ('unused', ctypes.c_uint8 * 4),
        ('no_data', ctypes.c_double * 3),
        ('min', ctypes.c_double * 3),
        ('max', ctypes.c_double * 3),
        ('scale', ctypes.c_double * 3),
        ('offset', ctypes.c_double * 3),
        ('description', ctypes.c_char * 32),
    ]

    def format_name(self):
        return self.name.rstrip(NULL_BYTE).decode().replace(' ', "_").replace('-', '_')

    def type_tuple(self):
        if self.data_type == 0:
            return self.format_name(), '{}u1'.format(self.options)
        return self.format_name(), get_type_for_extra_dim(self.data_type)

    @staticmethod
    def size():
        return ctypes.sizeof(ExtraBytesStruct)


class ExtraBytesVlr(BaseVLR, KnownVLR):
    def __init__(self):
        super().__init__('LASF_Spec', self.official_record_ids()[0], 'extra_bytes')
        self.extra_bytes_structs = []

    def parse_record_data(self, data):
        if (len(data) % ExtraBytesStruct.size()) != 0:
            raise ValueError("Data length of ExtraBytes vlr must be a multiple of {}".format(
                ExtraBytesStruct.size()))
        num_extra_bytes_structs = len(data) // ExtraBytesStruct.size()
        self.extra_bytes_structs = [None] * num_extra_bytes_structs
        for i in range(num_extra_bytes_structs):
            self.extra_bytes_structs[i] = ExtraBytesStruct.from_buffer_copy(
                data[ExtraBytesStruct.size() * i: ExtraBytesStruct.size() * (i + 1)])

    def type_of_extra_dims(self):
        return [extra_dim.type_tuple() for extra_dim in self.extra_bytes_structs]

    def __repr__(self):
        return 'ExtraBytesVlr(extra bytes structs: {})'.format(len(self.extra_bytes_structs))

    def into_raw(self):
        raw = super().into_raw()
        raw.record_data = b''.join(bytes(extra_struct) for extra_struct in self.extra_bytes_structs)
        return raw

    def __len__(self):
        return VLR_HEADER_SIZE + len(self.extra_bytes_structs) * ExtraBytesStruct.size()

    @staticmethod
    def official_user_id():
        return 'LASF_Spec'

    @staticmethod
    def official_record_ids():
        return 4,


class WaveformPacketStruct(ctypes.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ('bits_per_sample', ctypes.c_ubyte),
        ('waveform_compression_type', ctypes.c_ubyte),
        ('number_of_samples', ctypes.c_uint32),
        ('temporal_sample_spacing', ctypes.c_uint32),
        ('digitizer_gain', ctypes.c_double),
        ('digitizer_offset', ctypes.c_double)
    ]

    @staticmethod
    def size():
        return ctypes.sizeof(WaveformPacketStruct)


class WaveformPacketVlr(BaseVLR, KnownVLR):
    def __init__(self, record_id, description=''):
        super().__init__(
            self.official_user_id(),
            record_id=record_id,
            description=description,
        )
        self.parsed_record = None

    def into_raw(self):
        raw = super().into_raw()
        raw.record_data = bytes(self.parsed_record)
        return raw

    def parse_record_data(self, record_data):
        self.parsed_record = WaveformPacketStruct.from_buffer_copy(record_data)

    def __len__(self):
        return super().__len__() + WaveformPacketStruct.size()

    @staticmethod
    def official_record_ids():
        return range(100, 356)

    @staticmethod
    def official_user_id():
        return 'LASF_Spec'

    @classmethod
    def from_raw(cls, raw_vlr):
        vlr = cls(raw_vlr.header.record_id, description=raw_vlr.header.description.decode())
        vlr.description = raw_vlr.header.description
        vlr.parse_record_data(raw_vlr.record_data)
        return vlr


class GeoKeyEntryStruct(ctypes.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ('id', ctypes.c_uint16),
        ('tiff_tag_location', ctypes.c_uint16),
        ('count', ctypes.c_uint16),
        ('value_offset', ctypes.c_uint16),
    ]

    @staticmethod
    def size():
        return ctypes.sizeof(GeoKeysHeaderStructs)

    def __repr__(self):
        return 'GeoKey(Id: {}, Location: {}, count: {}, offset: {})'.format(
            self.id, self.tiff_tag_location, self.count, self.value_offset
        )


class GeoKeysHeaderStructs(ctypes.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ('key_direction_version', ctypes.c_uint16),
        ('key_revision', ctypes.c_uint16),
        ('minor_revision', ctypes.c_uint16),
        ('number_of_keys', ctypes.c_uint16),
    ]

    def __init__(self):
        super().__init__(
            key_directory_version=1,
            key_revision=1,
            minor_revision=0,
            number_of_kets=0
        )

    @staticmethod
    def size():
        return ctypes.sizeof(GeoKeysHeaderStructs)

    def __repr__(self):
        return 'GeoKeysHeader(vers: {}, rev:{}, minor: {}, num_keys: {})'.format(
            self.key_direction_version, self.key_revision, self.minor_revision,
            self.number_of_keys
        )


class GeoKeyDirectoryVlr(BaseVLR, KnownVLR):
    def __init__(self):
        super().__init__(
            self.official_user_id(),
            self.official_record_ids()[0],
            description=''
        )
        self.geo_keys_header = GeoKeysHeaderStructs()
        self.geo_keys = [GeoKeyEntryStruct()]

    def parse_record_data(self, record_data):
        record_data = bytearray(record_data)
        header_data = record_data[:ctypes.sizeof(GeoKeysHeaderStructs)]
        self.geo_keys_header = GeoKeysHeaderStructs.from_buffer(header_data)
        self.geo_keys, keys_data = [], record_data[ctypes.sizeof(GeoKeysHeaderStructs):]

        for i in range(self.geo_keys_header.number_of_keys):
            data = keys_data[(i * GeoKeyEntryStruct.size()): (i + 1) * GeoKeyEntryStruct.size()]
            self.geo_keys.append(GeoKeyEntryStruct.from_buffer(data))

    def into_raw(self):
        raw = super().into_raw()
        raw.record_data = bytes(self.geo_keys_header)
        raw.record_data += b''.join(map(bytes, self.geo_keys))
        return raw

    def __len__(self):
        return VLR_HEADER_SIZE + GeoKeysHeaderStructs.size() + len(self.geo_keys) * GeoKeyEntryStruct.size()

    @staticmethod
    def official_user_id():
        return 'LASF_Projection'

    @staticmethod
    def official_record_ids():
        return 34735,


class GeoDoubleParamsVlr(BaseVLR, KnownVLR):
    def __init__(self):
        super().__init__(
            self.official_user_id(),
            self.official_record_ids()[0],
            description=''
        )
        self.doubles = []

    def parse_record_data(self, record_data):
        sizeof_double = ctypes.sizeof(ctypes.c_double)
        if len(record_data) % sizeof_double != 0:
            raise ValueError("GeoDoubleParams record data length () is not a multiple of sizeof(double) ()".format(
                len(record_data), sizeof_double
            ))
        record_data = bytearray(record_data)
        num_doubles = len(record_data) // sizeof_double
        for i in range(num_doubles):
            b = record_data[i * sizeof_double:(i + 1) * sizeof_double]
            self.doubles.append(ctypes.c_double.from_buffer(b))

    def __len__(self):
        return VLR_HEADER_SIZE + len(self.doubles) * ctypes.sizeof(ctypes.c_double)

    def into_raw(self):
        raw = super().into_raw()
        raw.record_data = b''.join(map(bytes, self.doubles))
        return raw

    @staticmethod
    def official_user_id():
        return 'LASF_Projection'

    @staticmethod
    def official_record_ids():
        return 34736,


class GeoAsciiParamsVlr(BaseVLR, KnownVLR):
    def __init__(self):
        super().__init__(
            self.official_user_id(),
            self.official_record_ids()[0],
            description=''
        )
        self.strings = []

    def parse_record_data(self, record_data):
        self.strings = [s.decode('ascii') for s in record_data.split(NULL_BYTE)]

    def into_raw(self):
        raw = super().into_raw()
        raw.record_data = NULL_BYTE.join(s.encode('ascii') for s in self.strings)
        return raw

    def __len__(self):
        return VLR_HEADER_SIZE + sum(map(len, self.strings)) + len(NULL_BYTE) * (len(self.strings) - 1)

    @staticmethod
    def official_user_id():
        return 'LASF_Projection'

    @staticmethod
    def official_record_ids():
        return 34737,


def vlr_factory(raw_vlr):
    user_id = raw_vlr.header.user_id.rstrip(NULL_BYTE).decode()
    for known_vlr in KnownVLR.__subclasses__():
        if known_vlr.official_user_id() == user_id and raw_vlr.header.record_id in known_vlr.official_record_ids():
            return known_vlr.from_raw(raw_vlr)
    else:
        return VLR.from_raw(raw_vlr)