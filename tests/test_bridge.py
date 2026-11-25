"""Cloud bridge helpers that do not need NetSdk.dll."""
import struct

from xmcloud_bridge import clean_nals, sniff_codec

SC = b"\x00\x00\x00\x01"


def test_annex_b_without_pseudo_nals_is_unchanged():
    buf = SC + b"\x67abc" + SC + b"\x68def"
    assert clean_nals(buf) == buf


def test_pseudo_nal_with_forbidden_bit_is_removed():
    buf = SC + b"\x67sps" + SC + b"\xe0junk" + SC + b"\x65idr"
    assert clean_nals(buf) == SC + b"\x67sps" + SC + b"\x65idr"


def test_length_prefixed_is_converted_to_annex_b():
    buf = struct.pack(">I", 4) + b"\x67abc" + struct.pack(">I", 3) + b"\x68de"
    assert clean_nals(buf) == SC + b"\x67abc" + SC + b"\x68de"


def test_sniff_codec():
    assert sniff_codec(b"", 5) is True
    assert sniff_codec(b"\x00\x00\x01\x40\x01", 2) is False      # the encode type wins
    assert sniff_codec(b"xx\x00\x00\x01\x40\x01", 0) is True      # H.265 VPS
    assert sniff_codec(SC + b"\x67", 0) is False
