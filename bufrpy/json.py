from bufrpy.descriptors import ElementDescriptor, ReplicationDescriptor, OperatorDescriptor, SequenceDescriptor, LazySequenceDescriptor, StrongSequenceDescriptor
from bufrpy.value import _decode_raw_value
from bufrpy.bufrdec import Message, Section3, Section4
from bufrpy.util import int2fxy


def flatten_descriptors(descriptors):
    def _flatten_descriptors(descriptors):
        result = set()
        for d in descriptors:
            if isinstance(d, SequenceDescriptor):
                result |= _flatten_descriptors(d.descriptors)
            else:
                result.add(d)
        return result
    return list(sorted(_flatten_descriptors(descriptors), key=lambda x: x.code))

def to_json(msg):
    """Convert a BUFR message into JSON-encodable form.

    The conversion preserves descriptors in Sections 3 and data in
    Section 4 but not the other metadata.

    The resulting JSON is considerably larger than BUFR messages
    themselves, but compresses to smaller size with e.g. gzip. The
    JSON is also faster to read and self-descriptive, i.e. a separate
    descriptor table is no longer necessary.

    :param Message msg: Message to convert
    :returns: Dict that can be converted to JSON using the standard json module
    :rtype: dict

    """

    # Strongify the descriptors, lazy sequence descriptors would be difficult to handle otherwise
    # TODO Move strongifying to section 3 decoding
    strong_descriptors = [descriptor.strong() for descriptor in msg.section3.descriptors]

    flat_descriptors = flatten_descriptors(strong_descriptors)

    descriptor_index = {} # code -> index
    for i,descriptor in enumerate(flat_descriptors):
        descriptor_index[descriptor.code] = i

    def to_json_data(data):
        result = []
        for el in data:
            if isinstance(el, list):
                result.append(to_json_data(el))
            else:
                result.append({"desc":descriptor_index[el.descriptor.code], "val":el.raw_value})
        return result

    result = {"descriptors":strong_descriptors, "data":to_json_data(msg.section4.data)}
    return result

def from_json(json_obj):
    """Convert an object decoded from JSON into a BUFR message

    The conversion reads partial contents of BUFR sections 3 and 4 from a dict
    generated by :py:func:`to_json`.

    The resulting :class:`bufrpy.Message` contains only section 3 and 4, and the
    sections only contain descriptors and data, respectively.

    :param dict json_obj: JSON object to decode
    :returns: BUFR message with original descriptors and data
    :rtype: Message

    """

    def sequence_decoder(code, length, codes, significance, sub_descriptors):
        sub_descriptors = [decode_descriptor(s) for s in sub_descriptors]
        return StrongSequenceDescriptor(code, length, codes, significance, sub_descriptors)

    descriptor_types = {0:ElementDescriptor, 1:ReplicationDescriptor, 2:OperatorDescriptor, 3:sequence_decoder}
    def decode_descriptor(descriptor_def):
        descriptors = []
        dtype = descriptor_def[0] >> 14 & 0x3
        klass = descriptor_types[dtype]
        return descriptor_types[dtype](*descriptor_def)

        
    descriptors = []
    for descriptor_def in json_obj["descriptors"]:
        descriptors.append(decode_descriptor(descriptor_def))

    flat_descriptors = flatten_descriptors(descriptors)

    def decode_data(json_data):
        result = []
        for el in json_data:
            if isinstance(el, dict):
                descriptor = flat_descriptors[el["desc"]]
                result.append(_decode_raw_value(el["val"], descriptor))
            else:
                result.append(decode_data(el))
        return result

    data = decode_data(json_obj["data"])
            
    return Message(None, None, None, Section3(None, None, None, descriptors), Section4(None, data), None)
