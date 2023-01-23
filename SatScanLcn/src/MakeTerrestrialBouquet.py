from __future__ import print_function
# for localized messages
from . import _

from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Screens.MessageBox import MessageBox
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.ProgressBar import ProgressBar
from Components.Sources.Progress import Progress
from Components.Sources.FrontendStatus import FrontendStatus
from Components.config import config

from enigma import eDVBResourceManager, eTimer, eDVBDB, eDVBFrontendParametersTerrestrial

import os
import sys

import datetime
import time

from .TerrestrialScan import setParams, setParamsFe

from . import dvbreader
from .downloadbar import downloadBar


class MakeTerrestrialBouquet(Screen):
	skin = downloadBar()

	def __init__(self, session, args=0):
		self.config = config.plugins.TerrestrialScan
		self.debugName = self.__class__.__name__
		print("[%s][__init__] Starting..." % self.debugName)
		print("[%s][__init__] args" % self.debugName, args)
		self.session = session
		Screen.__init__(self, session)
		Screen.setTitle(self, _("MakeBouquet"))
		self.skinName = ["TerrestrialScan"]

		self.path = "/etc/enigma2"
		self.services_dict = {}
		self.tmp_services_dict = {}
		self.namespace_dict = {} # to store namespace when sub network is enabled
		self.logical_channel_number_dict = {}
		self.ignore_visible_service_flag = False # make this a user override later if found necessary
		self.VIDEO_ALLOWED_TYPES = [1, 4, 5, 17, 22, 24, 25, 27, 135]
		self.AUDIO_ALLOWED_TYPES = [2, 10]
		self.BOUQUET_PREFIX = "userbouquet.TerrestrialScan."
		self.bouquetsIndexFilename = "bouquets.tv"
		self.bouquetFilename = self.BOUQUET_PREFIX + "tv"
		self.bouquetName = _('Terrestrial')
		self.namespace_complete_terrestrial = not (config.usage.subnetwork_terrestrial.value if hasattr(config.usage, "subnetwork_terrestrial") else True) # config.usage.subnetwork not available in all images

		self.terrestrialXmlFilename = "terrestrial.xml"

		self.frontend = None
		self.rawchannel = None

		self["background"] = Pixmap()
		self["action"] = Label(_("Starting scanner"))
		self["status"] = Label("")
		self["progress"] = ProgressBar()
		self["progress_text"] = Progress()
		self["tuner_text"] = Label("")
		self["Frontend"] = FrontendStatus(frontend_source=lambda: self.frontend, update_interval=100)

		self["actions"] = ActionMap(["SetupActions"],
		{
			"cancel": self.keyCancel,
		}, -2)

		self.selectedNIM = -1
		self.transponders_unique = {}
		self.FTA_only = False
		self.makebouquet = True
		self.makexmlfile = False
		self.lcndescriptor = 0x83
		self.channel_list_id = 0
		if args:
			if "feid" in args:
				self.selectedNIM = args["feid"]
			if "transponders_unique" in args:
				self.transponders_unique = args["transponders_unique"]
			if "FTA_only" in args:
				self.FTA_only = args["FTA_only"]
			if "makebouquet" in args:
				self.makebouquet = args["makebouquet"]
			if "makexmlfile" in args:
				self.makexmlfile = args["makexmlfile"]
			if "lcndescriptor" in args:
				self.lcndescriptor = args["lcndescriptor"]
			if "channel_list_id" in args:
				self.channel_list_id = args["channel_list_id"]

		self.tsidOnidKeys = list(self.transponders_unique.keys())
		self.index = 0
		self.lockTimeout = 50 	# 100ms for tick - 5 sec

		self.onClose.append(self.__onClose)
		self.onFirstExecBegin.append(self.firstExec)

	def firstExec(self):
		if len(self.transponders_unique) > 0:
			self["action"].setText(_('Making bouquet...'))
			self["status"].setText(_("Reading streams"))
			self.progresscount = len(self.transponders_unique)
			self.progresscurrent = 1
			self["progress_text"].range = self.progresscount
			self["progress_text"].value = self.progresscurrent
			self["progress"].setRange((0, self.progresscount))
			self["progress"].setValue(self.progresscurrent)
			self.timer = eTimer()
			self.timer.callback.append(self.readStreams)
			self.timer.start(100, 1)
		else:
			self.showError(_('No transponders to read'))

	def readStreams(self):
		self["tuner_text"].setText("")
		if self.index < len(self.transponders_unique):
			self.transponder = self.transponders_unique[self.tsidOnidKeys[self.index]]
			self.progresscurrent = self.index
			self["progress_text"].value = self.progresscurrent
			self["progress"].setValue(self.progresscurrent)
			self["action"].setText(_("Tuning %s MHz") % str(self.transponder["frequency"] // 1000000))
			self["status"].setText(_("TSID: %d, ONID: %d") % (self.transponder["tsid"], self.transponder["onid"]))
			self.index += 1
			self.searchtimer = eTimer()
			self.searchtimer.callback.append(self.getFrontend)
			self.searchtimer.start(100, 1)
		else:
			if len(self.transponders_unique) > 0:
				self.corelate_data()
				self.solveDuplicates()
				if self.config.uhf_vhf.value != "xml" and self.makexmlfile:
					self.createTerrestrialXml()
				if self.makebouquet and len(self.services_dict) > 0:
					self.createBouquet()
				answer = [self.selectedNIM, self.transponders_unique]
			else:
				answer = None
			self.close(answer)

	def getFrontend(self):
		resmanager = eDVBResourceManager.getInstance()
		if not resmanager:
			print("[%s][getFrontend] Cannot retrieve Resource Manager instance" % self.debugName)
			self.showError(_('Cannot retrieve Resource Manager instance'))
			return

		if self.rawchannel:
			del(self.rawchannel)

		self.frontend = None
		self.rawchannel = None

		self.rawchannel = resmanager.allocateRawChannel(self.selectedNIM)
		if not self.rawchannel:
			print("[%s][getFrontend] Cannot get the NIM" % self.debugName)
			self.showError(_("Cannot get the NIM"))
			return

		print("[%s][getFrontend] Will wait up to %i seconds for tuner lock." % (self.debugName, self.lockTimeout // 10))

		self["tuner_text"].setText(chr(ord('A') + self.selectedNIM))

		self.frontend = self.rawchannel.getFrontend()
		if not self.frontend:
			print("[%s][getFrontend] Cannot get frontend" % self.debugName)
			self.showError(_('Cannot get frontend'))
			return

		self.demuxer_id = self.rawchannel.reserveDemux()
		if self.demuxer_id < 0:
			print("[%s][getFrontend] Cannot allocate the demuxer" % self.debugName)
			self.showError(_('Cannot allocate the demuxer'))
			return

		self.frontend.tune(setParamsFe(setParams(self.transponder["frequency"], self.transponder["system"], self.transponder["bandwidth"])))

		self.lockcounter = 0
		self.locktimer = eTimer()
		self.locktimer.callback.append(self.checkTunerLock)
		self.locktimer.start(100, 1)

	def checkTunerLock(self):
		self.dict = {}
		self.frontend.getFrontendStatus(self.dict)
		if self.dict["tuner_state"] == "TUNING":
			if self.lockcounter < 1: # only show this once in the log per retune event
				print("[%s][checkTunerLock] TUNING" % self.debugName)
		elif self.dict["tuner_state"] == "LOCKED":
			print("[%s][checkTunerLock] TUNER LOCKED" % self.debugName)
			self["action"].setText(_("Reading SI tables on %s MHz") % str(self.transponder["frequency"] // 1000000))
			#self["status"].setText(_("???"))

			self.readTransponderCounter = 0
			self.readTranspondertimer = eTimer()
			self.readTranspondertimer.callback.append(self.readTransponder)
			self.readTranspondertimer.start(100, 1)
			return
		elif self.dict["tuner_state"] in ("LOSTLOCK", "FAILED"):
			print("[%s][checkTunerLock] TUNING FAILED" % self.debugName)
			self.readStreams()
			return

		self.lockcounter += 1
		if self.lockcounter > self.lockTimeout:
			print("[%s][checkTunerLock] Timeout for tuner lock" % self.debugName)
			self.readStreams()
			return
		self.locktimer.start(100, 1)

	def readTransponder(self):
		self.readSDT()
		self.readNIT()
		self.readStreams()

	def readSDT(self):
		adapter = 0
		demuxer_device = "/dev/dvb/adapter%d/demux%d" % (adapter, self.demuxer_id)

		self.tsid = None
		self.onid = None
		sdt_pid = 0x11
		sdt_current_table_id = 0x42
		mask = 0xff
		sdtTimeout = 5 # maximum time allowed to read the service descriptor table (seconds)

		sdt_current_version_number = -1
		sdt_current_sections_read = []
		sdt_current_sections_count = 0
		sdt_current_content = []
		sdt_current_completed = False

		fd = dvbreader.open(demuxer_device, sdt_pid, sdt_current_table_id, mask, self.selectedNIM)
		if fd < 0:
			print("[%s][readSDT] Cannot open the demuxer" % self.debugName)
			return None

		timeout = datetime.datetime.now()
		timeout += datetime.timedelta(0, sdtTimeout)

		while True:
			if datetime.datetime.now() > timeout:
				print("[Satfinder][getCurrentTsidOnid] Timed out" % self.debugName)
				break

			section = dvbreader.read_sdt(fd, sdt_current_table_id, 0x00)
			if section is None:
				time.sleep(0.1)	# no data.. so we wait a bit
				continue

			if section["header"]["table_id"] == sdt_current_table_id and not sdt_current_completed:
				if section["header"]["version_number"] != sdt_current_version_number:
					sdt_current_version_number = section["header"]["version_number"]
					sdt_current_sections_read = []
					sdt_current_sections_count = section["header"]["last_section_number"] + 1
					sdt_current_content = []

				if section["header"]["section_number"] not in sdt_current_sections_read:
					sdt_current_sections_read.append(section["header"]["section_number"])
					sdt_current_content += section["content"]
					if self.tsid is None or self.onid is None: # save first read of tsid and onid, although data in self.transponder should already be correct.
						self.tsid = self.transponder["tsid"] = section["header"]["transport_stream_id"]
						self.onid = self.transponder["onid"] = section["header"]["original_network_id"]

					if len(sdt_current_sections_read) == sdt_current_sections_count:
						sdt_current_completed = True

			if sdt_current_completed:
				break

		dvbreader.close(fd)

		if not sdt_current_content:
			print("[%s][readSDT] no services found on transponder" % self.debugName)
			return

		for i in range(len(sdt_current_content)):
			service = sdt_current_content[i]

			if self.FTA_only and service["free_ca"] != 0:
				continue

			if service["service_type"] not in self.VIDEO_ALLOWED_TYPES and service["service_type"] not in self.AUDIO_ALLOWED_TYPES:
				continue

			servicekey = "%x:%x:%x" % (service["transport_stream_id"], service["original_network_id"], service["service_id"])
			service["signalQuality"] = self.transponder["signalQuality"] # Used for sorting of duplicate LCNs
			self.tmp_services_dict[servicekey] = service

	def readNIT(self):
		adapter = 0
		demuxer_device = "/dev/dvb/adapter%d/demux%d" % (adapter, self.demuxer_id)

		nit_current_pid = 0x10
		nit_current_table_id = 0x40
		nit_other_table_id = 0x00 # don't read other table
		if nit_other_table_id == 0x00:
			mask = 0xff
		else:
			mask = nit_current_table_id ^ nit_other_table_id ^ 0xff
		nit_current_timeout = 20 # maximum time allowed to read the network information table (seconds)

		nit_current_version_number = -1
		nit_current_sections_read = []
		nit_current_sections_count = 0
		nit_current_content = []
		nit_current_completed = False

		fd = dvbreader.open(demuxer_device, nit_current_pid, nit_current_table_id, mask, self.selectedNIM)
		if fd < 0:
			print("[%s][readNIT] Cannot open the demuxer" % self.debugName)
			return

		timeout = datetime.datetime.now()
		timeout += datetime.timedelta(0, nit_current_timeout)

		while True:
			if datetime.datetime.now() > timeout:
				print("[%s][readNIT] Timed out reading NIT" % self.debugName)
				break

			section = dvbreader.read_nit(fd, nit_current_table_id, nit_other_table_id)
			if section is None:
				time.sleep(0.1)	# no data.. so we wait a bit
				continue

			if section["header"]["table_id"] == nit_current_table_id and not nit_current_completed:
				if section["header"]["version_number"] != nit_current_version_number:
					nit_current_version_number = section["header"]["version_number"]
					nit_current_sections_read = []
					nit_current_sections_count = section["header"]["last_section_number"] + 1
					nit_current_content = []

				if section["header"]["section_number"] not in nit_current_sections_read:
					nit_current_sections_read.append(section["header"]["section_number"])
					nit_current_content += section["content"]

					if len(nit_current_sections_read) == nit_current_sections_count:
						nit_current_completed = True

			if nit_current_completed:
				break

		dvbreader.close(fd)

		if not nit_current_content:
			print("[%s][readNIT] current transponder not found" % self.debugName)
			return

		# descriptor_tag 0x5A is DVB-T, descriptor_tag 0x7f is DVB-T
		transponders = [t for t in nit_current_content if "descriptor_tag" in t and t["descriptor_tag"] in (0x5A, 0x7f) and t["original_network_id"] == self.transponder["onid"] and t["transport_stream_id"] == self.transponder["tsid"]] # this should only ever have a length of one transponder
		print("[%s][readNIT] transponders" % self.debugName, transponders)
		if transponders:

			if transponders[0]["descriptor_tag"] == 0x5A: # DVB-T
				self.transponder["system"] = eDVBFrontendParametersTerrestrial.System_DVB_T
			else: # must be DVB-T2
				self.transponder["system"] = eDVBFrontendParametersTerrestrial.System_DVB_T2

			if "frequency" in transponders[0] and abs((transponders[0]["frequency"] * 10) - self.transponder["frequency"]) < 1000000 and self.transponder["frequency"] != transponders[0]["frequency"] * 10:
				print("[%s][readNIT] updating transponder frequency from %.03f MHz to %.03f MHz" % (self.debugName, self.transponder["frequency"] // 1000000, transponders[0]["frequency"] // 100000))
				self.transponder["frequency"] = transponders[0]["frequency"] * 10

		# LCNs = [t for t in nit_current_content if "descriptor_tag" in t and t["descriptor_tag"] == self.lcndescriptor and t["original_network_id"] == self.transponder["onid"]]
		LCNs = [t for t in nit_current_content if "descriptor_tag" in t and t["descriptor_tag"] == self.lcndescriptor and (self.lcndescriptor == 0x83 or (self.lcndescriptor == 0x87 and ("channel_list_id" in t and t["channel_list_id"] == self.channel_list_id or self.channel_list_id == 0))) and t["original_network_id"] == self.transponder["onid"]]

		print("[%s][readNIT] LCNs" % self.debugName, LCNs)
		if LCNs:
			for LCN in LCNs:
				LCNkey = "%x:%x:%x" % (LCN["transport_stream_id"], LCN["original_network_id"], LCN["service_id"])

				if not self.ignore_visible_service_flag and "visible_service_flag" in LCN and LCN["visible_service_flag"] == 0:
					continue

				# Only write to the dict if there is no entry, or override the entry if the data comes from the same transponder the channel is located on.
				if LCNkey not in self.logical_channel_number_dict or LCN["transport_stream_id"] == self.transponder["tsid"]:
					self.logical_channel_number_dict[LCNkey] = LCN

		namespace = 0xEEEE0000
		if self.namespace_complete_terrestrial:
			namespace |= (self.transponder['frequency'] // 1000000) & 0xFFFF
		namespacekey = "%x:%x" % (self.transponder["tsid"], self.transponder["onid"])
		self.namespace_dict[namespacekey] = namespace

	def createBouquet(self):
		for tv_radio in ("tv", "radio"):
			radio_services = [x for x in self.services_dict.values() if x["service_type"] in self.AUDIO_ALLOWED_TYPES]
			if tv_radio == "radio" and (not radio_services or not self.config.makeradiobouquet.value):
				break
			self.tv_radio = tv_radio
			bouquetIndexContent = self.readBouquetIndex()
			if '"' + self.bouquetFilename[:-2] + tv_radio + '"' not in bouquetIndexContent: # only edit the index if bouquet file is not present
				self.writeBouquetIndex(bouquetIndexContent)
			self.writeBouquet()

		eDVBDB.getInstance().reloadBouquets()

	def corelate_data(self):
		servicekeys = self.iterateServicesBySNR(self.tmp_services_dict)
		self.duplicates = []
		for servicekey in servicekeys:
			if servicekey in self.logical_channel_number_dict:
				self.tmp_services_dict[servicekey]["logical_channel_number"] = self.logical_channel_number_dict[servicekey]["logical_channel_number"]
				if self.logical_channel_number_dict[servicekey]["logical_channel_number"] not in self.services_dict:
					self.services_dict[self.logical_channel_number_dict[servicekey]["logical_channel_number"]] = self.tmp_services_dict[servicekey]
				else:
					self.duplicates.append(self.tmp_services_dict[servicekey])

	def solveDuplicates(self):
		if self.config.uhf_vhf.value == "australia":
			vacant = [i for i in range(350, 400) if i not in self.services_dict]
			for duplicate in self.duplicates:
				if not vacant: # not slots available
					break
				self.services_dict[vacant.pop(0)] = duplicate

	def iterateServicesBySNR(self, servicesDict):
		# return a key list of services sorted by signal quality descending
		sort_list = [(k, s["signalQuality"]) for k, s in servicesDict.items()]
		return [x[0] for x in sorted(sort_list, key=lambda listItem: listItem[1], reverse=True)]

	def readBouquetIndex(self):
		try:
			bouquets = open(self.path + "/%s%s" % (self.bouquetsIndexFilename[:-2], self.tv_radio), "r")
		except Exception as e:
			return ""
		content = bouquets.read()
		bouquets.close()
		return content

	def writeBouquetIndex(self, bouquetIndexContent):
		bouquets_index_list = []
		bouquets_index_list.append("#NAME Bouquets (%s)\n" % ("TV" if self.tv_radio == "tv" else "Radio"))
		bouquets_index_list.append("#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET \"%s%s\" ORDER BY bouquet\n" % (self.bouquetFilename[:-2], self.tv_radio))
		if bouquetIndexContent:
			lines = bouquetIndexContent.split("\n", 1)
			if lines[0][:6] != "#NAME ":
				bouquets_index_list.append("%s\n" % lines[0])
			if len(lines) > 1:
				bouquets_index_list.append("%s" % lines[1])

		bouquets_index = open(self.path + "/" + self.bouquetsIndexFilename[:-2] + self.tv_radio, "w")
		bouquets_index.write(''.join(bouquets_index_list))
		bouquets_index.close()
		del bouquets_index_list

	def writeBouquet(self):
		allowed_service_types = not self.config.makeradiobouquet.value and self.VIDEO_ALLOWED_TYPES + self.AUDIO_ALLOWED_TYPES or\
					self.tv_radio == "tv" and self.VIDEO_ALLOWED_TYPES or\
					self.tv_radio == "radio" and self.AUDIO_ALLOWED_TYPES
		bouquet_list = []
		bouquet_list.append("#NAME %s\n" % self.bouquetName)

		numbers = range(1, 1001)
		for number in numbers:
			if number in self.services_dict and self.services_dict[number]["service_type"] in allowed_service_types:
				bouquet_list.append(self.bouquetServiceLine(self.services_dict[number]))
			else:
				bouquet_list.append("#SERVICE 1:832:d:0:0:0:0:0:0:0:\n")
				bouquet_list.append("#DESCRIPTION  \n")

		bouquetFile = open(self.path + "/" + self.bouquetFilename[:-2] + self.tv_radio, "w")
		bouquetFile.write(''.join(bouquet_list))
		bouquetFile.close()
		del bouquet_list

	def bouquetServiceLine(self, service):
		return "#SERVICE 1:0:%x:%x:%x:%x:%x:0:0:0:\n" % (
			service["service_type"],
			service["service_id"],
			service["transport_stream_id"],
			service["original_network_id"],
			self.getNamespace(service)
		)

	def getNamespace(self, service):
		namespacekey = "%x:%x" % (service["transport_stream_id"], service["original_network_id"])
		return self.namespace_dict[namespacekey] if namespacekey in self.namespace_dict else 0xEEEE0000

	def createTerrestrialXml(self):
		xml = ['<?xml version="1.0" encoding="UTF-8"?>\n']
		xml.append('<!-- File created on %s with the TerrestrialScan plugin -->\n' % (time.strftime("%A, %d of %B %Y, %H:%M:%S")))
		xml.append('<locations>\n')
		xml.append('\t<terrestrial name="My local region (Europe DVB-T/T2)" flags="5">\n')
		for tsidOnidKey in self.iterateUniqueTranspondersByFrequency():
			transponder = self.transponders_unique[tsidOnidKey]
			xml.append('\t\t<transponder centre_frequency="%d" system="%d" bandwidth="%d" constellation="3"/><!-- onid="%d" tsid="%d" signal_quality="%d" -->\n' % (transponder["frequency"], transponder["system"], transponder["bandwidth"] == 7 and 1 or 0, transponder["onid"], transponder["tsid"], transponder["signalQuality"]))
		xml.append('\t</terrestrial>\n')
		xml.append('</locations>')

		xmlFile = open(self.path + "/" + self.terrestrialXmlFilename, "w")
		xmlFile.write(''.join(xml))
		xmlFile.close()
		del xml

	def iterateUniqueTranspondersByFrequency(self):
		# returns an iterator list for self.transponders_unique in frequency order ascending
		sort_list = [(x[0], x[1]["frequency"]) for x in self.transponders_unique.items()]
		return [x[0] for x in sorted(sort_list, key=lambda listItem: listItem[1])]

	def showError(self, message):
		question = self.session.open(MessageBox, message, MessageBox.TYPE_ERROR)
		question.setTitle(_("TerrestrialScan"))
		self.close()

	def keyCancel(self):
		self.close()

	def __onClose(self):
		if self.frontend:
			self.frontend = None
			del(self.rawchannel)
