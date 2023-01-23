from . import _

from Screens.Screen import Screen
from Components.Label import Label
from Components.ActionMap import ActionMap
from Components.Sources.StaticText import StaticText
from Components.NimManager import nimmanager
from Components.config import config, configfile, ConfigSelection, getConfigListEntry
from Components.ConfigList import ConfigListScreen
from Screens.MessageBox import MessageBox
from Screens.ServiceScan import ServiceScan

from enigma import eComponentScan

from .TerrestrialScan import TerrestrialScan, setParams
from .MakeTerrestrialBouquet import MakeTerrestrialBouquet


class TerrestrialScan_Setup(ConfigListScreen, Screen):
	def __init__(self, session):
		self.config = config.plugins.TerrestrialScan
		Screen.__init__(self, session)
		self.setup_title = _('TerrestrialScan Setup')
		Screen.setTitle(self, self.setup_title)
		self.skinName = ["TerrestrialScan_Setup", "Setup"]
		self.onChangedEntry = []
		self.session = session
		ConfigListScreen.__init__(self, [], session=session, on_change=self.changedEntry)

		self["actions2"] = ActionMap(["SetupActions"],
		{
			"menu": self.keyCancel,
			"cancel": self.keyCancel,
			"save": self.keyGo,
		}, -2)

		self["key_red"] = StaticText(_("Exit"))
		self["key_green"] = StaticText(_("Scan"))

		self["description"] = Label("")

		self.transponders_unique = {}
		self.session.postScanService = self.session.nav.getCurrentlyPlayingServiceOrGroup()

		self.dvbt_capable_nims = []
		for nim in nimmanager.nim_slots:
			if self.config_mode(nim) != "nothing":
				if nim.isCompatible("DVB-T") or (nim.isCompatible("DVB-S") and nim.canBeCompatible("DVB-T")):
					self.dvbt_capable_nims.append(nim.slot)

		nim_list = []
		nim_list.append((-1, _("Automatic")))
		for x in self.dvbt_capable_nims:
			nim_list.append((nimmanager.nim_slots[x].slot, nimmanager.nim_slots[x].friendly_full_description))
		self.scan_nims = ConfigSelection(choices=nim_list)

		self.createSetup()

		if not self.selectionChanged in self["config"].onSelectionChanged:
			self["config"].onSelectionChanged.append(self.selectionChanged)
		self.selectionChanged()

	def createSetup(self):
		self.indent = "- "
		setup_list = []
		setup_list.append(getConfigListEntry(_("Tuner"), self.scan_nims, _('Select a tuner that is configured for terrestrial scans. "Automatic" will pick the highest spec available tuner.')))
		setup_list.append(getConfigListEntry(_("Bandplan"), self.config.uhf_vhf, _('Most transmitters in European countries only have TV channels in the UHF band. Select "UHF Europe channels 21-49" in countries that are now using channels 50+ for GSM. Select "From XML" to access bandplans that are preloaded on the device.')))

		if self.config.uhf_vhf.value == "xml":
			self.setTerrestrialLocationEntries()
			setup_list.append(self.terrestrialCountriesEntry)
			setup_list.append(self.terrestrialRegionsEntry)

		setup_list.append(getConfigListEntry(_("Clear before scan"), self.config.clearallservices, _('If you select "yes" all stored terrestrial channels will be deleted before starting the current search.')))
		if self.config.uhf_vhf.value not in ("australia",):
			setup_list.append(getConfigListEntry(_("Skip T2"), self.config.skipT2, _('If you know for sure there are no T2 multiplexes in your area select yes. This will speed up scan time.')))
		setup_list.append(getConfigListEntry(_("Only free scan"), self.config.onlyfree, _('If you select "yes" the scan will only save channels that are not encrypted; "no" will find encrypted and non-encrypted channels.')))
		setup_list.append(getConfigListEntry(_('Restrict search to single ONID'), self.config.networkid_bool, _('Select "Yes" to restrict the search to multiplexes that belong to a single original network ID (ONID). Select "No" to search all ONIDs.')))

		if self.config.networkid_bool.value:
			setup_list.append(getConfigListEntry(self.indent + _('ONID to search'), self.config.networkid, _('Enter the original network ID (ONID) of the multiplexes you wish to restrict the search to. UK terrestrial television normally ONID "9018".')))

		setup_list.append(getConfigListEntry(_("Create terrestrial bouquet"), self.config.makebouquet, _('If you select "yes" and LCNs are found in the NIT, the scan will create a bouquet of terrestrial channels in LCN order and add it to the bouquet list.')))
		if self.config.makebouquet.value:
			setup_list.append(getConfigListEntry(self.indent + _("Create separate radio bouquet"), self.config.makeradiobouquet, _('If you select "yes" and radio services are fond these will be place in a separate bouquet. Otherwise TV and radio services will be placed in a combined bouquet.')))
			setup_list.append(getConfigListEntry(self.indent + _("LCN Descriptor"), self.config.lcndescriptor, _('Select the LCN descriptor used in your area. 0x83 is the default DVB standard descriptor. 0x87 is used in some Scandinavian countries.')))
			if self.config.lcndescriptor.value == 0x87:
				setup_list.append(getConfigListEntry(self.indent + self.indent + _("Channel list ID"), self.config.channel_list_id, _('Enter channel list ID used in your area. If you are not sure enter zero.')))

		if self.config.uhf_vhf.value != "xml":
			setup_list.append(getConfigListEntry(_("Create terrestrial.xml file"), self.config.makexmlfile, _('Select "yes" to create a custom terrestrial.xml file and install it in /etc/enigma2 for system scans to use.')))
		setup_list.append(getConfigListEntry(_("Signal quality stabisation time (secs)"), self.config.stabliseTime, _('Period of time to wait for the tuner to stabalise before taking a signal quality reading. 2 seconds is good for most hardware but some may require longer.')))

		self["config"].list = setup_list
		self["config"].l.setList(setup_list)

	def setTerrestrialLocationEntries(self):
		slotid = self.dvbt_capable_nims[0] if self.scan_nims.value < 0 else self.scan_nims.value # number of first enabled terrestrial tuner if automatic is selected.
		nimConfig = nimmanager.nim_slots[slotid].config

		# country
		if not hasattr(self, "terrestrialCountriesEntry"):
			terrestrialcountrycodelist = nimmanager.getTerrestrialsCountrycodeList()
			terrestrialcountrycode = nimmanager.getTerrestrialCountrycode(slotid) # number of first enabled terrestrial tuner if automatic is selected.
			default = terrestrialcountrycode in terrestrialcountrycodelist and terrestrialcountrycode or None
			choices = [("all", _("All"))] + sorted([(x, self.countrycodeToCountry(x)) for x in terrestrialcountrycodelist], key=lambda listItem: listItem[1])
			self.terrestrialCountries = ConfigSelection(default=default, choices=choices)
			self.terrestrialCountriesEntry = getConfigListEntry(self.indent + _("Country"), self.terrestrialCountries, _("Select your country. If not available select 'all'."))

		# region
		if self.terrestrialCountries.value == "all":
			terrstrialNames = [x[0] for x in sorted(sorted(nimmanager.getTerrestrialsList(), key=lambda listItem: listItem[0]), key=lambda listItem: self.countrycodeToCountry(listItem[2]))]
		else:
			terrstrialNames = sorted([x[0] for x in nimmanager.getTerrestrialsByCountrycode(self.terrestrialCountries.value)])
		try:
			NConfig = nimConfig.terrestrial.value
		except:
			NConfig = nimConfig.dvbt.terrestrial.value

		default = NConfig in terrstrialNames and NConfig or None
		self.terrestrialRegions = ConfigSelection(default=default, choices=terrstrialNames)
		self.terrestrialRegionsEntry = getConfigListEntry(self.indent + _("Region"), self.terrestrialRegions, _("Select your region. If not available change 'Country' to 'all' and select one of the default alternatives."))

	def countrycodeToCountry(self, cc):
		if not hasattr(self, 'countrycodes'):
			self.countrycodes = {}
			from Tools.CountryCodes import ISO3166
			for country in ISO3166:
				self.countrycodes[country[2]] = country[0]
		if cc.upper() in self.countrycodes:
			return self.countrycodes[cc.upper()]
		return cc

	def selectionChanged(self):
		self["description"].setText(self["config"].getCurrent()[2])

	# for summary:
	def changedEntry(self):
		for x in self.onChangedEntry:
			x()

	def getCurrentEntry(self):
		return self["config"].getCurrent()[0]

	def getCurrentValue(self):
		return str(self["config"].getCurrent()[1].getText())

	def createSummary(self):
		from Screens.Setup import SetupSummary
		return SetupSummary

	def keyGo(self):
#		self.config.save()
		for x in self["config"].list:
			x[1].save()
		configfile.save()
		self.startScan()

	def startScan(self):
		args = {"feid": int(self.scan_nims.value), "uhf_vhf": self.config.uhf_vhf.value, "networkid": int(self.config.networkid.value), "restrict_to_networkid": self.config.networkid_bool.value, "stabliseTime": self.config.stabliseTime.value, "skipT2": self.config.skipT2.value}
		if self.config.uhf_vhf.value == "xml":
			args["country"] = self.terrestrialCountries.value
			args["region"] = self.terrestrialRegions.value
		self.session.openWithCallback(self.terrestrialScanCallback, TerrestrialScan, args)

	def keyCancel(self):
		if self["config"].isChanged():
			self.session.openWithCallback(self.cancelCallback, MessageBox, _("Really close without saving settings?"))
		else:
			self.cancelCallback(True)

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)
		self.newConfig()

	def keyRight(self):
		ConfigListScreen.keyRight(self)
		self.newConfig()

	def newConfig(self):
		cur = self["config"].getCurrent()
		if len(cur) > 1:
			if cur[1] in (self.config.uhf_vhf, getattr(self, "terrestrialCountries", None), self.config.networkid_bool, self.config.makebouquet, self.config.lcndescriptor):
				self.createSetup()

	def cancelCallback(self, answer):
		if answer:
			for x in self["config"].list:
				x[1].cancel()
			self.close(False)

	def terrestrialScanCallback(self, answer=None):
		print("[terrestrialScanCallback] answer", answer)
		if answer:
			self.feid = answer[0]
			self.transponders_unique = answer[1]
			if self.config.makebouquet.value or self.config.makexmlfile.value:
				self.session.openWithCallback(self.MakeBouquetCallback, MakeTerrestrialBouquet, {"feid": self.feid, "transponders_unique": self.transponders_unique, "FTA_only": self.config.onlyfree.value, "makebouquet": self.config.makebouquet.value, "makexmlfile": self.config.makexmlfile.value, "lcndescriptor": self.config.lcndescriptor.value, "channel_list_id": self.config.channel_list_id.value})
			else:
				self.doServiceSearch()
		else:
			self.session.nav.playService(self.session.postScanService)

	def MakeBouquetCallback(self, answer=None):
		print("[MakeBouquetCallback] answer", answer)
		if answer:
			self.feid = answer[0]
			self.transponders_unique = answer[1]
			self.doServiceSearch()
		else:
			self.session.nav.playService(self.session.postScanService)

	def doServiceSearch(self):
		tlist = []
		for transponder in self.transponders_unique:
			tlist.append(setParams(self.transponders_unique[transponder]["frequency"], self.transponders_unique[transponder]["system"], self.transponders_unique[transponder]["bandwidth"]))
		self.startServiceSearch(tlist, self.feid)

	def startServiceSearch(self, tlist, feid):
		flags = 0
		if self.config.clearallservices.value:
			flags |= eComponentScan.scanRemoveServices
		else:
			flags |= eComponentScan.scanDontRemoveUnscanned
		if self.config.onlyfree.value:
			flags |= eComponentScan.scanOnlyFree
		networkid = 0
		self.session.openWithCallback(self.startServiceSearchCallback, ServiceScan, [{"transponders": tlist, "feid": feid, "flags": flags, "networkid": networkid}])

	def startServiceSearchCallback(self, answer=None):
		self.session.nav.playService(self.session.postScanService)
		if answer:
			self.close(True)

	def config_mode(self, nim): # Workaround for OpenATV > 5.3
		try:
			return nim.config_mode
		except AttributeError:
			return nim.isCompatible("DVB-T") and nim.config_mode_dvbt or "nothing"