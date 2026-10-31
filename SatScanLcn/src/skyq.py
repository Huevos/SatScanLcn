# Sky Deutschland (19.2E). The logical channel numbers are not in a BAT or NIT. They are in a carousel (PID 0x08AE, table 0x9E) that holds an
# NDS-ARCHIVE of per bouquet text files, each line: "<lcn>=<channel id>=dvb://<onid hex>.<tsid hex>.<sid hex>;...". Takes the place of "read BAT".
from . import dvbreader
import datetime
import re
import struct
from time import sleep, time
from . import _

LINE = re.compile(rb"^\s*(\d+)=(\d+)=dvb://([0-9A-Fa-f]+)\.([0-9A-Fa-f]+)\.([0-9A-Fa-f]+)")
MAGIC = b"NDS-ARCHIVE\x00"
TIMEOUT = 60  # seconds


def archive(data, magic, base):
	"""The (name, bytes) of every file in the NDS-ARCHIVE whose magic is at offset magic. base is the origin of the file offsets in its entries."""
	if data[magic:magic + 12] != MAGIC:
		raise ValueError("NDS-ARCHIVE magic not found at 0x%x" % magic)
	offset = magic + 12
	count = struct.unpack(">I", data[offset + 8:offset + 12])[0]  # 18 byte header after the magic
	offset += 18
	files = []
	for _unused in range(count):
		if offset + 23 > len(data):
			break
		size, position, length = data[offset], struct.unpack(">I", data[offset + 5:offset + 9])[0], struct.unpack(">I", data[offset + 9:offset + 13])[0]
		name = data[offset + 23:offset + 23 + data[offset + 22]].rstrip(b"\x00").decode("latin-1", "replace")
		files.append((name, data[base + position:base + position + length]))
		offset += size
	return files


def extract(blob, filename):
	"""The bouquet text file inside the carousel archive. Raises KeyError, listing what is there, if it is not found."""
	magics = [m.start() for m in re.finditer(MAGIC, blob)]
	if len(magics) < 2:
		raise RuntimeError("Malformed NDS-ARCHIVE: expected at least 2 magics, got %d" % len(magics))
	nested = next((body for name, body in archive(blob, magics[0], 0) if name.endswith("sky_de_configuration.nsa")), None)
	if nested is None:
		raise RuntimeError("sky_de_configuration.nsa not found in NDS-ARCHIVE")
	magic = nested.find(MAGIC)
	if magic < 0:
		raise RuntimeError("Nested NDS-ARCHIVE magic not found")
	files = archive(nested, magic, magic - 6)  # the nested archive has 6 bytes in front of the magic that are not decoded
	for name, body in files:
		if name == filename:
			return body
	raise KeyError("%r not in the archive, available: %s" % (filename, sorted(n for n, _unused in files if "channels-" in n and not n.endswith(".headers"))))


def channels(body):
	"""{(onid, tsid, sid): lcn} from a bouquet text file. LCN 0 (data and interactive) is skipped."""
	found = {}
	for line in body.split(b"\r\n"):
		m = LINE.match(line)
		if m and int(m.group(1)):
			found.setdefault((int(m.group(3), 16), int(m.group(4), 16), int(m.group(5), 16)), int(m.group(1)))
	return found


def carousel(screen, settings):
	"""The reassembled archive, or None if it did not arrive complete in time."""
	fd = dvbreader.open(screen.demuxer_device, settings["pid"], settings["table_id"], 0xff, screen.selectedNIM)
	if fd < 0:
		print("[%s] Cannot open the demuxer" % screen.debugName)
		return None
	version = count = None
	received = {}
	timeout = datetime.datetime.now() + datetime.timedelta(0, TIMEOUT)
	while datetime.datetime.now() < timeout and (count is None or len(received) < count):
		section = dvbreader.read_skyq(fd, settings["table_id"])
		if section is None:
			sleep(0.1)
			continue
		header = section["header"]
		if header["variable_id"] != settings["variable_id"]:
			continue
		if header["version_number"] != version:  # the first section, or the carousel changed while we were reading
			version, count, received = header["version_number"], header["last_section_number"] + 1, {}
		received.setdefault(header["section_number"], section["content"])
	dvbreader.close(fd)
	if not count or len(received) != count:
		print("[%s] Incomplete Sky channel list carousel (%d/%s sections)" % (screen.debugName, len(received), count))
		return None
	return b"".join(received[n] for n in range(count))


def read(screen):
	"""Reads the channel list into the BAT structures, as read BAT would, then goes on to the next step."""
	print("[%s] Reading the Sky channel list..." % screen.debugName)
	screen.setDemuxer()
	start = time()
	settings = screen.skyq
	blob = carousel(screen, settings)
	screen.BATreadTime += time() - start
	lcns = {}
	if blob:
		try:
			lcns = channels(extract(blob, settings["bouquet_file"]))
		except (KeyError, RuntimeError, ValueError) as e:
			print("[%s] Sky channel list: %s" % (screen.debugName, e))
	if not lcns:
		return screen.showError(_("Could not read the Sky channel list"))
	for key, lcn in settings.get("overrides", {}).items():  # services that are broadcast but missing from the carousel, only used if the carousel has no entry for them
		lcns.setdefault(key, lcn)
	screen.TSID_ONID_list, screen.tmp_bat_content = [], []
	for (onid, tsid, sid), lcn in lcns.items():
		if "%x:%x" % (tsid, onid) not in screen.TSID_ONID_list:
			screen.TSID_ONID_list.append("%x:%x" % (tsid, onid))
		screen.tmp_bat_content.append({"transport_stream_id": tsid, "original_network_id": onid, "service_id": sid, "logical_channel_number": lcn})
	print("[%s] Sky channel list: %d services on %d transponders" % (screen.debugName, len(lcns), len(screen.TSID_ONID_list)))
	screen.manager()
