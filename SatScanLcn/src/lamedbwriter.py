# -*- coding: utf-8 -*-
from __future__ import print_function
import six

import codecs
import re

from enigma import eDVBFrontendParametersSatellite


class LamedbWriter():

	def writeLamedb(self, path, transponders, filename="lamedb"):
		print("[SatScanLcn-LamedbWriter] Writing lamedb...")

		transponders_count = 0
		services_count = 0

		lamedblist = []
		lamedblist.append("eDVB services /4/\n")
		lamedblist.append("transponders\n")

		for key in list(transponders.keys()):
			transponder = transponders[key]
			if "services" not in list(transponder.keys()) or len(transponder["services"]) < 1:
				continue
			lamedblist.append("%08x:%04x:%04x\n" %
				(transponder["namespace"],
				transponder["transport_stream_id"],
				transponder["original_network_id"]))

			if transponder["dvb_type"] == "dvbs":
				if transponder["orbital_position"] > 1800:
					orbital_position = transponder["orbital_position"] - 3600
				else:
					orbital_position = transponder["orbital_position"]

				if transponder["system"] == 0:  # DVB-S
					lamedblist.append("\ts %d:%d:%d:%d:%d:%d:%d\n" %
						(transponder["frequency"],
						transponder["symbol_rate"],
						transponder["polarization"],
						transponder["fec_inner"],
						orbital_position,
						transponder["inversion"],
						transponder["flags"]))
				else:  # DVB-S2
					multistream = ''
					t2mi = ''
					if "t2mi_plp_id" in transponder and "t2mi_pid" in transponder:
						t2mi = ':%d:%d' % (
							transponder["t2mi_plp_id"],
							transponder["t2mi_pid"])
					if "is_id" in transponder and "pls_code" in transponder and "pls_mode" in transponder:
						multistream = ':%d:%d:%d' % (
							transponder["is_id"],
							transponder["pls_code"],
							transponder["pls_mode"])
					if t2mi and not multistream:  # this is to pad t2mi values if necessary.
						try:  # some images are still not multistream aware after all this time
							multistream = ':%d:%d:%d' % (
								eDVBFrontendParametersSatellite.No_Stream_Id_Filter,
								eDVBFrontendParametersSatellite.PLS_Gold,
								eDVBFrontendParametersSatellite.PLS_Default_Gold_Code)
						except AttributeError as err:
							print("[ABM-BouquetsWriter] some images are still not multistream aware after all this time", err)
					lamedblist.append("\ts %d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d%s%s\n" %
						(transponder["frequency"],
						transponder["symbol_rate"],
						transponder["polarization"],
						transponder["fec_inner"],
						orbital_position,
						transponder["inversion"],
						transponder["flags"],
						transponder["system"],
						transponder["modulation"],
						transponder["roll_off"],
						transponder["pilot"],
						multistream,
						t2mi))
			elif transponder["dvb_type"] == "dvbt":
				lamedblist.append("\tt %d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d\n" %
					(transponder["frequency"],
					transponder["bandwidth"],
					transponder["code_rate_hp"],
					transponder["code_rate_lp"],
					transponder["modulation"],
					transponder["transmission_mode"],
					transponder["guard_interval"],
					transponder["hierarchy"],
					transponder["inversion"],
					transponder["flags"],
					transponder["system"],
					transponder["plpid"]))
			elif transponder["dvb_type"] == "dvbc":
				lamedblist.append("\tc %d:%d:%d:%d:%d:%d:%d\n" %
					(transponder["frequency"],
					transponder["symbol_rate"],
					transponder["inversion"],
					transponder["modulation"],
					transponder["fec_inner"],
					transponder["flags"],
					transponder["system"]))
			lamedblist.append("/\n")
			transponders_count += 1

		lamedblist.append("end\nservices\n")
		for key in list(transponders.keys()):
			transponder = transponders[key]
			if "services" not in list(transponder.keys()):
				continue

			for key2 in list(transponder["services"].keys()):
				service = transponder["services"][key2]

				lamedblist.append("%04x:%08x:%04x:%04x:%d:%d%s\n" %
					(service["service_id"],
					service["namespace"],
					service["transport_stream_id"],
					service["original_network_id"],
					service["service_type"],
					service["flags"],
					":%x" % service["ATSC_source_id"] if "ATSC_source_id" in service else ""))

				control_chars = ''.join(map(chr, list(range(0, 32)) + list(range(127, 160))))
				control_char_re = re.compile('[%s]' % re.escape(control_chars))
				if 'provider_name' in list(service.keys()):
					if six.PY2:
						service_name = control_char_re.sub('', service["service_name"]).decode('latin-1').encode("utf8")
						provider_name = control_char_re.sub('', service["provider_name"]).decode('latin-1').encode("utf8")
					else:
						service_name = control_char_re.sub('', service["service_name"])
						provider_name = control_char_re.sub('', service["provider_name"])
				else:
					service_name = service["service_name"]

				lamedblist.append("%s\n" % service_name)

				service_ca = ""
				if "free_ca" in list(service.keys()) and service["free_ca"] != 0:
					service_ca = ",C:0000"

				service_flags = ""
				if "service_flags" in list(service.keys()) and service["service_flags"] > 0:
					service_flags = ",f:%x" % service["service_flags"]

				if 'service_line' in list(service.keys()):
					if six.PY2:
						lamedblist.append(self.utf8_convert("%s\n" % service["service_line"]))
					else:
						lamedblist.append("%s\n" % service["service_line"])
				else:
					lamedblist.append("p:%s%s%s\n" % (provider_name, service_ca, service_flags))
				services_count += 1

		lamedblist.append("end\nHave a lot of bugs!\n")
		lamedb = codecs.open(path + "/" + filename, "w", "utf-8")
		lamedb.write(''.join(lamedblist))
		lamedb.close()
		del lamedblist

		print("[SatScanLcn-LamedbWriter] Wrote %d transponders and %d services" % (transponders_count, services_count))

	def writeLamedb5(self, path, transponders, filename="lamedb5"):
		print("[SatScanLcn-LamedbWriter] Writing lamedb V5...")

		transponders_count = 0
		services_count = 0

		lamedblist = []
		lamedblist.append("eDVB services /5/\n")
		lamedblist.append("# Transponders: t:dvb_namespace:transport_stream_id:original_network_id,FEPARMS\n")
		lamedblist.append("#     DVBS  FEPARMS:   s:frequency:symbol_rate:polarisation:fec:orbital_position:inversion:flags\n")
		lamedblist.append("#     DVBS2 FEPARMS:   s:frequency:symbol_rate:polarisation:fec:orbital_position:inversion:flags:system:modulation:rolloff:pilot[,MIS/PLS:is_id:pls_code:pls_mode][,T2MI:t2mi_plp_id:t2mi_pid]\n")
		lamedblist.append("#     DVBT  FEPARMS:   t:frequency:bandwidth:code_rate_HP:code_rate_LP:modulation:transmission_mode:guard_interval:hierarchy:inversion:flags:system:plp_id\n")
		lamedblist.append("#     DVBC  FEPARMS:   c:frequency:symbol_rate:inversion:modulation:fec_inner:flags:system\n")
		lamedblist.append('# Services: s:service_id:dvb_namespace:transport_stream_id:original_network_id:service_type:service_number:source_id,"service_name"[,p:provider_name][,c:cached_pid]*[,C:cached_capid]*[,f:flags]\n')

		for key in list(transponders.keys()):
			transponder = transponders[key]
			if "services" not in list(transponder.keys()) or len(transponder["services"]) < 1:
				continue
			lamedblist.append("t:%08x:%04x:%04x," %
				(transponder["namespace"],
				transponder["transport_stream_id"],
				transponder["original_network_id"]))

			if transponder["dvb_type"] == "dvbs":
				if transponder["orbital_position"] > 1800:
					orbital_position = transponder["orbital_position"] - 3600
				else:
					orbital_position = transponder["orbital_position"]

				if transponder["system"] == 0:  # DVB-S
					lamedblist.append("s:%d:%d:%d:%d:%d:%d:%d\n" %
						(transponder["frequency"],
						transponder["symbol_rate"],
						transponder["polarization"],
						transponder["fec_inner"],
						orbital_position,
						transponder["inversion"],
						transponder["flags"]))
				else:  # DVB-S2
					multistream = ''
					t2mi = ''
					if "is_id" in transponder and "pls_code" in transponder and "pls_mode" in transponder:
						try:  # some images are still not multistream aware after all this time
							# don't write default values
							if not (transponder["is_id"] == eDVBFrontendParametersSatellite.No_Stream_Id_Filter and transponder["pls_code"] == eDVBFrontendParametersSatellite.PLS_Gold and transponder["pls_mode"] == eDVBFrontendParametersSatellite.PLS_Default_Gold_Code):
								multistream = ',MIS/PLS:%d:%d:%d' % (
									transponder["is_id"],
									transponder["pls_code"],
									transponder["pls_mode"])
						except AttributeError as err:
							print("[-BouquetsWriter] some images are still not multistream aware after all this time", err)
					if "t2mi_plp_id" in transponder and "t2mi_pid" in transponder:
						t2mi = ',T2MI:%d:%d' % (
							transponder["t2mi_plp_id"],
							transponder["t2mi_pid"])
					lamedblist.append("s:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d%s%s\n" %
						(transponder["frequency"],
						transponder["symbol_rate"],
						transponder["polarization"],
						transponder["fec_inner"],
						orbital_position,
						transponder["inversion"],
						transponder["flags"],
						transponder["system"],
						transponder["modulation"],
						transponder["roll_off"],
						transponder["pilot"],
						multistream,
						t2mi))
			elif transponder["dvb_type"] == "dvbt":
				lamedblist.append("t:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d\n" %
					(transponder["frequency"],
					transponder["bandwidth"],
					transponder["code_rate_hp"],
					transponder["code_rate_lp"],
					transponder["modulation"],
					transponder["transmission_mode"],
					transponder["guard_interval"],
					transponder["hierarchy"],
					transponder["inversion"],
					transponder["flags"],
					transponder["system"],
					transponder["plpid"]))
			elif transponder["dvb_type"] == "dvbc":
				lamedblist.append("c:%d:%d:%d:%d:%d:%d:%d\n" %
					(transponder["frequency"],
					transponder["symbol_rate"],
					transponder["inversion"],
					transponder["modulation"],
					transponder["fec_inner"],
					transponder["flags"],
					transponder["system"]))
			transponders_count += 1

		for key in list(transponders.keys()):
			transponder = transponders[key]
			if "services" not in list(transponder.keys()):
				continue

			for key2 in list(transponder["services"].keys()):
				service = transponder["services"][key2]

				lamedblist.append("s:%04x:%08x:%04x:%04x:%d:%d%s," %
					(service["service_id"],
					service["namespace"],
					service["transport_stream_id"],
					service["original_network_id"],
					service["service_type"],
					service["flags"],
					":%x" % service["ATSC_source_id"] if "ATSC_source_id" in service else ":0"))

				control_chars = ''.join(map(chr, list(range(0, 32)) + list(range(127, 160))))
				control_char_re = re.compile('[%s]' % re.escape(control_chars))
				if 'provider_name' in list(service.keys()):
					if six.PY2:
						service_name = control_char_re.sub('', service["service_name"]).decode('latin-1').encode("utf8")
						provider_name = control_char_re.sub('', service["provider_name"]).decode('latin-1').encode("utf8")
					else:
						service_name = control_char_re.sub('', service["service_name"])
						provider_name = control_char_re.sub('', service["provider_name"])
				else:
					service_name = service["service_name"]

				lamedblist.append('"%s"' % service_name)

				service_ca = ""
				if "free_ca" in list(service.keys()) and service["free_ca"] != 0:
					service_ca = ",C:0000"

				service_flags = ""
				if "service_flags" in list(service.keys()) and service["service_flags"] > 0:
					service_flags = ",f:%x" % service["service_flags"]

				if 'service_line' in list(service.keys()):  # from lamedb
					if len(service["service_line"]):
						if six.PY2:
							lamedblist.append(",%s\n" % self.utf8_convert(service["service_line"]))
						else:
							lamedblist.append(",%s\n" % (service["service_line"]))
					else:
						lamedblist.append("\n")
				else:  # from scanner
					lamedblist.append(",p:%s%s%s\n" % (provider_name, service_ca, service_flags))
				services_count += 1

		lamedb = codecs.open(path + "/" + filename, "w", "utf-8")
		lamedb.write(''.join(lamedblist))
		lamedb.close()
		del lamedblist

		print("[SatScanLcn-LamedbWriter] Wrote %d transponders and %d services" % (transponders_count, services_count))

	def utf8_convert(self, text):
		for encoding in ["utf8", "latin1"]:
			try:
				if six.PY2:
					text.decode(encoding=encoding)
				else:
					six.ensure_str(text, encoding=encoding)
			except UnicodeDecodeError:
				encoding = None
			else:
				break
		if encoding == "utf8":
			return text
		if encoding is None:
			encoding = "utf8"
		if six.PY2:
			return text.decode(encoding=encoding, errors="ignore").encode("utf8")
		else:
			return six.ensure_text(six.ensure_str(text, encoding=encoding, errors='ignore'), encoding='utf8')
