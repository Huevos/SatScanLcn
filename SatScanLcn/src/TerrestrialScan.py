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
from Components.NimManager import nimmanager
from enigma import eDVBFrontendParameters, eDVBFrontendParametersTerrestrial, eDVBResourceManager, eTimer, iFrontendInformation

import os
import sys

import datetime
import time

from . import dvbreader
from .downloadbar import downloadBar


def setParams(frequency, system, bandwidth=8): # freq is nine digits (474000000)
	params = eDVBFrontendParametersTerrestrial()
	params.frequency = frequency
#	params.bandwidth = terrestrialTransponderconvBandwidth_P(bandwidth * 1000000)
	params.bandwidth = bandwidth * 1000000 # for testing: feed in bandwidth value in hz as dpeddi reports failure to tune on some hardware with the previous code
	params.code_rate_hp = eDVBFrontendParametersTerrestrial.FEC_Auto
	params.code_rate_lp = eDVBFrontendParametersTerrestrial.FEC_Auto
	params.inversion = eDVBFrontendParametersTerrestrial.Inversion_Unknown
	params.system = system
	params.modulation = eDVBFrontendParametersTerrestrial.Modulation_Auto
	params.transmission_mode = eDVBFrontendParametersTerrestrial.TransmissionMode_Auto
	params.guard_interval = eDVBFrontendParametersTerrestrial.GuardInterval_Auto
	params.hierarchy = eDVBFrontendParametersTerrestrial.Hierarchy_Auto
	return params


def setParamsFe(params):
	params_fe = eDVBFrontendParameters()
	params_fe.setDVBT(params)
	return params_fe

def terrestrialTransponderconvBandwidth_P(_bandWidth):
	bandWidth = {
		8000000 : eDVBFrontendParametersTerrestrial.Bandwidth_8MHz,
		7000000 : eDVBFrontendParametersTerrestrial.Bandwidth_7MHz,
		6000000 : eDVBFrontendParametersTerrestrial.Bandwidth_6MHz,
		5000000 : eDVBFrontendParametersTerrestrial.Bandwidth_5MHz,
		1712000 : eDVBFrontendParametersTerrestrial.Bandwidth_1_712MHz,
		10000000 : eDVBFrontendParametersTerrestrial.Bandwidth_10MHz,
	}.get(_bandWidth, eDVBFrontendParametersTerrestrial.Bandwidth_8MHz)
	return bandWidth

def channel2freq(channel, bandwidth=8): # Europe channels
	if 4 < channel < 13: # Band III
		return (((177 + (bandwidth * (channel - 5))) * 1000000) + 500000)
	elif 20 < channel < 70: # Bands IV,V
		return ((474 + (bandwidth * (channel - 21))) * 1000000) # returns nine digits


def getChannelNumber(frequency, descr):
	f = (frequency + 50000) / 100000 / 10.
	if descr in ("uhf", "uhf_vhf"):
		if 174 < f < 230: 	# III
			d = (f + 1) % 7
			return str(int(f - 174) // 7 + 5) + (d < 3 and "-" or d > 4 and "+" or "")
		elif 470 <= f < 863: 	# IV,V
			d = (f + 2) % 8
			return str(int(f - 470) // 8 + 21) + (d < 3.5 and "-" or d > 4.5 and "+" or "")
	elif descr == "australia":
		if 174 < f < 202:	 # III: CH6-CH9
			return str(int(f - 174) // 7 + 6)
		elif 202 <= f < 209:	 # III: CH9A
			return "9A"
		elif 209 <= f < 230:	 # III: CH10-CH12
			return str(int(f - 209) // 7 + 10)
		elif 526 < f < 820:	 # IV, V: CH28-CH69
			return str(int(f - 526) // 7 + 28)
	return ""


class TerrestrialScan(Screen):
	skin = downloadBar()

	def __init__(self, session, args=0):
		self.debugName = self.__class__.__name__
		print("[%s][__init__] Starting..." % self.debugName)
		print("[%s][__init__] args" % self.debugName, args)
		self.session = session
		Screen.__init__(self, session)
		Screen.setTitle(self, _("TerrestrialScan"))

		self["background"] = Pixmap()
		self["action"] = Label(_("Starting scanner"))
		self["status"] = Label("")
		self["progress"] = ProgressBar()
		self["progress_text"] = Progress()
		self["tuner_text"] = Label("")

		self["actions"] = ActionMap(["SetupActions"],
		{
			"cancel": self.keyCancel,
		}, -2)

		self.selectedNIM = -1
		self.uhf_vhf = "uhf"
		self.networkid = 0
		self.restrict_to_networkid = False
		self.stabliseTime = 2 # time in seconds for tuner to stablise on tune before taking a signal quality reading
		self.region = None
		self.country = None
		self.skipT2 = False
		if args:
			if "feid" in args:
				self.selectedNIM = args["feid"]
			if "uhf_vhf" in args:
				self.uhf_vhf = args["uhf_vhf"]
			if "networkid" in args:
				self.networkid = args["networkid"]
			if "restrict_to_networkid" in args:
				self.restrict_to_networkid = args["restrict_to_networkid"]
			if "stabliseTime" in args:
				self.stabliseTime = args["stabliseTime"]
			if "region" in args:
				self.region = args["region"]
			if "country" in args:
				self.country = args["country"]
			if "skipT2" in args:
				self.skipT2 = args["skipT2"]
		self.isT2tuner = False
		self.frontend = None
		self["Frontend"] = FrontendStatus(frontend_source=lambda: self.frontend, update_interval=100)
		self.rawchannel = None
		self.session.postScanService = self.session.nav.getCurrentlyPlayingServiceOrGroup()
		self.index = 0
		self.frequency = 0
		self.system = eDVBFrontendParametersTerrestrial.System_DVB_T
		self.lockTimeout = 50 	# 100ms for tick - 5 sec
		self.tsidOnidTimeout = 100 	# 100ms for tick - 10 sec
		self.snrTimeout = 100 	# 100ms for tick - 10 sec
		self.bandwidth = 8 # MHz
		self.scanTransponders = []
		systems = (eDVBFrontendParametersTerrestrial.System_DVB_T,) if self.skipT2 else (eDVBFrontendParametersTerrestrial.System_DVB_T, eDVBFrontendParametersTerrestrial.System_DVB_T2)
		if self.uhf_vhf == "uhf_vhf":
			bandwidth = 7
			for a in range(5, 13):
				for b in systems: # system
					self.scanTransponders.append({"frequency": channel2freq(a, bandwidth), "system": b, "bandwidth": bandwidth})
		if self.uhf_vhf in ("uhf", "uhf_short", "uhf_vhf"):
			bandwidth = 8
			for a in range(21, 50 if self.uhf_vhf == "uhf_short" else 70):
				for b in systems: # system
					self.scanTransponders.append({"frequency": channel2freq(a, bandwidth), "system": b, "bandwidth": bandwidth})
		if self.uhf_vhf == "australia":
			bandwidth = 7
			base_frequency = 177500000
			for a in list(range(0, 8)) + list(range(50, 74)):
				freq = (base_frequency + (a * bandwidth * 1000000 + (2000000 if a > 8 else 0)))
				self.scanTransponders.append({"frequency": freq, "system": eDVBFrontendParametersTerrestrial.System_DVB_T, "bandwidth": bandwidth})
		if self.uhf_vhf == "xml":
			# frequency 1, inversion 9, bandwidth 2, fechigh 4, feclow 5, modulation 3, transmission 7, guard 6, hierarchy 8, system 10, plp_id 1
			for tp in nimmanager.getTranspondersTerrestrial(self.region):
				# system contains "-1" when both DVB-T and DVB-T2 are to be scanned
				if tp[10] < 1: # DVB-T
					self.scanTransponders.append({"frequency": tp[1], "system": eDVBFrontendParametersTerrestrial.System_DVB_T, "bandwidth": tp[2] // 1000000})
				if tp[10] != 0: # DVB-T2
					self.scanTransponders.append({"frequency": tp[1], "system": eDVBFrontendParametersTerrestrial.System_DVB_T2, "bandwidth": tp[2] // 1000000})
		self.transponders_found = []
		self.transponders_unique = {}
		self.onClose.append(self.__onClose)
		self.onFirstExecBegin.append(self.firstExec)

	def showError(self, message):
		question = self.session.open(MessageBox, message, MessageBox.TYPE_ERROR)
		question.setTitle(_("TerrestrialScan"))
		self.close()

	def keyCancel(self):
		self.close()

	def firstExec(self):
		if len(self.scanTransponders) > 0:
			self["action"].setText(_('Starting search...'))
			self["status"].setText(_("Scanning for active transponders"))
			self.progresscount = len(self.scanTransponders)
			self.progresscurrent = 1
			self["progress_text"].range = self.progresscount
			self["progress_text"].value = self.progresscurrent
			self["progress"].setRange((0, self.progresscount))
			self["progress"].setValue(self.progresscurrent)
			self.timer = eTimer()
			self.timer.callback.append(self.search)
			self.timer.start(100, 1)
		else:
			self.showError(_('No frequencies to search'))

	def search(self):
		self["tuner_text"].setText("")
		if self.index < len(self.scanTransponders):
			self.system = self.scanTransponders[self.index]["system"]
			self.bandwidth = self.scanTransponders[self.index]["bandwidth"]
			self.frequency = self.scanTransponders[self.index]["frequency"]
			channelNumber = getChannelNumber(self.frequency, self.uhf_vhf == "xml" and ("australia" if self.country == "AUS"  else "uhf") or self.uhf_vhf)
			self.channelNumberText = (_("(ch %s)") % channelNumber) if channelNumber else ""
			print("[%s][Search] Scan frequency %d %s" % (self.debugName, self.frequency, self.channelNumberText))
			print("[%s][Search] Scan system %d" % (self.debugName, self.system))
			print("[%s][Search] Scan bandwidth %d" % (self.debugName, self.bandwidth))
			self.progresscurrent = self.index
			self["progress_text"].value = self.progresscurrent
			self["progress"].setValue(self.progresscurrent)
			self["action"].setText(_("Tuning %s MHz %s") % (str(self.frequency // 1000000), self.channelNumberText))
			self["status"].setText((len(self.transponders_unique) == 1 and _("Found %d unique transponder") or _("Found %d unique transponders")) % len(self.transponders_unique))
			self.index += 1
			if self.frequency in self.transponders_found or self.system == eDVBFrontendParametersTerrestrial.System_DVB_T2 and self.isT2tuner == False:
				print("[%s][Search] Skipping T2 search of %s MHz %s" % (self.debugName, str(self.frequency // 1000000), self.channelNumberText))
				self.search()
				return
			self.searchtimer = eTimer()
			self.searchtimer.callback.append(self.getFrontend)
			self.searchtimer.start(100, 1)
		else:
			if len(self.transponders_unique) > 0:
				answer = [self.selectedNIM, self.transponders_unique]
			else:
				answer = None
			self.close(answer)

	def config_mode(self, nim): # Workaround for OpenATV > 5.3
		try:
			return nim.config_mode
		except AttributeError:
			return nim.isCompatible("DVB-T") and nim.config_mode_dvbt or "nothing"

	def getFrontend(self):
		print("[%s][getFrontend] searching for available tuner" % self.debugName)
		nimList = []
		if self.selectedNIM < 0: # automatic tuner selection
			for nim in nimmanager.nim_slots:
				if self.config_mode(nim) not in ("nothing",) and (nim.isCompatible("DVB-T2") or (nim.isCompatible("DVB-S") and nim.canBeCompatible("DVB-T2"))):
					nimList.append(nim.slot)
					self.isT2tuner = True
			if len(nimList) == 0:
				print("[%s][getFrontend] No T2 tuner found" % self.debugName)
				for nim in nimmanager.nim_slots:
					if self.config_mode(nim) not in ("nothing",) and (nim.isCompatible("DVB-T") or (nim.isCompatible("DVB-S") and nim.canBeCompatible("DVB-T"))):
						nimList.append(nim.slot)
			if len(nimList) == 0:
				print("[%s][getFrontend] No terrestrial tuner found" % self.debugName)
				self.showError(_('No terrestrial tuner found'))
				return
		else: # manual tuner selection, and subsequent iterations
			nim = nimmanager.nim_slots[self.selectedNIM]
			if self.config_mode(nim) not in ("nothing",) and (nim.isCompatible("DVB-T2") or (nim.isCompatible("DVB-S") and nim.canBeCompatible("DVB-T2"))):
				nimList.append(nim.slot)
				self.isT2tuner = True
			if len(nimList) == 0:
				print("[%s][getFrontend] User selected tuner is not T2 compatible" % self.debugName)
				if self.config_mode(nim) not in ("nothing",) and (nim.isCompatible("DVB-T") or (nim.isCompatible("DVB-S") and nim.canBeCompatible("DVB-T"))):
					nimList.append(nim.slot)
			if len(nimList) == 0:
				print("[%s][getFrontend] User selected tuner not configured" % self.debugName)
				self.showError(_('Selected tuner is not cofigured'))
				return

		if len(nimList) == 0:
			print("[%s][getFrontend] No terrestrial tuner found" % self.debugName)
			self.showError(_('No terrestrial tuner found'))
			return

		resmanager = eDVBResourceManager.getInstance()
		if not resmanager:
			print("[%s][getFrontend] Cannot retrieve Resource Manager instance" % self.debugName)
			self.showError(_('Cannot retrieve Resource Manager instance'))
			return

		if self.selectedNIM < 0: # automatic tuner selection
			print("[%s][getFrontend] Choosing NIM" % self.debugName)

		# stop pip if running
		if self.session.pipshown:
			self.session.pipshown = False
			del self.session.pip
			print("[%s][getFrontend] Stopping PIP." % self.debugName)

		# Find currently playin NIM
		currentlyPlayingNIM = None
		currentService = self.session and self.session.nav.getCurrentService()
		frontendInfo = currentService and currentService.frontendInfo()
		frontendData = frontendInfo and frontendInfo.getAll(True)
		if frontendData is not None:
			currentlyPlayingNIM = frontendData.get("tuner_number", None)
		del frontendInfo
		del currentService

		current_slotid = -1
		if self.rawchannel:
			del(self.rawchannel)

		self.frontend = None
		self.rawchannel = None

		nimList.reverse() # start from the last
		for slotid in nimList:
			if current_slotid == -1:	# mark the first valid slotid in case of no other one is free
				current_slotid = slotid
			self.rawchannel = resmanager.allocateRawChannel(slotid)
			if self.rawchannel:
				print("[%s][getFrontend] Nim found on slot id %d" % (self.debugName, slotid))
				current_slotid = slotid
				break

		if current_slotid == -1:
			print("[%s][getFrontend] No valid NIM found" % self.debugName)
			self.showError(_('No valid NIM found for terrestrial'))
			return

		if not self.rawchannel:
			# if we are here the only possible option is to close the active service
			if currentlyPlayingNIM in nimList:
				slotid = currentlyPlayingNIM
				print("[%s][getFrontend] Nim found on slot id %d but it's busy. Stopping active service" % (self.debugName, slotid))
				self.session.postScanService = self.session.nav.getCurrentlyPlayingServiceReference()
				self.session.nav.stopService()
				self.rawchannel = resmanager.allocateRawChannel(slotid)
				if self.rawchannel:
					print("[%s][getFrontend] The active service was stopped, and the NIM is now free to use." % self.debugName)
					current_slotid = slotid

			if not self.rawchannel:
				if self.session.nav.RecordTimer.isRecording():
					print("[%s][getFrontend] Cannot free NIM because a recording is in progress" % self.debugName)
					self.showError(_("Cannot free NIM because a recording is in progress"))
					return
				else:
					print("[%s][getFrontend] Cannot get the NIM" % self.debugName)
					self.showError(_("Cannot get the NIM"))
					return

		print("[%s][getFrontend] Will wait up to %i seconds for tuner lock." % (self.debugName, self.lockTimeout // 10))

		self.selectedNIM = current_slotid # Remember for next iteration

		self["tuner_text"].setText(chr(ord('A') + current_slotid))

		self.frontend = self.rawchannel.getFrontend()
		if not self.frontend:
			print("[%s][getFrontend] Cannot get frontend" % self.debugName)
			self.showError(_("Cannot get frontend"))
			return

		self.rawchannel.requestTsidOnid()

		self.tsid = None
		self.onid = None

		self.demuxer_id = self.rawchannel.reserveDemux()
		if self.demuxer_id < 0:
			print("[%s][getFrontend] Cannot allocate the demuxer" % self.debugName)
			self.showError(_("Cannot allocate the demuxer"))
			return

		self.frontend.tune(setParamsFe(setParams(self.frequency, self.system, self.bandwidth)))

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
			print("[%s][checkTunerLock] LOCKED" % self.debugName)
			self["action"].setText(_("Reading %s MHz %s") % (str(self.frequency // 1000000), self.channelNumberText))
			self.tsidOnidtimer = eTimer()
			self.tsidOnidtimer.callback.append(self.tsidOnidWait)
			self.tsidOnidtimer.start(100, 1)
			return
		elif self.dict["tuner_state"] in ("LOSTLOCK", "FAILED"):
			print("[%s][checkTunerLock] TUNING FAILED" % self.debugName)
			self.search()
			return

		self.lockcounter += 1
		if self.lockcounter > self.lockTimeout:
			print("[%s][checkTunerLock] Timeout for tuner lock" % self.debugName)
			self.search()
			return
		self.locktimer.start(100, 1)

	def tsidOnidWait(self):
		self.getCurrentTsidOnid()
		if self.tsid is not None and self.onid is not None:
			print("[%s][tsidOnidWait] tsid & onid found" % self.debugName, self.tsid, self.onid)
			self.signalQualityCounter = 0
			self.signalQualitytimer = eTimer()
			self.signalQualitytimer.callback.append(self.signalQualityWait)
			self.signalQualitytimer.start(100, 1)
			return

		print("[%s][tsidOnidWaitABM] tsid & onid wait failed" % self.debugName)
		self.search()
		return

	def getCurrentTsidOnid(self, from_retune=False):
		adapter = 0
		demuxer_device = "/dev/dvb/adapter%d/demux%d" % (adapter, self.demuxer_id)
		start = time.time() # for debug info

		sdt_pid = 0x11
		sdt_current_table_id = 0x42
		mask = 0xff
		tsidOnidTimeout = 5 # maximum time allowed to read the service descriptor table (seconds)
		self.tsid = None
		self.onid = None

		fd = dvbreader.open(demuxer_device, sdt_pid, sdt_current_table_id, mask, self.selectedNIM)
		if fd < 0:
			print("[%s][getCurrentTsidOnid] Cannot open the demuxer" % self.debugName)
			return None

		timeout = datetime.datetime.now()
		timeout += datetime.timedelta(0, tsidOnidTimeout)

		while True:
			if datetime.datetime.now() > timeout:
				print("[%s][getCurrentTsidOnid] Timed out" % self.debugName)
				break

			section = dvbreader.read_sdt(fd, sdt_current_table_id, 0x00)
			if section is None:
				time.sleep(0.1)	# no data.. so we wait a bit
				continue

			if section["header"]["table_id"] == sdt_current_table_id:
				self.tsid = section["header"]["transport_stream_id"]
				self.onid = section["header"]["original_network_id"]
				break

		print("[%s][getCurrentTsidOnid] Read time %.1f seconds." % (self.debugName, time.time() - start))
		dvbreader.close(fd)

	def signalQualityWait(self):
		signalQuality = self.frontend.readFrontendData(iFrontendInformation.signalQuality)
		if signalQuality > 0:
			time.sleep(self.stabliseTime) # allow extra time to get a stable reading
			signalQuality = self.frontend.readFrontendData(iFrontendInformation.signalQuality)
			if signalQuality > 0:
				found = {"frequency": self.frequency, "tsid": self.tsid, "onid": self.onid, "system": self.system, "bandwidth": self.bandwidth, "signalQuality": signalQuality}
				self.transponders_found.append(self.frequency)
				tsidOnidKey = "%x:%x" % (self.tsid, self.onid)
				if (tsidOnidKey not in self.transponders_unique or self.transponders_unique[tsidOnidKey]["signalQuality"] < signalQuality) and (not self.restrict_to_networkid or self.networkid == self.onid):
					self.transponders_unique[tsidOnidKey] = found
				print("[%s][signalQualityWait] transponder details" % self.debugName, found)
				self.search()
				return

		self.signalQualityCounter += 1
		if self.signalQualityCounter > self.snrTimeout:
			print("[%s][signalQualityWait] Failed to collect SNR" % self.debugName)
			self.search()
			return
		self.signalQualitytimer.start(100, 1)

	def __onClose(self):
		if self.frontend:
			self.frontend = None
			del(self.rawchannel)
