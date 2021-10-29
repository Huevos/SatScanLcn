# for localized messages
from __future__ import print_function
from . import _
import six

from Components.ActionMap import ActionMap
from Components.config import config, getConfigListEntry, configfile, ConfigYesNo
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.NimManager import nimmanager
from Components.ProgressBar import ProgressBar
from Components.Sources.StaticText import StaticText
from Components.Sources.FrontendStatus import FrontendStatus
from Components.Sources.Progress import Progress

from Screens.MessageBox import MessageBox
from Screens.Screen import Screen

from .about import SatScanLcn_About
from .downloadbar import downloadBar
from .lamedbreader import LamedbReader
from .lamedbwriter import LamedbWriter
from .providers import PROVIDERS

from enigma import eTimer, eDVBDB, eDVBFrontendParametersSatellite, eDVBFrontendParameters, eDVBResourceManager

from time import localtime, time, strftime, mktime, sleep
import datetime
import re


from Plugins.SystemPlugins.AutoBouquetsMaker.scanner import dvbreader
#from . import dvbreader


class SatScanLcn(Screen): # the downloader
	skin = downloadBar()

	def __init__(self, session, args = None):
		self.config = config.plugins.satscanlcn
		self.debugName = self.__class__.__name__
		self.extra_debug = self.config.extra_debug.value
		self.screentitle = _("Sat Scan LCN")
		print("[%s][__init__] Starting..." % self.debugName)
		print("[%s][__init__] args" % self.debugName, args)
		self.session = session
		Screen.__init__(self, session)
		Screen.setTitle(self, self.screentitle)

		self["action"] = Label(_("Starting scanner"))
		self["status"] = Label("")
		self["progress"] = ProgressBar()
		self["progress_text"] = Progress()
		self["tuner_text"] = Label("")

		# don't forget to disable this ActionMap before writing to any settings files
		self["actions"] = ActionMap(["SetupActions"],
		{
			"cancel": self.keyCancel,
		}, -2)

		self.selectedNIM = -1
		if args:
			pass
		self.frontend = None
		self["Frontend"] = FrontendStatus(frontend_source = lambda : self.frontend, update_interval = 100)
		self.rawchannel = None
		self.postScanService = None # self.session.nav.getCurrentlyPlayingServiceOrGroup()
		self.LOCK_TIMEOUT_ROTOR = 1200 	# 100ms for tick - 120 sec
		self.LOCK_TIMEOUT_FIXED = 50 	# 100ms for tick - 5 sec

		self.LOCK_TIMEOUT = self.LOCK_TIMEOUT_FIXED

		self.TIMEOUT_NIT = 20 # DVB standard says less than 10
		self.TIMEOUT_BAT = 20 # DVB standard says less than 10
		self.TIMEOUT_SDT = 5 # DVB standard says less than 2

		self.path = "/etc/enigma2" # path to settings files

		self.homeTransponder = PROVIDERS[self.config.provider.value]["transponder"]
		self.bat = PROVIDERS[self.config.provider.value]["bat"] if "bat" in PROVIDERS[self.config.provider.value] else None

		self.descriptors = {"transponder": 0x43, "serviceList": 0x41, "lcn": 0x83}

		self.transponders_dict = {} # overwritten in firstExec
		self.services_dict = {} # Services waiting to be written to bouquet file. Keys of this dict are LCNs
		self.tmp_service_list = [] # holds the service list from NIT (for cross referencing)
		self.tmp_bat_content = [] # holds bat data waiting for processing
		self.logical_channel_number_dict = {} # Keys, TSID:ONID:SID in hex
		self.ignore_visible_service_flag = False # make this a user override later if found necessary. Visible service flag is currently available in the NIT and BAT on most home transponders
		self.VIDEO_ALLOWED_TYPES = [1, 4, 5, 17, 22, 24, 25, 27, 31, 135] # 4 and 5 NVOD, 17 MPEG-2 HD digital television service, 22 advanced codec SD digital television service, 24 advanced codec SD NVOD reference service, 27 advanced codec HD NVOD reference service, 31 ???, seems to be used on Astra 1 for some UHD/4K services
		self.AUDIO_ALLOWED_TYPES = [2, 10] # 10 advanced codec digital radio sound service
		self.BOUQUET_PREFIX = "userbouquet.%s." % self.config.provider.value # avoids hard coding below
		self.bouquetsIndexFilename = "bouquets.tv" # avoids hard coding below
		self.bouquetFilename = self.BOUQUET_PREFIX + self.config.provider.value + ".tv"
		self.lastScannnedBouquetFilename = "userbouquet.LastScanned.tv"
		self.bouquetName = PROVIDERS[self.config.provider.value]["name"] # already translated
		self.index = -1
		self.actionsList = ["read NIT",] # "read BAT", "read SDTs"]
		if self.bat is not None:
			 self.actionsList.append("read BAT")
		self.actionsListOrigLength = len(self.actionsList)

		self.adapter = 0 # fix me

		self.nit_pid_default = 0x10 # DVB default
		self.nit_current_table_id_default = 0x40 # DVB default
		self.nit_other_table_id_default = 0x41 # DVB default

		self.nit_pid = PROVIDERS[self.config.provider.value]["nit"]["nit_pid"] if "nit" in PROVIDERS[self.config.provider.value] and "nit_pid" in PROVIDERS[self.config.provider.value]["nit"] else self.nit_pid_default
		self.nit_current_table_id = PROVIDERS[self.config.provider.value]["nit"]["nit_current_table_id"] if "nit" in PROVIDERS[self.config.provider.value] and "nit_current_table_id" in PROVIDERS[self.config.provider.value]["nit"] else self.nit_current_table_id_default
		self.nit_other_table_id = PROVIDERS[self.config.provider.value]["nit"]["nit_other_table_id"] if "nit" in PROVIDERS[self.config.provider.value] and "nit_other_table_id" in PROVIDERS[self.config.provider.value]["nit"] else self.nit_other_table_id_default

		self.sdt_pid_default = 0x11 # DVB default
		self.sdt_current_table_id_default = 0x42 # DVB default
		self.sdt_other_table_id_default = 0x46 # DVB default is 0x46. Add the table id in the provider if this is to be read. Only used when self.sdt_only_scan_home_default = True
		self.sdt_only_scan_home_default = False
		
		self.sdt_pid = PROVIDERS[self.config.provider.value]["sdt"]["sdt_pid"] if "sdt" in PROVIDERS[self.config.provider.value] and "sdt_pid" in PROVIDERS[self.config.provider.value]["sdt"] else self.sdt_pid_default
		self.sdt_current_table_id = PROVIDERS[self.config.provider.value]["sdt"]["sdt_current_table_id"] if "sdt" in PROVIDERS[self.config.provider.value] and "sdt_current_table_id" in PROVIDERS[self.config.provider.value]["sdt"] else self.sdt_current_table_id_default
		self.sdt_other_table_id = PROVIDERS[self.config.provider.value]["sdt"]["sdt_other_table_id"] if "sdt" in PROVIDERS[self.config.provider.value] and "sdt_other_table_id" in PROVIDERS[self.config.provider.value]["sdt"] else self.sdt_other_table_id_default
		self.sdt_only_scan_home = PROVIDERS[self.config.provider.value]["sdt"]["sdt_only_scan_home"] if "sdt" in PROVIDERS[self.config.provider.value] and "sdt_only_scan_home" in PROVIDERS[self.config.provider.value]["sdt"] else self.sdt_only_scan_home_default
		
		
		self.bat_pid_default = 0x11 # DVB default
		self.bat_table_id_default = 0x4a # DVB default

		self.bat_pid = PROVIDERS[self.config.provider.value]["bat"]["bat_pid"] if "bat" in PROVIDERS[self.config.provider.value] and "bat_pid" in PROVIDERS[self.config.provider.value]["bat"] else self.bat_pid_default
		self.bat_table_id = PROVIDERS[self.config.provider.value]["bat"]["bat_table_id"] if "bat" in PROVIDERS[self.config.provider.value] and "bat_table_id" in PROVIDERS[self.config.provider.value]["bat"] else self.bat_table_id_default
		self.bat_lcn_descriptor = PROVIDERS[self.config.provider.value]["bat"]["bat_lcn_descriptor"] if "bat" in PROVIDERS[self.config.provider.value] and "bat_lcn_descriptor" in PROVIDERS[self.config.provider.value]["bat"] else None
		# self.bat_region, for use where the provider has multiple regions grouped under any single BouquetID. Will be a list containing the desired region id and may also contain the region id of the services that are common to all regions.
		self.bat_region = PROVIDERS[self.config.provider.value]["bat"]["bat_region"] if "bat" in PROVIDERS[self.config.provider.value] and "bat_region" in PROVIDERS[self.config.provider.value]["bat"] else None # input from providers should be a list
		
		if self.bat_lcn_descriptor:
			self.descriptors["lcn"] = self.bat_lcn_descriptor

		self.SDTscanList = [] # list of transponders we are going to scan the SDT of.
		self.tmp_services_dict = {} # services found in SDTs of the scanned transponders. Keys, TSID:ONID:SID  in hex 

		self.polarization_dict = {
			eDVBFrontendParametersSatellite.Polarisation_Horizontal: "H",
			eDVBFrontendParametersSatellite.Polarisation_Vertical: "V",
			eDVBFrontendParametersSatellite.Polarisation_CircularLeft: "L",
			eDVBFrontendParametersSatellite.Polarisation_CircularRight: "R"
		}

		self.video_services = 0
		self.radio_services = 0

		self.NITreadTime = 0
		self.BATreadTime = 0
		self.SDTsReadTime = 0
		self.tuningTime = 0
		self.run_start_time = time()

		self.namespace_complete = not (config.usage.subnetwork.value if hasattr(config.usage, "subnetwork") else True) # config.usage.subnetwork not available in all distros/images
		self.onFirstExecBegin.append(self.firstExec)

	def firstExec(self):
		from Screens.Standby import inStandby

		self.progresscount = 5 # plus number of transponder to scan once we know this
		self.progresscurrent = 1

		if not inStandby:
			self["action"].setText(_("Reading current settings..."))
			self["progress_text"].range = self.progresscount
			self["progress_text"].value = self.progresscurrent
			self["progress"].setRange((0, self.progresscount))
			self["progress"].setValue(self.progresscurrent)
		self.transponders_dict = LamedbReader().readLamedb(self.path)
		if not inStandby:
			self["action"].setText(_("Current settings read..."))

		self.timer = eTimer()
		self.timer.callback.append(self.manager)
		self.timer.start(100, 1)

	def manager(self):
		self.index += 1
		from Screens.Standby import inStandby

		self.progresscurrent += 1
		if not inStandby:
			self["progress_text"].value = self.progresscurrent
			self["progress"].setValue(self.progresscurrent)

		if len(self.actionsList) > self.index and self.actionsList[self.index] == "read NIT":
			if not inStandby:
				self["status"].setText(_("Searching for transponders..."))
			self.transpondercurrent = self.homeTransponder

			self.timer = eTimer()
			self.timer.callback.append(self.getFrontend)
			self.timer.start(100, 1)

		elif len(self.actionsList) > self.index and self.actionsList[self.index] == "read BAT":
			self["status"].setText(_("Reading bouquet allocation table..."))
			self.readBAT() # we are already tuned so go direct to read BAT

		elif len(self.actionsList) > self.index and self.actionsList[self.index] == "read SDTs":
			if not inStandby:
				self["status"].setText(_("Services: %d video - %d radio") % (self.video_services, self.radio_services))
			self.transpondercurrent = self.SDTscanList[self.index - self.actionsListOrigLength]
			if self.index == self.actionsListOrigLength: # this is the home transponder. We know it is the home transponder because that is first in the SDT scan list. And we are still tuned to it so go direct to read.
				self.readSDT()
			else:
				self.timer = eTimer()
				self.timer.callback.append(self.getFrontend)
				self.timer.start(100, 1)

		else:
			if not inStandby:
				self["action"].setText(_('Bouquets generation...'))
				self["status"].setText(_("Services: %d video - %d radio") % (self.video_services, self.radio_services))
			self.correctTsidErrors() # correct errors due to "broken" NIT on home transponder
			if self.bat is not None:
				self.processBAT()
			self.addTransponders()
			self.fixServiceNames()
			self.addLCNsToServices()
			self.addServicesToTransponders()
			self["actions"].setEnabled(False) # disable action map here so we can't abort half way through writing result to settings files
			self.saveLamedb()
			self.createBouquet()
			self.reloadSettingsAndClose()

	def getFrontend(self):
		from Screens.Standby import inStandby
		if not inStandby:
			self["action"].setText(_("Tune %s %s %s %s...") % (self.bouquetName, self.getOrbPosHuman(self.transpondercurrent["orbital_position"]), str(self.transpondercurrent["frequency"]/1000), self.polarization_dict.get(self.transpondercurrent["polarization"],"")))
		print("[%s][getFrontend] searching for available tuner" % self.debugName)
		nimList = []
		for nim in nimmanager.nim_slots:
			if not nim.isCompatible("DVB-S") or \
				nim.isFBCLink() or \
				(hasattr(nim, 'config_mode_dvbs') and nim.config_mode_dvbs or nim.config_mode) in ("loopthrough", "satposdepends", "nothing") or \
				self.transpondercurrent["orbital_position"] not in [sat[0] for sat in nimmanager.getSatListForNim(nim.slot)]:
				continue
			nimList.append(nim.slot)

		if len(nimList) == 0: # No nims found for this satellite
			print("[%s][getFrontend] No compatible tuner found" % self.debugName)
			self.showError(_("No compatible tuner found"))
			return

		resmanager = eDVBResourceManager.getInstance()
		if not resmanager:
			print("[%s][getFrontend] Cannot retrieve Resource Manager instance" % self.debugName)
			self.showError(_('Cannot retrieve Resource Manager instance'))
			return

		# stop pip if running
		if self.session.pipshown:
			self.session.pipshown = False
			del self.session.pip
			print("[%s][getFrontend] Stopping PIP." % self.debugName)

		# stop currently playing service if it is using a tuner in ("loopthrough", "satposdepends")
		currentlyPlayingNIM = None
		currentService = self.session and self.session.nav.getCurrentService()
		frontendInfo = currentService and currentService.frontendInfo()
		frontendData = frontendInfo and frontendInfo.getAll(True)
		if frontendData is not None:
			currentlyPlayingNIM = frontendData.get("tuner_number", None)
			if currentlyPlayingNIM is not None and nimmanager.nim_slots[currentlyPlayingNIM].isCompatible("DVB-S"):
				nimConfigMode = hasattr(nimmanager.nim_slots[currentlyPlayingNIM], "config_mode_dvbs") and nimmanager.nim_slots[currentlyPlayingNIM].config_mode_dvbs or nimmanager.nim_slots[currentlyPlayingNIM].config_mode
				if nimConfigMode in ("loopthrough", "satposdepends"):
					self.postScanService = self.session.nav.getCurrentlyPlayingServiceReference()
					self.session.nav.stopService()
					currentlyPlayingNIM = None
					print("[%s][getFrontend] The active service was using a %s tuner, so had to be stopped (slot id %s)." % (self.debugName, nimConfigMode, currentlyPlayingNIM))
		del frontendInfo
		del currentService

		current_slotid = -1
		if self.rawchannel:
			del(self.rawchannel)

		self.frontend = None
		self.rawchannel = None

		nimList = [slot for slot in nimList if not self.isRotorSat(slot, self.transpondercurrent["orbital_position"])] + [slot for slot in nimList if self.isRotorSat(slot, self.transpondercurrent["orbital_position"])] #If we have a choice of dishes, try "fixed" before "motorised".
		for slotid in nimList:
			if current_slotid == -1:	# mark the first valid slotid in case of no other one is free
				current_slotid = slotid

			self.rawchannel = resmanager.allocateRawChannel(slotid)
			if self.rawchannel:
				print("[%s][getFrontend] Nim found on slot id %d with sat %s" % (self.debugName, slotid, nimmanager.getSatName(self.transpondercurrent["orbital_position"])))
				current_slotid = slotid
				break

			if self.rawchannel:
				break

		if current_slotid == -1:
			print("[%s][getFrontend] No valid NIM found for %s" % (self.debugName, self.bouquetName))
			self.showError(_('No valid NIM found for %s') % self.bouquetName)
			return

		if not self.rawchannel:
			# if we are here the only possible option is to close the active service
			if currentlyPlayingNIM in nimList:
				slotid = currentlyPlayingNIM
				print("[%s][getFrontend] Nim found on slot id %d but it's busy. Stopping active service" % (self.debugName, slotid))
				self.postScanService = self.session.nav.getCurrentlyPlayingServiceReference()
				self.session.nav.stopService()
				self.rawchannel = resmanager.allocateRawChannel(slotid)
				if self.rawchannel:
					print("[%s][getFrontend] The active service was stopped, and the NIM is now free to use." % self.debugName)
					current_slotid = slotid

			if not self.rawchannel:
				if self.session.nav.RecordTimer.isRecording():
					print("[%s][getFrontend] Cannot free NIM because a recording is in progress" % self.debugName)
					self.showError(_('Cannot free NIM because a recording is in progress'))
					return
				else:
					print("[%s][getFrontend] Cannot get the NIM" % self.debugName)
					self.showError(_('Cannot get the NIM'))
					return

		# set extended timeout for rotors
		self.motorised = False
		if self.isRotorSat(current_slotid, self.transpondercurrent["orbital_position"]):
			self.motorised = True
			self.LOCK_TIMEOUT = self.LOCK_TIMEOUT_ROTOR
			print("[%s][getFrontend] Motorised dish. Will wait up to %i seconds for tuner lock." % (self.debugName, self.LOCK_TIMEOUT/10))
		else:
			self.LOCK_TIMEOUT = self.LOCK_TIMEOUT_FIXED
			print("[%s][getFrontend] Fixed dish. Will wait up to %i seconds for tuner lock." % (self.debugName, self.LOCK_TIMEOUT/10))

		self.selectedNIM = current_slotid  # Remember for downloading SI tables

		self["tuner_text"].setText(chr(ord('A') + current_slotid))

		self.frontend = self.rawchannel.getFrontend()
		if not self.frontend:
			print("[%s][getFrontend] Cannot get frontend" % self.debugName)
			self.showError(_('Cannot get frontend'))
			return

		self.demuxer_id = self.rawchannel.reserveDemux()
		if self.demuxer_id < 0:
			print("[%s][doTune] Cannot allocate the demuxer." % self.debugName)
			self.showError(_('Cannot allocate the demuxer.'))
			return

		params_fe = eDVBFrontendParameters()
		params_fe.setDVBS(self.setParams(), False)

		self.tune_start_time = time()

		self.frontend.tune(params_fe)

		self.lockcounter = 0
		self.locktimer = eTimer()
		self.locktimer.callback.append(self.checkTunerLock)
		self.locktimer.start(100, 1)

	def checkTunerLock(self):
		from Screens.Standby import inStandby
		self.dict = {}
		self.frontend.getFrontendStatus(self.dict)
		if self.dict["tuner_state"] == "TUNING":
			if self.lockcounter < 1: # only show this once in the log per retune event
				print("[%s][checkTunerLock] TUNING" % self.debugName)
		elif self.dict["tuner_state"] == "LOCKED":
			if not inStandby:
				self["action"].setText(_("Read %s %s %s %s...") % (self.bouquetName, self.getOrbPosHuman(self.transpondercurrent["orbital_position"]), str(self.transpondercurrent["frequency"]/1000), self.polarization_dict.get(self.transpondercurrent["polarization"],"")))

			self.readTransponderCounter = 0
			self.readTranspondertimer = eTimer()
			self.readTranspondertimer.callback.append(self.readTransponder)
			self.readTranspondertimer.start(100, 1)
			return
		elif self.dict["tuner_state"] in ("LOSTLOCK", "FAILED"):
			print("[%s][checkTunerLock] TUNING FAILED" % self.debugName)
			if self.actionsList[self.index] == "read SDTs": # if we can't tune a transponder just skip it (like enigma does)
				self.manager()
			else:
				self.showError(_("Tuning failed on %s") % str(self.transpondercurrent["frequency"]/1000))
			return

		self.lockcounter += 1
		if self.lockcounter > self.LOCK_TIMEOUT:
			print("[%s][checkTunerLock] Timeout for tuner lock" % self.debugName)
			self.showError(_("Timeout for tuner lock on %s") % str(self.transpondercurrent["frequency"]/1000))
			return
		self.locktimer.start(100, 1)

	def readTransponder(self):
		# if setup is motorized and we are about to read the NIT, first let's make sure the dish is receiving from the correct satellite.
		if self.motorised and self.actionsList[self.index] in ("read NIT",) and not self.tsidOnidTest(self.transpondercurrent["original_network_id"], self.transpondercurrent["transport_stream_id"]):
			print("[%s][readTransponder] Could not acquire the correct tsid/onid on the home transponder." % self.debugName)
			self.showError(_("Could not acquire the correct tsid/onid on the home transponder."))
			return

		self.tuningTime += time() - self.tune_start_time

		if self.actionsList[self.index] in ("read NIT",):
			self.readNIT()
		elif self.actionsList[self.index] in ("read SDTs",):
			self.readSDT()
		else: # readBAT does not follow this code path
			print("[%s][readTransponder] Something went terribly wrong" % self.debugName)
			self.showError(_("Something went terribly wrong"))

	def tsidOnidTest(self, onid=None, tsid=None):
		# This just grabs the tsid and onid of the current transponder.
		# Used to confirm motorised dishes have arrived at the correct satellite before starting the download.
		print("[%s] tsid onid test..." % self.debugName)

		mask = 0xff
		tsidOnidTestTimeout = 90
		passed_test = False

		self.setDemuxer()

		fd = dvbreader.open(self.demuxer_device, self.sdt_pid, self.sdt_current_table_id, mask, self.selectedNIM)
		if fd < 0:
			print("[%s][tsidOnidTest] Cannot open the demuxer_device '%s'" % (self.debugName, demuxer_device))
			self.showError(_('Cannot open the demuxer'))
			return

		timeout = datetime.datetime.now()
		timeout += datetime.timedelta(0, tsidOnidTestTimeout)

		while True:
			if datetime.datetime.now() > timeout:
				print("[%s][tsidOnidTest] Timed out checking tsid onid" % self.debugName)
				break

			section = dvbreader.read_sdt(fd, self.sdt_current_table_id, 0x00)
			if section is None:
				sleep(0.1)	# no data.. so we wait a bit
				continue

			if section["header"]["table_id"] == self.sdt_current_table_id:
				passed_test = (onid is None or onid == section["header"]["original_network_id"]) and (tsid is None or tsid == section["header"]["transport_stream_id"])
				print("[%s][tsidOnidTest] tsid: %d, onid: %d" % (self.debugName, section["header"]["transport_stream_id"], section["header"]["original_network_id"]))
				if passed_test:
					break

		dvbreader.close(fd)

		return passed_test

	def readNIT(self, read_other_section=True):
		print("[%s] Reading NIT..." % self.debugName)
		
		if self.nit_other_table_id == 0x00:
			mask = 0xff
		else:
			mask = self.nit_current_table_id ^ self.nit_other_table_id ^ 0xff

		self.setDemuxer()

		start_time = time()

		fd = dvbreader.open(self.demuxer_device, self.nit_pid, self.nit_current_table_id, mask, self.selectedNIM)
		if fd < 0:
			print("[%s] Cannot open the demuxer" % self.debugName)
			print("[%s] demuxer_device" % self.debugName, str(self.demuxer_device))
			print("[%s] nit_pid" % self.debugName, str(self.nit_pid))
			print("[%s] nit_current_table_id" % self.debugName, str(self.nit_current_table_id))
			print("[%s] mask", str(mask))
			print("[%s] current_slotid" % self.debugName, str(self.selectedNIM))
			self.showError(_('Cannot open the demuxer'))
			return

		nit_current_section_version = -1
		nit_current_section_network_id = -1
		nit_current_sections_read = []
		nit_current_sections_count = 0
		nit_current_content = []
		nit_current_completed = False

		nit_other_section_version = {}
		nit_other_sections_read = {}
		nit_other_sections_count = {}
		nit_other_content = {}
		nit_other_completed = {}
		all_nit_others_completed = not read_other_section or self.nit_other_table_id == 0x00

		timeout = datetime.datetime.now()
		timeout += datetime.timedelta(0, self.TIMEOUT_NIT)
		while True:
			if datetime.datetime.now() > timeout:
				print("[%s] Timed out reading NIT" % self.debugName)
				if self.nit_other_table_id != 0x00:
					print("[%s] No nit_other found - set self.nit_other_table_id=\"0x00\" for faster scanning?" % self.debugName)
				break

			section = dvbreader.read_nit(fd, self.nit_current_table_id, self.nit_other_table_id)
			if section is None:
				sleep(0.1)	# no data.. so we wait a bit
				continue

			if self.extra_debug:
				print("[%s] NIT raw section header" % self.debugName, section["header"])
				print("[%s] NIT raw section content" % self.debugName, section["content"])

			if (section["header"]["table_id"] == self.nit_current_table_id and not nit_current_completed):
				if self.extra_debug:
					print("[%s] raw section above is from NIT actual table." % self.debugName)

				if (section["header"]["version_number"] != nit_current_section_version or section["header"]["network_id"] != nit_current_section_network_id):
					nit_current_section_version = section["header"]["version_number"]
					nit_current_section_network_id = section["header"]["network_id"]
					nit_current_sections_read = []
					nit_current_content = []
					nit_current_sections_count = section["header"]["last_section_number"] + 1

				if section["header"]["section_number"] not in nit_current_sections_read:
					nit_current_sections_read.append(section["header"]["section_number"])
					nit_current_content += section["content"]

					if len(nit_current_sections_read) == nit_current_sections_count:
						nit_current_completed = True

			elif section["header"]["table_id"] == self.nit_other_table_id and not all_nit_others_completed:
				if self.extra_debug:
					print("[%s] raw section above is from NIT other table." % self.debugName)
				network_id = section["header"]["network_id"]

				if network_id in nit_other_section_version and nit_other_section_version[network_id] == section["header"]["version_number"] and all(completed == True for completed in nit_other_completed.values()):
					all_nit_others_completed = True
				else:

					if network_id not in nit_other_section_version or section["header"]["version_number"] != nit_other_section_version[network_id]:
						nit_other_section_version[network_id] = section["header"]["version_number"]
						nit_other_sections_read[network_id] = []
						nit_other_content[network_id] = []
						nit_other_sections_count[network_id] = section["header"]["last_section_number"] + 1
						nit_other_completed[network_id] = False

					if section["header"]["section_number"] not in nit_other_sections_read[network_id]:
						nit_other_sections_read[network_id].append(section["header"]["section_number"])
						nit_other_content[network_id] += section["content"]

						if len(nit_other_sections_read[network_id]) == nit_other_sections_count[network_id]:
							nit_other_completed[network_id] = True

			elif self.extra_debug:
				print("[%s] raw section above skipped. Either duplicate output or ID mismatch.")

			if nit_current_completed and all_nit_others_completed:
				break

		dvbreader.close(fd)

		self.NITreadTime += time() - start_time

		nit_content = nit_current_content
		for network_id in nit_other_content:
			nit_content += nit_other_content[network_id]

		if self.extra_debug:
			for x in nit_content:
				print("[%s] NIT item:" % self.debugName, x)

		#transponders_tmp = [x for x in nit_content if "descriptor_tag" in x and x["descriptor_tag"] == self.descriptors["transponder"]]
		transponders_count = self.processTransponders([x for x in nit_content if "descriptor_tag" in x and x["descriptor_tag"] == self.descriptors["transponder"]])

		from Screens.Standby import inStandby
		if not inStandby:
			self["status"].setText(_("transponders found: %d") % transponders_count)

		self.tmp_service_list = [x for x in nit_content if "descriptor_tag" in x and x["descriptor_tag"] == self.descriptors["serviceList"]]
		
		# start: only for providers that store LCN in NIT (not for providers where LCN is stored in the BAT)
		LCNs = [x for x in nit_content if "descriptor_tag" in x and x["descriptor_tag"] == self.descriptors["lcn"]]
		if self.extra_debug:
			print("[%s][readNIT] LCNs" % self.debugName, LCNs)
		if LCNs:
			for LCN in LCNs:
				LCNkey = "%x:%x:%x" % (LCN["transport_stream_id"], LCN["original_network_id"], LCN["service_id"])

				if not self.ignore_visible_service_flag and "visible_service_flag" in LCN and LCN["visible_service_flag"] == 0:
					continue

				self.logical_channel_number_dict[LCNkey] = LCN
		# end: only for providers that store LCN in NIT (not for providers where LCN is stored in the BAT)

		if read_other_section and len(nit_other_completed):
			print("[%s] Added/Updated %d transponders with network_id = 0x%x and other network_ids = %s" % (self.debugName, transponders_count, nit_current_section_network_id, ','.join(map(hex, list(nit_other_completed.keys())))))
		else:
			print("[%s] Added/Updated %d transponders with network_id = 0x%x" % (self.debugName, transponders_count, nit_current_section_network_id))

		print("[%s] Reading NIT completed." % self.debugName)

		self.manager()

	def readBAT(self):
		print("[%s] Reading BAT..." % self.debugName)
		self.TSID_ONID_list = [] # as we are searching the bat delete any data that may have been downloaded from the nit

		self.setDemuxer()

		start_time = time()

		fd = dvbreader.open(self.demuxer_device, self.bat_pid, self.bat_table_id, 0xff, self.selectedNIM)
		if fd < 0:
			print("[%s] Cannot open the demuxer" % self.debugName)
			self.showError(_('Cannot open the demuxer'))
			return

		bat_section_version = -1
		bat_sections_read = []
		bat_sections_count = 0
		bat_content = []

		timeout = datetime.datetime.now()
		timeout += datetime.timedelta(0, self.TIMEOUT_BAT)

		while True:
			if datetime.datetime.now() > timeout:
				print("[%s] Timed out reading BAT" % self.debugName)
				break

			section = dvbreader.read_bat(fd, self.bat_table_id)
			if section is None:
				sleep(0.1)	# no data.. so we wait a bit
				continue

			if self.extra_debug:
				print("[%s] BAT raw section header" % self.debugName, section["header"])
				print("[%s] BAT raw section content" % self.debugName, section["content"])

			if section["header"]["table_id"] == self.bat_table_id:
				if section["header"]["bouquet_id"] != self.bat["BouquetID"]:
					continue

				if section["header"]["version_number"] != bat_section_version:
					bat_section_version = section["header"]["version_number"]
					bat_sections_read = []
					bat_content = []
					bat_sections_count = section["header"]["last_section_number"] + 1

				if section["header"]["section_number"] not in bat_sections_read:
					bat_sections_read.append(section["header"]["section_number"])
					bat_content += section["content"]

					if len(bat_sections_read) == bat_sections_count:
						break

		dvbreader.close(fd)

		self.BATreadTime += time() - start_time

		#self.tmp_bat_content = [x for x in bat_content if "descriptor_tag" in x and x["descriptor_tag"] == self.descriptors["lcn"]] # used before region code added below.
		
		self.tmp_bat_content = []
		for x in bat_content:
			if "descriptor_tag" in x and x["descriptor_tag"] == self.descriptors["lcn"]:
				if self.bat_region and "region_id" in x and x["region_id"] not in self.bat_region:
					continue # skip regions that don't match
				TSID_ONID_key = "%x:%x" % (x["transport_stream_id"], x["original_network_id"])
				if TSID_ONID_key not in self.TSID_ONID_list:
					self.TSID_ONID_list.append(TSID_ONID_key)
				self.tmp_bat_content.append(x)
		
		print("[%s] Reading BAT completed." % self.debugName)

		self.manager()

	def readSDT(self):
		print("[%s] Reading SDTs..." % self.debugName)
		
		start_time = time()
		
		self.setDemuxer()
		
		# 2 choices, just search SDT Actual (on all transponders), or search SDT Actual and SDT Other but only on the home transponder
		if self.sdt_only_scan_home: # include SDT Actual and SDT Other
			if self.sdt_other_table_id == 0x00:
				mask = 0xff
			else:
				mask = self.sdt_current_table_id ^ self.sdt_other_table_id ^ 0xff
			
			fd = dvbreader.open(self.demuxer_device, self.sdt_pid, self.sdt_current_table_id, mask, self.selectedNIM)
			if fd < 0:
				print("[%s] Cannot open the demuxer" % self.debugName)
				return None
	
			TSID_ONID_list = self.TSID_ONID_list[:]
			
			sdt_secions_status = {}
			for TSID_ONID in TSID_ONID_list:
				sdt_secions_status[TSID_ONID] = {}
				sdt_secions_status[TSID_ONID]["section_version"] = -1
				sdt_secions_status[TSID_ONID]["sections_read"] = []
				sdt_secions_status[TSID_ONID]["sections_count"] = 0
				sdt_secions_status[TSID_ONID]["content"] = []
	
			timeout = datetime.datetime.now()
			timeout += datetime.timedelta(0, self.TIMEOUT_SDT)
			while True:
				if datetime.datetime.now() > timeout:
					print("[%s] Timed out reading SDT" % self.debugName)
					break
	
				section = dvbreader.read_sdt(fd, self.sdt_current_table_id, self.sdt_other_table_id)
				if section is None:
					sleep(0.1)	# no data.. so we wait a bit
					continue
	
				if self.extra_debug:
					print("[%s] SDT raw section header" % self.debugName, section["header"])
					print("[%s] SDT raw section content" % self.debugName, section["content"])
	
				if (section["header"]["table_id"] == self.sdt_current_table_id or section["header"]["table_id"] == self.sdt_other_table_id) and len(section["content"]):
					TSID_ONID = "%x:%x" % (section["header"]["transport_stream_id"], section["header"]["original_network_id"])
					if TSID_ONID not in TSID_ONID_list:
						continue
	
					if section["header"]["version_number"] != sdt_secions_status[TSID_ONID]["section_version"]:
						sdt_secions_status[TSID_ONID]["section_version"] = section["header"]["version_number"]
						sdt_secions_status[TSID_ONID]["sections_read"] = []
						sdt_secions_status[TSID_ONID]["content"] = []
						sdt_secions_status[TSID_ONID]["sections_count"] = section["header"]["last_section_number"] + 1
	
					if section["header"]["section_number"] not in sdt_secions_status[TSID_ONID]["sections_read"]:
						sdt_secions_status[TSID_ONID]["sections_read"].append(section["header"]["section_number"])
						sdt_secions_status[TSID_ONID]["content"] += section["content"]
	
						if len(sdt_secions_status[TSID_ONID]["sections_read"]) == sdt_secions_status[TSID_ONID]["sections_count"]:
							TSID_ONID_list.remove(TSID_ONID)
	
				if len(TSID_ONID_list) == 0:
					break
	
			if len(TSID_ONID_list) > 0:
				print("[%s] Cannot fetch SDT for the following TSID_ONID list: " % self.debugName, TSID_ONID_list)
	
			dvbreader.close(fd)
			
			# Now throw the lot in one list so it matches the format handling below which is one single list.
			sdt_current_content = []
			for key in sdt_secions_status:
				sdt_current_content	+= sdt_secions_status[key]["content"]

		else: # only read SDT Actual (other transponders will be read in the tuning loop)

			mask = 0xff
			sdt_current_version_number = -1
			sdt_current_sections_read = []
			sdt_current_sections_count = 0
			sdt_current_content = []
			sdt_current_completed = False
	
			fd = dvbreader.open(self.demuxer_device, self.sdt_pid, self.sdt_current_table_id, mask, self.selectedNIM)
			if fd < 0:
				print("[%s][readSDT] Cannot open the demuxer" % self.debugName)
				self.showError(_('Cannot open the demuxer'))
				return
	
			timeout = datetime.datetime.now()
			timeout += datetime.timedelta(0, self.TIMEOUT_SDT)
	
			while True:
				if datetime.datetime.now() > timeout:
					print("[%s][readSDT] Timed out" % self.debugName)
					break
	
				section = dvbreader.read_sdt(fd, self.sdt_current_table_id, 0x00)
				if section is None:
					sleep(0.1)	# no data.. so we wait a bit
					continue
	
				if self.extra_debug:
					print("[%s] SDT raw section header" % self.debugName, section["header"])
					print("[%s] SDT raw section content" % self.debugName, section["content"])
	
				# Check the ONID is correct... maybe we are receiving the "wrong" satellite or dish is still moving.
				if self.transpondercurrent["original_network_id"] != section["header"]["original_network_id"]:
					continue
	
				# Check for ONID/TSID miss match between the transport stream we have tuned and the one we are supposed to tune.
				# A miss match happens when the NIT table on the home transponder has broken data.
				# If there is a miss match correct it now, before the data is "used in anger".
	#			if self.transpondercurrent["transport_stream_id"] != section["header"]["transport_stream_id"]:
	#				print("[%s] readSDT ONID/TSID mismatch. Supposed to be reading: 0x%x/0x%x, Currently reading: 0x%x/0x%x. Will accept current data as  authoritative." % (self.debugName, self.transpondercurrent["original_network_id"], self.transpondercurrent["transport_stream_id"], section["header"]["original_network_id"], section["header"]["transport_stream_id"]))
	#				self.transpondercurrent["real_transport_stream_id"] = section["header"]["transport_stream_id"]
	
				if section["header"]["table_id"] == self.sdt_current_table_id and not sdt_current_completed:
					if section["header"]["version_number"] != sdt_current_version_number:
						sdt_current_version_number = section["header"]["version_number"]
						sdt_current_sections_read = []
						sdt_current_sections_count = section["header"]["last_section_number"] + 1
						sdt_current_content = []
	
					if section["header"]["section_number"] not in sdt_current_sections_read:
						sdt_current_sections_read.append(section["header"]["section_number"])
						sdt_current_content += section["content"]
	
						if len(sdt_current_sections_read) == sdt_current_sections_count:
							sdt_current_completed = True
	
				if sdt_current_completed:
					break
	
			dvbreader.close(fd)
		# End: only read SDT Actual

		self.SDTsReadTime += time() - start_time

		if not sdt_current_content: # if no channels in SDT just skip the transponder read. No need to abort the complete scan.
			print("[%s][readSDT] no services found on transponder" % self.debugName)
			self.manager()
			return

		namespace = self.SDTscanList[self.index - self.actionsListOrigLength]["namespace"] # this is corrected namespace after any resync from satellites.xml, (with subnet applied if so coonfigured or applicable)
		for i in range(len(sdt_current_content)):
			service = sdt_current_content[i]

			if service["service_type"] not in self.VIDEO_ALLOWED_TYPES and service["service_type"] not in self.AUDIO_ALLOWED_TYPES:
				continue

			service["flags"] = 0
			service["namespace"] = namespace

			if service["service_type"] in self.VIDEO_ALLOWED_TYPES:
				self.video_services += 1
			else:
				self.radio_services += 1

			servicekey = "%x:%x:%x" % (service["transport_stream_id"], service["original_network_id"], service["service_id"])
			self.tmp_services_dict[servicekey] = service

		self.manager()

	def processBAT(self):
		self.logical_channel_number_dict = {} # start clean (in theory should be empty but who knows what was in the NIT)
		if self.extra_debug:
			lcn_list = []
			sid_list = []
			tsid_list = []

		for service in self.tmp_bat_content:
			if not self.ignore_visible_service_flag and "visible_service_flag" in service and service["visible_service_flag"] == 0:
				continue

			key = "%x:%x:%x" % (service["transport_stream_id"], service["original_network_id"], service["service_id"])
			self.logical_channel_number_dict[key] = service

			if self.extra_debug:
				print("[%s] LCN entry" % self.debugName, key, service)
				sid_list.append(service["service_id"])
				lcn_list.append(service["logical_channel_number"])
				if service["transport_stream_id"] not in tsid_list:
					tsid_list.append(service["transport_stream_id"])

		if self.extra_debug:
			print("[%s] TSID list from BAT" % self.debugName, sorted(tsid_list))
			print("[%s] SID list from BAT" % self.debugName, sorted(sid_list))
			print("[%s] LCN list from BAT" % self.debugName, sorted(lcn_list))

	def correctTsidErrors(self):
		# I wish this was not necessary but SI tables contain errors
		errors_dict = {}
		tmp_service_list = []
		SDTscanList = []
		tmp_bat_content = []
		for tp in self.SDTscanList:
			if "real_transport_stream_id" in tp:
				key = "%x:%x" % (tp["transport_stream_id"], tp["original_network_id"])
				errors_dict[key] = tp["real_transport_stream_id"]
				tp["transport_stream_id"] = tp["real_transport_stream_id"]
				del tp["real_transport_stream_id"]
			SDTscanList.append(tp)
		self.SDTscanList = SDTscanList
		if self.extra_debug:
			print("[%s] errors_dict" % self.debugName, errors_dict)

		for service in self.tmp_service_list:
			key = "%x:%x" % (service["transport_stream_id"], service["original_network_id"])
			if key in errors_dict:
				service["transport_stream_id"] = errors_dict[key]
			tmp_service_list.append(service)
		self.tmp_service_list = tmp_service_list

		for service in self.tmp_bat_content:
			key = "%x:%x" % (service["transport_stream_id"], service["original_network_id"])
			if key in errors_dict:
				service["transport_stream_id"] = errors_dict[key]
			tmp_bat_content.append(service)
		self.tmp_bat_content = tmp_bat_content

	def processTransponders(self, transponderList):
		transponders_count = 0
		self.TSID_ONID_list = [] # so we know what to look for in the SDT when we are looking for SDT Other
		for transponder in transponderList:
			transponder["dvb_type"] = "dvbs" # so we know how to format it
			transponder["orbital_position"] = self.getOrbPosFromBCD(transponder)
			if not nimmanager.getNimListForSat(transponder["orbital_position"]): # Don't waste effort trying to scan or import from not configured satellites.
				if self.extra_debug:
					print("[%s] Skipping transponder as it is on a not configured satellite:" % self.debugName, transponder)
				continue
			TSID_ONID_key = "%x:%x" % (transponder["transport_stream_id"], transponder["original_network_id"])
			if TSID_ONID_key not in self.TSID_ONID_list:
				self.TSID_ONID_list.append(TSID_ONID_key)
			transponder["flags"] = 0
			transponder["frequency"] = int(round(transponder["frequency"]*10, -3)) # Number will be five digits according to SI output, plus 3 trailing zeros. This is the same format used in satellites.xml.
			transponder["symbol_rate"] = int(round(transponder["symbol_rate"]*100, -3))
			if transponder["fec_inner"] != eDVBFrontendParametersSatellite.FEC_None and transponder["fec_inner"] > eDVBFrontendParametersSatellite.FEC_9_10:
				transponder["fec_inner"] = eDVBFrontendParametersSatellite.FEC_Auto
			transponder["inversion"] = eDVBFrontendParametersSatellite.Inversion_Unknown
			transponder["namespace"] = self.buildNamespace(transponder)
			transponder["pilot"] = eDVBFrontendParametersSatellite.Pilot_Unknown

			if self.config.sync_with_known_tps.value:
				transponder = self.syncTransponder(transponder)

			transponders_count += 1

			if self.extra_debug:
				print("[%s] transponder" % self.debugName, transponder)

			self.SDTscanList.append(transponder)
			if not self.sdt_only_scan_home or "read SDTs" not in self.actionsList: # If we are only scanning home only enter this once... otherwise enter it for all transponders.
				self.actionsList.append("read SDTs") # Adds new task to actions list to scan SDT of this transponder.

		# Sort the transponder scan list.
		# step one: put the home transponder at the start of the list so no retune is required.
		# step two: next scan other transponders on the same satellite as home transponder.
		# step three: sort by orbital position so the dish doesn't need to keep going backwards and forwards unnecessarilly.
		# step four: cosmetic, sort by frequency.
		# Note: negation is needed because the sort is ascending and False has a lower value than True.
		self.SDTscanList.sort(key=lambda transponder: (not (self.homeTransponder["orbital_position"] == transponder["orbital_position"] and self.homeTransponder["frequency"] == transponder["frequency"] and self.homeTransponder["polarization"] == transponder["polarization"]), not (self.homeTransponder["orbital_position"] == transponder["orbital_position"]), transponder["orbital_position"], transponder["frequency"]))
		if self.extra_debug:
			for tp in self.SDTscanList:
				print("[%s] transponder scan list sorted, %s  %d %s" % (self.debugName, self.getOrbPosHuman(tp["orbital_position"]), tp["frequency"], self.polarization_dict.get(tp["polarization"], "UNKNOWN")))
		self.progresscount += transponders_count

		from Screens.Standby import inStandby
		if not inStandby:
			self["progress_text"].range = self.progresscount
			self["progress_text"].value = self.progresscurrent
			self["progress"].setRange((0, self.progresscount))
			self["progress"].setValue(self.progresscurrent)

		return transponders_count

	def fixServiceNames(self):
		from .servicenames import ServiceNames
		for servicekey in list(ServiceNames.keys()):
			if servicekey in self.tmp_services_dict:
				self.tmp_services_dict[servicekey]["service_name"] = ServiceNames[servicekey]

	def addServicesToTransponders(self):
		servicekeys = list(self.tmp_services_dict.keys())
		for servicekey in servicekeys:
			tpkey = "%x:%x:%x" % (self.tmp_services_dict[servicekey]["namespace"], self.tmp_services_dict[servicekey]["transport_stream_id"], self.tmp_services_dict[servicekey]["original_network_id"])
			if tpkey not in self.transponders_dict: # Can this really happen?
				print("[%s] tpkey not in self.transponders_dict" % self.debugName, self.tmp_services_dict[servicekey])
				del self.tmp_services_dict[servicekey]
				continue
			if "services" not in self.transponders_dict[tpkey]: # create a services dict on the transponder if one does not currently exist
				self.transponders_dict[tpkey]["services"] = {}
			# The original (correct) code
			# self.transponders_dict[tpkey]["services"][self.tmp_services_dict[servicekey]["service_id"]] = self.tmp_services_dict[servicekey]
			
			# Dirty hack to work around the (well known) service type bug in lamedb/enigma2
			self.transponders_dict[tpkey]["services"]["%x:%x" % (self.tmp_services_dict[servicekey]["service_type"], self.tmp_services_dict[servicekey]["service_id"])] = self.tmp_services_dict[servicekey]

	def addLCNsToServices(self):
		servicekeys = list(self.tmp_services_dict.keys())
		for servicekey in servicekeys:
			if servicekey in self.logical_channel_number_dict and self.logical_channel_number_dict[servicekey]["logical_channel_number"] not in self.services_dict:
				self.tmp_services_dict[servicekey]["logical_channel_number"] = self.logical_channel_number_dict[servicekey]["logical_channel_number"] # adds LCN to the service
				self.services_dict[self.logical_channel_number_dict[servicekey]["logical_channel_number"]] = self.tmp_services_dict[servicekey] # queues service for adding to bouquet file

		if self.extra_debug:
			for key in self.dict_sorter(self.tmp_services_dict, "service_name"): # prints service list in alphabetical order
				print("[%s] service-alpha-order" % self.debugName, key, self.tmp_services_dict[key])

			for key in self.dict_sorter(self.tmp_services_dict, "logical_channel_number"): # prints service list in LCN order
				print("[%s] service-LCN-order" % self.debugName, key, self.tmp_services_dict[key])

	def dict_sorter(self, in_dict, sort_by):
		sort_list = [(x[0], x[1][sort_by]) for x in list(in_dict.items())]
		return [x[0] for x in sorted(sort_list, key=lambda listItem: listItem[1])]

	def buildNamespace(self, transponder):
		namespace = transponder['orbital_position'] << 16
		if self.namespace_complete or not self.isValidOnidTsid(transponder):
			namespace |= ((transponder['frequency'] / 1000) & 0xFFFF) | ((transponder['polarization'] & 1) << 15)
		return namespace

	def addTransponders(self):
		for transponder in self.SDTscanList:
			key = "%x:%x:%x" % (transponder["namespace"],
				transponder["transport_stream_id"],
				transponder["original_network_id"])

			if key in self.transponders_dict:
				if "services" not in self.transponders_dict[key]: # sanity
					self.transponders_dict[key]["services"] = {}
				transponder["services"] = self.transponders_dict[key]["services"]
			self.transponders_dict[key] = transponder

	def syncTransponder(self, transponder):
		# this allows us to sync with data in satellites.xml to avoid crap data in broken SI tables
		tolerance = 5
		multiplier = 1000
		nameToIndex = {"frequency": 1, "symbol_rate": 2, "polarization": 3, "fec_inner": 4, "system": 5, "modulation": 6}
		tpList = nimmanager.getTransponders(transponder["orbital_position"]) # this data comes from satellites.xml
		for knownTransponder in tpList:
			if (knownTransponder[nameToIndex["polarization"]] % 2) == (transponder["polarization"] % 2) and \
				abs(knownTransponder[nameToIndex["frequency"]] - transponder["frequency"]) < (tolerance*multiplier) and \
				abs(knownTransponder[nameToIndex["symbol_rate"]] - transponder["symbol_rate"]) < (tolerance*multiplier):
				transponder["frequency"] = knownTransponder[nameToIndex["frequency"]]
				transponder["polarization"] = knownTransponder[nameToIndex["polarization"]]
				transponder["symbol_rate"] = knownTransponder[nameToIndex["symbol_rate"]]
				transponder["fec_inner"] = knownTransponder[nameToIndex["fec_inner"]]
				transponder["system"] = knownTransponder[nameToIndex["system"]]
				transponder["modulation"] = knownTransponder[nameToIndex["modulation"]]
				return transponder

		# nothing found so we make it a bit looser
		for knownTransponder in tpList:
			if (knownTransponder[nameToIndex["polarization"]] % 2) == (transponder["polarization"] % 2) and \
				abs(knownTransponder[nameToIndex["frequency"]] - transponder["frequency"]) < (tolerance*multiplier):
				transponder["frequency"] = knownTransponder[nameToIndex["frequency"]]
				transponder["polarization"] = knownTransponder[nameToIndex["polarization"]]
				transponder["symbol_rate"] = knownTransponder[nameToIndex["symbol_rate"]]
				transponder["fec_inner"] = knownTransponder[nameToIndex["fec_inner"]]
				transponder["system"] = knownTransponder[nameToIndex["system"]]
				transponder["modulation"] = knownTransponder[nameToIndex["modulation"]]
				return transponder

		return transponder

	def readBouquetIndex(self):
		try:
			return open(self.path + "/" + self.bouquetsIndexFilename, "r").read()
		except Exception as e:
			return ""

	def handleBouquetIndex(self):
		newBouquetIndexContent = bouquetIndexContent = self.readBouquetIndex()
		if '"' + self.bouquetFilename + '"' not in bouquetIndexContent: # only edit the index if bouquet file is not present
			bouquets_tv_list = []
			bouquets_tv_list.append("#NAME Bouquets (TV)\n")
			bouquets_tv_list.append("#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET \"%s\" ORDER BY bouquet\n" % self.bouquetFilename)
			if bouquetIndexContent: # if bouquet index not empty
				lines = bouquetIndexContent.split("\n", 1)
				if lines[0][:6] != "#NAME ":
					bouquets_tv_list.append("%s\n" % lines[0])
				if len(lines) > 1:
					bouquets_tv_list.append("%s" % lines[1])
			newBouquetIndexContent = ''.join(bouquets_tv_list)

		if '"' + self.lastScannnedBouquetFilename + '"' not in bouquetIndexContent: # check if LasScanned bouquet is present in the index
			newBouquetIndexContent += "#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET \"%s\" ORDER BY bouquet\n" % self.lastScannnedBouquetFilename

		if bouquetIndexContent != newBouquetIndexContent:
			with open(self.path + "/" + self.bouquetsIndexFilename, "w") as bouquets_tv:
				bouquets_tv.write(newBouquetIndexContent)

	def writeBouquet(self):
		bouquet_list = []
		bouquet_list.append("#NAME %s\n" % self.bouquetName)

		numbers = list(range(1, 1001))
		for number in numbers:
			if number in self.services_dict:
				bouquet_list.append(self.bouquetServiceLine(self.services_dict[number]))
			else:
				bouquet_list.append(self.spacer())

		with open(self.path + "/" + self.bouquetFilename, "w") as bouquetFile:
			bouquetFile.write(''.join(bouquet_list))

	def writeLastScannedBouquet(self):
		last_scanned_bouquet_list = ["#NAME " + _("Last Scanned") + "\n"]
		sort_list = []
		avoid_duplicates = []
		for key in list(self.tmp_services_dict.keys()):
			service = self.tmp_services_dict[key]
			# sort flat, alphabetic before numbers
			ref = "%x:%x:%x:%x" % (
				service["service_id"],
				service["transport_stream_id"],
				service["original_network_id"],
				service["namespace"]
				)
			if ref in avoid_duplicates:
				continue
			avoid_duplicates.append(ref)
			sort_list.append((key, re.sub('^(?![a-z])', 'zzzzz', self.cleanServiceName(service["service_name"]).lower()), service["service_type"] not in self.VIDEO_ALLOWED_TYPES))
		sort_list = [x[0] for x in sorted(sort_list, key=lambda listItem: (listItem[2], listItem[1]))] # listItem[2] puts radio channels second.
		for key in sort_list:
			service = self.tmp_services_dict[key]
			last_scanned_bouquet_list.append(self.bouquetServiceLine(service))
		print("[%s] Writing Last Scanned bouquet..." % self.debugName)
		with open(self.path + "/" + self.lastScannnedBouquetFilename, "w") as bouquet_current:
			bouquet_current.write(''.join(last_scanned_bouquet_list))

	def bouquetServiceLine(self, service):
		return "#SERVICE 1:0:%x:%x:%x:%x:%x:0:0:0:\n%s" % (
			service["service_type"],
			service["service_id"],
			service["transport_stream_id"],
			service["original_network_id"],
			service["namespace"],
			(("#DESCRIPTION %s\n" % self.cleanServiceName(service["service_name"])) if self.config.force_service_name.value else ""))

	def spacer(self):
		return "#SERVICE 1:320:0:0:0:0:0:0:0:0:\n#DESCRIPTION  \n"

	def cleanServiceName(self, text):
		control_chars = ''.join(map(chr, list(range(0,32)) + list(range(127,160))))
		control_char_re = re.compile('[%s]' % re.escape(control_chars))
		if six.PY2:
			return control_char_re.sub('', text).decode('latin-1').encode("utf8")
		return control_char_re.sub('', text)

	def createBouquet(self):
		self.handleBouquetIndex()
		self.writeBouquet()
		self.writeLastScannedBouquet()

	def saveLamedb(self):
		writer = LamedbWriter()
		writer.writeLamedb(self.path, self.transponders_dict)
		writer.writeLamedb5(self.path, self.transponders_dict)

	def reloadSettingsAndClose(self):
		from Screens.Standby import inStandby
		self.releaseFrontend()
		self.restartService()

		eDVBDB.getInstance().reloadServicelist()
		eDVBDB.getInstance().reloadBouquets()
		self.progresscurrent += 1
		if not inStandby:
			self["progress_text"].value = self.progresscurrent
			self["progress"].setValue(self.progresscurrent)
			self["action"].setText(_('Done'))
			self["status"].setText(_("Services: %d video - %d radio") % (self.video_services, self.radio_services))

		self.printStats()

		print("[%s] Scan successfully completed" % self.debugName)

		self.timer = eTimer()
		self.timer.callback.append(self.scanCompletedSuccessfully)
		self.timer.start(2000, 1)

	def scanCompletedSuccessfully(self):
		self.close(True)

	def printStats(self):
		total_time = time() - self.run_start_time
		print("[%s] time tuning %.2f" % (self.debugName, self.tuningTime))
		print("[%s] time reading NIT %.2f" % (self.debugName, self.NITreadTime))
		print("[%s] time reading BAT %.2f" % (self.debugName, self.BATreadTime))
		print("[%s] time reading SDTs on %d transponders %.2f" % (self.debugName, len(self.SDTscanList), self.SDTsReadTime))
		print("[%s] time processing %.2f" % (self.debugName, total_time - (self.tuningTime + self.NITreadTime + self.BATreadTime + self.SDTsReadTime)))
		print("[%s] total run time %.2f" % (self.debugName, total_time))


	def isValidOnidTsid(self, transponder):
		return transponder["original_network_id"] != 0x0 and transponder["original_network_id"] < 0xff00

	def getOrbPosFromBCD(self, transponder):
		# convert 4 bit BCD (binary coded decimal)
		# west_east_flag, 0 == west, 1 == east
		op = 0
		bits = 4
		bcd = transponder["orbital_position"]
		for i in range(bits):
			op += ((bcd >> 4*i) & 0x0F) * 10**i
		return op and not transponder["west_east_flag"] and 3600 - op or op

	def getOrbPosHuman(self, op):
		return "%0.1f%s" % (((3600 - op)/10.0, "W") if op > 1800 else (op/10.0, "E"))

	def setDemuxer(self):
		self.demuxer_device = "/dev/dvb/adapter%d/demux%d" % (self.adapter, self.demuxer_id)
		print("[%s] Demuxer %d" % (self.debugName, self.demuxer_id))

	def setParams(self):
		params = eDVBFrontendParametersSatellite()
		params.frequency = self.transpondercurrent["frequency"]
		params.symbol_rate = self.transpondercurrent["symbol_rate"]
		params.polarisation = self.transpondercurrent["polarization"]
		params.fec = self.transpondercurrent["fec_inner"]
		params.inversion = eDVBFrontendParametersSatellite.Inversion_Unknown
		params.orbital_position = self.transpondercurrent["orbital_position"]
		params.system = self.transpondercurrent["system"]
		params.modulation = self.transpondercurrent["modulation"]
		params.rolloff = self.transpondercurrent["roll_off"]
		params.pilot = eDVBFrontendParametersSatellite.Pilot_Unknown
		if hasattr(eDVBFrontendParametersSatellite, "No_Stream_Id_Filter"):
			params.is_id = eDVBFrontendParametersSatellite.No_Stream_Id_Filter
		if hasattr(eDVBFrontendParametersSatellite, "PLS_Gold"):
			params.pls_mode = eDVBFrontendParametersSatellite.PLS_Gold
		if hasattr(eDVBFrontendParametersSatellite, "PLS_Default_Gold_Code"):
			params.pls_code = eDVBFrontendParametersSatellite.PLS_Default_Gold_Code
		if hasattr(eDVBFrontendParametersSatellite, "No_T2MI_PLP_Id"):
			params.t2mi_plp_id = eDVBFrontendParametersSatellite.No_T2MI_PLP_Id
		if hasattr(eDVBFrontendParametersSatellite, "T2MI_Default_Pid"):
			params.t2mi_pid = eDVBFrontendParametersSatellite.T2MI_Default_Pid
		return params

	def showError(self, message):
		from Screens.Standby import inStandby
		self.releaseFrontend()
		self.restartService()
		if not inStandby:
			question = self.session.open(MessageBox, message, MessageBox.TYPE_ERROR)
			question.setTitle(self.screentitle)
		self.close()

	def keyCancel(self):
		self.releaseFrontend()
		self.restartService()
		self.close()

	def releaseFrontend(self):
		if hasattr(self, 'frontend'):
			del self.frontend
		if hasattr(self, 'rawchannel'):
			del self.rawchannel
		self.frontend = None
		self.rawchannel = None

	def restartService(self):
		if self.postScanService:
			self.session.nav.playService(self.postScanService)
			self.postScanService = None

	def isRotorSat(self, slot, orb_pos):
		rotorSatsForNim = nimmanager.getRotorSatListForNim(slot)
		if len(rotorSatsForNim) > 0:
			for sat in rotorSatsForNim:
				if sat[0] == orb_pos:
					return True
		return False


class SatScanLcn_Setup(ConfigListScreen, Screen):
	def __init__(self, session, args = None):
		Screen.__init__(self, session)
		self.setup_title = _('SatScanLcn') + " - " + _('Setup')
		Screen.setTitle(self, self.setup_title)
		self.skinName = ["SatScanLcn_Setup", "Setup"]
		self.config = config.plugins.satscanlcn
		self.onChangedEntry = []
		self.session = session
		ConfigListScreen.__init__(self, [], session = session, on_change = self.changedEntry)

		self["actions2"] = ActionMap(["SetupActions", "ColorActions"],
		{
			"ok": self.keyOk,
			"menu": self.keyCancel,
			"cancel": self.keyCancel,
			"save": self.keySave,
			"red": self.keyCancel,
			"green": self.keySave,
			"yellow": self.keyGo,
			"blue": self.keyAbout
		}, -2)

		self["key_red"] = StaticText(_("Exit"))
		self["key_green"] = StaticText(_("Save"))
		self["key_yellow"] = StaticText(_("Download"))
		self["key_blue"] = StaticText(_("About"))

		self["description"] = Label("")

		self.showAdvancedOptions = ConfigYesNo(default = False)

		self.createSetup()

		if not self.selectionChanged in self["config"].onSelectionChanged:
			self["config"].onSelectionChanged.append(self.selectionChanged)
		self.selectionChanged()

	def createSetup(self):
		indent = "- "
		self.list = []

		self.list.append(getConfigListEntry(_("Provider"), self.config.provider, _('Select the provider you wish to scan.')))
		self.list.append(getConfigListEntry(_("Scheduled fetch"), self.config.schedule, _("Set up a task scheduler to periodically update data.")))
		if self.config.schedule.value:
			self.list.append(getConfigListEntry(indent + _("Schedule time of day"), self.config.scheduletime, _("Set the time of day to run SatScanLcn.")))
			self.list.append(getConfigListEntry(indent + _("Schedule days of the week"), self.config.dayscreen, _("Press OK to select which days to run SatScanLcn.")))
			self.list.append(getConfigListEntry(indent + _("Schedule wake from deep standby"), self.config.schedulewakefromdeep, _("If the receiver is in 'Deep Standby' when the schedule is due wake it up to run SatScanLcn.")))
			if self.config.schedulewakefromdeep.value:
				self.list.append(getConfigListEntry(indent + _("Schedule return to deep standby"), self.config.scheduleshutdown, _("If the receiver was woken from 'Deep Standby' and is currently in 'Standby' and no recordings are in progress return it to 'Deep Standby' once the import has completed.")))
		self.list.append(getConfigListEntry(_("Show advanced options"), self.showAdvancedOptions, _("Select yes to access advanced setup options.")))
		if self.showAdvancedOptions.value:
			self.list.append(getConfigListEntry(indent + _("Force channel name"), self.config.force_service_name, _("Switch this on only if you have issues with \"N/A\" appearing in your channel list. Switching this on means the channel name will not auto update if the broadcaster changes the channel name.")))
			self.list.append(getConfigListEntry(indent + _("Sync with known transponders"), self.config.sync_with_known_tps, _('CAUTION: Sometimes the SI tables contain rogue data. Select "yes" to sync with transponder data listed in satellites.xml. Select "no" if you trust the SI data. Default is "no". Only change this if you understand why you are doing it.')))
			self.list.append(getConfigListEntry(indent + _("Show in extensions menu"), self.config.extensions, _('When enabled, this allows you start a SatScanLcn update from the extensions list.')))
			self.list.append(getConfigListEntry(indent + _("Extra debug"), self.config.extra_debug, _("CAUTION: This feature is for development only. Requires debug logs to be enabled or enigma2 to be started in console mode (at debug level 4).")))



		self["config"].list = self.list
		self["config"].l.setList(self.list)

	def keyOk(self):
		if self["config"].getCurrent() and len(self["config"].getCurrent()) > 1 and self["config"].getCurrent()[1] == self.config.dayscreen:
			self.session.open(DaysScreen)
		else:
			self.keySave()

	def keyCancel(self):
		if self["config"].isChanged():
			self.session.openWithCallback(self.cancelCallback, MessageBox, _("Really close without saving settings?"))
		else:
			self.cancelCallback(True)

	def cancelCallback(self, answer):
		if answer:
			for x in self["config"].list:
				x[1].cancel()
			self.close(False)

	def keySave(self):
		self.saveAll()
		self["description"].setText(_("The current configuration has been saved.") + (self.scheduleInfo and " " + _("Next scheduled fetch is programmed for %s.") % self.scheduleInfo + " " or " "))

	def keyGo(self):
		self.saveAll()
		self.startDownload()

	def startDownload(self):
		print("[SatScanLcn] startDownload")
		self.session.openWithCallback(self.close, SatScanLcn, {})

	def satscanlcnCallback(self, answer=None):
		if answer:
			self.close(True)

	def keyAbout(self):
		self.session.open(SatScanLcn_About)

	def selectionChanged(self):
		self["description"].setText(self.getCurrentDescription()) #self["description"].setText(self["config"].getCurrent()[2])

	# for summary:
	def changedEntry(self):
		for x in self.onChangedEntry:
			x()
		if self["config"].getCurrent() and len(self["config"].getCurrent()) > 1 and self["config"].getCurrent()[1] in (self.config.schedule, self.config.schedulewakefromdeep, self.showAdvancedOptions):
			self.createSetup()

	def getCurrentEntry(self):
		return self["config"].getCurrent()[0]

	def getCurrentValue(self):
		return str(self["config"].getCurrent()[1].getText())

	def createSummary(self):
		from Screens.Setup import SetupSummary
		return SetupSummary
	# end: for summary

	def saveAll(self):
		for x in self["config"].list:
			x[1].save()

		configfile.save()
		try:
			self.scheduleInfo = AutoScheduleTimer.instance.doneConfiguring()
		except AttributeError as e:
			print("[SatScanLcn] Timer.instance not available for reconfigure.", e)
			self.scheduleInfo = ""


class DaysScreen(ConfigListScreen, Screen):
	def __init__(self, session, args = 0):
		self.session = session
		Screen.__init__(self, session)
		Screen.setTitle(self, _('SatScanLcn') + " - " + _("Select days"))
		self.skinName = ["Setup"]
		self.config = config.plugins.satscanlcn
		self.list = []
		days = (_("Monday"), _("Tuesday"), _("Wednesday"), _("Thursday"), _("Friday"), _("Saturday"), _("Sunday"))
		for i in sorted(self.config.days.keys()):
			self.list.append(getConfigListEntry(days[i], self.config.days[i]))
		ConfigListScreen.__init__(self, self.list)
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["setupActions"] = ActionMap(["SetupActions", "ColorActions"],
		{
			"red": self.keyCancel,
			"green": self.keySave,
			"save": self.keySave,
			"cancel": self.keyCancel,
			"ok": self.keySave,
		}, -2)

	def keySave(self):
		if not any([self.config.days[i].value for i in self.config.days]):
			info = self.session.open(MessageBox, _("At least one day of the week must be selected"), MessageBox.TYPE_ERROR, timeout = 30)
			info.setTitle(_('SatScanLcn') + " - " + _("Select days"))
			return
		for x in self["config"].list:
			x[1].save()
		self.close()

	def keyCancel(self):
		if self["config"].isChanged():
			self.session.openWithCallback(self.cancelCallback, MessageBox, _("Really close without saving settings?"))
		else:
			self.cancelCallback(True)

	def cancelCallback(self, answer):
		if answer:
			for x in self["config"].list:
				x[1].cancel()
			self.close(False)


autoScheduleTimer = None
def Scheduleautostart(reason, session=None, **kwargs):
	#
	# This gets called twice at start up, once by WHERE_AUTOSTART without session,
	# and once by WHERE_SESSIONSTART with session. WHERE_AUTOSTART is needed though
	# as it is used to wake from deep standby. We need to read from session so if
	# session is not set just return and wait for the second call to this function.
	#
	# Called with reason=1 during /sbin/shutdown.sysvinit, and with reason=0 at startup.
	# Called with reason=1 only happens when using WHERE_AUTOSTART.
	# If only using WHERE_SESSIONSTART there is no call to this function on shutdown.
	#
	schedulename = "SatScanLcn-Scheduler"
	configname = config.plugins.satscanlcn
	
	print("[%s][Scheduleautostart] reason(%d), session" % (schedulename, reason), session)
	if reason == 0 and session is None:
		return
	global autoScheduleTimer
	global wasScheduleTimerWakeup
	wasScheduleTimerWakeup = False
	if reason == 0:
		# check if box was woken up by a timer, if so, check if this plugin set this timer. This is not conclusive.
		wasScheduleTimerWakeup = session.nav.wasTimerWakeup() and configname.schedule.value and configname.schedulewakefromdeep.value and abs(configname.nextscheduletime.value - time()) <= 450
		if wasScheduleTimerWakeup:
			# if box is not in standby do it now
			from Screens.Standby import Standby, inStandby
			if not inStandby:
				# hack alert: session requires "pipshown" to avoid a crash in standby.py
				if not hasattr(session, "pipshown"):
					session.pipshown = False
				from Tools import Notifications
				Notifications.AddNotificationWithID("Standby", Standby)

		print("[%s][Scheduleautostart] AutoStart Enabled" % schedulename)
		if autoScheduleTimer is None:
			autoScheduleTimer = AutoScheduleTimer(session)
	else:
		print("[%s][Scheduleautostart] Stop" % schedulename)
		if autoScheduleTimer is not None:
			autoScheduleTimer.schedulestop()

class AutoScheduleTimer:
	instance = None
	def __init__(self, session):
		self.schedulename = "SatScanLcn-Scheduler"
		self.config = config.plugins.satscanlcn
		self.itemtorun = SatScanLcn
		self.session = session
		self.scheduletimer = eTimer()
		self.scheduletimer.callback.append(self.ScheduleonTimer)
		self.scheduleactivityTimer = eTimer()
		self.scheduleactivityTimer.timeout.get().append(self.scheduledatedelay)
		self.ScheduleTime = 0
		now = int(time())
		if self.config.schedule.value:
			print("[%s][AutoScheduleTimer] Schedule Enabled at " % self.schedulename, strftime("%c", localtime(now)))
			if now > 1546300800: # Tuesday, January 1, 2019 12:00:00 AM
				self.scheduledate()
			else:
				print("[%s][AutoScheduleTimer] STB clock not yet set." % self.schedulename)
				self.scheduleactivityTimer.start(36000)
		else:
			print("[%s][AutoScheduleTimer] Schedule Disabled at" % self.schedulename, strftime("%c", localtime(now)))
			self.scheduleactivityTimer.stop()

		assert AutoScheduleTimer.instance is None, "class AutoScheduleTimer is a singleton class and just one instance of this class is allowed!"
		AutoScheduleTimer.instance = self

	def __onClose(self):
		AutoScheduleTimer.instance = None

	def scheduledatedelay(self):
		self.scheduleactivityTimer.stop()
		self.scheduledate()

	def getScheduleTime(self):
		now = localtime(time())
		return int(mktime((now.tm_year, now.tm_mon, now.tm_mday, self.config.scheduletime.value[0], self.config.scheduletime.value[1], 0, now.tm_wday, now.tm_yday, now.tm_isdst)))

	def getScheduleDayOfWeek(self):
		today = self.getToday()
		for i in range(1, 8):
			if self.config.days[(today+i)%7].value:
				return i

	def getToday(self):
		return localtime(time()).tm_wday

	def scheduledate(self, atLeast = 0):
		self.scheduletimer.stop()
		self.ScheduleTime = self.getScheduleTime()
		now = int(time())
		if self.ScheduleTime > 0:
			if self.ScheduleTime < now + atLeast:
				self.ScheduleTime += 86400*self.getScheduleDayOfWeek()
			elif not self.config.days[self.getToday()].value:
				self.ScheduleTime += 86400*self.getScheduleDayOfWeek()
			next = self.ScheduleTime - now
			self.scheduletimer.startLongTimer(next)
		else:
			self.ScheduleTime = -1
		print("[%s][scheduledate] Time set to" % self.schedulename, strftime("%c", localtime(self.ScheduleTime)), strftime("(now=%c)", localtime(now)))
		self.config.nextscheduletime.value = self.ScheduleTime
		self.config.nextscheduletime.save()
		configfile.save()
		return self.ScheduleTime

	def schedulestop(self):
		self.scheduletimer.stop()

	def ScheduleonTimer(self):
		self.scheduletimer.stop()
		now = int(time())
		wake = self.getScheduleTime()
		atLeast = 0
		if wake - now < 60:
			atLeast = 60
			print("[%s][ScheduleonTimer] onTimer occured at" % self.schedulename, strftime("%c", localtime(now)))
			from Screens.Standby import inStandby
			if not inStandby:
				message = _("%s update is about to start.\nDo you want to allow this?") % self.schedulename
				ybox = self.session.openWithCallback(self.doSchedule, MessageBox, message, MessageBox.TYPE_YESNO, timeout = 30)
				ybox.setTitle(_('%s scheduled update') % self.schedulename)
			else:
				self.doSchedule(True)
		self.scheduledate(atLeast)

	def doSchedule(self, answer):
		now = int(time())
		if answer is False:
			if self.config.retrycount.value < 2:
				print("[%s][doSchedule] Schedule delayed." % self.schedulename)
				self.config.retrycount.value += 1
				self.ScheduleTime = now + (int(self.config.retry.value) * 60)
				print("[%s][doSchedule] Time now set to" % self.schedulename, strftime("%c", localtime(self.ScheduleTime)), strftime("(now=%c)", localtime(now)))
				self.scheduletimer.startLongTimer(int(self.config.retry.value) * 60)
			else:
				atLeast = 60
				print("[%s][doSchedule] Enough Retries, delaying till next schedule." % self.schedulename, strftime("%c", localtime(now)))
				self.session.open(MessageBox, _("Enough Retries, delaying till next schedule."), MessageBox.TYPE_INFO, timeout = 10)
				self.config.retrycount.value = 0
				self.scheduledate(atLeast)
		else:
			self.timer = eTimer()
			self.timer.callback.append(self.runscheduleditem)
			print("[%s][doSchedule] Running Schedule" % self.schedulename, strftime("%c", localtime(now)))
			self.timer.start(100, 1)

	def runscheduleditem(self):
		self.session.openWithCallback(self.runscheduleditemCallback, self.itemtorun)

	def runscheduleditemCallback(self, answer=None):
		global wasScheduleTimerWakeup
		from Screens.Standby import Standby, inStandby, TryQuitMainloop, inTryQuitMainloop
		print("[%s][runscheduleditemCallback] inStandby" % self.schedulename, inStandby)
		if wasScheduleTimerWakeup and inStandby and self.config.scheduleshutdown.value and not self.session.nav.getRecordings() and not inTryQuitMainloop:
			print("[%s] Returning to deep standby after scheduled wakeup" % self.schedulename)
			self.session.open(TryQuitMainloop, 1)
		wasScheduleTimerWakeup = False # clear this as any subsequent run will not be from wake up from deep

	def doneConfiguring(self): # called from plugin on save
		now = int(time())
		if self.config.schedule.value:
			if autoScheduleTimer is not None:
				print("[%s][doneConfiguring] Schedule Enabled at" % self.schedulename, strftime("%c", localtime(now)))
				autoScheduleTimer.scheduledate()
		else:
			if autoScheduleTimer is not None:
				self.ScheduleTime = 0
				print("[%s][doneConfiguring] Schedule Disabled at" % self.schedulename, strftime("%c", localtime(now)))
				autoScheduleTimer.schedulestop()
		# scheduletext is not used for anything but could be returned to the calling function to display in the GUI.
		if self.ScheduleTime > 0:
			t = localtime(self.ScheduleTime)
			scheduletext = strftime(_("%a %e %b  %-H:%M"), t)
		else:
			scheduletext = ""
		return scheduletext
